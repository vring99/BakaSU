"""Exercise APK executable replacement without changing executable contents."""

from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import repack_apk


class MuxinsuRepackTests(unittest.TestCase):
    def test_old_input_gets_current_binary_and_selected_abi_only(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output, binary = root / "input.apk", root / "output.apk", root / "ksud"
            binary.write_bytes(b"current-executable")
            with ZipFile(source, "w") as archive:
                archive.writestr("classes.dex", b"unchanged-dex")
                archive.writestr("lib/arm64-v8a/libksud.so", b"old-executable")
                archive.writestr("lib/x86_64/libksud.so", b"other-abi")
                archive.writestr("lib/arm64-v8a/libjni.so", b"unchanged-jni")
            repack_apk.repack_apk(source, output, ["arm64-v8a"], {"arm64-v8a": binary})
            repack_apk.assert_required_libs(output, ["arm64-v8a"])
            with ZipFile(output) as archive:
                self.assertEqual(set(archive.namelist()), {
                    "classes.dex", "lib/arm64-v8a/libjni.so", "lib/arm64-v8a/libmuxinsu.so",
                })
                self.assertEqual(archive.read("lib/arm64-v8a/libmuxinsu.so"), binary.read_bytes())
                self.assertEqual(archive.read("classes.dex"), b"unchanged-dex")
                self.assertEqual(archive.read("lib/arm64-v8a/libjni.so"), b"unchanged-jni")

    def test_existing_current_binary_is_preserved_without_replacement(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / "input.apk", root / "output.apk"
            with ZipFile(source, "w") as archive:
                archive.writestr("lib/arm64-v8a/libmuxinsu.so", b"existing-executable")
            self.assertEqual(repack_apk.collect_existing_ksud_arches(source), ["arm64-v8a"])
            repack_apk.repack_apk(source, output, ["arm64-v8a"], {})
            repack_apk.assert_required_libs(output, ["arm64-v8a"])
            with ZipFile(output) as archive:
                self.assertEqual(archive.read("lib/arm64-v8a/libmuxinsu.so"), b"existing-executable")

    def test_old_name_alone_does_not_pass_current_package_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "input.apk"
            with ZipFile(source, "w") as archive:
                archive.writestr("lib/arm64-v8a/libksud.so", b"old-executable")
            self.assertEqual(repack_apk.collect_existing_ksud_arches(source), [])
            with self.assertRaises(RuntimeError):
                repack_apk.assert_required_libs(source, ["arm64-v8a"])


if __name__ == "__main__":
    unittest.main()
