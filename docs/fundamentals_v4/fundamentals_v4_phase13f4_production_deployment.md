# Phase 13F.4 Structural-Regime Production Deployment Record

Outcome: `OUTCOME B - PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED`.

Date: 2026-09-13.

## Authorization And Scope

The prompt authorized production writes only after all Phase 13F.4 pre-write gates passed.
No production writes were attempted because the mandatory package/dependency identity gate did
not pass from the checked-out production code and persisted metadata.

The expected write set would have been:

- `data/fundamentals_provider.db`
- `data/fundamentals_v4.db`
- `data/fundamentals_analysis.db`

The market and taxonomy sources were confirmed as read-only sources for this phase:

- `data/osakedata.db`
- `data/analysis.db`

No network request, scheduler change, UI change, V3 work, production report overwrite, backup
restore or production activation was performed.

## Source State

- Branch: `chore/ignore-backups`
- Source commit: `080460958ab39d1484bb55ae63ef9b30c881c4c0`
- Required commits present:
  - `0804609 Integrate structural regimes into fundamentals package`
  - `6488f34 Verify structural break contract closure`
  - `7ce2eb0 Add phase 13F.3.3 structural break contract`
- Worktree before documentation: clean.
- Free space before the stopped deployment: 696G available on `/home/kalle/projects/rawcandle`
  and `/tmp`.

## Pre-Write Evidence

Production target database integrity was read-only checked:

| Database | quick_check | SHA-256 |
| --- | --- | --- |
| `data/fundamentals_provider.db` | `ok` | `410c55518c053898c7603bfd43db1d20ee9eeeb9b72f566657126562e85ac40d` |
| `data/fundamentals_v4.db` | `ok` | `cbb63e42676a3fd90f63f94ff2c123e843d7808b4afb273c264fc745c6839f2d` |
| `data/fundamentals_analysis.db` | `ok` | `3c8db26ae81d2a7d8f3e331fea6bfd3926260c6efc05f7f3b3dece06e967bdea` |

No WAL, SHM or journal sidecars were present for those three databases.

Current production scale before any write:

| Area | Current production count |
| --- | ---: |
| Provider observations | 179,914 |
| Sharadar fundamental observations | 179,914 |
| Canonical quarters | 87,328 |
| Canonical TTM rows | 87,328 |
| Structural contract tables in canonical DB | 0 |
| Score rows | 87,328 |
| Diagnostic endpoints | 87,328 |
| Diagnostic evaluations | 698,624 |
| Active Relative Position rows | 13,743 |
| Relative Valuation company rows | 4,897 |

The active operating-income manifest still records the Phase 12E ten-year package identity:

- persistence fingerprint:
  `f9621556445ef7c85f5486ea170e2366cbd356fa9283cd8528436abeab0d0d40`
- economic result fingerprint:
  `7448d7b9212ce4645cf000d6264d824f3f488cdf5d7fce3ba7f6df839c3b8e78`
- physical content fingerprint:
  `369793b4036a1e407f9721ed6a3f5f455ffc3b7e9500c8ba00ecae92b49ab31d`

The active eight-flag diagnostic package still records:

- source fingerprint:
  `dea80c48cb6aca3980ab6562ba579b80a9b73d72ec14c5289b4d53edbf74f704`
- economic result fingerprint:
  `16a0b48797e74cafb837bbeb03d83872a795827f3cef1df1c4ffe4004d631cf4`
- physical content fingerprint:
  `3d737a2c40d8e4ea985667b2b26c9f3b978bb692c2322c45f06957cd4df38b0d`

The only persisted `OPERATING_INCOME_V2` dependency row identified the old package object and
Phase 13B provenance:

```json
{"family_fingerprint":"634824f179652da81ea6f38962d9a7c87df37c0627fed089a918ce9efa83d8e9","phase":"PHASE13B_VERSIONED_UNIVERSE_TAXONOMY_DEPENDENCY_FOUNDATION"}
```

## Gate Decision

The production code path can reach the structural-aware calculation code through
`operating_income_v2.pipeline.refresh_active_package`, `phase10b.calculate` and
`operating_income_v2.rehearsal.calculate`. However, the mandatory Phase 13F.4 identity gate also
requires the deployed package manifest or deterministic referenced dependencies to persist:

- `ECONOMIC_STRUCTURAL_BREAK_CONTRACT_V1`
- structural package fingerprint
- event fingerprint
- regime or structural-source fingerprint
- canonical/TTM source fingerprint
- package economic-result fingerprint
- persistence/layout identity
- calculation as-of semantics

The inspected persisted manifest and dependency contract do not yet provide that durable
structural package/dependency identity. The model manifest is only the formula/model map, and the
`OPERATING_INCOME_V2` dependency provenance does not name the structural contract or accepted
structural fingerprints.

Because the prompt states that this gate must pass before the first production write, deployment
was stopped before backup creation, provider staging, structural event persistence, package apply,
Relative Position rebuild, Relative Valuation refresh or Snapshot smoke generation.

## Production Changes

Production data changes: none.

The following were not executed because the phase stopped at the pre-write gate:

- successor provider import
- canonical identity or TTM rebuild
- structural event/regime persistence
- package activation
- Relative Position rebuild
- manual Relative Valuation refresh
- Snapshot smoke reports
- independent production `NO_CHANGE` replay
- rollback rehearsal against Phase 13F.4 backups

No Phase 13F.4 backup set was created, because no production write boundary was entered.

## Required Correction Before Retrying

A later Phase 13F.4 retry needs a copy-only verification that persists an unambiguous structural
package/dependency identity without changing formula identities, weights, anchors or thresholds.
At minimum, the copy-only run should prove that the active package or deterministic dependency
rows record the structural contract, structural package fingerprint, event fingerprint, structural
source/regime fingerprint, operational-universe and taxonomy/classification dependencies, source
fingerprints, package economic and physical fingerprints, persistence/layout identity and
calculation as-of semantics.

Only after that copy-only evidence exists should the production deployment be retried.

Phase 13F.4.1 later classified this as an architecture-level blocker rather than a small metadata
gap: the Operating-Income V2 package rows are not fully package-namespaced, so old and
structural-aware package row generations cannot coexist safely under the current schema. The next
production deployment attempt must therefore be a separately authorized Phase 13F.4.2 only after a
copy-only redesign proves coherent package-generation identity.
