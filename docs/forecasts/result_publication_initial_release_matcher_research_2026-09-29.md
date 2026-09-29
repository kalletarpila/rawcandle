# Initial earnings-release matcher research

Date: 2026-09-29

Scope: 651 current `result_publication_v1` `AMBIGUOUS` quarters

Decision: `SAFE_RULE_FOUND_FOR_PRODUCTION_VALIDATION`

## 1. Objective

This research tested whether competing SEC Item 2.02 candidates can be separated by evidence in the SEC filing and issuer-authored exhibit itself. The deciding classifier did not use Yahoo. Yahoo was joined only after each SEC-only decision. No production authority, evidence, forecast, or scheduler state was changed.

The result is a deliberately narrow safe candidate rule. It identifies a unique initial result filing in 25 of the 100 sampled quarters and 83 of all 651 ambiguous quarters. It is suitable for a separate production-validation phase, not deployment by this task.

## 2. Deterministic sample

The sample rule was `result_publication_initial_release_sample_v1`. It selected 100 quarters across 51 companies and 212 candidate filings:

1. Include all ambiguous quarters for the recurring or same-day controls WOR, BKD, CRGY, DTE, FANG, IPAR, LCID, OXY, CF, ABG, ORN, and FIS: 60 quarters.
2. From the remaining population, order each Yahoo-position/control stratum by `SHA256("result_publication_initial_release_sample_v1|<company_id>|<fiscal_year>|<fiscal_quarter>")`, then target Yahoo earliest 8, latest 8, middle 7, conflicts 8, and unavailable 5. Only four additional middle cases existed after the mandatory selection, so that stratum contributed 4.
3. Fill the remaining 7 places by deterministic SHA-256 order across the residual population.

This deliberately includes easy and difficult cases, recurring issuers, same-day conflicts, candidates separated by days or weeks, different fiscal calendars, large and small issuers, and Yahoo disagreement/unavailability controls. Yahoo defined validation strata but was not an input to the SEC classifier.

Sample Yahoo controls were 75 `SUPPORTS_DATE_ONLY`, 11 `DOES_NOT_DISCRIMINATE`, 9 `CONFLICTS`, and 5 `UNAVAILABLE`. Across candidate ordering, Yahoo pointed to the earliest candidate in 22 quarters, latest in 46, middle in 7, and no candidate in 25.

### Exact sample identities

- Mandatory (60): ABG 2025-Q1; BKD 2025-Q1, Q2, Q3, Q4 and 2026-Q1, Q2; CF 2025-Q1, Q2, Q3, Q4 and 2026-Q1, Q2; CRGY 2025-Q1, Q2, Q3, Q4 and 2026-Q1, Q2; DTE 2025-Q1, Q2, Q3, Q4 and 2026-Q1, Q2; FANG 2025-Q1, Q2, Q3, Q4 and 2026-Q1, Q2; FIS 2025-Q1 and Q4; IPAR 2025-Q1, Q2, Q3, Q4 and 2026-Q1, Q2; LCID 2025-Q1, Q2, Q3, Q4 and 2026-Q1, Q2; ORN 2025-Q3; OXY 2025-Q1, Q2, Q3, Q4 and 2026-Q1, Q2; WOR 2025-Q1, Q2, Q3, Q4 and 2026-Q1, Q2, Q3, Q4.
- Yahoo earliest (8): BKKT 2025-Q3; DIOD 2025-Q2; MMSI 2025-Q1; MNTK 2026-Q2; ONC 2025-Q4 and 2026-Q2; SEI 2025-Q1; WTI 2025-Q4.
- Yahoo latest (8): BBIO 2025-Q4; BYRN 2026-Q1; DSP 2026-Q1; EOG 2025-Q3; GME 2025-Q1; TNGX 2025-Q3; WDC 2025-Q2; XNCR 2025-Q4.
- Yahoo middle (4): IBRX 2025-Q1; OCGN 2026-Q1; ONDS 2025-Q4; VERI 2025-Q3.
- Yahoo conflict (8): ABAT 2026-Q4; ADTN 2026-Q2; DUOT 2025-Q1; EGY 2025-Q4; HLMN 2026-Q2; HRL 2025-Q4; LPG 2025-Q3; TROX 2025-Q4.
- Yahoo unavailable (5): DMLP 2025-Q2; FIEE 2025-Q4; GSIT 2026-Q2; MOVE 2026-Q2; XPON 2025-Q4.
- Hash fill (7): APA 2026-Q2; BRKR 2025-Q4; EPC 2025-Q4; FBIO 2025-Q1; MRNA 2025-Q4; REKR 2025-Q1; WGS 2025-Q4.

The exact period ends and candidate accessions were retained in the temporary sample artifact `/tmp/result_publication_initial_release_sample.json`. Temporary artifacts are not production inputs or durable authority.

## 3. SEC filing and exhibit findings

Every competing filing in the sample was reviewed through the official SEC filing index, primary document, and EX-99-class exhibits. The collection made 671 successful document requests with no collection errors. The full backtest made 3,476 further successful requests with no collection errors.

An EX-99 filename is not enough. Reliable positive cases combine all of the following:

- the primary filing has Item 2.02 and says the issuer issued or announced a result release;
- the statement identifies the canonical period end or fiscal quarter;
- an attached issuer-authored EX-99 exhibit is an actual earnings/results announcement for that same canonical quarter;
- the exhibit contains earnings/result language rather than merely reproducing prior-quarter context;
- the exhibit's own dateline contains the filing acceptance date in US/Eastern;
- no presentation, guidance-only, business-update, correction, or supplemental-only signal defeats the classification.

The exhibit dateline check is essential. The first classifier version omitted it. In the 651-quarter backtest that version selected FCN 2025-Q1, RDVT 2026-Q2, and TNXP 2025-Q4 on SEC acceptance dates one day after the issuer release datelines. Those were observed false timestamp selections. Requiring the issuer-authored release date to equal the acceptance local date removed all three and nine other insufficiently proven selections. The rejected V1 rule is `DO_NOT_AUTOMATE`.

Examples of genuine discrimination include:

- CF repeatedly files an earnings release and an investor presentation; the result release satisfies the complete rule and the presentation does not.
- DTE has an initial issuer result release and later DTE Gas unaudited financial statements. The latter repeats result context but is not the original publication.
- BRKR has an earlier result-context filing followed by the explicit fourth-quarter/full-year earnings release on 2026-02-12.
- GSIT has no usable Yahoo event, but its EX-99 explicitly reports fiscal 2026 second-quarter results with an October 30, 2025 dateline.

## 4. Ambiguity patterns

The deterministic sample classified as:

| Pattern | Quarters |
|---|---:|
| `INITIAL_RESULT + LATER_SUPPLEMENTAL` | 2 |
| `INITIAL_RESULT + SECOND_RESULT_RELATED_8K` | 23 |
| `MULTIPLE_GENUINE_RESULT_RELEASES` | 9 |
| `OTHER` | 66 |

No sampled case met the stricter definitions for a separate later-guidance, later-presentation, same-day-result, or fiscal-context-false-positive bucket. Presentation evidence is present in individual candidate classification, including CF, but only three full-population quarters cleanly formed `INITIAL_RESULT + LATER_PRESENTATION`.

The full population had 3 initial-plus-presentation, 4 initial-plus-later-supplemental, 76 initial-plus-second-result-related-8K, 156 multiple-genuine-result-release, and 412 other cases. Repeated prior-quarter context is therefore real and safely removable in a minority of cases, but most ambiguity cannot be resolved by a simple earliest/latest or exhibit-presence rule.

## 5. Research classifier

Classifier version: `initial_result_sec_semantic_v2_research`.

- `STRONG_INITIAL_RESULT`: primary Item 2.02 context explicitly says a result release was issued/announced for the canonical quarter; at least one attached issuer-authored EX-99 is an actual result announcement matching that quarter; its dateline contains the SEC acceptance local date; and no supplemental/presentation/guidance/business-update evidence defeats it.
- `POSSIBLE_INITIAL_RESULT`: some canonical result evidence exists, but at least one strong requirement is absent or inconclusive, including a mismatched/missing exhibit dateline.
- `SUPPLEMENTAL_OR_LATER_CONTEXT`: presentation, supplemental schedule, guidance, transaction, or business-update evidence dominates and there is no canonical earnings-release exhibit satisfying the positive combination.
- `NOT_INITIAL_RESULT`: the quarter appears only outside the relevant Item 2.02 result-release context and there is no positive release evidence.
- `INSUFFICIENT_EVIDENCE`: downloaded structure or text is not adequate for any stronger classification.

The safe quarter-level rule selects a filing only when exactly one candidate is `STRONG_INITIAL_RESULT` and every competitor is `SUPPLEMENTAL_OR_LATER_CONTEXT` or `NOT_INITIAL_RESULT`. A `POSSIBLE_INITIAL_RESULT`, a second strong candidate, or insufficient evidence blocks selection. Candidate ordering, nearest date, and Yahoo are not inputs.

## 6. SEC-only sample results

| Candidate classification | Filings |
|---|---:|
| `STRONG_INITIAL_RESULT` | 72 |
| `POSSIBLE_INITIAL_RESULT` | 85 |
| `SUPPLEMENTAL_OR_LATER_CONTEXT` | 54 |
| `NOT_INITIAL_RESULT` | 0 |
| `INSUFFICIENT_EVIDENCE` | 1 |

The rule selected 25 quarters and left 75 ambiguous. The selected candidate was earliest in 9, latest in 7, middle in 2, and on the same calendar date as its competitor in 7. This distribution demonstrates that the rule is semantic rather than positional.

The 75 blocked cases included 24 strong-plus-possible, 19 possible-plus-supplemental, 15 possible-plus-possible, 7 strong-plus-strong, and 10 less common combinations. The classifier appropriately refuses to turn those distinctions into canonical facts.

## 7. Yahoo post-hoc validation

Yahoo was joined only after the 25 SEC-only selections were fixed. It corroborated the selected local date in 24 cases and was unavailable for GSIT. It disagreed in zero sample cases.

Across the 83 full-backtest selections, Yahoo corroborated 79, was unavailable in 3, and disagreed in 1. The disagreement is PTEN 2025-Q4: Yahoo reports 2026-02-03, while the selected SEC filing was accepted on 2026-02-04 and the issuer-authored EX-99 explicitly says "February 4, 2026" and announces the canonical financial results. Under the required source hierarchy, this is a Yahoo conflict, not an observed false SEC selection.

Yahoo's strong corroboration is useful evidence that the conservative rule behaves sensibly. It is not part of the rule and cannot override issuer/SEC evidence.

## 8. Issuer-site validation

A narrow five-case issuer-site check was attempted for GSIT, BRKR, CRGY, DTE, and CF. Four pages were unavailable to the automated check due to timeout or lack of a discoverable official result page. The official CF Industries page was directly retrieved and states May 7, 2025 and the first quarter ended March 31, 2025, corroborating the SEC-only CF 2025-Q1 selection. There were no issuer-site disagreements.

Issuer-authored exhibits inside SEC filings provide additional first-party validation: PTEN's selected EX-99 explicitly carries the February 4, 2026 release date despite Yahoo's prior-day value, and GSIT's selected EX-99 explicitly carries October 30, 2025 despite Yahoo unavailability. These are part of SEC/issuer evidence, not external calendar substitution.

## 9. SwingMaster V3

SwingMaster V3 was not used. Current official SEC structures, issuer-authored exhibits, the narrow issuer check, and post-hoc Yahoo evidence were sufficient. No old-repository value was read or copied.

## 10. Candidate rules

| Candidate rule | Assessment | Reason |
|---|---|---|
| Unique V2 strong candidate, with all rivals supplemental/not-initial | `SAFE_CANDIDATE` | Complete primary-plus-exhibit semantics, issuer dateline alignment, no observed false selections, and abstains on any plausible rival. |
| EX-99 earnings-release exhibit plus canonical-quarter text, without issuer dateline agreement | `DO_NOT_AUTOMATE` | V1 produced three demonstrated one-day timestamp errors and nine more insufficiently proven selections. |
| Primary filing says an earnings release was issued, but exhibit evidence is absent/incomplete | `PROMISING_BUT_NEEDS_MORE_VALIDATION` | Useful positive evidence but not enough to distinguish repeated Item 2.02 context safely. |
| Earliest/latest accession or Yahoo-nearest candidate | `DO_NOT_AUTOMATE` | Selected safe cases occur at every position, and Yahoo is secondary evidence only. |
| Later candidate lacks a new result announcement or is clearly a presentation/supplement | `PROMISING_BUT_NEEDS_MORE_VALIDATION` alone | Strong negative evidence, but production selection still requires one fully strong positive candidate. |

## 11. False-resolution risk

For the proposed V2 safe rule:

- sample resolved: 25; unresolved: 75;
- observed false selections: 0;
- sample Yahoo disagreement: 0; unavailable: 1;
- issuer-site disagreement: 0; one direct corroboration and four unavailable checks;
- full backtest resolved: 83; unresolved: 568;
- full Yahoo disagreement: 1, with issuer-authored EX-99 supporting the SEC selection;
- remaining ambiguity: 568 quarters, including 156 multiple-genuine-result-release patterns.

The zero observed false-selection result applies to this reviewed research population and classifier implementation; it is not a proof over unseen filing formats. Coverage is intentionally low. Production validation must freeze fixtures and independently review all 83 proposed transitions before any authority update.

## 12. Full 651-quarter read-only backtest

| Measure | Result |
|---|---:|
| Quarters evaluated | 651 |
| Candidate filings | 1,318 |
| Quarters selected | 83 |
| Quarters still ambiguous | 568 |
| Companies affected | 63 |
| Yahoo corroborated / unavailable / disagreed | 79 / 3 / 1 |
| Selected earliest / latest / middle / same-date | 16 / 58 / 2 / 7 |
| Selected PRE_MARKET / AFTER_MARKET | 31 / 52 |
| Missing effective trading date | 0 |

Full candidate classifications were 601 strong, 534 possible, 168 supplemental/later, 1 not-initial, and 14 insufficient. The dominant unresolved combinations were strong-plus-possible (193), strong-plus-strong (151), possible-plus-possible (123), and possible-plus-supplemental (72). The rule does not guess among them.

## 13. Daily-OHLC impact

All 83 selected filings already have a derived publication date, publication session, and first full post-result trading date under the reviewed ET/OHLC convention. Of these, 76 are currently in `DAILY_RESEARCH_AMBIGUOUS`; 7 are already `DAILY_RESEARCH_USABLE` because their competing candidates lead to the same daily boundary.

If all 83 transitions pass production validation, materially ambiguous daily-research cases would fall from 640 to 564. No OHLC calendar, timestamp, session, or effective-date rule was changed by this research.

## 14. Production read-only verification

Before and after research:

- `data/fundamentals_v4.db`: SHA-256 `9c1c14be2f52165f93d4c9d30aba8bb64fc5489e37190ed9fb672ffa993caaad`, unchanged;
- `data/forecasts.db`: SHA-256 `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`, unchanged;
- authority status counts: 12,782 `VERIFIED`, 864 `UNRESOLVED`, 651 `AMBIGUOUS`, and 1,913 `NOT_FOUND`, unchanged;
- evidence disposition counts: 12,782 `ACCEPTED` and 1,318 `CONFLICT`, unchanged;
- canonical `PRAGMA quick_check`: `ok`;
- canonical `PRAGMA foreign_key_check`: zero rows.

All analytical JSON and helper scripts were written under `/tmp`. No production source, reusable parser, migration, `--apply`, forecast operation, or scheduler operation was added or run. The pre-existing modification to `data/.fundamentals_admin_publication_journal.json` was not changed or staged by this task.

## 15. Recommendation

Gate: `SAFE_RULE_FOUND_FOR_PRODUCTION_VALIDATION`.

The exact next step is a separate, non-deploying validation change that converts the V2 classifier into a focused tested module, freezes representative SEC primary/exhibit fixtures, adds rejection tests for the V1 dateline failures and every blocked classification combination, reproduces all 83 selections from a read-only production snapshot, and requires manual issuer/SEC sign-off for each proposed authority transition. Only after that review should a separately backed-up and reversible production apply be proposed.
