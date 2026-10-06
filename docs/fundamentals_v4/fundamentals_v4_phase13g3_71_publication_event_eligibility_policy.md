# Phase 13G.3.71: Publication-Event Eligibility Policy Audit

Date: 2026-10-06. Starting HEAD: `d3459097689ad15ea689b3e6a43b8babe49fe3b7`.
**Audit and proposal only. No policy, resolver, authority or Production changes.**

## Executive Summary

Reviewed all **26 original AMBIGUOUS quarters and their 52 durable candidate events**,
not just today's retry scope. All 26 still have AMBIGUOUS authority with NULL timestamps;
their two stored evidence candidates remain intact. **20** are in the current recent-open
scope; **six** have aged out: APA, CF, DMLP, PDYN, RGLD and SM. No original identity has
otherwise changed authority state. The current whole recent-open population remains
188: 20 UNRESOLVED, 148 NOT_FOUND and 20 AMBIGUOUS.

The dominant competing event is preliminary information: 18 preliminary events,
including broad earnings and selected revenue/cash/operating components, versus later
results. Other patterns are supplemental factors, repeat presentations, entity-perimeter
overlap, transaction pro forma context, distributions and cover-date context.

Recommend **Policy B: full results plus sufficiently broad completed-period preliminary
results**, with explicit minimum financial scope and separately approved typed event
precedence. This matches first qualifying earnings publication better than either
discarding all preliminary earnings or admitting every financial component. It is a
proposal, not an approved behavioral change.

Expected cohort impact, conditional on reviewed future implementation:

| Preferred-policy impact | Original 26 | Current recent-open 20 |
| --- | ---: | ---: |
| Unique through eligibility filtering alone | 19 | 13 |
| Need explicit preliminary-to-completion precedence | 4 | 4 |
| Insufficient period/entity scope; must stay open | 3 | 3 |
| Additional irreducible competing full events established after that precedence | 0 | 0 |

The four precedence cases are **GME, TE, RDVT and RXT**. They remain genuinely ambiguous
under filtering alone and current rules. The three review holdouts are **ABAT, OPTT
and AMR**. Thus 23 original cases, including 17 current cases, are potential resolutions
under B plus approved precedence; this is not a promise of production VERIFIED outcomes.
All 26 remain AMBIGUOUS today. A filter-only implementation must leave the four
precedence cases and three holdouts open.

## Contract Review and Method

Authoritative background: [13G.3.64 audit](fundamentals_v4_phase13g3_64_persistent_open_publication_audit.md),
[original audit CSV](fundamentals_v4_phase13g3_64_persistent_open_publication_cases.csv),
[13G.3.65 recognition contract](fundamentals_v4_phase13g3_65_sec_recognition_improvements.md),
[13G.3.70 live result](fundamentals_v4_phase13g3_70_live_reviewed_publication_apply.md),
and [publication authority V1](../forecasts/result_publication_timestamp_v1_implementation_2026-09-28.md).

Inspection was limited to those inputs, `result_publication.py`, the existing selector,
active-generation binding and the original candidate evidence. There was no repository
wide scan, full issuer crawl, resolver enrichment or workflow retry.

Separate five concepts:

1. **Source authority:** issuer exact reliable release, SEC Item 2.02 8-K acceptance,
   reviewed official fallback, otherwise NULL. Yahoo is secondary only.
2. **Timestamp authority:** the eligible parent acceptance instant for SEC evidence,
   not exhibit date, filing date, call time, website posting day or cover date.
3. **Event eligibility:** whether the disclosed economic information constitutes a
   result publication, as opposed to guidance, component information or repetition.
4. **Fiscal/entity matching:** which reporting entity and quarter the result concerns.
   Sharing a period end is not sufficient to equate annual, half-year and Q4 values.
5. **Event precedence:** which qualifying stage defines first publication when more
   than one eligible event exists. This must not be hidden inside filtering.

The existing `match_quarter_context` accepts exact period-end or fiscal-quarter text.
Legacy candidates bypass the 13G.3.65 additive event-safety gates intentionally.
`apply_resolution` compares same-source-rank timestamps and retains AMBIGUOUS when
they differ; sorting chronologically does not currently grant an earliest preference.
Recognition coverage was correctly kept separate from event policy in 13G.3.65.

The authority contract answers first public result availability but explicitly does
**not** reinterpret Sharadar `first_public_result_date` or `source_availability_date`.
Those provider fields select recent scope, not event eligibility or timestamp authority.
The policy below defines the new authority's qualifying economic event, not either
provider field and not availability of every subsequently revised financial value.

The SEC's Item 2.02 covers material completed-period financial information, including
updates. It is not a guarantee of a full earnings release; therefore metadata presence
alone cannot implement RawCandle event eligibility. This is an application-policy
inference from the [official Form 8-K, Item 2.02 and instructions](https://www.sec.gov/files/form8-k.pdf),
not a claim that partial issuers filed the wrong form.

### Evidence Boundary

- Active generation throughout: `publication_drain_20261006T110330Z_2d836e37`.
- Read active canonical authority/evidence/quarter rows using SQLite URI `mode=ro`
  and `query_only=ON`. All 52 stored evidence hashes equal the original local audit.
- Read the original SEC parent documents and linked context from the prior bounded
  official-document cache. All **52 parent HTML hashes match the committed 13G.3.64
  CSV**, not merely another temporary cache. These body observations are from the
  prior audit, not claimed fresh downloads. The cache supplies 54 linked exhibit
  observations; transaction/presentation companions are not all result exhibits.
- Fresh read-only SEC submissions metadata: **26 requests**, providing all 52 exact
  accession/form/filing-date/Item 2.02/primary-document records, with no missing records.
  No company universe expansion or archived-history crawl was necessary.
- Targeted official web review of the linked KLXE deck confirms Q1, not target Q2,
  content. The [deck](https://www.sec.gov/Archives/edgar/data/1738827/000173882726000025/klxcompanypresentationq1.htm)
  explicitly labels its result context Q1 2026; its newly reviewed HTML hash is not
  claimed captured. CSV records `NOT_CAPTURED_WEB_REVIEW` for that supplemental hash.
- Ten additional exact-accession SEC filing-index reads investigated the acceptance
  discrepancy described below. No financial/evidence write or automatic repair followed.
- Three simulations operate on manually reviewed event annotations, not a proposed
  text classifier. Counts measure this fixed 52-candidate cohort, not recall across
  all potential official issuer/SEC events. CSV has one row per event, with source
  URLs/hashes, fiscal context, metadata, counterpart and decisions; no raw documents.

### Acceptance-Source Disagreement

Fresh submissions metadata agrees with stored UTC acceptance for **42/52 events**.
For both accessions of **GME, MOVE, ANRO, KLXE and PDYN**, the freshly returned
`acceptanceDateTime` is four hours later than the stored value. All ten corresponding
filing-index Accepted displays, interpreted as America/New_York wall time for these
summer dates, corroborate the **stored** UTC values. The CSV preserves raw index
display, timezone interpretation, index URL/hash and both UTC observations.

Example: GME `0001326380-26-000046` is stored as `2026-08-31T10:23:08Z`;
fresh submissions says `2026-08-31T14:23:08Z`; the [official filing index](https://www.sec.gov/Archives/edgar/data/1326380/000132638026000046/0001326380-26-000046-index.htm)
displays `2026-08-31 06:23:08`, consistent with 10:23 UTC under Eastern daylight time.
This is corroboration under an explicit timezone interpretation, not a silent overwrite
or proof of the cause of the submissions discrepancy. Event comparisons below use
the existing stored evidence, whose index observations corroborate these ten values.
Before any future live application, acceptance-source/timezone corroboration must
be reviewed independently. Do not switch to the conflicting fresh values just because
they have a Z suffix. No timestamp-normalization code change belongs in this phase.

## Event Taxonomy

Primary class describes event meaning; `actual_vs_preliminary`, subclass and financial
scope describe completeness and numeric semantics separately. A class can be clear
while its mapping to the canonical quarter remains REVIEW.

| Class | Definition | Events |
| --- | --- | ---: |
| C1 FULL_PERIOD_RESULTS | Actual substantially complete period financial result release; unaudited alone is not preliminary | 25 |
| C2 PRELIMINARY_RESULTS | Explicit closed-period preliminary management results: broad earnings versus selected metrics | 18 |
| C3 PARTIAL_RESULTS | Monetary component/package without a broad earnings result, including distribution/cash receipts | 1 |
| C4 GUIDANCE_OR_EXPECTATION | Future-period outlook or anticipated announcement without completed-period results | 0 |
| C5 SUPPLEMENTAL_RESULT_INFORMATION | Selected result factors, schedules or presentation context rather than primary earnings publication | 2 |
| C6 REVISED_OR_CORRECTED_RESULTS | Expressly revises earlier results; distinguish clerical, material financial revision and restatement | 1 |
| C7 DUPLICATE_OR_REPEAT_PUBLICATION | Same result event repeated/presented, rather than independently announced anew | 1 |
| C8 PARENT_SUBSIDIARY_OVERLAP | Release subject and economic perimeter differ from parent registrant/canonical company | 1 |
| C9 PRO_FORMA_OR_TRANSACTION_CONTEXT | Hypothetical transaction combination, not actual standalone/consolidated result publication | 1 |
| C10 NON_RESULT_EVENT | Cover-date presentation or nonfinancial operating statistics, not target earnings | 2 |
| C11 OTHER / INSUFFICIENT_EVENT_EVIDENCE | Economic meaning itself cannot be established | 0 |

Total: **52**. Eighteen C2 events comprise six broad/broad-annual earnings shapes and
twelve selected-metric shapes; two broad shapes have explicit scope caveats. Cash-only
preliminary updates are C2 with partial/cash subclasses, not broad earnings. The three
REVIEW quarters concern period/perimeter sufficiency, not unclassified event meaning.
No original ambiguous pair includes 8-K/A; all 52 forms are 8-K.

## Evidence by Ambiguity Pattern

### Broad Preliminary Earnings Versus Completed Results

**GME, TE, RDVT and RXT** publish completed-quarter sales/revenue and GAAP net
income/loss before a later completed quarterly release. GME explicitly says complete
results will follow. RDVT's primary includes estimated revenue and GAAP income.
RXT supplies revenue, GAAP loss, operating loss and EPS, not merely its future outlook.
TE supplies sales and GAAP loss from continuing operations; that scope must stay explicit.
Their initial estimates are financial result information even when wording includes
expected ranges. They are not guidance for an uncompleted future quarter.

Example official parents: [GME preliminary](https://www.sec.gov/Archives/edgar/data/1326380/000132638026000046/gme-20260831.htm),
[GME full](https://www.sec.gov/Archives/edgar/data/1326380/000132638026000050/gme-20260908.htm),
[RDVT preliminary](https://www.sec.gov/Archives/edgar/data/1720116/000119312526335043/rdvt-20260805.htm),
[RXT preliminary](https://www.sec.gov/Archives/edgar/data/1810019/000181001926000078/rxt-20260702.htm).

Under A, only the full release remains. Under B both are eligible: excluding the
completion merely to force a unique candidate would hide a precedence decision.
The explicit preliminary-to-completion relationship must be represented and approved.
RXT's final revenue differs from its preliminary estimate; first-public time must
never imply that its final value was already known on the preliminary date.

**AMR** genuinely publishes preliminary GAAP loss/EPS, detailed coal revenue/cost and
shipment information, not a cash-only update. But its preliminary sales are labeled
Met-segment coal revenues, not explicitly consolidated total revenues. B fails closed
until the reporting perimeter is established. Its [preliminary exhibit](https://www.sec.gov/Archives/edgar/data/1704715/000170471526000025/a072726preliminarypressrel.htm)
is not excluded because of the word preliminary; the unresolved issue is whether
the sales measure exhausts the reporting entity's revenue. Treating segment sales
as total sales without that proof would silently weaken B's deterministic minimum.

### Selected Preliminary and Partial Information

Eleven filtering cases have narrow preliminary completed-period information:
**SMCI, GOSS, REKR, ANRO, KSCP, CDXS, ASTS, CRC, PLUG, PDYN and RGLD**.
Each also has a separate full target-quarter result candidate. Important distinctions:

- SMCI has revenue and gross-margin estimates, not preliminary GAAP net earnings.
- REKR has revenue, adjusted gross margin, adjusted EBITDA and cash. Four metrics
  still do not become a broad GAAP earnings package. Its final exhibit includes
  GAAP loss and condensed statements of operations.
- KSCP is revenue-only; CDXS and PDYN add cash/backlog, not earnings.
- GOSS, ANRO, ASTS and PLUG disclose estimated cash balances in other business or
  financing contexts. A balance is not a quarter cash-flow statement or net result.
- CRC's price/derivative summary explicitly disclaims a quarterly earnings estimate.
- RGLD supplies segment sales, cost and depreciation components but no net income.

These shapes are eligible under permissive C, but excluded by A/B. The exclusion is
the missing earnings scope, not whether a disclosure is earlier than the full release.
Representative official parents: [REKR](https://www.sec.gov/Archives/edgar/data/1697851/000143774926023616/rekr20260715_8k.htm),
[ASTS](https://www.sec.gov/Archives/edgar/data/1780312/000149315226033365/form8-k.htm),
[CRC](https://www.sec.gov/Archives/edgar/data/1609253/000160925326000122/crc-20260714.htm).

### Supplemental, Repeated and Non-Result Context

**APA and SM** disclose selected preliminary earnings factors before their full
results. Both explicitly describe limited, noncomprehensive information. Supplemental
does not necessarily mean after results: these are pre-result components, not new
full earnings events. **DMLP** reports distributions and cash receipts spanning older
sales periods; the full earnings release explicitly distinguishes distributions from
net earnings because of timing/depletion. These three are A/B filtering opportunities.

**CF** has a full earnings release and a separate presentation expressly for the call
discussing those same results. This is repeat/supplemental evidence, not an independent
first release. Presentation format alone is not a permanent exclusion: a deck that
genuinely first publishes a qualifying new earnings package must be assessed on content.
**BKD** gives monthly and quarter-average occupancy, not financial earnings.
**KLXE** is a generic presentation filed on target quarter end; the directly linked
deck's financial context is Q1, not Q2. It is a cover-date match, not a Q2 event.

Official evidence: [APA supplement](https://www.sec.gov/Archives/edgar/data/1841666/000184166626000045/apa8k-20260708.htm),
[SM considerations](https://www.sec.gov/Archives/edgar/data/893538/000089353826000104/sm-20260716.htm),
[DMLP distribution](https://www.sec.gov/Archives/edgar/data/1172358/000143774926024295/dmlp20260723_8k.htm),
[DMLP earnings](https://www.sec.gov/Archives/edgar/data/1172358/000143774926026405/dmlp20260806_8k.htm),
[CF presentation parent](https://www.sec.gov/Archives/edgar/data/1324404/000110465926091275/tm2622111d1_8k.htm),
[BKD occupancy exhibit](https://www.sec.gov/Archives/edgar/data/1332349/000133234926000057/june2026occupancy.htm).

### Entity and Transaction Perimeter

**ARKO:** the earlier parent-CIK filing attaches APC subsidiary results; the release
subject and consolidated statements are APC. Parent references/store conversions are
not a broad ARKO-parent earnings package. The next release expressly reports ARKO
consolidated results. This is an entity-scope filter, not company merging or a proven
CIK mapping defect. A parent-carried release could qualify for a subsidiary only with
an explicitly reviewed same-entity attribution; no automatic inheritance is proposed.
See [subsidiary-context parent filing](https://www.sec.gov/Archives/edgar/data/1823794/000119312526337978/arko-20260806.htm)
and [ARKO result filing](https://www.sec.gov/Archives/edgar/data/1823794/000119312526339092/arko-20260807.htm).

**MOVE/Corvex:** the actual Q2 release reports post-merger consolidated operations.
The later filing supplies hypothetical combined transaction figures and explicitly
does not update actual statements. Reject that pro forma event, not all result releases
by merged issuers. Same CIK/name/ticker history does not turn hypothetical information
into actual quarter results. [Actual release parent](https://www.sec.gov/Archives/edgar/data/1734750/000121390026090115/ea0302004-8k_corvex.htm);
[transaction parent](https://www.sec.gov/Archives/edgar/data/1734750/000121390026097690/ea0304515-8k_corvex.htm).

### Annual/Q4 and Material Revision Holdouts

**ABAT:** the preliminary Q4 release contains revenue/cost/gross profit, not Q4 net
earnings. The later release contains actual annual financial statements but does not
separately disclose Q4. An annual period-end match cannot establish that quarter's
minimum numeric package or its first earnings event. The original audit's broad
preliminary-versus-final shorthand is therefore insufficient for choosing this Q4.
[Preliminary exhibit](https://www.sec.gov/Archives/edgar/data/1576873/000149315226039500/ex99-1.htm);
[annual result exhibit](https://www.sec.gov/Archives/edgar/data/1576873/000149315226042948/ex99-2.htm).

**OPTT:** the initial primary announces fiscal Q4 and full-year results, while exhibited
financial tables are annual. The later release expressly revises previously announced
preliminary results after audit procedures, including revenue and GAAP losses. It is
a material financial revision in an ordinary 8-K, not a clerical amendment. Separate Q4
values remain unproven; even quoted prior net loss differs from the initial annual table.
Do not use that uncertainty to replace the first publication time or manufacture a
quarter result. Neither a formal restatement nor resolution of that discrepancy is
established here. [Initial parent](https://www.sec.gov/Archives/edgar/data/1378140/000149315226034425/form8-k.htm);
[revision exhibit](https://www.sec.gov/Archives/edgar/data/1378140/000149315226039793/ex99-1.htm).

## Policy Simulations

`YES`, `NO` and `REVIEW` are audit eligibility annotations, **not new workflow statuses**.
Known period/perimeter insufficiency is quarantined before event filtering. REVIEW
is not converted to NO to create a unique result; a competitor with unresolved scope
blocks automatic resolution even when another event qualifies. Counts below apply
eligibility only and retain the existing same-priority conflict behavior.

| Policy | Eligible events | Excluded events | REVIEW events | Unique quarters | Still ambiguous | Review-blocked quarters | No eligible event |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A: strict substantially complete, non-preliminary results | 24 | 25 | 3 | 24 | 0 | 2 | 0 |
| B: A plus minimum broad preliminary earnings | 28 | 20 | 4 | 19 | 4 | 3 | 0 |
| C: any own-entity completed-period monetary result/component | 45 | 4 | 3 | 4 | 20 | 2 | 0 |

All rows total 52 events and 26 quarters. Current recent-open subset results:

| Policy | Unique | Ambiguous | Review-blocked |
| --- | ---: | ---: | ---: |
| A | 18 | 0 | 2 |
| B | 13 | 4 | 3 |
| C | 4 | 14 | 2 |

C is deliberately permissive: it includes numeric management estimates of a **completed**
period as well as actual components, but not future-period guidance. These estimates
are explicitly marked preliminary, never mislabeled actual final values. A strictly
final-actual-only interpretation would be a different sensitivity, not this stress test.
Common fiscal/entity constraints remain: pro forma combinations, another entity's
results and wrong-period presentations do not qualify even under C.

### Precedence and Timestamp Effects

- **A:** 24 unique through filtering. Safety cost: rejects meaningful broad preliminary
  GAAP earnings and moves first-public time to the later completion in four proven B
  precedence cases; ABAT/OPTT remain review-blocked.
- **B:** 19 unique by filtering. With the separately proposed four typed preliminary-to-
  completion relations, **23** would have a proposed first event, leaving three open.
  There is no residual independent full/full tie established in this cohort; without
  approved precedence the four are still AMBIGUOUS. AMR requires manual scope judgment.
- **C:** 4 unique by filtering, 20 conflicts. As a negative stress experiment only,
  applying C's chronological first-disclosure preference to known eligible components
  would yield **24** selected quarters and two holdouts. This is not recommended and
  must not be implemented as a generic earliest rule. Compared with B's 23 determinate
  cases, **14** would move earlier to selected/cash/supplemental components, plus C
  would select AMR's unproven consolidated-sales preliminary stage. C admits CF's
  same-results presentation as another candidate even though its first preference
  would still pick the actual release. Maximum selected count is not policy quality.

The 14 earlier component choices under C: SMCI, GOSS, REKR, ANRO, KSCP, CDXS, ASTS,
CRC, PLUG, APA, DMLP, PDYN, RGLD and SM. These are false-positive risks for an earnings
event boundary, not a claim their reported financial components were false.

| Case | B qualifying preliminary SEC time | A later full SEC time |
| --- | --- | --- |
| GME | 2026-08-31T10:23:08Z | 2026-09-08T13:02:39Z |
| TE | 2026-07-28T10:37:38Z | 2026-08-12T10:50:51Z |
| RDVT | 2026-08-05T20:05:42Z | 2026-08-11T21:26:49Z |
| RXT | 2026-07-09T12:13:03Z | 2026-08-10T20:08:51Z |

All 26 current authority timestamps are NULL. These are **hypothetical policy-specific
choices**, not persisted timestamp changes. Stored SEC time is not inferred issuer
release time; the RDVT release date, for example, precedes its parent acceptance day.

## Recommended V1 Policy

Proposed definition: **the first qualifying broad earnings-result disclosure for the
canonical reporting entity and completed fiscal quarter**, under the reviewed authority
source/timestamp contract. Not the first financial number, the final audited value,
or the first time a provider observed it. Approval is needed before implementation.

### Eligibility Rules

1. Require established issuer/entity perimeter, target-period attribution, eligible
   source/form/Item 2.02 and existing acceptance-window rules. Evidence insufficient
   to distinguish year/quarter or parent/subsidiary remains open. Do not derive Q4
   numbers by annual-minus-nine-month arithmetic in event recognition.
2. A full actual results release qualifies when its result-bearing primary/exhibit
   publishes a substantially complete company-period earnings package: period revenue
   and GAAP net income/loss with supporting P&L scope, rather than isolated components.
   A complete reported GAAP operating-expense/net-loss statement for a pre-revenue
   issuer also qualifies: ANRO's actual consolidated statement begins with operating
   expenses and reports operating loss, other income and net loss. This does not infer
   a zero revenue number from a missing isolated metric. An explicit zero revenue is
   also valid. Ordinary unaudited quarterly results are not preliminary unless the
   relevant result disclosure says so.
3. Preliminary results qualify only for an already completed period, explicitly
   attributed to the same company, with **consolidated period revenue (including an
   explicit zero) and a GAAP net-income/loss measure**, reported amounts or ranges.
   GAAP continuing-operations net result may qualify only if expressly labeled and
   consistently scoped; it must not be relabeled total company net income. No automatic
   sector proxy, sum of incompletely scoped segments, adjusted EBITDA or gross profit
   substitution. A cash balance or financial margin is not an earnings metric.
4. Selected sales, production/volume, prices, gross margin, cash balances/flows,
   backlog, distributions and receipt components do not independently qualify without
   that earnings minimum. Preserve such economic observations separately if useful.
5. Guidance/expected future performance, anticipated releases, cover-date matches,
   unrelated fiscal references, monthly metrics, pure pro forma transaction context
   and generic presentations do not qualify. Apply exclusions to the relevant event
   unit, **not the whole document based on a word match**. A valid result release can
   also contain guidance, financing pro forma cash or merger discussion.
6. Proven repetition/supplementary presentation of an already identified event does
   not create another first-publication candidate. Require same entity/period and
   source-supported relation/content corroboration; presentation format, later date
   or an identical quarter token alone is not proof. Novel broad earnings in a deck
   require assessment rather than blanket exclusion.
7. Do not inherit results between parent and subsidiary. A carried release must meet
   the canonical entity's own scope/minimum; related-company statements alone fail.
   Ambiguous entity attribution remains open, not silently remapped.

### Separately Defined Event Precedence

Eligibility retains both a qualifying broad preliminary release and its completing
full release. Only then may an independently reviewed relationship determine first time:

- A confirmed **PRELIMINARY_RESULT -> COMPLETION_OF_SAME_RESULT** edge retains the
  qualifying preliminary event as first disclosure. Require same canonical entity,
  exact period/grain, completed-period minimum, and evidence that the later event
  completes that result. Date order validates the relation; it does not establish it.
- If the preliminary stage fails the minimum, it is filtered out; the later full release
  is the first qualifying event. This is eligibility, not a latest-release preference.
- A confirmed **INITIAL_RESULT -> CORRECTION/REVISION** relation does not reset first
  time if the initial release qualified. Retain clerical corrections, material revisions
  and restatements as later version evidence with their own availability instants.
  A revision that first adds the missing minimum may be the first qualifying event,
  but its timestamp must not be inherited from an earlier nonqualifying disclosure.
- A confirmed **RESULT -> SAME_RESULT_REPEAT** relation keeps original first time,
  retaining repeat evidence. In this cohort CF can be filtered as explicitly supplemental
  same-results call context; uncertain repeats must not be dismissed to manufacture uniqueness.
- Independent eligible events without a supported relation, incomparable result
  perimeters, divergent relation branches, missing predecessors, unknown scope or
  cyclic/inconsistent event relations remain AMBIGUOUS/open with NULL authority.

No generic earliest/latest shortcut is proposed. These rules specify event-stage
precedence; they are not a new source rank or permission to let a frozen plan override
resolver/apply. A timestamp for initial result publication is also not a PIT availability
time for revised financial values, final EPS or every individual financial field.

### Source Hierarchy and Amendments

Keep existing authority hierarchy and parent SEC acceptance semantics. The current
writer ranks sources globally, before same-priority timestamp conflicts. Applying event
precedence before source priority across **different** economic events would be a
separate cross-source contract decision, not harmless candidate filtering. This cohort
contains SEC-only pairs, so proposed initial automation must be scoped to reviewed SEC
events; mixed issuer/SEC event-stage conflicts need explicit review rather than changing
the hierarchy silently. Stronger issuer evidence should corroborate the selected event,
not automatically backdate/replace it with an unrelated later event.

No original candidate pair includes 8-K/A, so amendment impact is **not measured** here.
Current acquisition supports 8-K only. Do not broaden that form contract automatically.
An amendment's meaning is content-specific: clerical correction, material revision,
restatement or first substantive earnings disclosure. With a proven qualifying original,
retain first-public time and later amendment availability separately. If the original
was nonqualifying/missing, do not borrow its acceptance time; keep open or use an
explicitly reviewed existing official-fallback route. A future 8-K/A authority expansion
requires separate form/source review and positive/negative fixtures. The XRAY amendment
opportunity identified in 13G.3.64 is background, not a 27th audited ambiguity or a newly
approved amendment source. Updated results can also occur in an ordinary 8-K, as OPTT shows.

## Alternatives and Safety Implications

| Question | Alternatives | Recommended decision and safety |
| --- | --- | --- |
| Full versus preliminary | Reject all preliminary; accept selected metrics; accept a defined broad minimum | B minimum preserves genuine early earnings without admitting revenue/cash-only information |
| Partial disclosures | Any financial number; earnings minimum; sector-specific component proxies | Earnings minimum; defer sector proxies until separately evidenced, including AMR |
| Later full release | Prefer full always; prefer earliest always; typed stage precedence | Qualifying preliminary first only with a supported completion relation; both stay eligible |
| Revised/reissued results | Replace first time; ignore revision; separate initial and version availability | Preserve qualifying initial time, retain revision evidence; never backdate changed values |
| Supplemental/repeated | Ignore all decks; prefer latest detail; prove same event | Content and relation proof; preserve genuinely novel earnings in a deck if it meets minimum |
| Parent/subsidiary | Parent-CIK implies own results; inherit any related earnings; exact reporting scope | Exact entity perimeter; no merge/inheritance; partial parent context alone is insufficient |
| Pro forma | Match any historical values; reject any document mentioning pro forma; event-unit assessment | Reject hypothetical result unit, retain genuine actual units; MOVE/ANRO show why whole-document keywords are unsafe |
| Amendment | Treat same as original; always replace; inspect original and amendment economic meaning | No automatic form expansion or timestamp inheritance; separate approved review required |

## Unresolved Policy Questions

1. Approve B's revenue/GAAP-net-result boundary as the intended first earnings event.
   It intentionally does not mean that all final financial values were public then.
2. Approve the explicit continuing-operations scope exception exemplified by TE.
   Decide separate treatment of mixed total/continuing/per-share-only result packages.
3. Establish annual-to-Q4 event/financial scope for ABAT and OPTT before selecting either.
   Review OPTT's quoted original-value inconsistency and revision perimeter independently.
4. Establish whether AMR's preliminary Met-segment revenue exhausts consolidated revenue.
   This evidence gap must not be answered by ticker-specific assumptions.
5. Define source-supported relationship annotations and conflict proof for preliminary,
   completion, correction and repeat, including when more than two candidate events exist.
6. Separately review source-rank versus event-stage ordering before applying across mixed
   issuer/SEC candidates. This SEC-only audit cannot justify that broader change.
7. Resolve/corroborate the ten observed SEC acceptance-source discrepancies before live
   replay. Index support does not authorize an unreviewed timestamp-normalization patch.
8. Amendments, foreign filings, issuer acquisition, formal restatements and sector-specific
   minimums lack a representative ambiguous sample here; do not extrapolate coverage.

These are future approval/evidence gates, not material questions blocking this no-write
audit. None was silently implemented or used to mutate current statuses.

## Expected Implementation Impact

| Case group | Cases | Future operation |
| --- | ---: | --- |
| Selected preliminary versus full: SMCI, GOSS, REKR, ANRO, KSCP, CDXS, ASTS, CRC, PLUG, PDYN, RGLD | 11 | Event-scope filtering of incomplete initial disclosure |
| Supplemental/distribution/repeat: APA, SM, DMLP, CF | 4 | Content/relationship-backed first-event filtering |
| Wrong-period operational/presentation: BKD, KLXE | 2 | Event-period and financial-content filtering |
| Entity/transaction: ARKO, MOVE | 2 | Reporting-perimeter and actual-versus-pro-forma filtering |
| Broad preliminary/completion: GME, TE, RDVT, RXT | 4 | Both eligible; explicit reviewed precedence required |
| Scope/evidence holdouts: ABAT, OPTT, AMR | 3 | Keep open, targeted period/entity evidence completion |

19 + 4 + 3 = 26. No independent indistinguishable full/full publication pair is proven
after accepting the proposed typed precedence; this is not a general guarantee of
unambiguous future issuer history. The original 22 true-contract ambiguities were not
mistakes under the old contract: many could become decidable only after an explicit
semantic policy change. The four original context gaps remain part of these 26.

## Recommended Next Phase

Propose **13G.3.72: versioned publication-event eligibility and typed-precedence fixtures,
copy-only validation**. No live apply should be bundled into that implementation.

- Approve the economic boundary first. Preserve current default/source hierarchy and
  normal VERIFIED skip behavior; never reconsider existing authority opportunistically.
- Separate classification/filtering from relationship precedence. Carry an auditable
  rejection/relationship reason and immutable original evidence; do not delete historical
  candidates or turn REVIEW into a negative merely to force a unique outcome.
- Freeze the 52-event baseline, including GME/RDVT/RXT/TE broad positives and REKR/SMCI
  multi-metric negatives. Add annual/Q4, segment/parent, pro forma, monthly/cash-only,
  cover-date, repeat, original/amendment and unresolved competing full-result fixtures.
- Explicitly test the approved legacy eligibility changes; 13G.3.65's no-candidate-loss
  recognition guarantee cannot be reused to pretend policy filtering is additive.
- Copy-only replay must reconcile the 19/4/3 partition, retain unknown/independent ties,
  preserve outside-cohort/VERIFIED financial and publication state, and prove no source-
  hierarchy or timestamp substitution. No ticker-specific policy rules.
- Track acceptance-source corroboration as a separate bounded safety review. Only after
  those gates should a later separately authorized reviewed-plan production phase occur.

## Validation and No-Change Confirmation

Temporary read-only audit/simulation artifacts are under `/tmp/publication_event_371/`;
they are not committed. Pure assertion checks establish all 26 original natural keys,
two unique accessions per key, all 52 classifications, three complete policy partitions,
the 19/4/3 impact partition and the 20-case recent overlap. No resolver writer was called.

Before/after SHA-256 checks cover provider, canonical and analysis active databases,
active pointer, publication journal, Review Queue and scheduler configuration. All
remain identical; all 26 authority rows and 52 stored candidate events remain unchanged.
Active canonical fingerprint remains
`ce7a57a33e6fe40e7741c1bddc97b4580d2e374f3fc2b9c95164a189436ae48d`.
`git diff --check` passes. No source or tests were edited; no suite was run.

Publication authority, timestamps/statuses, resolver, candidate eligibility/ranking,
retry cap/horizon/logic, financial values, active generation, Review Queue and scheduler
state changed: **NO**. Live apply, drain, retry, Refresh or scheduler workflow executed:
**NO**. Forecast history and backups were not touched. Existing unrelated worktree
changes are preserved. Commit contains only this report and the
[52-event CSV](fundamentals_v4_phase13g3_71_publication_event_cases.csv). Nothing pushed.
