# Phase 13G.3.43: AYTU Companion Classifier Fix

## Original misclassification

AYTU fiscal 2016 Q4 produced two independently deterministic missing-source
events:

- ARQ: the obsolete 2016-09-01 source key was replaced by the current
  2016-10-25 key for the same fiscal identity.
- MRQ: the 2016-06-30 row was a coherent oldest-prefix row outside the current
  source window and met the required 41-quarter boundary.

The generic companion reconciliation previously converted any differing
non-ambiguous event classes for one fiscal identity into
`COMPANION_DIMENSION_CONTRADICTION`. AYTU therefore became
`REVIEW_REQUIRED` even though both dimensions had complete and deterministic
evidence.

## Allowed pattern

The classifier now preserves the two independently proven dispositions only
when one fiscal group contains exactly two events and all of these conditions
hold:

- both ARQ and MRQ source histories are `COMPLETE` and bound to the requested
  ticker and their expected dimensions
- the events belong to different ARQ/MRQ dimensions in the same fiscal group
- one event is exactly `TRUE_SOURCE_REMOVAL` with reason
  `SAME_FISCAL_SOURCE_KEY_REPLACEMENT`
- exactly one same-fiscal replacement source key is present in the current
  source history
- the replacement event and companion event are oldest-prefix events and meet
  the minimum fiscal-window span
- the companion event is exactly coherent
  `OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW` aging and has no same-fiscal current
  key
- no third event or already ambiguous event competes in that fiscal group

The replacement source key is checked against the actual normalized source
rows, not trusted from a detached evidence field.

## Deterministic result

For the AYTU shape, the existing merge semantics now apply without being
overwritten:

- the obsolete ARQ source key is removed under same-fiscal replacement
  semantics
- the current ARQ replacement key remains authoritative
- the MRQ boundary row is retained with
  `RETAINED_OUTSIDE_SOURCE_WINDOW` provenance
- the aggregate ticker classification is `SOURCE_REMOVAL`
- `COMPANION_DIMENSION_CONTRADICTION` and its resulting review stop are absent

No canonical publication-date policy was changed. In particular, this phase
does not alter AYTU 2016 Q4 `first_public_result_date` handling.

## Narrowness and fail-closed behavior

This phase does not weaken generic companion-dimension ambiguity handling. It recognizes only the proven same-fiscal replacement plus independently valid oldest-prefix aging combination.

Incomplete acquisition, a boundary shorter than 41 quarters, a missing explicit
replacement key, multiple replacement keys, interior removal, competing events,
and unrelated companion-class disagreements continue to fail closed through
the existing review classifications.

## YYAI non-change

The fixture-sized YYAI reproduction still contains 23 missing rows:

- one MRQ oldest-prefix event meets the 41-quarter boundary
- 22 ARQ/MRQ events span only 28-40 quarters
- the 22 short events remain `BOUNDARY_FISCAL_WINDOW_TOO_SHORT`
- aggregate classification remains `REVIEW_REQUIRED`

The minimum boundary remains `MINIMUM_HISTORY_YEARS * 4 + 1`, or 41 inclusive
quarters. This phase does not provide automatic retention for short complete
provider histories.

## Tests

Focused source-window tests cover the exact AYTU replacement-plus-aging shape,
ARQ removal, MRQ retention, complete-history enforcement, short-boundary
enforcement, explicit replacement-key enforcement, generic companion
contradiction behavior, and the 23-row YYAI short-window case. Existing normal
retention fixtures continue to cover ADBE/ANAB/CPB/GIS/WHLR-equivalent coherent
41-quarter behavior.

## Remaining workflow blocker

YYAI remains the known Refresh Preview blocker. A fresh live Preview was not run
in this phase. The next live Preview should be run only as a separately
authorized read-only operation after this commit; Test and Production remain
unauthorized while YYAI is unresolved.

## Safety

- Production databases changed: `NO`
- Live workflows executed: `NO`
- Scheduler state changed: `NO`
- Retention boundary changed: `NO`
