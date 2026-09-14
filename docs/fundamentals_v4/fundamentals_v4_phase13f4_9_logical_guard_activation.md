# Phase 13F.4.9 Logical Content Guard And Production Activation

Status: `OUTCOME C - MATERIAL DEPLOYMENT FAILURE; COMPLETE BACKUP SET RESTORED`.

Phase 13F.4.9 first added a protected logical-content guard to the production inventory
comparator, then made one authorized production write attempt on 2026-09-14. The write attempt
crossed the production boundary, activated the accepted structural-regime package and Relative
Valuation snapshot in the first pass, then failed the independent second-pass inventory gate because
the new guard detected real protected table-content changes. The runner restored the complete
writable database set from fresh Phase 13F.4.9 backups. No second production write attempt was made.

## Preparatory Commit

Commit `44cc70d` added deterministic table-content fingerprints to `database_inventory()` and made
`compare_production_inventory()` require matching schema, row counts, logical table fingerprints,
`quick_check` and foreign-key counts before raw SQLite file SHA, file size, page count, freelist
count or `mtime_ns` are treated as nonblocking physical drift.

The logical fingerprint covers every non-`sqlite_` user table in each writable database inventory.
Values are serialized deterministically, with explicit BLOB hex handling, binary64 float hex
handling and stable ordering by primary key when present, otherwise by all table columns. The only
excluded table class is SQLite internal metadata.

## Logical Guard Evidence

Machine-readable mutation evidence:

`temp/fundamentals_v4_phase13f4_9_structural_production/20260914T_PHASE13F4_9_PRODUCTION_ACTIVATION/logical_content_guard_evidence.json`

The evidence contains ten cases and all returned the expected result:

- Physical SQLite drift only: accepted as logically unchanged.
- Same-row-count numeric mutation: rejected for provider, canonical and analysis roles.
- Same-row-count status/reason mutation: rejected.
- Structural-regime value mutation: rejected.
- Row addition and row removal: rejected.
- Schema change: rejected.
- Simulated failed `quick_check` and foreign-key integrity: rejected.

The comparator reports the exact database and protected layer, including changed logical table names.

## Phase 13F.4.8 Re-Evaluation

Machine-readable re-evaluation summary:

`temp/fundamentals_v4_phase13f4_9_structural_production/20260914T_PHASE13F4_9_PRODUCTION_ACTIVATION/phase13f4_8_inventory_re_evaluation.json`

Phase 13F.4.8 did not retain the full second-pass before/after inventory objects because the legacy
runner failed before serializing them into the result. The retained payload still showed all
economic pipeline gates as no-change:

- provider replay changes: `0`
- package first pass in the second run: `NO_CHANGE`
- package inner second apply: `NO_CHANGE`
- Relative Position: `NO_CHANGE`
- Relative Valuation first pass in the second run: `NO_CHANGE`
- Relative Valuation second apply: `NO_CHANGE`

The only explicitly reported physical observation was content-identical taxonomy SHM timestamp
drift. Fresh Phase 13F.4.9 inventories now include table-content fingerprints for the writable set.

## Production Attempt

Artifact root:

`temp/fundamentals_v4_phase13f4_9_structural_production/20260914T_PHASE13F4_9_PRODUCTION_ACTIVATION`

Backup root:

`backups/fundamentals_v4_phase13f4_9_structural_production/20260914T_PHASE13F4_9_PRODUCTION_ACTIVATION`

Preflight:

- Branch: `chore/ignore-backups`
- Head: `44cc70d`
- Worktree: clean
- Write set: provider, canonical, analysis
- Read-only roles: market, taxonomy
- Conflicting writer processes: none
- Lock: available
- Free disk before execution: about 707 GB
- Writable database integrity: `quick_check=ok`, foreign-key errors `0`

First production pass:

- Package first apply: `APPLIED`
- Package logical writes: `2396550`
- Package inner second apply: `NO_CHANGE`
- Relative Valuation first apply: `ACTIVATED`
- Relative Valuation second apply: `NO_CHANGE`
- Snapshot smoke reports were generated for VMRK, IA, VAI, NXH, NMAD, AREB, NVDA and SNDK.

Independent second production pass:

- Provider replay changes: `0`
- Package outcome: `NO_CHANGE`
- Package inner second apply: `NO_CHANGE`
- Relative Position outcome: `NO_CHANGE`
- Relative Valuation outcome: `NO_CHANGE`
- Relative Valuation second apply: `NO_CHANGE`

Blocking failure:

`PHASE13F4_2_SECOND_RUN_NOT_NO_CHANGE`

The new logical guard reported protected table changes:

- Analysis row count changed: `relative_position_refresh_audit`
- Analysis logical fingerprint changed: `fundamentals_result_dependency`, `relative_position_refresh_audit`
- Canonical row count changed: `company_cik`, `provider_company_identity`, `provider_security_identity`
- Canonical logical fingerprint changed: `company_cik`, `fundamentals_economic_structural_event`, `provider_company_identity`, `provider_security_identity`

The taxonomy SHM timestamp drift was still reported as nonblocking content-identical sidecar
metadata. The blocking differences were protected logical database-content changes, so rollback was
required.

## Field-Level Diagnosis

The failure is not a stale test expectation and not harmless SQLite physical drift. It is a real
reader/orchestration idempotency defect exposed by the new comparator.

The likely write sources are:

- `phase13f3_2_successor_recovery._apply_provider_identity_links()`, which writes
  `provider_security_identity`, `provider_company_identity` and `company_cik` with `INSERT OR IGNORE`
  outside the second-run no-change summary;
- `structural_break.apply_contract()`, which owns `fundamentals_economic_structural_event`;
- `phase13b_foundation.attach_dependencies()`, which owns `fundamentals_result_dependency`;
- `relative_position.persistence._insert_audit()`, which inserts into
  `relative_position_refresh_audit` even when the persisted Relative Position result is unchanged.

`relative_position_refresh_audit` may be an audit-only candidate for future exclusion, but the other
listed tables are protected identity, structural or dependency state and cannot be ignored under the
Phase 13F.4.9 contract.

## Rollback Verification

The runner restored provider, canonical and analysis from the fresh Phase 13F.4.9 backup set with
`restore_error=None`.

Restored writable database hashes:

- Provider: `7957c44632ff98eda87b12014152eb26b9fd3d445c5d8d2510b7b0f9eca03e11`
- Canonical: `554aaa3c8fc359b08ed0c9171f62e08e2cd59c3be2bfed1fa6ff09713275e736`
- Analysis: `a46ab948a9b6b3d12078b7f09158ccde603d28ab649e6bd9015273aa3e54e8d2`

Post-restore active identities:

- Active package persistence fingerprint:
  `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Active Relative Valuation snapshot:
  `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`

Post-restore integrity:

- Provider quick_check: `ok`; foreign-key errors: `0`
- Canonical quick_check: `ok`; foreign-key errors: `0`
- Analysis quick_check: `ok`; foreign-key errors: `0`
- Taxonomy quick_check: `ok`; foreign-key errors: `0`

## Tests

Before the production write attempt:

- Compile checks: passed with `python3 -m compileall`.
- Logical guard, comparator, acceptance and isolation tests: `54 passed in 16.33s`.
- Expanded focused suite: `125 passed in 23.28s`.
- `git diff --check`: passed.

The full active repository suite was not run because production activation did not succeed; the
full-suite requirement remains a post-success gate.

## Cleanup

Removed only Phase 13F.4.9-owned restore rehearsal database copies:

- `restore_rehearsal/provider.restored.db`
- `restore_rehearsal/canonical.restored.db`
- `restore_rehearsal/analysis.restored.db`

Retained the compact temp evidence and the fresh verified backup set. Final Phase 13F.4.9 temp root
size was about 1.1 MB. Backup root size was about 3.0 GB. Final free space was about 704 GB.

## Remaining Risk

The structural-regime package is not active in production after this phase. Production remains on
the restored baseline package and RV snapshot. A later production attempt needs a separate explicit
authorization and should first make the second-pass identity, structural dependency and audit writes
fully idempotent or explicitly classify truly audit-only tables outside economic identity.
