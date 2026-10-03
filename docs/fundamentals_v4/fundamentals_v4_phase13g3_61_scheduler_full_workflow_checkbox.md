# Phase 13G.3.61 Scheduler Full-Workflow Checkbox

Date: 2026-10-03

## Result

The Scheduler Fundamentals Refresh mode control is now a single checkbox labeled
`Run Fundamentals Full Workflow`.

The checkbox simplifies operator interaction only. It does not weaken the existing FULL_WORKFLOW safety, approval, concurrency, or publication contracts.

## UI Change

The previous UI exposed both a `PREVIEW_ONLY` / `FULL_WORKFLOW` dropdown and a
password-style confirmation field with a reveal control. Those controls were removed.
The replacement checkbox maps directly to the existing persisted scheduler mode:

| Checkbox state | Persisted mode |
|---|---|
| Unchecked | `PREVIEW_ONLY` |
| Checked | `FULL_WORKFLOW` |

No second mode control, confirmation input, or eye/reveal control remains visible.

## Confirmation Handling

Saving an explicit unchecked-to-checked transition continues through the existing
validated config-building path. The UI supplies the existing internal
`CONFIRM_SCHEDULER_FULL_WORKFLOW` token for that transition; the token is not exposed
to the operator. Disabling Full Workflow persists `PREVIEW_ONLY` without a token.

The backend confirmation requirement was retained. Runtime orchestration and parsing
still consume the authoritative `fundamentals_refresh_mode` values without change.

## Compatibility And Reload

No config migration is required. Existing `PREVIEW_ONLY` configurations render the
checkbox unchecked, and existing `FULL_WORKFLOW` configurations render it checked.
The existing default remains `PREVIEW_ONLY`; the UI does not auto-enable Full
Workflow. `Reload config` reads persisted state and replaces any stale local checkbox
value.

Existing market checkbox values are preserved when the Fundamentals mode is saved.
The Run now action and scheduler summary/status display were not changed.

## Unchanged Safety Gates

The Phase 13G.3.59 gates remain in the scheduler runtime rather than the presentation
control. Preview and Test completion, blocker and quarantine handling, human-only
approval, Test/Production binding, publication recovery state, writer concurrency,
taxonomy/source locks, and file-state drift checks are unchanged. No path that creates
operator approvals was added.

## Verification

Focused scheduler UI/config/runtime regression:

```text
196 passed in 42.23s
```

The focused coverage verifies both persisted states, both save directions, internal
confirmation use, removal of the old controls, reload behavior, unchanged market
selection, and the existing scheduler runtime/safety tests.

The first full-suite run exposed one pre-existing generation-migration compatibility
issue in a read-only Snapshot UI integration test: its expected metadata came from
legacy flat paths while the UI service correctly read the active generation. The test
now derives its expectation from the same authoritative active-generation resolver.
The isolated test then passed.

Final full suite:

```text
3310 passed, 8 warnings in 1186.11s (0:19:46)
```

`python3 -m compileall -q dev_tools rawcandle tests`, the direct scheduler UI module
import, and `git diff --check` all completed successfully.

## Safety

- Live scheduler mode changed: `NO`
- Production financial databases changed: `NO`
- Operational Review Queue changed: `NO`
- Live scheduler or Fundamentals workflows executed: `NO`
- systemd state altered: `NO`
- Runtime configuration, logs, databases, or reports committed: `NO`
- Git push performed: `NO`
