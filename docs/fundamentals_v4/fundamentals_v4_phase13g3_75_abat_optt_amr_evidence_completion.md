# Phase 13G.3.75: ABAT / OPTT / AMR Evidence Completion

Date: 2026-10-06 (Europe/Helsinki).
Starting HEAD: `d7fbd1b171d7972d620f5729dd7530c3f437daa3`.
Scope: bounded official-source research and network-free, read-only Policy V1 replay.
No source changes, live plan, Production APPLY or full suite.

## Executive Summary

| Case | Original blocker | Additional evidence | Existing Policy V1 result | Selected UTC | Production follow-up |
| --- | --- | --- | --- | --- | --- |
| ABAT FY2026 Q4 | Direct Q4 GAAP net result missing; later package annual | Target 10-K Q4 highlights and all 13 linked presentation slides reviewed; no direct Q4 net result found | POLICY_V1_REVIEW | NULL | Not justified |
| OPTT FY2026 Q4 | Initial/revised financial tables annual, not distinct Q4 | Target 10-K and issuer initial/revised releases confirm annual numeric scope | POLICY_V1_REVIEW | NULL | Not justified |
| AMR FY2026 Q2 | Preliminary coal/Met revenue not proven exhaustive | Target 10-Q explicitly discloses additional other revenues and consolidated total; preliminary revenue is not exhaustive | POLICY_V1_REVIEW | NULL | Not justified under unchanged V1 |

Newly deterministic quarters: **0**. New qualifying publication events found: **0**
within the bounded windows. New corroborating/counter-evidence is not a new event.
Retain all three REVIEW holdouts and move on to broader C8 / NOT_FOUND work.

## Contract and Current State

Review was limited to the Phase 71/72/74 contracts, the three fixture cases, the
existing Policy V1 evaluator/replay, active-generation binding and publication
state. No broad repository scan, universe crawl or policy redesign occurred.

Read-only production verification found active generation
`publication_drain_20261006T150551Z_9cfd3ca0`, matching Phase 74 postflight.
All seven production hashes (provider/canonical/analysis, active pointer, journal,
Review Queue and scheduler configuration) matched that postflight. This also
establishes that unrelated publication rows had not changed since Phase 74.
Journal COMPLETED, terminal/clean; no recovery pending.

Exact keys: ABAT `(9, 2026, Q4)`, OPTT `(2527, 2026, Q4)`,
AMR `(145, 2026, Q2)`. Each authority remained AMBIGUOUS with NULL timestamp;
all six original candidate records and complete authority/identity rows matched
the original reviewed fixture. Each is inside the current 60-day selector as of
2026-10-06. Recent-open remains 171: UNRESOLVED 20, NOT_FOUND 148, AMBIGUOUS 3.
Recent membership was recorded only for operations, never used for eligibility.

Policy B still requires quarter-specific consolidated revenue and GAAP net
income/loss with supporting earnings context, or its existing explicit exceptions.
An annual package does not establish Q4 by matching its period end. A single
reportable segment does not establish exhaustive company revenue.
Issuer material and filed statements below corroborate scope only; no issuer
timestamp, 10-K/10-Q acceptance or presentation date replaces SEC parent authority.

## Evidence Review

### ABAT

Target: quarter ended June 30, 2026, FY2026 Q4.

The August 20 preliminary event, `0001493152-26-039500`, retains stored SEC UTC
`2026-08-20T21:00:28Z`. Its direct Q4 numbers are revenue $8.2m, cost of goods
sold $6.9m and gross profit $1.3m, not GAAP net income/loss. The issuer's matching
release does not add that missing measure. Event eligibility remains NO for
INSUFFICIENT_BROAD_EARNINGS_MINIMUM. [SEC preliminary exhibit](https://www.sec.gov/Archives/edgar/data/1576873/000149315226039500/ex99-1.htm),
[issuer preliminary release](https://americanbatterytechnology.com/press-release/american-battery-technology-company-announces-highest-ever-gross-profit-and-successful-appeal-for-reinstatement-of-57-million-us-department-of-energy-grant-in-fourth-quarter-fy2026-financial-results/).

The September event, `0001493152-26-042948`, retains stored SEC UTC
`2026-09-16T21:05:56Z`. The parent describes a September 14 annual earnings call,
presentation and release. Exhibit 99.2 supplies annual statements; it does not
report a separate qualifying Q4 result. The matching issuer release is likewise
annual. The September 14 release day is not substituted for SEC acceptance.
[SEC annual parent](https://www.sec.gov/Archives/edgar/data/1576873/000149315226042948/form8-k.htm),
[SEC annual release](https://www.sec.gov/Archives/edgar/data/1576873/000149315226042948/ex99-2.htm),
[issuer annual release](https://americanbatterytechnology.com/press-release/american-battery-technology-company-reports-fy-26-financial-results-delivering-407-revenue-growth-and-positive-adjusted-gross-profit/).

Exhibit 99.1 is image-only. All 13 same-accession images were downloaded and
visually inspected, not dismissed because the text extractor returned only a
heading. Slides 1/3 establish the annual presentation; financial slides 5/10
provide FY summaries and no Q4 GAAP net result. Other slides do not add one.
[Linked SEC presentation](https://www.sec.gov/Archives/edgar/data/1576873/000149315226042948/ex99-1.htm).

The exact-period 10-K, `0001493152-26-042497`, has direct Q4 revenue/cost/gross
margin highlights, followed separately by annual results. The Q4 section still
does not provide GAAP net income/loss. No qualifying Q4 package was established
by this additional review. No FY-minus-9M or other reconstruction was used.
[Target 10-K](https://www.sec.gov/Archives/edgar/data/1576873/000149315226042497/form10-k.htm).

Conclusion: POLICY_V1_REVIEW, NULL. Exact remaining gap: a direct, source-supported
Q4 consolidated revenue + GAAP net-result earnings package for an authorized event.
The annual candidate remains REVIEW; it was not discarded to manufacture uniqueness.

### OPTT

Target: quarter ended April 30, 2026, FY2026 Q4.

Initial accession `0001493152-26-034425`, stored SEC UTC
`2026-07-23T20:56:00Z`, announces Q4/full-year results, but Exhibit 99.2's P&L
columns are fiscal years: FY2026 revenue $4.076m and net loss $44.824m. The issuer
version does not supply separate Q4 numbers. The same-parent Exhibit 99.1 is an
asset-acquisition announcement, not a separate earnings package.
[SEC initial earnings exhibit](https://www.sec.gov/Archives/edgar/data/1378140/000149315226034425/ex99-2.htm),
[issuer initial release](https://investors.oceanpowertechnologies.com/news-releases/news-release-details/ocean-power-technologies-announces-fourth-quarter-and-full-1).

Revised accession `0001493152-26-039793`, stored SEC UTC
`2026-08-24T13:00:14Z`, explicitly updates the July 23 preliminary figures after
additional audit procedures. Its numeric revisions and statements concern FY2026,
also adjusting prior FY2025 net loss; no direct distinct Q4 package is supplied.
The issuer version corroborates that annual scope. The parent mentions quarter/FY,
so the document has mixed announcement terminology, but the proven correction
perimeter is annual, not a proven Q4 result correction.
[SEC revision](https://www.sec.gov/Archives/edgar/data/1378140/000149315226039793/ex99-1.htm),
[issuer revision](https://investors.oceanpowertechnologies.com/news-releases/news-release-details/ocean-power-technologies-provides-update-previously-announced).

The revision's quoted earlier FY loss ($43.7m) differs from the initial table
($44.824m). This discrepancy is preserved, not reconciled by assumption. It does
not prove a Q4 amount or justify changing first-publication time. The exact-period
10-K also has annual P&L columns, not a direct Q4 revenue/net-result package.
[Target 10-K](https://www.sec.gov/Archives/edgar/data/1378140/000149315226039261/form10-k.htm).

Conclusion: POLICY_V1_REVIEW, NULL. Exact remaining gap: direct Q4 revenue and
GAAP net income/loss in an identified qualifying result event. Both annual candidates
remain REVIEW. No subtraction, generic chronology, timestamp reset or unsupported
quarter-grain INITIAL_RESULT_TO_CORRECTION_OR_REVISION edge was introduced.

### AMR

Target: quarter ended June 30, 2026, FY2026 Q2.

Preliminary accession `0001704715-26-000025`, stored SEC UTC
`2026-07-27T12:02:06Z`, provides company GAAP loss and coal/Met revenue.
Its company-and-subsidiaries financial schedules corroborate coal revenue, not
exhaustive consolidated total revenue. The issuer version adds no separate other-
revenue or consolidated total-revenue measure.
[SEC preliminary exhibit](https://www.sec.gov/Archives/edgar/data/1704715/000170471526000025/a072726preliminarypressrel.htm),
[issuer preliminary release](https://alphametresources.com/news_articles/alpha-announces-preliminary-financial-results-for-second-quarter-2026/).

The exact target-period 10-Q, `0001704715-26-000031`, explicitly reports Q2 coal
revenue $491.505m, other revenue $1.351m and total revenue $492.856m in consolidated
statements. Note 15 states there is one reportable segment, Met, while MD&A also
identifies other revenue activities. Thus one segment does **not** make the
preliminary coal revenue equal total company revenue. These are directly reported
values, not inferred arithmetic or financial-database reconstructions.
[Target 10-Q, consolidated P&L / Note 15 / MD&A](https://www.sec.gov/Archives/edgar/data/1704715/000170471526000031/amr-20260630.htm).

The full event, `0001704715-26-000030`, stored SEC UTC
`2026-08-07T11:32:23Z`, contains the qualifying consolidated quarter package,
including other revenues and total revenue. It remains YES. The same-day Item 7.01
investor presentation is contextual investor material, not a newly admitted Item
2.02 authority source or a way to repair the earlier disclosure retroactively.
[SEC full release](https://www.sec.gov/Archives/edgar/data/1704715/000170471526000030/pressrelease6302026.htm),
[same-day presentation parent](https://www.sec.gov/Archives/edgar/data/1704715/000170471526000032/amr-20260807.htm).

Conclusion: POLICY_V1_REVIEW, NULL. The exhaustiveness hypothesis is now
contradicted by explicit reporting-perimeter evidence. However, **existing V1
classifies SEGMENT revenue with company GAAP net result as REVIEW**, not NO.
Changing that gate or relabeling the evidence to remove the preliminary candidate
would be a separate eligibility-policy change. The later YES cannot bypass that
REVIEW. Missing for a V1 resolution: an authoritative preliminary-period disclosure
of exhaustive company revenue, or proof it was already included in that event.
The later $1.351m/total figure must not be backfilled into July 27 evidence.

## Missed Event Search

Fresh SEC submissions metadata was read for exactly three CIKs. Recent metadata
contained all known accessions; no archive/history expansion was necessary.
Windows are earliest known acceptance minus 14 days through latest plus 14 days:

| Case | Inclusive acceptance-date window | Item 2.02 8-K events | Matching filed statements | Other 8-K parents reviewed |
| --- | --- | ---: | ---: | ---: |
| ABAT | 2026-08-06 to 2026-09-30 | 2 known | 1 10-K | 0 |
| OPTT | 2026-07-09 to 2026-09-07 | 2 known | 1 10-K | 4 |
| AMR | 2026-07-13 to 2026-08-21 | 2 known | 1 10-Q | 1 |

No additional Item 2.02 event or 8-K/A in those windows was found. All known
parents, linked HTML result/companion exhibits, the three exact-period statements,
ABAT's 13 slide images and five other-window 8-K parents were examined. OPTT's
other filings concern financing, contracts, strategic alternatives and listing
compliance; its companion exhibits concern acquisition/fireside-chat context.
AMR's same-day presentation does not become a new policy source.

Issuer indexes and exact-period releases were also reviewed: ABAT's
[press releases](https://investors.americanbatterytechnology.com/press-releases/),
AMR's [newsroom](https://alphametresources.com/newsroom/), and bounded OPTT
[August window](https://investors.oceanpowertechnologies.com/news-releases?page=4),
[July/August window](https://investors.oceanpowertechnologies.com/news-releases?page=7)
and [lower date boundary](https://investors.oceanpowertechnologies.com/news-releases?page=10).
No additional direct qualifying exact-quarter publication was found. Negative
findings are bounded to these windows/sources, not a claim about all issuer history.
Search snippets, aggregators and out-of-period results were never authority.

SEC acquisition captured 43 resources: 3 metadata, 6 Item 2.02 parents, 9 linked
HTML exhibits, 3 statements, 13 ABAT images, 5 other 8-K parents and 4 companions.
AMR's two issuer releases and newsroom were also captured. ABAT direct issuer
requests returned 403 and OPTT direct requests timed out; their official pages
were successfully reviewed with the web tool. Those CSV rows explicitly say
NOT_CAPTURED_WEB_REVIEW for hashes, never claim downloaded bytes or exact issuer
publication authority. All relevant SEC source downloads succeeded.

## Policy V1 Result and Validation

Baseline and fresh-evidence offline evaluation both retained the exact original
six candidates; none was removed and no new candidate was invented.

| Case | Original event eligibility | Filtering / final | Selected UTC |
| --- | --- | --- | --- |
| ABAT | NO / REVIEW | REVIEW / REVIEW | NULL |
| OPTT | REVIEW / REVIEW | REVIEW / REVIEW | NULL |
| AMR | REVIEW / YES | REVIEW / REVIEW | NULL |

All six fresh submissions acceptance values corroborated stored SEC UTC values.
All 15 fresh parent/linked HTML normalized texts were identical to the Phase 71
cached observations, although all 15 raw HTML hashes differed. The cause of raw
byte differences was not inferred. Fresh SHA-256 observations are kept separately;
original DB evidence/fixture hashes are neither replaced nor represented as fresh
download hashes. Every frozen excerpt fragment was verified against fresh text.

The research-only frozen input binds fresh primary context, fresh document hashes,
unchanged exact evidence identities and source-bound statement corroboration.
The existing evaluator reproduced the same proposals twice after freeze with
SecClient network calls explicitly denied. No generic earliest/latest selection,
Q4 reconstruction, segment-total assumption, authority write or financial write.
Replay network requests: 0; candidate count: 6; newly UNIQUE: 0.
The conditional DB-copy apply simulation was **not needed**, because no case
became UNIQUE. No live reviewed apply plan was created.

Final read-only verification matched the complete initial production file hashes,
three-case state/evidence, scope counts, fixture and Policy V1 source hashes.
No source change or new generic capability was required to record these REVIEW
results. Image inspection was manual evidence research, not an OCR implementation.
CSV validation and `git diff --check` passed. No pytest/full suite was run.

Runtime evidence is retained only under
`/tmp/rawcandle_publication_holdouts_13g375_20261006/`: preflight, downloaded
resources/hash manifest, bounded metadata searches, fresh-versus-prior comparison,
issuer fetch outcomes, frozen targeted evidence, policy replay and no-change proof.
Verifier: `/tmp/phase375_research.py`. No raw HTML, images, runtime inputs or DBs
are included in the documentation commit. CSV rows distinguish actual candidate
events from supporting evidence; research source-role labels do not introduce
production authority types. New evidence flags mean newly reviewed corroboration,
not a newly discovered qualifying publication. All selected flags are false.

## Next Action

Retain ABAT/OPTT/AMR as REVIEW/production AMBIGUOUS and proceed to broader C8 /
NOT_FOUND work. No reviewed-plan Production apply is justified from this phase.
ABAT/OPTT need direct Q4 minimum earnings evidence; AMR does not support an
exhaustive-preliminary-revenue assertion. Any later change to the treatment of
proven coal-only/segment preliminary packages needs separate generic eligibility
policy review, not a ticker exception or silent removal of a competing event.

Policy V1, source hierarchy, SEC acceptance semantics, production authority/status/
timestamp state, financial DBs, active generation, Review Queue, retry logic,
scheduler and 60-day horizon changed: NO. Live workflows executed: NO.
Only this report and the evidence CSV are committed. Nothing pushed.
