# Phase 13G.3.66: Controlled Publication Application STOP Report

Date: 2026-10-05. **STOPPED before fresh SEC resolution, rehearsal or production mutation.**
Starting HEAD: `c2b02c058caba0adaba3be9a450e19ccb94d6f93`.

## Material Contract Conflict

The reviewed production writer cannot express the requested exact allowlist. A source change is required, which this task explicitly prohibits: "If source code changes appear necessary, STOP and report instead of silently mixing implementation work into the production application."

Evidence from the current implementation:

- `rawcandle/fundamentals/admin/publication_backlog_drain.py:28`: `run_backlog_drain` accepts no exact-quarter allowlist parameter.
- `publication_backlog_drain.py:65`: after acquiring the existing writer lock, it reselects **all** recent-open identities using `new_quarter_identities=[]` and `retry_max_quarters=None`.
- `publication_backlog_drain.py:90`: candidate enrichment repeats the same unrestricted recent-open selection. An external preflight allowlist would not constrain the actual writer.
- `rawcandle/fundamentals/admin/candidate_publication.py:58`: the candidate helper accepts newly created quarter identities plus a retry cap, not an operator exact allowlist. Relabelling old open quarters as NEW_THIS_REFRESH would misuse the accepted contract and still cannot constrain the current production entry point.
- `rawcandle/fundamentals/result_publication.py:693`: low-level `enrich_database` supports exact `quarter_keys`, but is not the production generation/lock/journal/backup writer. Calling it against the active finalized generation or cloning the publication orchestration into an ad hoc helper would bypass the required safety path.
- `rawcandle/cli/run_result_publication_enrichment.py:52`: the older enrichment CLI is a flat-canonical path with ticker/company/year selection, not the required exact-natural-identity immutable-generation publication path. It is not an alternative for this task.

The current writer would select **278**, not the reviewed **60**. Its extra **218** identities include all **26 existing AMBIGUOUS** cases and **162 C8** cases. Their enrichment can update authority metadata even without resolving them. This violates the task's scope and untouched-row invariants, so the normal blanket drain was not invoked.

No monkeypatch, selector substitution, candidate-row deletion, ad hoc SQL update, custom activation mechanism or source modification was used to manufacture the required scope.

## Read-Only Preflight

Active generation:
`publication_drain_20261005T064921Z_43a1e040`.

All active roles passed the existing `sqlite_verification` contract: `PRAGMA quick_check=ok`, zero foreign-key errors, exact manifest fingerprints and no WAL/SHM/journal sidecars.

| Role | SHA-256 |
| --- | --- |
| Provider | `2b3a57add8b51413d98f220d4cdd313994d1a4079f987a94796bf6a2b6db5fbb` |
| Canonical | `6fb73fe67e9d28407012ebb76e9b57951e409898b817a4eca94e58d934d4b5c2` |
| Analysis | `a8dcc37e1a0e2442dd44023b63d8c6ba91ee5fdce3ab05e2fa5407413a0355ce` |

Journal status is terminal `COMPLETED`, with `production_writes_blocked=false`; this is the **existing** 2026-10-05 drain journal, not a journal created by this task. Its SHA-256 remains `c5cb787e01c57e6d6fbd7d6c96d5ad2729799ff4744a899a90025cb2628035cf`. The active pointer remains `bd6966b371297fd7f30a850ab6b74aacabe66398a59f77b740cc432f473e246e`.

A nonblocking shared kernel-lock probe on the existing admin lock succeeded without modifying its owner text. No exclusive admin writer held that lock at the probe. This is a preflight observation, not a replacement for acquiring the production writer/scheduler lock at application time. No production lock acquisition or scheduler operation was performed.

The existing selector reproduced the exact 60-day cohort at as-of **2026-10-05**: **278**, with 53 UNRESOLVED, 199 NOT_FOUND and 26 AMBIGUOUS. All 278 overlap the 13G.3.64 audit. No date or identity scope drift was observed.

The [13G.3.65 impact artifact](fundamentals_v4_phase13g3_65_sec_recognition_impact.csv) reconstructs **60 unique allowlisted identities**: 28 EXHIBIT_QUARTER_CONTEXT and 32 ITEM202_HEADING_VARIANTS, all marked newly added and uniquely resolvable in that copy study. Every key belongs to the original reviewed audit, remains recent-open, and has a current open authority row. None is AMBIGUOUS or C8. AYTU and XRAY are excluded. Prior states in this allowlist are 28 UNRESOLVED and 32 NOT_FOUND.

This is **allowlist/scope validation only**, not fresh source-resolution eligibility. The 13G.3.65 CSV was not treated as authorization to assign timestamps.

## Execution And Counts

| Metric | Result |
| --- | --- |
| Reviewed allowlist | 60 |
| Allowlist currently recent-open | 60 |
| Allowlisted identities no longer open | 0 at read-only scope check |
| Fresh SEC candidate resolution | NOT_RUN |
| Fresh unique / unchanged / ambiguous / evidence-drift classifications | NOT_RUN |
| Production-shaped rehearsal / rehearsal row diff | NOT_RUN |
| Live production application | NOT_RUN |
| Applied | 0 |
| Prior UNRESOLVED resolved | 0 |
| Prior NOT_FOUND resolved | 0 |
| Prior AMBIGUOUS modified | 0 |
| Remaining recent-open | 278 |
| Postflight | NOT_RUN |
| New journal / rollback backups / generation | NOT_CREATED |

No fresh candidate counts or proposed acceptance timestamps are claimed. The authority timestamp invariant for a new applied set is **NOT_EVALUATED**, because there was no fresh resolver run, rehearsal or apply. Existing authority/evidence state is unchanged.

The original 278-cohort distribution remains **53 UNRESOLVED / 199 NOT_FOUND / 26 AMBIGUOUS**. All 22 true ambiguity cases, the four other ambiguous cases and all 162 C8 cases are untouched. No blanket retry or drain was run.

## Artifacts And Safety

Structured read-only runtime evidence:
`fundamental_reports/publication_drains/publication_13g366_stop_20261005T192727Z/result.json`.

[Application summary CSV](fundamentals_v4_phase13g3_66_controlled_publication_application.csv): exactly 60 rows, one per reviewed allowlist identity. Each row has `fresh_outcome=NOT_RUN`, `apply_status=NOT_RUN`, an explicit `EXACT_ALLOWLIST_UNSUPPORTED_BY_EXISTING_JOURNALED_WRITER` reason and unchanged post status. Fresh candidate/accession/timestamp/method fields are deliberately blank, not copied from stale evidence. This early STOP is not misclassified as a resolver ERROR or a fresh UNCHANGED_OPEN outcome.

All database access was read-only. No network fetch, candidate DB, rehearsal generation, production backup, authority mutation, activation or recovery call occurred. All three role hashes and pointer/journal/queue/scheduler hashes were independently rechecked after inspection and remained identical. This is an unchanged-state check, not production postflight. No source/test files were changed. Focused tests were unnecessary for a documentation-only STOP; the full suite was not run. CSV row-count/status assertions and `git diff --check` passed.

- Canonical financial content changed: NO.
- Provider/analysis content changed: NO.
- Resolver / authority policy / retry logic changed: NO.
- Active generation / publication journal changed: NO.
- Review Queue changed: NO; hash `14f4fd5a9e98c49ec55f6e36cc1c78b7ac290a2c1d789dbf5074b70d755b393f`.
- Scheduler configuration/state changed by this task: NO; config hash `3a0b74412a0fb9cf5e7a9b370e97a6d48af031d5094d53b5689669e630c9e894`.
- Refresh / scheduler / systemd executed: NO.
- Existing backups deleted or changed: NO.

The already-dirty publication journal, untracked generation files and unrelated chart work are preserved. Commit contains only this report and the 60-row CSV. Runtime evidence and the temporary read-only inspector are not committed. No push.

## Required Separate Authorization

Authorize a narrowly scoped **existing-writer exact-allowlist extension** as a separate implementation step before resuming production application. It must enforce exact natural identities and fresh uniqueness inside the existing writer lock, recheck generation and terminal journal, exclude no-longer-open/AMBIGUOUS/drift cases, retain the existing candidate-only journal/backup/immutable-activation path, and leave ordinary refresh/retry defaults unchanged. Then repeat fresh SEC revalidation, copy rehearsal and supervised live application.

This phase is **not complete as a production application**. It stopped at the explicit source-change boundary; no weaker publication mechanism was substituted.
