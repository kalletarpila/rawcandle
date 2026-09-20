# Phase 13G.3.16 - Self-Contained Workflow Reporting

## Scope

This phase corrects terminal reporting for Fundamentals Administration full
workflows. It changes reporting and UI summaries only. It does not change
identity acceptance, Add Tickers calculations, publication authorization,
Refresh semantics, or any production database.

## Root Cause

The full-workflow orchestrator loaded the Test child `result.json` and derived
batch counts only inside the exact `COMPLETED` status/outcome branch. A
controlled `PARTIALLY_COMPLETED` Test therefore stopped the workflow before its
structured ticker results were promoted to the workflow result. The renderer
then consumed an empty/default final batch outcome, producing zero review and
integrity counts and the generic message `Test on copies failed`.

The operator consequently had to open the Test child report to learn that 19
tickers succeeded, DRK and KRSA required review, and Production never ran.

## Reporting Contract

The orchestrator now loads each child result immediately after that stage
returns. The latest materially completed child stage is authoritative when no
later stage ran:

- Preview supplies the terminal facts when Preview blocks progression.
- Test on copies supplies them when Test stops or requires review.
- Production supplies them when Production is entered.
- Successful Production alone supplies nonzero published/added counts.

The structured terminal summary carries the stage, child status and outcome,
stop classification and reason, affected tickers, issue codes and reasons,
Test batch counts, Production entry/completion/write evidence, and recommended
next action. The Markdown renderer consumes this object; it does not scrape
child report prose.

`Tested successfully` and `Test completed` are independent from
`Published/Added`. A Test stop therefore retains its actual analytical counts
while reporting zero publication.

## Report And UI

Non-clean workflow reports now place a `Failure / Review Summary` near the top.
For an Add Tickers review stop it lists every affected ticker and its structured
reason, plus the authoritative stage, Production status, write evidence, and
operator action. Child reports remain linked as detailed supporting evidence.

The Admin UI uses the same structured terminal summary. It displays the
workflow result, completed or stopped stage, concise reason, Test success and
review counts, affected tickers, and whether Production ran.

## Production-Parity Test

An acceptance-style fixture runs the real full-workflow orchestrator through
Preview, Test on copies, and a controlled review stop. The real Test child
result contains five requested tickers, three successful Test results, and two
review/integrity cases. The test proves that Production is not called and that
the workflow report and UI receive the actual structured child facts without
Markdown parsing.

Focused coverage also verifies clean Preview-Test-Production completion,
technical Test failure, Preview blocking, Production retry/failure reporting,
and the shared Refresh terminal-reason path.

## Files Changed

- `rawcandle/fundamentals/admin/full_workflow.py`
- `rawcandle/fundamentals/admin/ui_service.py`
- `tests/test_fundamentals_admin_full_workflow.py`
- `tests/test_fundamentals_admin_refresh_full_workflow.py`
- this report

## Verification And Safety

- Focused workflow and UI tests: 61 passed.
- Broader Fundamentals Administration regression tests: 66 passed.
- Total across the two non-overlapping test selections: 127 passed.
- Historical live reports were not rewritten.
- No live Add Tickers, Refresh, or scheduler workflow was executed.
- Production databases were not modified.
- No database candidates or large test artifacts were retained.

The post-test production hashes match the generation recorded by the last
successful Refresh Production report:

- provider: `3bc3dafc75a904c196828cd5a5e181d9b99d477b7a7c1039055fd945e77acec9`
- canonical: `6265d9600c5f8a6bebe1bb29acdf460b2d5552da19d5046964bbd1755787edc7`
- analysis: `4710a274f916fcaec33d6b86e86eab0661162addf95292ebf33bb60a9549c758`

The historical 21-ticker batch remains unpublished. DRK/KRSA identity handling
is intentionally unresolved by this phase, and broader backup cleanup remains
deferred until the Add Tickers runs are finished.

## Permanent Principle

Terminal Admin workflow reports must be self-contained for operator
decision-making; child reports are supporting evidence, not a prerequisite for
understanding why the workflow stopped or failed.
