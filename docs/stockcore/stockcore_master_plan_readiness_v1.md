# StockCore V1 — Master Plan Readiness

2026-10-15 · Readiness assessment only. No implementation Master Plan, full phase schedule, repository, code or database is created.

**Conclusion: READY to prepare a bounded implementation Master Plan with explicit design/evidence gates.** The architecture has coherent owners and settled user choices. Implementation, shared-identity activation and acceptance remain subject to the scoped prerequisites below. Planning readiness does not certify deployed V3 behavior, price histories, restoration or any runtime acceptance.

Sources: updated [architecture specification](stockcore_architecture_spec_v1.md), [question/decision register](stockcore_open_design_questions_v1.csv), unchanged [database responsibilities](stockcore_database_responsibilities_v1.csv), [acceptance checklist](stockcore_architecture_acceptance_v1.md), and [four-question evidence investigation including V2/V3 comparison](stockcore_architecture_evidence_review_v1.md).

## 1. Approved completeness and remaining counts

All D01–D14 requirements remain represented: independent StockCore, shared identity and explicit universes/metadata; Yahoo six-field source with qualified automatic maintenance; common approved math and strict confirmed r3 pivots/one Dow/divergence/patterns; compact relevance; two research modes/on-demand outcomes; selected SwingMaster capability; domain-owned Fundamentals/DC/EC; safe source/derived replay/publication/recovery; one scheduler and local browser UI. Additional specialized databases remain allowed when justified.

Q03/Q07/Q15/Q30/Q31 are **RESOLVED BY APPROVED REQUIREMENT**: Ordinary technical default; compact rebuildable current-state/evidence policy; **V3 selected**; no legacy relevance-history copy/exact classification reproduction; no legacy episode continuation/import as active state, with full new qualified 2018+ V3 replay. V2 comparison does not change V3 selection.

There are **31 traceable records: five resolved user decisions, 26 open questions**. Current open categories are **24 OPEN — DETAIL DESIGN**, **two NEEDS TARGETED EVIDENCE (Q05/Q29)** and **zero OPEN — REQUIRES USER DECISION**. Q01/Q16 source questions have resolved investigation outcomes but remaining contracts are open detail, counted once each rather than artificially closed. Any newly surfaced actual investment-policy choice must be escalated within its design gate; this assessment does not invent approval.

## 2. Evidence findings and planning implications

| Question | Current evidence and status | Consequence for readiness |
|---|---|---|
| Q01 | Allocation/mapping/identity mutation helpers and accepted-generation publisher are identified; OPEN — DETAIL DESIGN. | Enough evidence to define a narrow shared-identity workstream. Activation waits for complete writer exclusion, preserved issued IDs/evidence and stale candidate/projection protection. Financial engines/generation ownership stay external. |
| Q05 | Local Yahoo/inline-label writers and downstream read-only fingerprinting known; external maintainer cadence/as-of/last-success not known; NEEDS TARGETED EVIDENCE. | Plan an external read/freshness contract gate before metadata synchronization acceptance; no false timestamp or StockCore writeback. Does not prevent planning source/math services. |
| Q16 | V2/V3 call, provider/history and guard paths inspected; omitted context, disabled history and shipped projection mismatch verified; OPEN — DETAIL DESIGN. | Enough evidence to plan independent complete V3 adaptation with explicit causal history/facts/age contract. Raw module copying or a single enable_history switch cannot satisfy it. |
| Q29 | Named model/manifest/sidecar/macro/financial bindings known; exact important financial/vintage/user artifact set incomplete; NEEDS TARGETED EVIDENCE. | Preserve in place. Evidence gate applies to later import/disposal/integration; no first-release trained inference or financial migration is needed. |

### V2/V3 consequence for selected V3

The [concise comparison](stockcore_architecture_evidence_review_v1.md#q16) establishes the following useful implementation boundaries:

| Finding | Master Plan constraint |
|---|---|
| Both policies delegate to the same V1 history-dependent helpers; V3 builds on V2. | Selectively reuse scoped invalidation, slow-entry/origin, precedence/history and graph/guard contracts inside **one V3**, not parallel engines. |
| Both daily/range paths disable recent history; evaluator drops ticker/date for both. V2 audit's history=True still uses that evaluator; shipped history reader/schema disagree. | No verified functioning V2 history advantage. Specify actual prior states/reasons/signals/churn inputs, absence/errors and rerun cutoff, then verify through final evaluator rather than wrappers alone. |
| Shared six-state graph/minimum ages are unchanged. V3 adds profiles/phases and MA20/HL entry-gate proposals. | Genuine additions can work through current facts/previous attrs but may be blocked by graph/ages. Test final states and proposed/final attributes/reasons, including V3 override age carryover; do not infer superiority from version. |
| V2 provider default slow-decline threshold3% differs from helper default4.5%; V3 slow drift is fixed3% with MA filter. Several other constructor thresholds are ignored by actual detectors. | Preserve actual effective definitions/configuration, not parameter names. New Ordinary/Wilder/common-Dow inputs require explainable policy-impact evidence, not old-output equality. |
| SP500/NDX global regime is not passed to either inspected policy; stock-local SMA20 regime is separate. | Include approved combined regime in V1 as context/inspection; introduce no unapproved global-regime policy gate. |

## 3. Design gates and true blocking scope

A Master Plan can identify these gates without first implementing algorithms or inventing thresholds. The following contracts must be explicit **before the affected implementation decisions are locked or accepted**; unresolved detail cannot be hidden inside a generic “port legacy code” task.

| Gate group | Existing IDs | What must be settled and when |
|---|---|---|
| Identity/source meaning | Q01/Q02/Q04/Q05/Q06 | Alias/eligible history/source-action evidence and completed sessions before source acceptance; maintainer freshness before classification synchronization acceptance; one-allocator/generation handoff and rollback before shared-allocation activation. |
| Mathematics and common structure | Q08–Q14 | Seed/flat/missing/numerical conventions; coherent retained-low/level/tolerance/init/collision/processed-state rules; divergence matching finalization. Resolve those definitions before their reducers/matchers and acceptance oracles are fixed. Broad r3/common-Dow/Close-BOS/RESET/Ordinary choices are already approved. |
| V3 domain adaptation | Q16/Q17 | Explicit causal history/fact/state-attribute/age/reason contract and actual used settings before V3 integration implementation; combined regime's label/configuration/alignment/unavailable contract before acceptance. Any investment-policy change beyond approved input/delivery correctness requires separate review. |
| Relevance/pattern/research contracts | Q18–Q21/Q26/Q27 | Review relevance thresholds against new common Dow/divergence before implementation; concise context, on-demand horizons/maturity, cohort/user-policy and selected detector definitions before their acceptance. Broad empirical pattern utility need not block basic qualified detector research. |
| Publication/operations/external consumers | Q22–Q25/Q28 | Actual dependency influence/checkpoint invalidation, cross-DB compatible receipt publication, isolated failure/restart/restore and local UI services before operational acceptance. Domain adapters activate only on qualified input/projection contracts. |
| Deferred artifact obligations | Q29 | Exact selected source/model/training/financial/report evidence and restoration obligations before its later disposal/import/integration. Preserve current artifacts meanwhile; no evidence mandate for extra V1 DB or training. |

**No unresolved architecture-wide contradiction blocks Master Plan preparation.** Q05 and Q29 are scoped missing evidence, not permission to fabricate freshness or remove source artifacts. Q01 is an activation blocker; Q16 and common-Dow/relevance definitions block specific implementation/acceptance boundaries. Full live writer inventories, content reconciliation and runtime recovery tests are future separately authorized validation, not actions for this documentation task.

## 4. Main workstream boundaries and dependency constraints

These are functional owners and dependencies, **not implementation phases, tickets, dates or a full schedule**:

- **Identity/universe/metadata:** accepted issuer/security/provider IDs and dated routes, collection membership, current external taxonomy integration and eventual single-allocator handoff. Serves every source/technical consumer while leaving financial coverage and generation ownership outside StockCore initially.
- **Source/actions/quality:** one Yahoo adapter/source writer, six fields, completed-session overlap and qualified automatic split/rename/delisting maintenance. Depends on accepted routes/calendars; exposes qualified basis/segment readers and durable source-change receipts.
- **Shared mathematics/events:** Ordinary primitives, strict confirmed pivots, one full/processed-state common Dow, confirmed consecutive-pair divergence and selected patterns. Depends on qualified sessions/sources and fixed mathematical/availability contracts; source revisions affect real finite/recursive influence.
- **Relevance and simple research:** compact event-owned relevance and explanations, two honest research modes, on-demand maturity/outcomes and study receipts. Relevance requires confirmed event/common-Dow context; outcomes remain separate from decision-time features.
- **Selected V3 and market regime:** preserve useful V2/V1 foundation meanings and V3 additions through explicit facts/history, proposal and guarded result. Depends on shared Ordinary/Wilder/common Dow and accepted prior lifecycle state; combined index regime is a separate context capability, not a newly invented policy gate.
- **Persistence/operations/local browser/recovery:** compatible accepted source/derived publications, coverage/invalidation, locks and per-ticker partial/failure reporting. CLI/scheduler/browser share headless services. Browser does not own math or writes; source success and downstream success remain separate.
- **External interfaces and preservation:** Fundamentals consumes shared identity through controlled ownership change while retaining financial generations; DC/EC consumes accepted technical inputs while retaining domain rules/taxonomy/synthetic methodology. Later macro/model/episode/simulation capabilities stay outside first-release scope, with selected evidence retained safely.

Accepted source publication precedes dependent calculation acceptance, and compatible receipts bound every reader. A source correction must invalidate stateful tails, compact events/relevance and affected V3/domain/cache outputs. A complete V3 rebuild requires its own prior lifecycle history in addition to common Dow processed-state continuation. Independent components can be planned independently once their interface gates are named; no globally atomic multi-database transaction or generic event-sourcing framework is assumed.

## 5. Databases, isolation and acceptance readiness

Approved source/identity role remains `osakedata_ng.db`; approved derived technical role remains `analysis_ng.db`. The matrix's recommendation to co-locate initial V3/regime derived outputs does not make these an exhaustive list. A later specialized counterpart must have evidenced ownership/lifecycle/source/restoration need and recognizable legacy root plus `_ng` before `.db`. Q16 history projection and Q29 model artifacts require contracts, not newly invented databases. No matrix inventory/name was changed in this update.

The acceptance checklist now has **88 future criteria**: the initial 84 plus targeted identity-generation publication, causal history/rerun projection, V3/V2 configuration/global-regime distinction and no-old-relevance-import/current-state properties. It tests mathematical independent expectations, all-component availability/prefix stability, full/increment/restart equality, policy facts/proposal/final result, source revisions, per-ticker failure/crash, cross-DB receipt compatibility/restore and browser-independent operations. These are **NOT EXECUTED**; static artifact validation does not certify runtime acceptance or meaningful investment usefulness.

Planning must preserve existing production systems and unrelated worktrees; never operate against legacy paths by an accidental default or instantiate schema-writing production constructors for read-only validation. Provider collection, migrations, technical replay, training/backtests and cutover require their own later authorized scope. No such work happened here. The future `/home/kalle/projects/stockcore` remains absent.

**Readiness result:** the next Master Plan can safely specify independent workstream ownership, interface/definition gates and validation dependencies using the approved V3/Ordinary/new-replay/current-state choices. It must carry the 26 open records with their real scopes and obtain missing evidence at the named boundaries. This document supplies neither the Master Plan nor a phase schedule.
