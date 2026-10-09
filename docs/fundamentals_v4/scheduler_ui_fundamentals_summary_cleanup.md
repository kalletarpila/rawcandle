# Scheduler Fundamentals summary cleanup

The old Latest summary displayed preview timestamps, invocation flags, production
run IDs, pending-change metadata, duplicate messages, and a raw report path.

The UI now displays four Fundamentals fields:

- `fundamentals_refresh_status`: existing final outcome, falling back to preview status.
- `fundamentals_refresh_mode`: existing mode.
- `fundamentals_refresh_review_required`: existing review state.
- `fundamentals_refresh_decision`: existing production decision, falling back to
  preview message or technical failure when no decision is available.

The exact workflow report supplied by `fundamentals_refresh_preview_report` appears
once at the bottom as **Fundamentals full workflow report**, with an **Open** button.
It uses the existing Fundamentals admin download route and resolver. Only a report
matching the resolver's exact path is linked; missing or invalid reports are omitted.
No report directories are scanned. Existing market, EC source-layer, and datacenter
log entries and their Open actions retain their behavior.

Validation: `venv/bin/python -m pytest tests/test_stock_update_scheduler_ui.py -q`.
The focused cases cover completed FULL_WORKFLOW, stopped, and legacy PREVIEW_ONLY
summaries; the exact four visible fields; hidden implementation metadata and raw
path; single report placement; Open resolving the exact report contents; absent and
mismatched reports; unchanged existing log links; and unchanged file contents
before and after rendering. Result: **65 passed**. The initial attempt stalled in the HTTP test client and was
stopped; the completed run invokes the existing download handler directly.
The full suite was not run.

This is a presentation-only change. Scheduler execution, configuration, refresh
behavior, authorization, persisted summaries, report generation, run history,
systemd, financial databases, and active generation are unchanged. Pre-existing
unrelated worktree changes are excluded from the commit.
