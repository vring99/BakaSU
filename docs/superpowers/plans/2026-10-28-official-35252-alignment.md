# Official 35252 alignment and Release rebuild

> Execution: inline with one read-only whole-change review before push.

## Approved scope

The user requested official source and build alignment, then explicitly excluded
restoring the previously removed features and pinned the baseline to official
35252. The immutable source baseline is
`d5e9e025b8b49155f8014684d64c91742b465f65` (4552 commits + 30700).

Keep BakaSU Pro branding, the current private signing identity, selectable/random
package names, own update endpoints, private-manager trust, driver/query permission
checks, and removal of Magica and ksu:// entrypoints. This run uses the existing
package `xlvletre.mxmuylfh.arzxguim` to permit an in-place update. Restore the other
runtime differences, including Pro-only SELinux/preinit adapters, to the official
baseline. Keep monotonic versionCode derived from this branch's history.

Use the existing `codex/build-35233` checkout per the user's earlier main-line
preference; do not touch the separate device-helper variant or `diagnostics/`.
Only push to `vring99/BakaSU`. No phone installation, reboot, full GKI build,
automatic release publication, Telegram upload, or AV-avoidance claim.

## Approach and verification

An unqualified reset would restore declined functionality and break private
manager identity. A merge alone would change nothing because official 35252 is
already an ancestor. Instead, reduce the downstream patch to the retained scope
and assert source parity outside a reviewed exception list.

Use official Release Gradle arguments, official Rust/DDK build recipes and
official `--strip` repacking. Keep private-key validation, secret redaction,
source-cache integrity checks and artifact verification as non-runtime guardrails.
Official signing keys are unavailable: the user's existing private certificate
remains intentional. No bit-for-bit reproducibility claim is made for floating
upstream toolchain dependencies.

## Tasks

- [x] 1. Add and run the pinned-baseline parity check (must fail on current
  unretained runtime customizations). Keep existing identity, Magica-removal and
  executable authorization regression tests.
- [x] 2. Restore unretained runtime files from the immutable baseline; remove only
  the obsolete custom helpers/tests. Restore official regular late-load logic
  while keeping Magica unavailable. Align manager and repack build commands.
- [ ] 3. Run source parity, retained regressions, build-command tests and diff
  checks. Review the full diff independently. Commit one focused change and push
  the existing branch to the user's origin.
- [ ] 4. Dispatch the private Release workflow with the existing package, wait for
  all required jobs, download the original final artifacts, and verify signatures,
  package/version/ABI, manifest exclusions, ZIP integrity and hashes locally.

## Review focus

- No accidental restoration of Magica, ksu://, multi-manager trust or shell bypass.
- APK and embedded LKM trust the same existing certificate; GKI patch round-trip.
- Late-load CLI and Rust function signatures stay consistent after removing Pro
  preinit switches.
- Official source restoration removes references to deleted custom helpers.
- No passwords/private key are committed, logged or uploaded as artifacts.

## Ledger

- Baseline: HEAD `54983206`; working tree contains only untracked `diagnostics/`.
- Baseline host tests: 15 tests, OK, 7 skips (Clang/GNU make unavailable).
- Ruling: preserve safe build-cache checks and signing-secret redaction because
  they do not change application behavior; dropping them would recreate known
  provenance/leakage risks.
- Ruling: official 35252 is the source baseline, not a versionCode downgrade;
  keeping the history-based version allows updating the installed 35268 APK.
- Task 1: parity gate failed on 32 unretained runtime files before restoration.
- Task 2: restored those files, removed obsolete Pro-only preinit helpers/tests,
  and restored regular late-load while preserving Magica removal.
- Build invocation tests: three failures before changes, then all three passed.
  Official assembleRelease invocation and --strip now selected; validation and
  secrets handling remain separate. These tests do not compile an APK.
- Host suite: 16 tests OK, 3 skips for missing Clang. CI must execute native tests.
- Ruling: permit trailing-whitespace/blank-line normalization in parity checks;
  official makefiles contain whitespace that fails git diff --check, with no
  runtime effect. Other unretained source content must match the pinned baseline.
- Known upstream test defect: lkm_image.rs tests refer to assets::get_asset_data,
  but assets exports get_asset. Restored exactly as requested; Release builds do
  not compile cfg(test). Do not claim the full Rust unit suite passes.
- Scope note: restoring official SUSFS/preinit removes Pro-only external GKI
  adapters. This build verifies LKM/manager, not external GKI+SUSFS integration.
- Final review: fresh read-only reviewer found no Critical/Important issues;
  independently ran parity, recipe tests and diff --check successfully.
- Final: minor (deferred): local-build documentation omits the actual-symlink
  prerequisite for Windows after restoring official CMake include paths. This
  checkout has text symlink placeholders; use Linux CI for this build.
- Final: Ruling: APK/LKM correctness and real Gradle configuration-cache behavior
  remain CI/artifact gates, not inferred from host mocks. Failure means repair
  before delivery. Rust cfg(test) defect and external GKI/device validation remain
  explicitly unverified; no full-Rust-suite or boot-compatibility claim is made.
- GKI export: reverse-check passed; isolated index based on d5e9e025 accepted the
  patch and matched all nine retained kernel sources exactly. actionlint and
  Python bytecode checks passed. diagnostics remains untracked and excluded.
- First delivery commit 772db7665 pushed to user's origin. CI prepare ran all
  25 native/identity/parity/recipe tests successfully, without skips.
- Separate Lints Check run 40628686053 reproduced three concrete failures:
  dispatch.c extra blank line, cli.rs single-expression arm formatting, and an
  unused error import left after Magica removal. Removed only those residues;
  the same CI checks are the RED/GREEN regression gate. No runtime policy change.
