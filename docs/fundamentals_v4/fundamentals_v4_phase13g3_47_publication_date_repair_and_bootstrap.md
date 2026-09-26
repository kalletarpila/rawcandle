# Phase 13G.3.47 Publication-Date Repair and Bootstrap

## Decision

Canonical ARQ winner selection now rejects an observation as publication-date
authority when its source date is before its report period end. The existing
winner order is retained among valid observations. A fiscal identity with no
valid observation fails closed.

This deliberately disqualifies the whole invalid observation as the canonical
winner, including its financial values. Canonical financial fields, provenance,
and source-date metadata currently share one observation authority; selecting
financial values from the invalid row while taking a date from another row
would create an unsupported split-authority model. A direct regression uses
different financial values in the valid and invalid revisions and proves that
the valid observation supplies both the date and the canonical financial value.

SPCB is resolved by a generic publication-date validity rule, not a
ticker-specific repair.

Add Tickers must initialize `first_public_result_date` for new historical
canonical quarters at creation time using the same canonical publication-date
authority.

## Audited Baseline

- Canonical quarters: 89,872
- Established `first_public_result_date`: 88,856
- Missing values: 1,016
- Safe bootstrap candidates: 1,015
- Repair-required rows: 1
- Affected post-bootstrap companies: 42
- Repair case: SPCB, company 2532, FY2022 Q4, quarter 89588
- Invalid current availability: 2022-05-20 before period end 2022-12-31
- Valid provider observation: 2023-04-20, last updated 2026-04-29
- Invalid provider observation: 2022-05-20, last updated 2026-09-08

## Implementation

`publication_dates.py` owns the shared date-validity, winner-selection, and
bootstrap-classification rules. Canonical reconciliation groups observations by
stable company/fiscal identity, preserves the established ordering, and picks
the first valid observation. Invalid provider observations remain untouched as
source history and are counted in reconciliation evidence.

New canonical quarter rows receive both `source_availability_date` and
`first_public_result_date` from the accepted winner. Reconciliation continues
to preserve every established `first_public_result_date` on existing rows.

The bootstrap plan binds each eligible update to quarter ID, stable fiscal
identity, current source availability, and the accepted provider winner. The
apply step updates only a still-NULL row matching that binding and otherwise
fails stale.

Refresh Preview now uses an explicit publication-date gate predicate without
weakening its other manual-trigger, source-completeness, replacement, review,
or Test-side requirements. Full Workflow stops after Preview with the bootstrap
and repair counts when Preview has not authorized Test.

## Copy-Only Acceptance

One 663,535,616-byte canonical copy was created under `/tmp`; no provider,
analysis, market, or taxonomy database was copied. The candidate was removed
after verification.

| Check | Result |
| --- | --- |
| Initial safe bootstrap candidates | 1,015 |
| Initial repair-required rows | 1 |
| Rows bootstrapped in first pass | 1,015 |
| Established values preserved | 88,856 / 88,856 |
| Bootstrap identity fingerprint unchanged | PASS |
| Bootstrap non-target canonical fingerprint unchanged | PASS |
| Bootstrap source-availability fingerprint unchanged | PASS |
| Bootstrap financial fingerprint unchanged | PASS |
| Reconciliation result | 89,871 unchanged, 1 revised |
| Invalid provider candidates recorded | 1 |
| SPCB selected date | 2023-04-20 |
| SPCB rows initialized in second pass | 1 |
| Final bootstrap candidates | 0 |
| Final repair-required rows | 0 |
| Final NULL values | 0 |
| Candidate SQLite quick check | ok |
| Candidate foreign-key errors | 0 |
| Publication-date gate authorized | YES |

The SPCB candidate ended with the original quarter ID 89588,
`source_availability_date=2023-04-20`, and
`first_public_result_date=2023-04-20`. No TTM or analysis rebuild was run as
part of the bootstrap-only step.

## Production Safety

Live database state was captured before and after copy-only acceptance. The
provider, canonical, and analysis SHA-256 hashes were identical; market and
taxonomy size and mtime were also identical. No live workflow was invoked and
the scheduler state was not changed.

- Provider SHA-256: `5663ad710809199fe1b87f8828e1110092c831469123fe9bb86d41993b46a7d7`
- Canonical SHA-256: `c5c5db991b6e24864e2ec7796638533561f8c3de4a7fedca7356a0a12e84ee62`
- Analysis SHA-256: `c6a5d4a31444801514163f558faae7ea130f8451b276a89c5a489e0a13c0bdda`

## Remaining Step

Live Production remains a separately authorized operation. Its minimal path is
to create a fresh bound plan, apply the 1,015 safe initializations, reconcile
the canonical candidate through the shared winner authority, initialize SPCB
through the same generic bootstrap contract, and atomically publish only after
the same invariants pass. This phase did not execute or authorize that write.
