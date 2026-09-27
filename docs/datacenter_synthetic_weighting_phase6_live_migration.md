# Datacenter synthetic weighting Phase 6 live migration

## 1. Starting implementation

The live phase started from clean HEAD
`dc3a1b268eb667a8a4c81eebdca31f824a342b13`. Phase 5 migration machinery was
present. Two runtime blockers were fixed and committed before their affected
phase was restarted: timestamp formatting in `53f752ce` and replacement
watermark row counts in `e2e14113`.

## 2. Runtime scope

- Taxonomy: `DC_TAXONOMY_FULL_V2_1`
- Taxonomy CSV: `data/datacenter_taxonomy_full_v2_1.csv`
- Market: `usa`
- V1 range: `2025-08-01` through `2026-09-25`
- V1 rows: 15,370
- Rebuild and projection range: `2025-08-01` through runtime V1 maximum

Preflight `PRAGMA quick_check` returned `ok`. Scheduler version resolved to
`DC_SWING_OHLC_V1` before activation.

## 3. Pre-write fingerprints

| Scope | Rows | SHA-256 |
|---|---:|---|
| DC V1 | 15,370 | `c9bc7e40154ba980fb76bb6659147515b585aba2ee4a2d709e3f9bce75720bd9` |
| EC V1 | 15,370 | `4659a993031a5c178ed028a4274c298e21b0de548a6d85438e3cc2b65d06b6eb` |

The fingerprints cover all persisted columns in deterministic key order for the
active taxonomy and V1 version scope.

## 4. Backup

Canonical rollback backup:
`backups/datacenter-weighting-v2/20260927T123753Z/analysis.db`

- SQLite online backup semantics used
- `PRAGMA quick_check`: `ok`
- size: 11,357,200,384 bytes
- SHA-256: `2623f333104ee724437e35483bafcb60c4cf2d371eb8b8871b0392ae15727b1c`
- created before the first successful live V2 write
- retained after migration

An earlier equivalent pre-write backup under `20260927T123357Z` is also retained.

## 5. DC V2 build

The production candidate builder ran base, relative, and structure in dependency
order and wrote only `DC_SWING_OHLC_V2`. Result:

- rows: 15,370
- dates: 290
- groups: 53
- range: `2025-08-01..2026-09-25`
- run: `DC_GROUP_SYNTH_OHLC_20250801_20260925_DC_SWING_OHLC_V2`
- chain discontinuities: 0

## 6. DC integrity

Every date has exactly 53 groups. Duplicate keys, mixed-version lineage, invalid
NULL closes, usable rows marked `NO_DATA`, invalid relative fields, incomplete BOS,
and incomplete RESET counts are all zero. Strict pipeline audit status was `OK`.

V2 watermarks are `OK` and explicitly versioned:

| Component | Rows |
|---|---:|
| base | 15,370 |
| relative | 15,370 |
| structure | 15,359 |

Structure updates are lower than total rows because rows without a calculable
structure update retain the established warm-up/data-quality semantics.

## 7. Report regression

Daily V2 report status was `OK`, with 53 synthetic rows. Rolling-20 V2 report
status was `OK`, with 20 valid dates and 1,060 synthetic rows. Both report headers
identified `DC_SWING_OHLC_V2`; no V1 fallback occurred. Outputs remain under the
run-specific `temp/` directory and were not published.

## 8. EC V2 projection

The explicit V2 projection processed 290 dates and 15,370 rows. EC coverage is
exactly 53 rows per date from `2025-08-01` through `2026-09-25`, with one V2 source
run. EC V1 rows were not replaced.

## 9. DC/EC parity

The projection command ran version-scoped parity on every date:

- total material mismatches: 0
- latest date source/target rows: 53/53
- latest total mismatches: 0
- latest blocking mismatches: 0

Latest status was `OK_WITH_WARNINGS` only for the established intentionally
unmapped EC diagnostic fields: `latest_structure_date`, `structure_state`,
`relative_strength_5d`, and `relative_strength_20d`.

## 10. Activation gate

Backup, DC build, DC integrity, chain continuity, report regression, EC projection,
parity, V1 DC preservation, V1 EC preservation, V1 scheduler state, and rollback
availability were all true. Gate result: `GO`.

## 11. Scheduler switch

`scheduler_config.json` was changed only by adding:

```json
"datacenter_ohlc_calc_version": "DC_SWING_OHLC_V2"
```

Validated scheduler resolution changed from V1 to V2. The active systemd timer is
`Type=oneshot`; each trigger reads this config through its CLI entrypoint, so no
service restart or daemon reload was required. Next trigger was
`2026-09-28 04:30 EEST`.

## 12. Postflight

The full Datacenter pipeline dry-run planned all 15 stages, audits, and daily and
rolling 30/5/2 reports with explicit V2. A post-activation read-only daily report
returned `OK` and 53 V2 synthetic rows. Final database `PRAGMA quick_check` was
`ok`; V2 watermarks and latest DC/EC parity remained clean.

A full stock-update scheduler execution was not run because it performs market and
fundamental network work, while this phase explicitly prohibited network calls.
The pipeline dry-run plus real read-only report is the safe postflight equivalent.

## 13. V1 before/after

| Scope | Before SHA-256 | After SHA-256 | Result |
|---|---|---|---|
| DC V1 | `c9bc7e40154ba980fb76bb6659147515b585aba2ee4a2d709e3f9bce75720bd9` | `c9bc7e40154ba980fb76bb6659147515b585aba2ee4a2d709e3f9bce75720bd9` | unchanged |
| EC V1 | `4659a993031a5c178ed028a4274c298e21b0de548a6d85438e3cc2b65d06b6eb` | `4659a993031a5c178ed028a4274c298e21b0de548a6d85438e3cc2b65d06b6eb` | unchanged |

Both scopes remain at 15,370 rows. V1 was not deleted or semantically modified.

## 14. Runtime blockers and restart behavior

The first build attempt rejected an ISO timestamp containing `+00:00`; it failed
before any V2 row or watermark write. The CLI was fixed to emit the persistence
contract's `Z` form, tested, committed, and Phase 6 restarted.

The next integrity gate found a base watermark row count of zero because
`replace-range` reports inserted rows separately from upserts. Scheduler remained
on V1 and EC projection had not started. The row-count selection was fixed, tested,
committed, and Phase 6 restarted. The corrected full rebuild replaced the isolated
V2 scope and produced valid watermarks.

## 15. Rollback status

No rollback was required. Both blockers occurred before activation and V1 remained
active. The rollback remains an explicit scheduler selector change to V1; V2 rows
are retained for normal production use and the backup is available if version
isolation ever proves insufficient.

## 16. Audit artifacts

Successful run evidence is under
`temp/datacenter_weighting_v2_live_migration/20260927T124208Z/`. It contains
preflight, backup, fingerprints, build, integrity, report, projection, parity,
activation, and postflight summaries. Temp artifacts are not committed.

## 17. Final state

`DC_SWING_OHLC_V2` is the explicitly configured live scheduler calculation version.
DC V1 and EC V1 remain intact, DC V2 and EC V2 are complete and parity-clean, and
the pre-write backup is retained.
