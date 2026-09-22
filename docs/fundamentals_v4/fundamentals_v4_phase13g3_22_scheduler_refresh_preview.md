# Phase 13G.3.22 - Scheduler Refresh Preview

## Previous state

The scheduler already contained a guarded Fundamentals Refresh Preview post-step,
but the deployed `scheduler_config.json` set
`fundamentals_refresh_preview_enabled` to `false`. The dispatch path therefore
skipped the capability on every scheduled cycle.

## Invocation path

When the existing configuration flag is enabled, `run_scheduler_config()` calls
`_run_fundamentals_refresh_preview_post_step()`. That adapter calls
`run_scheduler_refresh_discovery()`, which invokes
`FundamentalsAdminUIService.preview("REFRESH_FUNDAMENTALS",
trigger_source="SCHEDULER")`. The service consequently uses the same real Refresh
Preview implementation and shared Sharadar client as Fundamentals Administration.
No scheduler-specific provider client, request pacing, or Refresh calculation was
introduced.

The deployed scheduler configuration now enables this existing post-step. The
configuration contract remains opt-in, so another configuration can explicitly
disable it and receive a structured `DISABLED` scheduler summary.

## Safety contract

Scheduled Fundamentals refresh is Preview-only. Test on copies and Production
remain operator-authorized actions.

Scheduler Preview never advances the published Fundamentals refresh watermark.
It compares current Sharadar evidence with the latest successfully published
Production watermark, writes only normal lightweight Preview evidence, and stops.
It cannot invoke Test on copies, Production update, or Full Workflow. Unknown
tickers remain outside the canonical universe for Add Tickers to handle.

The central Sharadar request limiter remains the only request-pacing authority and
continues to apply to normal requests and retries. Scheduler code adds no sleeps
and no alternate network path.

## Summary and failures

The existing scheduler summary JSON now carries explicit Refresh fields for the
Preview timestamp, published baseline, pending-change state, review-required
state, changed ticker counts, report path, concise message, and technical failure.
The Scheduler UI renders these fields in its existing latest-summary panel rather
than introducing a second report format.

Outcomes remain distinct:

- `NO_CHANGE`: Preview completed with no unpublished effective changes.
- `CHANGES_FOUND`: unpublished changes exist; manual administration is pending.
- `REVIEW_REQUIRED`: source evidence requires operator review.
- `FAILED`: Preview failed technically or provider evidence was unavailable.
- `DISABLED`: the configuration flag is off and Preview was not attempted.

Provider failures are never converted into no-change results. An incomplete or
corrupt newest relevant Preview remains an explicit error under the existing
pending-status contract; the scheduler does not create a separate watermark or
fall back to stale scheduler evidence.

## Verification

Focused tests cover enabled and disabled dispatch, real fixture-sized Preview with
fake provider transport, read-only database invariants, unchanged publication
watermark, no-change, pending changes, review-required and technical-failure
outcomes, zero Test/Production/Full Workflow calls, scheduler summary persistence,
and Scheduler UI visibility.

No live workflow or real Sharadar request was run. Production database size and
mtime evidence and scheduler systemd state were recorded before and after the
implementation.
