# SUSFS supplies inline entry points into the shared KSU SELinux implementation.
ifneq ($(CONFIG_KSU),y)
$(error SUSFS inline hooks require built-in CONFIG_KSU=y; use Tracepoint for LKM)
endif

$(eval $(call check_ksu_hook,ksu_selinux_hide_running,$(srctree)/security/selinux/hooks.c))
$(eval $(call check_ksu_hook,ksu_selinux_hide_running,$(srctree)/security/selinux/selinuxfs.c))
$(eval $(call check_ksu_hook,fake_status_initialize_key,$(srctree)/security/selinux/selinuxfs.c))
$(eval $(call check_ksu_hook,initialize_fake_status,$(srctree)/security/selinux/selinuxfs.c))

$(eval $(call check_ksu_hook,my_setprocattr,$(srctree)/security/selinux/hooks.c))
$(eval $(call check_ksu_hook,my_write_context,$(srctree)/security/selinux/selinuxfs.c))
$(eval $(call check_ksu_hook,my_write_access,$(srctree)/security/selinux/selinuxfs.c))
ccflags-y += -DKSU_COMPAT_HAS_SUSFS_FEATURE_SELINUX_HIDE
$(info -- $(REPO_NAME): using shared KSU SELinux fixes through SUSFS inline hooks)

# susfs's dev branch currently using post_execve_hook
# but in other branch, it still direcctly call ksu_install_su_fd
# to avoid install su fd repeatedly
ifeq ($(shell grep -q "ksu_install_su_fd" $(srctree)/fs/exec.c; echo $$?),0)
$(info -- $(REPO_NAME)/compat: ksu_install_su_fd direct call found)
ccflags-y += -DKSU_COMPAT_HAS_SUSFS_INSTALL_SU_FD_DIRECT_CALL
endif
