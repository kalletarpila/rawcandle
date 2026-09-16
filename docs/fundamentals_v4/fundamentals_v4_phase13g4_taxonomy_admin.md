# Fundamentals V4 Phase 13G.4 Taxonomy Administration

Phase 13G.4 adds a domain-aware `CHECK_UPDATE_TAXONOMY` admin CLI:

```bash
python3 -m rawcandle.cli.run_fundamentals_admin_taxonomy --taxonomy dc_ecosystem
python3 -m rawcandle.cli.run_fundamentals_admin_taxonomy --taxonomy ec_taxonomy
```

The CLI requires an explicit taxonomy domain. Preview payloads, fingerprints, run ids, reports, CSV rows, dependency decisions, and apply confirmation all include the selected domain. A preview from one domain is rejected before it can be applied to the other domain.

## Domain Discovery

`dc_ecosystem` is the current production-primary Datacenter taxonomy domain. Repository consumers resolve it through the `ec_*` sidecar tables in `data/analysis.db` for `ec_ecosystem.ecosystem_code = 'DATACENTER'`. The active production audit on 2026-09-16 found:

- active version: `DC_TAXONOMY_FULL_V2_1`
- storage tables: `ec_ecosystem`, `ec_taxonomy_version`, `ec_entity`, `ec_entity_alias`, `ec_membership`
- inventory: `DC_TAXONOMY_FULL_V1`, `DC_TAXONOMY_FULL_V2`, `DC_TAXONOMY_FULL_V2_1`
- active memberships: 350 rows, 257 tickers, 16 layers, 37 subindustries
- primary production taxonomy: remains `dc_ecosystem`

`ec_taxonomy` is kept as a separate future target domain. This phase found no repository-distinct general EC taxonomy storage, pointer, consumer set, or safe write contract separate from the Datacenter sidecar. The admin CLI therefore reports `EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY` for `ec_taxonomy` candidate apply while still allowing read-only audit and deterministic fingerprinting.

## Safety Contract

No production writes are authorized in Phase 13G.4. Candidate apply is copy-only for writable domains. The CLI refuses production database paths, creates isolated SQLite backup copies, validates selected-domain changes, compares the non-selected domain before and after apply, and records rollback evidence on injected post-write failures.

This phase does not synchronize `dc_ecosystem` and `ec_taxonomy`, infer memberships between them, merge fingerprints, or switch the active primary production taxonomy. A future DC-to-EC migration must be separately planned with explicit reconciliation, compatibility, and production gates.

## Acceptance Evidence

- Unit coverage: `pytest -q tests/test_fundamentals_admin_taxonomy.py` passed with 6 tests.
- Real read-only `dc_ecosystem` audit:
  `fundamental_reports/admin_runs/20260916T073004Z_check_update_taxonomy_dcb015ad6e99_dc_ecosystem_preview`
- Real read-only `ec_taxonomy` audit:
  `fundamental_reports/admin_runs/20260916T073004Z_check_update_taxonomy_031997db1f37_ec_taxonomy_preview`
- Scheduler was stopped with user `systemd` during the test/audit window after it was observed running as `stock-update-scheduler.service`; no `kill -9` was used.

## Phase 13G.4.1 Handoff

Phase 13G.4.1 adds the production-shaped `dc_ecosystem` copy-only acceptance lane for a real nonzero versioned taxonomy candidate. The candidate remains explicitly `TEST_ONLY_NOT_FOR_PRODUCTION`, runs only against isolated database copies, and keeps `ec_taxonomy` read-only with `EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY`. A future production-capable taxonomy update still requires a separate protected production phase.

## Phase 13G.4.2 Handoff

Phase 13G.4.2 adds the downstream closure lane for the same test-only `dc_ecosystem` candidate. It runs the established package, Relative Position, Relative Valuation, dependency and Snapshot chain on production-shaped copies, proves fixed-point repeat and downstream rollback, and replaces raw live hashing with bounded logical production postflight. This remains copy-only; no production taxonomy update is authorized.

## Phase 13G.4.2.1 Handoff

Phase 13G.4.2.1 supersedes only the over-broad production read-only `quick_check` blocker from the Phase 13G.4.2 audit trail. The retained 13G.4.2 copy evidence still records its original Outcome C, but role-aware verification now classifies production `data/analysis.db` as read-only for this copy-only operation and keeps heavy integrity, backup, rollback and full inventory checks on writable copy lanes or future production-writable operations. See [fundamentals_v4_phase13g4_2_1_role_aware_closure.md](fundamentals_v4_phase13g4_2_1_role_aware_closure.md).

## Phase 13G.4.3 Handoff

Phase 13G.4.3 adds protected production mode for `dc_ecosystem` while authorizing only a true `NO_CHANGE` production verification. The production path requires `--production`, `--apply`, an exact saved preview payload and fingerprint, explicit confirmation, clean worktree, exact production paths, and candidate provenance. The default no-change candidate provenance is `ACTIVE_PRODUCTION_BASELINE_NO_CHANGE`, a deterministic export of the active production taxonomy retained as evidence only.

`ec_taxonomy` remains production update-not-ready and is refused with `EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY`. The Phase 13G.4.1/13G.4.2 AAOI test-only candidate is explicitly blocked from production mode. See [fundamentals_v4_phase13g4_3_protected_taxonomy_production.md](fundamentals_v4_phase13g4_3_protected_taxonomy_production.md).
