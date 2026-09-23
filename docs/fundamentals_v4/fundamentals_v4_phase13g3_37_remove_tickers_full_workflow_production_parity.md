# Phase 13G.3.37 - Remove Tickers Full Workflow Production Parity

## Entry Point And Fixture

Phase 13G.3.37 proves Remove Tickers through the real Full Workflow from Preview through terminal Production behavior.

The permanent acceptance suite enters through `FundamentalsAdminUIService.full_workflow(operation_type="REMOVE_TICKERS")`. It uses the real Preview, Test on copies, full V2/RP/RV candidate builder, Production publisher, postflight, shared publication journal, rollback, recovery, and terminal cleanup. Only fixture paths, deterministic source data, and fault hooks are injected. No network or live database is used.

The fixture contains permanent company/security identities, aliases, provider identity/history, canonical quarter and TTM state, an active operational universe, market prices and classifications, active taxonomy membership, and a validated V2/Lifecycle/Valuation/Diagnostics/RP V2/RV analysis generation.

## Success Semantics

The single-security case deactivates the target security, retains company/security identity and aliases, removes the company from the current operational universe, and leaves no current TTM or derived participation.

The shared-company case deactivates only the target security, retains the active sibling and company membership, and deterministically rebinds TTM to the active sibling. Unrelated identity and current-state participation remain unchanged.

Preview creates the deterministic plan. Test consumes that exact plan and persists its mutation, identity, operational-universe, TTM, and source evidence. Production consumes the successful Test run, rebuilds fresh candidates, compares semantic Test and Production authority, and revalidates the durable Preview/Test evidence plus live provider/canonical/analysis state immediately before the first replacement.

## Sources And Publication

Preview, Test, and Production all use `STABLE_SOURCE_BUNDLE` for market and `DIRECT_LOCKED_READ` for taxonomy. Taxonomy writer contention was proven during Test downstream, Production downstream, and Production postflight. The semantic bindings remain in the child operation results and reports after compact source cleanup.

Normal Remove Tickers runtime creates no full market or taxonomy source database copies.

Publication and recovery roles remain exactly `provider`, `canonical`, and `analysis`. Market and taxonomy are never backup, replacement, rollback, or recovery roles.

## Failure And Recovery Acceptance

The suite proves that material provider drift after Preview blocks Test and never invokes Production. Canonical operational-universe drift, relevant market drift, and taxonomy version/fingerprint drift after Test stop Production before backups or publication.

An ordinary failure after durable `PREPARED` but before the first replacement removes the nonterminal journal, unnecessary backups, candidates, and compact source bundle without modifying the live fixture generation. A failure after the publication boundary restores the complete OLD provider/canonical/analysis generation and terminalizes the journal as `ROLLED_BACK`.

A simulated process crash after partial replacement leaves the durable journal recoverable. The next real Remove Tickers Production entrypoint restores the complete OLD generation, terminalizes the journal as `RECOVERED`, returns `RETRY_REQUIRED`, and does not continue the NEW mutation in that invocation.

## Cleanup And Measurements

Terminal success, rollback, and recovery leave no candidate database, compact market SQLite bundle, taxonomy copy, or held taxonomy lock. Lightweight run reports, source bindings, and terminal journal evidence remain. Unrelated artifacts are untouched.

Measured fixture database sizes were:

| Role | Bytes | KiB |
| --- | ---: | ---: |
| provider | 114,688 | 112 |
| canonical | 323,584 | 316 |
| analysis | 458,752 | 448 |
| market | 196,608 | 192 |
| taxonomy | 20,480 | 20 |

A measured single-security Full Workflow completed in approximately 2.03 seconds. Compact market bundles observed across Preview, Test, and Production were 94,208 or 151,552 bytes; the maximum was 148 KiB. No production-sized snapshot or unexpected large temporary artifact was created.

## Defect Closed

Acceptance exposed one orchestration/reporting defect after a successful Production child run: the common UI report writer routed Remove Tickers Production through the Add Tickers report renderer, whose backup evidence schema differs. The smallest fix gives Remove Tickers Preview, Test, and Production their own existing producer renderers. Source, identity, mutation, publication, and recovery behavior were not changed.

The Admin UI and run-history mode contract now expose Remove Tickers Full Workflow and recognize its Production and Full Workflow records.

## Tests

The permanent suite covers single-security and shared-company success, source modes and no-copy behavior, authorization continuity, stale Preview, stale Test, market drift, taxonomy drift, pre-boundary cleanup, complete rollback, partial-replacement recovery through the real entrypoint, taxonomy contention, identity/history preservation, current-state analytical absence, publication-role restrictions, and terminal cleanup.
