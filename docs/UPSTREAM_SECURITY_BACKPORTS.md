# Pro maintenance backports — 2026-11-10

## 35275 userspace security fixes

- KernelSU `a23184a0e`: quote SELinux policy and profile/template arguments as literal Shell values; validate module IDs before running actions. Reuse Pro's existing single-quote helper and retain dedicated Shell handling.
- KernelSU `dbb73665d`: validate profile names before directory creation or file access, rejecting empty names, dot/dot-dot, slashes, NUL and line breaks. Applied to Pro's android/profile.rs, preserving legacy template parsing compatibility.
- Manager version code has a 35275 floor; subsequent Git-derived versions can advance normally.
- Added Shell quoting and profile-path regression cases. Local provenance gate passes; Android build and executable regression results must be verified separately.

## Adaptive navigation alignment

KernelSU `02ffbd447` WindowSize.kt is ported with only the package changed.
Navigation and theme settings now use the actual Compose window size: width >= 840dp,
or width >= 600dp and height/width < 1.2. Pro retains its navigation components
and tablet Manifest declarations. This does not change OEM compatibility settings.

Base: Pro `eb576bf3c`, with official BakaSU `d5e9e025b` runtime baseline.

## Imported changes

- BakaSU `f98b7a5b909910e1830cae8a2f9c78a61f1f6c2a`: resolve the SELinux inode blob offset from vmlinux BTF for modular builds with BTF. Fail initialization on lookup errors instead of using an invalid offset. Built-in/no-BTF paths use the target kernel's compiled layout.
- BakaSU `e5473cdf2`: follow-up removing the inconsistent 5.10 version guard from the inode initialization declaration.
- SukiSU `708f083c4f5b10ec150cf43ea842c0b3ccba963a`: drop the temporary open reference after the wrapper successfully acquires its own reference. Error handling is unchanged.
- SukiSU `85d05cf22bb0bcc7d41d555221d7eedc850b709f`: increment `latest_granting` when publishing a replacement policy and pass that generation to AVC reset, netlink notification and status updates. Adapted to BakaSU compatibility branches. Legacy policydb paths retain their existing zero-generation behavior; this is not a fix for those older paths.

The private signer table, driver access checks, shell defaults, package selection, and Magica removal remain intact. The existing tablet Manifest edit is unrelated to these backports.

## Dynamic manager scope

SukiSU's multi-manager implementation was not imported. It changes the registration ABI, userspace integration, persistence and package/UID verification model. Pro retains its existing certificate-based dynamic manager mechanism. Do not describe this work as adding package/UID binding or disabling dynamic trust.

## Delivery and validation

The GKI patch exporter includes all new BTF/inode files and the modified SELinux/file-wrapper sources. Its dependency check applies the exported patch to an isolated Git index.

`python -m unittest discover -s scripts/tests -v`: 16 tests reported, OK with 3 skips (Clang unavailable; executable authorization/identity/symbol checks not run). Source checks and patch application are not a complete GKI/LKM build or device validation. Full builds for the target configurations and runtime SELinux/file-wrapper checks remain required before shipping.

These changes are local only: no push, Actions build, APK release or device installation was performed.

## Official main synchronization - 2026-11-10

Target: BakaSU `516d3e87fbc986ccefdde2c2765f1700612441a9`.

- Applied `5785bdb80` and `516d3e87f`: both ksud and ksuinit defaults now include `vklp_smaps_rollup`, with upstream formatting.
- Applied the scripts/ksubot.py portion of `01c11c70b`. The bot was not executed; no messages were sent.
- Retained Pro's replacement build-manager.yml and private build workflow. These already replace the upstream normal/spoofed matrix and preserve private signing and configurable package names.
- Translation changes on weblate-main are outside this main-branch target.
- Source changes remain local, without a merge commit, push, build or release.

## KernelSU main maintenance backports - 2026-11-10

Reference: tiann/KernelSU `dd1a0c0d3fe174dc3daf89b04c55579cb4acd6be`.

- `dd1a0c0d3`: preserve syscall-enter skip result (-1) on x86_64.
- `9ae6e65aa`: ARM64 syscall argument 1 uses orig_x0 on 7.3+.
- `c680b548f`: runner ELF maximum page size 64K, contiguous load layout. Adapted to Pro's split preinit_runner.mk; ARM libgcc linkage retained.
- `019a3c010` and `ca3466597`: original type generation metadata and single-parse setprocattr path with stale-metadata dual-parse fallback. Modern selinux_policy paths use upstream parser/ESTALE retry logic. Legacy policydb paths retain their previous implementation. Vendor context_add_hash handling retained before SID insertion. Old-kernel behavior is not claimed fixed by these changes.
- `730f64461`: x-zip MIME declarations for both activity entries. Pro already detects ZIP content independent of intent MIME, so no restrictive MIME gate was added to IntentDispatcher.
- `2e661cdd3`: handle external URL failures at NavContainer's LocalUriHandler boundary, retaining Pro navigation and resource-backed messages.
- Official installation documentation is not copied because Pro has its own signing/install contracts. This is a selective functional backport, not a full upstream merge.

Validation: host unittest suite reports 17 tests, OK with 3 Clang-dependent skips. The new GCC-compiled test runs the production original-type metadata helpers and checks generation rollover, stale-generation and policy-pointer fallback, and new/original type classification. Patch export and diff whitespace checks pass. XML manifests/string resources parse successfully.

Manager spotlessApply/spotlessCheck/assembleRelease/lintRelease were attempted but blocked during configuration because the local SDK lacks NDK 28.2.13676358. No formatter, Android lint or APK build success is claimed. Full kernel builds and device validation remain pending. No push or release was performed.
