# Fundamentals V4 Phase 13G.4.3 Protected Taxonomy Production

Phase 13G.4.3 promotes `CHECK_UPDATE_TAXONOMY --taxonomy dc_ecosystem` to a protected production-capable workflow.

The phase authorizes only a true production `NO_CHANGE` verification. It does not authorize applying a nonzero taxonomy change to production.

Phase 13G.4.3 ended with Outcome B before the write boundary because candidate safety used an over-broad `AAOI` plus `EXTENDED` text heuristic. Phase 13G.4.3.1 supersedes that guard behavior with explicit fingerprinted provenance while preserving the failed run as audit evidence.

## Contract

Production mode is selected with the established taxonomy CLI:

```bash
python3 -m rawcandle.cli.run_fundamentals_admin_taxonomy --taxonomy dc_ecosystem --production
python3 -m rawcandle.cli.run_fundamentals_admin_taxonomy --taxonomy dc_ecosystem --production --apply --preview-payload <payload> --preview-fingerprint <fingerprint> --confirm-production CONFIRM_PROTECTED_DC_ECOSYSTEM_PRODUCTION_NO_CHANGE
```

`ec_taxonomy` production mode is refused with `EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY`.

The production preview is immutable and domain-bound. Production apply requires the saved preview payload, exact preview fingerprint, explicit confirmation, clean worktree, exact production database paths, candidate provenance, and a fresh stale-source validation.

## Candidate Provenance

The default accepted no-change source is `ACTIVE_PRODUCTION_BASELINE_NO_CHANGE`. It is a deterministic compact export of the active production `dc_ecosystem` taxonomy and is retained only as evidence. It is not a new recommendation and does not create or activate a new version.

Production mode rejects test-only provenance, fixture provenance, `NOT_FOR_PRODUCTION`, `TEST_ONLY`, and the Phase 13G.4.1/13G.4.2 AAOI `CORE -> EXTENDED` candidate.

## Role Matrix

For the expected no-change production invocation, the production write boundary is not crossed. Production roles are read-only and receive targeted bounded checks only:

- active DC taxonomy version and semantic fingerprint;
- membership and hierarchy counts;
- absence of active test-only versions;
- absence of a general EC pointer;
- active package, Relative Position and Relative Valuation identities;
- scheduler state before and after;
- zero-write proof.

For a future nonzero `dc_ecosystem` production update, the tested role-aware plan classifies production `taxonomy` and `analysis` as writable and `provider`, `canonical` and `market` as read-only. Only writable physical databases receive verified backups, restore rehearsal, heavy preflight/postflight checks and rollback participation.

## Future Nonzero Path

Phase 13G.4.3 implements and tests the future nonzero runner on isolated production-shaped fixtures only. The simulation proves:

- writable-set discovery selects `taxonomy` and `analysis`;
- backups include writable roles only;
- scheduler pause/restore happens only before the write boundary;
- the downstream hook runs once for a simulated nonzero change;
- an independent second pass records `NO_CHANGE`;
- injected post-write failures restore the complete writable set.

No real nonzero production taxonomy candidate is executed in this phase.

## Required Production Result

The single real production invocation must return:

- outcome: `NO_CHANGE`;
- write boundary crossed: `false`;
- taxonomy/version/membership/pointer/dependency writes: `0`;
- package/RP/RV invocations: `0/0/0`;
- Snapshot regeneration: `0`;
- backup created: `false`;
- rollback required: `false`;
- scheduler stopped by this operation: `false`;
- active taxonomy and downstream identities unchanged.

If preview finds a real change, stop before production invocation and request separate authorization.
