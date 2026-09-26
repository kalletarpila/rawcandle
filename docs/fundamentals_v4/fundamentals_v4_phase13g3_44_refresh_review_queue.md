# Phase 13G.3.44: Refresh Review Queue and Ticker Quarantine

## Contract

Refresh review outcomes now have two scopes.

- `TICKER_LOCAL_REVIEW` is accepted only when structured evidence proves that
  the problem belongs to one known company/security, both complete-history
  responses are trusted, every affected source key belongs to that ticker, and
  no identity or companion-dimension conflict can affect another ticker.
- `GLOBAL_BLOCKING_REVIEW` is the fail-closed default. Incomplete history,
  identity ambiguity, source/schema inconsistency, cross-ticker evidence, and
  any review that cannot prove locality stop the workflow.

The initial local classifier is deliberately narrow. It covers the proven
YYAI-style oldest-prefix provider anomaly: complete ARQ/MRQ transport,
chronologically coherent single-ticker events, no same-fiscal replacement, no
companion conflict, and at least one boundary below the existing 41-quarter
minimum. It does not classify from the reason-code name alone.

Ticker-local review items do not block safe Refresh updates. Their last
published state is preserved and the unresolved review remains durably visible
independent of the discovery watermark.

Global or non-isolatable review conditions continue to stop Refresh
fail-closed.

## Durable queue

The queue is a small operational SQLite database named
`fundamentals_refresh_review_queue.db` beside the configured Admin run root.
It is separate from provider observations, canonical financial tables, and
derived analysis tables.

Each ticker row records review type, reason codes, exact source keys and fiscal
identities, a deterministic evidence fingerprint, first/last seen runs and
timestamps, status, published-state reference, and operator evidence.
Repeated identical evidence updates the same ticker row. Changed evidence also
updates that row while preserving first-seen provenance.

The queue is cumulative across Refresh runs. Newly discovered local holds are
added to every previously unresolved `OPEN` or `WAITING_PROVIDER` item;
later runs do not replace the active set. Resolved rows remain in the same
table as audit history and are excluded only from the active hold set. A
four-run regression covers YYAI, a later ABC hold, repeated safe publication,
and resolving only one of the two items.

Open statuses are `OPEN`, `WAITING_PROVIDER`, and
`RETRY_REEVALUATION`. A queued ticker is added to every later Preview
evaluation set even when ordinary watermark discovery no longer returns it.
Successful Production advances only the established publication watermark; it
does not create a second queue watermark.

## Safe and held sets

Preview creates and fingerprints one deterministic partition:

- applyable safe changes;
- ticker-local held items;
- global blockers.

The partition fingerprint is part of the Refresh set fingerprint. Test and
Production recompute both source evidence and the partition. Any expansion,
shrinkage, held-to-safe transition, or local-to-global transition makes the
authorization stale. A fresh Preview is required.

Only safe histories and identities are passed to provider replacement.
Canonical rebuild treats held companies as unaffected and enforces zero
unexplained changes outside safe company IDs.

Quarantine preserves the ticker's last published provider/canonical financial
state and excludes its quarantined source evidence from mutation. It does not
freeze the entire derived analysis package. The normal full V2/RP/RV rebuild
may recompute derived outputs from preserved canonical state and shared current
inputs. RP/RV may therefore legitimately change when safe peers or universe
state change.

## Operator actions

`WAIT_FOR_PROVIDER` and `RETRY_REEVALUATION` are implemented through the
Admin UI service. They update operational queue state only. The next Preview
still performs normal source acquisition and classification.

`ACCEPT_RETAINED_HISTORY` and `CONFIRM_TRUE_SOURCE_REMOVAL` remain
explicitly blocked because safe mutation semantics have not been authorized.
No review action edits provider or canonical financial rows directly.

The UI service exposes queue listing and these actions without adding I/O to
lazy run-history projection.

## Reporting

Preview and Full Workflow evidence distinguish safe changes, held items,
global blockers, queue status, and the completed-with-holds condition. The
terminal workflow remains the conventional `COMPLETED` outcome and sets
`completed_with_review_holds=true` when unresolved local items remain.

## Acceptance

The production-parity fixture invokes
`FundamentalsAdminUIService.full_workflow()` with two safe revisions and one
YYAI-style review containing 23 missing observations: one accepted boundary
aging event and 22 events below the 41-quarter minimum.

It proves that:

- Preview authorizes the two safe changes and queues YYAI;
- Test and Production mutate only the two safe tickers;
- YYAI provider and canonical financial fingerprints are unchanged;
- the full V2/RP/RV rebuild still runs normally;
- the publication watermark advances;
- YYAI remains open and is reevaluated by a later Preview even after it falls
  outside ordinary watermark discovery;
- compact market and direct locked taxonomy sources remain in use;
- publication roles remain provider, canonical, and analysis.

A second real Full Workflow fixture makes YYAI MRQ evidence incomplete. That
case is global-blocking and stops after Preview without changing a production
fixture database.

AYTU's deterministic replacement-plus-aging pattern remains automatic
`SOURCE_HISTORY_CHANGE` behavior and never enters the queue.

## Limitations

The initial local classifier intentionally does not generalize to arbitrary
fiscal, identity, or malformed-history reviews. Additional local classes need
their own structured locality proof and acceptance fixtures. Operator approval
of retained history or true source deletion also requires a separate,
explicitly authorized mutation contract.
