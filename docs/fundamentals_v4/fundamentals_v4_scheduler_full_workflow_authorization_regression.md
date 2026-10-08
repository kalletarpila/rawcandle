# 13G.3.82 — Scheduler FULL_WORKFLOW authorization regression

Date: 2026-10-08. Result: **PASS — bounded source fix and isolated validation**.

Scheduler FULL_WORKFLOW incorrectly stopped at Preview because the real Preview
backend required `trigger_source == "MANUAL"` for Test eligibility. The scheduler's
explicit workflow intent was absent from the child request. This was an actual
authorization regression, not a hold, financial-data issue or PREVIEW_ONLY run.

## Failed-run evidence and mode

The supplied `/mnt/data/workflow_report(24).md` path does not exist in this execution
environment. The local original report and linked runtime metadata independently
establish the exact reported 2026-10-08 failure; no inference from today's config
was needed to determine the failed run's mode:

- `logs/stock_update_scheduler_summary_20261008T013010Z.json` records
  `fundamentals_refresh_mode = FULL_WORKFLOW`, preview enabled, changed tickers 17,
  no held tickers/global blockers/review-required items, final outcome STOPPED,
  Test/Production both not invoked, and the false `MANUAL_PREVIEW_REQUIRED` reason.
- Parent run `20261008T041927Z_refresh_fundamentals_d00eb7239fed_full_workflow_98f9c50e`
  has `request.json` with `mode = FULL_WORKFLOW`, `trigger_source = SCHEDULER`.
  Its `workflow_report.md` matches the supplied observed result: 17 safe changes,
  zero holds/blockers/reviews/fiscal identity revisions requiring review, Test NO,
  Production NOT_AUTHORIZED, zero financial writes and no published watermark.
- Linked child `20261008T041927Z_refresh_fundamentals_b2fff7588d57` preserves
  `trigger_source = SCHEDULER`, but its old request has no workflow mode.
  Preview completed successfully and the false Test gate stopped the parent.

Expected mode and actual parent mode were both **FULL_WORKFLOW**. There was no
mode-deserialization/default fallback in the scheduler runner or parent wrapper,
and no lost trigger. The missing mode was specifically at the service → Preview
backend boundary.

## Contract and decision chain

The current persisted scheduler FULL_WORKFLOW contract explicitly enables the
existing unattended workflow; it does not create operator review approvals.
The authoritative operational decision presents the backend gate and cannot
grant authorization itself.

```text
stock-update-scheduler.service --config scheduler_config.json
  → scheduler.runner.run_scheduler_config reads explicit FULL_WORKFLOW
  → _run_fundamentals_refresh_preview_post_step(config.fundamentals_refresh_mode)
  → refresh_scheduler.run_scheduler_refresh_discovery(FULL_WORKFLOW)
  → FundamentalsAdminUIService.full_workflow(trigger_source=SCHEDULER)
  → _preview_unlocked(trigger_source=SCHEDULER, workflow_mode=FULL_WORKFLOW)
  → refresh_fundamentals.run_preview: authoritative future_test_authorized
  → refresh_operational_decision: reason/action from that exact gate
  → full_workflow.run_operation_workflow: never enters Test if gate is false
  → existing successful Test/Production binding and confirmation path
```

Previously the child mode argument above did not exist. `run_preview` both denied
every scheduler request and assigned `MANUAL_PREVIEW_REQUIRED` solely because its
trigger was not MANUAL. That was the only assignment found in the targeted backend
path. Downstream code propagated it faithfully into decision, terminal summary,
report and recommended action; the parent was correct to obey the false gate.

The misleading generic prerequisite guidance in `refresh_operational_decision`
was a consequence of that producer error, not an independent authorization gate.
No valid manual-only assignment or separate legacy scheduler assignment was found.
Historical artifacts retain their original reason; no global reason-code rewrite
or general override of false authorization was introduced.

## Exact bounded fix

- Preview accepts validated `workflow_mode` (`PREVIEW_ONLY` by default or
  `FULL_WORKFLOW`). The service passes FULL_WORKFLOW from its explicit parent
  workflow call. Mode is persisted in request options, child Preview/result and
  request identity; trigger stays SCHEDULER throughout.
- Eligibility is now manual Preview **or explicit FULL_WORKFLOW**, still requiring
  a nonempty safe replacement set, no global blockers, complete discovery and the
  unchanged publication-date gate. Mode never approves a held source event.
- An otherwise eligible scheduler PREVIEW_ONLY gets the precise false-gate reason
  `SCHEDULER_PREVIEW_ONLY`. Genuine blockers/date prerequisites take precedence.
  Its decision says the stop is intentional and no authorization prerequisite
  needs resolution. The scheduler summary also says Test/Production were not
  requested. It does not instruct the operator to resolve manual Preview permission.
- Preview and terminal workflow reports show mode explicitly. FULL_WORKFLOW reports
  retain the original parent mode rather than reconstructing it from child mode
  `PREVIEW`. Existing trigger, gate, source-count and reached-stage reporting remains.

Manual Preview previously returned a true Test eligibility gate when its source
conditions passed; it still does. That eligibility is not automatic progression:
manual Preview invokes neither Test nor Production. The existing explicit manual
Test/Production actions remain. No artificial manual prerequisite was added to
make the old scheduler-only reason appear valid.

No changes were made to Production gate evaluation, copy/source binding, Review
Queue classification/resolution, fiscal approval matching, watermark advancement,
provider/canonical/analysis semantics or P/B ownership. The only decision helper
change is presentation of the intentional PREVIEW_ONLY stop.

## Isolated rehearsal and tests

The new regression fixture runs actual discovery/classification/Preview against
small temporary SQLite databases and an injected offline Sharadar client, through
the real scheduler entrypoint and real Admin service/workflow orchestration.
The safe fixture contains exactly 17 changed known tickers and established dates.
Test callbacks deliberately return a failed bounded stage after verifying the
bound authorization; they prove Test invocation without running financial copy
rebuilds or allowing any Production callback. This is not a live refresh, provider
request, full financial rebuild or successful Production-publication rehearsal.

| Scenario | Backend Test gate | Actual stage behavior |
|---|---|---|
| Scheduler FULL_WORKFLOW, 17 safe, no reviews | True | Test invoked; harness deliberately stops there |
| Scheduler PREVIEW_ONLY, same 17 safe | False: SCHEDULER_PREVIEW_ONLY | Intentional Preview stop; correct reason/action |
| Manual Preview, same 17 safe | True, unchanged eligibility | Preview only; no automatic Test/Production |
| FULL_WORKFLOW, 17 safe + proven local hold | True | Test invoked; hold remains unapproved |
| FULL_WORKFLOW, 17 safe + unapproved ARQ/MRQ fiscal identity revision | False: GLOBAL_BLOCKER_PRESENT | Stops before Test; real human-required review preserved |
| FULL_WORKFLOW, zero safe + local hold | False: NO_SAFE_CHANGES_TO_PUBLISH | No Test/Production needed |
| FULL_WORKFLOW, 17 safe + denied date prerequisite | False: PUBLICATION_DATE_PREREQUISITES | Stops before Test; mode cannot override gate |

Every fixture asserts unchanged financial file hashes, unchanged persisted watermark
and successful-run binding, no generation candidate/journal, and forbidden
Production/approval callbacks. The tests check parent and child mode/trigger,
terminal reason, report and recommendation. Invalid mode fails before I/O.

Targeted tests plus one relevant Admin refresh-workflow regression group:

```sh
pytest -q tests/test_scheduler_refresh_authorization_regression.py \
  tests/test_fundamentals_refresh_scheduler_full_workflow.py \
  tests/test_fundamentals_admin_refresh_full_workflow.py \
  tests/test_refresh_operational_decision.py
```

**61 passed in 18.15s.** The full-workflow group includes successful bound Test →
Production orchestration, no-op/review stops, false-gate refusal and retry behavior.
The decision group retains authoritative local-hold/global-blocker/false-gate
semantics. After the final scheduler-summary wording change, the two affected
PREVIEW_ONLY rehearsal cases passed again.
Four hold/blocker/date-gate cases also passed after adding explicit assertions
that the terminal report preserves the real reason and recommended action.

The initial regression run found two pre-existing tests depending on the live
config being PREVIEW_ONLY. They now explicitly seed PREVIEW_ONLY in their test
config only, so confirmation transitions are tested independently of the local
persisted FULL_WORKFLOW setting. No runtime config was changed. These failures
did not indicate shared-core impact. No full suite or broad Fundamentals group ran.

## Current scheduler and Production safety

Current `scheduler_config.json` explicitly has `fundamentals_refresh_mode =
FULL_WORKFLOW`, preview enabled, `run_time = 04:30`, timezone `Europe/Helsinki`.
The parser's missing-mode default remains PREVIEW_ONLY. The inspected user service
uses `/usr/bin/python3 /home/kalle/projects/rawcandle/rawcandle/cli/run_stock_update_scheduler.py
--config /home/kalle/projects/rawcandle/scheduler_config.json`, working directory
`/home/kalle/projects/rawcandle`; the timer has `OnCalendar=*-*-* 04:30:00` and
`Persistent=true`. Neither service/timer nor scheduler cadence was changed.

Pre/post SHA-256 comparisons passed for active provider/canonical/analysis files,
active manifest, publication journal, operational Review Queue, scheduler config,
market/taxonomy files and existing WAL state, and V1/V2 ownership registries.
Whole provider equality includes persisted refresh state/watermark. Active generation
remains `pb_quarterly_ownership_v2_20261008T080025Z`. No live queue mutation or
financial DB write, real Production refresh, scheduler catch-up, publication,
watermark advance, generation activation or systemd operation occurred.

Compact [validation evidence](fundamentals_v4_scheduler_full_workflow_authorization_validation.csv)
records scenario expectations and live before/after hashes. Temporary detailed
snapshots and test logs remain under `/tmp/scheduler_authorization_*` outside Git.
The commit contains only this bounded source fix, targeted tests and documentation;
pre-existing unrelated worktree changes are excluded. Nothing is pushed.
