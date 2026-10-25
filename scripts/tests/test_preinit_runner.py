"""Execute the production preinit handoff with controlled kernel primitives."""

import ctypes
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_private_manager import PRIVATE, clang_path
from test_supercall_permissions import function

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / "kernel"

SHIM = r"""
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
#define __user
#define __init
#define __nocfi
#define CONFIG_KSU_SUSFS 1
#define CONFIG_COMPAT 1
#define KERNEL_VERSION(a,b,c) (((a) << 16) | ((b) << 8) | (c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,19,0)
#define EMPTY_VMA_FLAGS 0
#define module_param_named(...)
#define pr_info(...) ((void)0)
#define pr_err(...) ((void)0)
#define likely(x) (x)
#define unlikely(x) (x)
#define READ_ONCE(x) (x)
#define xchg(p,v) exchange_file(p,v)
#define EINVAL 22
#define ENOENT 2
#define O_CLOEXEC 0x80000
#define LOOKUP_FOLLOW 1
#define IS_ERR(p) ((uintptr_t)(p) > (uintptr_t)-4096)
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define get_user(x,p) ((p) ? ((x) = *(p), 0) : 1)
#define compat_ptr(p) ((void *)(uintptr_t)(p))
typedef uint32_t compat_uptr_t;
/* Keep the kernel shim independent of the host libc's loff_t definition. */
typedef int64_t test_loff_t;
#define loff_t test_loff_t
struct file { int unused; } runner_file;
struct path { int unused; };
struct pt_regs;
struct filename { const char *name; };
struct user_arg_ptr {
    bool is_compat;
    union { const char *const *native; const compat_uptr_t *compat; } ptr;
};
const char ksu_preinit_runner_start[1] = {0};
const char ksu_preinit_runner_end[1] = {0};
static int fail_fd, fail_path, closed, released, installed;
static int zero_fd, fd_calls, unused_puts, fd_number = 7;
static struct file *exchange_file(struct file **p, struct file *v) {
    struct file *old = *p; *p = v; return old;
}
static struct file *shmem_file_setup(const char *n, size_t s, int f) {
    (void)n; (void)s; (void)f; return &runner_file;
}
static ssize_t ksu_kernel_write_compat(struct file *f, const void *p, size_t n, loff_t *pos) {
    (void)f; (void)p; (void)pos; return n;
}
/* Model user-memory access without dereferencing invalid host addresses. */
static const char *get_user_arg_ptr(struct user_arg_ptr argv, int nr) {
    if (argv.is_compat)
        return argv.ptr.compat ? compat_ptr(argv.ptr.compat[nr]) : (void *)(intptr_t)-14;
    return argv.ptr.native ? argv.ptr.native[nr] : (void *)(intptr_t)-14;
}
static void fput(struct file *f) { (void)f; ++released; }
static int get_unused_fd_flags(int f) {
    (void)f;
    if (zero_fd && ++fd_calls == 1) return 0;
    return fail_fd ? -24 : fd_number;
}
static void put_unused_fd(int fd) { if (fd == 0) ++unused_puts; }
static void fd_install(int fd, struct file *f) { (void)fd; (void)f; ++installed; }
static int kern_path(const char *n, int f, struct path *p) {
    (void)n; (void)f; (void)p; return fail_path ? -ENOENT : 0;
}
static void path_put(struct path *p) { (void)p; }
static int ksu_close_fd(int fd) { (void)fd; ++closed; return 0; }
static long strncpy_from_user(char *d, const char *s, size_t n) {
    if (!s) return -14;
    strncpy(d, s, n); return strlen(s) < n ? strlen(s) : n;
}
"""

PROBE = r"""
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
EXPORT int probe(int mode) {
    char name[64];
    const char *args[] = {"/system/bin/init", "selinux_setup", NULL};
    struct filename file = {name}, *filename = &file;
    struct user_arg_ptr argv = {.is_compat = false, .ptr.native = args};
    int fd = -100, flags = 0, retval = -2, preinit_fd, ret;
    memset(name, 0xa5, sizeof(name));
    name[sizeof(name) - 1] = 0;
    strcpy(name, "/system/bin/init");
    fail_fd = mode == 3 || mode == 11; fail_path = mode == 4;
    zero_fd = mode == 10 || mode == 11;
    fd_calls = unused_puts = 0;
    fd_number = mode == 9 ? 100 : 7;
    ksu_preinit_release();
    closed = released = installed = 0;
    ksu_preinit_enabled = mode != 5;
    ksu_preinit_init();
    if (mode == 1) strcpy(name, "/system/bin/sh");
    if (mode == 2) args[1] = "second_stage";
    if (mode == 6) argv.ptr.native = NULL;
    preinit_fd = ksu_setup_preinit_file(&filename, &argv);
    if (mode == 1 || mode == 2 || mode == 5 || mode == 6)
        return preinit_fd <= 0 && !strcmp(filename->name, name) && !installed;
    if (mode == 3) return preinit_fd < 0 && released == 1 && !installed;
    if (mode == 11)
        return preinit_fd < 0 && released == 1 && !installed && unused_puts == 1;
    if (mode == 4) return preinit_fd < 0 && closed == 1;
    if (preinit_fd != fd_number || strcmp(filename->name,
            mode == 9 ? "/proc/self/fd/100" : "/proc/self/fd/7")) return 0;
    if (mode == 10 && unused_puts != 1) return 0;
    if (mode == 7) {
        struct filename next = {name}, *nextp = &next;
        return ksu_setup_preinit_file(&nextp, &argv) <= 0;
    }
    if (mode == 8) retval = 0;
    ret = ksu_preinit_handle_post_execveat(&fd, &filename, &argv, NULL,
                                          &flags, &retval, &preinit_fd);
    if (fd != -100 || flags != 0) return 0;
    if (mode == 8) return !ret && !closed && !strcmp(filename->name, "/proc/self/fd/7");
    return ret < 0 && closed == 1 && !strcmp(filename->name, "/system/bin/init") && retval == -2;
}
"""

TRACEPOINT_SHIM = r"""
struct pt_regs { const char **filename; };
static char userspace_buffer[128];
static int fail_copy;
static void *userspace_stack_buffer(const void *data, size_t len) {
    if (fail_copy || len > sizeof(userspace_buffer)) return NULL;
    void *ptr = userspace_buffer + sizeof(userspace_buffer) - len;
    memcpy(ptr, data, len);
    return ptr;
}
static void *ksu_task_user_ptr(uintptr_t ptr) { return (void *)ptr; }
static struct user_arg_ptr ksu_take_user_argv(const char *const *args) {
    return (struct user_arg_ptr){.is_compat = false, .ptr.native = args};
}
#define untagged_addr(x) (x)
static int exec_calls, fail_exec, wrong_exec;
static long ksu_call_syscall(int nr, const struct pt_regs *regs) {
    const char *expected = exec_calls ? "/system/bin/init" : "/proc/self/fd/7";
    if (nr != 0 || strcmp(*regs->filename, expected)) wrong_exec = 1;
    ++exec_calls;
    return fail_exec && exec_calls == 1 ? -2 : 0;
}
"""

TRACEPOINT_PROBE = r"""
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
EXPORT int tracepoint_probe(int mode) {
    const char *original = mode == 1 ? "/system/bin/sh" : "/system/bin/init";
    const char *filename = original;
    const char *args[] = {original, mode == 2 ? "second_stage" : "selinux_setup", NULL};
    struct pt_regs regs = {.filename = &filename};
    long ret = -99;
    int handled;
    ksu_preinit_release();
    closed = released = installed = exec_calls = wrong_exec = 0;
    zero_fd = fd_calls = unused_puts = 0;
    fd_number = 7;
    fail_fd = mode == 3; fail_path = mode == 4; fail_exec = mode == 7;
    fail_copy = mode == 8;
    ksu_preinit_enabled = mode != 5;
    ksu_preinit_init();
    handled = ksu_preinit_handle_execve_tracepoint(&filename, mode == 6 ? NULL : args, 0, &regs, &ret);
    if (wrong_exec) return 0;
    if (mode >= 1 && mode <= 6)
        return !handled && filename == original && ret == -99 && exec_calls == 0;
    if (mode == 7)
        return handled && ret == 0 && closed == 1 && filename == original && exec_calls == 2;
    if (mode == 8)
        return !handled && filename == original && ret == -99 && closed == 1 && exec_calls == 0;
    return handled && !ret && !strcmp(filename, "/proc/self/fd/7") && exec_calls == 1;
}
"""


class PreinitRunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = clang_path()
        if not cls.compiler:
            raise unittest.SkipTest("Clang is required")

    def test_real_susfs_runner_handoff_and_failure_recovery(self):
        path = KERNEL / "preinit/preinit.c"
        self.assertTrue(path.is_file(), "Pro still lacks the real upstream preinit runner")
        source = re.sub(r'^#include[^\n]*', '', path.read_text(), flags=re.M)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit = root / "preinit.c"
            unit.write_text(SHIM + source + PROBE)
            library = root / ("preinit.dll" if os.name == "nt" else "preinit.so")
            result = subprocess.run(
                [self.compiler, "-std=gnu11", "-Werror", "-Wno-unused-function", "-shared",
                 *([] if os.name == "nt" else ["-fPIC"]), str(unit), "-o", str(library)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            lib = ctypes.CDLL(str(library))
            try:
                for mode in range(12):
                    with self.subTest(mode=mode):
                        self.assertEqual(lib.probe(mode), 1)
            finally:
                if os.name == "nt":
                    import _ctypes
                    _ctypes.FreeLibrary(lib._handle)

    def test_runner_uses_existing_or_installed_headers_and_disables_if_unavailable(self):
        make = shutil.which("make")
        if not make:
            self.skipTest("GNU make is required")
        generator = KERNEL / "tools/code_generation/preinit_runner/preinit_runner.mk"
        # Exercise the real generator, including its recursive headers_install.
        for state, enabled, installs in (("existing", True, False),
                                         ("installable", True, True),
                                         ("unavailable", False, True)):
            for hook in ("TRACEPOINT_HOOK", "SUSFS", "MANUAL_HOOK"):
                with self.subTest(headers=state, hook=hook):
                    with tempfile.TemporaryDirectory() as directory:
                        root = Path(directory)
                        kernel_tree = root / "kernel"
                        kernel_tree.mkdir()
                        header = root / "usr/include/linux/unistd.h"
                        if state == "existing":
                            header.parent.mkdir(parents=True)
                            header.touch()
                        install = '\t@touch "$(O)/headers-install-called"\n'
                        if state == "installable":
                            install += ('\t@mkdir -p "$(INSTALL_HDR_PATH)/include/linux"\n'
                                        '\t@touch "$(INSTALL_HDR_PATH)/include/linux/unistd.h"\n')
                        else:
                            install += '\t@false\n'
                        (kernel_tree / "Makefile").write_text("headers_install:\n" + install)
                        (root / "Makefile").write_text(
                            f'include {generator.as_posix()}\n'
                            'all:\n\t@echo "$(kernelsu-objs) $(ccflags-y)"\n')
                        result = subprocess.run(
                            [make, "--no-print-directory", "all", "objtree=" + root.as_posix(),
                             "srctree=" + kernel_tree.as_posix(), "obj=" + root.as_posix(),
                             "KSU_SRC=" + KERNEL.as_posix(), "ARCH=arm64", "CC=" + self.compiler,
                             "CONFIG_KSU_" + hook + "=y"], cwd=root,
                            capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertEqual("preinit/preinit.o" in result.stdout, enabled)
                        self.assertEqual("preinit/blob.o" in result.stdout, enabled)
                        self.assertEqual("-DKSU_NO_PREINIT" in result.stdout, not enabled)
                        self.assertEqual((root / "headers-install-called").exists(), installs)
                        self.assertEqual(header.exists(), enabled)

    def test_gki_export_contains_runner_and_symbol_dependencies(self):
        required = ["kernel/preinit", "kernel/infra/symbol_resolver.c",
                    "kernel/infra/symbol_resolver.h", "kernel/runtime/ksud_integration.c",
                    "kernel/hook/syscall_event_bridge.c", "uapi/supercall.h"]
        for path in required:
            with self.subTest(path=path):
                self.assertIn(path, PRIVATE.GKI_FILES)

    def test_tracepoint_handoff_and_original_init_retry(self):
        source = re.sub(r'^#include[^\n]*', '', (KERNEL / "preinit/preinit.c").read_text(), flags=re.M)
        # Linux uses LP64; the Windows test host uses LLP64.
        source = source.replace('(unsigned long)', '(uintptr_t)')
        shim = SHIM.replace('#define CONFIG_KSU_SUSFS 1', '#define CONFIG_KSU_TRACEPOINT_HOOK 1')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit = root / "tracepoint.c"
            unit.write_text(shim + TRACEPOINT_SHIM + source + TRACEPOINT_PROBE)
            library = root / ("tracepoint.dll" if os.name == "nt" else "tracepoint.so")
            result = subprocess.run(
                [self.compiler, "-std=gnu11", "-Werror", "-Wno-unused-function", "-shared",
                 *([] if os.name == "nt" else ["-fPIC"]), str(unit), "-o", str(library)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            lib = ctypes.CDLL(str(library))
            try:
                for mode in range(9):
                    with self.subTest(mode=mode):
                        self.assertEqual(lib.tracepoint_probe(mode), 1)
            finally:
                if os.name == "nt":
                    import _ctypes
                    _ctypes.FreeLibrary(lib._handle)

    def test_real_runner_parses_quoted_actions_and_rejects_malformed_input(self):
        source = (KERNEL / "preinit/runner/runner.c").read_text()
        unit_source = '#include <stdbool.h>\n#include <stddef.h>\n#include <string.h>\n'
        unit_source += 'static char params_buf[8192];\n'
        for name in ("is_space", "tokenize", "has_space", "append", "build_params"):
            unit_source += function(source, name) + '\n'
        unit_source += r'''
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
static char line[4097];
static char *args[128];
EXPORT int parse(const char *s) { strncpy(line, s, sizeof(line) - 1); return tokenize(line, args, 128); }
EXPORT const char *token(int n) { return args[n]; }
EXPORT const char *parameters(int count) { return build_params(args + 2, count - 2) ? NULL : params_buf; }
'''
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            unit = root / "parser.c"
            unit.write_text(unit_source)
            library = root / ("parser.dll" if os.name == "nt" else "parser.so")
            result = subprocess.run(
                [self.compiler, "-std=gnu11", "-Werror", "-shared",
                 *([] if os.name == "nt" else ["-fPIC"]), str(unit), "-o", str(library)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            lib = ctypes.CDLL(str(library))
            lib.parse.argtypes = [ctypes.c_char_p]
            lib.token.restype = ctypes.c_char_p
            lib.parameters.restype = ctypes.c_char_p
            try:
                self.assertEqual(lib.parse(b'insmod kmod/test.ko param="hello world" enabled=1'), 4)
                self.assertEqual(lib.token(2), b'param=hello world')
                self.assertEqual(lib.parameters(4), b'param="hello world" enabled=1')
                self.assertEqual(lib.parse(b'exec? bin/test "a b"'), 3)
                self.assertEqual(lib.token(0), b'exec?')
                self.assertEqual(lib.token(2), b'a b')
                self.assertEqual(lib.parse(b'exec bin/test "unclosed'), -1)
                self.assertEqual(lib.parse(b'arg ' * 128), -1)
            finally:
                if os.name == "nt":
                    import _ctypes
                    _ctypes.FreeLibrary(lib._handle)

    def test_nolibc_runner_and_embedded_blob_cross_link(self):
        prefix = Path(os.environ.get("PREINIT_UAPI_ROOT", "/usr"))
        headers = prefix / "include"
        if not (headers / "linux/unistd.h").is_file():
            self.skipTest("Installed Linux UAPI headers are required (PREINIT_UAPI_ROOT)")
        linker = shutil.which("ld.lld")
        if not linker:
            self.skipTest("LLD is required")
        resource = subprocess.check_output([self.compiler, "-print-resource-dir"], text=True).strip()
        tested = 0
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for arch, triple, machine in (("arm64", "aarch64-linux-gnu", 183),
                                           ("x86", "x86_64-linux-gnu", 62)):
                arch_headers = prefix / "lib/linux/uapi" / arch
                if not (arch_headers / "asm/unistd.h").is_file():
                    arch_headers = headers / triple
                if not (arch_headers / "asm/unistd.h").is_file():
                    arch_headers = prefix / triple / "include"
                if not (arch_headers / "asm/unistd.h").is_file():
                    continue
                with self.subTest(arch=arch):
                    obj = root / (arch + ".o")
                    elf = root / (arch + ".elf")
                    result = subprocess.run(
                        [self.compiler, "--target=" + triple, "-std=gnu11", "-Os", "-Wall", "-Werror",
                         "-nostdinc", "-isystem", str(Path(resource) / "include"),
                         "-I", str(KERNEL / "preinit/runner/nolibc"), "-I", str(arch_headers),
                         "-I", str(headers), "-I", str(ROOT), "-ffreestanding", "-fno-stack-protector",
                         "-fno-pic", "-fno-pie", "-ffunction-sections", "-fdata-sections",
                         "-c", str(KERNEL / "preinit/runner/runner.c"), "-o", str(obj)],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    result = subprocess.run(
                        [linker, "-static", "-nostdlib", "-e", "_start", "--gc-sections", "-s",
                         str(obj), "-o", str(elf)], capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    data = elf.read_bytes()
                    self.assertEqual(data[:4], b"\x7fELF")
                    self.assertEqual(int.from_bytes(data[18:20], "little"), machine)
                    result = subprocess.run(
                        [self.compiler, "--target=" + triple,
                         '-DKSU_PREINIT_RUNNER_BIN="' + elf.as_posix() + '"',
                         "-c", str(KERNEL / "preinit/blob.S"), "-o", str(root / (arch + "-blob.o"))],
                        capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    tested += 1
        self.assertGreater(tested, 0, "No supported architecture UAPI headers found")


if __name__ == "__main__":
    unittest.main()
