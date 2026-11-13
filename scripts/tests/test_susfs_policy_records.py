"""Exercise the production commit-time recorder with small policydb fixtures.

No SELinux/RCU emulation: this verifies record selection, original values,
repeated updates, error reporting and the disabled/old-SUSFS link boundary.
"""
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def function(source, name):
    start = source.index("void " + name + "(")
    end = source.index("{", start) + 1
    depth = 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


class SusfsPolicyRecordsTests(unittest.TestCase):
    def test_maintenance_version_does_not_follow_commit_count(self):
        make = os.environ.get("MAKE") or shutil.which("make")
        self.assertIsNotNone(make, "Set MAKE to GNU make")
        source = (ROOT / "kernel/Kbuild").read_text()
        manager = (ROOT / "manager/build.gradle.kts").read_text()
        self.assertRegex(manager, r'extra\["managerVersionCode"\] = 35275\s*\n')
        assignments = "\n".join(re.findall(r"^KSU_VERSION\s*:=.*$", source, re.M))
        self.assertTrue(assignments)
        with tempfile.TemporaryDirectory() as directory:
            mk = Path(directory) / "Makefile"
            mk.write_text(assignments + "\nall:\n\t@echo VERSION=$(KSU_VERSION)\n")
            for count in (4575, 4576, 4600):
                result = subprocess.run([make, "-s", "-f", str(mk), "KSU_LOCAL_VERSION=" + str(count)],
                                        capture_output=True, text=True, check=True)
                self.assertIn("VERSION=35275", result.stdout)

    def test_make_capability_detection(self):
        make = os.environ.get("MAKE") or shutil.which("make")
        self.assertIsNotNone(make, "Set MAKE to GNU make")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "fs").mkdir()
            (root / "security/selinux").mkdir(parents=True)
            (root / "fs/exec.c").write_text("")
            (root / "security/selinux/hooks.c").write_text("ksu_selinux_hide_running\n")
            mk = ROOT / "kernel/tools/susfs_compat.mk"
            (root / "Makefile").write_text("include " + mk.as_posix() +
                                           "\nall:\n\t@echo FLAGS=$(ccflags-y)\n")
            both = "int susfs_add_sus_type(\nint susfs_add_sus_avd_allowed_by_type(\n"
            for config, source, expected in (("y", both, True), ("y", "", False),
                    ("y", "int susfs_add_sus_type(\n", False), ("n", both, False)):
                with self.subTest(config=config, source=source):
                    (root / "fs/susfs.c").write_text(source)
                    args = [make, "-s", "-f", str(root / "Makefile"),
                            "srctree=" + root.as_posix(), "CONFIG_KSU_SUSFS=" + config]
                    if os.environ.get("BAKASU_TEST_BASH"):
                        args.append("SHELL=" + os.environ["BAKASU_TEST_BASH"])
                    result = subprocess.run(args, capture_output=True, text=True, check=True)
                    self.assertEqual("-DKSU_COMPAT_HAS_SUSFS_SELINUX_POLICY_RECORDS" in result.stdout, expected)

    def test_publication_boundaries(self):
        source = (ROOT / "kernel/selinux/rules.c").read_text()
        self.assertEqual(source.count("ksu_susfs_record_policy("), 4)
        self.assertEqual(source.count("ksu_susfs_record_policy(&old_pol->policydb, db);\n"
                                      "    rcu_assign_pointer(selinux_state.policy, pol);"), 2)
        self.assertEqual(source.count("ksu_susfs_record_policy(policydb_ptr, newpolicydb);\n"
                                      "    /* Save the old policydb to free later. */"), 2)
        # Both parse-error exits precede the sole runtime publication section.
        runtime = source[source.index("cursor.cur = payload;"):]
        self.assertLess(runtime.rindex("goto out_drop_new_policy;"),
                        runtime.index("ksu_susfs_record_policy("))

    def test_production_recorder(self):
        compiler = os.environ.get("CC") or shutil.which("cc") or shutil.which("clang")
        self.assertIsNotNone(compiler, "Set CC to a host C compiler")
        source = (ROOT / "kernel/selinux/sepolicy.c").read_text()
        recorder = function(source, "ksu_susfs_record_policy")
        macros = source[source.index("#define ksu_hash_for_each"):source.index("static struct avtab_node *get_avtab_node", source.index("#define ksu_hash_for_each"))]
        macros = macros[:macros.index("#if defined(CONFIG_KSU_SUSFS)")]
        prelude = r'''
typedef unsigned int u32;
typedef unsigned short u16;
#define NULL ((void *)0)
#define KERNEL_VERSION(a,b,c) (((a)<<16)|((b)<<8)|(c))
#define LINUX_VERSION_CODE KERNEL_VERSION(6,12,23)
#define AVTAB_ALLOWED 1
#define CHECK(x) do { if (!(x)) return __LINE__; } while (0)
struct type_datum { u32 value; int attribute; };
struct hashtab_node { char *key; void *datum; struct hashtab_node *next; };
struct hashtab { struct hashtab_node **htable; int size; };
struct avtab_key { u16 source_type, target_type, target_class, specified; };
struct avtab_node { struct avtab_key key; struct { union { u32 data; } u; } datum; struct avtab_node *next; };
struct avtab { struct avtab_node **htable; int nslot; };
struct policydb { struct { struct hashtab table; u32 nprim; } p_types; struct avtab te_avtab; };
static struct avtab_node *avtab_search_node(struct avtab *tab, struct avtab_key *key) {
    for (int i=0;i<tab->nslot;i++) for (struct avtab_node *n=tab->htable[i];n;n=n->next)
        if (n->key.source_type==key->source_type && n->key.target_type==key->target_type &&
            n->key.target_class==key->target_class && n->key.specified==key->specified) return n;
    return NULL;
}
static int reports;
#define pr_err(...) (reports++)
#if defined(CONFIG_KSU_SUSFS) && defined(KSU_COMPAT_HAS_SUSFS_SELINUX_POLICY_RECORDS)
static int type_calls, av_calls, fail;
static u32 saved[10], seen[10];
static int susfs_add_sus_type(const char *name, u32 value) {
    type_calls++; if (name[0]!='n' || value!=3) return -1; return fail;
}
static int susfs_add_sus_avd_allowed_by_type(u32 s, u32 t, u32 c, u32 bits) {
    av_calls++; if (fail) return fail;
    if (s>=10 || t!=1 || c!=1) return -1;
    if (!seen[s]) { saved[s]=bits; seen[s]=1; } return 0;
}
#endif
'''
        cases = r'''
int test_entry(void) {
    struct type_datum platform={1,0}, existing={2,0}, added={3,0}, attr={4,1};
    struct hashtab_node ta={"attribute",&attr,NULL}, tn={"new",&added,&ta},
        te={"existing",&existing,&tn}, tp={"platform",&platform,&te};
    struct hashtab_node *types[]={&tp};
    struct avtab_node o1={{1,1,1,1},{{3}},NULL}, n1={{1,1,1,1},{{7}},NULL},
        removed={{2,1,1,1},{{8}},NULL}, fresh={{3,1,1,1},{{16}},NULL},
        audit={{4,1,1,2},{{99}},NULL}, unchanged={{5,1,1,1},{{32}},NULL},
        xperm={{6,1,1,256},{{123}},NULL};
    struct avtab_node *oldnodes[]={&o1,&removed,&unchanged};
    struct avtab_node *newnodes[]={&n1,&fresh,&audit,&unchanged,&xperm};
    struct policydb old={{{types,1},2},{oldnodes,3}}, next={{{types,1},4},{newnodes,5}};
    ksu_susfs_record_policy(&old,&next);
#if defined(CONFIG_KSU_SUSFS) && defined(KSU_COMPAT_HAS_SUSFS_SELINUX_POLICY_RECORDS)
    CHECK(type_calls==1 && av_calls==3 && reports==0);
    CHECK(seen[1] && saved[1]==3 && seen[2] && saved[2]==8 && seen[3] && saved[3]==0);
    CHECK(!seen[4] && !seen[5] && !seen[6]);
    // Later updates preserve the first baseline; existing types are not re-added.
    next.p_types.nprim=old.p_types.nprim=4;
    o1.datum.u.data=7; n1.datum.u.data=15;
    ksu_susfs_record_policy(&old,&next);
    CHECK(type_calls==1 && av_calls==6 && saved[1]==3 && saved[3]==0);
    fail=-12;
    ksu_susfs_record_policy(&old,&next);
    CHECK(reports==1 && n1.datum.u.data==15 && o1.datum.u.data==7);
    // No mutation, no record, including a discarded copy never published.
    av_calls=0; fail=0;
    ksu_susfs_record_policy(&next,&next);
    CHECK(av_calls==0 && type_calls==1 && reports==1);
#else
    CHECK(reports==0);
#endif
    return 0;
}
#ifndef FREESTANDING_WINDOWS
int main(void) { return test_entry(); }
#endif
'''
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "records.c"
            exe = Path(directory) / ("records.exe" if os.name == "nt" else "records")
            src.write_text(prelude + macros + recorder + cases)
            flags = shlex.split(os.environ.get("SUSFS_TEST_CFLAGS", ""))
            for defines in ([], ["CONFIG_KSU_SUSFS"], ["KSU_COMPAT_HAS_SUSFS_SELINUX_POLICY_RECORDS"],
                            ["CONFIG_KSU_SUSFS", "KSU_COMPAT_HAS_SUSFS_SELINUX_POLICY_RECORDS"]):
                with self.subTest(defines=defines):
                    subprocess.run([compiler, "-std=c11", "-Wall", "-Werror", "-Wno-unused-function",
                                    *flags, *("-D"+d for d in defines), str(src), "-o", str(exe)], check=True)
                    subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    unittest.main()
