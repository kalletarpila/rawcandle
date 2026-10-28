# Ordinary quarterly P/B ownership auto-continuation policy

2026-10-28, Europe/Helsinki. Task P/B-OWNERSHIP-AUTO-CONTINUATION-1. Starting HEAD `49cad24e9fb54a294a1198a1f4f31342d6f429fb`.

**Implemented, copy-only rehearsal PASS; live rollout NOT performed.** Exact current partition after controlled copy reconciliation: **6 AUTO_CONTINUE, 0 MANUAL_REVIEW, 0 DEEP_REVIEW/BLOCKED**. Safe ordinary set: **AMT, BA, DHR, GM, PNR, PSA**. GE/RTX/T remain published, without duplicate decisions. The explicit rollout gate remains outstanding under this task’s boundary.

Governing evidence: [factor-loss audit](pb_ownership_provider_factor_null_audit_2026-10-28.md), [payload completeness](pb_provider_payload_completeness_repair_2026-10-28.md), [controlled source repair](pb_payload_repair_controlled_workflow_2026-10-28.md), [GE/RTX/T revalidation](pb_ownership_revalidation_ge_rtx_t_2026-10-28.md), [successful ownership publication](pb_ownership_publication_ge_rtx_t_2026-10-28.md) and [locked cleanup contract](ownership_publication_cleanup_contract_2026-10-28.md). Prior approvals/publication/cleanup do not authorize this new six-case rollout.

## Current burden and bounded cohort

Before policy edits, read-only detection/preview reproduced six CONTINUATION_CANDIDATE cases requiring a new manual confirmation despite ordinary reviewed interpretation, factor 1→1 and stable company/security/category. Their hypothetical P/B values reconstruct. The six stored live OPEN candidates also contain the pre-GE-publication registry hash; fresh detection under the current registry has the same observation-bound case IDs but different candidate hashes. Controlled reconciliation refreshes those bindings on the disposable queue only. Treating the old stored hashes as current would fail the stale-candidate guard.

| Ticker | Prior shares | New shares | Delta % | Factors | Prior/current category | Prior/current security | Hypothetical Current P/B |
| --- | ---: | ---: | ---: | --- | --- | --- | ---: |
| AMT | 465,960,048 | 463,763,555 | -0.471390843 | 1.0 → 1.0 | Domestic Common Stock Primary Class → same | 150 → 150 | 24.243205131327542 |
| BA | 790,370,020 | 792,449,940 | 0.263157755 | 1.0 → 1.0 | Domestic Common Stock Primary Class → same | 269 → 269 | 20.35653354286288 |
| DHR | 702,986,054 | 703,530,815 | 0.077492433 | 1.0 → 1.0 | Domestic Common Stock Primary Class → same | 671 → 671 | 3.0439407896160087 |
| GM | 877,451,541 | 843,549,423 | -3.863702600 | 1.0 → 1.0 | Domestic Common Stock Primary Class → same | 958 → 958 | 1.0817353644669707 |
| PNR | 159,637,950 | 159,654,682 | 0.010481217 | 1.0 → 1.0 | Domestic Common Stock Primary Class → same | 1771 → 1771 | 2.5765299466159455 |
| PSA | 175,621,134 | 186,843,449 | 6.390070913 | 1.0 → 1.0 | Domestic Common Stock Primary Class → same | 1811 → 1811 | 4.025757519078477 |

All six current sources retain the full 112-field SF1 acquisition shape, non-null factor 1.0, exact accepted observation ID/hash, ARQ/DIRECT/HIGH shares provenance, one active canonical security and matching stable provider/security identity. No current source substitution is used. Each reason in the final partition is AUTO_CONTINUE with every required guard passed; both corporate-action coverage and dated quarterly-share warnings remain attached.

## Share-delta evidence and policy

| Ordinary reviewed/approved cohort | Delta % |
| --- | ---: |
| AMT | -0.471390843 |
| BA | 0.263157755 |
| DHR | 0.077492433 |
| GE | -0.405815741 |
| GM | -3.863702600 |
| PNR | 0.010481217 |
| PSA | 6.390070913 |
| RTX | 0.124829815 |
| T | -1.691560034 |

Bounded current/recent cohort n=9; minimum -3.863702600%, median 0.010481217%, maximum 6.390070913%. GE/RTX/T values come from the retained exact pre-publication approved cases, not newly generated decisions. The cohort is too small and lacks labeled structural exceptions to derive a reliable NORMAL/WARNING/MANUAL numeric band. **Share-change magnitude is diagnostic and nonblocking**, never the sole release criterion. No 5% rule, ticker-specific exception or magnitude normalization is introduced; PSA’s +6.39% is assessed through the same guards. Synthetic regression cases also exercise larger ordinary drift without a magnitude shortcut.

## Exact eligibility contract

Policy version: **PB_ORDINARY_AUTO_CONTINUATION_V1**. `pb_ownership_auto.evaluate` is read-only and deterministic. It returns AUTO_CONTINUE only when every gate passes:

1. Candidate body/hash, fresh detector binding, registry and exact accepted quarter/observation match. Tampered, stale or missing evidence is DEEP_REVIEW/BLOCKED.
2. Prior interpretation is REVIEWED_SUPPORTED / ORDINARY_COMMON / COMMON_OR_ORDINARY / ORDINARY_COMMON release, without identity override or policy hold. ADS/ADR and other interpretations remain manual; they are not implicitly inherited into automatic approval.
3. Exactly one active canonical security; company key/company ID/security ID/canonical ticker match the reviewed interpretation. Category must be exactly unchanged and ordinary common. Provider stable identity must resolve uniquely, with consistent current listing/category metadata and no delisted conflict.
4. Previous and current factor must both be present, non-Boolean and exactly 1.0. None is never normalized to 1.0. None→1 and 1→None produce SOURCE_PAYLOAD_INCOMPLETE; 1→other, other→1 and other→other require factor review. No non-ordinary equivalence is inferred.
5. Acquisition payload contains every field of the versioned, observed full 112-field SF1 shape. Nullable unrelated metrics remain nullable, but factor/shares/equity/equityusd/price/marketcap/pb must be present and non-null. Missing keys, legacy 29-field projections and incomplete ownership evidence explicitly produce SOURCE_PAYLOAD_INCOMPLETE. Additional source fields are allowed.
6. Exact SHARADAR/fundamentals/ARQ observation, natural key, raw/canonical values, company/security/provider ID and accepted source availability match. Native observation count is exactly one. Content hash uses a recognized existing ingestion convention; full raw payload and completeness fingerprints are also bound separately. This preserves the financial-projection hash convention without treating it as a full-payload hash.
7. Shares provenance is exactly SHARADAR / sharesbas / DIRECT / SHARADAR_ARQ_PRIMARY_V1 / HIGH from the accepted observation. Positive finite shares equal canonical shares_outstanding. No fallback/hybrid/mixed source is allowed.
8. Current history has no invalid rows, ambiguous source versions, current retention anomaly or unresolved source review. Already classified out-of-historical-horizon retained rows remain historical evidence; they are not reclassified, deleted or treated as unresolved current source removal. Exact completed source-payload repair provenance is accepted only when its new observation/hash/completeness bind the current raw payload. Other current provenance requires deep review.
9. Known share changes, newer-share-count requirements, class/perimeter conflicts, matching internal ownership-basis actions (ticker or counterparty) and local splits all block automatic continuation. Holds are not cleared.
10. Existing hypothetical P/B is OK with positive finite usable price, equity USD and value; Decimal(price) × accepted ordinary shares / parent_equity_usd reconstructs within 1e-12 relative/absolute tolerance. Provider P/B is not substituted. Missing inputs remain held.

The prior observation may have been replaced by normal provider-history refresh. Its reviewed canonical identity is still exact: the unique SHARADAR security binding must match the current stable provider ID and predate the original review. If the prior observation is still retained, its provider/company/security identity must also agree. A ticker alone cannot establish continuity; missing or conflicting stable mapping blocks the decision.

## Corporate-action coverage choice

**Incomplete internal corporate-action coverage is an informational warning, not proof of no action and not a standalone blocker.** This is an explicit policy choice for the requested hobby-mode quarterly continuation. The existing quarterly reporting contract already treats accepted shares as a dated reporting approximation, not a complete daily capitalization ledger. Automatic decisions inherit only the previously reviewed ordinary unit interpretation and bind new complete accepted quarterly shares; all positive conflicts and independent source/identity/provenance/P/B gates remain hard holds.

Available provider actions are a filtered bootstrap ending 2026-08-31; local split coverage is more recent but does not cover every merger, issuance or class event. Every automatic decision records CORPORATE_ACTION_COVERAGE_INCOMPLETE and QUARTERLY_SHARES_ARE_A_DATED_APPROXIMATION. Matching events are checked from the previous share-source date through as-of, including counterparties. Routine cash dividends do not change ownership units; other/unknown action types block. No acquisition or outside research extends the ledger in this phase. Residual limitation: an unrecorded event with no contradictory source/category/identity evidence can escape this internal-event guard. The policy does not claim otherwise.

## Decision, manual approval and publication lifecycle

An automatic queue state/event is **AUTO_CONTINUED / PB_OWNERSHIP_AUTO_CONTINUED**, with result AUTO_CONTINUED_PENDING_PUBLICATION. The shared inactive-candidate builder is reused. Approval evidence contains decision_type, policy_version, decision timestamp (`approved_at` in the shared envelope), case/candidate IDs, exact observation/hash, source identity, provider metadata, delta, provenance, completeness/raw fingerprint, history evidence, corporate-action scan/coverage warning and Decimal reconstruction. The record uses approval_mode=AUTO_CONTINUED and carries the complete policy evidence. It has **no operator or operator_note**; Kalle is not fabricated. Prior URLs support the reviewed unit interpretation, not an assertion that the old filing contains the new share count.

Manual `approve` and the UI-service API accept missing/None/empty operator and note. Literal confirmed=True remains mandatory, with exact case/hash and the existing candidate/artifact audit. Historical approvals with operator/note retain their original record semantics. UI changes are limited to optional labels/enabling on confirmation and showing pending automatic decisions as automatic. Hold notes and the separate Production-publication operator/confirmation contract remain unchanged. Source-repair and accounting-boundary approval requirements are untouched.

Canonical reporting accepts a structurally bound automatic ordinary record and displays **AUTO_CONTINUED_QUARTER**, distinct from OPERATOR_CONFIRMED_QUARTER. All exact observation/date/value/category guards still apply; malformed or unsupported automatic evidence remains held.

An existing automatic decision whose candidate/registry hash changes is invalidated through PB_OWNERSHIP_AUTO_INVALIDATED. Its full prior approval/result are retained in audit before the current row returns to OPEN for fresh policy evaluation. Later observations supersede pending automatic rows through normal history retention. Human approvals are not silently rewritten. An explicit hold note remains an automatic blocker even if ordinary reconciliation reopens that same case.

Execution timing: normal ownership reconciliation can explicitly opt in with `sync_ownership(..., auto_continue=True, provider_db=..., market_db=..., output_root=...)` after complete source validation under the existing operation/Production/scheduler owner guards. Defaults remain off, so installing this code does not migrate live OPEN cases or silently enable a scheduler policy. `auto.reconcile(..., enabled=False)` only partitions; enabled=True creates decisions and inactive candidates. It never publishes or writes live financial roles.

Automatic decisions wait for the existing separate OwnershipPublicationWorkflow. Its explicit selection, source-bound preview, candidate generation, final guarded activation, postflight, journal, queue finalization and rollback mechanisms are reused. Publication rechecks frozen automatic evidence at its decision date and fresh policy eligibility at publication as-of, with provider/market/queue bindings; raw/identity/registry drift blocks. New policy code joins the publication code fingerprint. A later usable price can be previewed normally only if original evidence and all fresh guards still pass. Changed registry/source evidence requires fresh reconciliation rather than bypassing a stale decision. No exceptional review, source repair, accounting boundary or ADS interpretation is automatically published.

## Exact current OPEN partition and rollout set

| Ticker | Partition | Reason | Case ID | Fresh candidate hash |
| --- | --- | --- | --- | --- |
| AMT | AUTO_CONTINUE | All gates pass; coverage warnings retained | `9e013833acbece570cd72b1239965a6b31f008ce5ebce2d754cd25da9fa8d1b3` | `a900ca83a300da6e50a99bb9cb4fef2cc8a48139e786b0fb964fcec6356a78e3` |
| BA | AUTO_CONTINUE | All gates pass; coverage warnings retained | `8bc27f080d9d65718994ff08fd4d50590b4d43aa7b3c9bdc35aeb04758abb937` | `9dc018f6efcccee49beeebc7b13d522da9285eb6b360152d79ceca0f6491574d` |
| DHR | AUTO_CONTINUE | All gates pass; coverage warnings retained | `02d04d87dd80c0a3dab8dd153bc1f32afe8191e9eda8c1b016bab3a713f948d3` | `918750ea3a90cd5b346ae802c08b836e60a221ea7144dad51143ee79dbc34659` |
| GM | AUTO_CONTINUE | All gates pass; coverage warnings retained | `5cbe89d48b437067184311ab89c783144bfa50a94ee7920f9c660c3830ed106a` | `4e3687e1c9cb24887d8e2c07a2f1a8ed326ab41a92525f17527b050ee431c010` |
| PNR | AUTO_CONTINUE | All gates pass; coverage warnings retained | `3cd1f003fea91b9b4556f479ffc2e87ed7afdaeeb69a3ac15d5a7b7d0f268bc7` | `cbd280a1c2ad3a9a75bf6bd9f6f52e634bacba4f68511a256d8b55ea19e08f57` |
| PSA | AUTO_CONTINUE | All gates pass; coverage warnings retained | `e8d431a55be32e1a74d82d91865f631c63ac642889e870f15a499562d053ab1d` | `858adedf0fee5c7584f75684ae2afe47f09ebce2addd7772fe1c07980fdaaa1c` |

Current count: 6. AUTO_CONTINUE: 6. MANUAL_REVIEW: 0. DEEP_REVIEW/BLOCKED: 0. These counts apply only after controlled reconciliation on the copied queue against the current registry. Existing live OPEN rows and all reviewed history are unchanged. Synthetic exception tests prove that this all-ordinary current set does not release exceptional cases.

| Ticker | Exact accepted observation | Content hash |
| --- | --- | --- |
| AMT | `d76ed514b053931df52a6f88c7f30cbb2194d0d739342cd444944a2746089413` | `6dec2f5339ba3ef18abf1fc8e1c3a04b26c83a01020853c6c9998fa60e95ed0c` |
| BA | `432ef662bf06829a4100e4dc9602803130530635af1bb95a57a81fc0fe9733ad` | `0428d5210e9c1f7fa948b8cdde1a54783b106de786785003aa9cb305c8e0480b` |
| DHR | `92be12ae42c6b7a9247123045a0b60c2fdb7c789ac8834b6fa77e70de35e93d2` | `b50bd10488850f0fa36eba6b7ca0e7419d21f9031d0a9e5899c18b89835ed697` |
| GM | `5fcba15c830f9e3de94982bcde763446d7e011c96453ed079af9e9862436d6e3` | `18722e7e780f9ee0544399676dcf545fdc0eb12cfffad360906bb23f0a842490` |
| PNR | `8e634936641d81e2c6a103452c110f8518c5674694e22304d4235ab21cf9d85a` | `acabbad2cbd305829d69b7b4c5da6382632681ded3c2c44f0fee8421f33f2cd7` |
| PSA | `33ad245568687f57fb6474842a23e2dce75a46fa540b10c3c4e49c648f63a57d` | `06bf0a260b7d556cc4f2e1630b12dcd11f1bc07914d2ce0d499fa0d9bff8e6b8` |

## Copy-only rehearsal and protected state

Final rehearsal directory: `/tmp/pb_auto_continuation_20261028/rehearsal_200857`. Completed `2026-10-28T20:09:50.637457+00:00` UTC (22:09:50 Europe/Helsinki). Provider/canonical inputs were copied from the verified immutable generation; market and WAL-aware queue copies used SQLite backup. Initial role hashes and complete queue logical content matched the protected live baseline. Controlled sync refreshed six stale candidate bindings, then the normal inactive builder created exactly six automatic decisions/candidates. Repeating reconciliation created zero additional decisions.

All six candidates passed quick/FK verification and complete canonical financial/schema/publication-authority content equality, excluding only the two ownership artifact/configuration tables. The 66 existing artifact records remain exactly in order; cumulative inactive candidate sizes are 67 through 72 records. GE/RTX/T published rows and all their historical/superseded rows are identical. Source-repair/other queue tables remain identical; only the six selected copy ownership rows and their copied queue audit change.

Live current generation remains `pb_ownership_903cf258a97f4873aa0f4797404a61ac`; provider watermark remains 2026-10-27. Active manifest, provider/canonical/analysis/market hashes, journal, source-repair decisions, WFRD/publication-authority state, full live queue and scheduler configuration are unchanged. Only the authorized source/tests/UI files and this report change. No live decision, generation publication, provider repair, source acquisition, backup cleanup or generation deletion occurs.

Rehearsal result SHA-256: `a2972376b320ce56fb768d3d59e724a5a6d19c85b6cf66194b6ce3622970f43d`. Protected baseline: `/tmp/pb_auto_continuation_20261028/before.json`. Working evidence: `reproduction.json`, `result.json` and candidate paths under the rehearsal directory above. Final-source read-only verification produced the identical six-case partition at `/tmp/pb_auto_continuation_20261028/final_partition_verified.json`; final live equality is retained in `final_live_verification.json` beside it. Runtime files/DBs are excluded from Git.

## Focused regressions

**472 compatibility tests passed in 524.62s; 168 final-source focused tests passed in 159.22s.** The groups overlap quarterly/reporting cases; they are not a claim of 640 distinct tests. Full suite: **NO**. The compatibility group covers `test_fundamentals_pb_quarterly_ownership.py`, `test_fundamentals_pb_reporting.py`, `test_fundamentals_pb_ownership.py`, `test_fundamentals_pb_ownership_publication.py`, `test_provider_payload_completeness.py`, `test_provider_payload_workflow.py`, `test_wfrd_accounting_boundary_review.py`, `test_wfrd_production_candidate_parity.py` and `test_ownership_publication_cleanup.py`. The final group covers `test_pb_ownership_auto_continuation.py`, `test_fundamentals_pb_new_quarter_review.py`, `test_fundamentals_pb_quarterly_ownership.py` and `test_fundamentals_pb_reporting.py`. All paths are under `tests/`. Commands used `PYTHONDONTWRITEBYTECODE=1 venv/bin/python -B -m pytest -q <listed files> --disable-warnings --maxfail=1`. Raw logs: `/tmp/pb_auto_compatibility_tests.log` and `/tmp/pb_auto_release_tests.log`. Focused coverage includes quarterly ownership and reporting, exact normal drift, missing/explicit-null/changing/nonordinary factors, complete repaired GE/RTX/T evidence, category/security/source-key drift, duplicate observations, actions/counterparties, invalid price/equity/reconstruction, stale/tampered evidence, holds, ADS/ADR exclusion, optional manual fields and literal confirmation, historical approvals, real ownership publication on isolated generations, source repair, WFRD and cleanup lifecycle compatibility.

## Live rollout boundary and next phase

**Live rollout: NO.** This task explicitly says: “If no operator gate is already present in this prompt: STOP before live rollout and report the exact safe set.” No approval gate has been satisfied for these new six cases. Backend implementation, tests and copy-only rehearsal are completed; the exact six-case set above is reviewable. Prior YES replies authorize different completed operations, not these decisions.

**Next hobby-mode phase:** explicit operator gate for the exact freshly revalidated six-case policy partition; then bounded guarded live reconciliation and controlled ownership publication. Enabling automatic reconciliation for future normal refreshes should be an explicit rollout choice after that acceptance, while exceptional cases stay in manual/deep review. Do not enable unattended publication, loosen source repairs or broaden queue/UI redesign as an implicit follow-on.
