# Scheduler log Fundamentals workflow report normalization

The Fundamentals Full workflow report now participates in the scheduler log artifact list with a timestamped Markdown identity, common chronological sorting, and an explicit inline Open route. The physical report and explicit download routes remain unchanged. Run History is outside this change.

## Real 2026-10-13 reproduction

The latest scheduler summary in the configured `logs` directory references:

```
/home/kalle/projects/rawcandle/fundamental_reports/admin_runs/20261013T041843Z_refresh_fundamentals_d00eb7239fed_full_workflow_0538b308/workflow_report.md
```

Its Markdown title is `Refresh Fundamentals Full Workflow Report`; it contains the existing workflow summary, decisions, stages, publication outcome, cleanup, warnings and appended authoritative child report.

Normal stock-update/datacenter/EC source-layer `.txt`/`.log` entries are filesystem-discovered by `list_scheduler_log_files`. Before this change, `apply_scheduler_view` separately appended an untimestamped `Fundamentals full workflow report` row after those entries. That pseudo-row bypassed the artifact sort and paging, explaining its permanent bottom placement.

Its Open callback used `scheduler_fundamentals_report_url`, pointing to:

```
/fundamentals/admin/reports/20261013T041843Z_refresh_fundamentals_d00eb7239fed_full_workflow_0538b308/workflow_report.md
```

`add_fundamentals_admin_download_route` returns `FileResponse(media_type="text/markdown", content_disposition_type="attachment")`. Thus the browser download was explicitly requested by the endpoint, not caused by CSS or Markdown content.

## Timestamp and naming authority

The exact parent `result.json` binds the report directory ID, `mode=FULL_WORKFLOW` and `operation_type=REFRESH_FUNDAMENTALS`. Its persisted `completed_at_utc` is **2026-10-13T04:35:56Z**. This completion timestamp produces:

```
fundamentals_full_workflow_20261013T043556Z.md
```

The scheduler artifact normalization layer owns this canonical display name; the inline response also uses it as its filename. The physical `workflow_report.md` is not renamed, copied or rewritten, so existing workflow, child-report and download references continue to work. Explicit downloads retain their original physical filename for compatibility.

A valid timezone-aware parent completion timestamp takes precedence. If completion is unavailable/invalid but the parent has a valid persisted `started_at_utc`, that exact start timestamp is used. Values are normalized to UTC. Filesystem mtime, summary Preview timestamp, latest child timestamp and current wall clock are never timestamp authorities.

## Artifact model, ordering and paging

`scheduler_log_artifacts` merges the exact summary-referenced workflow report into the ordinary artifact collection before visible paging. The row carries canonical filename, physical path, size/mtime metadata, authoritative timestamp, `type=fundamentals_workflow_report`, readable MIME, inline Open URL, existing download URL and metadata status.

The common comparator normalizes ordinary minute/second filename timestamps and workflow timestamps to second precision, then preserves the existing suffix ordering and stable ties. It sorts newest first. Fundamentals receives no special top/bottom placement. Normal artifact names and their Open behavior are unchanged.

The merged collection uses the existing cache, Show more increments and explicit refresh. The report consumes one ordinary visible artifact slot rather than being appended outside the page limit. This change does not scan unrelated report trees or add a second report registry; discovery remains the exact report reference already supplied by the scheduler summary.

Historical reports with the untimestamped physical filename work immediately when their parent metadata is available. No migration is needed. For an existing approved report with missing, malformed, symlinked or contradictory parent metadata, the artifact remains listed as `fundamentals_full_workflow_unknown_timestamp.md`, `timestamp=None`, `metadata_status=UNKNOWN`; it sorts with unknown metadata after dated entries and remains available through paging. No timestamp is guessed. Missing/unapproved report files retain the existing safe omission behavior.

## Inline Open and explicit Download

Dedicated route:

```
/scheduler/reports/fundamentals/{run_id}
```

It resolves only the approved run's fixed `workflow_report.md`, using the existing operation report resolver. The endpoint returns the original Markdown bytes as readable plain text:

```
Content-Type: text/plain; charset=utf-8
Content-Disposition: inline; filename="fundamentals_full_workflow_20261013T043556Z.md"
X-Content-Type-Options: nosniff
```

This is the smallest safe viewer behavior: browser-readable Markdown source, no new rendering dependency, no raw HTML injection and no report reformatting. The Open callback explicitly uses Flet's supported `web_window_name="_blank"`, preserving the existing sync/async launch bridge. Normal log links still use their existing asset URLs/callbacks.

Existing Fundamentals/Admin download routes remain attachment responses; the generic Fundamentals report download and forecast Open/download routes are unchanged. No new Download button or modal was added. The new route is registered before the Flet root mount.

## Path and metadata safety

The summary reference must point to the exact recognized workflow filename and agree with the shared approved-root resolver. Symlink files/ancestors are rejected by the report-link normalization. The view endpoint accepts only a run ID and fixed workflow filename, not an arbitrary path or extension; shared run-ID traversal/root containment checks remain required. Resolved report symlinks to another filename or outside the run directory cannot enter the inline viewer. Invalid/missing paths return 404.

Parent metadata must agree with the exact run ID, workflow mode and operation. Symlinked metadata cannot supply a timestamp. Unsupported binary references are not normalized as readable workflow reports. No existing download security is loosened.

## Focused tests

```
python3 -m pytest -q tests/test_scheduler_log_workflow_report.py \
  tests/test_stock_update_scheduler_ui.py \
  tests/test_forecast_scheduler_ui.py
# 109 passed
```

Coverage includes authoritative timestamp versus altered mtime, deterministic `.md` naming, chronological position among surrounding logs, mixed minute/second ordering, historical physical filenames, missing/corrupt/unbound/naive metadata, valid start-time fallback, actual ASGI inline headers and exact body bytes, unchanged explicit attachment downloads, file/run/metadata symlinks, traversal, unsupported binary references, rendered new-tab callbacks and normal text-log callbacks. Existing scheduler UI paging/refresh tests and one directly relevant forecast artifact-view regression group passed. No full suite was run.

The restricted runner stalled AnyIO worker-thread file I/O for both the new endpoint and a minimal unchanged `FileResponse` probe. ASGI tests therefore execute file I/O inline via a test-only `anyio.to_thread.run_sync` shim while exercising real routing, response headers and body streaming. Production `FileResponse` behavior is unpatched. Existing direct-endpoint regression tests also pass.

## Real read-only result

The actual report normalized to `fundamentals_full_workflow_20261013T043556Z.md`, with the exact parent completion timestamp. Its current chronological position is **first**, followed by:

1. `ec_source_layer_usa_20261013T0418Z.txt`
2. `datacenter_pipeline_usa_20261013T0417Z.txt`
3. `stock_update_usa_20261013T0134Z.txt`
4. `stock_update_omxh_20261013T0130Z.txt`

ASGI GET validation of the real approved report returned status 200, the inline headers above and all **11,440 original bytes**. The existing download GET returned the same bytes with `text/markdown` and `attachment; filename="workflow_report.md"`.

The original report SHA-256 is unchanged:

`3c1e2863f2f396dbd76df0d624541b18fa14ec804a63d9e2029b0cd90336a70c`.

## Production invariance and scope

Before/after SHA-256 comparisons passed for **153 protected files**, covering active provider/canonical/analysis databases, active pointer, canonical journal, Review Queue, scheduler configurations, the exact workflow run artifacts and existing scheduler summaries. The scheduler runtime status also matched before/after real route validation. All comparisons passed.

No scheduler or Fundamentals execution was launched. No financial contents, publication authority, watermark, Review Queue, scheduler configuration/state, Run History records, historical reports or logs were modified/deleted. Run History implementation, Policy V1 and resolver code were not edited. Only scheduler-log UI/normalization/view routing, focused tests and this report belong in the commit; unrelated worktree changes remain excluded. Nothing is pushed.
