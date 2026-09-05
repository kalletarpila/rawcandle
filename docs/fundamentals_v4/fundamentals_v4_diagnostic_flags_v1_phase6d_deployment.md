# Diagnostic Flags V1 Phase 6D Production Deployment

## Outcome

`CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V1` was deployed successfully on 2026-09-05.
The normalized revised-history package is active in
`/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`.

- maintenance window start: `2026-09-05T19:05:00Z`
- final verification completed: `2026-09-05T19:43:50Z`
- provider update: not run
- push: not performed
- rollback: not required

The production order is now:

```text
provider/canonical -> TTM -> Fundamental Score -> Lifecycle
-> Absolute Valuation at Filing -> Diagnostic Flags
-> Fundamental Delta -> Relative Position current snapshot
```

Diagnostic Flags has no dependency on Delta or Relative Position. Each stage has
its own transaction. A Diagnostic Flags failure preserves the previously committed
package, downstream stages are still attempted, and the combined post-Valuation
operation reports failure.

## Git And Tests

- branch: `chore/ignore-backups`
- Phase 6C base: `d454b98705d91d137ef1fd1d8afaea96c09f31a0`
- production gate and pipeline hook: `1193e7e98ab25789b6136f7a8f47bb6eb10358ca`
- deterministic smoke-date correction: `a435ffaf008f050247c07ec5332b7b6c388b9dc6`
- physical-content ordering correction: `11d67d53fae91f1502e6937a7ceebec13bfbfdc4`
- complete Fundamentals V4 suite: 599 passed in 57.34 seconds
- focused final production/Delta/Relative tests: 34 passed in 1.39 seconds
- `compileall`: passed
- `git diff --check`: passed
- full repository suite: not run because changes remained within Fundamentals V4

The primary code/integration commit was created before any production write. The
two corrections were also committed before the first Diagnostic Flags package
write. The first pins Relative Position smoke to its active snapshot date. The
second aligns the new pre-apply physical-content gate with the already locked
persisted row order. Neither changes a flag definition or economic output.

## Locked Contract

| Contract | Value |
|---|---|
| Model | `CURRENTLY_REVISED_DIAGNOSTIC_FLAGS_V1` |
| Model fingerprint | `1d985892734c1401de55d91e06bbb1f295fe247e96bb3acbffcd6272027f26ad` |
| Persistence | `DIAGNOSTIC_FLAGS_REVISED_HISTORY_V1` |
| Layout fingerprint | `f48e6e7b40071fe536b7846cac17c59d2fed7c0b118c4771813348877d065aba` |
| Source fingerprint | `6c0ef9696386e8c9e47856d5e61ab4456dea4f6b05a6982f7a87c76e87c9dfe3` |
| Economic result | `e712798c9c4d6dc43d26d1a638e434ba9e97e9d8dcaa43c5c51764c200bc4f51` |
| Package fingerprint | `9cb22911df493b71a54985c81eae3de9e5d5ad5db259cbe9fc70b57cb6b49b4d` |
| Physical content | `e21536fd5b693d20773808ce89bd79f0ca23783067a100e08893861cf0006461` |

The schema contains exactly the seven locked flags. It contains no yield-divergence
flag, severity, confidence, aggregate score, causal classification, or JSON
evidence.

## Production Targets

The exact regular, non-symlink files were validated before every production
operation:

| Role | Path |
|---|---|
| Provider, writable | `/home/kalle/projects/rawcandle/data/fundamentals_provider.db` |
| Canonical, writable | `/home/kalle/projects/rawcandle/data/fundamentals_v4.db` |
| Analysis, writable | `/home/kalle/projects/rawcandle/data/fundamentals_analysis.db` |
| Market, read-only | `/home/kalle/projects/rawcandle/data/osakedata.db` |
| Taxonomy, read-only | `/home/kalle/projects/rawcandle/data/analysis.db` |

The gate required all five exact paths, full-history mode, the locked model,
persistence and layout identities, and explicit `--apply --confirm-production`.
Path aliases, symlinks, temporary destinations, role swaps, partial history, and
wrong fingerprints are rejected.

## Backups

Three online SQLite backups were created and independently opened before mutation.
Each returned `quick_check=ok`, zero foreign-key violations, and matching key row
counts.

Backup directory:

`/home/kalle/projects/rawcandle/backups/fundamentals_v4_diagnostic_flags_phase6d_20260905T190500Z`

| Database | Backup file | Bytes | SHA-256 |
|---|---|---:|---|
| Provider | `fundamentals_provider_before_phase6d.db` | 546,754,560 | `660115d7c69129efe9c12d9708ca845b143de28066df61307710049533f8245e` |
| Canonical | `fundamentals_v4_before_phase6d.db` | 288,563,200 | `58ed8e2b89d034f05e5fa5bb7a8b604e13777c6780ad5b4b699321d7a8709d2a` |
| Analysis | `fundamentals_analysis_before_phase6d.db` | 390,258,688 | `08193a30411472ac0905a8833d4b845ef4288a3177dc0beca0030257245f8caa` |

Restore commands and validation steps are recorded in
`temp/fundamentals_v4_diagnostic_flags_phase6d/20260905T190500Z/rollback_commands.txt`.
All three backups are retained.

## Commands

All production CLI operations used this exact common contract:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_diagnostic_flags_production \
  --analysis-db /home/kalle/projects/rawcandle/data/fundamentals_analysis.db \
  --canonical-db /home/kalle/projects/rawcandle/data/fundamentals_v4.db \
  --provider-db /home/kalle/projects/rawcandle/data/fundamentals_provider.db \
  --market-db /home/kalle/projects/rawcandle/data/osakedata.db \
  --taxonomy-db /home/kalle/projects/rawcandle/data/analysis.db \
  --model-fingerprint 1d985892734c1401de55d91e06bbb1f295fe247e96bb3acbffcd6272027f26ad \
  --persistence-version DIAGNOSTIC_FLAGS_REVISED_HISTORY_V1 \
  --layout-fingerprint f48e6e7b40071fe536b7846cac17c59d2fed7c0b118c4771813348877d065aba \
  --expected-source-fingerprint 6c0ef9696386e8c9e47856d5e61ab4456dea4f6b05a6982f7a87c76e87c9dfe3 \
  --expected-economic-result-fingerprint e712798c9c4d6dc43d26d1a638e434ba9e97e9d8dcaa43c5c51764c200bc4f51 \
  --expected-package-fingerprint 9cb22911df493b71a54985c81eae3de9e5d5ad5db259cbe9fc70b57cb6b49b4d \
  --expected-content-fingerprint e21536fd5b693d20773808ce89bd79f0ca23783067a100e08893861cf0006461 \
  --full-universe --output-dir OUTPUT_DIR OPERATION_FLAGS
```

Operations were executed in this order:

1. Provider compatibility twice: `--provider-compatibility --apply --confirm-production`.
2. Working Capital twice: `--working-capital --apply --confirm-production`.
3. Diagnostic schema twice: `--diagnostic-schema --apply --confirm-production`.
4. Dry-run: no operation or apply flags.
5. First package: `--apply --confirm-production`.
6. Deep replay: `--deep-replay` without apply.
7. Required second package: `--apply --confirm-production`.
8. Pipeline smoke: `--pipeline-smoke --as-of-date 2026-09-01 --apply --confirm-production`.

Structured outputs are under
`temp/fundamentals_v4_diagnostic_flags_phase6d/20260905T190500Z/`.

## Provider And Canonical

Provider compatibility added only `netinccmn` and populated 101,562 existing
provider rows. It did not rewrite raw payload JSON and did not download data. Its
second application reported zero schema and row changes.

The Working Capital operation added five provider and five canonical columns:

- accounts receivable;
- inventory;
- accounts payable;
- deferred revenue;
- total assets.

First application metrics:

| Metric | Count |
|---|---:|
| Provider rows changed | 101,866 |
| Canonical values changed | 252,915 |
| Provenance rows added | 252,915 |
| Invalid values | 0 |
| Provenance rows removed | 0 |

The second operation reported zero columns, provider rows, canonical values,
provenance inserts, updates, or deletes.

Each field has 50,583 observed canonical values and 50,583 provenance rows; two
quarters are missing each field. There are zero observed values without provenance
and zero direct provider/canonical mismatches. All five fields are simultaneously
available for 50,583 endpoints. There are 45,131 consecutive current/prior chains.
For eligible balance sheets, `assetsc + assetsnc` versus total assets had zero
observations outside the accepted tolerance. Explicit zeros were retained as
observed values.

The compatibility operation also created the empty, already authorized Working
Capital provenance table and its index while advancing the canonical schema
version. It added no economic row. This was an additive Stage B schema effect, not
an economic output change.

## Existing Economic Layers

Fifteen protected table projections were compared directly with the verified
pre-write backups after upstream migration and again after pipeline smoke. All row
counts and logical hashes matched. This covers Score and its seven components,
Lifecycle, Absolute Valuation, Delta totals/components, active Relative Position
snapshot/results/coverage, canonical quarter/TTM values, and pre-existing provider
observation fields.

Relative Position smoke appended one bounded refresh-audit row, from 4 to 5. It did
not alter its active snapshot or economic result and is intentionally excluded from
the economic-layer comparison.

## Diagnostic Schema And Apply

The additive schema created eight normalized tables/codebooks and three measured
indexes. The identical migration created zero objects. No existing table was
rebuilt, no trigger or view was added, and no `VACUUM` was run.

The first full-history apply produced:

| Metric | Value |
|---|---:|
| Endpoints inserted | 50,585 |
| Evaluations inserted | 354,095 |
| Evaluations per endpoint | 7 |
| Inserts outside target model | 0 |
| Updates/deletes | 0 |

The package was activated only after its internal checks passed. The required
second apply returned `NO_CHANGE`: 50,585 endpoints and 354,095 evaluations were
unchanged, with zero inserts, updates, deletes, or active-package changes.

## Deep Replay And Readers

The authoritative replay rebuilt all source inputs and compared 50,585 endpoints
and 354,095 evaluations. Mismatch count was zero. This covers flag decisions,
statuses, reason codes, fiscal identities, comparison identities, NULL versus zero,
numeric evidence, and row fingerprints. Economic and physical fingerprints matched
the locked values. SQLite quick check was `ok` and foreign-key violations were zero.

Reader validation passed for package metadata, current company, history, batch,
flagged universe, fiscal cross-section, deterministic flag order, reopen behavior,
and wrong-fingerprint rejection.

## Current Distribution

The current-fresh population at `2026-09-02`, using the locked 180-day freshness
rule, contains 2,441 companies. The common abrupt-evaluated cohort contains 2,097.

| Flag | Flagged | Clear | Not ready | Not applicable |
|---|---:|---:|---:|---:|
| Abrupt fundamental shift | 282 | 1,815 | 20 | 324 |
| Earnings/cash divergence | 239 | 1,858 | 20 | 324 |
| Capex intensity shift | 74 | 2,023 | 20 | 324 |
| Net debt shift | 169 | 1,928 | 20 | 324 |
| Valuation yield outlier | 36 | 2,209 | 57 | 139 |
| Recent margin deceleration | 22 | 2,040 | 240 | 139 |
| Working Capital shift | 51 | 2,245 | 6 | 139 |

Common-cohort flag union:

| Flag count | Companies | Percent |
|---|---:|---:|
| 0 | 1,664 | 79.3515% |
| 1 | 174 | 8.2976% |
| 2 | 124 | 5.9132% |
| 3 or more | 135 | 6.4378% |
| At least one | 433 | 20.6485% |

The complete pairwise overlap matrix is stored in `flag_overlap_matrix.csv` in the
deployment artifact directory.

## CRMD And APD

| Ticker | Quarter | Working Capital metric | Threshold | Result |
|---|---|---:|---:|---|
| CRMD | FY2026 Q2 | 1.970007% | 10% | `EVALUATED_CLEAR` |
| APD | FY2026 Q3 | 1.811907% | 10% | `EVALUATED_CLEAR` |

Both production reader results matched Phase 6C exactly.

## Pipeline Smoke

The no-provider smoke used the active Relative Position snapshot date
`2026-09-01` and returned:

```text
Diagnostic Flags: NO_CHANGE, 50,585 / 354,095 unchanged
Fundamental Delta: NO_CHANGE, 50,585 / 354,095 unchanged
Relative Position: NO_CHANGE, 0 result/coverage/snapshot writes
```

The Relative Position active snapshot remained
`42efd2f3d42e019a21dee2fb03acf9b1cc698502b189e930ec83e24ac135c1ff`.
One expected audit row was appended. No provider update or deep replay was triggered
by the smoke.

## Final Inventory

| Database | Before bytes | Final bytes | Final pages | Final SHA-256 |
|---|---:|---:|---:|---|
| Provider | 546,754,560 | 551,792,640 | 134,715 | `1905d09cf93901622ae178e7b472e571bc872ba2b243ff3b02a5957f9b6e2c14` |
| Canonical | 288,563,200 | 372,228,096 | 90,876 | `f553639e7f25ce75fed51af0c2127121a96573cd88728c2eafa84b9dfdc087da` |
| Analysis | 390,258,688 | 476,631,040 | 116,365 | `8d19e39465be56779fd31a6202c871bfb426499f8853bbcadef05fbca8eff8b6` |
| Market | 1,965,867,008 | 1,965,867,008 | 479,948 | `42b661d17f953e9bc592701e9e98df9876e44ed0ce40d0f54d2c8ee0e6126344` |
| Taxonomy | 10,406,510,592 | 10,406,510,592 | 2,540,652 | `538cc96d1b55ceb1d7283f426c6cb1ab3bfd1f81206ccbe4bcd9b7dbd3b46ae2` |

All databases use 4,096-byte pages, had zero foreign-key violations, and returned
`quick_check=ok`. Provider, canonical, analysis, and market had no final WAL/SHM.
The taxonomy main file retained identical size, mtime, and SHA-256. Its pre-existing
WAL/SHM remained in place at 0 and 32,768 bytes; read-only SQLite access advanced
shared-memory metadata timestamps but did not alter the main database or sidecar
sizes.

## Dry-Run Incident

The first pre-apply dry-run correctly stopped before any Diagnostic result write.
Its source, economic result, and package fingerprints matched, but the new
pre-apply helper ordered normalized evaluation hashes by hashed endpoint ID rather
than the locked persisted company/fiscal/flag order. Commit `11d67d5` corrected the
gate and added a multi-company regression test. The repeated dry-run then matched
all four locked fingerprints exactly. This incident did not change production
economic data or the locked package.

## Rollback And Residual Risks

No acceptance criterion required rollback. The verified backups and explicit
restore commands remain available.

Known operational facts:

- history is currently revised, not PIT;
- sector and industry classification are current-state, not PIT-versioned;
- a full Diagnostic package calculation measured approximately 45-46 seconds;
- routine Score runs use the execution date for new Relative Position snapshots,
  while deployment smoke pins the existing snapshot date for deterministic no-op
  verification;
- Relative Position intentionally appends one bounded audit row per refresh check.
