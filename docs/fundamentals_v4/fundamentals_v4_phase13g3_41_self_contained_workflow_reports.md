# Phase 13G.3.41: Self-Contained Full Workflow Reports

## Previous problem

A terminal Full Workflow report could show only aggregate counts and a link to a
child operation report. For a Preview that stopped with `REVIEW_REQUIRED`, the
operator had to open the child report to identify the affected tickers and
understand why the workflow stopped.

## Reporting contract

Terminal workflow reports are self-contained. Child operation reports remain supporting evidence and are not required to understand why the workflow stopped or completed.

The common Full Workflow reporter now keeps two explicit authority decisions:

- **Item evidence authority** selects the child whose structured result supplies
  the concise problem or review items promoted near the top of the workflow
  report.
- **Appendix source** selects the child `operation_report.md` embedded in full at
  the end of the workflow report.

The selections normally identify the same child, but they are independent.
The latest materially completed child is the default. A child with better
structured item evidence remains authoritative for item details when a later
stage adds no better evidence.

## Promoted details

For stopped, review, and failure outcomes, the workflow report includes an
`Authoritative Child Details` section. Add Tickers, Refresh Fundamentals, and
Remove Tickers child results are projected into a small common presentation
model containing, where available:

- ticker or item
- classification and reason codes
- concise reasons
- affected row or count evidence
- source, removal, or revision state
- recommended operator action

Operation-specific business decisions remain in their existing child producers.
The common reporter only normalizes their existing structured evidence; it does
not reimplement workflow rules or parse report prose.

## Appendix behavior

Every terminal report ends with `Appendix: Authoritative Child Operation Report`.
It records the source stage and run ID and embeds the selected child Markdown
without deleting or replacing the separately stored child report. Nested
workflow appendices are omitted to prevent recursive duplication.

The child Markdown file is read only while finalizing a terminal workflow
report. General run-history construction does not read, parse, or hash child
reports.

## Failure tolerance

A missing or unreadable child report produces an explicit appendix availability
message and does not change the workflow outcome. Empty, malformed, or recursive
appendix content is handled the same way. Incomplete or malformed structured
item details fall back to the existing workflow summary and an explicit
statement that structured item details were unavailable.

Structured item evidence remains useful even when the child Markdown file is
missing.

## UI and workflow non-changes

The richer `workflow_report.md` is exposed through the existing report path.
Run-history ordering, visibility, lazy loading, and 8/16/24 paging are unchanged.
Preview, Test, Production, publication, recovery, and authorization semantics
are unchanged. No live workflow or production database operation is part of
this phase.

## Verification

Focused fixture tests cover Refresh multi-item review evidence, Add Tickers and
Remove Tickers stopped reports, Preview/Test/Production authority selection,
successful reports, missing child Markdown with retained structured details,
malformed structured details, recursive appendix suppression, and preservation
of the original child report. UI regressions prove that history paging and
global newest-first ordering remain unchanged and that terminal history
projection does not read `operation_report.md` files.
