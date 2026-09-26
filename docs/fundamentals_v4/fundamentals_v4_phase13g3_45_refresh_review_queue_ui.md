# Phase 13G.3.45 Refresh Review Queue UI

## Result

Fundamentals Administration now has a `Refresh Review Queue` section. It is an
operator-facing view of the durable queue introduced in Phase 13G.3.44.

The Refresh Review Queue UI is an operational view over the durable review queue. It does not modify financial data and does not replace Preview/Workflow reports as audit evidence.

## Authority and loading

- The only list authority is `fundamentals_refresh_review_queue.db` beside the
  configured Admin run root.
- The list is not loaded during page construction, activation, or run-history
  loading. The operator loads it with its own refresh button.
- Queue reads use SQLite read-only/query-only mode and one bounded list query.
- List and detail rendering do not read provider, canonical, analysis, operation
  reports, or historical run artifacts, and do not recompute evidence hashes.
- A missing queue returns `NOT_INITIALIZED`; an empty active view returns a clear
  no-quarantine state; an unreadable queue returns a controlled error without
  repair or recreation.

## List and detail

The default filter includes `OPEN`, `WAITING_PROVIDER`, and
`RETRY_REEVALUATION`. `Include resolved history` also exposes retained
`RESOLVED` audit rows.

Each row shows the ticker, queue and operator status, classification, abbreviated
evidence reference, deterministic reason summary and raw reason codes, first and
last seen timestamps/run IDs, and reevaluation state. The published-state binding
is retained as row metadata.

The selected-item panel shows persisted reason codes, fiscal identities, exact
source keys, first/latest run references, published binding, full evidence
fingerprint, operator action/evidence, and resolution evidence. Known reason codes
have fixed human-readable descriptions. Unknown codes are displayed verbatim.

## Operator actions

The view exposes only these existing operational-state actions:

- `WAIT_FOR_PROVIDER`
- `RETRY_REEVALUATION`

They update only the durable review queue through the existing Admin operation
lock. `ACCEPT_RETAINED_HISTORY` and `CONFIRM_TRUE_SOURCE_REMOVAL` are visible but
disabled. No action edits provider, canonical, or analysis financial rows.

## Verification

Focused fixtures cover active statuses, resolved filtering, known and unknown
reason rendering, YYAI-shaped stored evidence, detail rendering, both supported
actions, blocked actions, empty/missing/corrupt states, unchanged lazy history
loading, and queue-only database access.

- Compile/import validation: passed with `python3 -m py_compile`.
- Focused Admin UI and Refresh review queue tests: 70 passed.
- Live Refresh or Full Workflow execution: not run.
- Production financial databases: unchanged.
- Refresh watermark and scheduler state: unchanged.
