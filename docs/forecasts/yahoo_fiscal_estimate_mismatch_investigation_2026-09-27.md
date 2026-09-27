# Yahoo Fiscal Estimate Mismatch Investigation (2026-09-27)

## Scope and evidence

This investigation covered only ABVC, AEI, AIFF, AIMD, AIV, and VAI at the
production `quoteSummary/earningsTrend` boundary. Evidence came from the six
immutable failed fetches in run `ed343155a53c4e6c8dc37014c65d3c0b`, their
retained raw bodies, and two normally paced read-only live rounds. No production
row was updated and no broader acquisition was run.

Both live rounds returned HTTP 200 on the first attempt, with no Yahoo error
envelope. For every symbol the provider raw SHA-256 was identical between the
production observation and both live rounds. The anomaly is stable rather than
transient.

## Six-symbol findings

Every response contained `quoteSummary.result[0].earningsTrend`, a `trend`
list, and exactly four object rows. Every row had a valid string `period` in
the sequence `0q`, `+1q`, `0y`, `+1y`. No missing, empty, null, or non-string
period was observed.

| Symbol | Methodology | endDate states by row | Stable raw hash | Classification |
|---|---|---|---|---|
| ABVC | nongaap | 2023-06-30, null, 2023-12-31, null | `c78b82c...f2dc4` | VALID_EMPTY_ROW, partial dates |
| AEI | nongaap | null, null, null, null | `f6e8c759...7a28` | VALID_EMPTY_ROW, no dates |
| AIFF | nongaap | null, null, null, null | `f6e8c759...7a28` | VALID_EMPTY_ROW, no dates |
| AIMD | nongaap | 2007-09-30, null, 2007-12-31, null | `607e54da...59c7` | VALID_EMPTY_ROW, stale partial dates |
| AIV | gaap | null, null, 2026-12-31, null | `0aee55a3...f19f55` | VALID_EMPTY_ROW, annual date only |
| VAI | nongaap | null, null, null, null | `f6e8c759...7a28` | VALID_EMPTY_ROW, no dates |

The three structural subshapes are all-dates-null, partial quarterly/annual
dates, and annual-date-only. AIMD shares the partial-date shape but carries old
2007 dates. Semantically all six belong to the same `VALID_EMPTY_ROW` class.

## Value inventory

All four estimate sections exist as objects in all 24 rows. Their content is
the same empty provider template:

- earnings avg/low/high/yearAgo/count/growth are empty objects;
- revenue avg/low/high and analyst count are `{raw: 0, fmt: null, longFmt: "0"}`;
- revenue yearAgo/growth are empty objects;
- every EPS trend and revision field is an empty object;
- row growth is an empty object;
- earnings, revenue, EPS trend, and revision currencies are null;
- earnings analyst count is absent as a value and revenue analyst count is the
  zero placeholder.

There are 96 raw numeric zeros across the six payloads, all inside the same
four-field revenue placeholder pattern. There are zero nonzero raw values,
zero analyst-covered estimates, and zero currencies. No meaningful estimate,
trend, revision, growth, or currency value is currently being discarded.
Methodology is the only non-target module metadata present.

## Current parser behavior

The previous parser validated `period` and `endDate` before deciding whether a
row contained semantic data. The first null `endDate` therefore failed the
whole payload as `MALFORMED_OR_SCHEMA_MISMATCH`, even though every row was an
empty Yahoo template. Production correctly preserved those historical fetches,
their diagnostics, and their raw evidence; they remain unchanged.

Canonicalization itself remains strict: a row entering canonicalization still
requires a string period and ISO date. The refinement is an acquisition-level
empty-template classification before canonicalization.

## Acquisition versus fiscal linking

These payloads are valid observations of no forecast data, not usable sparse
forecasts with unresolved targets. New observations of this exact shape should
be `VALID_NO_DATA`, have no semantic snapshot or normalized estimate rows, and
produce no fiscal-link attempt. `UNRESOLVED` is not appropriate because there
is no estimate value to preserve or attach.

If a future row lacks target metadata but contains even one usable estimate,
the current refinement does not classify it as empty. It remains malformed
until a separately versioned sparse-forecast representation can preserve the
values without inventing a target. Unknown provider fields likewise prevent
empty-template suppression.

## Decision matrix

| Anomaly class | Usable estimates? | Acquisition classification | Fiscal-link behavior | Persist normalized values? |
|---|---:|---|---|---:|
| Exact observed empty template, any target metadata state | No | `VALID_NO_DATA` | No link target | No |
| Missing target metadata with usable estimates | Yes | Future `SUCCESS_WITH_DATA` sparse contract; currently `MALFORMED_OR_SCHEMA_MISMATCH` | `UNRESOLVED`, never inferred | Yes, only after versioned support |
| Structurally invalid row | Unknown/unsafe | `MALFORMED_OR_SCHEMA_MISMATCH` | No link | No |
| Normal row with period and ISO endDate | Yes | `SUCCESS_WITH_DATA` | Existing LINKED/AMBIGUOUS/UNRESOLVED rules | Yes |

For the six current cases, the recommendation changes new-fetch acquisition
classification from `MALFORMED_OR_SCHEMA_MISMATCH` to `VALID_NO_DATA`.

## Contract refinement

`parse_payload` now recognizes only the exact observed placeholder:

- module and row keys must be within the existing known contract;
- all four estimate sections must exist with their complete expected keys;
- all non-revenue values must have the observed empty/null states;
- revenue avg/low/high/count must have the exact zero/null/`"0"` wrapper;
- every trend row must match this predicate.

Any usable value, altered wrapper, missing section, extra unknown field, or
mixed payload falls through to existing strict canonicalization. Normal V1
canonical JSON and hashes are unchanged, so no contract-version bump is
required. No missing period or date is inferred.

## Fixtures

- `empty_trend_all_end_dates_null_aei.real_compact.json`: AEI/AIFF/VAI shared
  all-null-date shape.
- `empty_trend_partial_end_dates_abvc.real_compact.json`: ABVC partial-date
  shape; AIMD is the same shape with stale dates.
- `empty_trend_annual_end_date_aiv.real_compact.json`: AIV annual-date-only
  shape.

Fixture metadata records source, observation time, stable two-round evidence,
and provider raw SHA-256. Fixtures omit session, cookie, crumb, and headers.

## Tests

Focused tests lock the three observed shapes to `VALID_NO_DATA`, preserve all
endDate distinctions and four-row counts, cover a missing-period empty row,
and confirm repeated deterministic classification. Guard tests prove that
canonicalization remains strict, usable estimates with missing target metadata
remain malformed, and unknown provider fields cannot be hidden by no-data
classification. Existing normal success and semantic-hash tests remain intact.

## Re-probe and production history

The two allowed live rounds were byte-for-byte stable and exhausted the task's
live-round cap. After the source refinement, all six retained production raw
payloads were replayed read-only through the new parser and returned
`VALID_NO_DATA`. Their matching hashes prove this is the same shape observed in
both live rounds. No third live round and no production write were performed.

Production still contains the original six malformed fetch statuses as valid
historical evidence. `PRAGMA quick_check` remained `ok`.

## Scheduler recommendation

Keep the scheduler bound at 100 and keep the timer disabled until this change
is reviewed. No parser, pacing, retry, timeout, concurrency, identity, fiscal
link, PIT, database, or scheduler-bound change is otherwise needed. After
approval, the next normal 100-symbol run should observe these symbols as
`VALID_NO_DATA`; verify that no new malformed fiscal rows appear before using
the existing rollout promotion criteria.
