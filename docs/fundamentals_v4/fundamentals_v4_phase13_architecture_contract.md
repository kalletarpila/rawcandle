# Fundamentals V4 Phase 13 Architecture Contract

Phase 13 separates three manual Fundamentals UI operations:

1. Snapshot Generation
2. Add Tickers
3. Taxonomy Update

Phase 13A selected `OUTCOME B — AUTHORITATIVE OPERATIONAL UNIVERSE WORK REQUIRED FIRST` for Add Tickers. Phase 13A.1 selected `OUTCOME B — TAXONOMY VERSIONING OR DEPENDENCY TRACKING REQUIRED FIRST` for Taxonomy Update. Phase 13B selected `OUTCOME A - UNIVERSE AND TAXONOMY DEPENDENCY FOUNDATION READY FOR PRODUCTION MIGRATION` on production-shaped copies.

The Taxonomy Update workflow must be separate from the existing top-level Scheduler Taxonomy page. The existing page orchestrates Datacenter/EC taxonomy changes. A Fundamentals Taxonomy Update view may reuse safe read-only diff, lock, backup and rollback conventions, but must not merge unrelated taxonomy concepts merely because they share a name.

`Check Taxonomy Changes` is read-only and produces an immutable preview fingerprint. `Apply Taxonomy Changes` must reference that exact preview, require explicit confirmation, acquire the maintenance lock, verify source/database fingerprints, back up every database that may change and leave the system coherent or restore all modified databases.

Presentation-only taxonomy changes do not require Relative Valuation refresh. Economically material peer-group, membership or applicability changes require coherent full-universe Relative Position and Relative Valuation refresh inside the same confirmed manual operation. A materially stale peer snapshot must not be silently displayed as coherent with the active taxonomy.

The Snapshot integration test diagnosis in Phase 13A.1 found a stale hard-coded Relative Valuation expectation, not a reader defect: report date `2026-09-12` correctly selects the active non-future `2026-09-10` Relative Valuation snapshot under the Phase 11E rule.

Phase 13B adds a candidate company-level operational universe registry and result dependency metadata before either deferred UI is allowed to mutate state. The foundation is additive: current readers must continue to operate without the new tables, while future Add Tickers and Taxonomy Update workflows must prove their intended results are compatible with the recorded operational universe and taxonomy economic fingerprints.
