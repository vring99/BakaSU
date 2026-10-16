#include <linux/types.h>

#include "supercall/internal.h"
#include "manager/manager_identity.h"
#include "policy/allowlist.h"

#include "compat/kernel_compat.h"

bool only_manager(void)
{
    return is_manager();
}

bool only_root(void)
{
    return ksu_get_uid_t(current_uid()) == 0;
}

bool manager_or_root(void)
{
    return ksu_get_uid_t(current_uid()) == 0 || is_manager();
}

bool allowed_for_su(void)
{
    bool is_allowed = is_manager() || ksu_is_allow_uid_for_current(ksu_get_uid_t(current_uid()));

    return is_allowed;
}

bool allowed_for_driver(void)
{
    // Boot/ksud callers may be root outside the KernelSU SELinux domain.
    // Recheck the current caller even when a driver fd predates revocation.
    return only_root() || allowed_for_su();
}
