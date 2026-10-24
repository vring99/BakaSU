# Remove Magica Jailbreak Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the unused Magica privilege-escalation and boot-autostart path from the main BakaSU build while preserving normal KernelSU management and late-load behavior.

**Architecture:** Remove the Android Manifest components, UI/settings state, Java/Kotlin references, and native JNI bridge that start Magica. Remove only the Magica-specific `ksud` CLI flags and Rust module; keep the regular `late-load` command and all kernel, LKM, GKI, and manager paths unrelated to Magica.

**Tech Stack:** Android Manifest, Kotlin/Java, C JNI, Rust/Clap, XML resources, existing host and portable tests.

**Spec:** User request in the current conversation: remove Magica because it is unused.

## Global Constraints

- Apply changes only to `E:\project\BakaSU` on `codex/build-35233`.
- Preserve the pre-existing untracked `diagnostics/` directory.
- Do not change the independent `device-helper` worktree.
- Keep normal `late-load`, Root management, GKI, LKM, package/signature, and architecture behavior.

## Review Focus

- Android Manifest has no Magica service, receiver, zygote preload, or boot permission.
- Manager UI and settings no longer expose manual or automatic jailbreak controls.
- JNI and Rust no longer expose Magica-only launch flags or ADB bootstrap code.
- Regular `late-load` remains callable with its existing arguments.
- No source or resource retains a stale Magica reference that can reintroduce the removed path.

---

### Task 1: Remove manager-side Magica surface

**Files:**
- Modify: `manager/app/src/main/AndroidManifest.xml`
- Modify: `manager/app/src/main/java/org/bakasu/bakasu/KernelSUApplication.kt`
- Modify: `manager/app/src/main/java/org/bakasu/bakasu/ui/screen/main/HomePage.kt`
- Modify: `manager/app/src/main/java/org/bakasu/bakasu/ui/screen/main/SettingsPage.kt`
- Modify: `manager/app/src/main/java/org/bakasu/bakasu/data/settings/SettingsPlatformRepository.kt`
- Modify: `manager/app/src/main/java/org/bakasu/bakasu/domain/model/SettingsPlatform.kt`
- Modify: `manager/app/src/main/java/org/bakasu/bakasu/ui/viewmodel/SettingsViewModel.kt`
- Delete: `manager/app/src/main/java/org/bakasu/bakasu/magica/`
- Modify: `manager/app/src/main/res/values*/strings.xml`

Remove the zygote preload, service, boot receiver, boot permission, manual jailbreak button, automatic-jailbreak setting state, and related localized resources. Preserve late-load mode display and unrelated reboot/ADB-root settings.

### Task 2: Remove native and userspace Magica path

**Files:**
- Modify: `manager/app/src/main/cpp/jni.c`
- Modify: `userspace/ksud/src/android/cli.rs`
- Modify: `userspace/ksud/src/android/late_load/mod.rs`
- Delete: `userspace/ksud/src/android/late_load/magica.rs`
- Modify: `userspace/ksud/Cargo.toml`
- Modify: `userspace/ksud/Cargo.lock`

Delete the JNI fork/exec bridge and the `--magica` and `--post-magica` CLI flags. Keep ordinary late-load execution and remove the now-unused ADB client dependency.

### Task 3: Regression verification

- Run repository searches for Magica symbols, flags, component names, and stale resource references.
- Run `git diff --check` and the existing portable Python tests.
- Run standalone Rust compilation/tests available in the workspace and the manager Spotless/configuration check where the Android SDK permits it.
- Review the final diff and ensure only the main branch changed.
