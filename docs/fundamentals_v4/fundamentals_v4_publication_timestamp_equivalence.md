# P1.2 — Same-accession timestamp representation equivalence

Date: 2026-10-09. Baseline: P1.1 commit `c2499ec7fb7d683759a3c66a67c8c7f54d1e19be` and active generation `refresh_20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`.

The exact 264-case / 538-comparison population reproduces. All comparisons refer to the same ordinary SEC parent event and differ by exactly four or five hours. All 264 cases also contain independent, distinct parent accession candidates. Removing timestamp representation as an ambiguity reason therefore releases **zero** cases. The original **599** deterministic recognition candidates remain unchanged; all still require exact-key reviewed validation before any application.

## Implementation and authority contract

The new pure helper is `rawcandle/fundamentals/publication_timestamp_equivalence.py`, specifically `compare_timestamp_representations` and `classify_timestamp_case`. It is used in the read-only historical diagnostic comparison layer. It accepts two untouched evidence records, their retained current `SecFiling` parent witness, the complete company quarter scope used by the resolver, and independent conflict / reviewed exclusion or precedence blockers. It returns both clocks, exact signed offset, parent identity finding, date-boundary flags, eligibility finding, representation finding, operational equivalence decision, reasons, and rule version.

The helper requires exact company/year/quarter, source type, accession, primary document, form, source reference and Item 2.02 status identity. Both records must identify an ordinary 8-K Item 2.02 parent. The current parent witness must agree on accession, form, primary document, SEC archive URL and current acceptance timestamp. UTC-qualified inputs are required; no unqualified clock is interpreted or repaired. Absolute offsets must be exactly 14,400 or 18,000 seconds. Identical timestamps are reported unchanged. Other offsets, missing identity, different accessions, cross-source pairs, amendments and changed eligibility remain held.

A representation match with no independent blocker is `TIMESTAMP_REPRESENTATION_ONLY`: the timestamp discrepancy alone no longer creates an ambiguity. A representation match with an independent blocker is `TIMESTAMP_PLUS_INDEPENDENT_AMBIGUITY`; the case remains held. Failed identity, offset or eligibility checks are `DOES_NOT_MEET_EQUIVALENCE_RULE`. A positive representation finding does not override Policy V1 `REVIEW`, an exclusion, a precedence relation, or a production plan fingerprint.

P1.1's timestamp mismatch field was an annotation appended **after** classification. It was not a distinct Policy V1 ambiguity reason. In these cases the ordinary resolver already returned multiple valid parent candidates, and Policy V1 lacked reviewed event observations or exclusion/precedence proof. No parser change is needed to recognize two clocks as representations of the same parent. This implementation deliberately leaves the ordinary acquisition/parser, extraction, reviewed application gate, provenance fingerprint comparison and authority writer untouched. It does not create an apply plan or automatically select either clock. Any later production integration must preserve the existing exact-evidence plan binding and reviewed safety gates.

## Population and event identity verification

The current generation and all three financial database hashes match P1.1. No refreshed baseline was needed. The authority census remains 16,242 rows: 12,890 VERIFIED; open 842 UNRESOLVED, 1,882 NOT_FOUND and 628 AMBIGUOUS. Open scope remains 3,352: 152 recent and 3,200 historical. The normal 60-day retry horizon and cap of 100 were not changed.

For every targeted comparison, retained persisted evidence was joined to the current resolver evidence by exact natural key and literal accession. Duplicate accession records were checked rather than silently overwritten. The current parent witness was checked against official captured SEC metadata for exact accession, ordinary 8-K form, primary document and acceptance timestamp, and its URL CIK against the company's active CIK. All 538 pairs pass these identity checks. The retained persisted records and captured current metadata are different evidence representations of the same exact archived parent URL; neither a submissions endpoint distinction nor an archived submissions origin creates a different event here. The original acquisition endpoint for retained evidence is not independently asserted where that provenance is absent.

Parent and exhibit identity stay separate: a linked exhibit can establish quarter context while the candidate continues to identify its parent 8-K. An exhibit URL cannot substitute for the witnessed parent. No 8-K/A is collapsed into an 8-K, no related accession is made equal, and no new event is inferred from duplicate clocks. Different evidence hashes are retained because timestamp-containing evidence records really differ; they are never substituted for one another.

| Finding | Cases / comparisons |
|---|---:|
| Original timestamp-difference cases | 264 |
| Exact accession comparisons | 538 |
| Current timestamp exactly +4h | 334 |
| Current timestamp exactly +5h | 204 |
| TIMESTAMP_REPRESENTATION_ONLY | 0 |
| TIMESTAMP_PLUS_INDEPENDENT_AMBIGUITY | 264 |
| DOES_NOT_MEET_EQUIVALENCE_RULE | 0 |
| Cases with two distinct parent accessions | 243 |
| Cases with three distinct parent accessions | 21 |
| Additional unresolved competing context | 179 |
| Cases released from LEGACY_AMBIGUITY | 0 |
| Targeted cases remaining held for independent reasons | 264 |

All 264 contain distinct parent accession candidates without reviewed exclusion or precedence proof; 179 additionally have unresolved competing context. The remaining 85 still have multiple parent candidates. Exact identity is proven **within each pair**, not between those separate parents. No ordering rule, earliest/latest preference or accession merge was used to remove the independent conflict. Total historical LEGACY_AMBIGUITY remains 630, including 366 outside the timestamp-difference population.

## Calendar boundaries and existing semantics

206 cases cross at least one calendar boundary: 205 cross UTC dates, four cross America/New_York dates, and three cross both. There are 308 UTC-boundary comparisons and four New York-boundary comparisons. These are reporting flags, not timezone corrections.

The ordinary resolver uses the acceptance UTC calendar date for its inclusive period-end through 180-day plausibility window, followed by quarter-specific document context. For every pair, both original clock values were checked against **all current open quarters for that company**, including recent quarters. Zero pairs change the eligible quarter-key set. Parent document context and natural identity are unchanged. Calendar crossing therefore introduces no additional quarter assignment ambiguity in this population. Both clocks remain preserved, and no authority publication date or instant is selected or rewritten. A pair that changes the existing plausibility window is explicitly held by the helper; focused tests cover both the start and 180-day boundary.

## Full historical recomputation and candidate stability

The P1.1 diagnostic was rerun using its retained complete official SEC acquisition captures, current committed resolver and reviewed Policy V1 / Form 6-K evaluators. Acquisition was not repeated: the baseline databases and original inputs were unchanged. The full company open-quarter scope, unresolved-context veto, durable competitor checks, reviewed domestic fixture overrides, foreign identity checks and frozen reviewed Form 6-K binding checks were retained. The original temporary replay was executed with only its two output paths redirected to the separate P1.2 temporary directory. No P1.1 artifact or raw capture was rewritten.

All 3,200 replayed rows match the P1.1 rows exactly before the new pair comparison. The new comparison is then applied to the 264 exact mismatch cases, with their independently reproduced competitors retained. None qualifies for release, so the mutually exclusive classification is unchanged:

| Classification | P1.1 | P1.2 |
|---|---:|---:|
| CURRENT_RESOLVER_CAN_SOLVE | 599 | 599 |
| RESOLVER_GAP | 10 | 10 |
| TRUE_NO_PUBLICATION_FOUND | 0 | 0 |
| LEGACY_AMBIGUITY | 630 | 630 |
| STALE_OPEN_STATE | 0 | 0 |
| INSUFFICIENT_EVIDENCE | 1,961 | 1,961 |
| OTHER | 0 | 0 |
| Total historical open | 3,200 | 3,200 |

Original 599 candidate stability: **PASS**. Natural keys, current quarter IDs, selected accessions, parent source references, source types, selected timestamps and evidence hashes match the original inventory. Full reconstructed evidence and resolver outputs reproduce deterministically. No held competitor was removed. New exact-key candidates: **0**; total next-phase candidates: **599**. All 599 have current recognition status VERIFIED but reviewed Policy V1 diagnostic status REVIEW, as before. The next phase must bind and validate exact evidence; these are neither new VERIFIED authority rows nor an authorized apply plan.

A hypothetical later successful drain of all 599 would leave 2,601 historical open and 2,753 full open authority rows. This phase performed no drain.

The candidate CSV includes the natural key, current quarter ID, display ticker, selected parent accession/source/reference/time, alternate equivalent time and offset (empty because none of the 599 has a targeted difference), equivalence status, ordinary resolver status, reviewed diagnostic status, competing-context status, evidence hash, full evidence fingerprint and next phase. Its ordered candidate population fingerprint is `38f7243d673fa58c8a18b4d4cdabae440357a4b4d37db7739ea7247ec2a3d0cd`.

## Validation and production invariance

Command:

```sh
python3 -m pytest -q tests/test_publication_timestamp_equivalence.py tests/test_policy_reviewed_publication_plan.py
```

**48 passed**: 23 focused timestamp-equivalence tests and 25 tests in the one directly relevant reviewed-publication regression group. Coverage includes positive/negative exact offsets, nonqualifying offsets, distinct accessions, amendments, exhibit context versus parent identity, unchanged identical timestamps, timestamp-only qualification, independent holds, reviewed exclusion and precedence blockers, harmless calendar crossing, actual eligibility changes, original 599 artifact stability, immutable inputs, authority-file invariance, and deterministic comparison. Full suite: **not run**.

The current pure resolver is replayed twice per captured company scope and compared with the acquisition's original complete candidate/diagnostic inventory. The entire P1.1 3,200-row replay matches. Two P1.2 measurement runs produce byte-identical committed case and candidate CSVs and identical measurement results. All 1,070 retained company capture JSON files (including captured document text and metadata) retain their hashes. Original P1.1 report and CSV hashes retain their values. Final protected-file checks verify provider/canonical/analysis databases, active generation pointer, Review Queue and existing sidecars, both scheduler configurations and publication journal unchanged. Provider watermark remains `2026-10-08`, successful run `20261009T042704Z_refresh_fundamentals_c7bbcb6dfda4_production_adc49771`.

Production publication authority/statuses/timestamps changed: **NO**. Provider, canonical and analysis financial databases changed: **NO**. Active generation, Review Queue, scheduler, watermark, retry horizon/cap and SEC raw evidence changed: **NO**. No acquisition/parser or ordinary resolver modification. No authority writer, production apply, new publication plan, network acquisition or push.

## Deliverables

- Detailed report: `docs/fundamentals_v4/fundamentals_v4_publication_timestamp_equivalence.md`
- Exact 264-case comparison artifact: `docs/fundamentals_v4/fundamentals_v4_publication_timestamp_equivalence_cases.csv`
- Exact 599-key future validation artifact: `docs/fundamentals_v4/fundamentals_v4_historical_publication_candidates_after_timestamp_equivalence.csv`

The case CSV preserves all 538 pairs, both clocks, exact offsets, event findings, boundaries, eligibility findings, original/new evidence hashes and blocking reasons in compact JSON comparison cells. Tickers are display only. No databases, raw downloads, temporary caches or unrelated worktree changes belong to this commit.
