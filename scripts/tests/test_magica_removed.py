from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


class MagicaRemovalTests(unittest.TestCase):
    def test_manifest_has_no_magica_bootstrap_components(self):
        manifest = read("manager/app/src/main/AndroidManifest.xml")

        for marker in (
            "android.permission.RECEIVE_BOOT_COMPLETED",
            "zygotePreloadName",
            "MagicaService",
            "BootCompletedReceiver",
            "org.bakasu.bakasu.magica",
        ):
            if marker in manifest:
                self.fail(f"stale manifest marker: {marker}")

    def test_manifest_has_no_kernel_su_deep_link_entrypoints(self):
        manifest = read("manager/app/src/main/AndroidManifest.xml")

        for marker in (
            'android:scheme="ksu"',
            'android:host="action"',
            'android:host="webui"',
        ):
            if marker in manifest:
                self.fail(f"detector-visible deep-link marker: {marker}")

    def test_manager_has_no_magica_runtime_entrypoints(self):
        source_roots = (
            ROOT / "manager/app/src/main/java",
            ROOT / "manager/app/src/main/cpp",
            ROOT / "manager/app/src/main/res",
        )
        text_suffixes = {".c", ".h", ".java", ".kt", ".xml"}
        files = [
            path
            for source_root in source_roots
            for path in source_root.rglob("*")
            if path.is_file() and path.suffix in text_suffixes
        ]
        contents = "\n".join(
            path.read_text(encoding="utf-8", errors="ignore") for path in files
        )

        for marker in (
            "MagicaService",
            "BootCompletedReceiver",
            "AppZygotePreload",
            "org.bakasu.bakasu.magica",
            "settings_auto_jailbreak",
            "home_jailbreak",
            "jailbreak_timeout",
        ):
            if marker in contents:
                self.fail(f"stale manager marker: {marker}")

    def test_ksud_keeps_regular_late_load_without_magica_flags(self):
        cli = read("userspace/ksud/src/android/cli.rs")
        late_load_mod = read("userspace/ksud/src/android/late_load/mod.rs")
        cargo = read("userspace/ksud/Cargo.toml")

        self.assertIn("LateLoad", cli)
        self.assertIn("crate::android::late_load::run", cli)
        for marker in ("magica", "post_magica", "adb_client"):
            if marker in cli:
                self.fail(f"stale CLI marker: {marker}")
            if marker in late_load_mod:
                self.fail(f"stale late-load marker: {marker}")
            if marker in cargo:
                self.fail(f"stale Cargo marker: {marker}")


if __name__ == "__main__":
    unittest.main()
