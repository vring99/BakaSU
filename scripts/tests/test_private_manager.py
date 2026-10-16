"""Checks the identity boundary shared by built-in and modular kernels."""

import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("private_manager", ROOT / "scripts/private_manager.py")
PRIVATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRIVATE)


def clang_path():
    compiler = shutil.which("clang")
    sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if not compiler and sdk:
        candidates = sorted(Path(sdk).glob("ndk/*/toolchains/llvm/prebuilt/*/bin/clang.exe"))
        if candidates:
            compiler = str(candidates[-1])
    return compiler


class PrivateManagerTests(unittest.TestCase):
    def test_public_certificate_matches_kernel(self):
        certificate = (ROOT / "docs/private-manager-cert.der").read_bytes()
        PRIVATE.check_certificate(certificate)
        with self.assertRaises(ValueError):
            PRIVATE.check_certificate(certificate[:-1] + bytes([certificate[-1] ^ 1]))

    def test_only_private_signer_in_gki_and_lkm_even_if_multi_manager_is_enabled(self):
        compiler = clang_path()
        if not compiler:
            self.skipTest("clang is required for the kernel whitelist compile check")
        source = (ROOT / "kernel/manager/apk_sign.c").read_text(encoding="utf-8")
        match = re.search(r"static apk_sign_key_t apk_sign_keys\[\] = \{.*?\n\};", source, re.S)
        self.assertIsNotNone(match)
        header = (ROOT / "kernel/manager/manager_sign.h").as_posix()
        unit = f'#include "{header}"\n{match[0]}\n'
        unit += '_Static_assert(sizeof(apk_sign_keys)/sizeof(apk_sign_keys[0]) == 1, "Unexpected trusted manager");\n'
        unit += '_Static_assert(EXPECTED_SIZE_BAKASU <= 1024, "Certificate is too large");\n'
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "identity.c"
            file.write_text(unit, encoding="utf-8")
            for mode, mode_flags in [
                ("GKI", ["-DCONFIG_KSU=1"]),
                ("LKM", ["-DCONFIG_KSU_MODULE=1", "-DMODULE=1"]),
            ]:
                for multi in (False, True):
                    with self.subTest(mode=mode, multi_manager=multi):
                        flags = mode_flags + (["-DCONFIG_KSU_MULTI_MANAGER_SUPPORT=1"] if multi else [])
                        subprocess.run([compiler, "-std=c11", "-fsyntax-only", *flags, str(file)], check=True)

    def test_package_selection_and_validation(self):
        self.assertEqual(PRIVATE.select_package(" com.example.pro "), "com.example.pro")
        first, second = PRIVATE.select_package(), PRIVATE.select_package()
        self.assertNotEqual(first, second)
        for package in (first, second):
            self.assertRegex(package, r"^[a-z]{8}\.[a-z]{8}\.[a-z]{8}$")
        for package in ("bad package", "com.example.$(cmd)", "com..example", "single"):
            with self.subTest(package=package), self.assertRaises(ValueError):
                PRIVATE.select_package(package)

    def test_ci_forwards_one_package_to_manager_and_ksud(self):
        import yaml

        workflow = yaml.safe_load((ROOT / ".github/workflows/build-private-manager.yml").read_text())
        jobs = workflow["jobs"]
        self.assertEqual(jobs["build-ksud"]["with"]["manager_package"], "${{ needs.prepare.outputs.package_name }}")
        step = next(step for step in jobs["build-manager"]["steps"] if step.get("name") == "Build and verify manager")
        self.assertEqual(step["env"]["MANAGER_PACKAGE"], "${{ needs.prepare.outputs.package_name }}")
        daemon = yaml.safe_load((ROOT / ".github/workflows/ksud.yml").read_text())
        build = next(step for step in daemon["jobs"]["build"]["steps"] if step.get("name") == "Build ksud")
        self.assertEqual(build["env"]["KSU_PACKAGE_NAME"], "${{ inputs.manager_package }}")

    def test_legacy_and_release_entrypoints_use_private_build(self):
        import yaml

        legacy = yaml.safe_load((ROOT / ".github/workflows/build-manager.yml").read_text())
        # YAML 1.1 parses the unquoted GitHub Actions "on" key as True.
        self.assertEqual(set(legacy.get("on", legacy.get(True))), {"workflow_call"})
        for workflow in (legacy, yaml.safe_load((ROOT / ".github/workflows/release.yml").read_text())):
            build = workflow["jobs"]["build-manager"]
            self.assertEqual(build["uses"], "./.github/workflows/build-private-manager.yml")
            self.assertIn("inputs.package_name", build["with"]["package_name"])
            self.assertEqual(build["secrets"], "inherit")

    def test_github_secrets_use_stdin_and_check_certificate_before_upload(self):
        with tempfile.TemporaryDirectory() as directory:
            keystore = Path(directory) / "key.jks"
            keystore.write_bytes(b"test keystore")
            properties = Path(directory) / "signing.properties"
            properties.write_text(
                f"KEYSTORE_FILE={keystore.as_posix()}\nKEYSTORE_PASSWORD=store-secret\n"
                "KEY_ALIAS=private-alias\nKEY_PASSWORD=key-secret\n", encoding="utf-8")
            certificate = (ROOT / "docs/private-manager-cert.der").read_bytes()
            with mock.patch.object(PRIVATE.shutil, "which", side_effect=lambda name: name), \
                    mock.patch.object(PRIVATE.subprocess, "check_output", return_value=certificate) as export, \
                    mock.patch.object(PRIVATE.subprocess, "run") as run, \
                    mock.patch("builtins.print"):
                PRIVATE.configure_github_secrets("example/private-manager", properties)
                self.assertIn("-storepass:env", export.call_args.args[0])
                self.assertNotIn("store-secret", export.call_args.args[0])
                uploads = [call for call in run.call_args_list if call.args[0][1:3] == ["secret", "set"]]
                self.assertEqual(len(uploads), 4)
                self.assertEqual({call.args[0][3] for call in uploads},
                                 {"KEYSTORE", "KEYSTORE_PASSWORD", "KEY_ALIAS", "KEY_PASSWORD"})
                for call in uploads:
                    self.assertEqual(call.args[0][-2:], ["--repo", "example/private-manager"])
                    self.assertNotIn(call.kwargs["input"], call.args[0])
                export.return_value = b"wrong certificate"
                run.reset_mock()
                with self.assertRaises(ValueError):
                    PRIVATE.configure_github_secrets("example/private-manager", properties)
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
