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
