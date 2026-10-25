#ifndef __KSU_H_PREINIT
#define __KSU_H_PREINIT

#include <linux/types.h>
#include <asm/ptrace.h>

struct filename;
struct user_arg_ptr;

#ifdef CONFIG_KSU_SUSFS
#include "compat/susfs_preinit.h"
#endif

#ifndef KSU_NO_PREINIT
void ksu_preinit_init(void);
void ksu_preinit_exit(void);

#ifdef CONFIG_KSU_TRACEPOINT_HOOK
// Swap the runner in for PID 1's "/system/bin/init selinux_setup" execve.
// Returns true when it issued the syscall itself; the result is in *ret.
bool ksu_preinit_handle_execve_tracepoint(const char __user **filename_user, const char __user *const __user *argv_user,
                                          int orig_nr, struct pt_regs *regs, long *ret);
#elif defined(CONFIG_KSU_MANUAL_HOOK)
void ksu_preinit_handle_execve_manual(const char **filename, struct user_arg_ptr *argv);
#elif defined(CONFIG_KSU_SUSFS)
int ksu_setup_preinit_file(struct filename **filename_ptr, struct user_arg_ptr *argv_user);
int ksu_preinit_handle_post_execveat(int *fd, struct filename **filename_ptr, void *argv_user, void *envp_user,
                                     int *flags, int *retval, int *preinit_fd);
#else
#error Unsupported hook type
#endif

// Drop the staged runner if selinux_setup was never seen.
void ksu_preinit_release(void);

// Whether the runner is built in and not disabled with preinit=0.
bool ksu_preinit_enabled_param(void);
#else
static inline void ksu_preinit_init(void)
{
}
static inline void ksu_preinit_exit(void)
{
}
#ifdef CONFIG_KSU_TRACEPOINT_HOOK
// Swap the runner in for PID 1's "/system/bin/init selinux_setup" execve.
// Returns true when it issued the syscall itself; the result is in *ret.
static inline bool ksu_preinit_handle_execve_tracepoint(const char __user **filename_user,
                                                        const char __user *const __user *argv_user, int orig_nr,
                                                        struct pt_regs *regs, long *ret)
{
    return false;
}
#elif defined(CONFIG_KSU_MANUAL_HOOK)
static inline void ksu_preinit_handle_execve_manual(const char **filename, struct user_arg_ptr *argv)
{
}
#elif defined(CONFIG_KSU_SUSFS)
// External SUSFS hooks are provided by compat/susfs_preinit.c when disabled.
#else
#error Unsupported hook type
#endif
static inline void ksu_preinit_release(void)
{
}
static inline bool ksu_preinit_enabled_param(void)
{
    return false;
}
#endif

#endif // __KSU_H_PREINIT
