"""Execute the shared SELinux query path with model kernel primitives.

This checks SID synchronization and call ordering, not on-device timing.
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


def function(source, name):
    match = re.search(r"^[\w *]+\b" + name + r"\([^;]*?\)\s*\{", source, re.M)
    if not match:
        raise AssertionError(f"Missing compiled production function {name}")
    depth, end = 1, match.end()
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


MODEL = r'''
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
typedef unsigned int u32;
typedef unsigned short u16;
typedef unsigned int gfp_t;
typedef __PTRDIFF_TYPE__ ssize_t;
typedef _Bool bool;
#define true 1
#define false 0
#define __nocfi
#define EINVAL 22
#define ENOMEM 12
#define ERANGE 34
#define GFP_KERNEL 0
#define SECSID_NULL 0
#define SIMPLE_TRANSACTION_LIMIT 4096
#define pr_err(...) ((void)0)
#define rcu_read_lock() ((void)0)
#define rcu_read_unlock() ((void)0)
#define rcu_dereference(p) (p)
#define likely(x) (x)
#define kfree free
#define ksu_get_uid_t(x) (x)
#define current_uid() caller_uid
#define current_sid() 7
#define avc_has_perm(...) permission()
#define security_bounded_transition(...) 0
#define scnprintf snprintf
#ifdef _WIN32
#define EXPORT __declspec(dllexport)
#else
#define EXPORT __attribute__((visibility("default")))
#endif
struct context { u32 user, role, type; };
struct symtab { int live, kind; };
struct user_datum { u32 value; };
struct role_datum { u32 value; };
struct type_datum { u32 value; int attribute; };
struct sidtab { unsigned int seen, entries; };
struct policydb { struct symtab p_users, p_roles, p_types; };
struct selinux_policy { struct policydb policydb; struct sidtab *sidtab; };
struct file { int unused; };
struct av_decision { u32 allowed, auditallow, auditdeny, seqno, flags; };
static struct sidtab backup_sids, live_sids;
static struct selinux_policy backup, live;
static struct selinux_policy *backup_sepolicy = &backup;
static struct { struct selinux_policy *policy; } selinux_state = { &live };
static unsigned int caller_uid;
static int denied, checks, originals, lookups, allocations;
static int permission(void) { ++checks; return denied ? -13 : 0; }
static void context_init(struct context *c) { memset(c, 0, sizeof(*c)); }
static void context_destroy(struct context *c) { (void)c; }
static void *symtab_search(struct symtab *s, const char *name) {
    static struct type_datum one = { 1, 0 }, two = { 2, 0 };
    ++lookups;
    if (!strcmp(name, s->kind == 0 ? "u" : s->kind == 1 ? "r" : "app")) return &one;
    if (s->live && s->kind == 2 && !strcmp(name, "extra")) return &two;
    return NULL;
}
static int mls_context_to_sid(struct policydb *p, char old, char *text,
                             struct context *c, struct sidtab *s, u32 def) {
    (void)p; (void)c; (void)s; (void)def;
    return old == ':' && !strcmp(text, "s0") ? 0 : -EINVAL;
}
static int policydb_context_isvalid(struct policydb *p, struct context *c) {
    (void)p; return c->user && c->role && c->type;
}
static int context_add_hash(struct policydb *p, struct context *c) {
    (void)p; (void)c; return 0;
}
static int sidtab_context_to_sid(struct sidtab *s, struct context *c, u32 *sid) {
    if (!(s->seen & (1u << c->type))) { s->seen |= 1u << c->type; ++s->entries; }
    *sid = c->type + 10;
    return 0;
}
static char *kmemdup_nul(const char *p, size_t n, gfp_t flags) {
    char *result; (void)flags; ++allocations;
    result = malloc(n + 1);
    if (result) { memcpy(result, p, n); result[n] = 0; }
    return result;
}
static void *kzalloc(size_t n, gfp_t flags) { (void)flags; return calloc(1, n); }
static int security_sid_to_context_with_policy(struct selinux_policy *p, u32 sid,
                                                char **text, u32 *length) {
    static const char canonical[] = "u:r:app:s0";
    (void)p; (void)sid; *length = sizeof(canonical);
    *text = malloc(*length); memcpy(*text, canonical, *length);
    return 0;
}
static void security_compute_av_user_with_policy(struct selinux_policy *p, u32 ssid,
                                                  u32 tsid, u16 tclass, struct av_decision *avd) {
    (void)p; (void)ssid; (void)tsid; (void)tclass;
    memset(avd, 0, sizeof(*avd)); avd->allowed = 1; avd->seqno = 9;
}
static ssize_t original_write(struct file *f, char *buf, size_t size) {
    (void)f; (void)buf; (void)size; ++originals; return 77;
}
static ssize_t (*orig_context_write)(struct file *, char *, size_t) = original_write;
static ssize_t (*orig_access_write)(struct file *, char *, size_t) = original_write;
struct task_security_struct { u32 sid; };
struct cred { struct task_security_struct security; };
static struct cred new_cred;
#define selinux_cred(c) (&(c)->security)
static struct cred *prepare_creds(void) { new_cred.security.sid = 7; return &new_cred; }
static void commit_creds(struct cred *c) { (void)c; }
static void abort_creds(struct cred *c) { (void)c; }
static int current_is_single_threaded(void) { return 1; }
static u32 ptrace_parent_sid(void) { return 0; }
typedef int (*setprocattr_fn)(const char *, void *, size_t);
static int original_attr(const char *name, void *value, size_t size) {
    (void)name; (void)value; (void)size; ++originals; return 77;
}
static struct { setprocattr_fn original; } selinux_setprocattr_hook = { original_attr };
'''

ENTRY = r'''
EXPORT void reset(unsigned int uid, int deny) {
    memset(&backup_sids, 0, sizeof(backup_sids)); memset(&live_sids, 0, sizeof(live_sids));
    backup.policydb = (struct policydb){{0, 0}, {0, 1}, {0, 2}};
    live.policydb = (struct policydb){{1, 0}, {1, 1}, {1, 2}};
    backup.sidtab = &backup_sids; live.sidtab = &live_sids;
    caller_uid = uid; denied = deny; checks = originals = lookups = allocations = 0;
}
EXPORT int query(int kind, int extra) {
    char buf[4096]; const char *context = extra ? "u:r:extra:s0" : "u:r:app:s0";
    if (kind == 0) { strcpy(buf, context); return (int)my_write_context(NULL, buf, strlen(buf)); }
    if (kind == 1) { snprintf(buf, sizeof(buf), "%s %s 1", context, context);
                    return (int)my_write_access(NULL, buf, strlen(buf)); }
    strcpy(buf, context);
#ifdef TEST_SUSFS
    return my_setprocattr("current", buf, strlen(buf));
#else
    return ksu_handle_selinux_setprocattr("current", buf, strlen(buf));
#endif
}
EXPORT int metric(int kind) {
    switch(kind) {
    case 0: return backup_sids.entries; case 1: return live_sids.entries;
    case 2: return checks; case 3: return originals; case 4: return lookups;
    default: return allocations;
    }
}
'''


class SharedSelinuxTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = clang_path()
        if not compiler:
            raise unittest.SkipTest("clang is required")
        cls.directory = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.directory.cleanup)
        root = Path(cls.directory.name)
        shared = (KERNEL / "feature/selinux_hide.c").read_text()
        (root / "selinux_hide.c").write_text(shared)
        for header in set(re.findall(r'^#include [<"]([^>"]+)[>"]', shared, re.M)):
            path = root / header
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("")
        cls.libraries = []
        for major, minor, susfs in ((5, 10, True), (5, 15, True), (6, 1, True),
                                    (6, 6, True), (6, 12, True), (6, 6, False)):
            name = f"{major}.{minor}-{'SUSFS' if susfs else 'LKM'}"
            flags = [f"-DLINUX_VERSION_CODE={(major << 16) + (minor << 8)}",
                     "-DKERNEL_VERSION(a,b,c)=(((a)<<16)+((b)<<8)+(c))",
                     "-DKSU_COMPAT_HAS_CONTEXT_ADD_HASH=1"]
            if susfs:
                flags += ["-DCONFIG_KSU_SUSFS=1", "-DKSU_COMPAT_HAS_SUSFS_FEATURE_SELINUX_HIDE=1"]
            entry = root / "selinux_hide.c"
            preprocessed = subprocess.check_output(
                [compiler, "-E", "-P", "-I", str(root), *flags, str(entry)], text=True)
            functions = ["string_to_context_struct", "security_context_to_sid_with_policy",
                         "my_write_context", "my_write_access", "ksu_handle_selinux_setprocattr"]
            if susfs:
                functions.append("my_setprocattr")
            unit = root / f"{name}.c"
            unit.write_text(MODEL + "\n" + "\n".join(function(preprocessed, f) for f in functions) + ENTRY)
            library = root / (name + (".dll" if os.name == "nt" else ".so"))
            result = subprocess.run([compiler, "-std=gnu11", "-Werror", "-shared", *(["-DTEST_SUSFS=1"] if susfs else []),
                                     *([] if os.name == "nt" else ["-fPIC"]),
                                     str(unit), "-o", str(library)], capture_output=True, text=True)
            if result.returncode:
                raise AssertionError(f"{name}: {result.stdout}{result.stderr}")
            lib = ctypes.CDLL(str(library))
            lib.reset.argtypes = [ctypes.c_uint, ctypes.c_int]
            lib.reset.restype = None
            lib.query.argtypes = [ctypes.c_int, ctypes.c_int]
            cls.libraries.append((name, lib, susfs))
            if os.name == "nt":
                import _ctypes
                cls.addClassCleanup(_ctypes.FreeLibrary, lib._handle)

    def test_valid_context_synchronizes_both_sid_tables_on_all_entry_points(self):
        for name, lib, _ in self.libraries:
            for kind in range(3):
                with self.subTest(build=name, entry=kind):
                    lib.reset(10287, 0)
                    self.assertGreater(lib.query(kind, 0), 0)
                    self.assertEqual((lib.metric(0), lib.metric(1)), (1, 1))
                    self.assertGreaterEqual(lib.metric(4), 6)

    def test_added_context_is_rejected_without_populating_either_sid_table(self):
        for name, lib, _ in self.libraries:
            for kind in range(3):
                with self.subTest(build=name, entry=kind):
                    lib.reset(10287, 0)
                    self.assertEqual(lib.query(kind, 1), -22)
                    self.assertEqual((lib.metric(0), lib.metric(1)), (0, 0))
                    self.assertEqual(lib.metric(4), 6)

    def test_permission_denial_precedes_context_parsing(self):
        for name, lib, _ in self.libraries:
            for kind in range(3):
                with self.subTest(build=name, entry=kind):
                    lib.reset(10287, 1)
                    self.assertEqual(lib.query(kind, 0), -13)
                    self.assertEqual(lib.metric(2), 1)
                    self.assertEqual((lib.metric(4), lib.metric(5)), (0, 0))

    def test_lkm_system_callers_keep_original_path(self):
        for name, lib, susfs in self.libraries:
            if susfs:
                continue
            for kind in range(3):
                with self.subTest(build=name, entry=kind):
                    lib.reset(2000, 0)
                    self.assertEqual(lib.query(kind, 0), 77)
                    self.assertEqual(lib.metric(3), 1)
                    self.assertEqual(lib.metric(4), 0)


if __name__ == "__main__":
    unittest.main()
