# Relative Valuation V1 Current-Snapshot Persistence

## Contract

Persistence version is `RELATIVE_VALUATION_CURRENT_SNAPSHOT_V1`; layout
fingerprint is `9ffbfa6dd1ed86be3c5858607eb3284070d7a20285f0d46799cc198ba2a6d523`.
The economic model remains `CURRENTLY_REVISED_RELATIVE_VALUATION_V1` /
`76c2974108b2c5085b7dfa102acd4bb04eea36a5267bbdb1930a2bc7dc8cb35e`.
The layer stores a current, revised, non-PIT snapshot. It is not a backtest
history and does not normalize earnings or combine valuation with quality.

## Layout

The normalized layout contains schema metadata, immutable snapshot metadata,
an active pointer, one company result, four explicit peer-scope rows, one
own-history aggregate, three component-history rows, and a bounded refresh
audit. Stable company identity is the key; ticker is evidence only. Filing
valuation history and filing Relative Position remain authoritative references
and are not duplicated.

Tables are `relative_valuation_schema_meta`, `relative_valuation_snapshot`,
`relative_valuation_active_snapshot`, `relative_valuation_company_result`,
`relative_valuation_peer_position`, `relative_valuation_own_history`,
`relative_valuation_component_history`, and
`relative_valuation_refresh_audit`. The three deliberate secondary indexes are
for model snapshot selection, peer-group scans, and bounded audit lookup.
Company and component reads use composite primary keys.

Normalized storage was selected over a wide repeated-text layout and a JSON
snapshot. It preserves independent component counts and signed current yields,
supports indexed report reads, and uses about 5.74 MB for one 2,448-company
snapshot. The Phase 11B JSON representation alone was about 24.63 MB without
relational indexes. Extending Relative Position directly was rejected because
own-history evidence and current-price valuation have different cardinality
and lifecycle semantics.

## Atomicity And Retention

`apply_snapshot()` validates model identity, result fingerprint, company set,
four peer scopes, peer formulas, three components, component percentiles, and
40/40/20 aggregation before writing. It inserts and reconciles all bulk rows in
one immediate transaction, marks the snapshot complete, switches the pointer,
then removes snapshots older than active plus immediately previous. Any error,
including after pointer change or during cleanup, rolls back the transaction.

Same as-of/source/result is a true zero-write `NO_CHANGE`. A new as-of with
identical economic bulk content leaves the immutable active snapshot unchanged
and appends only bounded `DATE_ONLY_NO_CHANGE` audit metadata. A date change
that alters price age, freshness, eligibility, or results creates a complete
new snapshot. Audit retention is 64 rows per model; bulk retention is two.

## Reader API

`RelativeValuationRepository` provides active and previous identities,
explicit snapshot metadata, active or explicit company reads, ticker lookup,
20-company/batch reads, current-universe scans, and scope/group peer scans.
Every lookup requires an explicit model fingerprint or resolves only its
explicit active pointer. It never recalculates the universe or falls back to a
different model.

## Production Status And Refresh Boundary

Phase 11D deployed and activated this persistence on 2026-09-08. The active
snapshot is `b7f786edfa7632a320df5281182761471a15281ca1c518d2d729bbfab36dc5df`.
Its source, result, and physical-content fingerprints are recorded in
`fundamentals_v4_relative_valuation_v1_phase11d_deployment.md`.

The safe refresh unit is the complete universe because one company, price,
classification, or taxonomy change can alter many ranks. The production CLI
defaults to dry-run and requires exact absolute source/destination paths,
explicit as-of, full model and persistence identities, expected content
identities, `--full-universe`, `--apply`, and `--confirm-production`. V1 uses
this protected manual refresh after a successful source refresh; no company
report request or scheduler hook triggers it.

Company Snapshot V2 reads only the active persisted snapshot. It requires an
exact date match and degrades explicitly when the pointer is absent or the
requested date differs. It does not perform a one-company recalculation.
