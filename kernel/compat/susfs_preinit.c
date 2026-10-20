#include <linux/errno.h>

#include "susfs_preinit.h"

/* Keep the official hooks linkable when target UAPI headers disable the runner. */
#ifdef KSU_NO_PREINIT
int ksu_setup_preinit_file(struct filename **filename_ptr, struct user_arg_ptr *argv_user)
{
    return -EOPNOTSUPP;
}

int ksu_preinit_handle_post_execveat(int *fd, struct filename **filename_ptr, void *argv_user, void *envp_user,
                                     int *flags, int *retval, int *preinit_fd)
{
    return 0;
}
#endif
