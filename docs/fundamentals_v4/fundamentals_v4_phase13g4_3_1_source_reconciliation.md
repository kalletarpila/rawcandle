# Fundamentals V4 Phase 13G.4.3.1 Source Reconciliation

Phase 13G.4.3.1 corrects the Phase 13G.4.3 production-source provenance defect and closes the `dc_ecosystem` production path as a read-only `NO_CHANGE` verification.

## Source Contract

`data/analysis.db` is the authoritative taxonomy source for the active Datacenter taxonomy. The current active domain is `dc_ecosystem`, stored in the established `ec_*` tables for ecosystem code `DATACENTER`. The active source taxonomy version is `DC_TAXONOMY_FULL_V2_1`.

`data/fundamentals_analysis.db` consumes taxonomy/dependency state downstream. This phase verifies consumption identities only; it does not rebuild downstream packages, Relative Position, Relative Valuation or Snapshot outputs.

No taxonomy source, membership, active pointer, package pointer, Relative Position pointer, Relative Valuation identity or dependency row is changed in this phase.

## AAOI Reconciliation

The authoritative active AAOI membership is:

- domain: `dc_ecosystem`
- ecosystem: `DATACENTER`
- version: `DC_TAXONOMY_FULL_V2_1`
- path: `Networking / Optics / photonics / high-speed connectivity`
- role: `CORE`
- primary: `1`

The earlier AAOI `CORE -> EXTENDED` change remains a synthetic `TEST_ONLY_NOT_FOR_PRODUCTION` copy-lane mutation used only to prove propagation, replay and rollback in Phase 13G.4.1/13G.4.2. It must not be interpreted as the production baseline or as an authorized production taxonomy update.

## Root Cause

Phase 13G.4.3 exported the active production baseline correctly: AAOI was `CORE`. The failure came from the production guard, which treated the text pattern `AAOI` plus any `EXTENDED` row in the same CSV as test-only evidence. Active production contains valid non-AAOI `EXTENDED` memberships, so the heuristic incorrectly rejected a valid `ACTIVE_PRODUCTION_BASELINE_NO_CHANGE` export before the write boundary.

Phase 13G.4.3.1 replaces that heuristic with explicit trusted provenance:

- `ACTIVE_PRODUCTION_BASELINE_NO_CHANGE`
- `CURATED_PRODUCTION_CANDIDATE`
- `TEST_ONLY_NOT_FOR_PRODUCTION`

Provenance is fingerprinted with the candidate content and source identity. Editing a label alone cannot promote a test-only candidate into a production candidate.

## Role Matrix

This closure is read-only:

- production writable databases: none
- `data/analysis.db`: authoritative read-only taxonomy source
- `data/fundamentals_analysis.db`: read-only downstream dependency and identity verification
- canonical/provider/market: targeted read-only only when required

No production backup, restore rehearsal, rollback or full production `quick_check` is required when the write boundary is not crossed.

## Historical Record

The Phase 13G.4.3 Outcome B run remains preserved as audit evidence. It stopped before the write boundary and left production unchanged.

Future real taxonomy changes require a separately reviewed curated candidate and explicit authorization.
