"""Check the external Gradle/repack invocation contract, not compilation itself."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest import mock

from test_private_manager import PRIVATE, ROOT


class ReleaseRecipeTests(unittest.TestCase):
    def test_assemble_uses_official_arguments_and_keeps_secrets_out_of_argv(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "manager/app/build/outputs/apk/release"
            output.mkdir(parents=True)
            (output / "fixture.apk").write_bytes(b"not a real APK")
            properties = root / "signing.properties"
            properties.write_text(
                "KEYSTORE_FILE=fixture.jks\nKEYSTORE_PASSWORD=store-secret\n"
                "KEY_ALIAS=private-alias\nKEY_PASSWORD=key-secret\n", encoding="utf-8")
            with mock.patch.object(PRIVATE, "ROOT", root), \
                    mock.patch.object(PRIVATE.subprocess, "check_output", return_value="a" * 40 + "\n"), \
                    mock.patch.object(PRIVATE.subprocess, "run") as run, \
                    mock.patch.object(PRIVATE, "verify_apk", return_value={}), \
                    mock.patch("builtins.print"):
                PRIVATE.build_manager("com.example.pro", properties)
            calls = run.call_args_list
            self.assertEqual(len(calls), 2, "Validation must be separate from official assembleRelease")
            prefix = [str(root / "manager/gradlew.bat")] if os.name == "nt" else ["bash", "./gradlew"]
            arguments = ["-Pcommit=" + "a" * 40, "-PKSU_PACKAGE_NAME=com.example.pro", "-PKSU_NAME=BakaSU Pro"]
            self.assertEqual(calls[0].args[0], prefix + ["spotlessCheck", "testDebugUnitTest", "lintRelease"] + arguments)
            self.assertEqual(calls[1].args[0], prefix + ["assembleRelease"] + arguments)
            for call in calls:
                self.assertTrue(call.kwargs["check"])
                self.assertEqual(call.kwargs["cwd"], root / "manager")
                self.assertEqual(call.kwargs["env"]["ORG_GRADLE_PROJECT_KEY_PASSWORD"], "key-secret")
                self.assertNotIn("key-secret", " ".join(call.args[0]))
                self.assertNotIn("store-secret", " ".join(call.args[0]))

    def test_failed_validation_never_assembles_or_verifies(self):
        with mock.patch.object(PRIVATE, "read_signing_properties", return_value={}), \
                mock.patch.object(PRIVATE.subprocess, "check_output", return_value="a" * 40), \
                mock.patch.object(PRIVATE.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "gradle")) as run, \
                mock.patch.object(PRIVATE, "verify_apk") as verify:
            with self.assertRaises(subprocess.CalledProcessError):
                PRIVATE.build_manager("com.example.pro", Path("unused.properties"))
            self.assertEqual(len(run.call_args_list), 1)
            self.assertNotIn("assembleRelease", run.call_args.args[0])
            verify.assert_not_called()

    def test_final_repack_requests_official_release_strip_for_all_abis(self):
        import yaml

        workflow = yaml.safe_load((ROOT / ".github/workflows/build-private-manager.yml").read_text())
        step = next(step for step in workflow["jobs"]["repack"]["steps"]
                    if step.get("name") == "Pack ksud with private LKM files and resign")
        command = shlex.split(step["run"].replace("\\\n", " "))
        self.assertIn("--strip", command)
        self.assertNotIn("--no-strip", command)
        self.assertEqual([command[i + 1] for i, value in enumerate(command) if value == "-a"],
                         ["arm64-v8a", "armeabi-v7a", "x86_64", "riscv64"])
        self.assertEqual(command[command.index("-b") + 1], "release")
        self.assertEqual(command[command.index("-t") + 1], "release")


if __name__ == "__main__":
    unittest.main()
