"""Run the production type-generation helpers with minimal host kernel stubs.

This checks stale-generation fallback and original/new type classification;
it does not emulate SELinux, RCU or the Android kernel.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class OriginalTypeMetadataTests(unittest.TestCase):
    def test_generation_and_policy_identity(self):
        compiler = shutil.which("gcc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host C compiler required")
        source = (ROOT / "kernel/selinux/sepolicy.c").read_text()
        declarations = "\n".join(re.findall(r"^static .*ksu_original_types_.*;$", source, re.M))
        functions = []
        for name in ("ksu_set_original_types", "ksu_advance_original_types", "ksu_type_is_original"):
            match = re.search(r"^(?:bool|int) " + name + r"\([^;]*?\)\n\{", source, re.M)
            self.assertIsNotNone(match)
            end, depth = match.end(), 1
            while depth:
                depth += (source[end] == "{") - (source[end] == "}")
                end += 1
            functions.append(source[match.start():end])
        unit = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef uint32_t u32;
struct policydb { struct { u32 nprim; } p_types; };
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
'''+ declarations + "\n" + "\n".join(functions) + r'''
int main(void) {
    struct policydb original = {{4}}, live = {{6}}, next = {{8}}, other = {{8}};
    assert(ksu_type_is_original(&live, 1, 1) == -1);
    assert(ksu_set_original_types(&live, &original, 2));
    assert(ksu_type_is_original(&live, 2, 1) == 1);
    assert(ksu_type_is_original(&live, 2, 4) == 1);
    assert(ksu_type_is_original(&live, 2, 5) == 0);
    assert(ksu_type_is_original(&live, 2, 0) == 0);
    assert(ksu_type_is_original(&live, 2, 7) == -1);
    assert(ksu_type_is_original(&live, 3, 1) == -1);
    assert(ksu_type_is_original(&other, 2, 1) == -1);
    assert(ksu_advance_original_types(&next, &live, 2, 3));
    assert(ksu_type_is_original(&next, 3, 4) == 1);
    assert(ksu_type_is_original(&next, 3, 5) == 0);
    assert(ksu_type_is_original(&live, 2, 1) == -1);
    assert(!ksu_advance_original_types(&other, &next, 2, 4));
    assert(ksu_type_is_original(&next, 3, 1) == -1);
    assert(!ksu_set_original_types(&original, &next, 4));
    assert(!ksu_set_original_types(&live, &original, 0));
    return 0;
}
'''
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "metadata.c"
            exe = Path(directory) / ("metadata.exe" if os.name == "nt" else "metadata")
            src.write_text(unit)
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)
