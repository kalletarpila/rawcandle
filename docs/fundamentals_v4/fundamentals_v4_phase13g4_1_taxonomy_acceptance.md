# Fundamentals V4 Phase 13G.4.1 Taxonomy Acceptance

Phase 13G.4.1 adds a `dc_ecosystem` production-shaped copy-only acceptance orchestrator:

```bash
python3 -m rawcandle.cli.run_fundamentals_admin_taxonomy_acceptance
```

The acceptance run creates an explicit `TEST_ONLY_NOT_FOR_PRODUCTION` candidate from the active `dc_ecosystem` taxonomy, changes one existing membership role tier, previews it with the Phase 13G.4 taxonomy service, applies it only to isolated copies, repeats the same candidate to prove true `NO_CHANGE`, applies it on an independent replay lane, and restores a rollback lane from the original baseline after a material taxonomy write boundary.

`dc_ecosystem` remains the current production-primary Datacenter taxonomy. In this repository it is resolved through the established `ec_*` sidecar for `ecosystem_code='DATACENTER'`. `ec_taxonomy` remains read-only/not-ready and must continue to report `EC_TAXONOMY_UPDATE_CONTRACT_NOT_READY`.

The orchestrator records compact evidence under `fundamental_reports/admin_runs/` and removes phase-owned database copies after evidence capture. The long downstream chain is explicit: by default the orchestrator records dependency reasoning without running heavy package/RP/RV work; `--run-full-downstream` executes the copy-only downstream refresh path.

No production database writes, production-primary taxonomy switch, DC-to-EC migration, Scheduler configuration change, provider API call, or production report regeneration is authorized by this phase.
