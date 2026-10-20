"""Run the upstream symbol resolver across old and new kallsyms interfaces."""

import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_private_manager import clang_path

KERNEL = Path(__file__).resolve().parents[2] / "kernel"

SHIM = r"""
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
#define __nocfi
#define KERNEL_VERSION(a,b,c) (((a) << 16) | ((b) << 8) | (c))
#define ALWAYS_HAVE_ON_EACH_SYMBOL (LINUX_VERSION_CODE >= KERNEL_VERSION(5,19,0))
#define HAVE_ON_EACH_MATCH_SYMBOL (LINUX_VERSION_CODE >= KERNEL_VERSION(6,1,0))
#define KSYM_NAME_LEN 128
#define GFP_KERNEL 0
#define kzalloc(n,f) calloc(1,n)
#define kvmalloc_array(n,s,f) calloc(n,s)
#define kfree(p) free(p)
#define kvfree(p) free(p)
#define sort(p,n,s,cmp,swap) qsort(p,n,s,cmp)
#define ENOMEM 12
#define EINTR 4
static int interrupted;
#define current 0
#define fatal_signal_pending(t) interrupted
#define cond_resched() ((void)0)
struct module { int unused; };
static const char *symbols[] = {"alpha", "beta.llvm.123", "beta", "gamma$123"};
static unsigned long addresses[] = {0x1000, 0x2000, 0x3000, 0x4000};
static unsigned long find_kernel_symbol_exact(const char *name) {
    for (int i = 0; i < 4; ++i) if (!strcmp(name, symbols[i])) return addresses[i];
    return 0;
}
#if LINUX_VERSION_CODE >= KERNEL_VERSION(6,6,0)
static int kallsyms_on_each_symbol(int (*cb)(void *, const char *, unsigned long), void *ctx) {
    for (int i = 0; i < 4; ++i) { int ret = cb(ctx, symbols[i], addresses[i]); if (ret) return ret; }
    return 0;
}
#else
static int test_walk(int (*cb)(void *, const char *, struct module *, unsigned long), void *ctx) {
    for (int i = 0; i < 4; ++i) { int ret = cb(ctx, symbols[i], NULL, addresses[i]); if (ret) return ret; }
    struct module mod = {0};
    return cb(ctx, "module_only", &mod, 0x5000);
}
#if ALWAYS_HAVE_ON_EACH_SYMBOL
#define kallsyms_on_each_symbol test_walk
#else
static int (*kallsyms_on_each_symbol_fn)(int (*)(void *, const char *, struct module *, unsigned long), void *) = test_walk;
#endif
#endif
#if HAVE_ON_EACH_MATCH_SYMBOL
static int test_match(int (*cb)(void *, unsigned long), const char *name, void *ctx) {
    /* Force the suffix cases through the fallback walk. */
    return !strcmp(name, "alpha") ? cb(ctx, 0x1000) : 0;
}
static int (*kallsyms_on_each_match_symbol_fn)(int (*)(void *, unsigned long), const char *, void *) = test_match;
#endif
"""

PROBE = r"""
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
EXPORT int probe(int cancel) {
    const char *names[] = {"beta", "alpha", "gamma", "beta", "missing", NULL, "module_only"};
    unsigned long out[7];
    interrupted = cancel;
    int ret = ksu_lookup_kernel_symbols(names, out, 7);
    if (cancel) return ret == -EINTR;
    return ret == 4 && out[0] == 0x2000 && out[1] == 0x1000 && out[2] == 0x4000 &&
           out[3] == 0x2000 && !out[4] && !out[5] && !out[6];
}
"""


class PreinitSymbolsTests(unittest.TestCase):
    def test_batch_lookup_keeps_first_match_duplicates_and_kernel_only_scope(self):
        compiler = clang_path()
        if not compiler:
            self.skipTest("Clang is required")
        source = (KERNEL / "infra/symbol_resolver.c").read_text()
        source = source[source.index("struct ksu_batch_entry {"):source.index("void __init ksu_init_symbol_resolver")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit = root / "symbols.c"
            unit.write_text(SHIM + source + PROBE)
            for major, minor in ((5, 10), (5, 15), (6, 1), (6, 6), (6, 12)):
                with self.subTest(kernel=f"{major}.{minor}"):
                    library = root / (f"symbols-{major}-{minor}" + (".dll" if os.name == "nt" else ".so"))
                    result = subprocess.run(
                        [compiler, "-std=gnu11", "-Werror", "-shared",
                         f"-DLINUX_VERSION_CODE={major * 65536 + minor * 256}",
                         *([] if os.name == "nt" else ["-fPIC"]), str(unit), "-o", str(library)],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    lib = ctypes.CDLL(str(library))
                    try:
                        self.assertEqual(lib.probe(0), 1)
                        self.assertEqual(lib.probe(1), 1)
                    finally:
                        if os.name == "nt":
                            import _ctypes
                            _ctypes.FreeLibrary(lib._handle)


if __name__ == "__main__":
    unittest.main()
