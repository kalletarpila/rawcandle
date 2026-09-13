# Phase 13F.3.3.1 Structural-Break Verification Closure

Outcome: `OUTCOME B — CORRECTABLE VERIFICATION OR IMPLEMENTATION GAP IDENTIFIED; PRODUCTION NOT AUTHORIZED`

Evidence root:
`temp/fundamentals_v4_phase13f3_3_1_verification_closure/20260913T_PHASE13F3_3_1_VERIFICATION`

Reused Phase 13F.3.3 FINAL3 evidence:
`temp/fundamentals_v4_phase13f3_3_structural_break_contract/20260913T_PHASE13F3_3_FINAL3`

## Rationale

Phase 13F.3.3 implemented `ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1` and verified the copy-only downstream chain, but this closure audit found that the contract is not yet enforced across every upstream Fundamentals V4 calculation layer. The current implementation classifies event companies and gates current Relative Position, current Relative Valuation, Own-History input selection for eligible current rows, and Snapshot current-price valuation rendering. It does not yet make canonical quarter selection, TTM construction readiness, Score, Lifecycle, filing Valuation, Delta 2Q, or the eight Diagnostic evaluations structurally fail closed at package-build time.

This is a correctable implementation gap rather than a redesign finding: the additive structural-event tables, fingerprints, current eligibility reader, and downstream gates exist. Production activation is not authorized until the upstream package refresh contract consumes the same structural regime state and persists explicit structural statuses/reasons.

## Baseline

- Branch: `chore/ignore-backups`
- Required commit present: `7ce2eb0de94c677fe687cc2b927a132e086fea17`
- Production paths:
  - provider: `/home/kalle/projects/rawcandle/data/fundamentals_provider.db`
  - canonical: `/home/kalle/projects/rawcandle/data/fundamentals_v4.db`
  - analysis: `/home/kalle/projects/rawcandle/data/fundamentals_analysis.db`
  - market: `/home/kalle/projects/rawcandle/data/osakedata.db`
  - taxonomy: `/home/kalle/projects/rawcandle/data/analysis.db`
- Active Operating-Income family: `OPERATING_INCOME_MODEL_FAMILY_V2`
- Active family fingerprint: `634824f179652da81ea6f38962d9a7c87df37c0627fed089a918ce9efa83d8e9`
- Active package persistence fingerprint: `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- Active operational universe: `1e01484c56dec911b961d680e867a51a`
- Active operational-universe economic fingerprint: `bfa502d3bd16c11dceee9e03849c0c0f04b91b24e9f07e967401a9de6685e594`
- Active Relative Valuation snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`
- Active Relative Valuation result fingerprint: `7a207058792a8e35da35d7a4d4ab384b6621a9ca0ad2ada12f4c883ead652315`
- Disk before closure artifacts: about 696 GiB free on `/home/kalle/projects/rawcandle` and `/tmp`.

## Structural Identities

- Contract: `ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1`
- Structural package fingerprint: `4ba542c7e28c2d92ba65863f2932e2683a60b053cb4b2debe344b051a84441ad`
- Event fingerprint: `5ec6403d231e41a52fdf04609892df1c9bdd841805180a52578b638114bf5bfd`
- Regime fingerprint: `b6c1fbed8182ee589e3f85ee7057571ff34b75f56de7d92f4b1a3d74aac64852`
- Current structural source fingerprint: `04339360f686ae6d68c6f502139a9af4cf6ebe38699c22ba30d6216a6ff06e1f`

## Enforcement Matrix

The machine-readable matrix is retained at `verification_evidence.json`. Summary:

| Layer | Finding |
| --- | --- |
| Canonical quarter selection | Partial. Overlay classifies quarters by `period_end` and event date, but canonical selection itself is not structural-aware. |
| TTM construction | Partial. Overlay marks `STRUCTURAL_NOT_READY`, but `v4_ttm_values.readiness_status` remains independent. |
| Score components/lookbacks | Gap. `operating_income_v2/rehearsal.py` computes scores from TTM rows without structural eligibility. |
| Score readiness | Gap. No persisted structural not-ready status exists in `score_result`. |
| Lifecycle | Gap. State machine can traverse a material break without structural reset/unavailable reason. |
| Filing/current Valuation | Partial. Snapshot current valuation is gated; filing valuation package is not structurally aware. |
| Delta 2Q | Gap. Delta histories are built from score observations without regime checks. |
| Eight Diagnostics | Gap. Current/prior endpoints can span a break without structural reason codes. |
| Relative Position | Enforced for current source eligibility through `relative_position/source.py`. |
| Current Relative Valuation peer | Enforced through `relative_valuation/source.py`; blocked inputs are excluded before peer results. |
| Own-History Relative Valuation | Partial. Same-regime history filtering exists for eligible current rows; future post-event READY/LIMITED integration still needs direct proof. |
| Persisted reader/Snapshot | Partial. Snapshot current-price valuation is blocked and audited; archived rows remain readable but are not reinterpreted. |

## Date Boundary Evidence

Focused tests now cover:

- availability after event does not reclassify a pre-event fiscal period;
- event during period and event on period end fail closed without explicit period-start evidence;
- missing event date fails closed for current cross-boundary calculations;
- no fixed 90-day post-event clean-quarter inference is used;
- companies without a registered structural event retain existing behavior.

Test file: `tests/test_structural_break_contract.py`.

## Company Acceptance Matrix

| Ticker | Result |
| --- | --- |
| VMRK | Major business combination; current Relative Valuation excluded with `CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM`. Snapshot Markdown can be generated but must show structural limitation. |
| IA | Accepted same-security continuity; eligible under `NO_ECONOMIC_BREAK`. |
| VAI | Conservative `BUSINESS_COMPARABILITY_REVIEW_REQUIRED`; current Relative Valuation excluded until independently resolved or clean post-event evidence exists. |
| NXH | Current Overstock/Beyond/NXH lineage accepted; bankrupt BBBYQ issuer separated by CIK/permaticker evidence. |
| NMAD | Reverse-merger major business break; current Relative Valuation excluded until clean post-event inputs exist. |
| AREB | Historical participation remains readable inside listing interval; post-delisting current Relative Valuation rows remain zero. |
| NVDA | No-event control Snapshot generated in FINAL3. No structural contract row is registered. |

## Relative Valuation And Own-History

FINAL3 evidence remains valid for the downstream chain:

- pre-refresh Relative Valuation became incompatible through operational-universe dependency mismatch;
- manual copy-only full-universe Relative Valuation refresh completed;
- second Relative Valuation apply returned `NO_CHANGE`;
- blocked current input counts included `CURRENT_REPORT_REQUIRES_POST_EVENT_CLEAN_TTM: 3`;
- `second_logical_zero_writes` and `second_physical_no_change` were true.

Own-History filtering uses `allowed_history_quarter_ids()` to restrict history to the current accepted regime when a current structurally registered company is eligible. Because VMRK, VAI and NMAD are currently excluded before Own-History readiness, this closure cannot claim full future post-event READY/LIMITED behavior without the upstream package changes and a future/post-clean integration case.

## Test Results

- Pre-change full suite baseline: `2 failed, 2912 passed, 14 deselected, 8 warnings in 594.22s`.
- Baseline failures:
  - `tests/test_phase13d_backend.py::test_ticker_apply_rebuilds_copy_dependencies_and_second_apply_no_changes`
  - `tests/test_phase13d_backend.py::test_ticker_apply_failure_restores_all_copies`
- Root cause: stale test fixture expectation. Both tests built a preview at `2026-09-12T10:00:00Z`; by the current run date, `2026-09-13`, the real 24-hour preview expiry correctly raised `PHASE13D_PREVIEW_EXPIRED`.
- Minimal correction: freeze `phase13d_backend.utc_now()` inside those apply tests to `2026-09-12T11:00:00Z`, leaving the production expiry rule unchanged.
- Focused post-correction tests: `8 passed in 6.90s`.
- Post-change full suite: `2918 passed, 14 deselected, 8 warnings in 596.87s`.

Commands:

```bash
python3 -m py_compile tests/test_phase13d_backend.py tests/test_structural_break_contract.py
pytest tests/test_phase13d_backend.py::test_ticker_apply_rebuilds_copy_dependencies_and_second_apply_no_changes tests/test_phase13d_backend.py::test_ticker_apply_failure_restores_all_copies tests/test_structural_break_contract.py
pytest
```

## Production Immutability

No production writes, production activation, Scheduler/UI changes, network requests, or report regeneration were performed. Preflight and postflight `PRAGMA quick_check` returned `ok` for provider, canonical, analysis, market and taxonomy databases; foreign-key check counts were all zero. FINAL3 normalized production immutability evidence remained identical except the already documented read-only taxonomy SHM mtime/content-identical sidecar behavior.

## Cleanup

This closure did not create a new large copy-only rehearsal. The prior FINAL3 run had already removed its copied `.db`, WAL, SHM and journal files and retained compact JSON/Markdown artifacts. The new closure artifact root contains compact JSON only.

## Remaining Blockers

Production deployment and a Phase 13F.4 production runbook are not justified until a follow-up implementation makes the structural-break regime a first-class dependency of:

- canonical/TTM source readiness or an equivalent package input contract;
- Score component lookbacks and Score readiness;
- Lifecycle transitions;
- filing Valuation;
- Delta 2Q;
- all eight Diagnostic evaluations;
- future post-event Own-History READY/LIMITED integration tests.
