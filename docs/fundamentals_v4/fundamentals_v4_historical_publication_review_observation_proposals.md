# P1.4 — Source-bound historical publication review observation proposals

Proposal timestamp: `2026-10-09T09:00:48Z`. Baseline HEAD: `3e49c14721d2b25d36e2940d0a5f7c144a1a0d33`. Prior phases: P1.1 `c2499ec7fb7d683759a3c66a67c8c7f54d1e19be`, P1.2 `510648e3e7681c2ffde3f7cfd9ff0f6038235908`, P1.3 `3e49c14721d2b25d36e2940d0a5f7c144a1a0d33`.

**599 keys reconcile to 85 proposed observations and 514 holds.** All 85 proposals use retained official linked result exhibits plus their parent 8-K identity/publication context. They contain 595 short, exactly located source excerpts. The existing Policy V1 can represent these proposed facts without a policy change. No proposal is approved, authoritative, installed or applied.

## Current baseline and reconciliation

Active generation: `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`. The active generation, protected production hashes and provider watermark match P1.3; no normal production advancement occurred. The 599 keys remain open: 368 NOT_FOUND and 231 UNRESOLVED. Already VERIFIED: zero. Every accepted canonical quarter ID, natural key, selected accession, source reference, timestamp and complete evidence fingerprint still agrees with P1.3. No new competing context or durable same-rank conflict exists.

The canonical database passes `quick_check`. All 16,242 authority keys are unique and bind accepted canonical quarters with matching quarter IDs. The census remains 12,890 VERIFIED, 1,882 NOT_FOUND, 842 UNRESOLVED and 628 AMBIGUOUS: 3,352 open, comprising 152 recent and 3,200 historical. Authority logical fingerprint: `41e710eb4dca4418d48e403fde8c70777efa1c02be24cb48e7eb3a6a4ccce577`.

Provider watermark: `2026-10-08`. Latest successful normal Fundamentals production run: `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`, agreed by provider refresh state and completed journal. Provider completion: `2026-10-09T04:27:27Z`. Journal state/step: COMPLETED; activation: ACTIVATED_AND_VERIFIED; postflight: PASSED; journal last update: `2026-10-09T04:37:11Z`; recovery: NOT_REQUIRED.

Review Queue: six RESOLVED rows, 38 audit rows, zero ownership-review rows; no exact publication candidate natural-key binding supplies reviewed event evidence. No queue approval was reused as publication approval. The preexisting modified publication journal and untracked active-generation data and unrelated PE research files were preserved and excluded from the commit.

The baseline was freshly read through SQLite `mode=ro`, `query_only=on` and frozen before proposal generation. Its 599 keys span 144 companies. The ordinary resolver was replayed with every current open quarter for each company, preserving its complete candidate inventory and unresolved-context findings. The prior domestic reviewed Policy V1 and reviewed Form 6-K cohorts have no exact-key intersection with these candidates. No frozen reviewed observation or relation was silently rebound.

## Existing observation contract

The exact semantic model is `rawcandle/fundamentals/publication_event_policy.py`, specifically `evidence_binding`, `_proof_present`, `classify_event` and `evaluate_candidates`, with the source-context gate in `resolve_sec_filings_with_event_policy` in `result_publication.py`. The reviewed input container and exact-evidence handoff are in `admin/policy_reviewed_publication_plan.py`. Domestic examples are `tests/fixtures/publication_event_policy_v1.json`.

The separate retained reviewed Form 6-K example was checked for its explicit issuer/security/temporal identity and reviewed binding structure. It is a different policy, with no eligible source or exact-key intersection here. Its observations, identity dates and financial evidence were not transplanted into domestic cases.

Existing Policy V1 observations require:

| Dimension | Existing fields / requirement |
|---|---|
| Exact evidence identity | `evidence_binding`: fingerprint of company/year/quarter, source type/time, accession, source reference, primary document, form, Item 2.02 status and evidence hash |
| Resolver context | `resolver_context_sha256`: fingerprint of the full retained current `SecFiling`, required by the reviewed wrapper |
| Review reference | Nonempty `review_reference`; here explicitly a reference to this non-authoritative proposal report |
| Source provenance | `documents[]` with exact source reference, raw source hash, nonempty excerpt and excerpt hash; document must be the parent or an allowed same-accession document |
| Event | Existing `event_class`, `actual_vs_preliminary`, `financial_scope` |
| Entity/period | `entity_confidence`, `period_confidence`, exact `period_end`, `period_grain=QUARTER` |
| Financial minimum | Existing `revenue_scope`, `net_result_scope`, `supporting_p_and_l`; the full-results branch also requires `complete_earnings_package` |
| Special cases | Existing continuing-operations / pre-revenue flags; no new alternative semantic rule |
| Competition | Existing typed reviewed relations, exclusions and precedence; no relation invented from chronology |

These proposals use the existing full-period branch only: FULL_PERIOD_RESULTS, ACTUAL, CONSOLIDATED revenue, GAAP_TOTAL net result, a broad supporting profit-and-loss statement, and a complete quarter earnings package. Preliminary, revised, ambiguous repeat and complex perimeter cases are held instead of being forced into that branch. No Policy V1 eligibility, exclusion or precedence code was changed.

Each `documents[]` entry adds an audit locator alongside the existing required fields: original `filing_text` representation, extracted-text SHA-256, zero-based Unicode start/end offsets and supported dimension. These are provenance metadata, not a second observation model. The excerpt is exactly the indicated contiguous substring; no stitched text, invented quotation or inserted ellipsis is represented as source text. Raw source SHA-256 and extracted-text SHA-256 are separately identified.

## Evidence requirements and review method

For every proposal, source facts were inspected independently of the ordinary candidate count:

1. **Entity:** retained parent cover identifies the registrant, and exact archive CIK agrees with the current company/active CIK. The parent identifies the attached release as that registrant's publication. The release title/body and consolidated statement provide reporting context for the same event. Ticker is display metadata only.
2. **Period:** the actual consolidated income/operations statement explicitly contains a quarter, three-month or 13-week heading and the current canonical economic period-end date. Multi-period statements must contain the quarter column as well as any year-to-date column. Annual-only statements are not mapped to Q4 by assumption. No filing-date proximity or nearest-quarter rule is used.
3. **Event:** the parent records publication/attachment of results or earnings material, and its exact linked release supplies actual quarter financial results. An Item 2.02 heading alone never proves the event. References to earlier issued reports, preliminary/revised results and uncertain event scope remain held.
4. **Financial scope:** an actual consolidated income/operations statement supplies aggregate revenue/net sales, GAAP total net income/loss and costs/expenses supporting a broad profit-and-loss package for the quarter. A narrative reference to a statement, a reconciliation, segment revenue, adjusted net income or EPS alone cannot substitute for that statement.
5. **Binding:** exact source accession, 8-K form, primary document, parent URL, timestamp, raw document hash, current evidence hash/fingerprint and full resolver context are pinned. All excerpts are checked against those documents.

The preparation used bounded source-text inspection and conservative proof checks; it does not claim that every hold is ineligible or that no other sufficient evidence could exist. Unclear layout, incomplete retained financial details, unfamiliar period phrasing and ambiguous semantics remain document-review work. The hold CSV's `NO_EXPLICIT...` reasons mean that the required proof was not established by this bundle, not a definitive absence-of-publication finding.

For example, company 22 FY2025 Q1 (Arcosa) has a parent announcing the registrant's earnings release and a linked statement explicitly headed “Three Months Ended March 31, 2025”, with revenues 632.0 million, net income 23.6 million and operating costs. Company 1457 FY2025 Q1 (Motorcar Parts of America) binds the accepted economic quarter ended June 30, 2024 to a source quarter statement showing net sales 169,887,000 and net loss 18,085,000; calendar year is not substituted for fiscal identity. Exact supporting text and locators are in the bundle, not inferred from those example amounts.

All 85 proposed cases lack active-security `valid_from`, as warned by P1.3. No dates were invented. The proposed historical entity confidence is supported by the contemporaneous filing's registrant identity and attached issuer reporting context, rather than current ticker or later identity witnesses. That confidence remains a proposed fact for operator review. Five complex multi-registrant/perimeter cases are explicitly held.

## Classification and hold set

| Classification | Count |
|---|---:|
| PROPOSED_REVIEWED_EVENT_OBSERVATION | 85 |
| PERIOD_SCOPE_REVIEW_REQUIRED | 102 |
| EVENT_SCOPE_REVIEW_REQUIRED | 13 |
| FINANCIAL_SCOPE_REVIEW_REQUIRED | 394 |
| ENTITY_OR_PERIMETER_REVIEW_REQUIRED | 5 |
| SOURCE_BINDING_REVIEW_REQUIRED | 0 |
| COMPETING_EVENT_REVIEW_REQUIRED | 0 |
| ALREADY_VERIFIED | 0 |
| OTHER_HOLD | 0 |
| Total reconciled | 599 |

Every original key receives exactly one classification. The proposal set and hold set are disjoint and their union equals the full starting inventory. Counts are measured, not an approval target.

The 102 period holds comprise 94 cases without a sufficiently explicit bound quarter-end mapping established from retained results content and eight company 685 Dollar Tree cases with explicit source/canonical fiscal-year label differences. For example, canonical FY2025 Q4 ends February 1, 2025, while the source calls it fiscal 2024 Q4. All eight source labels were checked. These require an explicit fiscal identity mapping review; no automatic one-year offset or economic-period rewrite was introduced.

The 13 event holds comprise seven preliminary, revised or previously issued report contexts and six cases whose Item 2.02 material did not establish the publication semantics strongly enough for this proposal. The earlier-report subgroup includes five company 1917 RPM cases whose primary source says the release provides details not included in previously issued reports; no generic first-event or repeat decision is fabricated.

The five entity/perimeter holds are one Carnival dual-registrant combined reporting case (company 420) and four joint CMS Energy / Consumers Energy parent-subsidiary filings (company 504). Source CIK or current-chain compatibility alone does not resolve their combined reporting perimeter.

The 394 financial holds lack an established complete quarter package containing consolidated revenue, GAAP total net result and broad profit-and-loss support in the evidence reviewed for this bundle. Many parent filings refer to an attached earnings release without reproducing its financial statement. Other retained content supplies useful results language but insufficiently explicit quarter/GAAP/aggregate financial scope. These are retained as research holds; policy requirements were not reduced to release existence or one-candidate uniqueness.

## Retained source usage and acquisition boundary

All 599 cases have retained official parent 8-K source content. Among them, 268 also have a retained linked source usable for inspection; 331 have only parent text available through the checked retained-source paths. Source hashes reproduce against the exact retained raw HTML, and `filing_text(raw)` reproduces the bound extracted text. No third-party summaries or general web search were used.

| Proposal quality / source usage | Count |
|---|---:|
| Proposals supported by parent 8-K alone | 0 |
| Proposals using linked result exhibit context | 85 |
| Companies represented in proposals | 32 |
| Proposals with retained source excerpt review | 85 |
| Exact supporting excerpt locators | 595 |
| Proposals using additional already-retained exhibits beyond the resolver's original captured exhibit list | 6 |
| Cases requiring new network acquisition for this proposal set | 0 |
| Cases with required explicit proof not established in this bundle | 514 |

The six additional exhibit witnesses were already retained in the official-source caches and are within the exact parent's accession. They add review evidence without changing the resolver's filing context, acquisition, candidate hash or timestamp. All source hashes and context fingerprints stay separate and pinned.

No new network acquisition was attempted or required to substantiate the 85 proposals. The 514 holds do not establish that new acquisition would necessarily solve them. Some may be resolvable by deeper inspection of retained content; missing linked financial sections may need a later explicitly scoped official-source research/acquisition phase. This phase stops at those holds and does not turn a material research backlog into broad reacquisition. All parent source evidence was available, so population classification and the supported subset could be completed without an acquisition expansion.

## Non-authoritative proposal boundary

The existing reviewed-evidence input format is reused inside `proposed_policy_evidence`: `policy_version`, `cases[]`, current `quarter`, `events[]` containing exact `evidence`, compact `primary_excerpt`, existing `observation`, `acceptance_index_review`, and `relations[]`. No relation or acceptance discrepancy is needed for these cases. No new financial semantic model is introduced.

The targeted existing workflow has an explicit reviewed-evidence reader and immutable production plan format, but no suitable pending-proposal approval container. Its reader treats explicitly supplied root `cases` as reviewed evidence. Therefore this artifact adds a **non-active proposal envelope** around the unchanged observation format, with `status=PROPOSED`, `approved=false`, `operator_approval_required=true` and `runtime_use_permitted=false`. The envelope intentionally lacks root `cases`, `policy_cases`, prepared keys and a plan ID. The current production plan validator rejects it. No plan preparation or authority writer was invoked.

Location: `docs/fundamentals_v4/review_proposals/historical_publication_review_proposal_v1.ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657.json`. It is outside active data, runtime-discovered input locations, fixtures and production plans. Current code uses an explicitly supplied evidence path; adding this docs artifact cannot install observations or change a worker's inputs. All inspected source code and existing reviewed fixtures remain byte-identical to baseline HEAD.

The proposal reference in each observation points to this report's non-authoritative boundary. Semantic labels such as PROVEN exist **within a proposal**, and do not mean an operator approved them. The 85 copy-only Policy V1 previews return UNIQUE when supplied the proposed facts; without proposals, the complete current 599-key scope still returns REVIEW. Holds remain REVIEW even in the copy-only preview. No runtime default, stored authority status or authoritative reviewed input changed.

This is not an apply-ready file. The existing reviewed-plan preparer additionally expects exact durable candidate evidence and reconstructs its own frozen filing context. P1.3 confirmed that these recognized candidates are not yet durable evidence rows. The compact source excerpts here must not be substituted blindly for the full retained resolver context. A later authorized handoff must explicitly address those bindings and approval before any plan could be considered; existence of this bundle does not satisfy that step.

## Deterministic replay and fingerprints

The entire analysis, classification, proposed observation construction, source binding, locator construction and serialization pipeline ran twice over the same frozen current inputs and fixed proposal timestamp. Both runs produced identical classifications, observations, hashes, locators, CSV bytes, bundle bytes and fingerprints. Result: **PASS**.

The separate validation rechecked all 595 excerpt locations against raw source hashes and reproduced extracted text, checked exact accepted natural-key/quarter binding, recomputed evidence hashes/fingerprints, confirmed full resolver context, and executed the unchanged reviewed wrapper over the entire current company scope. Copy-only outcomes: 85 UNIQUE proposals and 514 REVIEW holds; empty-observation control: 599 REVIEW. No ticker authority join or chronology-only quarter assignment is used.

Proposal artifact fingerprint: `ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657`.

The filename uses the existing Policy V1 canonical fingerprint of the JSON payload **excluding** `artifact_fingerprint` and `artifact_fingerprint_contract`. The contract is explicit in the bundle to avoid a self-referential file hash.

Exact bundle file SHA-256: `6ca99cbc6aeb05ec15fd0927a0c008c9f6add54229ed705b0654c81f89891786`.

Classification CSV SHA-256: `96b24b620694bea88203485fd6c7d29c5bddf62fa566d77bafb4117e7b4636ad`.

Proposed-observation CSV SHA-256: `ab6cd037a0c9480f157700a96af26e98d3dcd7c4e262f0c62bba1e7a3ad4d6a2`.

The bundle includes protected artifact hashes, baseline generation/authority fingerprint, source code and reviewed input fingerprints, retained capture/raw document hashes, exact existing-schema observations, per-case current bindings, copy-only previews, all 514 holds and complete reconciliation. Cases and CSV rows are ordered by numeric company ID, fiscal year and fiscal quarter. No complete filing, database copy or temporary capture is committed.

No reusable source code was added or changed. Verification used deterministic review assertions only, as requested; no pytest group was run merely for ceremony. Assertions cover complete reconciliation, schema, source/document/excerpt hashes, exact locator contents, natural-key and current quarter binding, explicit period and financial proof, no competitor suppression, unapproved envelope rejection as a production plan, unchanged source/runtime inputs, byte-identical replay and protected production invariance. Full suite: **not run**.

## Production invariance and next phase

Provider/canonical/analysis financial databases, authority/statuses/timestamps, active-generation pointer, Review Queue and sidecars, publication journal, scheduler configurations, watermark, retry horizon/cap, source code, authoritative reviewed observations and SEC raw evidence are unchanged. All 1,070 original retained company-capture hashes still match P1.2; used raw document and legacy cache hashes match their frozen input values. Original P1.1–P1.3 artifacts remain unchanged. No new SQLite sidecars appeared.

| Protected production artifact | SHA-256 |
|---|---|
| provider | `fda234de30f448fe342fd5fc842ff430575fd6b361146409cf1f8131e17f2981` |
| canonical | `996deb198513b94e22888dbbb11b8139698b68cf98201a5df4d9bb8cd30a1845` |
| analysis | `9da7016ef65571d47b8ae9d2db79f4f42589dc866c1967042fbde8e770db9e8c` |
| pointer | `30c08f22b5b9b2a3cbb07f5183d2946e3ed8b980634d0e54255936b9310b5de3` |
| queue | `84c18a698ef541a355950c91805ba0e949c9dd4d1a1d4d7d991a7bebc5d3e15b` |
| journal | `6f7e625fe10c0ab98c31902bb34d4e7a0c24ea2c94b840497b0459a07817aa67` |
| scheduler | `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894` |
| forecast_scheduler | `67e55b992b6144306b8b96a23157d4879490256c3af1d267f3852da5f1587e79` |

Recommended next phase: explicit operator review of the 85 exact proposed cases and their source excerpts, with approval recorded separately and bound to the proposal fingerprint. Research the 514 holds separately, prioritizing exact fiscal-label mapping, joint-registrant perimeter and repeat/preliminary event questions before any broader acquisition. After any explicit approvals, re-establish current state and design a separately authorized exact-evidence handoff; do not run a drain or treat this bundle as an apply plan.

No observation was installed or approved. No publication plan, authority update, worker invocation, manual drain, financial rebuild, generation activation or push occurred. Only the report, classification CSV, optional proposed-observation CSV and one non-active proposal JSON belong to this commit.

## Deliverables

- Detailed report: `docs/fundamentals_v4/fundamentals_v4_historical_publication_review_observation_proposals.md`
- Classification CSV: `docs/fundamentals_v4/fundamentals_v4_historical_publication_review_observation_classification.csv`
- Proposed-observation CSV: `docs/fundamentals_v4/fundamentals_v4_historical_publication_proposed_reviewed_observations.csv`
- Proposal bundle: `docs/fundamentals_v4/review_proposals/historical_publication_review_proposal_v1.ea28d203681fa6c331ef3ef1741d80908f7520fd1c3924e9703284c313614657.json`
