// SELinux query hooks live in the SUSFS-patched kernel, not in this driver.
#include <linux/errno.h>
#include <linux/init.h>
#include <linux/jump_label.h>
#include <linux/mm.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/version.h>
#include <security.h>
#include <ss/policydb.h>
#include <ss/services.h>
#include <ss/sidtab.h>

#include "klog.h" // IWYU pragma: keep
#include "ksu.h"
#include "policy/feature.h"
#include "selinux/sepolicy.h"
#include "selinux_hide.h"

#if LINUX_VERSION_CODE < KERNEL_VERSION(5, 10, 0)
#error Native SUSFS SELinux integration requires a GKI 5.10 or newer kernel
#endif

static DEFINE_MUTEX(selinux_hide_mutex);
bool ksu_selinux_hide_enabled __read_mostly;
bool ksu_selinux_hide_running __read_mostly;
DEFINE_STATIC_KEY_FALSE(fake_status_initialize_key);
struct page *fake_status;

#ifdef KSU_SUSFS_HAS_FAKE_STATE
struct selinux_state fake_state;
#endif

void initialize_fake_status(void);

void initialize_fake_status(void)
{
    struct selinux_kernel_status *status, *new_status;
    struct page *new_page;

    mutex_lock(&selinux_state.status_lock);
    if (fake_status || !selinux_state.status_page)
        goto out;

    status = page_address(selinux_state.status_page);
    if (!status->enforcing)
        goto out;

    new_page = alloc_page(GFP_KERNEL | __GFP_ZERO);
    if (!new_page) {
        pr_err("initialize_fake_status: failed to allocate page\n");
        goto out;
    }
    new_status = page_address(new_page);
    memcpy(new_status, status, sizeof(*status));
    fake_status = new_page;
out:
    mutex_unlock(&selinux_state.status_lock);
}

void ksu_selinux_hide_handle_second_stage(void)
{
    initialize_fake_status();
    if (fake_status)
        static_key_disable(&fake_status_initialize_key.key);
    else
        pr_warn("selinux_hide: fake status needs late initialization\n");
}

void ksu_selinux_hide_handle_post_fs_data(void)
{
    static_key_disable(&fake_status_initialize_key.key);
    if (!fake_status)
        pr_err("selinux_hide: fake status is not initialized after post-fs-data\n");
}

static int selinux_hide_feature_get(u64 *value)
{
    *value = ksu_selinux_hide_enabled ? 1 : 0;
    return 0;
}

static int selinux_hide_feature_set(u64 value)
{
    bool enable = value != 0;
    int ret = 0;

    mutex_lock(&selinux_hide_mutex);
    ksu_selinux_hide_enabled = enable;
    if (enable && !ksu_selinux_hide_running) {
        if (!backup_sepolicy) {
            pr_err("no backup sepolicy available, please save feature and reboot to retry!\n");
            ret = -EAGAIN;
            goto out;
        }
#ifdef KSU_SUSFS_HAS_FAKE_STATE
        fake_state.initialized = true;
        fake_state.policy = backup_sepolicy;
#endif
        ksu_selinux_hide_running = true;
    } else if (!enable) {
        ksu_selinux_hide_running = false;
    }
out:
    mutex_unlock(&selinux_hide_mutex);
    return ret;
}

static const struct ksu_feature_handler selinux_hide_handler = {
    .feature_id = KSU_FEATURE_SELINUX_HIDE,
    .name = "selinux_hide",
    .get_handler = selinux_hide_feature_get,
    .set_handler = selinux_hide_feature_set,
};

void __init ksu_selinux_hide_init(void)
{
    if (ksu_register_feature_handler(&selinux_hide_handler))
        pr_err("Failed to register selinux_hide feature handler\n");
    static_key_enable(&fake_status_initialize_key.key);
}

void __exit ksu_selinux_hide_exit(void)
{
    mutex_lock(&selinux_hide_mutex);
    ksu_selinux_hide_running = false;
    mutex_unlock(&selinux_hide_mutex);
    static_key_disable(&fake_status_initialize_key.key);
    ksu_unregister_feature_handler(KSU_FEATURE_SELINUX_HIDE);
    mutex_lock(&selinux_state.status_lock);
    if (fake_status)
        __free_page(fake_status);
    fake_status = NULL;
    mutex_unlock(&selinux_state.status_lock);
}

void ksu_selinux_hide_drop_backup_if_unused(void)
{
    mutex_lock(&selinux_hide_mutex);
    if (!ksu_selinux_hide_running && backup_sepolicy) {
#ifdef KSU_SUSFS_HAS_FAKE_STATE
        fake_state.policy = NULL;
        fake_state.initialized = false;
#endif
        sidtab_destroy(backup_sepolicy->sidtab);
        kfree(backup_sepolicy->sidtab);
        ksu_destroy_sepolicy(backup_sepolicy);
        backup_sepolicy = NULL;
    }
    mutex_unlock(&selinux_hide_mutex);
}
