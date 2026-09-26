# Phase 13G.3.51 - Evidence-Bound Retained-History Resolution

## Decision

`ACCEPT_RETAINED_HISTORY` authorizes retention only for an exact reviewed
evidence set. It does not weaken the global source-window boundary and does
not directly modify financial databases.

The action applies to ticker-local review items whose complete ARQ/MRQ
response has a clean oldest-prefix absence shape. It is not a ticker
whitelist and it cannot authorize a true source removal.

## Eligibility

The operational review queue enables the action only when its durable row
proves all of the following:

- the item is unresolved and scoped as `TICKER_LOCAL_REVIEW`;
- company and security identity are uniquely known and stable;
- exact source keys, fiscal identities, evidence fingerprint, queue item ID,
  and published-generation binding are present;
- ARQ and MRQ evidence is complete;
- all events belong to one ticker and a clean oldest prefix;
- no same-fiscal replacement, companion-dimension, cross-ticker, identity,
  publication, or recovery conflict exists;
- reason codes are limited to the accepted rolling-window ambiguity shape.

The global `MINIMUM_QUARTER_BOUNDARY_SPAN` remains unchanged. The normal
classifier still produces the review item before approval is considered.
`CONFIRM_TRUE_SOURCE_REMOVAL` remains disabled.

## Evidence Binding

An approval is stored only in the operational review queue. Its versioned
payload binds:

- ticker and durable queue item ID;
- exact ordered source-key and fiscal-identity multisets;
- source evidence fingerprint;
- published-generation reference;
- review scope, class, reasons, identity, and locality proof;
- action and resolution contract version;
- originating review run and queue status at approval;
- operator timestamp, source, and optional comment.

The approval evidence receives its own deterministic fingerprint. A boolean
approval is not sufficient.

## Queue Lifecycle

Approval changes the item from `OPEN` or `WAITING_PROVIDER` to
`RETRY_REEVALUATION`. It does not mark the item resolved.

The next normal Preview fetches and classifies provider history again. An
exact match is consumed and recorded as `RESOLVED` with the consuming
Preview run ID. Approval, consumption, and evidence-drift invalidation are
also appended to `refresh_review_queue_audit`, preserving the original
first-seen fields and prior operator evidence.

Repeated identical approval is idempotent.

## Preview Consumption

Preview first executes normal acquisition, trust validation, identity
resolution, and source-window classification. Only a ticker-local review may
then compare against its active approval.

On an exact match, the approved missing observations enter the existing
`RETAINED_OUTSIDE_SOURCE_WINDOW` merge path. Their provenance records
`ACCEPT_RETAINED_HISTORY`, approval fingerprint, and contract version.
Other evidence continues through normal classification.

The applied approval and its exact binding are included in Preview artifacts.
Test and Production source revalidation explicitly reevaluate approved
tickers even when watermark discovery does not rediscover the old event, and
rebuild the same bound retention merge plan.

## Drift And Staleness

Approval fails closed when any source key, fiscal identity, evidence
fingerprint, published binding, stable identity, review scope, locality proof,
or reason set differs. Newly missing or differently reappearing observations
therefore cannot inherit an older approval.

When drift remains a local review, queue upsert reopens the item as `OPEN`,
clears the active approval, and appends invalidation evidence. Global or
identity ambiguity remains blocking.

## YYAI Fixture

The fixture contains 23 missing observations: 13 ARQ and 10 MRQ. One oldest
observation reaches the unchanged 41-quarter boundary and 22 observations
remain below it. Both provider dimensions are complete, the absence is a
clean prefix, and there are no identity, same-fiscal, or companion conflicts.

The verified sequence is:

1. First Preview classifies one row as normally aged out and 22 rows as
   ambiguous, queues YYAI as `OPEN`, and holds it.
2. Operator approval writes only the queue DB and changes status to
   `RETRY_REEVALUATION`.
3. Matching Preview retains all 23 observations, removes the hold, records
   approval consumption, and leaves all financial/source fixture DBs
   unchanged.
4. Test/Production source revalidation reconstructs the same 23-row merge
   plan.
5. Source-key, fiscal, identity, scope, or published-binding drift rejects the
   approval and requires a new decision.

## UI And Reporting

The Review Queue shows an enabled check-circle action only for eligible
items. Otherwise it remains disabled and its tooltip states the blocking
reason. Confirmation shows ticker, row count, classification, evidence
fingerprint, published binding, the exact-retention explanation, and an
optional operator comment.

Queue details show approval timestamp, operator evidence, approved row count,
approval fingerprint, and consumption state. Preview reports operator-reviewed
retention separately and keeps the retained-row provenance visible.

The true-source-removal action remains visible and disabled.

## Safety And Tests

No live Refresh, Test, Production, scheduler, systemd, watermark, or financial
database mutation was performed in this phase.

Focused coverage proves eligibility, global blocking, exact durable binding,
idempotence, retry lifecycle, matching consumption, all 23 retained rows,
unchanged boundary behavior, unapproved fail-closed behavior, source/fiscal/
binding/identity/scope drift, reappearance drift, audit preservation,
financial isolation, UI gating, and disabled true-source removal.

The focused Refresh review queue, source-window Preview, copy-runtime, and
Admin UI regression group passed.

## Limitations

Existing queue databases are migrated lazily on the next queue write. A
legacy row that does not yet contain the new durable queue item ID and
review-context evidence is ineligible by design. A normal subsequent Preview
can reevaluate and persist that context; this phase does not run a live
Preview or infer missing approval authority from historical reports.

The action does not confirm provider deletion, bypass acquisition, modify
financial state directly, or freeze derived V2/RP/RV outputs.
