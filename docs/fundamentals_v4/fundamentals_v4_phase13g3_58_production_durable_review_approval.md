# Phase 13G.3.58: Production-Durable Review Approval

Date: 2026-10-02

## Outcome

The retained-history and fiscal-identity review approvals now remain durable
through Preview and Test and are finalized only after successful Production
publication, postflight, and publication-journal commit.

Operator approval is not irreversibly consumed by Preview or Test. It remains
reusable across retries while exact evidence and the published-state binding
remain unchanged, and is finalized only after successful Production
publication.

This report supersedes the Preview-consumption lifecycle described in Phase
13G.3.56. It does not change approval eligibility, ticker-local quarantine,
ARQ authority, source-window interpretation, or global-blocker behavior.

## Live Issue And Old Lifecycle

The observed workflow approved LITS, NB, SGLY, and TRUG, completed Preview and
Test, and then stopped when the UI closed before Production. Preview had already
marked the queue rows `RESOLVED`, so a later workflow could not reuse the
approvals and returned the same items to review.

The old lifecycle was:

`OPEN -> approval -> RETRY_REEVALUATION -> Preview exact match -> RESOLVED`

That made Preview an irreversible consumption boundary despite no approved
effect having reached Production.

## New Lifecycle

The lifecycle is now:

`OPEN -> approval -> RETRY_REEVALUATION -> Preview validation -> Test validation -> Production validation -> successful publication/postflight/journal commit -> RESOLVED`

Preview re-fetches and reconstructs the existing exact retained-history or
fiscal-revision binding. A match makes the item non-blocking and includes the
stable approval fingerprint and binding in the Preview artifact. Preview keeps
the queue row in `RETRY_REEVALUATION` and excludes it from generic
`resolve_absent` processing.

Test independently re-fetches the evidence and checks both the Preview approval
artifact and the durable queue row with the existing exact matcher. Test does
not mutate or resolve the queue approval. A process/UI interruption after
Preview or Test therefore leaves one reusable operator approval rather than
creating a new approval identity.

Production performs the same durable-queue check during initial source
revalidation and again immediately before publication. This binds Production
to the approved evidence, queue item ID, approval fingerprint, identity and
locality proof, and old published-state baseline authorized by Preview and
Test.

## Finalization Boundary

After all three database roles have been published, Production postflight has
passed, and the durable publication journal has reached `COMPLETED`, Production
finalizes each applied approval. Resolution evidence records:

- Production run ID
- publication timestamp
- published-state binding before publication
- published-state binding after publication
- stable approval evidence fingerprint
- `SUCCESSFULLY_PUBLISHED` publication status

The queue then becomes `RESOLVED`. Repeating the identical finalization returns
the existing resolved row and does not add another consumption audit event.

## Failure, Rollback, And Recovery

Pre-publication failures never call approval finalization. Post-boundary
failures use the existing complete-generation rollback and likewise leave the
approval pending. Crash recovery that restores and verifies the old generation
does not mutate the queue. Once the old published-state binding is restored,
the same approval can be reused without operator action if all exact evidence
still matches. The first recovery invocation's `RETRY_REQUIRED` behavior is
unchanged.

## Drift Invalidation

The existing exact match remains fail-closed. Source keys, missing rows, source
or queue evidence fingerprints, old/current fiscal identities, source
fingerprints, ARQ companion proof, identity binding, locality proof, review
classification/reasons, queue item identity, and published-state binding must
all remain exact. A legitimate changed observation is upserted as current
evidence, invalidates the prior approval, and reopens the item as `OPEN`.
Tampered queue evidence remains unreadable/fail-closed.

## UI

An accepted unresolved item is shown as `Approved - pending publication`.
Neither retained-history nor fiscal approval is offered again while that state
is pending. The two actions remain separate before approval. `RESOLVED` appears
only after successful Production finalization; evidence drift returns the row
to ordinary open review with its approval-invalidation audit evidence.

## Tests And Safety

Focused coverage verifies queue finalization and duplicate-finalize
idempotency, Preview non-consumption, durable queue checks in Test and
Production, retained-history and TRUG fiscal approval across a Preview/Test
interruption, post-boundary rollback reuse, exact drift rejection, UI pending
publication state, ARQ-authoritative canonical behavior, and existing
publication/crash-recovery contracts.

The focused Refresh review/quarantine/UI/copy/production group passed with
`233 passed in 100.36s`. The repository-wide suite passed with `3272 passed, 8
warnings in 1145.92s`. Compile/import validation and `git diff --check` passed.

All implementation tests use fixture and temporary databases. No live workflow
was run, no production financial database or operational Review Queue was
modified, no backup was deleted, and scheduler/systemd state was unchanged.
