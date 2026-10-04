# Fundamentals candidate publication enrichment

Date: 2026-10-04

Decision: `FUNDAMENTALS_CANDIDATE_PUBLICATION_INTEGRATION_READY`

## Architecture and integration

Post-activation canonical mutation would invalidate the immutable generation SHA
recorded in its manifest. Later recovery calls activate_generation on the old
manifest and validates that SHA. This implementation leaves generations and
publication-journal recovery unchanged and never writes publication data after activation.

The shared `refresh_production.run_production_apply` path now executes:

1. Build core provider/canonical/analysis candidates.
2. Validate the complete core candidate and analysis lineage.
3. RESULT_PUBLICATION: bounded enrichment of the inactive canonical candidate.
4. Revalidate all candidate DBs and analysis lineage.
5. Recheck source state, verify old-generation backups, prepare the publication journal.
6. Finalize candidate hashes, prepare the immutable generation, activate and postflight.

The scheduler already uses this shared production path. No additional publication
timer or forecast scheduler integration is introduced. Existing production and
rehearsal orchestration remain the only callers; standalone enrichment is not invoked.

## Carry-forward and quarter IDs

Before fresh canonical construction, refresh copies the active canonical DB with
online_backup. This carries all publication authority/evidence with the DB.
`fresh_rebuild_canonical` deletes/reconstructs financial quarter/TTM tables, NOT
the publication tables. It already resynchronizes authority and evidence quarter_id
for surviving `(company_id,fiscal_year,fiscal_quarter)` keys before downstream build.
Historical evidence fingerprints and authority status/timestamp are preserved.
No historical SEC replay or new synchronization mechanism is introduced.

The core rebuild now exposes `new_quarter_identities`: the exact sorted natural-key
difference between before/after core quarter maps already computed for impact.
Ticker remains display metadata. The real canonical-rebuild parity test now carries
reviewed publication evidence through rebuild and verifies both quarter_id resyncs.

## Scope and configuration

New module: `rawcandle.fundamentals.admin.candidate_publication`.
APIs: `select_candidate_scope`, `run_candidate_publication`.
The existing `result_publication.enrich_database` accepts an optional exact
quarter_keys scope; its resolver, hierarchy, fingerprint deduplication and company
transaction boundaries are reused, not duplicated.

NEW_THIS_REFRESH selects all newly added natural keys regardless of age, with no
retry cap. VERIFIED is still excluded. RECENT_OPEN_RETRY excludes those new keys
and selects missing authority, UNRESOLVED, NOT_FOUND, AMBIGUOUS, in that order.
Within each status: descending context date then ascending stable natural key.
The recent context is max(first_public_result_date, source_availability_date),
between as_of_date minus retry_days and as_of_date inclusive. These provider dates
are scope context ONLY, never publication timestamp authority.

The existing function-keyword configuration style is used:

- `result_publication_retry_days=60`
- `result_publication_retry_max_quarters=50`

Both are optional `run_production_apply` parameters. No extra config file or timer
setting is introduced. NEW_THIS_REFRESH is processed in SQL-safe chunks of 200;
chunking does not impose a cap. Retry eligible total, selected and unselected
backlog counts are recorded separately. Resolved VERIFIED rows leave the next
selection, demonstrated in tests. Unresolved rows may remain eligible on subsequent
refreshes; there is no invented evidence retry ledger or forced resolution.
Missing/ambiguous CIK identity is reported as unprocessed selected scope, not
silently matched by ticker. Historical open rows outside the horizon are untouched.

## Network and failure isolation

Normal candidate SEC client has a 300-second request budget. Existing request
timeouts, pacing, three-attempt retries, caching and request counters remain.
Once the budget expires, remaining companies yield timeout/open results without
additional network calls. This bounds network work while processing every selected
new-quarter identity. Candidate filing-document scope is period-end through latest
selected period-end + 180 days; standalone enrichment keeps its existing scope.
The budget is a network-request deadline, not a hard whole-process wall-clock kill.

The source hierarchy and publication rules are unchanged. No Yahoo canonical fallback.
Report counters include metadata/document/total requests, retries, transients,
HTTP failures and 429s through the existing SEC stats.

Publication status is SUCCESS, PARTIAL or SKIPPED. Open NOT_FOUND/UNRESOLVED/
AMBIGUOUS results or provider failures produce PARTIAL, not core failure.
Zero selected keys produces SKIPPED without SEC requests.
Candidate-mode database errors are structural and propagate; final quick_check and
foreign_key_check also block activation on corruption. Standalone exception behavior
remains unchanged. Unexpected schema/scope errors fail before the write boundary.

Core outcome stays COMPLETED and exit code stays zero for publication PARTIAL.
Separate `completion_status=SUCCESS_WITH_PUBLICATION_PARTIAL` and the
`result_publication` object preserve the distinction. Operation report has a
Result Publication block with scope, backlog, statuses, requests and runtime.
A core failure before this stage never invokes enrichment.

## Locking and recovery

Enrichment runs with the existing refresh production lock held, writes only the
inactive candidate, and does not acquire another standalone lock. The candidate
API rejects any DB under a finalized generation_manifest.json directory.
There is no enrichment-specific production backup or journal. Existing verified
old-generation backup and refresh publication journal remain the recovery boundary.

Crash behavior:

- Before enrichment: no active writes; rebuild/discard the incomplete candidate.
- During enrichment: company transactions may exist only in the inactive candidate;
  no manifest is published, so discard/rebuild is sufficient.
- After enrichment before finalization: no active writes; candidate can be discarded.
- After final manifest/prepare but before activation: existing generation recovery
  keeps/restores the old active pointer and requires a fresh invocation.
- During/after activation: existing journal restores the complete old generation,
  with its original manifest/hashes. Publication-enriched DB hash belongs to the
  new generation from the outset, so no manifest drift is introduced.

Existing crash/recovery tests and new BEFORE/AFTER_CANDIDATE_PUBLICATION crash
tests verify these boundaries. A during-enrichment BaseException test verifies that
no active pointer exists and the inactive candidate remains SQLite-valid.

## Production-copy rehearsal

No real production refresh was fabricated. All three current production roles were
copied read-only into `/tmp/rawcandle_candidate_publication_7dnljysn`.
The canonical copy retained 16,210 authority rows and 14,100 evidence rows.
Rehearsal uses a controlled SEC timeout provider: zero real network requests.
It is NOT a demonstration of new live authoritative evidence.

Current recent-open population: 348, comprising 20 MISSING, 71 UNRESOLVED,
222 NOT_FOUND, 35 AMBIGUOUS. NEW_THIS_REFRESH in this unchanged-copy rehearsal: 0.
Deterministic retry selection: 50. Unselected retry backlog: 298.
Publication result: PARTIAL; 50 processed, 50 UNRESOLVED, zero new VERIFIED.
Enrichment runtime: 1.138 seconds, excluding copy and generation preparation.

Candidate canonical SHA before enrichment:
`bb946fdba502906b8b0131735974b0405efdf82e2f4f88fa6700e24b460db4f4`.
After enrichment:
`d76a79a44d20e2df43180003e68b14bd57551393f5d9e7357924208c63876bd7`.
Only afterward were the generation manifest and hashes finalized. Activation in
the temporary project accepted the final hash and the activated DB matched it.

Retained local audit:
`exports/fundamentals/candidate_publication_rehearsal_2026-10-04.json`.
The artifact includes scope keys, results, finalization evidence and source hashes.
Synthetic tests separately demonstrate uncapped 61-new-quarter processing scope,
the 50 retry cap, VERIFIED skipping and advancement after actual resolutions.

## Verification and safety

Focused tests only: candidate_publication, result_publication_authority,
selected refresh_production and generation crash/recovery tests. No score,
valuation, DC suite or full repository suite is run.
Final result: 61 passed, 38 deselected. Selection includes publication/candidate,
crash/recovery/rehearsal/report, production parity and completed-generation checks.

Active production provider/canonical/analysis DBs and both production manifests
have matching current before/after hashes. Canonical:
`765a5efdc601dc99c6969ef0e3fe80c2206472b91437486cf5b6b73fa8370a89`.
Forecasts current before/after SHA:
`d31d72a7ab74340a15adfc8cdf5573f64bb2b17fd2c292a515f381b056f172cc`.
These are current-run comparisons, not historical-SHA gates. No concurrent scheduler
write was detected. Forecast DB is only read for safety hashing.
Forecast research code, publication heuristics, manifests/recovery code and forecast
timer/service configuration are untouched. Existing unrelated worktree changes are retained.

## Limitations and next step

No production activation occurred, so no new forecast-overlap research is run.
Live SEC success and production publication coverage remain to be verified during
the next legitimately due normal refresh. Copy timeout results must not be reported
as production authority changes. A large unresolved high-priority backlog can
continue to consume retries; explicit reviewed operator backlog draining remains separate.

Recommended action: run the next due normal Fundamentals Preview/Test/Production
workflow. Inspect its separate Result Publication block and only then perform a
small read-only publication/forecast overlap check. Never mutate the active generation
with standalone enrichment as a workaround.
