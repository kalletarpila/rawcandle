# Fundamentals V4 Phase 13E Production Deployment Record

Phase 13E is the protected SNDK-only production onboarding path.

The deployment command is:

```bash
python3 -m rawcandle.cli.run_phase13e_sndk_production_onboarding \
  --output temp/fundamentals_v4_phase13e_production_onboarding/20260912T_PHASE13E_SNDK_PRODUCTION_ONBOARDING \
  --apply
```

The authorized ticker is `SNDK` only. AREB, SNDK1 and every other local-provider candidate are explicitly excluded. The source is the managed Phase 12C.3 archive `data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip` with SHA-256 `dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`.

SNDK remains a distinct current security: permaticker `643888`, CIK `0002023554`. SNDK1 remains the historical predecessor/reuse evidence with permaticker `197210`; price, valuation, share-count and listing histories must not be merged across the 2016-2025 listing gap.

The write set is limited to:

- `data/fundamentals_provider.db`;
- `data/fundamentals_v4.db`;
- `data/fundamentals_analysis.db`.

`data/osakedata.db` is read-only market evidence. `data/analysis.db` is read-only taxonomy evidence; Phase 13E verifies the existing SNDK taxonomy entity and active memberships without creating aliases or memberships.

Before writing, the runner requires a clean reviewed Git worktree at commit `5f4ec74`, exact production paths, no non-empty SQLite sidecars, no conflicting writer process, production `quick_check=ok`, zero FK violations, verified source archive and sufficient storage. It creates full SQLite online backups for every database in the write set under `backups/fundamentals_v4_phase13e_sndk_onboarding/<run-id>/`.

The apply sequence reuses the existing production engines:

1. create or reuse the SNDK canonical identity;
2. stage verified SNDK archive observations;
3. connect existing SNDK taxonomy membership with alias evidence only;
4. reconcile canonical quarters and TTM;
5. rebuild the active Operating Income V2 package;
6. rebuild and activate the operational universe;
7. rebuild full-universe Relative Position;
8. prove the existing Relative Valuation snapshot is incompatible before refresh;
9. explicitly run the manual full-universe Relative Valuation refresh;
10. attach compatible dependency state;
11. generate deterministic SNDK Snapshot smoke output;
12. run an independent second invocation requiring `NO_CHANGE` evidence.

If any post-backup gate fails, the runner restores every write-set database from the verified backups and records `OUTCOME C`.

## Deployment Result 2026-09-12

Final run:

`temp/fundamentals_v4_phase13e_production_onboarding/20260912T_PHASE13E_SNDK_PRODUCTION_ONBOARDING_APPLY_R4`

Selected outcome:

`OUTCOME A — SNDK PRODUCTION ONBOARDING COMPLETE AND STABLE`

Activation timestamp: `2026-09-12T16:48:26Z`.

Backup directory:

`backups/fundamentals_v4_phase13e_sndk_onboarding/20260912T_PHASE13E_SNDK_PRODUCTION_ONBOARDING_APPLY_R4`

Earlier protected attempts were retained as evidence:

- R2 restored from backups after a wrapper diagnostic verification bug: the gate counted endpoint rows instead of eight evaluation rows.
- R3 restored from backups after the wrapper incorrectly required the pre-refresh Relative Valuation mismatch during the second `NO_CHANGE` invocation.

Both wrapper defects were corrected before R4. The defects were orchestration gates, not production reader defects.

R4 production evidence:

- SNDK provider observations: 61 total, 13 ARQ.
- Canonical identity: company `2459`, security `2471`, active ticker `SNDK`.
- SNDK canonical quarters: 9.
- SNDK TTM endpoints: 9.
- Active operational universe members: 2459.
- SNDK universe status: `ACTIVE_SINGLE_SECURITY`.
- Active Relative Valuation snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`.
- Relative Valuation as-of date: `2026-09-12`.
- Relative Valuation company rows: 2449.
- SNDK Relative Valuation rows: 1.
- Active diagnostic endpoints: 87328, with zero non-eight evaluation endpoints.
- Snapshot smoke report: `SNDK_2026-09-12.md`, deterministic fingerprint `34f1ca4d439409e08c88c096b1a73e5fcdcbb3f8b95c56c984806070cf9c4648`.

The required intermediate Relative Valuation boundary was observed in the first apply:

- pre-refresh state: `OPERATIONAL_UNIVERSE_MISMATCH`;
- old snapshot: `7edd6226bd9cc0346f24c1f92d3d4c1dabb67df18e9d4f3210550530daf68324`;
- post-refresh state: `COMPATIBLE`;
- new snapshot: `11bdf3367e4099f25afbc750836a1a95488af13d09a226f7357c8cbce978fada`.

The second invocation returned logical `NO_CHANGE` for provider inserts, canonical, TTM, package, universe, Relative Position and Relative Valuation. The original R4 artifact also records `inventory_exact_no_change=false`; field inspection showed the meaningful write targets were no-change and the Relative Valuation second apply reported `second_analysis_inventory_no_change=true`. The wrapper was updated after R4 to report a normalized inventory comparison that ignores content-identical SQLite sidecar mtime variation.
