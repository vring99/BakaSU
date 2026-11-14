"""Keep the APK, driver and SU protocol version on the same maintenance release."""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]


class MaintenanceVersionTests(unittest.TestCase):
    def test_all_components_use_the_declared_35275_release(self):
        declarations = {
            "manager": ("manager/build.gradle.kts", r'extra\["managerVersionCode"\]\s*=\s*(\d+)\s*$'),
            "driver": ("kernel/Kbuild", r'^KSU_VERSION\s*:=\s*(\d+)\s*$'),
            "userspace": ("userspace/ksud/build.rs", r'^const MAINTENANCE_VERSION_CODE:\s*u32\s*=\s*(\d+);\s*$'),
        }
        for component, (path, pattern) in declarations.items():
            with self.subTest(component=component):
                source = (ROOT / path).read_text(encoding="utf-8")
                match = re.search(pattern, source, re.M)
                self.assertIsNotNone(match, f"{component} must declare its maintenance version")
                self.assertEqual(int(match[1]), 35275)


if __name__ == "__main__":
    unittest.main()
