# Fundamentals V4 Phase 13D.2 Complete Onboarding Rehearsal

Outcome: **OUTCOME B — ECONOMIC REBUILD COMPLETE; RELATIVE VALUATION, REPORTING OR ROLLBACK CONTRACT STILL BLOCKED**

Phase 13D.2 rehearsed a two-ticker AREB/SNDK onboarding batch on production-shaped SQLite online-backup copies only. No production database, Scheduler configuration, production pointer or existing `fundamental_reports` file was intentionally written.

Final artifact directory:

`temp/fundamentals_v4_phase13d2_complete_onboarding/20260912T_PHASE13D2_RECOVERY_FINAL_DETERMINISTIC`

The recovery-final run used fresh copy identifiers after the WSL disk-capacity recovery. Earlier incomplete copy directories are not required evidence.

## Source And Identity

AREB used existing local provider observations and existing canonical identity:

- identity status: `CANONICAL_HISTORICAL_SECURITY`
- provider ARQ observations: 47
- provider MRQ observations: 42
- canonical quarters: 39
- operational universe status: `HISTORICAL_RETAINED_NO_ACTIVE_SECURITY`
- taxonomy status: `TAXONOMY_REVIEW_REQUIRED`

SNDK used the verified managed Sharadar archive only:

- archive: `data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip`
- SHA-256: `dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`
- network/API requests: 0
- identity status: `RESOLVED_WITH_PREDECESSOR_RISK`
- current Sharadar permaticker: `643888`
- SEC CIK: `0002023554`
- provider ARQ observations: 13
- provider MRQ observations: 13
- canonical quarters: 9

SNDK1 remained separate. The predecessor/reuse evidence is `SNDK1` / permaticker `197210`; no SNDK1 archive observation was attached to current SNDK.

## Taxonomy

SNDK retained the Phase 13D.1 conclusion: `CONNECTED_EXISTING_MEMBERSHIP`.

The copy-only taxonomy identity linkage added stable alias evidence to the existing SNDK entity and created no duplicate memberships. Reported groups were:

- `MEMORY_HBM_DRAM_NAND_SSD:EXTENDED`
- `STORAGE:CORE`

The active membership query currently returns duplicate rows for those memberships; Phase 13D.2 did not create additional duplicates. The taxonomy economic fingerprint did not change because SNDK already had valid active economic membership.

AREB remained `TAXONOMY_REVIEW_REQUIRED`. No taxonomy group was invented to make the batch pass.

## Downstream Rebuild

The full copy-only authoritative downstream package was rebuilt and activated:

- AREB Score: `SCORE_LIMITED`
- AREB Lifecycle: `LIFECYCLE_READY`
- AREB Valuation: `VALUATION_FULL`
- AREB Delta: `DELTA_READY/DELTA_READY/DELTA_READY`
- AREB diagnostics: eight latest statuses all `TTM_READY`
- SNDK Score: `SCORE_FULL`
- SNDK Lifecycle: `LIFECYCLE_READY`
- SNDK Valuation: `VALUATION_FULL`
- SNDK Delta: `DELTA_ENDPOINT_NOT_COMPARABLE/DELTA_ENDPOINT_NOT_COMPARABLE/DELTA_ENDPOINT_NOT_COMPARABLE`
- SNDK diagnostics: latest statuses include `TTM_READY` and earlier `TTM_NOT_READY`
- Relative Position result rows in package: 13,743

TTM endpoint existence is not treated as full economic readiness. Both AREB and SNDK have `ttm_core_ready_rows=0` in the final readiness matrix and are represented with the exact downstream statuses above.

## Relative Valuation Boundary

Before the explicit manual refresh, the old Relative Valuation snapshot was incompatible:

- old snapshot date: `2026-09-10`
- state: `OPERATIONAL_UNIVERSE_MISMATCH`

The manual full-universe Relative Valuation refresh was invoked separately on the analysis copy:

- new snapshot date: `2026-09-12`
- source fingerprint: `b3659267cc950f2af6a74c66396aa71a5a45fb5b9d5e42d25addc9f4948737d8`
- result fingerprint: `7a207058792a8e35da35d7a4d4ab384b6621a9ca0ad2ada12f4c883ead652315`
- physical content fingerprint: `643a58f441002838092263dcdbfbaeddebc2d9563c36df03b20d3c190548e5f0`
- company rows: 2,449
- peer rows: 9,796
- own-history rows: 2,449
- component rows: 7,347
- apply outcome: `ACTIVATED`

The immediate second manual refresh returned genuine `NO_CHANGE` with zero logical writes and no physical change.

## Snapshot Reports

Temporary reports were generated under the artifact directory for SNDK, AREB and NVDA, both pre-refresh and post-refresh. All report generations returned `CREATED`, and SNDK reports contained no `SNDK1` text.

Post-refresh reports rendered with compatible Relative Valuation data. Pre-refresh reports also rendered rather than explicitly suppressing the Relative Valuation section, even while `pre_refresh_compatibility.json` correctly reported `OPERATIONAL_UNIVERSE_MISMATCH`. This remains a UI/reporting contract gap for Phase 13E.

Report content determinism remains blocked. After fixing Relative Valuation source nondeterminism, the raw pipeline replay was identical, but report content fingerprints still differed because the technical appendix source-state fingerprint includes run-local audit state such as generated timestamps and relative package identities. The diffed report body differed only in:

- `Source-state fingerprint`
- `Report-content fingerprint`

## Determinism Investigation

Two reader corrections were made before the final deterministic run:

- Relative Valuation source now strips upstream Relative Position `snapshot_id` from `filing_peer_results`.
- Relative Valuation source now strips filing valuation `calculated_at_utc` from `filing_valuation`.

These fields were run-local metadata and caused different RV source/result fingerprints despite identical physical RV bulk output.

Final replay evidence:

- `raw_equal`: true
- raw differences: none
- RV source fingerprints: equal
- RV physical content fingerprints: equal
- `normalized_equal`: false, due only to Snapshot report content fingerprints

## Rollback And Idempotency

The rehearsal produced copy-only recovery artifacts but did not prove the full required failure-injection matrix. `rollback_rehearsal.json` therefore remains `NOT_FULLY_PROVEN`, and Phase 13E must require full online backup restoration for every database in the write set.

The second Relative Valuation refresh proved `NO_CHANGE`. The full second onboarding/apply no-change contract remains `NOT_FULLY_PROVEN` in this orchestration artifact.

## Production Safety

Production postflight SHA-256 checks matched preflight for:

- provider
- canonical
- analysis
- market
- taxonomy

Production quick checks were `ok` before the full rehearsal. The final rehearsal wrote only under `temp/fundamentals_v4_phase13d2_complete_onboarding/`.

## Remaining Blockers

Phase 13E must not proceed as Outcome A until these are resolved:

- AREB taxonomy remains `TAXONOMY_REVIEW_REQUIRED`.
- Snapshot/UI pre-refresh rendering does not explicitly suppress incompatible Relative Valuation despite the dependency state reporting mismatch.
- Snapshot report content fingerprint is not deterministic because source-state includes run-local audit fields.
- Full failure-injection and exact multi-database rollback restoration matrix is not proven.
- Full onboarding second-apply `NO_CHANGE` remains not fully proven.

## Phase 13D.3 Closure Update

Phase 13D.3 supersedes two D13D.2 blocker interpretations:

- The 14 full-suite failures were retired Fundamentals V3 real-CSV fixture tests for `temp/v3_active_tickers_99_27.csv`, not active V4 runtime failures. They are marked `retired_v3`; synthetic V4 bootstrap tests remain active.
- Snapshot report-content nondeterminism was traced to reuse of the same source-state object for both machine audit and rendered report fingerprinting. The Snapshot assembler now retains full `source_state_audit` while rendering/fingerprinting a stable presentation `source_state`.

AREB remains blocked for batch production onboarding unless local classification is reconciled. Local evidence confirms `AMERICAN REBEL HOLDINGS INC`, but `ticker_meta` currently says `Consumer Cyclical / Footwear & Accessories`, which does not match the corrected expected classification `Industrials / Commercial Services & Supplies`.
