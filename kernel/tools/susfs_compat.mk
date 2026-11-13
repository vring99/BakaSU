# susfs selinux_hide feature
# old susfs won't have this manual hook
# and nongki 4.14- can't use simonpunk's hook for that
# check it, when there doesn't have, fallback to auto hook
ifeq ($(shell grep -q "ksu_selinux_hide_running" $(srctree)/security/selinux/hooks.c; echo $$?),0)
$(info -- $(REPO_NAME)/susfs_feature_check: selinux_hide manual hook found)
ccflags-y += -DKSU_COMPAT_HAS_SUSFS_FEATURE_SELINUX_HIDE
endif

# SUSFS 2.4 context/access queries consume policy records. Older manual hooks
# do not provide these APIs; detect both definitions rather than the version.
ifeq ($(CONFIG_KSU_SUSFS),y)
ifeq ($(shell grep -Eq '^int susfs_add_sus_type\>' $(srctree)/fs/susfs.c && grep -Eq '^int susfs_add_sus_avd_allowed_by_type\>' $(srctree)/fs/susfs.c; echo $$?),0)
$(info -- $(REPO_NAME)/susfs_feature_check: SELinux policy record API found)
ccflags-y += -DKSU_COMPAT_HAS_SUSFS_SELINUX_POLICY_RECORDS
endif
endif

# susfs's dev branch currently using post_execve_hook
# but in other branch, it still direcctly call ksu_install_su_fd
# to avoid install su fd repeatedly
ifeq ($(shell grep -q "ksu_install_su_fd" $(srctree)/fs/exec.c; echo $$?),0)
$(info -- $(REPO_NAME)/compat: ksu_install_su_fd direct call found)
ccflags-y += -DKSU_COMPAT_HAS_SUSFS_INSTALL_SU_FD_DIRECT_CALL
endif
