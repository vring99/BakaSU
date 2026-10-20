"""Check SUSFS inline callback compatibility and exported source dependencies."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_private_manager import PRIVATE

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / "kernel"


def find_tool(name, ndk_relative):
    found = shutil.which(name)
    if found:
        return found
    sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if sdk:
        candidates = sorted(Path(sdk).glob(f"ndk/*/{ndk_relative}"))
        if candidates:
            return str(candidates[-1])
    return None


class NativeSusfsTests(unittest.TestCase):
    def test_optional_export_includes_native_object_dependencies(self):
        for name in ("kernel/Kbuild", "kernel/feature/selinux_hide.c",
                     "kernel/feature/selinux_hide.h", "kernel/tools/susfs_compat.mk"):
            self.assertIn(name, PRIVATE.GKI_FILES)

    def test_source_selection_preserves_tracepoint(self):
        source = (KERNEL / "Kbuild").read_text()
        self.assertEqual(source.count("kernelsu-objs += feature/selinux_hide.o"), 1)
        self.assertNotIn("selinux_hide_susfs.o", source)

    def test_make_accepts_current_interfaces_and_rejects_missing_hooks(self):
        make = find_tool("make", "prebuilt/*/bin/make.exe")
        if not make:
            self.skipTest("GNU make is required")
        env = os.environ.copy()
        if os.name == "nt":
            git_bin = Path("C:/Program Files/Git/usr/bin")
            env["PATH"] = str(git_bin) + os.pathsep + env["PATH"]
        inline = (KERNEL / "tools/inline_hook_check.mk").read_text()
        check = inline[:inline.index("endef") + len("endef")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "security/selinux/ss").mkdir(parents=True)
            (root / "fs").mkdir()
            (root / "fs/exec.c").write_text("ksu_install_su_fd\n")
            shutil.copyfile(KERNEL / "tools/susfs_compat.mk", root / "compat.mk")
            (root / "Makefile").write_text(
                "SHELL := sh\nsrctree := .\nCONFIG_KSU := y\nREPO_NAME := test\n" + check +
                '\ninclude compat.mk\nall:\n\t@echo "$(ccflags-y)"\n')
            hooks = root / "security/selinux/hooks.c"
            selinuxfs = root / "security/selinux/selinuxfs.c"
            common = "ksu_selinux_hide_running\nfake_status_initialize_key\ninitialize_fake_status\n"
            callbacks = "my_write_context\nmy_write_access\n"

            def run(*args):
                return subprocess.run([make, "--no-print-directory", *args], cwd=root,
                                      env=env, capture_output=True, text=True)

            hooks.write_text("ksu_selinux_hide_running\nmy_setprocattr\n")
            selinuxfs.write_text(common + callbacks)
            result = run()
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("KSU_COMPAT_HAS_SUSFS_INSTALL_SU_FD_DIRECT_CALL", result.stdout)
            self.assertIn("KSU_COMPAT_HAS_SUSFS_FEATURE_SELINUX_HIDE", result.stdout)
            self.assertNotEqual(run("CONFIG_KSU=m").returncode, 0)
            for symbol in ("initialize_fake_status", "my_write_context", "my_write_access"):
                selinuxfs.write_text((common + callbacks).replace(symbol, ""))
                self.assertNotEqual(run().returncode, 0, symbol)
            selinuxfs.write_text(common + callbacks)
            hooks.write_text("ksu_selinux_hide_running\nfake_state\n")
            self.assertNotEqual(run().returncode, 0)


if __name__ == "__main__":
    unittest.main()
