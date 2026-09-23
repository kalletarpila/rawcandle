# Phase 13G.3.36 - Remove Tickers Production

## Authorization

Production requires an eligible durable Remove Tickers Preview and its matching successful Test on copies result. The Test result and its dedicated evidence file must agree exactly. Requested tickers, resolved company/security identities, Preview fingerprint, mutation set, identity invariants, active-universe result, TTM result, source contract, and market/taxonomy semantic binding are revalidated.

A material difference returns a stale Preview/Test outcome before publication. Production never adopts a newly calculated plan silently.

## Recovery Guard Order

The entrypoint acquires the Admin Production and scheduler lock first, then the authoritative taxonomy lock. It runs shared publication recovery before interpreting Preview or Test evidence. If recovery occurs, the invocation returns `RETRY_REQUIRED` and does not continue. A later invocation must repeat Preview, Test, and normal Production validation.

## Candidate Generation

Writable candidates are provider, canonical, and analysis only. Market uses `STABLE_SOURCE_BUNDLE`; taxonomy uses `DIRECT_LOCKED_READ` under the authoritative lock.

The canonical candidate deactivates the target security, creates the next active operational-universe version, preserves permanent company/security identity and ticker history, and reconciles TTM only to active securities. A shared company remains through its active sibling. A company with no active security leaves the current universe but retains historical quarter and identity state.

The normal full V2, Lifecycle, Valuation, Diagnostics, RP V2, and RV rebuild runs exactly once. Candidate integrity, identity, universe, TTM, derived-state absence, and Test-to-Production semantic binding must pass before backups or journal preparation.

## Publication And Recovery

Remove Tickers Production publishes only provider, canonical, and analysis under the shared durable publication/recovery contract.

Verified OLD-generation backups are created before the journal enters durable `PREPARED`. Each role replacement uses the shared fsync, fingerprint verification, and journal transition helpers. The journal is the recovery authority.

An ordinary failure before the first replacement removes a nonterminal journal, unnecessary backups, and candidates. A process crash after `PREPARED` retains only journal-required recovery material. Failure after the publication boundary restores the complete OLD provider/canonical/analysis generation. The first invocation encountering an incomplete journal restores OLD, terminalizes recovery, and returns retry-required.

Market and taxonomy remain read-only inputs and are never publication, rollback, or recovery roles.

## Postflight

Postflight independently verifies published role fingerprints and SQLite integrity, target exclusion from the active universe, inactive target security state, permanent identity and alias preservation, reviewed identity evidence, shared sibling participation, active-security TTM linkage, removed V2/RP/RV participation, and unrelated identity preservation. Postflight failure enters the same complete-generation rollback contract.

## UI

Production is visible only after an eligible current Preview and successful matching Test, and while global publication safety is clear. Ambiguous and blocked Preview results cannot authorize Test or Production. Operator outcomes distinguish completion, stale authorization, recovery retry, rollback, and technical failure.

## Tests

Fixture-only tests cover single and shared company publication, Preview/Test/source/universe drift, pre-boundary cleanup, durable `PREPARED`, partial replacement recovery, complete rollback, postflight failure, role restrictions, taxonomy contention, postflight invariants, and UI dispatch. No live workflow is executed.

## Next Phase

A fixture-sized Remove Tickers Full Workflow production-parity acceptance is mandatory after Phase 13G.3.36.
