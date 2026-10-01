# Phase 13G.3.54: TRUG Fiscal-Identity Blocker Locality Audit

Date: 2026-10-01

Audited HEAD: `cb472b40fdeaf78b26c1bdd2f5bb41d789b6f9fe`

Scope: read-only audit of the Refresh fiscal-identity classifier, review partition, and production-safety contract.

## Technical conclusion

`LOCAL_QUARANTINE_SAFE`

The eight changes are real, review-worthy Sharadar MRQ source revisions, but the evidence does not make them global. TRUG can remain on its currently published provider and canonical state while the 18 safe tickers proceed. A copy-only counterfactual completed provider and canonical candidate construction plus one full V2/RP/RV build without publication, identity, structural, or referential-integrity violations.

This conclusion does not accept the revised TRUG history. TRUG must remain held until an operator separately resolves the fiscal revisions.

## Source evidence

TRUG resolves uniquely to company `2212`, security `2222`, Sharadar permaticker `636515`, provider ticker `TRUG`, and company key `SEC_CIK:0001857086`. Both fetched dimensions were complete: ARQ 24 rows and MRQ 23 rows. A targeted live read reproduced the Preview fingerprints exactly (`ARQ` effective `a8ea6f0c...`, `MRQ` effective `5353333f...`) and reproduced zero ARQ and eight MRQ fiscal revisions.

The source key is `(ticker, dimension, date, reportperiod)`. For every row below, `ticker=TRUG`, `dimension=MRQ`, and `date=calendardate=reportperiod`; report period is therefore not distinct. RawCandle reads and validates the provider's literal `fiscalperiod`; it does not derive these labels from calendar dates.

| Provider source key (date/reportperiod) | Old source fiscalperiod / RawCandle identity | New source fiscalperiod / RawCandle identity | Lastupdated old -> new | Financial values changed | Source row changed |
|---|---|---|---|---|---|
| `TRUG/MRQ/2021-12-31/2021-12-31` | `2021-Q4` / 2021 Q4 | `2022-Q3` / 2022 Q3 | `2026-05-20` -> `2026-09-29` | YES: revenue, gp, opinc, ebit, ebitda, netinc, ncfo, fcf, sharesbas, shareswa, shareswadil, netinccmn | YES |
| `TRUG/MRQ/2022-03-31/2022-03-31` | `2022-Q1` / 2022 Q1 | `2022-Q4` / 2022 Q4 | `2026-05-20` -> `2026-09-29` | YES: revenue, gp, opinc, ebit, ebitda, netinc, ncfo, capex, fcf, sharesbas, shareswa, shareswadil, netinccmn | YES |
| `TRUG/MRQ/2022-06-30/2022-06-30` | `2022-Q2` / 2022 Q2 | `2023-Q1` / 2023 Q1 | `2026-05-20` -> `2026-09-29` | YES: revenue, gp, opinc, ebit, ebitda, netinc, ncfo, capex, fcf, sharesbas, shareswa, shareswadil, netinccmn | YES |
| `TRUG/MRQ/2022-09-30/2022-09-30` | `2022-Q3` / 2022 Q3 | `2023-Q2` / 2023 Q2 | `2026-05-20` -> `2026-09-29` | YES: sharesbas, shareswa, shareswadil | YES |
| `TRUG/MRQ/2022-12-31/2022-12-31` | `2022-Q4` / 2022 Q4 | `2023-Q3` / 2023 Q3 | `2026-05-20` -> `2026-09-29` | YES: sharesbas, shareswa, shareswadil | YES |
| `TRUG/MRQ/2023-03-31/2023-03-31` | `2023-Q1` / 2023 Q1 | `2023-Q4` / 2023 Q4 | `2026-05-20` -> `2026-09-29` | YES: sharesbas, shareswa, shareswadil | YES |
| `TRUG/MRQ/2023-06-30/2023-06-30` | `2023-Q2` / 2023 Q2 | `2024-Q1` / 2024 Q1 | `2026-05-20` -> `2026-09-29` | YES: sharesbas, shareswa, shareswadil | YES |
| `TRUG/MRQ/2023-09-30/2023-09-30` | `2023-Q3` / 2023 Q3 | `2024-Q2` / 2024 Q2 | `2026-05-20` -> `2026-09-29` | YES: cashneq, debt, debtc, debtnc, sharesbas, shareswa, shareswadil, receivables, inventory, payables, assets | YES |

The first five target fiscal identities occur once in the fetched MRQ history. The last three also occur on later MRQ source keys, so they correctly remain review-required; that collision is within TRUG and does not create a cross-ticker dependency.

### Root cause

This is Sharadar historical MRQ republication/correction. The provider changed the literal MRQ `fiscalperiod`, `lastupdated`, fingerprints, and financial payloads on stable source keys. RawCandle did not reinterpret unchanged source data, and the identity binding is unchanged. The new MRQ sequence agrees with the already-published ARQ sequence, including 2022 Q4 at report period 2022-03-31, consistent with a March fiscal year end. There is no evidence that a company fiscal-year-end change occurred in this Refresh; ARQ already carried these identities before it.

## ARQ versus MRQ

| Question | Finding |
|---|---|
| ARQ fiscal identity revised in this change? | NO; targeted comparison reproduced zero ARQ fiscal revisions. |
| MRQ fiscal identity revised? | YES; exactly the eight rows above. |
| Does current ARQ agree with new MRQ labels? | YES for all eight report periods. ARQ already maps them to 2022 Q3 through 2024 Q2. |
| Is canonical financial history currently affected? | NO. Canonical/downstream financial values remain ARQ-based and MRQ overlay is intentionally deferred. |
| Could accepting TRUG later alter TRUG output? | YES, subject to operator review; this does not make the present hold global. |

The currently published ARQ source dates are filing dates while their `calendardate` and `reportperiod` identify the quarter. MRQ uses quarter-end dates for all three fields in the affected sample. That dimension difference does not account for the change: the provider's MRQ `fiscalperiod` and financial values themselves changed.

## Classifier path

1. `normalize_source_row()` in `refresh_fundamentals.py:241-270` copies provider `fiscalperiod` and validates it through `fiscal_identity()`.
2. `detect_fiscal_identity_revisions()` at `refresh_fundamentals.py:953-991` joins old and new rows on the stable source key and emits `FISCAL_IDENTITY_REVISION` when parsed fiscal identities differ. Every emitted event receives `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION`; financial payload change is recorded separately.
3. `compare_ticker_histories()` at `refresh_fundamentals.py:1003-1057` returns `classification=REVIEW_REQUIRED` and `review_reason=REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION` when any such event exists.
4. `classify_review_scope()` at `refresh_review_queue.py:138-201` proves only one deliberately narrow local shape. Its local predicate requires `review_reason == AMBIGUOUS_SOURCE_REMOVAL`, oldest-prefix events, and short-window reason codes. A fiscal-identity review cannot satisfy that predicate, so line 176 defaults it to `GLOBAL_BLOCKING_REVIEW`.
5. `partition_changes()` at `refresh_review_queue.py:337-354` places that scope in `global_blockers`. `_load_bound_preview()` at `refresh_copy_runtime.py:162-188` then raises `REFRESH_PREVIEW_HAS_GLOBAL_BLOCKER`; revalidation also rejects it at lines 289-291.

The promotion is a conservative policy/historical implementation limitation, not an invariant demonstrated by the TRUG evidence. The current local-scope function was built specifically for oldest-prefix source-window anomalies and has no fiscal-revision locality branch. Its generated proof already reports known identity, complete ARQ/MRQ, one ticker, zero ARQ affected observations, eight MRQ affected observations, and no cross-ticker or companion conflict. Its false `oldest_prefix_only` and `short_window_is_ticker_local` fields describe an inapplicable anomaly shape, not evidence of global coupling.

One evidence-shape issue must be fixed with the policy: fiscal events contain `old_fiscal_identity` and `current_fiscal_identity`, while the queue collector currently reads only `event.fiscal_identity`. A local fiscal-review item therefore needs an explicit old/current fiscal-identity evidence binding rather than an empty list.

## Locality analysis

### A. Provider scope

YES. All eight stable source keys and both source generations belong only to TRUG. The copy-only replacement of the 18 safe tickers reported `unrelated_state_unchanged=true`, and the TRUG provider semantic fingerprint was identical before and after.

### B. Canonical scope

YES. Holding TRUG leaves its published ARQ-backed canonical rows untouched while other companies rebuild. The counterfactual preserved TRUG's canonical financial semantic fingerprint and reported zero unexplained unaffected-company changes.

### C. Publication-date scope

YES. All 18 published TRUG canonical quarters have non-null `first_public_result_date` evidence (range `2021-10-12` through `2026-08-14`). Its publication-date fingerprint was identical before and after, and the candidate reported `publication_date_repair_required=0`.

### D. Identity scope

YES. The company/security/permaticker/CIK binding is unique and unchanged. The candidate's global identity check reported `company_security_identity_mapping_unchanged=true`, and TRUG's own identity fingerprint was identical.

### E. Downstream scope

YES. Existing semantics rebuild full V2/RP/RV from the preserved canonical generation. The counterfactual reached `READY` with one invocation each of full V2, package, RP, and RV. TRUG's own derived output may change after a later approval, and cross-sectional values can move as the 18 safe tickers update; neither creates an invalid mixed identity or publication state.

### F. Transaction/publication scope

YES. The provider candidate applied only 18 safe ticker histories; the canonical candidate consumed that self-consistent provider generation while preserving TRUG. Provider, canonical, and analysis candidates all passed `PRAGMA quick_check=ok` with zero foreign-key errors. No shared generation contained new TRUG provider data paired with old TRUG canonical data.

## Counterfactual quarantine study

The copy-only audit used the exact Preview safe set: AIR, BB, BTDR, CAG, CALM, CCL, CDT, CELU, CPRT, CTNT, FOXX, IDT, KMX, MLKN, MTN, PAYX, PRGS, and SCHL. Current ARQ/MRQ histories were fetched read-only and each classification matched the bound Preview. All candidates and the compact market-source bundle were created under `/tmp/rawcandle_trug_locality_audit_20261001_v2`; no production publication path was invoked.

Results:

- safe ticker count: 18;
- provider candidate: PASS, unrelated state unchanged;
- canonical candidate: PASS, zero unexplained unaffected changes and zero publication repairs;
- TRUG provider, canonical financial, publication-date, and identity fingerprints: identical before/after;
- full V2/RP/RV/package candidate: `READY`, exactly one invocation each;
- provider/canonical/analysis quick checks: `ok`, zero foreign-key errors;
- production writes reported by harness: 0;
- elapsed time: 699.61 seconds.

The first harness attempt compared regenerated surrogate `quarter_id` and audit timestamps and correctly failed that overly strict equality. Inspection showed no semantic TRUG difference. The final experiment excluded only those expected physical rebuild fields and compared all fiscal, source, publication, identity, and financial content.

## Recommended next phase

Make the smallest dedicated extension to `classify_review_scope()` and queue evidence construction:

1. Add a fiscal-revision locality branch; do not broaden the existing oldest-prefix predicate.
2. Require known unique company/security/provider identity, complete ARQ and MRQ histories, stable source keys, all revision events bound to one ticker, and no cross-ticker or companion identity conflict.
3. For the evidenced MRQ-only shape, require the companion ARQ identity for each report period to agree with the proposed MRQ identity. Fail closed on incomplete history, ARQ conflict, identity ambiguity, or evidence outside one ticker.
4. Persist both old and current fiscal identities plus affected source keys in the Review Queue binding. Preserve the current provider/canonical TRUG state while held.
5. Keep classification and operator semantics review-required. Do not auto-accept fiscal revisions, including duplicate target identities.
6. Add positive TRUG-shaped fixture coverage and negative tests for incomplete, cross-ticker, ARQ-conflicting, and identity-ambiguous evidence. Retain the global blocker for all unproven shapes.

The resulting behavior should enqueue TRUG as ticker-local, let the 18 safe changes proceed, and require a later explicit operator decision.

## Validation

Targeted pytest selection covered literal fiscal-period parsing, fiscal-only and fiscal-plus-financial revision detection, duplicate target identities, independent removal evidence, local/global partition behavior, partition tamper rejection, and production-parity local/global workflow behavior: `13 passed in 16.17s`.

## Safety confirmation

- Source code changed: NO.
- Production financial DBs changed: NO. Pre/post SHA-256 values remained:
  - provider `d296c5454dd701aa91adeb4509b65e4538891bf2c247ad8695c3db79f5ad261f`
  - canonical `9c1c14be2f52165f93d4c9d30aba8bb64fc5489e37190ed9fb672ffa993caaad`
  - analysis `2a5a2d234dbffff69ddc6a24cde640bc1a0dec843bfe998ac16c831504b640a9`
- Operational Review Queue mutated: NO; SHA-256 remained `5ce3c70866aa1c16590e9369d2bd5f4ab18a0cf8a3d036c2efb05d93c6d2e1db`.
- Live workflows executed: NO. Targeted source reads and a copy-only `/tmp` experiment were used.
- Scheduler/systemd state changed: NO.
- Backups deleted: NO.
- TRUG resolved or approved: NO.
- Existing unrelated worktree modification `data/.fundamentals_admin_publication_journal.json` was not altered, reverted, or staged by this audit.
