# Current SUSFS owns the SELinux query hooks; BakaSU owns their state and lifecycle.
ifneq ($(CONFIG_KSU),y)
$(error SUSFS inline hooks require built-in CONFIG_KSU=y; use Tracepoint for LKM)
endif

$(eval $(call check_ksu_hook,ksu_selinux_hide_running,$(srctree)/security/selinux/hooks.c))
$(eval $(call check_ksu_hook,ksu_selinux_hide_running,$(srctree)/security/selinux/selinuxfs.c))
$(eval $(call check_ksu_hook,fake_status_initialize_key,$(srctree)/security/selinux/selinuxfs.c))
$(eval $(call check_ksu_hook,initialize_fake_status,$(srctree)/security/selinux/selinuxfs.c))

ifeq ($(shell grep -qw "fake_state" $(srctree)/security/selinux/hooks.c; echo $$?),0)
$(eval $(call check_ksu_hook,fake_state,$(srctree)/security/selinux/selinuxfs.c))
ccflags-y += -DKSU_SUSFS_HAS_FAKE_STATE
else
$(eval $(call check_ksu_hook,my_security_context_to_sid,$(srctree)/security/selinux/hooks.c))
$(foreach symbol,my_security_context_to_sid my_security_context_str_to_sid my_security_sid_to_context my_security_compute_av_user,\
    $(eval $(call check_ksu_hook,$(symbol),$(srctree)/security/selinux/ss/services.c))\
    $(eval $(call check_ksu_hook,$(symbol),$(srctree)/security/selinux/selinuxfs.c)))
endif
$(info -- $(REPO_NAME): using native SUSFS SELinux integration)

# susfs's dev branch currently using post_execve_hook
# but in other branch, it still direcctly call ksu_install_su_fd
# to avoid install su fd repeatedly
ifeq ($(shell grep -q "ksu_install_su_fd" $(srctree)/fs/exec.c; echo $$?),0)
$(info -- $(REPO_NAME)/compat: ksu_install_su_fd direct call found)
ccflags-y += -DKSU_COMPAT_HAS_SUSFS_INSTALL_SU_FD_DIRECT_CALL
endif
