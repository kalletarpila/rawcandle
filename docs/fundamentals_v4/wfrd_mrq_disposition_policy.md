# WFRD MRQ disposition policy

Date: 2026-10-26. Task: WFRD-MRQ-DISPOSITION-1. Documentation/policy phase only.

## Decision

**`RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE` (A). Confidence: HIGH for this bounded policy.**

Preserve the previously accepted December 31 successor-stock MRQ observation as immutable, separately queryable historical source evidence, explicitly absent from the current provider response and ineligible for financial calculation. Keep the December 13 predecessor residual-flow observation as current provider evidence, with explicit partial-period/accounting-basis context and no authority to supply ordinary full-quarter or canonical values. Do not merge, fill nulls across, or declare equivalence between the records.

“Retain historical source” does **not** mean insert the absent old row into the current-source view or the ordinary history returned by `load_current_history()`. Both observations remain available for investigation, but only the actually returned row belongs to the current response. This is A rather than C: historical availability is not active financial authority.

A bounded implementation is feasible, but current schema/readers/review actions do not implement this meaning safely. The smallest extension is a distinct historical-source store plus exact-source accounting/eligibility context and a reviewed disposition binding. A full multi-segment canonical-quarter model is not required before implementing that separation. No implementation, review approval, or global-blocker change is made here.

This policy resolves the previously unspecified MRQ retention/disposal choice. It does not supersede the separate ARQ conclusion or authorize its runtime application. The next phase may implement MRQ historical retention and ARQ exact-source preservation together, with approval and publication still gated by complete evidence, copies, tests and a new Preview.

## Governing evidence and scope

- [WFRD fiscal-identity evidence review](wfrd_fiscal_identity_review_2026-10-25.md), commit `12e915cf4f908cef276c4d69ee49b1cbc9332607`.
- [WFRD preservation stop report](wfrd_exact_source_fiscal_identity_preservation.md), commit `16696efccb2ab0e21177380d770af32b6c8fcd8b`.
- Exact Preview: `fundamental_reports/admin_runs/20261025T032113Z_refresh_fundamentals_bcfcec765c58/refresh_preview.json`.
- Current source-history contract in `rawcandle/fundamentals/admin/{refresh_fundamentals.py,refresh_review_queue.py,refresh_copy_runtime.py}` and history policy in `rawcandle/fundamentals/schema/sharadar_history_policy.py`.
- Consumer reads followed from these modules' provider tables and the ARQ canonical/TTM/provenance paths, including the existing ARQ/MRQ shares study. No repository-wide content scan was performed.

The unchanged stored parent Scheduler FULL_WORKFLOW is STOPPED at Preview: 84 safe effective changes, 0 local holds, 1 global blocker, Test unauthorized, Production unauthorized. No workflow was run during this phase.

## Exact MRQ event reproduced

A single current WFRD MRQ read-only provider request returned 32 rows and validated as `COMPLETE`, with no validation errors. Its normalized complete-response fingerprints exactly equal those in the October 25 Preview and the preservation stop report:

```text
raw comparison: d8fd585f22669710e25f160ae326e322312d9bbe97a56b79a426ed1d015d9cef
effective:      f64e0a571711993723d7bbba91c4a80f7ff01c0ae0bed842d304d7cb03372edb
```

The API response was kept only under `/tmp`. No provider DB or queue write occurred. “Raw comparison fingerprint” is the Refresh contract's normalized requested-field fingerprint, not a hash of all bytes/fields in the HTTP response.

| Attribute | Previously accepted, now absent | Current observation |
| --- | --- | --- |
| True source key | `(WFRD, MRQ, 2019-12-31, 2019-12-31)` | `(WFRD, MRQ, 2019-12-13, 2019-12-13)` |
| Provider date | 2019-12-31 | 2019-12-13 |
| Report period | 2019-12-31 | 2019-12-13 |
| Calendar date | 2019-12-31 | 2019-12-31 |
| Fiscal label | 2019-Q4 | 2019-Q4 |
| Last updated | 2026-07-22 | 2026-10-22 |
| Normalized row fingerprint | `9940188ff3a36d457cb5c3683156a15e07f31a638258b928fea130a69c00a3c8` | `a133a4f4a8d732975f5fd76be7a5257989926f737d49c48294735c497dcf3c67` |
| 22-field financial fingerprint | `774acaca5472dd641f6c404d2b71168d389ba242bb2c66773b35fd4abf19198c` | `b84a41068c7acd0d6854c0a253c898b18f80a893798797bf2d4c10be2190df3f` |

Accepted observation ID: `15d7195100fac119b2d47a45294860afaa594a73c8032cac2be0dca38eddd3bf`. Its original persisted `content_hash` is `0621f4ddbc93c0ca5f42d40b79ce597a62ef592c0440c3be934708574f508cbf`; this hashes a different acquisition representation from the normalized row fingerprint above. Both must be preserved, not conflated.

Its published company/security IDs are 2368/2379. The individual legacy provider row's `provider_security_id` is null, while the published identity mapping binds WFRD to Sharadar permaticker 635310. A future decision must bind that verified mapping and preserve the legacy null as observed; it must not fabricate a raw per-row identifier.

All non-null fields among the 22 Refresh financial fields are listed below. Every unlisted field is null, including revenue, gross profit, operating income, EBIT, EBITDA, net income, common net income and diluted weighted shares in both records.

| Native field | Accepted Dec. 31 | Current Dec. 13 |
| --- | ---: | ---: |
| ncfo | null | -68,000,000 |
| capex | null | -73,000,000 |
| fcf | null | -141,000,000 |
| cashneq | 800,000,000 | null |
| debt | 2,456,000,000 | null |
| debtc | 92,000,000 | null |
| debtnc | 2,364,000,000 | null |
| sharesbas | 69,999,966 | null |
| shareswa | 69,999,966 | 1,004,000,000 |
| receivables | 1,241,000,000 | null |
| inventory | 972,000,000 | null |
| payables | 585,000,000 | null |
| deferredrev | 0 | null |
| assets | 7,293,000,000 | null |

Using the published histories and current MRQ response in the pure `build_source_history_merge()` function reproduces the exact MRQ event:

- `TRUE_SOURCE_REMOVAL` / `SAME_FISCAL_SOURCE_KEY_REPLACEMENT`.
- Oldest prefix: true; `chronology_coherent=false`.
- Boundary span 28 against required 41; `expected_quarterly_window_covered=false`.
- Published minimum MRQ report period `2019-12-31`; current response range `2018-12-31`–`2026-09-30`.
- Old key absent, current same-fiscal key present, absence proof from the complete 32-row response and its two fingerprints above.

This MRQ-only reproduction kept published ARQ history unchanged to isolate the MRQ predicate; it is not a new full Preview or a substitution for the stored ARQ review. The reproduction confirms that the MRQ event has not changed since the stop report.

### Accounting interpretation and limits

The [10-K accounting policies](https://www.sec.gov/Archives/edgar/data/1603923/000160392320000017/R8.htm) establish predecessor results through December 13, 2019, successor results from December 14, and a successor December 31 balance sheet. The accounting bases are not directly comparable.

The current row's operating cash flow reconciles as `-747m - (-679m) = -68m`; capex as `-250m - (-177m) = -73m`; signed OCF plus capex is `-141m`. The amounts come from the [predecessor cash-flow statement through emergence](https://www.sec.gov/Archives/edgar/data/1603923/000160392320000017/R7.htm) and the [first-nine-month 2019 statement](https://www.sec.gov/Archives/edgar/data/1603923/000160392319000095/wftq3201910-q093019.htm). They support an inferred predecessor residual-flow interval of October 1–December 13. The API row does not itself provide a flow start date or a vendor derivation.

The older row contains successor year-end stocks with null flow fields. Its MRQ debt of $2,456m differs from the original ARQ/filing debt of $2,164m, as the stop report notes. Retaining historical evidence does not certify all its values as authoritative or use them to correct ARQ.

The two rows are economically non-equivalent. The current row is neither a normal full October–December quarter nor proof that the successor stocks were wrong. Its weighted shares must not substitute for successor period-end shares. Provider absence establishes a source-history fact; A preserves that fact without requiring speculation about the vendor's removal rationale.

MRQ `date` equals its report period in these records; it is not evidence that the amounts were publicly filed on December 13 or December 31. The disposition must not manufacture publication authority from that field or use it to alter an ARQ first-public date.

## Current MRQ semantics and bounded consumer inventory

In this architecture MRQ is native provider history retained alongside ARQ. It participates in source acquisition, trust checks, history comparison, candidate construction and review. It is **not current canonical financial authority, an enabled financial overlay, or direct TTM/scoring/valuation input**. The term does not grant each vendor row ordinary full-quarter meaning; WFRD is an explicit counterexample.

The following inventory follows the known Fundamentals provider-table paths. Historical tools are distinguished from the live Refresh path; their existence is not a claim that they execute in every refresh.

| Consumer/path and symbols | Classification | Actual MRQ use and consequence |
| --- | --- | --- |
| `providers/sharadar.py`: `SharadarClient.fundamentals()`, raw observation adapter | Acquisition / evidence | Returns/filter-dimensions native records and their fields. No predecessor/successor interpretation. |
| `schema/production_bootstrap.py`: `ingest_bulk_provider_rows()`, `provider_observed_ranges()`; `schema/phase12c_backfill.py`: staged validation/reconciliation/import | Bootstrap/backfill storage and reporting | Accept both ARQ/MRQ, preserve provider records, count dimensions and ranges. History policy explicitly says absence alone does not authorize deletion. These are not current financial MRQ overlays. |
| `schema/prototype.py`: `insert_sharadar_observation()`, `provider_counts()`, `validate_integrity()` | Storage / diagnostic | Stores both dimensions, counts rows and joins ARQ/MRQ on ticker/reportperiod/fiscal label. No accounting-basis or full-quarter eligibility predicate. `canonicalize_arq()` separately filters ARQ. |
| `admin/refresh_fundamentals.py`: discovery/state, `validate_complete_history()`, `load_current_history()`, `detect_fiscal_identity_revisions()`, `build_source_history_merge()`, `compare_ticker_histories()` | Live comparison / review / orchestration input | MRQ affects discovery, watermark derivation, row/fiscal fingerprints, absence classification, affected-quarter diagnostics, source completeness and global/local partition. `load_current_history()` also returns absent rows retained under existing source-window provenance; its name does not mean an exact current API snapshot. |
| `admin/refresh_review_queue.py`: `classify_review_scope()`, retained/fiscal/removal eligibility and approval matchers | Live review / approval binding | MRQ revisions can be local only with prescribed evidence; removal proofs and both dimensions bind approvals and drift. WFRD's mixed ARQ revision/removal is global. |
| `admin/refresh_copy_runtime.py`: `revalidate_bound_source()`, `replace_provider_histories()`, `validate_provider_candidate()`, unrelated-state and refresh-set fingerprints | Candidate construction / validation | Fetches and validates both dimensions. Deletes replaced ticker's old provider rows and inserts merged history. MRQ rows affect provider candidate keys/counts/fingerprints and acceptance. Canonical reconstruction then filters ARQ. |
| `admin/batch_add_tickers.py`: quarterly coverage checks, `fiscal_sequence_contradictions()`, `incomplete_fiscal_identity_rows()` | Add-ticker plan / review / candidate input | Validates both quarterly dimensions; compares fiscal labels for the same report period. Distinct report periods do not establish accounting equivalence, nor automatically trigger same-period conflict. |
| `sharadar_acceptance.py`: `validate_arq_vs_mrq()`, `build_scorecard()`, `run_paid_acceptance()` | Provider acceptance/research reporting | MRQ contributes counts and same-period/label comparisons of revenue, EBIT, EBITDA, FCF, debt and basic shares. Its provider acceptance “scorecard” is not financial Score V2. FCF/debt/share validations in the normal acceptance runner otherwise receive ARQ. Unmatched periods are skipped, not certified comparable. |
| `schema/operating_working_capital.py`: provider payload backfill and ARQ winner selection | Migration/provider enrichment; canonical ARQ only | Parses endpoint native fields for all provider dimensions in the copy, then filters `s.dimension='ARQ'` for canonical selection. Historical-only evidence must not be indiscriminately included in future backfill inputs. |
| `admin/universe_removal.py`, `admin/remove_tickers.py`; `phase13d1_real_source.py`, `phase13d2_complete.py` | Removal planning / historical rehearsal diagnostics | Count/filter provider observations, including MRQ, or inspect dimension coverage. Generic removal paths also require an explicit future archive-retention policy; immutable historical evidence must not disappear through cascade cleanup. |
| `admin/operation_report.py`, `refresh_copy_runtime.py` report rendering, `admin/refresh_production.py`, Review Queue/UI presentation | Read-only display/reporting | Show ARQ/MRQ counts, retained keys, removals and approval evidence. The production report explicitly states ARQ-based financial values and deferred MRQ overlay. Display may change without a financial calculation changing. |
| `operating_income_v2/rehearsal.py`: database-integrity inventory; `ttm/engine.py`: provider inventory/backlog reports | Diagnostic / orchestration | Provider counts/schemas/file identities include MRQ. The reported CORZ MRQ debt inconsistency is diagnostic; it does not alter canonical debt. No MRQ summation is performed here. |

Negative financial-path checks are equally important:

| Financial consumer | Verified input boundary |
| --- | --- |
| `phase12d._provider_winners()` / `reconcile_canonical()` | SQL `WHERE s.dimension='ARQ'`; same ARQ restriction in prototype canonicalization. |
| `ttm/engine.load_canonical_rows()` / `compute_ttm_rows()` | `v4_quarter` + `v4_quarter_financials`; flows and endpoint stocks are canonical, not native MRQ. |
| `operating_income_v2/rehearsal.calculate()` and `canonical_valuation_source.load_canonical_source()`; `full_rebuild.py` orchestration | Canonical TTM/quarter values, market data, taxonomy and structural context feed Score/Lifecycle/Valuation and RP. Provider DB being a required source does not imply consumption of MRQ financial values. |
| `relative_valuation/source._listing_eligibility()` / RV source assembly | Provider dependency is `sharadar_ticker_metadata` for listing status/dates; monetary inputs come from canonical-based analysis. Changing MRQ does not change listing metadata. |
| `schema/parent_equity.accept_parent_equity()`, `book_value.py`, `admin/pb_ownership_review.py` | Parent equity/P/B source is bound to the exact accepted ARQ shares observation; source table constrains dimension to ARQ and raw payload is checked for ARQ. Ownership review consumes that canonical accepted source, not MRQ `sharesbas` or `shareswa`. |

The [existing shares study](fundamentals_v4_phase13g3_39_sharesbas_arq_mrq_semantics.md) independently documents why MRQ shares are not a same-quarter replacement authority and explicitly authorizes no overlay. Future P/B/share-basis research must opt in to appropriate current/historical views, inspect the accounting context and obtain a new financial-usage policy. Historical availability is not future calculation eligibility.

## Four conceptual layers and the current schema gap

| Layer | Required meaning | Current capability/gap |
| --- | --- | --- |
| Current provider snapshot | Precisely the keys/values returned by one complete response | Response trust records/fingerprints capture this during Refresh; provider DB may also contain retained rows, so an undifferentiated table read is not the exact source snapshot. |
| Previously accepted provider observation | The exact earlier acquisition, with ID, raw payload, native fields, content hashes and identity binding | Stored in `provider_observation` / `sharadar_fundamental_observation` until replacement. Existing content/version identity does not ensure permanent retention under replacement deletes. |
| Canonical interpretation | Explicit ARQ-derived accepted fiscal quarters and financials | Separate canonical DB/provenance; MRQ does not override it. |
| Historical/audit source evidence | Queryable immutable earlier observation, including its later absence and contextual restrictions | Queue audit stores review events/keys/bindings, not a mandatory complete historical financial payload archive. Old generation/backups can contain the row, but are not a permanent query contract across cleanup. |

`replace_provider_histories()` deletes old ticker ARQ/MRQ observations before inserting its approved merged histories; native rows cascade with parent deletion. There is no separate historical-only table in the active provider schema. `provenance_json` can mark source-window retention, but ordinary history readers still return that retained observation. A new archive must be independently durable and excluded by default from current-source/calculation readers; merely adding an ignored JSON flag is insufficient.

## A/B/C decision matrix

The assessments below concern each option with the safeguards its definition requires, not automatic approval under today's tooling.

| Criterion | A: reviewed historical source | B: active removal, audit only | C: both active accounting observations |
| --- | --- | --- | --- |
| Provider snapshot truth | Exact current response; old key explicitly historical/absent | Exact current response | Requires separate current-response membership; otherwise resurrects an absent key |
| Auditability | Full immutable source record, queryable as historical evidence | Depends on audit payload/access; current queue audit is insufficient | Both records available with explicit basis |
| Data loss risk | Low; old source values/provenance retained | Higher if audit is keys/logs only; low only with a full durable source archive | Low storage loss, greater interpretation risk |
| Double counting/null filling | Prohibited; historical row excluded from ordinary calculations | Must annotate/exclude current partial-flow row | Requires all consumers to understand two bases/segments |
| Current canonical financial impact | None with ARQ fixed | None with ARQ fixed | None while MRQ stays noncanonical; active new semantics increase future risk |
| MRQ consumer risk | Bounded view/context migration; explicit history opt-in | Current partial row still needs context; diagnostic coverage changes | Largest consumer change, especially fiscal-label grouping |
| TTM/comparability | No MRQ inputs; historical retention grants no future authority | Same current non-use; audit-only is not evidence of future safety | Requires basis/duration-aware eligibility if activated financially |
| Implementation complexity | Bounded archive + exact review/context + reader separation | Not safely “just delete”; full audit/context required | Architectural active accounting-observation semantics |
| Refresh stability | Archive once; re-prove absence and context, never replay removal as a new loss | Requires durable acknowledged-removal history and context | Requires ongoing membership, segment/basis and precedence rules |
| Current review compatibility | New action/meaning needed | Existing deletion action lacks full audit/context guarantees for WFRD | No existing multi-basis review action |

**A is the smallest safe choice for this task's evidence-retention goal.** It preserves already accepted source evidence without elevating it to active or canonical authority. B can be safe only if its “audit” contains the complete immutable source and is retrievable with the same restrictions; that converges on A's required historical-source facility. B is therefore not selected as an audit-log-only shortcut. C adds active accounting semantics that no current financial consumer needs to resolve this blocker.

No vendor explanation is required merely to retain an old observed fact as historical evidence. Selecting A also makes no claim that the vendor's removal is an error. This supplies a narrow RawCandle policy where the stop report correctly found none previously established.

## Existing retained-history machinery: not reusable as-is

`schema/sharadar_history_policy.py` states `APPEND_ONLY_NO_WINDOW_PRUNING` and `absence_from_later_snapshot_authorizes_deletion=false`. Later Refresh contracts distinguish true removals from window expiry; these mechanisms must be read together, not as either a blanket no-delete rule or a blanket permission to prune.

`RETAINED_OUTSIDE_SOURCE_WINDOW` carries absent aged-out observations into merged provider history. `load_current_history()` returns them with provenance; subsequent Refresh carries them until reappearance. Exact source-key/absence evidence and operator-reviewed bindings already exist for narrowly supported shapes.

However, `ACCEPT_RETAINED_HISTORY` requires a proven local clean oldest prefix with window-compatible reasons, no same-fiscal replacement conflict and no cross-dimension conflict. `build_source_history_merge()` explicitly raises `RETAINED_HISTORY_APPROVAL_TRUE_REMOVAL_BLOCKED` if a retained-history approval is applied to a true removal. WFRD has a same-fiscal replacement, false chronology, an ARQ revision and a mixed global review. Its date being old does not change those facts.

Thus source-window retention supplies useful provenance/binding patterns, but it does not implement A's historical-only meaning or eligibility. Do not relabel this event as age-out or retain the row inside the ordinary merged current-history projection.

## Existing true-removal mechanism: deletion, not equivalence certification

`CONFIRM_TRUE_SOURCE_REMOVAL` authorizes re-evaluation of exactly bound provider removals; on a valid new comparison/candidate it permits absent keys to be omitted from replacement history. It does not publish data at the approval click. Evidence drift invalidates approval. If the removed data were canonical-authoritative, candidate canonical consequences would also have to be inspected.

Its predicate checks complete provider absence, exact identity/evidence, local scope, allowed event set and reasons. It **does not prove financial or accounting equivalence** to any same-fiscal row. `SAME_FISCAL_SOURCE_KEY_REPLACEMENT` is a history-classifier reason, not a warranty that two observations have identical economic content.

WFRD is ineligible because its review is `REVIEW_REQUIRED_FISCAL_IDENTITY_REVISION`, its scope is global, and its event set contains an ARQ revision in addition to the MRQ removal. Only positive local removal shapes enter the relevant queue. The live queue has no WFRD row.

Broadening this action to WFRD would neither preserve the full old observation as historical source nor attach the necessary accounting context. A generic confirmation is therefore insufficient for the selected policy, even though it does not itself require replacement equivalence. No eligibility or existing action was changed.

## Structural-event requirement

**No structural event is required now for A's passive, nonfinancial historical retention and context-tagged current evidence.** Current MRQ financial values do not feed canonical quarters or TTM. A's calculation exclusion and separate historical view make that boundary explicit.

`structural_break.py` already provides economic-event/quarter/TTM regime machinery distinct from issuer/security identity. Published WFRD has no structural-event row. That machinery does not itself describe two financial bases within a single quarter, and a Chapter 11 event must not automatically populate it.

If predecessor residual flows are ever admitted to canonical, TTM or comparable-quarter calculations, a separately reviewed period/accounting-basis and structural/comparability policy becomes a prerequisite. The same is true of any MRQ overlay or archived-stock fallback. This phase grants none of those uses. A can be implemented independently of full multi-segment canonical modeling precisely because it grants evidence availability, not financial usage.

## Canonical impact proof and limits

With ARQ state, metadata, market/taxonomy inputs and other companies fixed, **A, B and C have no direct current canonical financial impact solely from changing MRQ membership**: `_provider_winners()` selects only ARQ, and the downstream financial paths above read canonical state. This is a code-path/input-dependency proof, not a new end-to-end rebuild.

Targeted published reads confirm:

- WFRD has 27 accepted canonical quarters. Their combined quarter/financial-row fingerprint is `fef6762b1057c4ce1bb7f054cb45a080000129e7cf7d8817139330c4a74a40a3`.
- All 315 WFRD rows in `v4_field_provenance` resolve to ARQ observations; all 27 `v4_parent_equity_source` rows are ARQ.
- 2019 Q4: quarter ID 84335, period end 2019-12-31, first-public/source availability 2020-03-16; canonical debt $2,164m rather than the old MRQ $2,456m; canonical flows remain null.
- 2020 Q4: quarter ID 84339, period end 2020-12-31, first-public/source availability 2021-02-19. Its values and source remain independent.

MRQ disposition does not initialize/transplant dates, fix the contradictory ARQ label, replace canonical shares or synthesize cash flows. V2/RP/RV/TTM monetary input values therefore remain fixed for an MRQ-only change. Provider row counts, hashes, review status, source/partition fingerprints and workflow authorization can change; these are real operational effects. Releasing other safe peer changes in a future workflow can also change cross-sectional scores independently. No claim of blanket output/fingerprint invariance is made.

Future ARQ preservation must handle all accepted-source checks, not only fiscal winner grouping: for example `schema/parent_equity.accept_parent_equity()` currently compares raw ARQ fiscal label to the canonical key. A reviewed interpretation must be recognized consistently there without rewriting raw vendor evidence. That is an integration requirement for the already proposed ARQ mechanism, not a new MRQ financial authority.

## Future bounded implementation contract

Proposed action: **`RETAIN_REMOVED_ACCEPTED_MRQ_AS_HISTORICAL_SOURCE`**, with a versioned exact-source disposition artifact. This name and the metadata below are design requirements, not implemented runtime vocabulary.

### Evidence and decision binding

Bind all of the following:

1. Ticker WFRD, provider/dataset, MRQ dimension and exact old/current source keys; old/current labels, dates, reportperiods, calendardates and update dates.
2. Old observation ID, original raw `payload_json`, native row/provenance, persisted content hash, normalized row and financial fingerprints. Copy the full acquisition record, not only selected metrics, before any candidate replacement can delete it.
3. Current row's raw acquisition evidence, normalized/financial fingerprints and exact source key. Record the association as `DISTINCT_ACCOUNTING_OBSERVATION`, never replacement equivalence.
4. Complete-response absence proof: status, row count, source snapshot/run identifier and both response fingerprints. Recompute absence from keys rather than trusting a boolean alone.
5. Published company/security binding and permaticker mapping; canonical fiscal keys and baseline generation/state fingerprint. Preserve legacy missing raw identity fields without inventing them.
6. Authoritative filing accession `0001603923-20-000017`, accounting-boundary evidence and residual-flow derivation references; label the inferred start date as derived, not supplied by the vendor. Do not infer a duration for `shareswa` solely from cash-flow arithmetic.
7. Policy/action version, unique decision/item ID, operator/reviewer identity, timestamp, status and authenticated evidence fingerprint; explicitly linked ARQ preservation item/fingerprint.

### Active versus historical data and consumer visibility

- Keep an immutable historical-source record in a separate table/store published with the generation, outside the default `provider_observation`/native current-history join. It must not depend on a cascading FK to a provider row that replacement deletes. Backups alone are insufficient.
- Preserve the original vendor fields exactly. Record absence and review interpretation in a separate envelope/ledger; absence is relative to the observed snapshot, not a timeless claim.
- Keep the December 13 raw row in the current-response view. Attach source-bound context: predecessor residual-flow evidence, derived partial interval, explicitly nonordinary-quarter, not financial-overlay eligible. Historical old row: successor stocks, historical-only, not calculation eligible.
- Ordinary acquisition comparisons/counts use current response membership; historical evidence is an explicit opt-in view and is never unioned into canonical winner inputs, completeness calculations, watermark derivation, share/P/B selection or ordinary quarter reports.
- Diagnostic/UI readers show current source count, historical count, both bases/roles, absence proof and eligibility separately. Same-fiscal matching must not display them as comparable full-quarter financial observations.
- Existing migration/removal/cleanup paths must respect the historical store's retention and audit contract. Future financial or research consumers must explicitly declare and validate which view they consume; no archived-value fallback is authorized.

### Drift, staleness and future-refresh stability

Pending operator decisions remain bound to the exact published baseline and complete response. Any bound-source/key/label/update/financial/identity/authority/absence-proof drift makes approval stale and keeps/reopens the global review. Missing or incomplete history, reappearance of the old key, a changed contextual row or new conflicting same-period evidence cannot silently consume approval.

After a decision is actually published, historical evidence remains immutable even when later evidence changes. Separate the permanent fact of retention from the currently valid disposition. A future Refresh must re-prove complete current absence and validate the unchanged source-bound accounting context; if not, stop and record the new evidence without deleting or rewriting the archive.

Routine unrelated new quarters should not generate another “loss” of the archived old key: historical-only rows are outside the ordinary active-history absence comparator. New response attestations and approved generation lineage must be appended/linked, not used to overwrite the original decision or turn it into a ticker-wide ignore. Specify and test this published-decision lifecycle explicitly; do not weaken existing approval fingerprints as an incidental shortcut.

### Review representation and ARQ interaction

Use a dedicated global review/artifact record capable of displaying both sub-decisions. Reuse exact queue evidence, audit and stale-reopening patterns, but do not force the existing local-only `upsert_local()` path or broaden the three existing acceptance actions.

Show the old/current keys, non-equivalence, historical/source membership, accounting context, financial fingerprints, canonical consequences, authoritative references and stale status. No generic “approve anyway” action. OPEN, pending approved disposition, rejected/keep-blocked and stale states must have explicit semantics under the established lifecycle.

The ARQ action remains `PRESERVE_ACCEPTED_FISCAL_IDENTITY` for `(WFRD, ARQ, 2020-03-16, 2019-12-31)`, preserving effective canonical 2019 Q4 with provider raw label 2020 Q4. It must not act on MRQ. The MRQ historical disposition does not change an ARQ fiscal label or publish either decision alone.

## Complete WFRD blocker-clearing rule

WFRD may cease being a global blocker only when a **new Preview**, after explicit operator authorization of exact evidence, independently proves all of:

1. The implemented ARQ preservation is valid against its bound source, published state and authoritative evidence, and all canonical consumers honor its effective identity.
2. The implemented MRQ disposition is valid; old evidence is durably retained historical-only; current response and partial-flow interpretation are faithful and consumer exclusions verified.
3. The original mixed event is fully accounted for by those two distinct reviewed meanings. No source-history contradiction, incomplete response, unreviewed removal or other unresolved WFRD event remains.
4. Neither decision is stale; identity/source/financial/evidence/absence bindings revalidate and no accounting-boundary consumer hazard remains.
5. Copy-only rehearsal/tests show both canonical Q4s and their dates survive, provider raw evidence remains unchanged, archive/current views are correct, and unrelated data are unaffected.

Only then may Preview recompute WFRD's classification, safe set, blocker count and Test authorization. The old October 25 authorization cannot be reused. Zero WFRD blockers does not imply zero unrelated blockers, authorize Test execution automatically, or authorize Production. Until this complete chain exists, the current global blocker remains.

## In-memory policy rehearsal

A conceptual data-view rehearsal used actual normalized source records. It created Python dictionaries only, not DBs or queue items, and asserted that the old payload was copied unchanged and the new payload was unchanged. Published MRQ had 27 keys; current source has 32. The following views describe the proposed A semantics:

| View | Rehearsed result |
| --- | --- |
| Current provider snapshot | 32 source keys; Dec. 13 present; removed Dec. 31 key absent |
| Historical-source evidence | 1 selected full old normalized observation, historical-only / successor stocks / calculation-ineligible |
| Explicit combined evidence view | 33 distinct source keys, not 33 active or comparable quarters |
| Null filling / merged hybrid | None |
| Source dates/range | Unchanged; current range remains 2018-12-31–2026-09-30 |
| Response fingerprints | Unchanged; the archive is not inserted into the complete response |
| Consumer difference | Opt-in historical display gains the old record; ordinary source/calculation views cannot gain an old active stock fallback |

The replayed current classifier still says chronology false and expected window false for the original removal. A new reviewed disposition must record these diagnostics as observed, not change them to true or fabricate quarterly coverage. An archived observation must not inflate the current-source boundary span. In a future generation the historical-only key would not be fed back as an active missing key; its current absence would instead be checked by the disposition validator.

The rehearsal establishes feasible separation of evidence views. It does **not** execute or validate an implemented action, storage migration, complete candidate build, or non-blocking Preview. A faithful runtime rehearsal is unavailable without the new semantics; work stops at this documented policy result. With ARQ preservation and every rule above satisfied, non-blocking classification is conceptually possible; current code still blocks and no blocker count was changed.

## Validation and Production invariance

No code/helper changes were necessary. No pytest or full suite was run in this policy phase; the prior phase's 127 passing regressions are not reported as a new run. Validation comprised targeted source/contract reads, one MRQ fetch, pure source-history reproduction, source/financial fingerprints, bounded in-memory view assertions, targeted canonical/provenance reads and documentation whitespace checks.

Active generation remains `refresh_20261022T043408Z_refresh_fundamentals_bb23ca223d59_production_eb6f648d`. SQLite reads used URI `mode=ro` and `PRAGMA query_only=ON`, including the attached provider DB used to verify canonical provenance. Queue reads did not instantiate a queue writer. The provider schema lists no historical-only archive table, and the live Review Queue still has no WFRD item.

The following hashes were captured before work and verified again before commit:

| Authority | SHA-256 |
| --- | --- |
| Active provider DB | `cadd3a90f40e0320558b7a6e4de14deb06c77373b9cf3ed81fbb22d26d69dac8` |
| Active canonical DB | `02a13632b45008734ff6078e4e8ba717778bc261471febae504908f951c66b6b` |
| Active analysis DB | `e984fe99df5a3683e76ad9fe9a3dd5c6f55f87d530ef7ca0a30ac5cbb9436adf` |
| Active manifest | `f07a6022eb747f10dc4211b996ffd4fa52bcc5a3393fcc57f32c4cc931a47401` |
| Review Queue DB | `5864471eb66848b015e537308f2f6ba245c1ff9fa910bdca35744c1519fd6652` |

Production changed NO; Review Queue changed NO; WFRD approved NO; global blocker cleared NO; Preview/Test/Production run NO; first-public dates/watermark/active generation changed NO; Policy V1/resolver/vendor raw evidence changed NO. Only this policy document is committed; provider downloads, DBs, runtime state and unrelated worktree changes are excluded. Nothing is pushed.

## Next implementation phase

Implement the bounded MRQ historical-source/context contract and the already proposed exact-source ARQ preservation as a coordinated reviewed resolution. First prove archive durability, truthful current membership, consumer exclusions and stale lifecycle in focused tests; then integrate canonical interpretation consistently, including parent-equity/P/B accepted-source checks. Rehearse complete WFRD consequences on copies before preparing an exact approval proposal.

No full multi-segment canonical-quarter model is required first. No approval is requested in this phase. After implementation and successful rehearsal, explicit operator authorization and a newly validated Preview remain mandatory.
