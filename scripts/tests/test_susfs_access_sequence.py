"""Exercise the production SUSFS response adapter without changing policy."""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


def extract(source, name):
    match = re.search(r"static ssize_t " + name + r"\([^;]+?\)\n\{", source)
    assert match, name
    end, depth = match.end(), 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[match.start():end]


def harness():
    source = (ROOT / "kernel/feature/selinux_hide.c").read_text()
    return r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include <sys/types.h>
typedef unsigned int u32;
#define SIMPLE_TRANSACTION_LIMIT 4096
#define scnprintf snprintf
#define READ_ONCE(x) (x)
#define ksu_get_uid_t(x) (x)
struct file { int unused; };
struct selinux_kernel_status { u32 policyload; };
struct page { struct selinux_kernel_status status; };
static struct page page = {{1}}, *fake_status = &page;
static bool ksu_selinux_hide_running = true;
static unsigned int uid = 10530, calls;
static ssize_t result;
static const char *response;
static unsigned int current_uid(void) { return uid; }
static void *page_address(struct page *p) { return &p->status; }
static ssize_t susfs_access_original(struct file *file, char *buf, size_t size) {
    (void)file; (void)size;
    calls++;
    if (result > 0) strcpy(buf, response);
    return result;
}
''' + extract(source, "ksu_susfs_access_result") + "\n" + extract(source, "ksu_susfs_write_access") + r'''
int main(void) {
    char buf[4096];
    response="400 ffffffff 0 ffffff7f 4 0"; result=strlen(response);
    assert(ksu_susfs_write_access(0,buf,29)>0);
    assert(!strcmp(buf,"400 ffffffff 0 ffffff7f 1 0") && calls==1);
    uid=0; ksu_susfs_write_access(0,buf,29); assert(!strcmp(buf,response));
    uid=10530; ksu_selinux_hide_running=false;
    ksu_susfs_write_access(0,buf,29); assert(!strcmp(buf,response));
    ksu_selinux_hide_running=true; fake_status=0;
    ksu_susfs_write_access(0,buf,29); assert(!strcmp(buf,response));
    fake_status=&page; page.status.policyload=7;
    ksu_susfs_write_access(0,buf,29); assert(!strcmp(buf,"400 ffffffff 0 ffffff7f 7 0"));
    result=-13; strcpy(buf,"untouched");
    assert(ksu_susfs_write_access(0,buf,29)==-13 && !strcmp(buf,"untouched"));
    result=0; assert(ksu_susfs_write_access(0,buf,29)==0);
    response="malformed"; result=strlen(response);
    assert(ksu_susfs_write_access(0,buf,29)==result && !strcmp(buf,response));
    response="0 0 0 0 123456 1"; result=strlen(response);
    ksu_susfs_write_access(0,buf,29); assert(!strcmp(buf,"0 0 0 0 7 1"));
    assert(calls==9); puts("PASS: sequence adapter, unchanged decisions/errors, UID and feature gates");
    return 0;
}
'''


class SusfsAccessSequenceTests(unittest.TestCase):
    def test_response_adapter(self):
        compiler = os.environ.get("CC") or shutil.which("cc") or shutil.which("clang")
        if not compiler:
            self.skipTest("host compiler required")
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory) / "sequence.c"
            exe = Path(directory) / ("sequence.exe" if os.name == "nt" else "sequence")
            src.write_text(harness())
            subprocess.run([compiler, "-Wall", "-Wextra", "-Werror", str(src), "-o", str(exe)], check=True)
            subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    unittest.main()
