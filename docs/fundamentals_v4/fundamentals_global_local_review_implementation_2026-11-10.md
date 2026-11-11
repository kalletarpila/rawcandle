# Fundamentals global/local review implementation — 2026-11-10

Historical report of the November 10 STOP. For the subsequent recovery fix, qualification and November 11 rollout STOP, see [the recovery and rollout report](fundamentals_generation_recovery_and_review_rollout_2026-11-11.md). Runtime counts, hashes and Git status below describe the original investigation; raw runtime artifacts remain outside this documentation commit.

## STOP: immutable-generation recovery qualification failed

**No live Full Workflow was executed. No financial publication occurred. The implementation is preserved for review, but is not deployed or committed. Task-owned source/test edits were removed from the scheduler's working checkout after a real disposable recovery failure was confirmed.**

The governing audit is `a162640d87b0ac7841eb68ed8689ef96b01cd7ec`, documented in `fundamentals_review_semantics_rebase_audit_2026-11-10.md`. The new combined native acceptance test disproved an assumption not covered by its 42-test selection: the actual Refresh production caller does not select the existing byte-exact immutable-generation backup mode. The generation recovery verifier expects physical hashes matching the OLD immutable files, while the caller creates SQLite online backups with different physical hashes.

This invokes the user's explicit STOP conditions: “any disposable-copy scenario fails” and “post-boundary failure cannot restore OLD generation”. It is a **TRANSACTION_OR_RECOVERY_SAFETY** defect affecting publication independently of ticker locality. The safe-peer live gate therefore cannot pass. The existing terminal live journal remains healthy; `RECOVERY_FAILED` below refers exclusively to disposable test journals.

The prior audit's architectural PASS for rollback/recovery is insufficient to authorize rollout in light of this combined native-path failure. No ticker was made an exception to bypass it. The native journal/recovery protocol was not changed to conceal the failure.

## Fresh implementation baseline

The source checkout initially matched audit commit `a162640d87b0ac7841eb68ed8689ef96b01cd7ec`. Relevant source/tests were clean. Existing runtime journal modifications, untracked generations, price repair/research files and other unrelated work were preserved.

Fresh inspection of completed November run metadata, current queue, active roles and journal found no later authoritative financial run or intervening financial publication:

| Fact | Fresh baseline |
| --- | --- |
| Full Workflow parent | `20261110T071841Z_refresh_fundamentals_d00eb7239fed_full_workflow_ba5bad1d` |
| Authoritative Preview | `20261110T071841Z_refresh_fundamentals_dbbcb6f12f21` |
| Parent result | STOPPED at Preview, completed `2026-11-10T07:59:27Z` |
| Preview computation completed | `2026-11-10T07:54:32Z` |
| Safe effective changes | 1,073 |
| Already-local holds | 354 |
| Existing policy globals | 16 |
| Test / Production entered by baseline run | NO / NO |
| Active generation | `current_rebuild_2a684ef130c6a540de4adc560ab171ad` |
| Published provider watermark | `2026-10-28` |
| Journal / postflight / recovery | COMPLETED / PASSED / NOT_REQUIRED |
| Queue current / resolved / audit rows | 354 / 5 / 1,210 |
| P/B queue | 10 PUBLISHED, 3 SUPERSEDED; no unresolved cases |
| Accounting-boundary queue | WFRD APPROVED |
| Preserved-history queue N / latest intersection M | 342 / 342 |
| Pure / mixed preserved queue cases | 319 / 23 |
| Current accepted frozen conflict identities | 1,858 |
| Scheduler settings | FULL_WORKFLOW, Fundamentals enabled, P/B auto-continuation enabled; unchanged |

Current blockers and exact issue codes remain those in the governing audit:

| Ticker | Primary issue and additional report codes |
| --- | --- |
| AG | SOURCE_PAYLOAD_KEY_REGRESSION; RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON |
| ARM | SOURCE_PAYLOAD_KEY_REGRESSION |
| BBAI | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION |
| CAMT | SOURCE_PAYLOAD_KEY_REGRESSION; RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON |
| CHRD | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION |
| CIFR | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION |
| INDV | COMPLETE_HISTORY_NOT_TRUSTED |
| KLXE | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION |
| MIR | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; BOUNDARY_CHRONOLOGY_INCONSISTENT; INTERIOR_SOURCE_KEY_REMOVAL; SAME_FISCAL_SOURCE_KEY_REPLACEMENT |
| NXH | SOURCE_PAYLOAD_KEY_REGRESSION; RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON |
| OSK | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; BOUNDARY_FISCAL_WINDOW_TOO_SHORT; OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW |
| PI | AMBIGUOUS_SOURCE_REMOVAL; COMPANION_DIMENSION_CONTRADICTION; OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW |
| RCEL | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION |
| SNDK | SOURCE_PAYLOAD_KEY_REGRESSION |
| SUPN | COMPLETE_HISTORY_NOT_TRUSTED |
| VTOL | REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION; OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW |

No ticker-specific new shared semantic defect was found during initial rebase. The recovery defect was discovered later in the required combined acceptance, before any live operation.

## Preserved implementation and source containment

Review artifacts are in:

`temp/fundamentals_global_local_review_20261110/`

- `implementation.patch`: all 13 tracked-file edits and four new source/test files against the audit commit. `git apply --check` passed against the restored checkout.
- `source/`: exact implementation/test snapshots for inspection without applying the patch.
- `source_inventory.json`: base commit, per-file hashes and patch hash.
- `evidence/baseline-files.json`, `baseline-manifest.json`, `final_live_files.json`: live baseline and final hash evidence.
- `evidence/failed_crash_recovery_0.json`, `failed_crash_recovery_1.json`: exact disposable journals from the before/after activation recovery failures.

Patch SHA-256: `e6d1f1c280e966f836d6febc162195d2d0c35ccbd83385a2b9f6134a309fc75d`.

These are review artifacts, not a qualified deployment. No patch was left active for the scheduler to import. No unrelated file was restored or removed. The existing price-pipeline and runtime-generation artifacts were not staged or committed. This report is the only new task document in the main worktree.

## Implemented design in the preserved patch

### Locality is independent of approval

`review_locality.py` adds `FUNDAMENTALS_TICKER_QUARANTINE_V1`. It recognizes finite supported evidence shapes and creates a proof only after read-only validation of the exact accepted provider/canonical baseline. Unknown reasons/errors, cross-ticker source keys, ambiguous source history, missing accepted provenance, and unbound identity remain global. No ticker names are used as implementation exceptions or allowlists.

The proof binds normalized ticker, company/security/provider identity, full relevant incoming fiscal/removal/payload/completeness evidence, accepted economic/provider fingerprints, and the operation's identity partition fingerprint. Empty/limited responses additionally bind successful full-history request evidence to the requested ticker/dimension and returned count; they do not invent missing observations or infer deletion/delisting/zero values. Optional-key regression support excludes the shared required SF1 fields.

Legacy accepted provider headers may legitimately have NULL `provider_security_id`. Their non-null company/security IDs are verified against the exact single canonical SHARADAR provider mapping. The old headers remain byte/semantically retained; no ID is filled into accepted financial evidence. All 16 audited cases could be positively localized in read-only development replay once this legacy mapping was handled correctly. That is development evidence, not an executed fresh live Preview or authority to reuse the old blocked Preview.

Existing fiscal, true-removal, retained-history, historical repair, WFRD and P/B approval predicates/authorities were not broadened. A new quarantine proof alone does not satisfy an old approval-compatible shape. Unsupported repairs remain ineligible.

### Partition, persistence, and native gates

`refresh_review_queue.py` consumes the positive proof after its existing supported-local shapes. It checks company/security/provider identity collisions across the evaluated operation and promotes collisions or proof/partition drift globally. It persists new quarantine evidence in the existing queue context/integrity binding and appends `LOCAL_QUARANTINE_OBSERVED` when evidence changes. Payload comparison keys and failed-dimension evidence are retained. There is no parallel queue or schema migration.

`refresh_fundamentals.py` binds locality before Preview partitioning. `refresh_copy_runtime.py` independently rebuilds the same proof at fresh source revalidation. Bound Test and Production authorization continue to recompute/check the partition, so changing only a parent outcome cannot authorize publication.

`refresh_production.py` verifies actual provider replacement tickers against the authorized safe set and supplies existing journal `scope_evidence`: safe replacement tickers, held tickers, true globals, partition fingerprint, bound Preview and Test IDs. Existing shared schema/discovery, identity mapping, input-drift, source-revalidation, generation/postflight and recovery gates remain in place.

### Held economic authority

The patch fingerprints complete held provider headers/payloads/capture provenance plus canonical economic quarters, all financial fields including parent equity, natural fiscal identities, source/publication dates, identity mappings, and field/parent-equity provenance semantics. Regenerated canonical physical IDs and acceptance/write timestamps are excluded from economic comparisons. Native accepted source/provenance/equity contradictions prevent proof creation.

Test and Production compare before/after held authority. Production repeats the comparison after candidate enrichment and before the final publication gate. Actual provider replacement-set mismatch fails before publication. These checks passed in the completed single-shape disposable acceptance cases; live preservation was not attempted.

### Workflow reporting

The patch separates safe changes, holds, globals and actual published peers; records held incoming publication count as zero on successful safe publication; and avoids displaying the local-hold “NO” field as an authorization fact when a separate global stop exists. New compact financial execution metadata resolves completed parent workflows to their native Preview child for UI projection. Existing authorization and transaction boundaries are retained.

### Preserved-history presentation and CSV

`preserved_history_presentation.py` defines a pure-row predicate using persisted primary review type, current HELD evidence, unresolved status, benign reason codes, absence of independent/global/deep/capture/explicit work, and existing approval flags. It does not hide rows merely by label or `needs_action=False`. Mixed reviews retain their primary current issue and permitted next action; historical preservation becomes secondary explanation.

The normal UI hides only pure cases. An explicit Deep Review evidence section lazily loads hidden rows with existing Details/technical evidence and Wait/Retry access. It does not add approval capabilities or route OPEN cases through terminal-history age filtering.

Shared aggregation defines:

- **N:** normalized unique current unresolved queue tickers with HELD frozen conflicts, excluding pending approvals and resolved/terminal rows.
- **M:** N intersected with preserved encounters in the latest completed authoritative financial Preview; missing/corrupt latest evidence yields unavailable, not zero or an older substitution.

Completed execution metadata resolves parent/child identity and ignores running, copy-only, ownership and unrelated runs. New Preview artifacts contain a compact encounter list; legacy ticker evidence is streamed with bounded memory. No Preview is rerun to compute UI counts.

The dedicated fixed read-only route `/fundamentals/admin/preserved-history.csv` generates UTF-8 CSV on demand with the nine requested columns, sorted normalized ticker rows, deterministic accepted-binding counts, mixed action flags, CSV quoting and formula neutralization. The Markdown report resolver is unchanged. No new persistent list database or saved CSV is introduced.

A read-only projection against the current live evidence, without publication or queue mutation, produced **N=342, M=342, pure=319, mixed=23, CSV rows=342**. Those are baseline observations, not hardcoded targets. The live UI/CSV route was not deployed after the acceptance STOP.

## Test and disposable acceptance results

Only directly relevant tests were selected. No full suite was run.

Completed development batches:

| Batch | Result | Scope/limit |
| --- | --- | --- |
| Existing native local fiscal/window publication smoke | 2 passed in 23.21 s | Existing supported-local behavior with strengthened economic comparison |
| New single-shape and locality-negative acceptance rerun | 13 passed in 73.82 s | Nine shape scenarios plus incomplete-proof and identity-collision checks; actual disposable generation publication and below-overlap reevaluation |
| New UI/CSV plus action/operational presentation batch | 97 passed, one stale positional UI assertion failed | Corrected to reference the exposed evidence control instead of an obsolete child index |
| Subsequent bounded UI/CSV/approval rerun | 16 passed in 8.37 s | Pure/mixed visibility, explicit evidence access, N/M, CSV, parent resolution, existing fiscal/removal confirmation controls |
| Combined safety/regression selection | 421 selected; interrupted after confirmed recovery STOP | Included new locality, queue, native parity, generations, historical freeze, WFRD, payload completeness and P/B modules; no final all-pass result |
| Focused native generation crash reproduction | FAILED in 17.17 s | `AFTER_NEW_GENERATION_READY` cannot complete OLD verification |

The preserved patch remains unqualified. Earlier passing batches are not represented as a complete validation of every final source edit.

Disposable scenario status:

| Required scenario | Status |
| --- | --- |
| A: fiscal local hold plus safe peers | Passed in completed single-shape acceptance, including MRQ disagreement and ARQ relabel |
| B: multiple local shapes in one generation | Exercised in the larger selection; not accepted as part of an all-pass qualification |
| C: real shared/global defect | Schema/discovery/cross-ticker rejection exercised; zero live progression |
| D: ordinary post-boundary rollback | Original-generation pointer/hash checks alone are insufficient; must also require terminal successful recovery journal state; qualification incomplete |
| E: crash recovery at generation preparation/activation | **FAILED** before and after activation; STOP |
| F: UI/CSV/read-only behavior | Bounded UI/endpoint-function tests passed; no live UI deployment/HTTP acceptance |

The crash tests run against isolated provider, canonical, analysis, market, taxonomy, manifest, journal and queue paths. They do not invoke recovery against the live journal. Other disposable success cases confirmed safe replacement set `AAA, BBB`, held incoming publication zero, economic held-state equality and generation/postflight success. Those synthetic names are test fixtures only.

## Exact recovery defect

The defect predates this implementation patch. `git show a162640d:rawcandle/fundamentals/admin/refresh_production.py` shows:

```python
def _verified_backups(..., immutable_generation: bool = False):
    ...
    if immutable_generation:
        shutil.copyfile(source, backup)
    else:
        online_backup(source, backup)
    ...

# Native Refresh production caller:
backups = _verified_backups(source_paths, backup_dir)
```

The caller is at line 1132 in the governing source. It leaves `immutable_generation=False` even when publishing through a generation pointer. SQLite's online backup produces a valid database, but its physical file hash differs from the OLD immutable role file. `publication_journal.py::restore_old_generation()` reactivates the OLD manifest and compares each original role with the verified **backup** hash. The mismatch raises `RECOVERY_OLD_GENERATION_SET_MISMATCH:provider`, then `CRITICAL_RECOVERY_FAILED`.

Before-activation reproduction (`test_new_locality_crash_requir0`):

| Role | OLD manifest/file SHA-256 | Verified online-backup SHA-256 |
| --- | --- | --- |
| Provider | `63fcf785a5d9733df8b30191cf9ab531a597f42ba418201ad9a5bca439ccdc9b` | `8840190e1c32b2182f27ebb12d3930077b475264127f560721f2a5c581a1167c` |
| Canonical | `efa24a84f6d12b96d7da5153d048f2776b72dd1c805f774dd89271cd6b134807` | `0a2d886066c567f686cda61f5585e031add3c863650ff9c0d6f70730150808eb` |
| Analysis | `1397982264fd9550504b4605b74e8320729b1e74318e95d680a62eaee7f39d98` | `77d701ca0b3bc2c07dc6a1700f7fbfd07a51c4c1ca381a343e2eaeb8e5cb9fb9` |

The actual original provider file still matched its OLD manifest hash. This is a recovery-verification/protocol binding failure, not proof that the OLD financial values were corrupted. Reactivating the old pointer alone does not satisfy the contract: the journal remained `RECOVERY_FAILED`, with recovery required rather than the expected verified OLD state and fresh-retry result.

Both `AFTER_NEW_GENERATION_READY` and `AFTER_GENERATION_ACTIVATION` failed. The focused rerun independently reproduced the first boundary. The standalone generation unit tests passing does not cover this production backup-caller integration.

## Required next safety work before resuming rollout

Review and repair the native Refresh backup/generation binding first. The existing `_verified_backups(..., immutable_generation=True)` branch already supports byte-exact immutable copies with sidecar and hash checks. Select the correct mode for actual immutable generations and prove every OLD role, backup receipt and OLD manifest hash agrees **before** the destructive boundary. Preserve the existing legacy-flat online backup behavior and full-generation recovery protocol; do not weaken the verifier or improvise partial restoration.

Strengthen the ordinary rollback tests to require successful terminal journal/recovery state in addition to old pointer/file equality. Rerun the complete combined scenarios, including before-activation, activation-intent/after-swap and postflight failures, under the exact qualified source snapshot. Revalidate the archived locality/UI patch and approval regressions only after that shared safety condition is resolved. No current blocked Preview may be reused as publication authorization.

The one controlled live-run authorization was **not consumed**. The requested fresh pre-production checks and fresh Full Workflow were not reached. No further YES was requested, and no alternative publication mechanism was used.

## Live state, collateral checks, and commit

Final SHA-256 and size comparisons matched the fresh baseline for all seven protected files: active manifest, live journal, operational queue, scheduler configuration, and the three active financial roles. Exact receipts are in `evidence/final_live_files.json`.

| Live role/control | Final unchanged SHA-256 |
| --- | --- |
| Provider | `14a032489577c079607e16986380076986ab8206ed1d96aa135700499432de4f` |
| Canonical | `2178d467a12a601e9554353fea8a3f8354444cb9347be000c3dca6c13b3e0a6d` |
| Analysis | `6feb14748b4088096d96287d7f3b1c812faed4dc8e2352a81b390d8b86d11d8f` |
| Manifest | `82afaa462cc12ef41616c10d3ad011bac266b452cca02e6abea605c8d5b97097` |
| Journal | `91fadb71f55be7bad2107db8948744abb17a1a7494bfb3d64d78fe2d155c1e72` |
| Queue | `9d461822eb51b5e01fdf6310c58b1a67265a9fefb210b3c50232911f1a041428` |
| Scheduler configuration | `f4ba4fc0fde48e3ac82f5314353556ae35a0327a2e568b41abf9c759c35bb8a3` |

Provider/canonical/analysis, review decisions/audit, WFRD, P/B state, active generation, watermark and existing publication dates remain unchanged. No new safe quarters or P/B continuation were published. No cleanup or price-pipeline/StockCore modification was performed.

No implementation commit was created because the required acceptance gates did not pass. HEAD remains the audit commit. No push was performed. The report and isolated patch preserve the concrete work and failure evidence for the next safety review.
