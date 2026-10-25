# BakaSU Pro upstream sync — 2026-10-25

## Scope

- Local branch: `codex/build-35233`; original Pro commit: `cc2e4f766b2ee41123bdc80ad6d9a8f108620685`.
- Official upstream: `Baka-SU/BakaSU`, main at `d5e9e025b8b49155f8014684d64c91742b465f65` (23 incoming commits).
- Application self-update source: `vring99/BakaSU`, with the private workflow and final signed artifact.
- No remote push, Actions dispatch, publication, installation or device flashing is part of this change.

## Integration decisions

Import official module repository/script support, flash result UI, hot installation, boot feature configuration,
ADB-only shell-root option, module blacklist, compatibility fixes and translations. Keep the existing Pro
private-certificate trust boundary, information/fd authorization checks, shell opt-in default, channel suffix,
optional/random package selection, four architectures and universal APK.

Do not restore Magica components, automatic jailbreak or public `ksu://action`/`ksu://webui` filters.
Remove the reintroduced Serbian translations for those deleted controls.

Use the official preinit generator and native ELF/older-kernel compatibility changes, removing the previous
duplicate generator. Keep Pro's tested policy helpers, SELinux fixes and external disabled-preinit callbacks
for SUSFS. Deduplicate the symbol lookup UAPI, handler and userspace wrapper that were previously backported.
Retain `--no-preinit` through upstream's shared boot configuration and capsule format.

Rebase the exported GKI patch on official `d5e9e025`, not `35229`: the old base lacks the new code generators
and feature objects. The historical `gki-manager-signature-35229.patch` remains unchanged.

## Verification

- Update-source JVM tests: 6 assertions groups failed against the old configuration, then all passed.
- GKI export regression: applying the patch to the old base lacked `shell_su_adb_only.c`; using the current
  upstream base passes the dependency check in an isolated temporary index.
- Python discovery passes (reports 15 tests; seven tests or test classes are skipped because Clang/GNU make
  are unavailable). These skips include native permission and SELinux execution tests.
- Root `:spotlessCheck` passes with `--offline --configure-on-demand` (after `:spotlessApply`).
- Full `:app:testDebugUnitTest :app:assembleRelease :app:lintRelease` is blocked during configuration by
  the missing Android NDK. No APK was generated or installed.
- A separate read-only code review found an upstream test calling nonexistent `assets::get_asset_data`;
  corrected the test to the existing `assets::get_asset`. Cargo tests are not runnable on this host.
- GitHub API read-only checks resolve the intended manual build and its unexpired final artifact.
  The user's latest formal Release endpoint returns HTTP 404; beta Actions updates are the available channel.
- No kernel-build, device-boot or downloaded-update installation claim is made by these source/host checks.

## Update limitations

The update checker does not publish releases. Stable updates require a formal release in the user's repository;
beta updates use successful Actions artifacts and their normal retention period. Random package names remain
supported, but an in-place update requires the original package name and private signing key. Existing APKs
continue using their compiled-in settings until replaced by a newly built APK.
