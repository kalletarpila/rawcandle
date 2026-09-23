# Phase 13G.3.35 - Remove Tickers Test on Copies

## Contract

Remove Tickers Test requires the durable Preview payload and its exact plan fingerprint. Before creating writable candidates it rebuilds the plan from the current canonical, provider, analysis, market, and taxonomy state. A material difference returns `STALE_PREVIEW`; Test does not silently adopt a new plan.

Eligible classifications are `REMOVABLE_ACTIVE_SECURITY` and `SHARED_COMPANY_PRESERVE_COMPANY`. `ALREADY_ABSENT` is a clean no-op. Ambiguous identity and blocked operational-universe states stop before candidate creation.

## Candidate Mutation

The Test copy lane contains writable provider, canonical, and analysis roles. The target security is deactivated and omitted from the next active operational-universe version. Permanent company and security rows, ticker aliases, provider identity/history, reviewed identity evidence, and unrelated securities remain intact.

For a shared company, only the target security leaves active participation. The company remains represented by its other active securities. For a company with no remaining active security, the company is omitted from the next active operational universe while its permanent identity and quarter history remain stored.

TTM reconciliation is a general current-state rule: company quarter history is linked to the lowest active `security_id`. A company with no active security produces no current TTM. Multiple active securities retain the existing deterministic minimum-ID selection.

Permanent company/security identity and historical ticker evidence are preserved while current active-universe participation is removed.

## Sources And Rebuild

Market data uses `STABLE_SOURCE_BUNDLE`. Taxonomy uses `DIRECT_LOCKED_READ` with semantic version/fingerprint binding. Test creates no full market or taxonomy copy.

After canonical reconciliation, Test runs the normal full V2, Lifecycle, Valuation, Diagnostics, RP V2, and RV downstream path exactly once. It verifies candidate database integrity, active-universe exclusion, active-security TTM linkage, and absence of removed-security participation from rebuilt current-state analysis.

## Evidence And Cleanup

Durable evidence records the Preview identity, requested tickers, exact mutation set, post-mutation universe fingerprint, identity invariants, source bindings, downstream invocation counts, database health, and per-ticker derived-state checks.

Candidate databases and compact source artifacts are removed after every terminal outcome. Lightweight reports remain. UI enables Test only for a current eligible Preview and keeps Production unavailable.

Remove Tickers Test mutates candidate copies only and does not publish any live database changes.

## Tests

Focused fixtures cover single-security removal, shared-company preservation, deterministic active-security TTM reconciliation, no-op, review and blocked outcomes, stale Preview, writer contention, cleanup, source modes, UI dispatch, and production immutability. Relevant identity, source-consistency, downstream, and Admin UI regressions are run before phase closure.

## Remaining Production Work

Production publication is not implemented. A later phase must add explicit authorization from successful Test evidence, stale/replay protection, durable three-role publication and recovery, postflight validation, and rollback handling before exposing Production in the UI.
