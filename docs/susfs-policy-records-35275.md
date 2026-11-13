# Pro 35275: SUSFS SELinux policy records

The SUSFS 2.4 context/access query hooks consume type and original-allowed
records. Pro 35275 previously detected the manual hooks but never populated
these records. This does not imply that other SUSFS features failed.

## Compatibility

`susfs_compat.mk` detects both producer APIs in the kernel's `fs/susfs.c`.
With both APIs and `CONFIG_KSU_SUSFS=y`, BakaSU records policy changes before
publishing them. Older SUSFS retains its existing manual-hook behavior; builds
without SUSFS retain the BakaSU path and have no references to these APIs.
This change does not add compatibility for unrelated obsolete inline hooks.

The kernel version code is fixed at 35275 for this maintenance release. Git
commit identity still distinguishes the corrected source from the old build.

## Recording boundary

Both initial rules and runtime policy batches use a private policy copy. The
recorder compares the old and new copies immediately before publication,
under the existing policy writer mutex. Rejected batches never reach it.

- Only newly created concrete types are registered, excluding attributes and
  pre-existing platform types.
- Changed and removed `AVTAB_ALLOWED` rules retain the old bitmap; newly added
  rules record zero. Audit and extended-permission entries are excluded.
- SUSFS retains the first bitmap for a key across repeated updates.
- Type attribute, transition, permissive and xperm operations have no separate
  producer API here. This fix does not claim complete policy-view equivalence.

SUSFS exposes no transactional rollback/reset API. Allocation/registration
failures are reported as `SUSFS SELinux policy records incomplete`; the policy
still publishes using the existing enforcement behavior. Logging this failure
is not a claim that hiding succeeded. Upstream type-table collision behavior
and policy reload generations remain limitations of the supplied SUSFS API.

## Validation

`scripts/tests/test_susfs_policy_records.py` compiles and runs the production
recorder with host policy fixtures and runs GNU make capability detection.
It covers new/old/disabled configurations, changed/removed/new rules, repeated
updates, audit/xperm exclusion, failure reporting, publication call sites and
the fixed version code. These tests do not compile a complete kernel or emulate
SELinux, RCU, Android app domains or SUSFS's hash-table implementation.

Device acceptance requires a newly built 6.12.23 kernel, explicit installation
and reboot authorization, then context/access comparisons, the real detector
app result and a kstat regression. UID 10000 with an inherited root SELinux
domain is a query-path probe, not a real app-domain test.
