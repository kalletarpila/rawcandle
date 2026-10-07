# Phase 13G.3.81: Form 6-K Holdout Resolution

Date: 2026-10-07 (Europe/Helsinki).
Starting HEAD: `537843e2c0a84f5c7f0b257f7fafe31572d8d07e`.
Active generation: `publication_drain_20261007T093516Z_fd654a20`.
Mode: bounded official-source research and isolated canonical-copy simulation.
No Production APPLY, source edits, identity repair, or workflow execution.

## Executive Summary

Audited **nine holdout quarters**. **Six are newly deterministic research
proposals**: TSEM, TSM, POET, GDS and CLLS through existing Form 6-K V1 typed
relations; IQMX through the existing stronger issuer source. **Three remain
REVIEW**: BABA, BIDU and NBIS because acceptance representations disagree.
Five of six multiple-event cases resolve in the copy; NBIS does not.

`UNIQUE_WITH_GENERIC_RELATION` below means newly reviewed economic-chain evidence
using an **already implemented** generic V1 relation, not a new policy/version.
All original candidates remain in the reviewed inputs. No preliminary candidate
is removed, no earliest/latest shortcut is introduced, and no missing relationship
type was found. IQMX remains held by the SEC-specific evaluator; its independent
issuer proposal is deliberately not relabeled as a successful 6-K decision.

All six proposals passed the existing common apply function on a copied active
canonical DB. Production remains **9 VERIFIED / 14 NOT_FOUND** in the original
23-case cohort. Research labels are not new SQL statuses or live mutations.

Recommended bounded follow-up: fresh reviewed-plan preparation/rehearsal for the
five relationship cases, and a separately reviewed issuer-source handoff for
IQMX. Neither is executed here. The next major branch remains **P/B / Book Value
investigation**, not automatic domestic C8 or NOT_FOUND expansion.

## Contract Review and Current State

Reviewed Phase [77](fundamentals_v4_phase13g3_77_form6k_authority_v1.md),
[78](fundamentals_v4_phase13g3_78_form6k_reviewed_plan_integration.md),
[80](fundamentals_v4_phase13g3_80_live_form6k_reviewed_apply.md), its
[23-row CSV](fundamentals_v4_phase13g3_80_live_form6k_reviewed_apply.csv), the
frozen fixture, and their direct evaluator/schema/common-apply/plan contracts.
No broad repository scan or unrelated contracts were used.

Read-only preflight and postflight agree exactly: active generation, manifest,
provider/canonical/analysis hashes and sizes, full cohort authority/quarter/company/
CIK/security/evidence state, fixture/source hashes, active pointer, journal,
Review Queue and scheduler configuration. All three DBs have `quick_check=ok`
and zero foreign-key errors. Journal is `COMPLETED`; no recovery is pending.

Canonical SHA-256:
`9656dc5523c282b7243390c79913264f7614a99ba951f0b172059d8c16f3e16b`.
Canonical size: 675,102,720 bytes. Fixture SHA-256 remains
`689f3e25f3309a5414af84ff6c58f9563f0eb401be6421400373168e1a418387`.

The 60-day operational scope on October 7 contains 152 open quarters. BABA,
BIDU, TSEM, TSM, POET, GDS, NBIS and IQMX are inside; CLLS is outside. Membership
does not prove evidence validity or forbid separately reviewed exact-key work.
The nine live-applied Phase 80 cases all remain VERIFIED. All fourteen holdouts
remain NOT_FOUND, with no authority timestamp installed.

Hierarchy is unchanged: issuer release rank 4/HIGH, Item 2.02 rank 3/HIGH,
explicit reviewed Form 6-K rank 2/MEDIUM, reviewed filing fallback rank 2,
manual review rank 1. Yahoo remains secondary, not publication authority.

## Acceptance-Time Conflict Review

Fresh SEC submissions, filing indexes and complete submission files were fetched
only for BABA, BIDU, NBIS and IQMX. Index/header bytes for BABA/BIDU/IQMX reproduce
their frozen hashes; current metadata preserves the conflicting instants.

| Case / accession | Fresh submissions Z representation | Index Accepted / header wall time | Existing NY interpretation (UTC) |
| --- | --- | --- | --- |
| BABA `0001104659-26-099220` | 2026-08-21T00:05:09.000Z | 2026-08-20 16:05:09 / 20260820160509 | 2026-08-20T20:05:09Z |
| BIDU `0001193125-26-355431` | 2026-08-19T00:08:11.000Z | 2026-08-18 16:08:11 / 20260818160811 | 2026-08-18T20:08:11Z |
| NBIS `0001104659-26-094568` | 2026-08-12T17:15:23.000Z | 2026-08-12 09:15:23 / 20260812091523 | 2026-08-12T13:15:23Z |
| NBIS `0001104659-26-094844` | 2026-08-13T00:01:08.000Z | 2026-08-12 16:01:08 / 20260812160108 | 2026-08-12T20:01:08Z |
| IQMX `0001193125-26-331538` | 2026-08-04T15:12:58.000Z | 2026-08-04 07:12:58 / 20260804071258 | 2026-08-04T11:12:58Z |

Official evidence links:
[BABA index](https://www.sec.gov/Archives/edgar/data/1577552/000110465926099220/0001104659-26-099220-index.html)
and [header](https://www.sec.gov/Archives/edgar/data/1577552/000110465926099220/0001104659-26-099220.txt);
[BIDU index](https://www.sec.gov/Archives/edgar/data/1329099/000119312526355431/0001193125-26-355431-index.html)
and [header](https://www.sec.gov/Archives/edgar/data/1329099/000119312526355431/0001193125-26-355431.txt).
Metadata is from the same CIKs' official `data.sec.gov/submissions` endpoints.

The [SEC Webmaster FAQ, EDGAR Timestamps](https://www.sec.gov/files/about/webmaster-faq.htm)
directs users to the complete submission header and defines the acceptance date
and acceptance time. Its time definition uses **EST**. The linked
[SEC PDS specification, section 2.1](https://www.sec.gov/files/edgar/pds_dissemination_spec.pdf)
also describes acceptance time in EST; that particular PDF is marked DRAFT.
These support index/header as evidence of the EDGAR acceptance clock, not issuer
release time. The FAQ separately says there is no timestamp for first availability
of filing content on sec.gov; acceptance remains the reviewed filing proxy.

Bounded official documentation review did **not** establish a submissions-JSON
timezone defect/serialization rule, an official precedence rule between conflicting
representations, or an instruction to shift every Z value. The
[SEC API description](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
does not specify a reconciliation rule for this field. Literal EST wording is
not by itself a safe instruction to replace the existing DST-aware NY contract
with fixed UTC-5. No independent SEC confirmation of these specific anomalies
was found. Earlier observations are corroboration, not a fresh-source override.

**Generic operational rule: `REVIEW_WHEN_DISAGREE`**, retaining current V1
exact-agreement requirements. Index plus same-accession header is stronger
corroboration of the original local acceptance record, but is not two independent
clocks or sufficient authorization for a new canonical precedence rule.
Neither BABA nor BIDU is selected. Proposed index/header UTC values in the table
are comparison values, not installed authority timestamps.

The anomaly is not BABA/BIDU-specific: five filings across four reviewed issuers
exhibit the same +4-hour disagreement, including ordinary-share NBIS and ADS
issuers using different filing-agent prefixes. This is bounded evidence of a
cross-issuer pattern, **not** an EDGAR-wide defect claim. Other frozen cases have
zero disagreement, so a blanket shift would damage known-consistent observations.
Any future precedence implementation needs an explicit version and independent
SEC clarification, DST/winter coverage and discordant-field fixtures.

## Multiple-Event Review

All six cases refer to the same reviewed consolidated reporting issuer and
explicit quarter ended June 30, 2026. H1 headings do not supply Q2 by arithmetic.
The source packages contain actual three-month tables. Relations below are
reviewer conclusions from issuer/perimeter, period, complete statements,
publication purpose and content comparison together, not equality of one metric.

### Financial-Statement Republication

**TSEM: `UNIQUE_WITH_GENERIC_RELATION`.**
[August 4 result release](https://www.sec.gov/Archives/edgar/data/928876/000117891326003776/exhibit_99-1.htm)
already includes Tower and subsidiaries' unaudited consolidated GAAP operations.
The [August 17 parent](https://www.sec.gov/Archives/edgar/data/928876/000117891326004158/zk2635857.htm)
explicitly furnishes the same three/six-month interim statements and MD&A, with
[full statements](https://www.sec.gov/Archives/edgar/data/928876/000117891326004158/exhibit_99-1.htm).
Their Q2 rows agree: revenue 460,079; cost 322,307; gross profit 137,772; R&D
23,569; operating profit 90,290; total net profit 90,619; parent-attributable net
90,769 (USD thousands). Expanded notes/MD&A are not another result release or
identified correction. Apply `RESULT_TO_FINANCIAL_STATEMENT_REPUBLICATION` from
`0001178913-26-003776` to `0001178913-26-004158`.
Select first qualifying parent acceptance **2026-08-04T11:04:37Z**.

**POET: `UNIQUE_WITH_GENERIC_RELATION`.**
The [August 13 release](https://www.sec.gov/Archives/edgar/data/1437424/000117184326005485/exh_991.htm)
directs readers to the statements filed on SEDAR+ that day. The
[second parent](https://www.sec.gov/Archives/edgar/data/1437424/000149315226037615/form6-k.htm)
explicitly names that August 13 earnings release and supplies the same
[three/six-month consolidated statements](https://www.sec.gov/Archives/edgar/data/1437424/000149315226037615/ex99-1.htm),
MD&A and officer certifications. Q2 revenue USD569,925, statutory net loss
USD11,338,060 and EPS -0.07 reproduce the same result. The release's mixed
non-IFRS/proforma presentation is not used to disqualify its pre-existing
candidate or substitute an adjusted measure for statutory loss.
Apply `RESULT_TO_FINANCIAL_STATEMENT_REPUBLICATION` from
`0001171843-26-005485` to `0001493152-26-037615`.
Select **2026-08-13T13:01:09Z**; twelve-minute proximity is not the proof.

**GDS: `UNIQUE_WITH_GENERIC_RELATION`.**
The [August 13 release](https://www.sec.gov/Archives/edgar/data/1526125/000110465926095498/tm2621440d1_ex99-1.htm)
and [September interim report](https://www.sec.gov/Archives/edgar/data/1526125/000110465926105234/tm2624826d1_ex99-1.pdf)
are the same GDS consolidated Q2 GAAP result. PDF explanatory notes identify
the HK listing-rule interim-report purpose. Its Q2 highlights/results repeat
the original narrative, comparative periods, DayOne dilution-gain explanation
and statutory figures: revenue RMB3,088.0m; net income RMB837.6m; gross profit
RMB664.2m; tax RMB213.5m; equity-method income RMB959.9m; diluted ADS EPS RMB3.53.
Neither an inferred Q2 from H1 totals nor a newly revised result is selected.
Apply `RESULT_TO_FINANCIAL_STATEMENT_REPUBLICATION` from
`0001104659-26-095498` to `0001104659-26-105234`.
Select **2026-08-13T12:15:43Z**.

### Preliminary to Completion

**TSM: `UNIQUE_WITH_GENERIC_RELATION`.**
The [July 16 TIFRS release](https://www.sec.gov/Archives/edgar/data/1046179/000104617926000451/a2q26e_withguidancexfinal.htm)
explicitly says the Q2 figures are not Board-approved; it retains its existing
eligible `PRELIMINARY_RESULTS` role. The
[reviewed consolidated statements](https://www.sec.gov/Archives/edgar/data/1046179/000104617926000541/a2026q2consolidatedreport-.htm)
include explicit three-month results, the independent review report and Note 2's
August 11 authorization for issuance. Release NT$ millions and statement NT$
thousands reconcile by stated units/rounding: revenue 1,270,381 versus
1,270,380,250; parent net 706,562 versus 706,561,938; EPS 27.25.
Statement total net 706,780,923 is a different perimeter and is **not** equated
to the parent's net income. No H1 subtraction or final-over-preliminary policy.
Apply `PRELIMINARY_RESULT_TO_COMPLETION_OF_SAME_RESULT` from
`0001046179-26-000451` to `0001046179-26-000541`.
Select **2026-07-16T11:45:43Z**, the qualifying preliminary result, not the later
Board approval or final filing.

### Statement First, Release Repeat, Technical Amendment

**CLLS: `UNIQUE_WITH_GENERIC_RELATION`.**
The [first statement package](https://www.sec.gov/Archives/edgar/data/1627281/000119312526338220/clls-ex99_1.htm)
is consolidated Cellectis IFRS/IAS34, Board-approved August 6, and already contains
the complete Q2 result. The
[later release](https://www.sec.gov/Archives/edgar/data/1627281/000117184326005324/exh_991.htm)
reports those interim statements and reproduces their Q2 statutory table:
revenue 5,229; other income 1,675; R&D 24,976; SG&A 5,739; operating loss 23,521;
financial gain 1,727; net loss 21,819 (USD thousands); EPS -0.22.
Apply `RESULT_TO_SAME_RESULT_REPEAT` from `0001193125-26-338220` to
`0001171843-26-005324`; retain the later release as a proven non-independent
repeat, not a deleted candidate. Select **2026-08-06T20:30:05Z**.

The [September 6-K/A](https://www.sec.gov/Archives/edgar/data/1627281/000119312526389336/clls-20260630.htm)
explicitly adds XBRL without revising results. Preserve the existing
`RESULT_TO_XBRL_ONLY_SUPPLEMENT` edge from `0001193125-26-338220` to
`0001193125-26-389336`. All three parents remain in the input. The new two-result
review, not merely excluding the amendment, removes the original blocker.

### Economic Relationship Proven, Time Still Held

**NBIS: `REVIEW_ACCEPTANCE_TIMESTAMP`.**
The [release and shareholder-letter parent](https://www.sec.gov/Archives/edgar/data/1513845/000110465926094568/tm2622968d1_6k.htm)
and [later financial-statement parent](https://www.sec.gov/Archives/edgar/data/1513845/000110465926094844/nbis-20260812x6k.htm)
support financial-statement republication, not an independent AI-segment result:
same consolidated issuer, GAAP three/six-month end, revenue 582.3; cost 133.6;
development 191.0; SG&A 173.9; continuing net loss 190.4 (USD millions), and same
Toloka discontinued-operations treatment. The later document supplies expanded
notes/operating review, rather than an identified financial revision.

The proposed `RESULT_TO_FINANCIAL_STATEMENT_REPUBLICATION` edge is nevertheless
**invalid under unchanged V1** because both endpoints have acceptance conflicts.
The evaluator returns `REVIEW_EVENT_RELATION_OR_DUPLICATE_INPUT` with NULL
selection for this newly supplied edge; original no-edge inputs remain multiple.
Research reports the actual residual blocker as acceptance REVIEW. No timestamp
is installed, no edge is asserted machine-valid, and economic chronology alone
cannot make this case unique.

## IQMX Issuer-Source / Identity Review

**IQMX: `UNIQUE_ISSUER_SOURCE` as a company-event research proposal.**
The [official issuer release](https://investors.iqm.tech/news-releases/news-release-details/iqm-quantum-computers-reports-first-earnings-public-company)
identifies IQM Quantum Computers Plc/Oyj and publishes an explicit release clock:
August 4, 2026, **08:00 EEST**, normalized using Europe/Helsinki to
**2026-08-04T05:00:00Z**. Use this release clock, not the 08:00 EDT conference
call, a search-title date, website modification time, or disputed SEC acceptance.
The release links the complete official
[Q2/H1 financial report](https://ml-eu.globenewswire.com/Resource/Download/4da51a85-c7d3-4032-9fe8-54e2f86ec1d5)
and [statement tables](https://ml-eu.globenewswire.com/Resource/Download/28cdc92d-b343-41e2-af34-9a1ef5fe6f6e).
These explicitly report consolidated Q2 IFRS revenue approximately EUR6.7m
(detailed EUR6.683m) and period loss EUR36.6m, not H1-only or future guidance.

The official report identifies IQM ADS trading beginning **July 2, 2026** and
Helsinki ordinary-share trading July 3. Thus the **quarter end predates** the US
listing but the **August 4 publication postdates** it. The
[July SEC issuer package](https://www.sec.gov/Archives/edgar/data/2113060/000119312526292513/d61136d6k.htm)
supports the existing current security -> IQM -> reporting CIK `0002113060`
mapping. BNY is the depositary, not the operating company; RAAQ is the SPAC
predecessor, not the Q2 operating-financial perimeter. No identity row is repaired
or synthesized. The provider's earlier security history and the SEC temporal
witness remain UNCERTAIN; the 6-K evaluator still returns IDENTITY_TEMPORAL_REVIEW.

**Current authority semantics are company-level.**
`v4_result_publication_authority` has natural key `(company_id, fiscal_year,
fiscal_quarter)` and quarter reference, not a security key. Optional `security_id`
and provider symbol belong to evidence provenance. `first_public_result_date`
is likewise a canonical company-quarter attribute; it is not a guarantee of
tradability or a security-listing eligibility window. The existing common apply
function accepts issuer evidence with `security_id=NULL`. This phase leaves
`first_public_result_date` and all source financial fields untouched.

Consequently a later listing date does not block verified publication evidence
for an earlier operating-company quarter. Company/period/perimeter proof remains
mandatory: company-level does not authorize historical RAAQ prices, security
mapping backfills, depositary filings, or linking unrelated predecessor financials.
The issuer proposal uses **rank 4/HIGH** and no disputed SEC timestamp. This
explains which existing contract applies; it does not weaken the SEC-specific
ADR temporal gate or rewrite the frozen IQMX candidate as valid 6-K evidence.

**Issuer reviewed handoff is still required before live application.**
The SQL/common writer already supports the source, but schema-1/2 reviewed plans
are SEC/domestic modes and schema 3 explicitly authorizes Form 6-K. There is no
reviewed issuer-input dispatch that binds this official release/attachments,
exact company/period, original clock/timezone, authority state and common-apply
result. The copied common writer test is not a reviewed-plan rehearsal or live
authorization. A future generic issuer handoff must retain the existing lock,
journal, immutable plan, source/state fences and higher-authority rules.

## Copy-Only Validation

Runtime evidence is under `/tmp/rawcandle_13g381/`; no downloaded documents,
plans, DB copies or logs are committed. Existing Phase 76 official bytes were
hash-verified before rereading the relevant candidate documents. New economic
proofs bind both candidate fingerprints, exact canonical identity, quarter,
original document hashes, short contextual excerpt hashes and review reasons.
No original candidate/accession is lost. No fixture or authority version changes.

The fresh network helper made 17 attempts: four SEC metadata requests, ten SEC
index/header requests and three failed direct issuer-page attempts (two retries;
three transient timeouts). No 429 was recorded. The official issuer page and
its linked reports were accessible through bounded web reads. Its retained web
observation hash is explicitly a **rendered observation**, not a claimed original
HTML-body fingerprint. This distinction is preserved in the copy issuer payload.

Production source was opened read-only and backed up using SQLite's backup API
to `/tmp/rawcandle_13g381/canonical_simulation_verified.db`. Existing
`evaluate_form6k` and `reviewed_evidence_payload` reproduce the five UNIQUE
decisions; `apply_resolution(..., form6k_reviewed_case=...)` independently replays
their frozen proof. IQMX uses the same common `apply_resolution` with explicit
issuer evidence at its existing rank, not a parallel writer or 6-K alias.

Results: **COPY_ONLY_SIMULATION_PASS**, exactly six changed authority keys,
16,230 authority rows unchanged in total, **16,224 unrelated authorities identical**,
all **14,173 existing evidence rows identical**, six new evidence rows.
All **26 nonpublication tables** (including quarter, financials, identity,
provenance and TTM inputs/values) have identical semantic hashes and row counts.
Every held key is unchanged. Copy `quick_check=ok`, foreign-key errors zero.
Provider/analysis and all Production roles are byte-identical pre/post.

Focused research assertions additionally prove reversed candidate ordering yields
the same five selected times, missing edges do not select a winner, stronger
issuer/Item 2.02 authority remains protected, NBIS's conflicting edge cannot
select, candidate counts are preserved and source hierarchy is unchanged.
No source changes occurred; no pytest/full-suite run was needed or executed.

Reviewed-case artifact SHA-256:
`18f6edef3e6e4826b93d55bb9692d67992796b86d371e3a726e63af1d43f853a`.
Decision artifact SHA-256:
`44aef1301b527b40b713ffd71eb5091b020c9a7a1f92ad457f4474858241f2f7`.
Issuer rendered observation SHA-256:
`a90bf558981f73cfb69306d5098160e6289efb4b55341b2149275914b28ef04e`.
These are reproducibility witnesses, not signatures or authorization to APPLY.
Temporary artifacts must be recaptured/reviewed if absent or stale in a later phase.

## Remaining Holdouts

BABA and BIDU: official acceptance representations still disagree; no documented
safe cross-feed precedence or blanket shift. NBIS: economic republication is
supported, but both parent timestamps remain disputed and its V1 edge is invalid.
Their selected source/accession/timestamp/rank/confidence fields remain empty.

The five untouched wrong-period cases MKDW, MLGO, HOLO, SCNI and BHP remain
evidence gaps. No new searches, status changes or decisions were made for them.
Together with the three unresolved researched keys they are eight still-held
cohort keys **in the copy proposal**, not a reduced live backlog count.

## Recommended Next Phase

1. Preserve acceptance REVIEW; request official SEC clarification before any
   separately versioned acceptance-precedence implementation.
2. A future controlled phase can build a **fresh** V1 plan for the five economic
   relations, bind current authority/generation/evidence, rehearse and obtain
   explicit exact-plan approval. The Phase 80 plan and old 23-case fixture's
   NOT_FOUND witnesses are stale for its nine live VERIFIED keys and must not
   be replayed as a new proposal against current Production.
3. Separately implement/review a generic issuer-source frozen-evidence handoff for
   IQMX; existing SQL support alone is not a live reviewed-plan capability.
4. Stop this branch here. Next major investigation: **P/B / Book Value**.

No Production authority, financial DB, active generation, Review Queue,
scheduler, retry behavior or 60-day horizon changed. No live workflow ran.
Nothing was pushed.
