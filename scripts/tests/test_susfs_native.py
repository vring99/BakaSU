"""Compile the native adapter and exercise its Make interface checks."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_private_manager import PRIVATE

ROOT = Path(__file__).resolve().parents[2]
KERNEL = ROOT / "kernel"


def find_tool(name, ndk_relative):
    found = shutil.which(name)
    if found:
        return found
    sdk = os.environ.get("ANDROID_SDK_ROOT") or os.environ.get("ANDROID_HOME")
    if sdk:
        candidates = sorted(Path(sdk).glob(f"ndk/*/{ndk_relative}"))
        if candidates:
            return str(candidates[-1])
    return None


class NativeSusfsTests(unittest.TestCase):
    def test_optional_export_includes_native_object_dependencies(self):
        self.assertIn("kernel/feature/selinux_hide_susfs.c", PRIVATE.GKI_FILES)
        self.assertIn("kernel/tools/susfs_compat.mk", PRIVATE.GKI_FILES)

    def test_source_selection_preserves_tracepoint(self):
        source = (KERNEL / "Kbuild").read_text()
        selection = re.search(
            r"ifeq \(\$\(CONFIG_KSU_SUSFS\),y\)\n"
            r"kernelsu-objs \+= feature/selinux_hide_susfs.o\nelse\n"
            r"kernelsu-objs \+= feature/selinux_hide.o\nendif", source
        )
        self.assertIsNotNone(selection)

    def test_native_adapter_compiles_for_all_gki_families(self):
        clang = find_tool("clang", "toolchains/llvm/prebuilt/*/bin/clang.exe")
        if not clang:
            self.skipTest("clang is required")
        # Only platform primitives are stubbed; compile the actual adapter and
        # feature handler declaration, including kernel-side symbol consumers.
        base = """
#ifndef TEST_KERNEL_H
#define TEST_KERNEL_H
typedef _Bool bool;
typedef unsigned int u32;
typedef unsigned long long u64;
typedef __SIZE_TYPE__ size_t;
#define true 1
#define false 0
#define NULL ((void *)0)
#define __read_mostly
#define __init
#define __exit
#define GFP_KERNEL 1
#define __GFP_ZERO 2
#define EAGAIN 11
#define KERNEL_VERSION(a,b,c) (((a)<<16)+((b)<<8)+(c))
struct mutex { int locked; };
#define DEFINE_MUTEX(n) struct mutex n
void mutex_lock(struct mutex *);
void mutex_unlock(struct mutex *);
struct static_key { int enabled; };
struct static_key_false { struct static_key key; };
#define DEFINE_STATIC_KEY_FALSE(n) struct static_key_false n
void static_key_enable(struct static_key *);
void static_key_disable(struct static_key *);
struct page;
void *page_address(struct page *);
struct page *alloc_page(int);
void __free_page(struct page *);
void kfree(void *);
void *memcpy(void *, const void *, __SIZE_TYPE__);
struct sidtab;
void sidtab_destroy(struct sidtab *);
struct selinux_policy { struct sidtab *sidtab; };
struct selinux_state {
    struct mutex status_lock;
    struct page *status_page;
#ifdef KSU_SUSFS_HAS_FAKE_STATE
    bool initialized;
    struct selinux_policy *policy;
#endif
};
struct selinux_kernel_status { u32 sequence, enforcing, policyload; };
extern struct selinux_state selinux_state;
extern struct selinux_policy *backup_sepolicy;
void ksu_destroy_sepolicy(struct selinux_policy *);
#define pr_err(...) ((void)0)
#define pr_warn(...) ((void)0)
#endif
"""
        source = (KERNEL / "feature/selinux_hide_susfs.c").read_text()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "base.h").write_text(base)
            for header in re.findall(r'^#include [<"]([^>"]+)[>"]', source, re.M):
                path = root / header
                path.parent.mkdir(parents=True, exist_ok=True)
                if header == "policy/feature.h":
                    shutil.copyfile(KERNEL / header, path)
                elif header == "selinux_hide.h":
                    shutil.copyfile(KERNEL / "feature" / header, path)
                else:
                    path.write_text('#include "base.h"\n')
            for header in ("linux/types.h", "linux/sched.h"):
                (root / header).write_text('#include "base.h"\n')
            (root / "uapi").mkdir()
            shutil.copyfile(ROOT / "uapi/feature.h", root / "uapi/feature.h")
            unit = root / "adapter.c"
            unit.write_text(source)
            consumer = root / "consumer.c"
            consumer.write_text('''#include "base.h"
extern bool ksu_selinux_hide_running, ksu_selinux_hide_enabled;
extern struct page *fake_status;
extern struct static_key_false fake_status_initialize_key;
extern void initialize_fake_status(void);
#ifdef KSU_SUSFS_HAS_FAKE_STATE
extern struct selinux_state fake_state;
#endif
void consume(void) {
    initialize_fake_status();
    (void)ksu_selinux_hide_running;
    (void)ksu_selinux_hide_enabled;
    (void)fake_status;
    (void)fake_status_initialize_key;
#ifdef KSU_SUSFS_HAS_FAKE_STATE
    (void)fake_state;
#endif
}
''')
            for major, minor in ((5, 10), (5, 15), (6, 1), (6, 6), (6, 12)):
                flags = [f"-DLINUX_VERSION_CODE={(major << 16) + (minor << 8)}"]
                if (major, minor) < (6, 6):
                    flags.append("-DKSU_SUSFS_HAS_FAKE_STATE=1")
                with self.subTest(kernel=f"{major}.{minor}"):
                    result = subprocess.run(
                        [clang, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
                         "-fsyntax-only", "-I", str(root), *flags, str(unit), str(consumer)],
                        capture_output=True, text=True,
                    )
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_make_accepts_current_interfaces_and_rejects_missing_hooks(self):
        make = find_tool("make", "prebuilt/*/bin/make.exe")
        if not make:
            self.skipTest("GNU make is required")
        env = os.environ.copy()
        if os.name == "nt":
            git_bin = Path("C:/Program Files/Git/usr/bin")
            if not (git_bin / "sh.exe").exists():
                self.skipTest("Git shell is required on Windows")
            env["PATH"] = str(git_bin) + os.pathsep + env["PATH"]
        inline = (KERNEL / "tools/inline_hook_check.mk").read_text()
        check = inline[:inline.index("endef") + len("endef")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "security/selinux/ss").mkdir(parents=True)
            (root / "fs").mkdir()
            (root / "fs/exec.c").write_text("ksu_install_su_fd\n")
            shutil.copyfile(KERNEL / "tools/susfs_compat.mk", root / "compat.mk")
            (root / "Makefile").write_text(
                "SHELL := sh\nsrctree := .\nCONFIG_KSU := y\nREPO_NAME := test\n" + check +
                '\ninclude compat.mk\nall:\n\t@echo "$(ccflags-y)"\n'
            )
            hooks = root / "security/selinux/hooks.c"
            selinuxfs = root / "security/selinux/selinuxfs.c"
            services = root / "security/selinux/ss/services.c"
            common = "ksu_selinux_hide_running\nfake_status_initialize_key\ninitialize_fake_status\n"
            helpers = ("my_security_context_to_sid\nmy_security_context_str_to_sid\n"
                       "my_security_sid_to_context\nmy_security_compute_av_user\n")

            def run(*args):
                return subprocess.run([make, "--no-print-directory", *args], cwd=root,
                                      env=env, capture_output=True, text=True)

            for kind in ("state", "policy"):
                with self.subTest(interface=kind):
                    hooks.write_text(common + ("fake_state\n" if kind == "state" else helpers))
                    selinuxfs.write_text(hooks.read_text())
                    services.write_text(helpers)
                    result = run()
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("KSU_COMPAT_HAS_SUSFS_INSTALL_SU_FD_DIRECT_CALL", result.stdout)
                    self.assertEqual("KSU_SUSFS_HAS_FAKE_STATE" in result.stdout, kind == "state")
                    self.assertNotEqual(run("CONFIG_KSU=m").returncode, 0)
                    # An incomplete kernel patch must fail rather than silently use old hooks.
                    selinuxfs.write_text(selinuxfs.read_text().replace("initialize_fake_status", ""))
                    self.assertNotEqual(run().returncode, 0)
            selinuxfs.write_text(common + helpers)
            services.write_text(helpers.replace("my_security_compute_av_user", ""))
            self.assertNotEqual(run().returncode, 0)
            hooks.write_text("ksu_selinux_hide_running\nsecurity_context_to_sid_with_policy\n")
            self.assertNotEqual(run().returncode, 0)


if __name__ == "__main__":
    unittest.main()
