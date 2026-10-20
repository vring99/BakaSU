"""Link official SUSFS preinit calls and preserve Pro's normal init path."""

import ctypes
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_private_manager import PRIVATE, clang_path
from test_susfs_native import find_tool

KERNEL = Path(__file__).resolve().parents[2] / "kernel"
CALLER = """
struct filename;
struct user_arg_ptr;
extern int ksu_setup_preinit_file(struct filename **filename_ptr, struct user_arg_ptr *argv_user);
extern int ksu_preinit_handle_post_execveat(int *fd, struct filename **filename_ptr,
                                         void *argv_user, void *envp_user,
                                         int *flags, int *retval, int *preinit_fd);
int probe(void)
{
    int fd = -100, flags = 0, retval = -1, preinit_fd = 0;
    struct filename *filename = 0;
    preinit_fd = ksu_setup_preinit_file(&filename, 0);
    return ksu_preinit_handle_post_execveat(&fd, &filename, 0, 0, &flags, &retval, &preinit_fd);
}
"""


class SusfsPreinitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compiler = clang_path()
        cls.make = find_tool("make", "prebuilt/*/bin/make.exe")
        if not cls.compiler or not cls.make:
            raise unittest.SkipTest("Clang and GNU make are required")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        cls.root = Path(cls.directory.name)
        (cls.root / "linux").mkdir()
        (cls.root / "linux/errno.h").write_text("#define EOPNOTSUPP 95\n")
        cls.caller = cls.root / "exec.c"
        cls.caller.write_text(CALLER)
        objects = (KERNEL / "Kbuild").read_text().split("ccflags-y +=", 1)[0]
        (cls.root / "Makefile").write_text(
            objects + '\nall:\n\t@echo "$(kernelsu-objs)"\n')

    def selected_objects(self, susfs):
        env = os.environ.copy()
        if os.name == "nt":
            env["PATH"] = "C:/Program Files/Git/usr/bin" + os.pathsep + env["PATH"]
        result = subprocess.run(
            [self.make, "--no-print-directory", "CONFIG_KSU_SUSFS=" + ("y" if susfs else "")],
            cwd=self.root, env=env, capture_output=True, text=True, check=True)
        return result.stdout.split()

    def test_aarch64_link_resolves_both_official_entry_points(self):
        sources = [KERNEL / "compat/susfs_preinit.c"] if "compat/susfs_preinit.o" in self.selected_objects(True) else []
        for lto in (False, True):
            with self.subTest(lto=lto):
                result = subprocess.run(
                    [self.compiler, "--target=aarch64-linux-gnu", "-fuse-ld=lld", "-ffreestanding", "-nostdlib",
                     "-Werror", "-Wl,-e,probe", "-Wl,--no-undefined", "-I", str(self.root),
                     *(["-flto"] if lto else []), str(self.caller), *(str(source) for source in sources),
                     "-o", str(self.root / "vmlinux")], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual((self.root / "vmlinux").read_bytes()[:4], b"\x7fELF")

    def test_disabled_preinit_preserves_exec_arguments_and_results(self):
        source = KERNEL / "compat/susfs_preinit.c"
        library = self.root / ("preinit.dll" if os.name == "nt" else "preinit.so")
        result = subprocess.run(
            [self.compiler, "-shared", "-Werror", "-I", str(self.root), str(source),
             *(["-Wl,--export-all-symbols"] if os.name == "nt" else ["-fPIC"]), "-o", str(library)],
            capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lib = ctypes.CDLL(str(library))
        if os.name == "nt":
            import _ctypes
            self.addCleanup(_ctypes.FreeLibrary, lib._handle)
        lib.ksu_setup_preinit_file.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        lib.ksu_preinit_handle_post_execveat.argtypes = [ctypes.c_void_p] * 7
        path = ctypes.create_string_buffer(b"/system/bin/init")
        filename = ctypes.c_void_p(ctypes.addressof(path))
        argv = ctypes.create_string_buffer(b"selinux_setup")
        before = (filename.value, path.raw, argv.raw)
        self.assertEqual(lib.ksu_setup_preinit_file(ctypes.byref(filename), argv), -95)
        self.assertEqual((filename.value, path.raw, argv.raw), before)
        for result_code in (0, -2, -13):
            with self.subTest(exec_result=result_code):
                values = [ctypes.c_int(value) for value in (-100, 0, result_code, -95)]
                fd, flags, retval, preinit_fd = values
                self.assertEqual(lib.ksu_preinit_handle_post_execveat(
                    ctypes.byref(fd), ctypes.byref(filename), argv, None,
                    ctypes.byref(flags), ctypes.byref(retval), ctypes.byref(preinit_fd)), 0)
                self.assertEqual([value.value for value in values], [-100, 0, result_code, -95])
                self.assertEqual((filename.value, path.raw, argv.raw), before)

    def test_lkm_does_not_link_susfs_preinit_compatibility(self):
        self.assertNotIn("compat/susfs_preinit.o", self.selected_objects(False))

    def test_export_contains_link_dependencies(self):
        for name in ("kernel/Kbuild", "kernel/compat/susfs_preinit.c", "kernel/compat/susfs_preinit.h"):
            self.assertIn(name, PRIVATE.GKI_FILES)


if __name__ == "__main__":
    unittest.main()
