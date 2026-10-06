# Phase 13G.3.68: Controlled Exact Publication Apply

Date: 2026-10-06 (Europe/Helsinki)

## Corrected Fingerprint: PASS

The user explicitly confirmed the complete reviewed SHA-256 after the initial
fingerprint STOP. The committed CSV parser reproduces 60 unique natural keys
and this exact value:

`4b69d8500733c1d3e3d5219458bf070dc5c8fb6b99f4082e3241413c9a99ce4e`

The previous truncated fingerprint is no longer a blocker. The initial STOP
remains historical evidence in commit `d4ab2cec0efda2ca028674998bc0ca25b4444c26`
and its runtime report; this report describes the corrected-fingerprint retry.

## Outcome: STOP Before Network or Publication

A separate existing-contract conflict prevents executing the requested operator
sequence without implementation changes. The task says to STOP if source changes
become necessary; none were made.

### 1. Fresh unique apply scope cannot be enforced independently

At `rawcandle/fundamentals/admin/candidate_publication.py:153`, exact-mode
`apply_keys` are every selected key without a preview fetch error. They are not
restricted to FRESH_UNIQUE. NO_CANDIDATE and newly ambiguous successful resolutions
use the existing apply contract, which can update authority/evidence metadata.
The Phase 13G.3.67 report explicitly describes this scope-only behavior.

The new task requires publication only for the separately reviewed FRESH_UNIQUE
set, while supplying the original 60-row CSV to the CLI. The current entry point
has no separate expected fresh apply set or in-lock assertion against that set.
Supplying a smaller CSV instead would not meet the requested original artifact
and fingerprint contract. Silently changing resolver/apply eligibility would
violate the accepted scope-only semantics.

### 2. Cross-stage frozen evidence is not a CLI contract

At `candidate_publication.py:132`, each writer invocation creates a new internal
frozen client. It reuses evidence between that invocation's preview and apply,
which correctly implements Phase 13G.3.67. It does not expose a frozen precheck
artifact for a later rehearsal and production invocation.

The CLI in `rawcandle/cli/result_publication_backlog_drain.py` accepts the
allowlist but no reviewed frozen-input artifact or expected evidence fingerprint.
It constructs its own client through the writer. Thus running the live CLI after
a separate precheck/rehearsal would fetch fresh inputs again, not enforce the
same approved accession/context set or fail on material evidence drift against
that rehearsal. The API's injectable client is not an existing reviewed CLI
artifact-handoff contract.

These are capability conflicts, not proof that current live evidence is
nonunique or that the resolver is broken. No network was run to manufacture an
answer. No monkeypatch, alternate activation, reduced operator CSV, direct SQL
or low-level enrichment against production was used.

## Read-Only Preflight

| Evidence | Result |
| --- | --- |
| Retry starting HEAD | `d4ab2cec0efda2ca028674998bc0ca25b4444c26` |
| Phase 13G.3.67 included | YES |
| Unexpected source modifications | NO |
| Reviewed normalized count / fingerprint | 60 / PASS |
| Active generation | `publication_drain_20261005T064921Z_43a1e040` |
| Provider / canonical / analysis quick_check | ok / ok / ok |
| Foreign-key violations, all three role DBs | 0 |
| All three role DB hashes against Phase 13G.3.66 | UNCHANGED |
| Current journal | COMPLETED, non-incomplete |
| Current recent-open count, as of 2026-10-06 | 231 |
| Current UNRESOLVED / NOT_FOUND / AMBIGUOUS | 41 / 170 / 20 |
| Allowlist currently SELECTED_OPEN | 43 (21 UNRESOLVED, 22 NOT_FOUND) |
| Allowlist outside current 60-day scope | 17 |
| Allowlist currently VERIFIED / AMBIGUOUS / missing | 0 / 0 / 0 |
| Required disk under existing writer check | 7661223936 bytes |
| Free disk at preflight | 699114950656 bytes |
| Fresh SEC resolution / rehearsal / production apply | NOT_RUN |
| New VERIFIED / applied | 0 / 0 |

The 60-day selector is evaluated on 2026-10-06, not backdated to reproduce the
historical 278 cohort. All original 60 remain UNRESOLVED/NOT_FOUND, but 17 are
now out of scope. Historical allowlist priors remain 28 UNRESOLVED and
32 NOT_FOUND. No retry horizon or retry behavior was changed.

Production/scheduler lock acquisition and final in-lock validation were not
performed because the source-contract STOP occurred first. A terminal journal
is reported from read-only inspection; recovery/guard machinery was not invoked.
No claim of complete operational clearance or completed live postflight is made.

## Results and Artifacts

Fresh unique/candidate/timestamp/error classifications remain NOT_RUN for the
43 eligible keys. The 17 out-of-scope keys are marked IDENTITY_OR_SCOPE_DRIFT.
The CSV distinguishes initial current scope from fresh apply selection; no key
is represented as freshly authorized. Post-status contains read-only current
authority status, not a publication result.

There was no application: prior UNRESOLVED -> VERIFIED = 0,
prior NOT_FOUND -> VERIFIED = 0, existing AMBIGUOUS modified = 0.
All original 60 remain open in the all-age sense. Fresh ambiguous/error outcomes
and authority timestamp invariants were not evaluated. No post-run cohort is
claimed because there was no production run.

Structured retry evidence is retained, uncommitted, under:

`fundamental_reports/publication_drains/publication_13g368_corrected_fingerprint_stop_20261006/result.json`

No source/test files, resolver, authority hierarchy, journal/recovery machinery,
retry settings or scheduler were changed. No production publication, Refresh,
backup creation/deletion or activation was executed. Existing dirty runtime and
research artifacts were preserved. Only this report and its 60-row CSV belong
to the docs commit; no runtime DB, JSON, raw SEC evidence or generation is staged.
Read-only comparisons also confirm pointer, journal, Review Queue and scheduler
configuration hashes unchanged against the Phase 13G.3.66 STOP evidence.
No tests or full suite were run. CSV identity checks and `git diff --check` pass.
Nothing pushed.

## Required Separate Decision

Authorize a separate operator-gating/artifact-handoff implementation, or explicitly
revise the operator sequence to the capabilities of the existing writer.
Any extension must keep None/default and current resolver/apply semantics intact:
the operator gate may constrain a reviewed apply set and bind frozen inputs,
but must not redefine publication status, authority, ambiguity or retry policy.
Until that decision, the controlled production application remains stopped.
