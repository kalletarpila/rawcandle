# Result-publication backlog drain

Date: 2026-10-04

## Decision and scope

Normal candidate publication now defaults to 100 RECENT_OPEN_RETRY quarters,
previously 50. NEW_THIS_REFRESH remains uncapped; VERIFIED remains excluded.
The horizon remains 60 calendar days. The previous 50-quarter production result
(97 SEC requests, 26.692 seconds) supports a bounded increase, not a runtime SLA.
Normal refresh retains its 300-second network budget.

The manual drain reuses select_candidate_scope with an unlimited retry count and
empty NEW_THIS_REFRESH, and the existing candidate publication resolver. Priority
remains MISSING, UNRESOLVED, NOT_FOUND, AMBIGUOUS; newest context first, stable
canonical identity tie-breaker. Authority hierarchy, evidence deduplication,
company transactions, financial refresh ordering and scheduler are unchanged.

## Operator commands

Read-only discovery, with no network calls or report writes:

```bash
python3 -m rawcandle.cli.result_publication_backlog_drain
```

Supervised apply, only after production authorization:

```bash
python3 -m rawcandle.cli.result_publication_backlog_drain --retry-days 60 --network-budget-seconds 1800 --apply --confirm-production
```

An isolated generation copy can be targeted with --rehearsal-root PATH.
The drain defaults to a finite 1800-second SEC network budget, serial fetching,
existing pacing/timeouts/retries, and no quarter cap. This bounds network work,
not total wall time including copying and validation. An exhausted budget or
unprocessed selection fails before activation; active production is untouched.
PARTIAL exits 2, independently of generation integrity or systemd state.

## Immutable generation and recovery

Under the existing production/scheduler lock, verify the active generation and
reselect its scope. Copy all three immutable role files into an inactive lane;
reject SQLite sidecars. Enrich only candidate canonical. Provider and analysis
hashes, and all old active files, must remain unchanged. Validate SQLite integrity
and foreign keys, create verified rollback backups, finalize candidate hashes,
prepare a new generation, and activate using the existing publication journal.
Postflight hashes must match candidate fingerprints before journal completion.

Immutable rollback backups use byte-identical copies with fsync and verification.
This narrowly addresses a proven conflict: SQLite online backup can change the
physical header hash, incompatible with generation-pointer recovery's comparison
against the original immutable file. Ordinary refresh backup behavior is unchanged.
No alternative journal/recovery model was introduced.

Journal operation is RESULT_PUBLICATION_BACKLOG_DRAIN. Preview/Test identifiers
explicitly mark publication maintenance; ordinary financial no-op rules are not
changed. Existing recovery restores the old pointer on failure. Focused crash
tests cover prepared, ready, and activated boundaries, plus ordinary postactivation
failure. For interruption, use existing journal recovery before another writer;
do not manually replace active database files. Preserve rollback backups/journal.

Run reports are fundamental_reports/publication_drains/<run_id>/result.json.
Reports distinguish attempted_current_backlog from still_open_after_attempt;
attempting every eligible row does not mean clearing legitimate open cases.

## Actual read-only discovery

Source generation:
refresh_20261004T173815Z_refresh_fundamentals_1c0cfaa31765_production_0452fc80.

- Eligible and selected for drain: 332.
- MISSING: 0; UNRESOLVED: 72; NOT_FOUND: 225; AMBIGUOUS: 35.
- Normal default would select 100 retries and leave 232 unattempted.
- Earlier 298 meant unattempted rows only: 34 previously attempted rows remain
  eligible, so actual current scope is 332, not 298.
- First ordered natural keys: (707,2027,Q1), (394,2027,Q1), (1225,2027,Q2),
  (420,2026,Q3), (412,2026,Q4).
- VERIFIED and older out-of-horizon rows are excluded.

The previous runtime scaled to 332 is approximately 177 seconds, an estimate
only. The full copy rehearsal below measured the actual supervised scope.
Dry-run artifact: /tmp/publication_drain_dry_run_2026-10-04.json.

## Live SEC copy rehearsal

Isolated root: /tmp/rawcandle_publication_drain_rehearsal_20261004.
Full result: /tmp/publication_drain_rehearsal_2026-10-04.json.

- Status PARTIAL; all 332 selected rows attempted; none unprocessed.
- New VERIFIED: 8.
- Still eligible/open: 324 = 64 UNRESOLVED + 225 NOT_FOUND + 35 AMBIGUOUS.
- SEC requests: 330 metadata + 197 documents = 527 total; one cache hit.
- Runtime: 171.974 seconds; network budget not exhausted.
- Activated copy generation: publication_drain_20261004T200007Z_0b3f603e.
- Manifest/hash, quick_check, foreign_key_check and activation postflight passed.
- No duplicate evidence hashes. Symmetric row comparisons of v4_quarter,
  v4_quarter_financials, company and security found no financial/identity changes.
- Production role hashes, forecasts DB, scheduler configuration and review queue
  were identical before/after. Production active pointer was unchanged.
- Rollback not required in rehearsal; recovery exercised separately in tests.

## Production outcome and overlap

Production apply was NOT EXECUTED. The environment approval reviewer rejected
the escalated supervisor command because it did not accept the attached task as
trusted authorization for live generation activation and backup/journal mutation.
No workaround was attempted. Explicit user confirmation was requested.

Production eligible backlog remains 332: 72 UNRESOLVED, 225 NOT_FOUND,
35 AMBIGUOUS. No production rows were attempted by this task; no production
VERIFIED rows or generation were added. Production SEC counts/runtime/postflight
are not applicable, and rollback was not required.

Production forecast overlap remains the previously validated 7-event cohort;
before/after is 7/7 because production was not changed. No new production overlap
tickers exist. The requested post-production overlap measurement is deferred
until an authorized apply; rehearsal VERIFIED counts are not production gains.

## Tests and next operation

Only relevant candidate-publication, operator-drain, generation, authority and
selected production-recovery tests were run: 71 passed, 41 deselected.
Coverage includes normal default/explicit caps, uncapped new quarters, unlimited
drain scope, ordering, VERIFIED exclusion, dry-run, empty scope, PARTIAL, finite
budget and exhausted-budget abort, deduplication, immutable source files,
manifest parity, rollback/crash recovery, and forecast/scheduler separation.
No score/valuation/DC suites were run.

Future normal refreshes use bounded 100-quarter retries, not automatic drains.
Manual drains should be justified by current dry-run counts; do not repeatedly
fetch persistent AMBIGUOUS cases merely to claim an empty backlog.

Next: obtain explicit environment approval for one production maintenance apply,
rerun dry discovery to check for drift, run the supervised apply command above,
and record production postflight plus the small read-only forecast-overlap delta.

RESULT_PUBLICATION_BACKLOG_DRAIN_NEEDS_REVISION

Implementation/rehearsal are validated; the requested production completion is
pending accepted authorization, not a resolver or immutable-generation redesign.
