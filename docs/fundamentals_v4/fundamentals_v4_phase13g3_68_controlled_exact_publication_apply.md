# Phase 13G.3.68: Controlled Exact Publication Apply

Date: 2026-10-06 (Europe/Helsinki)

## Outcome: STOP Before Network or Production Mutation

The mandatory allowlist fingerprint comparison failed. The task explicitly
requires STOP if this fingerprint differs; the expected value was not silently
corrected. No live resolver, copy rehearsal or production application was run.
This is a stopped operator phase, not a successful publication.

| Evidence | Value |
| --- | --- |
| Actual HEAD | `7f7367ef5cb770becf2420fd603059b54a5fdaab` |
| Exact writer implementation | Phase 13G.3.67 is HEAD |
| Reviewed unique identities | 60 |
| Historical prior statuses in reviewed CSV | 28 UNRESOLVED, 32 NOT_FOUND |
| Expected fingerprint length | 63 hex characters |
| Actual fingerprint length | 64 hex characters |
| Fingerprint gate | FAIL |
| Fresh unique count | NOT_RUN |
| Applied / new VERIFIED | 0 / 0 |
| Rehearsal / production postflight | NOT_RUN / NOT_RUN |
| Journal / immutable activation | NOT_CHECKED / NOT_RUN |

Expected value supplied in the Phase 13G.3.68 task:

```text
4b69d8500733c1d3e3d5219458bf070dc5c8fb6b99f4082e3241413c9a99ce4
```

Actual value calculated by the committed `read_allowlist_csv` and
`allowlist_evidence` APIs from the reviewed Phase 13G.3.66 CSV:

```text
4b69d8500733c1d3e3d5219458bf070dc5c8fb6b99f4082e3241413c9a99ce4e
```

The actual value matches the complete SHA-256 recorded in the Phase 13G.3.67
report. The task value omits the final `e`. This looks like a transcription
truncation, but that inference does not authorize overriding the explicit gate.
Continuation requires confirmation of the complete reviewed fingerprint.

## Review and Worktree

HEAD and worktree were checked before execution. There were no source changes.
Existing dirty runtime journal, untracked active-generation files and unrelated
P/E research artifacts were preserved and are excluded from this docs commit.
The committed exact-allowlist contract and the original 60-row operator artifact
were read. Their 60 identities normalize successfully without duplicates.

The fingerprint gate failed before further operational preflight. Active
generation resolution, DB integrity, journal recovery, lock availability, disk
space, current cohort and per-key current authority were not measured in this
phase. Historical CSV statuses are not represented as current production state.

No read-only fresh SEC resolution was run. Therefore remaining-open counts,
fresh ambiguity/error counts, authority timestamp invariants, rehearsal diffs
and production postflight results are unavailable, not zero or PASS.

## Artifacts and Safety

The companion CSV has one row per original reviewed identity. All fresh,
selection, rehearsal and application fields are NOT_RUN; post-status is
NOT_CHECKED. Every row records `ALLOWLIST_FINGERPRINT_MISMATCH` as the stop reason.
No SEC evidence or historical candidate is presented as newly validated.

Structured runtime STOP evidence:

`fundamental_reports/publication_drains/publication_13g368_stop_20261006/result.json`

Only this Markdown report and the companion CSV are committed. The runtime
JSON is not committed. No raw SEC files were downloaded, no source or policy
changes were made, no tests or full suite were run, and no production writer,
Refresh, scheduler, recovery, backup deletion or activation was invoked.
This task made no changes to production publication/financial DBs, active
generation, Review Queue, scheduler configuration or runtime journal.
`git diff --check` and CSV identity/row-count validation passed. Nothing pushed.
