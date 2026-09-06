# Operating-Income V2 Phase 9C Implementation

Phase 9C implements parallel pure V2 calculation contracts under `rawcandle.fundamentals.operating_income_v2`.

The implementation uses typed V2 inputs and distinct V2 outputs. Where the arithmetic and state-machine mechanics are intentionally identical, V2 calls existing pure V1 helpers through validated adapters. Operating income is mapped only inside those adapters; public V2 contracts do not accept EBIT as an affected input. V2 component names, evidence terminology, model versions, model fingerprints and result fingerprints remain distinct.

This approach avoids changing V1 modules and protects their existing fingerprints. Compatibility checks reject V1/V2 mixing in Delta, Relative Position and Company Snapshot bundles.

The read-only rehearsal CLI is:

```bash
python -m rawcandle.fundamentals.operating_income_v2.rehearsal
```

It has no apply mode. It opens production sources with SQLite URI `mode=ro&immutable=1`, runs the economic calculation twice, and writes only timestamped Phase 9C artifacts under `temp/`.

The accepted rehearsal is `temp/fundamentals_v4_operating_income_v2_phase9c/20260906T165026Z/`. It calculated 50,585 TTM, Score, Lifecycle, Valuation and Delta endpoints, 335,272 historical diagnostic evaluations, 2,431 current-fresh companies and 13,740 current Relative Position rows. The V1 Score replay matched all 50,585 persisted results exactly, and Revenue Growth, FCF Margin and Dilution matched V1 exactly on every V2 row. Both passes produced identical result fingerprints.

Reference checks use an absolute tolerance of 0.02 points. Rehearsed Score/Valuation pairs were AMZN 56.08/18.43, GOOG 77.53/27.82, NVDA 96.94/27.02, CRMD 91.08/100.00 and APD 26.96/0.00.

All five inspected database files had identical size, mtime, SHA-256, schema hash, key row counts, quick-check result, foreign-key result and WAL/SHM state before and after. The pre-existing `data/analysis.db-wal` and `data/analysis.db-shm` remained present and unchanged in state; Phase 9C did not create or checkpoint them.

Production persistence, migrations, backfill, active readers, pipeline hooks, Scheduler behavior and generated production reports are explicitly deferred to Phase 9D.
