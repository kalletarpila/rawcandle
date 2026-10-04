# Historical Source-Window Review Horizon

Date: 2026-10-04

## Motivation and Evidence

KO investigation commits 7c43c496 and 9613dbf5 established three missing historical
source keys and a reproducible source boundary. Q2 ARQ/MRQ normal aging was proven;
Q3 MRQ remained ambiguous under the minimum 41-quarter window contract. All 79
returned rows had genuine cash revisions. A disappearance hold prevented normal
classification of these returned revisions. This policy changes operational absence
review, not the factual diagnosis of Sharadar's missing Q3 row.

Relevant prior contracts: refresh_quarantine_workflow_semantics_2026-10-04.md,
ko_retained_history_review_2026-10-04.md, and ko_raw_arq_mrq_followup_2026-10-04.md.

## Exact Policy

`historical_source_window_review_years = 3` is the default keyword configuration
on the existing refresh Preview/compare/merge APIs, recorded in Preview request
options. No new configuration store, scheduler setting or ticker whitelist exists.
An explicit zero retains the prior strict policy (also used for legacy Previews).
Invalid negative, non-integer, boolean or out-of-range horizons are rejected.

Age uses accepted source `reportperiod`, the period-end identity basis, compared
with Preview `as_of_date`. Default as-of is the UTC calendar date captured once at
Preview start. It never uses fetch time, lastupdated or ticker age. Calendar-year
subtraction clamps February 29 to February 28 in a non-leap target year.

For as-of 2026-10-04 the cutoff is 2023-10-04. Only periods strictly BEFORE the
cutoff qualify; a row ON the cutoff remains strict.

Relaxation requires COMPLETE ARQ and MRQ, a coherent oldest missing prefix,
all missing rows in that dimension older than the cutoff, no same-fiscal current
replacement, no companion conflict, no true-removal classification, and no detected
fiscal identity revision for the ticker. Short fiscal span alone no longer blocks
such a passive historical prefix. Absent history is merged from accepted rows with
unchanged financial payload and identity, retaining the existing durable
`RETAINED_OUTSIDE_SOURCE_WINDOW` status.

## What Remains Strict

Recent disappearance behavior is unchanged, including short boundary ambiguity.
Interior removal is deliberately NOT exempt, even for old rows without a known
conflict. This is the conservative interpretation of the requested prefix/window
scope; age alone does not authorize selective deletion or retention.

Same-fiscal source-key replacement, revised date/reportperiod, fiscal reclassification,
contradictory identity, incoherent chronology, incomplete history and companion
conflicts continue through existing review. TRUE_SOURCE_REMOVAL is not suppressed.
BOUNDARY_CHRONOLOGY_INCONSISTENT and COMPANION_DIMENSION_CONTRADICTION remain strict.

Only eligible historical prefix decisions formerly using
BOUNDARY_FISCAL_WINDOW_TOO_SHORT / AMBIGUOUS_SOURCE_REMOVAL or
OLDEST_PREFIX_EXPECTED_FISCAL_WINDOW gain the horizon explanation. No global code
disablement occurs, and KO has no special path.

Returned rows always enter ordinary financial/metadata comparison. The merge uses
current returned rows, not stale retained values. Reappearance, old financial revision,
new row and fiscal revision handling remain active regardless of age.

## Reporting and Binding

Events explain `RETAINED_OUTSIDE_HISTORICAL_REVIEW_HORIZON` and persist the exact
as-of, years and cutoff in retention provenance. Source-history action reports count,
oldest/newest affected period and `canonical_impact = RETAINED_HISTORY`; this impact
describes missing rows only, not other returned financial revisions in the ticker.
Preview JSON includes full policy; operational report includes policy and retained count.

Preview refresh-set fingerprint binds the policy in addition to existing source,
partition and retention fingerprints. Copy Test / Production revalidation reuses the
bound Preview as-of and years, never the later execution date. Altering the policy
invalidates binding. Legacy artifacts without policy use zero horizon and preserve
their existing fingerprint representation; they do not acquire the new rule silently.
The existing candidate writer consumes the bound merge plan, including old accepted
retained rows plus current safe revisions. No silent source deletion is introduced.

## Queue and Quarantine

Horizon-only aging produces no new OPEN item. Existing review items remain unchanged
by a fresh Preview's horizon relaxation, including status, last-seen evidence and
approval fields. The normal resolve_absent path excludes these historical items;
policy relaxation is not an operator approval or audit resolution.

Recent held items and ordinary approvals retain their prior behavior. Generic safe-peer,
local quarantine, global blockers and workflow gates are unchanged. No action was
performed on the production KO review item, and no approval was executed.

## KO Copy Rehearsal

Used the exact complete KO raw responses fetched at 2026-10-04T15:10 UTC, whose
projected fingerprints match Preview 20261004T132346Z_refresh_fundamentals_bee6f4d28686.
Copied only KO ARQ/MRQ accepted observations into a temporary SQLite database:
`/tmp/ko_horizon_rehearsal_2026-10-04.db`.
Result evidence: `/tmp/ko_horizon_rehearsal_2026-10-04.json`.

This is an offline execution of the actual Preview comparator/merge/partition on
the KO-only database copy, not a live persisted operator Preview or full discovery.

- Before (zero horizon): REVIEW_REQUIRED / AMBIGUOUS_SOURCE_REMOVAL.
- After (three years): HISTORICAL_REVISION, no held partition.
- Missing ARQ Q2, MRQ Q2 and MRQ Q3: three retained old rows; zero removals.
- 40 ARQ and 39 MRQ effective changes exposed: changed_count = 79.
- Under ARQ-primary, 40 canonical cash revisions would be visible; none applied.
- Merged history: 41 ARQ and 41 MRQ rows; retained-row raw/effective fingerprints
  exactly match their accepted originals.

The Q3 source disappearance is not newly declared proven provider truncation. It is
retained under an explicit bounded operational review policy. The previous NOT_SAFE
diagnosis remains historically valid; no retroactive approval is attached.

## Verification and Safety

Focused tests cover strict cutoff before/on/after, leap-year semantics, invalid config,
old passive prefix retention, multiple old rows, deterministic revisions, old interior
removal, key replacement, fiscal reclassification, disabled/legacy policy, queue spam
prevention, existing OPEN evidence preservation and exact Preview/Test policy binding.
Existing strict-policy tests use zero horizon to keep validating the original classifier.
Copy Test and review queue suites also retain existing stale-source protections.

Relevant test files: test_historical_source_window_horizon.py,
test_fundamentals_admin_source_window_retention.py,
test_fundamentals_admin_refresh_preview.py,
test_fundamentals_admin_refresh_copy_test.py,
test_fundamentals_admin_refresh_review_queue.py, and test_candidate_publication.py.
No unrelated score/valuation/DC or full repository suite was run.
Final focused run: **143 passed in 17.15 seconds**. `git diff --check`: PASS.

Production provider/canonical/analysis/forecasts/queue pre/post SHA-256 hashes are equal,
recorded in the rehearsal evidence. No financial database, forecast, production review
queue, scheduler or systemd writes. Temporary test/copy databases alone were written.
No provider network requests were needed; the preserved exact fresh KO evidence was reused.

Candidate publication code and its orchestration were not edited. Existing tests retain
core candidate validation -> candidate publication enrichment -> final integrity/hash/
manifest -> activation, including PARTIAL finalizability and crash isolation.
There are no new post-activation writes.

## Decision and Next Step

`HISTORICAL_SOURCE_WINDOW_HORIZON_READY`.
Next operator step: run a fresh normal Fundamentals Preview under the default horizon,
inspect the three retained KO rows and 40-quarter cash impact, then use the existing
bound copy Test workflow. Do not approve the old KO queue item just to unlock these
revisions. Production remains a separate explicit operator decision after Test review.
