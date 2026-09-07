# Fundamentals V4 Non-Operating Gap Phase 10C Deployment

## Outcome

Phase 10C persisted and activated the eight-flag Operating-Income V2 package
on 2026-09-07 at `20260907T205955Z`. The only production database written was
`/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`. Canonical,
provider, market and taxonomy databases were read-only and content-identical
through deployment and the mandatory second production command.
Existing files under `fundamental_reports/` remained byte-identical.

Production-gate commits were `ef2fd0e`, `eeb1f74` and `2c53d56`. The latter
two corrected smoke assertions before the successful activation; neither
changed model economics. The deployment-record commit is the commit containing
this document.

## Identities

| Identity | Active after deployment |
|---|---|
| Package | `0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30` |
| Diagnostic model | `0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904` |
| Snapshot economic | `f04e5dedf0cadecbd6039eabdcfc16d77a17b8cce729a63a810df7914d352a11` |
| Snapshot presentation | `b539ceb4e4745aa1233b27d9883b442d6106a2a1b4769a7c52bcf099cb55ad87` |
| Diagnostic layout | `d2040687f976f6e3807f5de6b2022a384bedeee02eb8d5294e98101b3fe06979` |
| Diagnostic source | `ae75df9522de07ea2113f505d32f06dc4b112057c1cd74ac103af3b89b6414df` |
| Diagnostic economic | `a3dde822dbfff98081d50fd4dd7534ee346b31cc74d75d3a40a1d91c45aeff5d` |
| Diagnostic physical | `7f4ea56523a403a2789a4f74977301a299bc4941228b205fe84c820adc36f8bf` |
| Package economic | `da43d4f0c466c06dbf7a7777ae8e92d2f69b5fb7d27d5280345cb76c92be69fb` |
| Package physical | `d0b39ac2b568623e59b50288ebe304fa169f99830d615715b69a68b492f4b362` |

Score `271585e4...`, Lifecycle `0502822c...`, Valuation `9675c2d9...`, Delta
`c65062c1...` and Relative Position `993a3cfb...` remained unchanged. The
archived rollback package is `a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d`
with seven-flag Diagnostic model `7f6291bf04e69cf22944ea3f81e07b284ccffd8edbd0edea4190ddc79050b031`.

## Preflight and backup

The dry-run artifact is
`temp/fundamentals_v4_non_operating_gap_phase10c/20260907T_phase10c_dry_run/`.
It confirmed the old active package, clean Git state, exact regular non-symlink
production paths, correct database types, no conflicting writer, `quick_check=ok`,
zero foreign-key violations and locked source/results. Production SHA-256 and
sizes matched the Phase 10B rehearsal. Available space was about 479 GB; the
conservative gate required 3,050,803,200 bytes before the first persistence.

The verified pre-write online backup is:

```text
/home/kalle/projects/rawcandle/backups/fundamentals_analysis.phase10c.20260907T204916Z.db
size: 1,043,939,328 bytes
SHA-256: b93112be06e2a415b8eaf27ad2b6e4092c31b88f04d24738e7011dccf0ec5e2a
quick_check: ok
foreign-key violations: 0
active package: a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d
old Diagnostic rows: 50,585 endpoints / 354,095 evaluations
```

The backup opens independently and has no WAL/SHM dependency. Two later online
backups retain the old active pointer plus the inactive candidate after the
smoke-controlled retries: `20260907T205510Z` and `20260907T205955Z`, each
1,146,810,368 bytes with SHA-256 `c2fb877d...`.

## Commands

All invocations used the five exact production database arguments and this
complete identity argument set:

```text
python3 -m rawcandle.fundamentals.operating_income_v2.phase10c \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --market-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db \
  --taxonomy-db /home/kalle/projects/rawcandle/data/analysis.db \
  --backup-dir /home/kalle/projects/rawcandle/backups \
  --package-fingerprint 0e269e52a63500342df8a08ee2f91552fdc8fb216fa68cfe469bafb6aa8e3c30 \
  --score-fingerprint 271585e4136f6733c047e89dac7646f2ff91f8c84b10f88c56356ad495970360 \
  --lifecycle-fingerprint 0502822c20501c1487d09a20a378e86c0908a0953dfcb13b384428822fc4e175 \
  --valuation-fingerprint 9675c2d947a86d2115f366424eab7454ec013cc100c7548af004c19c691c9aeb \
  --delta-fingerprint c65062c1ac66f1e98ab239404dba96c43060708a35a84bcfd2ed01c30d5e2f11 \
  --relative-fingerprint 993a3cfbbfd7d724852cf78466a91edf0a1adca8cd08c35e8bcc2891a5cbe30f \
  --diagnostic-fingerprint 0ac66c6749afc889cf553c47436757a54f644b6a81febd161cf947885e444904 \
  --snapshot-fingerprint f04e5dedf0cadecbd6039eabdcfc16d77a17b8cce729a63a810df7914d352a11 \
  --full-universe <mode-specific arguments>
```

Dry-run used output `20260907T_phase10c_dry_run`, expected active package
`a36d6903...`, and no apply arguments. The successful activation used output
`20260907T_phase10c_activation_final`, expected `a36d6903...`, and
`--apply --confirm-production`. The independent second command used output
`20260908T_phase10c_second_no_change`, expected `0e269e52...`, and the same
apply/confirmation arguments. Every exact argv is retained in its artifact
directory's `commands_run.json` where the command completed.

## Apply and reconciliation

The initial persistence inserted 50,585 candidate endpoints and 404,680
evaluations, 455,265 logical rows. A report-smoke string assertion and then an
incorrect UI method name stopped two attempts after activation; both times the
failure-safe restored the old active pointer and its original activation time.
The assertions were corrected and committed without economic changes.

The successful retry found the already reconciled candidate as `NO_CHANGE`,
then atomically activated the coherent full package. Pre-activation explicit
reader reconciliation and post-activation default reader reconciliation each
reported zero differences across all 404,680 evaluations. There are exactly
eight evaluations per endpoint, zero duplicates and zero orphans. The first
seven flags comprise 354,095 evaluations and match the corrected seven-flag V2
engine in decision, status, reason, applicability and numeric evidence.

Current-fresh Non-Operating Earnings Gap distribution:

| Measure | Count | Evaluable denominator (2,110) | Full fresh denominator (2,431) |
|---|---:|---:|---:|
| Active | 334 | 15.8294% | 13.7392% |
| Clear | 1,776 | 84.1706% | 73.0564% |
| Not ready | 182 | - | 7.4866% |
| Not applicable | 139 | - | 5.7188% |
| Eight-flag active union | 531 | 25.1659% | 21.8429% |

The new flag has 36,893 historical evaluable rows and 5,319 active rows. Its
current active rows split into 230 UPLIFT and 104 DRAG. Of the current active
set, 226 overlap the seven-flag union and 108 are incremental.

Reference results were NVDA USD 32.628B / 10.7694% UPLIFT, AMZN USD 84.515B /
10.8956% UPLIFT and GOOG USD 152.615B / 34.2288% UPLIFT. Temporary report
smokes also covered ABAT (DRAG), A (clear), ABOS (not ready) and AAT (not
applicable). Reports contain eight definitions and statuses, signed direction,
the inclusive 10% boundary, Reported Common Earnings terminology and no
internal database IDs.

Default active, explicit candidate and explicit archived readers passed. The
provider-disabled pipeline returned `NO_CHANGE` with zero logical changes. UI
multi-ticker partial-batch behavior, recent reports, secure download, traversal
rejection and symlink rejection passed. No production report was regenerated.

## Idempotency, rollback and storage

The independent second production command returned `NO_CHANGE` for both direct
apply and pipeline refresh. Analysis SHA-256, mtime, size, page count, freelist,
manifest and activation time all remained exactly unchanged:

```text
size: 1,146,810,368 bytes
pages: 279,983
freelist: 0
SHA-256: 8193f11efa8494c060e8fdb7772c3e89de1565baaedf1a25e8e48ad3f5417d87
activation: 20260907T205955Z
WAL/SHM: absent
```

Production grew by 102,871,040 bytes from the pre-write boundary. All
non-analysis database hashes were unchanged. Taxonomy SHM content remained
byte-identical; only its read-lock mtime changed. Final `quick_check` is `ok`
and foreign-key check is empty. V1 histories and unchanged V2 layers retained
their content fingerprints.

On `activation_rollback_rehearsal.db`, activation-only rollback selected
`a36d6903...`, returned 50,585 x 7 rows and rendered an old-package Snapshot.
Reactivation selected `0e269e52...`, returned 50,585 x 8 rows and rendered the
new Snapshot.

Activation-only rollback requires the maintenance lock, an immediate
transaction, `activate_package(connection, "a36d6903...", activated_at=...)`,
`assert_v2_active(connection)`, and commit. For a full restore, stop writers,
retain the failed database, verify the pre-write backup's full SHA-256, restore
through `sqlite3.Connection.backup()` into a new regular file, require
`quick_check=ok`, zero foreign-key violations and the old active manifest, then
atomically replace the production analysis database.

## Tests and remaining risks

Pre-write groups passed 118 and 331 tests. Post-fix focused groups passed 65
and 53 tests. The active Snapshot production-fixture group passed 31 tests.
The complete Fundamentals group passed 795 tests in 96.04 seconds. The complete
repository suite passed 2,666 tests in 376.16 seconds with eight existing
warnings and no failures. Repository pytest configuration uses
`--disable-warnings`, so the warning details are intentionally suppressed while
the count remains visible. `compileall`, final SQLite integrity checks and
`git diff --check` passed. No optional tool was installed and no test was
skipped or omitted.

Post-suite integrity review found that the pre-existing
`test_generate_random_findings_returns_tuple` test had written one random
downtrend finding into the production taxonomy database `data/analysis.db`.
The row was uniquely identified as `analysis_findings.id=4711711`, ticker HRB,
date 2018-12-24 and creation time `2026-09-07 21:28:55` UTC. A guarded
transaction removed exactly that row and restored the table's
`sqlite_sequence` from 4,711,711 to 4,711,710. Logical state, row count,
`MAX(id)`, `quick_check` and foreign-key checks reconcile after cleanup. The
test now writes findings to a pytest temporary database; its focused suite
passes. The complete 2,666-test repository suite was then rerun in 373.04
seconds; it passed with the same eight warnings, and SHA-256 comparison before
and after confirmed that none of the ten production `.db` files changed.

No pre-suite byte backup of the 10.4 GB taxonomy database existed because it
was contractually read-only in Phase 10C. SQLite's insert/delete transaction
changed database page bytes even after the exact logical cleanup, so the
taxonomy SHA-256 cannot be restored honestly from
`c95f9b163241c1e3998d6011b3375fe5df73fd1a83fca9d25aa94b5a2b9d2ed2`.
The cleaned file SHA-256 is
`44bfe4782a431a68f621af2e999fc8016e5c4766373c3722b2a04c8c6a83b8ac`.
Replacing it with an older backup would discard legitimate taxonomy data and
was therefore not done. This side effect happened after the successful
deployment and byte-identical second command; it did not affect package
activation or any Phase 10C calculation.

Remaining risks are current-revised rather than PIT history, current taxonomy,
the fixed 2026-09-06 source/as-of state until the next controlled refresh, and
the operational cost of full-history deterministic refreshes. No provider
update, canonical/TTM rebuild, economic model change or push occurred.
