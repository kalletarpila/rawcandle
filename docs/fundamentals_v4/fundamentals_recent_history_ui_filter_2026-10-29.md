# Recent completed review history — 2026-10-29

Task: `FUNDAMENTALS-UI-RECENT-HISTORY-FILTER`.

Normal provider and P/B review-history panels now omit known terminal cases whose authoritative terminal date is older than two calendar months. This is a display filter, not a retention, approval, or financial policy. Current work is never filtered by age.

## Eligibility and calendar cutoff

The existing action-first model still determines current versus terminal membership. Only provider `RESOLVED` and ownership `PUBLISHED`/`SUPERSEDED` rows are eligible. OPEN, REVIEW_REQUIRED, waiting, reevaluation-pending, HELD, manual/deep, APPROVED pending publication, AUTO_CONTINUED pending publication, and unknown nonterminal states remain visible regardless of age. Accounting-boundary evidence remains untouched because its retained APPROVED record is not an authoritative terminal publication state.

The pure `recent_history.py` helper subtracts two **calendar months**, clamps the day to the target month's last day using standard-library `calendar.monthrange`, and compares calendar dates inclusively. No existing calendar-cutoff helper was found in the bounded presentation/contracts/utility inspection; there is no new dependency or 60-day approximation. Examples: 2026-10-29 → 2026-08-29; 2026-01-31 → 2025-11-30; 2024-04-30 → 2024-02-29. A terminal event on the cutoff day remains visible.

Current date and timezone-aware timestamps use UTC calendar days, consistent with existing `_utc` queue/audit timestamps. Explicit ISO dates are accepted; timezone-less datetime strings, invalid/missing dates, or uncertain terminal metadata cannot cause a row to disappear. Future dates remain visible. No first_seen, observation/fiscal date, ordinary last_seen, or approval-preparation timestamp is used as a terminal cutoff.

## Timestamp authority

| Case | Preferred existing authoritative timestamp |
| --- | --- |
| Provider RESOLVED | `resolution_at_utc`, with successful publication/consumption dates from `approval_published_at_utc` and `resolution_evidence.published_at_utc`; the most recent valid material date is used |
| Ownership PUBLISHED | `result.publication.published_at` from native postflight-completed publication metadata |
| Ownership SUPERSEDED | Exact matching `PB_OWNERSHIP_SUPERSEDED` audit event's `occurred_at_utc` |
| Ownership terminal fallback | Exact matching PUBLISHED/SUPERSEDED audit event if primary publication metadata is absent |

The ownership case reader did not expose the supersession event date. The UI service now adds transient `history_terminal_event` / `history_terminal_at_utc` display metadata from the existing shared audit table through a `mode=ro` connection. Matching requires exact case_id and the event corresponding to the row's current terminal status. Other cases and unrelated event types do not supply a cutoff.

Unavailable/malformed audit data or multiple distinct dates for the same terminal event leave its fallback date unestablished and the row visible. A malformed primary date also remains visible rather than being replaced with an older fallback. This introduces no new persisted fields, schema, audit event, or state transition.

## UI behavior and audit access

Filtering occurs only on the historical portion after existing current/history grouping. The current-case population, action eligibility, Normal/Review/Deep routing, current action counts, policy diagnostics, and backend totals are unchanged. Recent history stays collapsed. History headers explicitly count **visible recent cases** and explain: completed cases from the last two calendar months are shown, with undated/uncertain terminal records retained.

Backend readers still return complete retained history; the UI service only annotates terminal dates and does not filter its returned population. Existing technical run-history navigation, direct report/artifact paths, stored review/audit records, and immutable evidence remain available. This filter targets operational review-history cards rather than pruning technical artifact navigation. No old data is deleted, archived, repaired, or relabelled.

## Focused tests

**162 passed in 9.04 seconds** across:

```text
tests/test_fundamentals_recent_history.py
tests/test_fundamentals_operational_presentation.py
tests/test_fundamentals_review_action_first.py
tests/test_fundamentals_admin_ui.py
```

The 40 new cases cover calendar/year/month-end/leap boundaries, inclusive cutoff, UTC offsets, all current statuses remaining visible with old dates, recent/old PUBLISHED/SUPERSEDED/RESOLVED rows, recent resolution of an old case, precedence over first_seen and approval dates, missing/malformed/ambiguous timestamp safety, matching terminal-event identity, unchanged action counts, old current deep/boundary cases, visible history counts, collapsed history, rendering purity, read-only audit projection, unchanged queue bytes, and ambiguous audit fallback. Existing action-first guidance, optional approval fields, operational routing, confirmation controls, history access, and UI-service regressions remained passing. The full suite was not run.

## Current-state read-only replay

Result: **PASS**. Real Flet controls used real read-only service methods with startup recovery disabled and mutation methods guarded against invocation. A fresh source/runtime baseline was captured for this task. Replay used existing admin/production exclusion locks and a shared scheduler read lock; it did not run a workflow or modify another process's locks.

| Observation | Current result |
| --- | --- |
| UTC current date / cutoff | 2026-10-29 / 2026-08-29 |
| Provider current | FDX OPEN and RRC OPEN, visible with unchanged staged guidance and blocked approval |
| Current review / deep counts | 2 lightweight reviews; 1 saved APPROVED accounting-boundary evidence record, unchanged |
| Ownership | V1 enabled, automatic/manual/deep 0/0/0; no current ownership action |
| Provider terminal history | All 6 resolved events are recent (2026-09-27 through 2026-10-04); 6 visible, 0 omitted |
| Ownership terminal history | All 13 are recent; 10 publications on 2026-10-28/29, 3 supersession events on 2026-10-28; 13 visible, 0 omitted |
| Native state / backups | Full captured runtime/source baseline unchanged except intended UI page/service code fingerprints; all 53 backup files unchanged |

There are no currently retained old terminal rows to remove in this live population. The current-state replay therefore correctly keeps all 19 terminal rows in collapsed history; deterministic UI fixtures prove actual exclusion of older terminal rows and preservation of old active rows. No live state was artificially aged or inserted to manufacture a replay result.

Active generation remains `pb_ownership_719201a6f6f4497bb6a3e1ada35b81b6`, provider watermark `2026-10-28`, journal/postflight/recovery COMPLETED/PASSED/NOT_REQUIRED. Runtime journals, queues, databases, configuration, generations, and backup content were not mutated. Local evidence is under ignored `temp/fundamentals_recent_history_20261029/`, excluded from the commit. Replay validates the headless control tree, not a browser screenshot.

## Safety and scope

No review, approval, publication/recovery, cleanup, financial, historical freeze, provider-history, or scheduler semantics changed. No refresh, publication, approval, queue write, DB/history pruning, artifact deletion, generation/config/journal change, or backup deletion was performed. The commit contains only task-owned presentation/UI-service, test, and report files; runtime and unrelated OHLCV/research/worktree artifacts remain excluded. No push.
