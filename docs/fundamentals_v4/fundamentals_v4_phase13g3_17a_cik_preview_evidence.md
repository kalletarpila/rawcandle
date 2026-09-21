# Phase 13G.3.17A CIK Preview Before/After Evidence

## Outcome

CIK Synchronization Preview now reports the actual stored-before and proposed-after representation changes for every `FORMAT_NORMALIZATION_ELIGIBLE` company. Classification, change-set semantics, Production authorization, Add Tickers behavior, and canonical data are unchanged.

Formatting-only identity changes must be reported using actual stored-before -> proposed-after values; normalized semantic equality alone is not sufficient operator evidence.

## Root Cause

The Phase 13G.3.17 audit retained raw canonical and provider-identity rows, but also derived normalized `canonical_ciks` for semantic comparison. The Markdown renderer displayed only `provider_ciks` and normalized `canonical_ciks`. Consequently, a stored value such as `1308648` was rendered as `0001308648`, making the report show two equal values while hiding the reason the row was normalization-eligible.

The actual raw values were not absent from the audit internals, but they were not transformed into an authoritative field-level mutation contract. The renderer therefore lacked explicit before/after evidence. This correction constructs that evidence in the Preview backend; neither Markdown nor UI queries a database to reconstruct it.

## Structured Result

Each formatting candidate now includes:

- `semantic_cik`: the ten-digit normalized CIK;
- `semantic_identity_change: false`;
- `representation_changes`: an ordered list of `table`, `field`, `field_identifier`, `before`, and `after` values, plus provider identity selectors where applicable.

Only fields whose stored value actually differs from the value written by the existing apply path are included. Genuine conflicts receive no safe formatting mutation evidence. The schema contract version is now `PHASE13G3_17_PROVIDER_CANONICAL_CIK_SYNC_V2`, so the historical V1 Preview cannot authorize a new Test.

The read-only live audit still derives 16 missing-CIK backfills, 86 formatting-only candidates, and zero review/conflict cases. All 86 current formatting candidates have the same six real field changes:

1. `company_cik.cik_normalized`
2. `company_cik.cik_display`
3. CIK-derived `company_cik.source_value`
4. `provider_company_identity.provider_identifier_value`
5. CIK-derived `provider_company_identity.source_value`
6. CIK-derived `company.company_key`

The implementation does not assume that uniformity. A mixed-field fixture proves that an already canonical field is omitted while the remaining unpadded field is reported.

## Report And UI

Old misleading form:

`AG / company_id=2460: FORMAT_NORMALIZATION_ELIGIBLE; provider CIK: 0001308648; canonical CIK: 0001308648`

New form includes:

`semantic CIK: 0001308648; semantic identity change: No`

and exact changes such as:

`company_cik.cik_normalized: 1308648 -> 0001308648`

`provider_company_identity.provider_identifier_value: 1308648 -> 0001308648`

`company.company_key: SEC_CIK:1308648 -> SEC_CIK:0001308648`

The complete Markdown report lists every real field mutation for every formatting candidate. The Admin UI summary shows counts plus concise before/after detail for up to three candidates and directs the operator to the complete report for the remainder.

The ambiguous label was changed to:

`Provider CIK unavailable among canonical missing-CIK cases`

The underlying count and classification semantics did not change.

## Verification

The focused and relevant suite passed 83 tests covering:

- structured formatting evidence and mixed-field filtering;
- genuine conflict and missing-CIK backfill reporting;
- zero-write Preview;
- real Preview -> Test -> Production fixture orchestration and rollback;
- Admin UI and operation report rendering;
- Add Tickers CIK propagation and conflict handling.

Python compilation and `git diff --check` passed.

The historical live Preview report was not rewritten:

- run: `20260921T063329Z_synchronize_provider_cik_236f42875bd7`
- report SHA-256: `a83b1379a3b67e373fa68e57fcdde3093369c388bcf00624dabee382d468dee4`
- report mtime: `2026-09-21 09:33:33.418491279 +0300`

No live Test on copies, Production update, Add Tickers, Refresh, or scheduler operation was run. Production databases were not changed. No candidate, backup, or phase-owned large database file was created; remaining phase-owned large files: **0**.
