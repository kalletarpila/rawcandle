# Relative Position V1 Phase 4B Implementation

## Scope

Phase 4B implements production-quality pure calculation, read-only source adaptation, tests, and a full-universe rehearsal. It intentionally contains no schema, migration, persistence writer, production result, daily pipeline hook, or enabled apply path.

Implementation files:

- `rawcandle/fundamentals/relative_position/engine.py`: immutable contracts, validation, peer construction, midrank calculation, coverage audit, and fingerprints.
- `rawcandle/fundamentals/relative_position/source.py`: explicit-path SQLite `mode=ro` adapter for current Score, Valuation, classification, identity, and taxonomy sources.
- `rawcandle/fundamentals/relative_position/rehearsal.py`: in-memory double replay and explicit output-directory artifacts.
- `rawcandle/cli/run_fundamentals_v4_relative_position_rehearsal.py`: read-only CLI with no `--apply` argument.
- `tests/test_fundamentals_v4_relative_position_engine.py` and `tests/test_fundamentals_v4_relative_position_source.py`.

The pure API is `calculate_snapshot(observations, snapshot_date, freshness_days, classification_fingerprint, taxonomy_fingerprint)`. It has no database, clock, network, or mutable-global dependency. `load_current_relative_source` is the separate source adapter.

## Rehearsal

Run date contract: 2026-09-01 with 180-day maximum age.

Artifacts:

```text
temp/fundamentals_v4_relative_position_phase4b/20260901T182112Z/
```

Command:

```bash
python3 -m rawcandle.cli.run_fundamentals_v4_relative_position_rehearsal \
  --analysis-db data/fundamentals_analysis.db \
  --canonical-db data/fundamentals_v4.db \
  --market-db data/osakedata.db \
  --taxonomy-db data/analysis.db \
  --as-of-date 2026-09-01 \
  --freshness-days 180 \
  --output-dir temp/fundamentals_v4_relative_position_phase4b/20260901T182112Z
```

### Fingerprints

- Model: `983dc38a2805806d4e2709a6956f51bf9cb06ebb61fdb3d9e78344bca58cd7e2`
- Source: `692106e6edca56a18d0c1ec34247093a9b936d0be7a2bc7abb03deedec05cf5a`
- Result: `841ab14cd9861123cb01fb0adb9dd4b1f0053a90df318a5e11625876b6f08ff1`
- Canonical replay-file SHA-256: `aa09247319d6a31846ad71117ae1fcd50c6f83b153c20fdf13620b33b05d4acc`

`relative_snapshot_run1.json` and `relative_snapshot_run2.json` are 15,175,208 bytes each and byte-identical.

### Reconciliation

| Item | Fundamental | Valuation |
|---|---:|---:|
| Latest as-of observations | 2,451 | 2,448 |
| Eligible universe | 2,198 | 2,246 |
| Eligible DATACENTER CORE+EXTENDED | 204 | 201 |
| Ready universe percentiles | 2,198 | 2,246 |
| Ready sector percentiles | 2,188 | 2,236 |
| Ready industry percentiles | 1,911 | 1,947 |
| Ready ecosystem percentiles | 204 | 201 |

All counts exactly reconcile Phase 4A. Every one of the 4,899 latest observations resolved through its observation `security_id`. All eligible rows had current sector and industry.

The active taxonomy had 350 membership rows and 257 unique tickers. It mapped 215 directly and uniquely to V4 companies; 42 were absent from the V4 universe, with no ambiguous mappings.

There were 11 sector groups per measure; one 10-member sector was below the minimum for each measure. Fundamental had 128 industries and Valuation 119; 54 industry groups were below 10 for each measure, affecting 287 and 299 eligible companies respectively. No universe or ecosystem group was below minimum.

### Tie behavior

The Valuation universe had 631 exact zero scores. All received percentile `14.031180400890868`, average rank 316, and tie count 631. Its six exact 100 scores all received `99.88864142538975`, average rank 2243.5, and tie count 6.

Tie-block counts were 9 Fundamental universe, 5 Fundamental sector, 3 Fundamental industry, 4 Valuation universe, 21 Valuation sector, 72 Valuation industry, and 1 Valuation ecosystem. No ticker or input ordering entered tie resolution.

### CRMD

CRMD's persisted Valuation Score 100 produced:

| Scope | Group | Peers | Rank interval / average | Percentile |
|---|---|---:|---:|---:|
| `UNIVERSE` | `ALL` | 2,246 | 2241...2246 / 2243.5 | 99.88864142538975 |
| `SECTOR` | Healthcare | 584 | 582...584 / 583 | 99.82847341337907 |
| `INDUSTRY` | Biotechnology | 312 | 312...312 / 312 | 100 |
| `ECOSYSTEM` | none | 0 | not a member | null |

These values were selected from engine output by ticker after calculation and were not hard-coded. They rank the persisted score; they do not validate sustainability of CRMD's run rate.

### Representative cases

`representative_cases.json` records INSW, SITM, HOV, NNDM, IRWD, AIN, LION, VRT, O, CRMD, and the current WATCH_ONLY-only case ASPI. VRT's multiple taxonomy source memberships produce one DATACENTER denominator entry. ASPI receives no ecosystem group entry. No taxonomy-layer ranking exists in the model, enum, output, or summary.

## Verification and production boundary

Focused tests cover ranking order, endpoints, group sizes, every tie position, all-equal scores, exact zeros/100s, finite-value validation, independent measures, missing classifications, ecosystem deduplication, multiple ecosystems, WATCH_ONLY exclusion, duplicate-source protection, as-of selection, 180-day boundary, current classification, alias resolution, deterministic replay, explicit CLI paths, and source-file hash preservation. The final targeted run passed 194/194 tests.

Targeted Score, Lifecycle, Valuation reader/engine/persistence, schema/bootstrap, and production import regressions are run as part of Phase 4B completion. The full repository suite is not required because no existing schema, persistence, absolute model, or pipeline module changed.

Phase 4C remains responsible for a separately authorized relative-position schema, atomic snapshot activation, idempotent unchanged-source behavior, production readers, backup/runbook evidence, and daily refresh integration. Phase 4B's CLI cannot write production data.

### Production integrity

Pre- and post-Phase 4B database size, mtime, and SHA-256 values were identical:

| Database | Bytes | mtime epoch | SHA-256 |
|---|---:|---:|---|
| `fundamentals_v4.db` | 288,563,200 | 1788278801 | `2e4bc3d99c1eca1d1b28eaacffe581fad61f6a2ef7ead7dee2eeae1a0338ee10` |
| `fundamentals_analysis.db` | 302,678,016 | 1788279035 | `72c76a455569bd9aa0b9d1db46849bf8f7d16d9bc85e77de723b44b23a092122` |
| `fundamentals_provider.db` | 546,754,560 | 1788157472 | `17660df9f00837fbb52668aff17144d1b167aae4458dfa1a3c057701924b6d9c` |
| `osakedata.db` | 1,963,397,120 | 1788241471 | `3a9cbf1c9498acb0c0911fa279c4334b8832f03e57ffc80e5062132c6991f2b6` |
| `analysis.db` | 10,037,084,160 | 1788241642 | `17164dda0b95fd96823c413c6c2f75d7ee3c4311ed690a5fdb2c9e669c33bea7` |

The analysis schema hash remained `a1bd99740b2b1a98169e7a8389faf8dab1b3dc839b2929c996b8f74553fc7a3e`. Row counts remained Score 50,585, components 354,095, revised Lifecycle 50,585, and revised Valuation 50,585. `PRAGMA quick_check` returned `ok` for all five databases.
