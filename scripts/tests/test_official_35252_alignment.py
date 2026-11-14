"""Release provenance gate: runtime changes outside the approved Pro scope fail.

This is an explicit source-parity contract, not a claim of runtime equivalence.
Behavioral coverage for retained authorization and identity lives in their tests.
"""

from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
BASELINE = "d5e9e025b8b49155f8014684d64c91742b465f65"
# Reviewed maintenance backports; provenance is recorded in docs/UPSTREAM_SECURITY_BACKPORTS.md.
BACKPORTED = {
    "userspace/ksud/src/android/profile.rs",
    "kernel/feature/selinux_hide.c",
    "kernel/selinux/sepolicy.c",
    "kernel/selinux/sepolicy.h",
    "kernel/include/arch.h",
    "kernel/hook/x86_64/syscall_hook.c",
    "kernel/tools/code_generation/preinit_runner/preinit_runner.mk",
    "manager/app/src/main/java/org/bakasu/bakasu/ui/NavContainer.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/ui/util/WindowSize.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/ui/screen/themeSettings/themeSettings/ThemeSettings.kt",

    "userspace/ksud/src/boot_patch.rs", "userspace/ksuinit/src/init.rs",
    "kernel/infra/btf_parser.c", "kernel/infra/btf_parser.h",
    "kernel/infra/file_wrapper.c", "kernel/selinux/inode.c",
    "kernel/selinux/selinux.h", "kernel/selinux/rules.c",
}
RETAINED = {
    # Native old/new SUSFS API compatibility: docs/susfs-policy-records-35275.md.
    "kernel/tools/susfs_compat.mk",
    "kernel/Kbuild", "kernel/Kconfig", "kernel/core/init.c",
    "kernel/manager/apk_sign.c", "kernel/manager/manager_sign.h",
    "kernel/supercall/dispatch.c", "kernel/supercall/internal.h",
    "kernel/supercall/perm.c", "kernel/supercall/supercall.c",
    "manager/.gitignore", "manager/build.gradle.kts", "manager/app/build.gradle.kts",
    "manager/gradle/libs.versions.toml",
    "manager/app/src/main/AndroidManifest.xml",
    "manager/app/src/main/cpp/jni.c", "manager/app/src/main/cpp/legacy.c",
    "manager/app/src/main/java/org/bakasu/bakasu/KernelSUApplication.kt",
    # User-requested application entry rename; initialization is unchanged.
    "manager/app/src/main/java/muxinsu/MuxinsuApplication.kt",
    "manager/app/src/main/generated/baselineProfiles/baseline-prof.txt",
    "manager/app/src/main/generated/baselineProfiles/startup-prof.txt",
    "manager/app/src/main/java/org/bakasu/bakasu/data/settings/SettingsPlatformRepository.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/data/shell/KsuCli.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/data/application/DynamicManagerRepository.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/data/shell/ManagerSignature.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/data/update/ManagerUpdateRepository.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/data/update/ManagerUpdateSource.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/domain/model/SettingsPlatform.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/magica/AppZygotePreload.java",
    "manager/app/src/main/java/org/bakasu/bakasu/magica/BootCompletedReceiver.java",
    "manager/app/src/main/java/org/bakasu/bakasu/magica/MagicaService.java",
    "manager/app/src/main/java/org/bakasu/bakasu/ui/screen/main/HomePage.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/ui/screen/main/SettingsPage.kt",
    "manager/app/src/main/java/org/bakasu/bakasu/ui/viewmodel/SettingsViewModel.kt",
    "userspace/ksud/Cargo.lock", "userspace/ksud/Cargo.toml", "userspace/ksud/build.rs",
    "userspace/ksud/src/android/cli.rs", "userspace/ksud/src/android/late_load/mod.rs",
    "userspace/ksud/src/android/late_load/magica.rs",
}


class Official35252AlignmentTests(unittest.TestCase):
    def test_runtime_tree_only_differs_for_retained_pro_requirements(self):
        changed = subprocess.check_output(
            ["git", "diff", "--name-only", BASELINE, "--", "kernel", "userspace", "manager"],
            cwd=ROOT, text=True,
        ).splitlines()
        unexpected = [
            path for path in changed
            if path not in RETAINED and path not in BACKPORTED
            and not path.startswith("manager/app/src/test/")
            and not (path.startswith("manager/app/src/main/res/values") and path.endswith("/strings.xml"))
            and subprocess.run(
                ["git", "diff", "--quiet", "--ignore-space-at-eol", "--ignore-blank-lines",
                 BASELINE, "--", path], cwd=ROOT,
            ).returncode != 0
        ]
        self.assertEqual(unexpected, [], "Unapproved runtime differences from official 35252")


if __name__ == "__main__":
    unittest.main()
