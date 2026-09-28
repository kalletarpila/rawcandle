# Full FY2025+ result-publication enrichment

Date: 2026-09-28  
Rule version: `result_publication_v1`  
Final gate: `PRODUCTION_ENRICHMENT_COMPLETE`

## Preflight

The run started from approved commit `994a8e09d7c8f716947604ce7ce0843455360393`. The only pre-existing worktree change was `data/.fundamentals_admin_publication_journal.json`; it was neither reverted nor staged. The production canonical path was `/home/kalle/projects/rawcandle/data/fundamentals_v4.db` and the publication journal was `COMPLETED` with production writes permitted.

Preflight integrity was `quick_check=ok` with zero foreign-key errors. Available disk space was 796,502,773,760 bytes, above the 1.5 GB requirement. Production authority and evidence counts were both zero. The forecast database was 271,114,240 bytes with SHA-256 `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`.

The preflight scope was:

- 16,224 canonical quarters with `fiscal_year >= 2025`
- 2,535 resolver-eligible companies and 16,210 resolver-eligible quarters with valid CIK identity
- 2,439 companies and 15,668 quarters in the active operational-universe context recorded by the approved preflight

## Backup and execution

The production CLI acquired the existing production/publication lock and created exactly one online backup before enrichment:

- path: `backups/fundamentals_result_publication/20260928T171148072426Z/fundamentals_v4.db`
- timestamp encoded in path: `2026-09-28T17:11:48.072426Z`
- size: 663,560,192 bytes
- SHA-256: `a772c470666bdedc777b785c391a40cd10dd3cfaa6e03aa849013179ae45b51e`
- `quick_check=ok`
- foreign-key errors: 0

The approved production command ran without scope limits or concurrency:

```bash
python3 -m rawcandle.cli.run_result_publication_enrichment \
  --from-fiscal-year 2025 \
  --apply --confirm-production \
  --report temp/result_publication_full_fy2025.json
```

It exited 0 after processing all 2,535 eligible companies and 16,210 eligible quarters. Company-level checkpoints, in-process SEC reuse, current pacing, and current retry behavior were retained. No persistent filing HTML cache was introduced.

## Runtime and requests

- runtime: 9,556.135 seconds (2:39:16.135), 3.770 seconds per company
- SEC metadata requests: 2,538
- SEC document requests: 19,080
- total SEC network requests: 21,618
- requests per company: 8.528
- requests per quarter: 1.334
- candidate filings inspected: 19,042
- old/out-of-scope candidate documents skipped before fetch: 78,951
- documents fetched: 19,042
- retries: 38
- HTTP 429 responses: 0
- other HTTP failures: 32
- transient failures: 6
- company failures / terminal run errors: 0

Zero-valued `rate_limit_responses` is omitted by the report's sparse counter serialization; therefore the absent field means zero 429 responses, not unknown.

## Resolution results

| Status | Rows | Share of eligible quarters |
|---|---:|---:|
| VERIFIED | 12,782 | 78.85% |
| UNRESOLVED | 864 | 5.33% |
| AMBIGUOUS | 651 | 4.02% |
| NOT_FOUND | 1,913 | 11.80% |
| Total | 16,210 | 100.00% |

All 12,782 VERIFIED rows use `SEC_8K_ITEM_2_02` with HIGH confidence. No issuer, SEC fallback, manual, or Yahoo source was added. The evidence table contains 14,100 rows: 12,782 ACCEPTED and 1,318 CONFLICT rows, all from SEC Item 2.02.

## Timestamp QA

- VERIFIED rows with exact timestamp: 12,782 / 12,782 (100.0%)
- VERIFIED rows normalized to UTC: 12,782 / 12,782 (100.0%)
- timestamps before canonical `period_end`: 0
- timestamps more than 180 days after `period_end`: 0
- authority rows without an exactly matching canonical quarter identity: 0
- evidence rows without an exactly matching canonical quarter identity: 0
- VERIFIED selections missing evidence, crossing company/quarter identity, or selecting non-ACCEPTED evidence: 0
- AMBIGUOUS rows with a selected timestamp: 0
- same-quarter multiple-valid-candidate cases: 651
- AMBIGUOUS cases with fewer than two CONFLICT evidence rows: 0

Of the 651 conflict cases, 636 have two valid candidates, 14 have three, and one has four. The resolver preserved all of them as AMBIGUOUS and did not silently choose a same-priority timestamp. The current evidence schema does not duplicate CIK on each evidence row; CIK/company safety is enforced by canonical company-scoped SEC resolution, and the post-write company/quarter/evidence key checks above found no structural identity mismatch.

## Provider-date lag

These comparisons are descriptive only. Neither Sharadar field was rewritten or used as timestamp authority.

Against `first_public_result_date`:

- same calendar date: 7,454
- +/-1 day: 2,587
- 2-7 days: 1,539
- 8-30 days: 1,125
- more than 30 days: 77
- direction: 5,136 negative, 192 positive, 7,454 zero
- absolute difference: median 0 days, p90 7, p95 13, maximum 225 days

Against `source_availability_date`:

- same calendar date: 7,454
- +/-1 day: 2,585
- 2-7 days: 1,539
- 8-30 days: 1,126
- more than 30 days: 78
- direction: 5,136 negative, 192 positive, 7,454 zero
- absolute difference: median 0 days, p90 7, p95 13, maximum 225 days

## Database and integrity

The canonical database grew from 663,560,192 to 674,754,560 bytes: 11,194,368 bytes, or 1.687%. Postflight was `quick_check=ok` with zero foreign-key errors.

The following deterministic preflight/postflight hashes are identical:

- full `v4_quarter`: `65308a16e9e6385c87887fb3689c6f40850e4116d1a8266254f06d28a46702fd`
- `quarter_id`, `first_public_result_date`, and `source_availability_date`: `86a1a17acdf0c69eba150e0395f00af419efbb9e78ca70a6e11889cf77386796`
- full `v4_quarter_financials`: `b218cacc5f76a5ef49fac59f6e6f00d7c09974d31cbcbc7368a08eda3f0472a7`

Direct bidirectional `EXCEPT` comparisons against the pre-run backup also found zero changed rows in `v4_quarter`, `v4_quarter_financials`, `v4_ttm_contract`, `v4_ttm_values`, and `v4_ttm_input_quarter`.

`data/forecasts.db` remained byte-identical. Its before and after SHA-256 is `8fc6785ce83f8a94a0cb80be8d1514e6a9f3ea1d42ac33b9d2081f83ffc9cd42`. No forecast migration, fiscal-link operation, scheduler change, or forecast-table write occurred.

Focused publication/recovery smoke tests passed: 41 tests in `tests/test_result_publication_authority.py`, `tests/test_publication_date_authority.py`, and `tests/test_fundamentals_admin_production_transaction.py`.

## Open cases

The 3,428 non-VERIFIED quarters remain explicitly open:

| Resolver reason | Rows | Persisted status |
|---|---:|---|
| `NO_ITEM_2_02_FOUND` | 1,740 | NOT_FOUND |
| `QUARTER_MATCH_FAILED` | 887 | 714 UNRESOLVED, 173 NOT_FOUND |
| `MULTIPLE_VALID_CANDIDATES` | 651 | AMBIGUOUS |
| `UNRESOLVED_CONTEXT` | 150 | UNRESOLVED |

The next review should distinguish true non-8-K/foreign-issuer coverage from missing evidence inside `NO_ITEM_2_02_FOUND`; inspect the 714 plausible-evidence quarter-match failures and 150 context failures; and review all conflicts before any rule expansion. No open case was force-resolved in this run.

### AMBIGUOUS review list

There are 651 AMBIGUOUS quarters across 451 companies. The highest-volume company candidates are:

| Ticker | Ambiguous quarters |
|---|---:|
| WOR | 8 |
| BKD, CF, CRGY, DMLP, DTE, FANG, IPAR, LCID, OXY | 6 each |
| BYRN, EOG, EQT, INBS, LPG, RGLD, RRC, SUPN | 5 each |
| ADTN, APA, DIOD, REGN, TNXP | 4 each |
| ACMR, AMR | 3 each |

The complete review list, including company ID, ticker, fiscal year/quarter, all candidate accessions, and timestamps, is retained in `temp/result_publication_full_fy2025.json`. It is selected without ambiguity by `results[].status == "AMBIGUOUS"`; the report contains all 651 rows. The production database is the durable canonical list and can be reviewed with:

```sql
SELECT a.company_id, s.current_ticker, a.fiscal_year, a.fiscal_quarter,
       a.status_reason, e.accession_number, e.source_timestamp_utc,
       e.source_reference
FROM v4_result_publication_authority AS a
LEFT JOIN security AS s
  ON s.company_id = a.company_id AND s.active = 1
JOIN v4_result_publication_evidence AS e
  ON e.company_id = a.company_id
 AND e.fiscal_year = a.fiscal_year
 AND e.fiscal_quarter = a.fiscal_quarter
WHERE a.status = 'AMBIGUOUS'
ORDER BY a.company_id, a.fiscal_year, a.fiscal_quarter,
         e.source_timestamp_utc;
```

## Downstream contract and next phase

The exact UTC timestamp remains canonical. A later daily-OHLC research phase may derive `publication_date` and `publication_session` as PRE_MARKET, REGULAR_HOURS, AFTER_MARKET, or UNKNOWN. PRE_MARKET on D may make D the first post-result trading day; AFTER_MARKET and, conservatively, REGULAR_HOURS on D use the next trading day as the first full post-result day. This run did not implement that derived classification.

Recommended next step: begin a targeted, read-only open-case review with all 651 AMBIGUOUS quarters first, followed by plausible-evidence UNRESOLVED cases and then NOT_FOUND cases. Yahoo historical earnings dates and, where useful, narrowly targeted old SwingMaster V3 lookups may be added only as secondary corroboration; they must not override issuer/SEC authority. After those reviews, design the separate daily-OHLC publication-session derivation.

The full intended eligible scope was processed, the verified pre-run backup is retained, integrity and authority checks are clean, matching-window violations are zero, and `forecasts.db` is unchanged. Final gate: `PRODUCTION_ENRICHMENT_COMPLETE`.
