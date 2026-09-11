# Fundamentals V4 Phase 13D Scope

Phase 13D is the backend and CLI implementation phase for controlled Add Tickers and Fundamentals Taxonomy Update operations. It may build on the Phase 13C production foundation, but it is not authorized to silently change production economics.

## Foundation Now Available

Phase 13C activated:

- the authoritative operational universe registry;
- result dependency metadata for operational-universe-sensitive outputs;
- taxonomy source, economic and presentation dependency metadata;
- Relative Valuation compatibility checks that preserve Phase 11E non-future snapshot selection;
- rollback and second-apply evidence for the additive foundation.

Future workflows must consult this foundation instead of deriving operational membership directly from `security.active` or assuming limited taxonomy absence means provider classification is missing.

## Add Tickers Backend

Add Tickers must remain a confirmed, locked, backup-protected operation. Before any write it must produce a durable preview that identifies:

- proposed provider/company/security additions;
- ticker aliases and CIK mappings;
- fiscal calendar and fiscal year anchor requirements;
- whether the ticker joins the operational universe immediately or remains staged;
- downstream results that become dependency-incompatible until recomputed;
- exact database paths, preflight fingerprints and rollback backups.

Applying Add Tickers must not reuse stale universe-sensitive Relative Position or Relative Valuation results as coherent. If the operational universe changes, affected results need explicit invalidation, compatible recomputation, or a blocked state that the UI cannot present as fresh.

## Fundamentals Taxonomy Update Backend

Taxonomy Update must be separate from the top-level Datacenter/EC taxonomy scheduler page. It must preserve the distinction between broad provider/canonical sector and industry classifications and the limited curated or multi-membership taxonomy used by Fundamentals peer contexts.

Before any taxonomy write, Phase 13D must produce an immutable preview with:

- source taxonomy version and fingerprint;
- economic taxonomy fingerprint;
- presentation-only fingerprint;
- affected companies, peer groups and dependency-sensitive results;
- classification of changes as presentation-only or economically material.

Presentation-only taxonomy changes may reuse economic results if compatibility checks pass. Economically material peer-group, membership or applicability changes require coherent refresh or invalidation of dependent Relative Position and Relative Valuation outputs.

## Production Safety

Both operations must:

- require clean preflight and explicit confirmation;
- acquire the established maintenance lock;
- reject path drift and unexpected active package/snapshot drift;
- create verified online backups before writes;
- rehearse or prove rollback for modified databases;
- leave a durable artifact directory with commands, inventories and reconciliation;
- run second no-change or equivalent idempotency checks when technically applicable;
- avoid provider network access unless the operation explicitly requests and gates it.

Phase 13D should first implement backend/CLI preview and rehearsal paths. UI wiring can follow only after the backend can prove coherent state transitions and blocked-state reporting.
