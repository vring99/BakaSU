#ifndef __KSU_COMPAT_SUSFS_PREINIT_H
#define __KSU_COMPAT_SUSFS_PREINIT_H

struct filename;
struct user_arg_ptr;

int ksu_setup_preinit_file(struct filename **filename_ptr, struct user_arg_ptr *argv_user);
int ksu_preinit_handle_post_execveat(int *fd, struct filename **filename_ptr,
                                   void *argv_user, void *envp_user,
                                   int *flags, int *retval, int *preinit_fd);

#endif
