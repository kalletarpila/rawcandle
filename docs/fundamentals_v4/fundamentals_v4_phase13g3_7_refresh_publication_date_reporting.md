# Phase 13G.3.7: Refresh Publication-Date Reporting

## Purpose

This phase corrects Refresh Preview reporting after the one-time production
`first_public_result_date` bootstrap. It does not change canonical rebuild, date
preservation, source comparison, or Refresh publication logic.

## Production Baseline

The standalone bootstrap is complete. Production contains 88,835 canonical quarters,
88,835 established first-public dates, zero historical bootstrap-eligible rows, and
zero repair-required rows. Refresh state remains `BOOTSTRAP_BASELINE` until the first
successful normal Refresh Production publication.

## Root Cause

The old report reduced every missing canonical fiscal identity in
`publish_date_impact` to `ESTABLISH_INITIAL_DATE_USING_EXISTING_CANONICAL_POLICY`.
Some historical source revisions contain MRQ-driven fiscal identities with no ARQ
canonical winner. These rows had no source publication date and could not initialize a
canonical quarter, but the Markdown renderer treated any initialize policy as `New Q`.

The high-level source-change classification was correct. The defect was in the
publication-date impact helper and report interpretation, not in Refresh source
comparison or canonical rebuild behavior.

## Correct Semantics

- `New quarter`: a genuinely new stable canonical quarter has an ARQ winner and will
  receive its initial first-public date.
- `Preserved`: affected quarters already exist and retain their established
  first-public dates. Their current `source_availability_date` may change.
- `New quarter + preserved history`: a new quarter is initialized while established
  historical quarter dates are preserved.
- `No date impact`: affected source fiscal identities do not produce a canonical date
  change, including MRQ-only identities without an ARQ canonical winner.

Source removals do not bootstrap dates. Removed-quarter dates remain evidence where the
existing Test/rebuild contract records them, while surviving historical dates remain
preserved.

## Preview Evidence

Preview now reports explicit production date-state counters: existing quarters,
established first-public dates, historical bootstrap eligibility, preservation
applicability, repair-required count, and Preview-level expected new-quarter
initializations. An established first-public date differing from current source
availability remains valid and is not a repair condition.

Scheduler-triggered Preview uses the same reporting semantics but is informational
only and sets `future_test_authorized=false`. It does not advance the Refresh watermark.

## Live Acceptance

The corrected live manual Preview completed successfully:

- Run: `20260920T085848Z_refresh_fundamentals_0fb542ea4f44`
- Refresh-set fingerprint: `2fea98011b0268c9b714aa7abd4fcc03c7808d475ff2fda0399402caee2c0491`
- Discovery rows/source tickers: 545 / 269
- Effective changed known tickers: 71
- Unknown tickers: 191
- Review required: 0
- New Quarter / Historical Revision / New Quarter And Revision / Source Removal:
  8 / 4 / 48 / 11
- Publication-date ticker statuses: 10 New Quarter, 46 New Quarter + Preserved
  History, 15 Preserved
- Expected Preview-level new-quarter initializations: 56
- Historical established / bootstrap eligible / repair required: 88,835 / 0 / 0
- Refresh state: `BOOTSTRAP_BASELINE`; watermark absent and not advanced

Representative statuses are AI `New quarter`, GOSS `Preserved`, ABAT `New quarter +
preserved history`, and ABM `Preserved`.

Provider, canonical, and analysis SHA-256, size, and mtime_ns were identical before and
after Preview. No candidates, Test databases, backups, or publication journal were
created. The first live Test on copies remains separately authorized and was not run in
this phase.

## Verification

The relevant Refresh, date preservation, publication/recovery, workflow, scheduler,
UI, and standalone-bootstrap suite passed 302 tests. An additional canonical schema,
identity/calendar, and production-bootstrap suite passed 80 tests. There were no
skips or failures. `py_compile` and `git diff --check` passed.
