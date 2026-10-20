"""Execute production permission/dispatch/entry code with mocked kernel primitives.

These are host regression tests, not a kernel build or Android device test.
Handlers are replaced with counters so a denied call must not reach its handler.
"""

import ctypes
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_private_manager import PRIVATE, clang_path

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / "kernel"
QUERIES = ("GET_INFO", "GET_INFO_LEGACY", "GET_FULL_VERSION", "CHECK_SAFEMODE")


def function(source, name):
    match = re.search(r"^(?:static )?(?:int|long|bool) " + name + r"\([^;]*?\)\n\{", source, re.M)
    if not match:
        raise AssertionError(f"Missing production function {name}")
    depth = 1
    end = match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


class SupercallPermissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = clang_path()
        if not compiler:
            raise unittest.SkipTest("clang is required for executable permission tests")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        directory = Path(cls.directory.name)
        dispatch = (KERNEL / "supercall/dispatch.c").read_text()
        entry = (KERNEL / "supercall/supercall.c").read_text()
        permissions = (KERNEL / "supercall/perm.c").read_text()
        permissions = re.sub(r"^#include[^\n]*", "", permissions, flags=re.M)
        table = re.search(r"static const struct ksu_ioctl_cmd_map ksu_ioctl_handlers\[\] = \{.*?\n\};",
                          dispatch, re.S)[0]
        commands = re.findall(r"\.cmd = (KSU_IOCTL_\w+)", table)
        cls.commands = {name.removeprefix("KSU_IOCTL_"): i for i, name in enumerate(commands, 1)}
        handlers = re.findall(r"\.handler = (\w+)", table)
        header = (KERNEL / "supercall/supercall.h").read_text()
        map_type = re.search(r"// IOCTL handler types.*?\n\};", header, re.S)[0]
        init = (KERNEL / "core/init.c").read_text()
        # Include the real compile-time default, including the old debug branch.
        default = re.search(r"(?:#ifdef CONFIG_KSU_DEBUG\n)?bool allow_shell = .*?;"
                            r"(?:\n#else\nbool allow_shell = .*?;\n#endif)?", init, re.S)[0]
        prelude = r"""
typedef _Bool bool;
#define true 1
#define false 0
#define NULL ((void *)0)
#define __user
#define EINVAL 22
#define EPERM 1
#define ENOTTY 25
#define pr_info(...) ((void)0)
#define pr_warn(...) ((void)0)
#define pr_err(...) ((void)0)
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
struct file { bool su_session; };
struct task { int pid; } task = { 123 };
#define current (&task)
static unsigned int caller_uid;
static bool manager, authorized;
static int handler_calls, install_calls;
#define current_uid() caller_uid
#define ksu_get_uid_t(uid) (uid)
static bool is_manager(void) { return manager; }
static bool ksu_is_allow_uid_for_current(unsigned int uid) {
    return authorized || (allow_shell && uid == 2000);
}
static bool ksu_is_su_session_fd(const struct file *file) { return file->su_session; }
static int ksu_install_fd(void) { ++install_calls; return 7; }
static void ksu_close_fd(int fd) { (void)fd; }
static int copy_to_user(void *dest, const void *src, unsigned long size) {
    (void)size;
    *(int *)dest = *(const int *)src;
    return 0;
}
#define KSU_INSTALL_MAGIC1 0xDEADBEEF
#define KSU_INSTALL_MAGIC2 0xCAFEBABE
"""
        # The default needs bool; the mocked allowlist needs the default.
        prelude = prelude.replace("struct file {", default + "\nstruct file {")
        source = prelude + map_type + "\n" + permissions + "\n"
        source += "enum {" + ",".join(f"{name}={value}" for name, value in zip(commands, range(1, len(commands)+1))) + "};\n"
        source += "\n".join(f"static int {name}(void *arg) {{ (void)arg; ++handler_calls; return 41; }}"
                            for name in handlers if name != "NULL")
        source += "\n" + table + "\n" + function(dispatch, "ksu_supercall_handle_ioctl")
        source += "\n" + function(entry, "ksu_handle_sys_reboot")
        source += r"""
EXPORT int default_shell(void) { return allow_shell; }
EXPORT void caller(unsigned int uid, int is_manager, int allowed, int shell_override) {
    caller_uid = uid;
    manager = is_manager;
    authorized = allowed;
    allow_shell = shell_override;
    handler_calls = install_calls = 0;
}
EXPORT int query(unsigned int cmd, int session) {
    struct file file;
    file.su_session = session;
    return (int)ksu_supercall_handle_ioctl(&file, cmd, NULL);
}
EXPORT int request_fd(int *reply) {
    void *arg = reply;
    return ksu_handle_sys_reboot(KSU_INSTALL_MAGIC1, KSU_INSTALL_MAGIC2, 0, &arg);
}
EXPORT int handlers_called(void) { return handler_calls; }
EXPORT int fds_installed(void) { return install_calls; }
"""
        unit = directory / "permission.c"
        unit.write_text(source)
        cls.libraries = []
        for mode, flags in (("GKI", ["-DCONFIG_KSU=1"]),
                            ("LKM", ["-DCONFIG_KSU_MODULE=1", "-DMODULE=1"])):
            for debug in (False, True):
                name = f"{mode}-debug{int(debug)}"
                defines = flags + (["-DCONFIG_KSU_DEBUG=1"] if debug else [])
                library = directory / (name + (".dll" if os.name == "nt" else ".so"))
                if os.name == "nt":
                    obj = directory / (name + ".obj")
                    subprocess.run([compiler, "--target=x86_64-pc-windows-msvc", "-std=c11",
                                    "-Werror", *defines, "-c", str(unit), "-o", str(obj)], check=True)
                    linker = Path(compiler).parent / "ld.lld.exe"
                    subprocess.run([str(linker), "-flavor", "link", "/dll", "/noentry", "/nodefaultlib",
                                    f"/out:{library}", str(obj)], check=True)
                else:
                    subprocess.run([compiler, "-std=c11", "-Werror", "-shared", "-fPIC", *defines,
                                    str(unit), "-o", str(library)], check=True)
                lib = ctypes.CDLL(str(library))
                lib.caller.argtypes = [ctypes.c_uint, ctypes.c_int, ctypes.c_int, ctypes.c_int]
                lib.caller.restype = None
                lib.query.argtypes = [ctypes.c_uint, ctypes.c_int]
                lib.request_fd.argtypes = [ctypes.POINTER(ctypes.c_int)]
                cls.libraries.append((name, lib, lib.default_shell()))
                # Unload before TemporaryDirectory cleanup on Windows.
                if os.name == "nt":
                    import _ctypes
                    cls.addClassCleanup(_ctypes.FreeLibrary, lib._handle)

    def test_unauthorized_callers_cannot_install_driver_fd(self):
        for name, lib, _ in self.libraries:
            for uid in (2000, 1000, 10287, 110287, 99001):
                with self.subTest(build=name, uid=uid):
                    lib.caller(uid, 0, 0, 0)
                    reply = ctypes.c_int(-1)
                    self.assertEqual(lib.request_fd(ctypes.byref(reply)), -1)
                    self.assertEqual(reply.value, -1)
                    self.assertEqual(lib.fds_installed(), 0)

    def test_old_or_transferred_fds_do_not_authorize_queries(self):
        for name, lib, _ in self.libraries:
            for uid in (2000, 10287):
                for session in (0, 1):
                    for command in QUERIES:
                        with self.subTest(build=name, uid=uid, session=session, command=command):
                            lib.caller(uid, 0, 0, 0)
                            self.assertEqual(lib.query(self.commands[command], session), -1)
                            self.assertEqual(lib.handlers_called(), 0)

    def test_authorized_callers_keep_entry_and_queries(self):
        for name, lib, _ in self.libraries:
            # Root need not already be in the KernelSU SELinux domain at boot.
            for uid, manager, allowed, override in ((0, 0, 0, 0), (10288, 1, 0, 0),
                                                    (2000, 0, 1, 0), (10287, 0, 1, 0),
                                                    (2000, 0, 0, 1)):
                with self.subTest(build=name, uid=uid, manager=manager, override=override):
                    lib.caller(uid, manager, allowed, override)
                    reply = ctypes.c_int(-1)
                    self.assertEqual(lib.request_fd(ctypes.byref(reply)), 0)
                    self.assertEqual(reply.value, 7)
                    self.assertEqual(lib.fds_installed(), 1)
                    for command in QUERIES:
                        self.assertEqual(lib.query(self.commands[command], 0), 41)

    def test_revocation_takes_effect_on_existing_descriptor(self):
        for name, lib, _ in self.libraries:
            with self.subTest(build=name):
                lib.caller(2000, 0, 1, 0)
                reply = ctypes.c_int(-1)
                self.assertEqual(lib.request_fd(ctypes.byref(reply)), 0)
                self.assertEqual(lib.query(self.commands["GET_INFO"], 0), 41)
                lib.caller(2000, 0, 0, 0)
                self.assertEqual(lib.query(self.commands["GET_INFO"], 0), -1)
                self.assertEqual(lib.handlers_called(), 0)

    def test_su_session_keeps_only_its_existing_scoped_exceptions(self):
        for name, lib, _ in self.libraries:
            with self.subTest(build=name):
                lib.caller(10287, 0, 0, 0)
                for command in ("GET_WRAPPER_FD", "DISABLE_ESCAPE_TO_ROOT"):
                    self.assertEqual(lib.query(self.commands[command], 0), -1)
                    self.assertEqual(lib.query(self.commands[command], 1), 41)
                for command in ("GRANT_ROOT", "GET_MANAGER_APPID", "SET_APP_PROFILE", "DYNAMIC_MANAGER"):
                    self.assertEqual(lib.query(self.commands[command], 1), -1)

    def test_su_authorization_does_not_grant_management_permissions(self):
        for name, lib, _ in self.libraries:
            with self.subTest(build=name):
                lib.caller(10287, 0, 1, 0)
                self.assertEqual(lib.query(self.commands["GRANT_ROOT"], 0), 41)
                for command in ("GET_MANAGER_APPID", "SET_APP_PROFILE", "DYNAMIC_MANAGER"):
                    self.assertEqual(lib.query(self.commands[command], 0), -1)

    def test_symbol_lookup_is_root_only_even_with_su_authorization_or_scoped_fd(self):
        self.assertIn("LOOKUP_SYMBOLS", self.commands)
        for name, lib, _ in self.libraries:
            with self.subTest(build=name):
                for uid, manager, allowed in ((10287, 0, 0), (10287, 0, 1),
                                               (10288, 1, 0), (2000, 0, 1)):
                    lib.caller(uid, manager, allowed, 0)
                    for session in (0, 1):
                        self.assertEqual(lib.query(self.commands["LOOKUP_SYMBOLS"], session), -1)
                lib.caller(0, 0, 0, 0)
                self.assertEqual(lib.query(self.commands["LOOKUP_SYMBOLS"], 0), 41)

    def test_debug_build_does_not_implicitly_authorize_shell(self):
        for name, _, default in self.libraries:
            with self.subTest(build=name):
                self.assertEqual(default, 0)

    def test_gki_export_contains_permission_dependencies(self):
        for path in ("supercall/perm.c", "supercall/internal.h", "supercall/dispatch.c",
                     "supercall/supercall.c", "core/init.c"):
            self.assertIn("kernel/" + path, PRIVATE.GKI_FILES)


if __name__ == "__main__":
    unittest.main()
