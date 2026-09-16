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
