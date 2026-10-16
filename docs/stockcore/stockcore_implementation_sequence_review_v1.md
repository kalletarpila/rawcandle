# StockCore Implementation V1 — Sequencing and Readiness Review

2026-10-16 · Critical review of the proposed [seven-phase Master Plan](stockcore_implementation_master_plan_v1.md). Planning/document validation only; no future repository, schema, code, provider data, application tests or activation exists as a result of this task.

Sources are the six existing architecture/evidence/readiness/database/question/acceptance documents listed in the plan. Current source package is the locally committed V1 evidence update; legacy call-path observations remain attributed to that static investigation, not new runtime proof. The [phase](stockcore_implementation_phases_v1.csv), [question](stockcore_question_phase_map_v1.csv) and [acceptance](stockcore_implementation_acceptance_map_v1.csv) matrices are execution indexes; they record planned ownership and unexecuted criteria, not completed implementation.

## 1. Review conclusion and phase size

**READY for subsequent explicitly scoped implementation requests, with seven substantial development phases and separate data/pilot/activation gates.** All approved D01–D14 and Q03/Q07/Q15/Q30/Q31 choices are preserved. No architecture-wide contradiction prevents planning. Real shared-ID activation, unsettled reducer/policy semantics, metadata freshness and operational recovery remain explicit prerequisites at their appropriate scopes.

Seven phases balance meaningful commits and failure boundaries:

| Phase | Why this is one coherent slice and how it can be tested independently |
|---|---|
| P01 identity/common contracts | Identity resolution, collection policy, owned source persistence, service receipts and CLI planning form an offline vertical operation. Repository/configuration/job scaffolding is not a separate empty phase. Tests use fixture or separately authorized pinned identity inputs, with real allocation disabled. |
| P02 source/actions | Six-field ingestion, overlap qualification and safe corporate-action replacements share one source writer/evidence/transaction boundary. Splitting them into independent collectors would duplicate infrastructure and undermine replacement tests. Fake transport plus isolated SQLite proves failure/retry before provider access. |
| P03 math/pivots/common Dow | Mathematical readiness, strict pivots, recursive state and the first actual derived publisher/readers form one usable technical service. It is the largest correctness slice (22 primary criteria); internal definition/oracle/replay gates keep it reviewable without unrelated consumers or premature live replay. |
| P04 events/relevance | Divergence and selected patterns share stable confirmed-event/coverage publication; relevance consumes their actual availability and common context. Reviewed rule/catalog gates keep this coherent without statistical utility optimization or legacy relevance history. |
| P05 V3/regime | Selected V3 uses the accepted technical layer and its own causal state history; independent index regime shares math/source/inspection but never becomes a new policy gate. Meaningful final-state and missing-index fixtures exercise the complete slice. |
| P06 research/interfaces | Both research and external contracts consume the same accepted as-of/basis/quality readers and receipts. Scope stays small: on-demand horizons/cohorts/exports and interface fixtures, not a regression platform, simulator or installed financial/DC/EC migration. |
| P07 operations/recovery/browser | Composes already exercised services into one local operating surface and verifies whole-stack correction/restore. Actual data/pilot/activation are separately scoped runs, so this is not a giant unbounded live migration phase. |

Preferred commit boundary is one complete accepted capability per phase. A needed preliminary definition/evidence commit is permissible while dependent implementation is blocked, but it is not phase completion. If later evidence shows a phase cannot be validated/committed safely at this size, split on an actual independently accepted behavior/publication boundary with revised maps; do not manufacture micro-phases from Python files or tables.

## 2. Weaknesses identified and improvements included

| Potential weakness in a naive sequence | Improvement incorporated in the final plan | Residual gate |
|---|---|---|
| All runners built before a final monolithic scheduler | P01 establishes the sole service/intent/lock/receipt boundary; P02–P06 use it. P07 composes rather than replaces those services. | Q23/Q25 contract checks and OPS-01 end-to-end. |
| Pure indicator scaffolding without accepted persistence/readers | P03 includes the first real analysis_ng.db writer/reader and pinned-dependency publication tests, not math alone. | Q08–Q13 definitions precede their code; PUB-02/PUB-03. |
| False V3 dependence on divergence/relevance | P05 hard-depends on P01/P02/P03, matching actual OHLC/facts/history needs. P04 is a separate branch and only final release composition requires both. | Explicit selected-fact contract Q16; no new policy input. |
| Cross-phase owner labels delay prerequisite decisions | Q08 numerical comparison subset is settled before P02 even though math owner is P03. Q16/Q19/Q28 inform common fields before P03 output is sealed; Q24/Q25 boundaries start P01. Earliest relevant phase and primary owner are separate fields. | No backwards implementation prerequisite; detailed contract evidence still required. |
| Publication receipt check followed by an unprotected commit | Plan recommends a shared short acceptance lock for cooperating source commits and derived recheck/local commit, plus receipt-qualified readers and durable invalidation. Compute/fetch happens outside long locks. | Q23 implementation must prove races/crashes, not assume global atomicity. |
| P01 creates a second allocator to support an early pilot | Authoritative allocation is disabled; use accepted pinned IDs and synthetic isolated tests. Unassigned official IDs hold. Non-Sharadar eligibility is supported independently of financial membership. | Real Q01 handoff and issued-ID/stale-candidate protection at G-IDENTITY. |
| Automatic rename/deactivation quietly edits a real identity projection before ownership handoff | P01 authority guard covers mapping/alias/deactivation as well as allocation. P02 tests automatic changes in fixture authority mode; a real prehandoff pilot retains source action evidence and requires an accepted owner projection update or routing hold. Qualified automatic operation remains implemented for actual StockCore authority after handoff. | No second independently mutated identity master or per-action manual approval added. |
| Identity handoff treated as a toggle after tests | P01/P06/P07 produce contract, consumer tests and a concrete handoff/rollback package covering every creation/mapping/mutation/publisher path. Actual legacy bridge installation/exclusion is separately authorized. | No operational StockCore authority until real legacy-writer protection is qualified. |
| Broken V3 wiring silently inherited or V2 chosen as fallback | P05 specifies context/history reader-writer fields, absent/error semantics, prior-day rerun, used thresholds and proposal/final age/reasons before implementation. V3 remains selected; useful V2/V1 contracts are reused within it. | Q16 may surface a genuine material policy choice requiring explicit decision; version is not reopened. |
| Phase accepts new source after failed split or unchanged-action rerun | P02 includes complete replacement qualification, old-history retention, action-version idempotency and atomic source-change receipt. | ACT/SRC fault cases before real provider scope. |
| Huge universal outcomes/relevance histories creep back in | P04 event-owned relevance and P06 on-demand 5/10/20/60 outcomes with bounded justified artifacts. P05 stores only accepted lifecycle/history facts required by actual behavior, not every run's copy. | Q07 current-state retention and Q22 dependency/cost evidence. |
| Metadata UNKNOWN becomes invented freshness or global blocker | P01 source read/fingerprint/observed-at/UNKNOWN is honest. Q05 gates relevant metadata synchronization acceptance; unrelated technical development can continue. Full applicable acceptance cannot be claimed without the needed contract. | Named external maintainer/check-success evidence remains missing. |
| Model/financial preservation question forces an early migration | Q29 owner P07 tracks preservation-in-place/deferred scope; it is not a first-release integration deliverable or disposal permission. | Before later disposal/import, obtain selected owning-domain manifest/evidence. |
| Fake consumer acknowledgment implies live domain integration | P06 StockCore contract fixtures prove producer behavior only; actual installed consumer acknowledgments wait G-CONSUMERS. Existing financial/taxonomy/synthetic methods remain untouched. | CON-01 ownership and CON-02/CON-03 installed binding gates remain real. |
| Tests passing conflated with real source readiness and activation | G-DEV, G-DATA, G-PILOT, G-IDENTITY, G-CONSUMERS, G-ACTIVATE and G-MONITOR record distinct states. Provider acquisition/replay and ownership/cutover never run from default unit tests. | Each later execution needs its explicit scope and actual receipts. |

These improvements change sequencing/mechanisms, not approved formulas or policy. Routine detailed representation choices may be resolved inside phases; a material new policy/ownership decision is surfaced before affected implementation. The current plan does not close any of the 26 open records.

## 3. Question and acceptance coverage

The question map contains **31 unique original IDs with unchanged current source statuses**:

- Five inherited approved decisions: Q03/Q07/Q15/Q30/Q31. They remain identifiable, carry their approved constraints and are not unresolved development tasks.
- Twenty-four detailed-design questions, including Q01/Q16 with completed source investigation but unfinished transition/adapter design. Each has one phase owner, earliest decision boundary, evidence and development/acceptance/activation scope.
- Two targeted-evidence questions: Q05 and Q29. Q05 gates metadata synchronization acceptance; Q29 gates later selected artifact disposal/import/integration only and does not block first-release construction.

No substitute question IDs or new database requirements were invented. Q21's normal horizons are now explicitly 5/10/20/60 from the current request; reference-date/label/maturity/quality details remain legitimately open. Q29 has a real P07 tracking owner rather than a fake optional implementation phase, with its nonblocking deferred boundary preserved.

The acceptance map contains **88 unique existing criteria, each with exactly one primary phase owner**, verbatim criterion text, secondary dependencies, earliest test stage/type, required evidence and final gate:

| Phase | Primary criteria |
|---|---:|
| P01 | 10 |
| P02 | 16 |
| P03 | 22 |
| P04 | 12 |
| P05 | 7 |
| P06 | 8 |
| P07 | 13 |
| Total | 88 |

All future verification statuses are **NOT EXECUTED**. P07 whole-stack secondary checks do not create duplicate primary ownership. Real allocation/financial binding criteria are not falsely passed by a fixture; corresponding final gates explicitly reference actual handoff/consumer acceptance. Deferred SetupMaster/LongMaster consumer contracts can be tested by receiving fixtures without implementing those applications. The historical wording of SCOPE-03 remains attributed to the prior evidence task; analogous task isolation is verified separately rather than rewriting the source criterion.

## 4. Database, recoverability and isolation review

The two approved core roles remain source/identity `osakedata_ng.db` and derived `analysis_ng.db`. The first is created only under later P01 authorization; the second starts with an actual derived writer in P03. P02–P07 extensions belong to the slice that introduces their readers/writers and accepted data. Schema initialization, update from prior owned schema and failure/recovery are tested in those slices; reverse DDL is not assumed a data rollback.

Specialized databases are allowed on evidence, with recognizable legacy root plus `_ng` before `.db`. Conditional Fundamentals/SwingMaster examples are not a creation list. Q16 history-reader projection does not require a separate history DB; Q29 file/model evidence does not require a model DB. No full legacy database or generation-framework transplantation is part of development.

All phases can be developed/tested in owned environments without legacy writes. New filenames alone are insufficient: physical path/alias checks, explicit own roots/configuration, safe fixture stores, disabled network/autostart and scoped provider/job intents are required. A real accepted identity projection must be narrowly read-only and version-pinned or separately approved/sanitized; no application constructors that may ensure legacy schemas are used to “read” it. No second official allocator starts to fill pilot coverage gaps.

Source acceptance and downstream acceptance are separately durable; changed existing values without new dates still invalidate consumers. Owned recovery preserves accepted source/evidence and marks incompatible derived scopes stale for replay. P07 qualifies actual SQLite-consistent/WAL-aware backup practices with Restic where applicable and an isolated restore drill; no permanent every-generation database snapshots or redundant production full copies are introduced.

**Residual operational concern:** G-IDENTITY can require separately authorized engineering in existing legacy allocation/financial-generation adapters. The development phases provide its concrete reviewed contract and fixture/rollback evidence, not a secretly installed bridge. A user-approved handoff scope must identify permitted legacy files/operations and actual writer exclusion before live shared ownership. Until then the system is development-tested or pilot-qualified with allocation disabled; it is not activated shared identity authority.

## 5. First-release and future-extension review

The final plan includes USA identity/universes/metadata, six-field source and corporate-action continuity, shared math/strict pivots/one Dow, four divergences/selected patterns/relevance, both research modes/on-demand outcomes, selected V3 plus independent combined regime, safe publication/invalidation/recovery, scheduler/local browser, and Fundamentals/DC/EC contracts. Nothing required is silently moved into a later model/research project. Held/unqualified data is visible rather than fabricated; accepted pilot scope must be stated accurately.

Deferred capabilities remain deferred: full Fundamentals migration; DC/EC method redesign; OMXH/OMXS activation and initial Xetra; extended macro; EW/dual inference/training; old episode migration; genuine simulator; rich research/chart/Master views; SetupMaster/LongMaster implementation. Reusable security/price/event/clock/fact interfaces support them without a registry/plugin/microservice/workflow framework. No performance target, sample size, deadline or processing-time estimate was invented.

Long-running historical work is restartable by security/qualified segment/processed state and accepted dependency receipts. A bounded pilot is chosen and authorized for useful coverage after isolated invariants pass. Each phase can stop on a named gate, keep prior accepted owned state/receipts, commit its validated capability and resume without disturbing production. A live restore/ownership rollback is separately authorized; newly issued IDs must not be lost or reused by an old snapshot.

## 6. Final validation and execution boundary

This plan's static validation checks the phase DAG and prerequisite order, 31 original question IDs/statuses/approved constraints, 26 open allocations, 88 original acceptance IDs/text/unique owners, phase versus matrix consistency, all D01–D14 and five resolved choices, preserved optional `_ng` storage boundaries, local links and unchanged source/worktrees. It checks the five-file commit boundary and verifies no future StockCore directory was created.

**Artifact validation: PASS.** Seven acyclic phases; all 31 question IDs mapped once with unchanged statuses (five resolved, 24 detailed-design and two evidence); all 88 acceptance IDs/text mapped once to their primary phase and marked NOT EXECUTED. Three new CSVs parse with complete unique records. All 14 local Markdown links resolve; 19 pre-existing document/modified-file hashes and 47 untracked file size/mtime records are unchanged. SwingMaster HEAD/worktree status is unchanged and the future repository remains absent. Future application tests, provider calls, database access and acceptance execution were not performed.

Document validation can pass while implementation questions remain open and all application acceptance remains unexecuted. The readiness conclusion authorizes no implementation or production work by itself. Subsequent prompts can use each phase's capsule after its scope is authorized, carry forward the relevant mapped gates and commit only its own reviewed/tested slice. Operational cutover always requires a separate explicit user decision.

**Production changes initiated by this planning task: 0. NOT PUSHED.** Only the five new requested plan documents belong in the local commit; all previous source documents and unrelated worktree changes are preserved.
