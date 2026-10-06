# Phase 13G.3.77: Form 6-K Result-Publication Authority V1

Date: 2026-10-06 (Europe/Helsinki).
Starting HEAD: `34852538020f441c3dd80be3fa812fbbac78144d`.
Source generation: `publication_drain_20261006T150551Z_9cfd3ca0`.
Mode: explicitly selected, offline, copy-only evaluation and in-memory state simulation.

## Executive Summary

Implemented `FORM_6K_RESULT_PUBLICATION_AUTHORITY_V1` with explicit source
`SEC_FORM_6K_RESULT`, rank **2**, confidence **MEDIUM**. It is not an 8-K alias,
generic fallback, or issuer-release source. Production ranks, schema, domestic
Policy V1, reviewed writer, selector, and default resolver remain unchanged.

The exact [Phase 76 cohort](fundamentals_v4_phase13g3_76_foreign_6k_c8_cases.csv)
reproduces **9 deterministic / 2 acceptance-time REVIEW / 6 multiple-event /
5 wrong-period / 1 temporal-identity and separate issuer-handoff case**. All 23
quarters and 30 relevant parent candidates are frozen: 24 exact-quarter result
filings, five wrong-period packages, and one XBRL-only amendment. The six
multiple-event cases remain unresolved; no chronology shortcut was introduced.

All 11 actual ADR cases were evaluated. One remains held for temporal identity
(IQMX); no depositary-bank filer is accepted. Ten provider security-type conflicts
are retained, not corrected in Production. The 9 deterministic proposals are
ready for **copy-only reviewed-plan integration design**, not live APPLY.

## Contract Review

The bounded inputs were Phase [76](fundamentals_v4_phase13g3_76_foreign_6k_c8_evidence_audit.md),
[72](fundamentals_v4_phase13g3_72_publication_event_policy_v1.md),
[73](fundamentals_v4_phase13g3_73_policy_v1_reviewed_plan_integration.md), current
source/timestamp authority, and immutable-generation/journal safety. No broad
repository scan, new network research, or historical-completeness audit occurred.

Existing reviewed observations already support source hashes, short excerpts,
semantic facts, and fingerprints without an ADR schema migration. They provide
the appropriate explicit reviewed-input boundary, not general-purpose financial
NLP. The new path is isolated in `rawcandle/fundamentals/form6k_authority.py`;
only source-neutral `fingerprint` and event taxonomy are reused from domestic
Policy V1. Its 8-K classifier and reviewed discrepancy override are not reused.

The current SQL publication schema CHECK constraints do not admit the new source,
and the ordinary rank table/writer does not authorize it. These constraints are
intentionally unchanged. This phase simulates authority **in copied Python state**,
not through an incompatible SQL writer. A future schema/adapter change requires
its own explicit copy-only reviewed-plan contract. No schema migration is needed
to finish this phase, and no Production mapping is silently synthesized.

## Authority Contract

The explicit entry point is `evaluate_form6k(..., authority_version=V1)`.
Missing version cannot default into the path; an unsupported version raises.
It has no network client, database connection, writer, scheduler dispatch,
production selector, or automatic acquisition integration.

Candidates bind canonical natural key and quarter ID, reporting CIK, form,
accession, SEC parent URL, primary/result document URLs and original hashes,
short excerpt hashes, linked-exhibit roles, acceptance observations, reviewed
financial facts, and official identity witnesses. `reviewed_binding` covers the
entire candidate. Each result emits the versioned contract/rank/confidence,
retained complete candidates, candidate assessments, identity/acceptance reasons,
relations, exact selected parent/time or NULL, and a decision fingerprint.

Fingerprints are reproducibility/tamper evidence, not signatures or proof that
a reviewer's semantic assertion is true. Regenerating a consistently modified
artifact requires a new review. Missing, stale, cross-accession, or malformed
proof cannot create an authority proposal. Fixture expected outcomes are checked
by the replay harness; they are never evaluator policy inputs. No ticker appears
in production policy logic.

## Source Hierarchy

| Source | Rank | Confidence / scope |
| --- | ---: | --- |
| Exact reliable issuer earnings release | 4 | Existing stronger authority, unchanged |
| SEC Item 2.02 8-K | 3 | Existing HIGH authority, unchanged |
| Explicit `SEC_FORM_6K_RESULT` | 2 | New copy-only reviewed foreign-filer authority, MEDIUM |
| Explicitly reviewed official filing fallback | 2 | Existing behavior unchanged; no arbitrary 6-K authorization |
| Manual review | 1 | Existing behavior unchanged |

Rank 2 is representable without redesigning the existing integer hierarchy.
It deliberately does not confer Item 2.02/HIGH semantics. The original
`SOURCE_RANK` dictionary is not modified. Existing VERIFIED issuer/8-K authority
is preserved by the copy evaluator. Different same-rank timestamps fail closed;
an unsupported/mismatched existing VERIFIED source or identity raises rather than
being replaced. A candidate labeled generic fallback, issuer release, or Item
2.02 cannot enter the 6-K source gate. Default domestic behavior is untouched.

## Timestamp Authority

The authority is the qualifying **parent** 6-K acceptance. V1 requires agreement
between fresh submissions `acceptanceDateTime` and the filing-index Accepted
display interpreted in `America/New_York`. The full-submission acceptance header,
when supplied, must corroborate that display with matching accession/source hash.
Prior reviewed observations are retained separately and must also agree; they
cannot override a conflicting fresh observation. Metadata/index source URLs,
hashes, observed time, accession, timezone, raw display, interpreted UTC, and
available headers are retained.

Invalid/missing inputs, naive dates, uncertain DST wall times, and conflicting
sources leave selection NULL. No blanket four-hour correction, unconditional
preference for a trailing Z, exhibit timestamp, filing date, finance-provider
date, or issuer timestamp substitution is allowed. This is deliberately stricter
than the domestic reviewed-stored-boundary discrepancy rule, which is unchanged.

BABA and BIDU reproduce `REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT`. IQMX's SEC
conflict remains visible independently of its issuer release. NBIS's two result
filings also have preserved acceptance conflicts; its case stays in the
multiple-event partition, with both candidate-level timing holds reported. A
multiple-event label does not erase timing review or make a typed chain eligible.

## Event Eligibility

Automated authority needs reviewed same-entity consolidated reporting perimeter,
explicit fiscal year/quarter and quarter grain, exact period end, completed period,
consolidated revenue/explicit zero or statutory equivalent top line, statutory
consolidated/attributable/explicit continuing-operations income, income-perimeter
witness, and a supporting complete result statement. GAAP, IFRS, and TIFRS are
supported; another statutory framework requires an explicit reference. Preliminary
completed-period results retain a distinct event role and must meet the same
broad statutory minimum. Domestic preliminary/partial eligibility is not changed.

Unknown scope requires REVIEW. H1 and FY packages are WRONG_PERIOD, not inferred
Q2/Q4. Partial, pro forma, guidance, dividend/operational/non-result events cannot
supply authority. Adjusted EBITDA, segment metrics, cash, production volume,
arithmetic reconstruction, or bare period-end equality are not the minimum.

Results may be in the primary 6-K (CAMT/NVMI), one Ex99, or multiple same-accession
documents (PAAS/WPM). Parent context and result proof remain separately bound.
Ex99 is not required. Unrelated linked exhibits are retained but cannot supply
financial proof. One parent accession is one SEC authority candidate; duplicate
candidate IDs or repeated accessions fail closed rather than counting exhibits
as new economic events.

## ADR / Identity Contract

Required reviewed chain:

`security -> canonical underlying company -> consolidated reporting issuer -> SEC CIK -> exact-period result`

The witness binds security ID/company, canonical underlying company/CIK,
official security type, ADR flag, issuer role, reporting perimeter, official
source proof, and time-qualified applicability. Depositary-bank, ADR-program,
other-entity or known different-perimeter filers are rejected. Unknown mappings,
parent/subsidiary attribution, security type, or temporal applicability require
REVIEW. Same name/CIK cannot override a financial-perimeter mismatch. A foreign
listed holding company's consolidated group is not silently replaced with a
standalone operating subsidiary or VIE.

Official reviewed security descriptions win over provider categories; the
comparison still emits a structured conflict. No provider category or canonical
placeholder name alone proves an ADR chain. Ten metadata conflicts remain in
the fixture and results. No Production identity changes were made.

Four existing security rows (MLGO, HOLO, NEGG, SCNI) have NULL `valid_from`.
The initial test run exposed that fixture-input omission. Their official annual
covers confirm the listed security before the target quarter end. The frozen
witness uses that cover's filing date as a **reviewed coverage boundary**, not
an inferred first-listing date: April 1, March 27, April 28, and April 1 respectively.
The original NULL and the official source reference remain in the fixture.
This is a reviewed external witness, not a backfill into canonical identity.

IQMX's current underlying issuer is supported, but its stored/provider security
history predates the actual July 2026 IQM ADS listing. Its temporal witness stays
UNCERTAIN, producing `IDENTITY_TEMPORAL_REVIEW`. The independent exact issuer
release (`2026-08-04T05:00:00Z`) remains a separate issuer-handoff candidate, never
an SEC timestamp repair. Its issuer reviewed handoff is not implemented here.

## Duplicate / Amendment Semantics

Supported explicit relation types:

- `RESULT_TO_SAME_RESULT_REPEAT`
- `RESULT_TO_FINANCIAL_STATEMENT_REPUBLICATION`
- `INITIAL_RESULT_TO_REVISION`
- `RESULT_TO_XBRL_ONLY_SUPPLEMENT`
- `PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT`

Edges bind both complete candidate fingerprints, same canonical entity/period,
reviewed economic-chain assertion, reason, and source proof from both endpoints.
Role compatibility is checked. Chronology validates non-XBRL edges only after
economic-chain proof; it never creates an edge. Equal values, same-day filing,
or a later financial-statement title alone do not resolve anything. Invalid,
orphan, divergent, repeated, or unsupported edges cannot select a first event.

A proven repeat/XBRL-only supplement is retained but excluded as an independent
result. A proven connected, unbranched chain of eligible initial/completion/
revision/republication events can select its first eligible economic result.
Later observations keep their own availability times. An excluded partial initial
event cannot donate its time to an eligible later revision.

Form 6-K/A needs a reviewed economic role: an explicitly reviewed first
substantive result can qualify at its own parent acceptance; content revisions
need the typed revision relationship; technical/XBRL-only roles need relationship
proof and cannot become first publication by acceptance chronology alone.
CLLS's known XBRL-only amendment has a proven supplement edge to its filed
statements. Excluding that non-independent supplement still leaves **two** result
filings unresolved. The other five multiple-event cases have no invented edges.

## Exact Cohort Replay

| Case | Copy-only V1 result | Selected UTC |
| --- | --- | --- |
| MKDW | WRONG_PERIOD | NULL |
| WDH | UNIQUE | 2026-09-08T11:30:46Z |
| CAN | UNIQUE | 2026-09-08T11:20:24Z |
| MLGO | WRONG_PERIOD | NULL |
| HOLO | WRONG_PERIOD | NULL |
| NEGG | UNIQUE | 2026-08-27T20:30:01Z |
| SCNI | WRONG_PERIOD | NULL |
| BABA | REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT | NULL |
| BHP | WRONG_PERIOD | NULL |
| BIDU | REVIEW_ACCEPTANCE_TIMESTAMP_CONFLICT | NULL |
| VNET | UNIQUE | 2026-08-18T10:16:34Z |
| IQMX | IDENTITY_TEMPORAL_REVIEW; separate issuer handoff | NULL |
| TSEM | MULTIPLE_COMPETING_EVENTS | NULL |
| TSM | MULTIPLE_COMPETING_EVENTS | NULL |
| POET | MULTIPLE_COMPETING_EVENTS | NULL |
| GDS | MULTIPLE_COMPETING_EVENTS | NULL |
| PAAS | UNIQUE | 2026-08-12T21:38:01Z |
| NBIS | MULTIPLE_COMPETING_EVENTS; acceptance conflicts retained | NULL |
| BTDR | UNIQUE | 2026-08-10T11:08:07Z |
| CAMT | UNIQUE | 2026-08-10T11:16:13Z |
| WPM | UNIQUE | 2026-08-06T22:47:58Z |
| NVMI | UNIQUE; outside operational 60 days | 2026-08-06T11:30:57Z |
| CLLS | MULTIPLE_COMPETING_EVENTS; outside 60 days | NULL |

Fixture: `tests/fixtures/form6k_authority_v1.json`. Its aggregate fingerprint and
the Phase 76 source CSV SHA-256 bind the exact natural-key set. It contains
normalized reviewed facts, original source hashes, short quotes, all relevant
parents/result exhibits, identity and acceptance observations, known amendment
relation, and expected outcomes. No raw SEC HTML is committed.

Offline reproducible replay:

```sh
venv/bin/python -m analysis.research.form6k_authority_v1_replay \
  --output-csv /tmp/form6k_authority_v1_results.csv
```

The CLI consumes only the explicit frozen fixture and writes an optional research
CSV. It does not load a production writer, perform network requests, prepare an
APPLY plan, or activate a generation. Detailed outcomes are in the
[23-row result CSV](fundamentals_v4_phase13g3_77_form6k_authority_v1_results.csv).

## Safety / Validation

Focused coverage: **110 passed** before final hardening; the final relevant
group passed **240 tests**, including **112 new 6-K tests** plus the existing
domestic event-policy, timestamp/source-authority, and policy-reviewed-plan tests.
No full suite was run and no automatic suite escalation occurred.

```sh
venv/bin/python -m pytest -q \
  tests/test_form6k_authority_v1.py \
  tests/test_publication_event_policy_v1.py \
  tests/test_result_publication_authority.py \
  tests/test_policy_reviewed_publication_plan.py
```

Coverage includes version/source/rank, primary and exhibit support, statutory
minimum, H1/FY exclusions, authoritative parent acceptance and conflicts,
non-authority date substitutions, ADR/provider conflicts, bank/perimeter rejection,
temporal REVIEW, every typed relation, revision without backdating, XBRL/first
substantive amendment roles, invalid/divergent relationships, complete cohort,
retained inputs, copy-only changes, and unchanged ordinary writer/schema behavior.

Read-only Production queries captured all **16,230 authority rows** into copied
test state. Exactly the nine approved natural keys changed to simulated VERIFIED
with the explicit source, exact parent and acceptance time, MEDIUM confidence,
version, and complete decision provenance. All 14 held cohort rows and every
outside-cohort authority remain equal. A repeated simulation is identical.
The simulation does not accept or write financial tables: financial changes **0**.
This is not an inactive-generation SQL rehearsal and not a substitute for the
later reviewed writer/journal rehearsal.

Pre/post complete cohort-state equality and byte hashes verify unchanged provider,
canonical, analysis, active pointer, journal, Review Queue, scheduler configuration,
domestic resolver, event policy, and reviewed-plan source. No live APPLY, Refresh,
retry/drain, scheduler operation, lock/recovery change, source hierarchy switch,
mapping edit, or 60-day horizon change. The pre-existing dirty journal and other
unrelated files are preserved. No runtime fixture builder, captured downloads,
DBs, plans, cache, journal, or logs enter the commit. Nothing is pushed.

## Recommended Next Phase

**13G.3.78: Form 6-K Authority V1 Reviewed Apply Plan Integration, Copy-Only.**
Bind this version, source/rank, full frozen acceptance/identity/event/relation
proof, selected parent/time, source generation state, and reproduced decisions.
Review the narrow explicit source-type storage/adapter changes needed by the
current SQL CHECK constraints, without globally enabling default 6-K acquisition
or weakening domestic Policy V1. Rehearse no-refetch apply, evidence retention,
immutable candidate validation, journal fencing/recovery, and outside-cohort
invariance on copies before proposing any live rollout. BABA/BIDU, the six
unresolved multiple-event cases, and IQMX remain excluded until their respective
generic review requirements are satisfied.
