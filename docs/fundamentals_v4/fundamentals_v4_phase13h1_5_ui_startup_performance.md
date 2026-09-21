# Phase 13H.1.5: UI startup performance

## Scope and baseline

This phase changes UI read performance only. The audited baseline was commit
`4517f8fcde0b0a65a4625494f07006da63f37f6a` on branch
`chore/ignore-backups`, with a clean worktree.

The warm-cache baseline contained 153 Fundamentals Administration run
directories, about 225 MB of Admin artifacts, about 83 MB of `result.json`
content, 607 scheduler logs, and 57 Fundamentals reports. Before this change,
Admin history construction took about 2.60 seconds and complete fake-page
`run_app` construction took about 5.45 seconds. Pending Refresh inspection
took about 0.47 seconds.

The synchronous startup path built every tab, scanned every Admin run, parsed
every Admin `result.json`, reopened terminal run artifacts through history,
mode, and artifact helpers, scanned all runs again for pending Refresh state,
listed reports and scheduler logs, inspected taxonomy state, and invoked
`systemctl` before the initial UI was useful.

Visible history limits must also bound expensive history parsing; limiting
rows only after a complete scan is not sufficient. Unopened UI tabs must not
delay the first render. Show more must continue from prior session history
state instead of repeatedly reparsing the same historical runs.

## Deferred loading

The installed runtime is Flet 0.28.3. The implementation uses
`Page.run_task()` for a session-owned coroutine and `asyncio.to_thread()` for
blocking filesystem and subprocess work. Control changes are applied after
the thread call returns to the coroutine, not from the worker thread.

Each route owns a session-local `DeferredLoadController` with `NOT_LOADED`,
`LOADING`, `LOADED`, and `ERROR` states. Duplicate activation while loading is
ignored, a loaded route is reused, and explicit Refresh invalidates only that
route. A generation token discards stale completions. Disconnect closes all
four controllers so queued work cannot update a dead session. Errors produce
concise route-local warnings.

`run_app` now adds the tab shell before activating the selected route. Direct
routes `/scheduler`, `/taxonomy`, `/fundamentals`, `/fundamentals/admin`, and
the required `/fundamentals-admin` alias select the matching tab. Only that
route starts initial data loading. Route changes lazily activate a previously
unopened tab; returning to a loaded tab does no new work.

## Bounded histories

All four histories initially display eight rows and reveal another eight per
Show more action.

Fundamentals Administration uses an `AdminHistoryCursor`. It enumerates names
once in deterministic newest-first order, keeps its scan position and accepted
rows, and stores one small projection per processed run. It stops after eight
visible Administration rows; hidden technical rows do not count. Show more
continues to 16 and 24 without reopening processed runs. A terminal projection
parses `result.json`, request, and lightweight status at most once and uses a
report existence check. It does not read `progress_events.jsonl`. Explicit
Refresh creates a new cursor generation.

On the live warm-cache tree, the initial Admin page plus pending status opened
36 unique `result.json` paths with zero repeated result reads. The old path
attempted all 153 results for history, scanned all run results again for pending
Refresh, and reopened terminal results via multiple helpers. In an isolated
cursor fixture, initial 8 processed only the three newer hidden technical rows
plus eight qualifying runs; 8 -> 16 -> 24 added exactly eight new result reads
at each step, with no duplicate reads.

Pending Refresh retains the prior authority: the newest scheduler-triggered
Refresh Preview describes pending work relative to the published production
watermark. A newer successful no-change scheduler Preview supersedes an older
pending Preview. Candidate names eliminate unrelated operations before JSON
parsing, scanning stops at the newest relevant Preview, and projections already
read by history are shared. Corrupt newest relevant evidence is shown as an
error instead of falling back to stale pending state. No watermark is changed.

Scheduler log filename metadata is listed only when Scheduler is opened and is
cached for 8-row slicing. Show more reuses that session list; Refresh rescans.
Fundamentals report metadata follows the same rule and never reads report
contents for listing. Taxonomy inspection is deferred until its tab is opened,
keeps the selected deployment, caches the operation list, and renders 8-row
slices. No taxonomy database fact is needed for the global shell.

## Status and browser audit

The Scheduler `systemctl --user is-active` call has a two-second timeout.
`TimeoutExpired` is reported as an explicit unknown observation with a warning,
not as inactive, and `subprocess.run` performs bounded child cleanup.

The existing one-second browser-open timer was left unchanged. It opens one
localhost URL and was not the measured source of the 15-60 second unusable
window. With shell-first rendering, no reproducible failed first connection or
duplicate browser opening remained to justify a readiness-polling change.

## Informational benchmark

Environment: Python 3.10.12, Flet 0.28.3, local Linux filesystem, warm cache.
Measurements used `time.perf_counter`; no OS caches were dropped.

| Measurement | Before | After |
| --- | ---: | ---: |
| Complete synchronous fake-page initialization | 5.45 s | replaced by shell + selected load |
| Shell and selected placeholder committed | blocked by all initial reads | 0.007 s |
| Selected Admin initial data load | part of startup | 0.112 s |
| Admin history construction | 2.60 s, full scan | 0.002 s for initial cursor 8 |
| Admin Show more from 8 to 16 | repeated full request model | 0.280 s incremental warm-cache scan |
| Pending Refresh lookup | 0.47 s, all runs | newest-first bounded scan with projection reuse |

These numbers are informational and are not CI thresholds. Deterministic tests
instead prove shell-before-loader ordering, unopened-route isolation, duplicate
load suppression, stale-completion rejection, explicit reload, incremental
paging, and bounded file reads.

## Safety and verification

Focused UI tests cover deferred loading and races, Scheduler routing and timer
timeout, Admin projection/cursor behavior, pending Refresh semantics, snapshot
reports, corrupt artifacts, and symlink/path protections. Compile/import checks
and `git diff --check` are also required at closure.

The retained Add Tickers Preview
`20260921T172732Z_add_tickers_04250d2cb4f0` remains valid. The real Test binding
compares the saved V5 `source_state` with a freshly computed state. The saved
and current states compare equal, including database fingerprints, active RP/RV
identity, active taxonomy, and contract version. This phase does not modify any
binding producer or consumer. No replacement Preview is required before Test
on copies unless one of those bound sources changes later.

Production provider, canonical, analysis, market, and taxonomy database
size/mtime values remained unchanged. No scheduler state was changed, no live
workflow was run, and no phase-owned database copy or large benchmark artifact
was created.
