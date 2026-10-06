# Phase 13G.3.72: Publication Event Policy V1

Date: 2026-10-06

Baseline HEAD: `87a589da5a1f45a9a67caf355c2dadea95a3f11b`.
Baseline active generation: `publication_drain_20261006T110330Z_2d836e37`.
Scope: versioned policy evaluation and offline copy-only replay. No live apply.

Publication Event Policy V1 defines event eligibility and typed event-stage precedence. It does not change source authority or SEC acceptance timestamp authority.

No generic earliest/latest candidate rule is introduced.

## Contract Review

The existing resolver's metadata and primary-context matching deliberately preserve
preliminary, partial, cover-date and other legacy candidate shapes. `apply_resolution`
still treats different same-rank timestamps as AMBIGUOUS. Recognition coverage is
not proof of broad earnings scope. The existing `SecFiling` does not establish
consolidated versus segment revenue, annual versus quarterly statements, entity
perimeter, or an economic preliminary/completion chain.

Consequently V1 consumes **reviewed, source-bound semantic observations**, including
the approved Phase 71 audit, rather than guessing those facts from filing dates or
whole-document keyword matches. This is a deterministic policy evaluator, not an
autonomous general-purpose financial-document extractor. Review assertions are
explicit inputs with provenance; hashes bind the assertions and excerpts but do
not themselves prove their financial meaning. Missing proof remains REVIEW.

No conflicting production locking, generation, recovery or apply contract needs
changing. No schema migration, default configuration switch, acquisition change,
or production writer integration is included. Existing reviewed plans continue to
reproduce legacy ambiguity, not V1 proposals.

## Implementation

- `rawcandle/fundamentals/publication_event_policy.py`: explicit
  `PUBLICATION_EVENT_POLICY_V1`, all 11 approved event classes, Policy B assessment,
  separate relationship validation and chain precedence, structured provenance.
- `resolve_sec_filings_with_event_policy`: separate explicitly versioned copy-only
  resolver entry point. Both existing resolver functions remain unchanged. The
  returned `legacy_matches` are not filtered or repurposed as writer inputs.
- `tests/fixtures/publication_event_policy_v1.json`: 26 exact natural keys and all
  52 original stored evidence records, normalized primary/exhibit excerpts and
  original document hashes, reviewed dimensions, relation proof, stored acceptance
  boundaries, expected eligibility/outcomes, and 10 reviewed index observations.
- `analysis/research/publication_event_policy_v1_replay.py`: offline replay and
  discrepancy gate, reproducible CSV and optional temporary detailed JSON output.

Fixture SHA-256:
`899ed0f8e5a61f7b8159632c0d5ab74640d6c8805cd69ad75fbaa9e771a54a3e`.
No raw SEC HTML, databases, network cache or runtime journal is committed.

### Evidence and Eligibility

Observations bind natural identity, source, accession, stored timestamp, parent
document and legacy evidence hash. Excerpts have their own SHA-256 plus original
source-document hash; linked excerpts must belong to the same accession. Copy
integration additionally fingerprints the complete frozen `SecFiling` context,
including primary text, sections and exhibits. Changed context with unchanged
accession/timestamp fails closed instead of reusing stale reviewed facts.

Each assessment emits policy version, class, actual/preliminary dimension,
financial scope, entity/period confidence, eligibility and reason, review reason,
observation fingerprint, relationship evidence fingerprint, precedence decision
and selected-first reason. Original candidate evidence is retained separately and
unchanged; no authority table mutation is needed to emit this provenance.

Full packages require complete entity-quarter scope, GAAP net result and broad
supporting P&L, including consolidated revenue/explicit zero or the approved full
pre-revenue operating-expense/net-loss statement. ANRO qualifies by that latter
path without inventing revenue. Preliminary packages require closed-period
consolidated revenue and GAAP net result with broad scope; TE's explicitly labeled
continuing-operations measure remains labeled. Adjusted EBITDA, gross profit,
cash, backlog, distributions and other components do not substitute for GAAP net
result. Unknown financial dimensions remain REVIEW, not NO.

Known other-entity/wrong-period and non-result/pro-forma event units are excluded.
Scope uncertainty, including annual/Q4 and segment/consolidated boundaries, blocks
automatic selection. This is not a global keyword veto: actual results containing
separate merger, pro-forma financing cash or outlook discussion remain eligible.

### Relationships and Precedence

Supported typed edges:

- `PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT`
- `INITIAL_RESULT_TO_CORRECTION_OR_REVISION`
- `RESULT_TO_SAME_RESULT_REPEAT`

Edges require same canonical entity, exact fiscal identity, period end and quarter
grain, SEC Item 2.02 source, reviewed economic-chain evidence, quotations from both
bound observations, and observation fingerprints. Chronology validates an edge;
it cannot create one. Invalid/orphan edges, uncertain scopes or mixed source stages
require review. Divergent/incomparable chains remain ambiguous. Only a connected,
unbranched supported chain of eligible events can establish first publication.

CF's expressly proven supplemental same-results presentation is excluded after
relationship validation as an eligibility rule, not by choosing an earlier date.
Its evidence remains retained. A duplicate label without proof stays REVIEW.

Qualifying initial/preliminary results retain first-public time through completion
or revision; later evidence retains its own availability timestamp. A filtered
initial event cannot donate its timestamp to a qualifying later revision/result.
Independent full/full events remain ambiguous even if one is earlier or later.

## Exact Replay Results

All 52 legacy candidates remain available; legacy result is AMBIGUOUS for all 26
quarters with NULL selected authority timestamps.

| Stage | UNIQUE | AMBIGUOUS | REVIEW |
| --- | ---: | ---: | ---: |
| V1 eligibility, including proven supplemental-repeat exclusion | 19 | 4 | 3 |
| V1 eligibility plus typed precedence | 23 | 0 | 3 |

Event eligibility totals: 28 YES, 20 NO, 4 REVIEW.
There are no unsupported independent full/full deterministic claims.

Exact 23 potentially deterministic cases:
GME, SMCI, MOVE, GOSS, REKR, ANRO, KSCP, TE, CDXS, KLXE, ASTS, BKD, CRC, PLUG,
RDVT, RXT, ARKO, APA, CF, DMLP, PDYN, RGLD, SM.

| Typed precedence case | Proposed first SEC acceptance UTC |
| --- | --- |
| GME | 2026-08-31T10:23:08Z |
| TE | 2026-07-28T10:37:38Z |
| RDVT | 2026-08-05T20:05:42Z |
| RXT | 2026-07-09T12:13:03Z |

Holdouts:

- ABAT: early Q4 gross-profit components excluded; later annual-only package
  remains REVIEW. No annual-minus-nine-month inference.
- OPTT: annual-only initial/revised evidence cannot establish distinct Q4 scope.
  Both events remain REVIEW; the known revision does not fix quarter uncertainty.
- AMR: preliminary GAAP company loss does not prove the disclosed Met-segment
  sales are consolidated total revenue. REVIEW competes with eligible final results.

The committed results CSV has one row per quarter, candidate classes/reasons,
filtered/eligible counts, relation edges and fingerprints, final proposal,
selected accession/time, and clearly labeled **hypothetical** earliest/latest
comparisons. These comparison columns are reporting only, not policy inputs.

## Acceptance Discrepancy Gate

Both accessions for GME, MOVE, ANRO, KLXE and PDYN (10 events) pass
`ACCEPTANCE_SOURCE_DISCREPANCY_REVIEWED`. The fixture preserves stored acceptance,
fresh submissions observation, raw filing-index accepted display, index URL/hash
and existing America/New_York interpretation. The gate recomputes index display
to UTC solely to corroborate the stored boundary. All 10 match stored UTC.

Fresh submissions timestamps remain distinct observations and are never used to
replace authority. A missing corroboration, wrong accession/index context, or
index timestamp mismatch aborts the replay. No feed discrepancy cause is assumed;
normalization/acquisition semantics remain unchanged.

## Validation

Focused tests: **156 passed, 35 reviewed-plan tests deselected**. No full suite.

```sh
venv/bin/python -m pytest -q \
  tests/test_publication_event_policy_v1.py \
  tests/test_sec_result_recognition.py \
  tests/test_result_publication_authority.py \
  tests/test_reviewed_publication_plan.py \
  -k 'not test_reviewed_publication_plan or linked_exhibit_roundtrip or resolver_cannot_be_forced or plan_reproduction_failures or request_drift'
venv/bin/python -m analysis.research.publication_event_policy_v1_replay
```

Coverage includes all original 26/52 cases, existing 22 legacy ambiguities,
pre-revenue and continuing-operations scope, every reviewed exclusion group,
all 10 timestamp discrepancies, revision/repeat/no-backdating semantics,
independent full/full ambiguity, divergent/orphan relationships, cross-entity,
cross-period and mixed-source guards, tampered/stale frozen context, retained
evidence, default legacy apply behavior and reviewed-plan reproduction safety.

Outside-cohort safety: PASS. Isolated test state includes VERIFIED, ordinary unique
SEC results, unresolved context, NOT_FOUND and unrelated contexts. VERIFIED
evaluation is skipped when supplied as existing authority; database dumps,
financial/identity/fiscal state and all input objects remain unchanged. Unresolved
competing context blocks a V1 selection. Existing authority/source/PIT tests pass.
Compile/import validation and `git diff --check`: PASS.

## Production Safety and Next Gate

Seven production file SHA-256 hashes match the captured pre-task baseline:
provider DB, canonical DB, analysis DB, active-generation pointer, publication
journal, Review Queue DB and scheduler configuration. No live workflow, network
request, drain, activation, apply, timer or service operation was run.

Production publication/financial state, active generation, Review Queue and
scheduler state changed: NO. The pre-existing dirty worktree is preserved.
Retry cap, recent horizon, uncapped NEW_THIS_REFRESH and manual drain are untouched.

**Ready for later reviewed-plan integration design, not live rollout.** The 23
deterministic cases are copy-only proposals, not executable apply plans. A later
authorized phase must bind the versioned observations/relations and complete
frozen context into the reviewed-plan contract, preserve every retained evidence
record through the existing safe writer, and independently rehearse that handoff.
The current reviewed-plan loader/writer still uses legacy reproduction and must
not be forced to accept these proposals or to bypass its ambiguity rules.
Any wider/unreviewed cohort also needs proven semantic observations; the 26-case
replay does not validate autonomous extraction or authorize expansion. ABAT,
OPTT and AMR remain explicit scope-review blockers, not retry/selection failures.
