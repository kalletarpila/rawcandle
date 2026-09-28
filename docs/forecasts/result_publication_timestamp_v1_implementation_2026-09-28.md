# Result publication timestamp V1 implementation

Date: 2026-09-28

## Purpose and boundary

This phase adds an additive market-publication authority for canonical quarterly results. It answers when a result first became public, with an exact UTC timestamp when authoritative evidence supports one.

It does not change or reinterpret `v4_quarter.first_public_result_date` or `v4_quarter.source_availability_date`. Those remain Sharadar/provider date semantics. Sharadar dates are never a fallback for the new authority. No forecast table or linker behavior changes in this phase.

## Physical schema

`v4_result_publication_authority` stores one current resolution per stable canonical key `(company_id, fiscal_year, fiscal_quarter)`. It also records the current `quarter_id`, status, timestamp, source, confidence, evidence reference, selected evidence ID, verification time, rule version, and status reason.

`v4_result_publication_evidence` stores compact immutable evidence. It includes the canonical identity, source timestamp, source type, SEC accession/document/form/Item 2.02 status, reference, matching method, rule version, review flag, evidence fingerprint, and disposition. It can also retain Yahoo's original timestamp/timezone, normalized UTC timestamp, fetch/observation time, provider symbol, and security identity.

The natural quarter key is authoritative because the existing refresh workflow deletes and recreates `v4_quarter`. `quarter_id` is retained for direct consumers and resynchronized for surviving rows after refresh. The evidence table does not store filing HTML.

Migration is additive and idempotent. Fundamentals provider, analysis, and forecast databases are not modified.

## Authority and source hierarchy

Implemented hierarchy:

1. `ISSUER_EARNINGS_RELEASE`: exact official issuer timestamp, HIGH.
2. `SEC_8K_ITEM_2_02`: exact SEC acceptance timestamp clearly tied to the quarter, HIGH.
3. `SEC_FILING_FALLBACK`: explicitly reviewed official filing fallback, MEDIUM.
4. `MANUAL_REVIEW`: explicit reviewed evidence, confidence assigned by review.
5. Otherwise no timestamp.

`YAHOO_EARNINGS_CALENDAR` is supported only as secondary evidence. It is never eligible for authority selection and is persisted with disposition `REJECTED` in the authority-selection sense. This means useful corroboration is retained without implying that Yahoo is the publication source.

The reproducibility contract is `result_publication_v1`.

## SEC Item 2.02 resolution

The focused SEC client reads official submissions metadata, including archive chunks needed for FY2025, and downloads only candidate Item 2.02 primary documents. An accepted candidate must have:

- canonical company-to-CIK identity;
- form `8-K` and submissions metadata containing Item 2.02;
- document text confirming Item 2.02 Results of Operations;
- exact canonical period-end text or explicit matching fiscal quarter and year;
- an acceptance date no earlier than period end and no more than 180 days after it.

Ticker is only an operator scope/display value. It is not permanent matching identity. Multiple same-priority timestamps produce `AMBIGUOUS`; unmatched plausible Item 2.02 context produces `UNRESOLVED`; absence produces `NOT_FOUND`. Existing verified authority survives an unsuccessful retry. A stronger issuer source can supersede SEC under the documented hierarchy, while a same-priority disagreement becomes a preserved conflict.

Issuer-site scraping was not added. Exact issuer timestamps remain a stronger future override when reliably acquired.

## Operator workflow

The explicit command is:

```bash
python3 -m rawcandle.cli.run_result_publication_enrichment \
  --from-fiscal-year 2025 --tickers AAPL NVDA AMZN ADBE --apply
```

Without `--apply`, it is read-only. Verified rows are skipped by default, making retries resumable; `--refresh-existing` requests explicit reconsideration. Company-level failures roll back only that company and are reported. Production apply requires `--confirm-production`, the existing publication journal guard, the Fundamentals production/scheduler lock, a verified online backup, and post-write `quick_check` plus `foreign_key_check`.

## Validation sample

The official sample was run against an online copy of production:

| Symbol | Canonical quarter | SEC Item 2.02 acceptance UTC | Existing first-public/source date | Yahoo history |
|---|---|---:|---:|---|
| AAPL | FY2026 Q3 | 2026-07-30T20:30:28Z | 2026-07-31 | UNAVAILABLE_TECHNICAL |
| NVDA | FY2026 Q4 | 2026-02-25T21:31:25Z | 2026-02-25 | UNAVAILABLE_TECHNICAL |
| AMZN | FY2026 Q2 | 2026-07-30T20:06:23Z | 2026-07-31 | UNAVAILABLE_TECHNICAL |
| ADBE | FY2026 Q3 | 2026-09-10T20:06:14Z | 2026-09-22 | UNAVAILABLE_TECHNICAL |

All 30 FY2025+ quarters for the four companies resolved as `VERIFIED` from SEC Item 2.02, with 100% exact timestamp precision. The original canonical dates remained unchanged.

Yahoo/yfinance 0.2.66 was inspected through `Ticker.get_earnings_dates()`. All four requests were unavailable because the installed environment lacks yfinance's optional `lxml` dependency. No dependency or HTML workaround was introduced, and forward-looking `get_calendar()` data was not used. Therefore the requested Yahoo match/date-only/difference comparison is unavailable rather than inferred.

## Representative copy pilot and coverage

A second copy-based pilot covered COST, GOOG, JNJ, KO, META, MSFT, TSLA, WMT, and XOM:

- total quarters: 61
- `VERIFIED`: 58
- `UNRESOLVED`: 2
- `AMBIGUOUS`: 0
- `NOT_FOUND`: 1
- coverage: 95.08%
- source mix: 58 `SEC_8K_ITEM_2_02`
- confidence mix: 58 HIGH
- exact timestamp precision: 100%

For the 58 verified rows, lag against each existing date field was: same calendar date 8, +/-1 day 19, 2-7 days 14, and more than 7 days 17. These differences reflect distinct source semantics; they do not rewrite or label the old fields as incorrect.

Production currently has 16,224 canonical quarters with fiscal year 2025 or later.

## Production rollout

Rollout state: `STOP_FOR_REVIEW` for data enrichment. The reviewed production action in this phase is schema-only; no production authority/evidence rows are populated.

The schema-only production migration completed under the existing publication guard and production/scheduler lock. Its verified online backup is `backups/fundamentals_result_publication/20260928T152118Z/fundamentals_v4.db` (SHA-256 `87a8b734646f83120b9e8aa2ce10bf51130ff263487cc4069fa280497b57749d`). Postflight was `quick_check=ok`, zero foreign-key errors, zero authority rows, and zero evidence rows. The before/after hash of all existing `quarter_id`, `first_public_result_date`, and `source_availability_date` values remained `86a1a17acdf0c69eba150e0395f00af419efbb9e78ca70a6e11889cf77386796`.

Reason: the representative pilot is strong, but a serial full-universe SEC run would require several hours and thousands of official-source requests. The unresolved cases should be sampled before approving that network/write scope. The full run must remain an explicit operator action, not a scheduler job.

Future updates should query only rows without `VERIFIED` authority, emphasizing newly created and recent quarters. Explicit `--refresh-existing` review can reconsider verified rows. There is no scheduler hook in V1.

## Research contracts

For future research, and only where authority status is `VERIFIED`:

```text
forecast.fetched_at_utc < result_publication_timestamp_utc  -> PRE_RESULT
forecast.fetched_at_utc >= result_publication_timestamp_utc -> POST_RESULT
```

Without verified authority, classification is unavailable. It must not fall back to either Sharadar date.

Yahoo's forecast-regime transition remains separate: the last fetch with the old `0q` and first fetch with the next `0q` define an observed interval. Future research may compare the publication timestamp `T1` with the first new-regime fetch `T2` to measure provider lag. `T2` is not company publication time.

## Unresolved issues and next gate

- Review the two `UNRESOLVED` and one `NOT_FOUND` representative-pilot quarters.
- Decide whether SEC request caching/checkpoint artifacts are required before the several-hour full FY2025+ run.
- Add or approve the optional Yahoo parser dependency only if Yahoo corroboration is worth operating; it is not required for authority.
- Issuer release timestamps remain a future stronger-source override.

Recommended next step: review the three pilot exceptions and approve a bounded 100-company copy run before any full FY2025+ production enrichment.
