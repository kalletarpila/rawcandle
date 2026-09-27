# Datacenter synthetic weighting Phase 5 production migration design

## 1. Baseline architecture

`dc_*` remains the calculation authority. Synthetic OHLC, relative OHLC, pivots,
HH/HL/LH/LL, BOS, RESET, freshness, and trend are persisted in
`dc_group_synthetic_ohlc_daily`. EC is an explicit projection of those DC facts;
reports still read DC. Starting HEAD was
`2390670987d246a10ed4abf77741c8dcd99d1f87`.

## 2. V1 and V2 contract

- `DC_SWING_OHLC_V1` is permanently bound to historical equal membership weight.
- `DC_SWING_OHLC_V2` is bound to Membership Weighting V1: primary `1.00`, secondary
  subindustry `0.33`, secondary layer `0.25`, and WATCH_ONLY/TOO_SMALL `0.00`.
- Canonical memberships use `(ticker, group_type, group_name)` and duplicate routes
  use the maximum route weight. `role_weight` is ignored.
- Unknown synthetic calculation versions are rejected. V1 remains the default until
  an explicit later activation.

## 3. Affected tables and components

| Order | Table/component | Producer/input | Range |
|---:|---|---|---|
| 1 | `dc_group_synthetic_ohlc_daily` base columns | synthetic OHLC producer, V2 | full chain |
| 2 | same table, relative columns | relative producer, V2 | full chain |
| 3 | same table, pivots/structure/BOS/RESET/trend | structure producer, V2 | full chain |
| 4 | `dc_swing_pipeline_watermark` | the three candidate stages, V2 key | full chain |
| 5 | daily/rolling report reads | explicit V2 selector | regression dates |
| 6 | `ec_group_synthetic_ohlc_daily` | DC V2 projection only | every V2 date |

Group signal and group index tables do not consume synthetic OHLC and need no
semantic rebuild. Report migration to EC is out of scope.

## 4. Chain-safe boundary

The validated anchor is `2025-08-01`. Runtime metadata determines the end from the
current V1 generation; on 2026-09-27 it was `2026-09-25` for
`DC_TAXONOMY_FULL_V2_1`. The rule is therefore
`2025-08-01 -> requested/current V1 end`, never a recent incremental interval.
The price loader reads pre-anchor history for previous-close and rolling warm-up.
The build refuses a different V1 start or an end beyond current V1.

## 5. Rebuild dependency order

The executable order is base, relative, then structure. The structure producer
calculates pivots, HH/HL/LH/LL, BOS, RESET, age/freshness, and trend together.
All stages use V2 and replace only the V2 date/version scope. Reports and EC run
only after all three stages and integrity checks pass.

## 6. Coexistence

DC synthetic and watermark keys include `calc_version`; EC synthetic keys include
`ohlc_calc_version`. V1 and V2 therefore coexist. Reports require an explicit
version. EC refresh also receives explicit V2 and replaces only that date/version
scope. There is no latest-version resolution in the migration path.

## 7. Coverage diagnostics

No coverage guardrail or single-member suppression was added. Zero positive
effective weight remains `NO_DATA`; one positive member is calculated normally.
`member_count`, `eligible_count`, taxonomy status, and the reusable concentration
helpers are enough to derive NO_EFFECTIVE_MEMBERS, SINGLE_MEMBER, THIN, and HEALTHY
later. No production column or schema redesign is required for V2 correctness.

## 8. DC to EC sequence

The sequence is validated DC V2, per-date EC V2 replacement, then version-scoped
parity on each date. The projection uses the existing loader and never calculates
EC independently. Parity covers OHLC, relative values, structure, BOS, RESET,
quality, lineage hashes/source PK, and source run. Accepted unmapped EC diagnostic
fields may yield `OK_WITH_WARNINGS`; every blocking and total mismatch count must
remain zero.

## 9. Consumer transition

Daily, weekly, and rolling reports already accept explicit OHLC versions. Pipeline
orchestration already threads the selected version. Scheduler configuration now
has `datacenter_ohlc_calc_version`, validates only V1/V2, defaults old and new
configs to V1, and always sends `--ohlc-calc-version`. The live scheduler config
was not edited. Its explicit switch to V2 is the last activation action.

## 10. Failure and rollback

V1 is never deleted or rewritten. A failed base, relative, structure, EC, parity,
or report gate leaves consumers and scheduler on V1. Partial V2 is rebuildable with
the same full-range commands. Rollback is: restore every consumer selector to V1,
leave V1 rows in place, then optionally delete only V2 DC, watermark, EC fact, and
V2 signal-run scopes. The pre-run SQLite backup protects against storage/operator
failure beyond version isolation.

## 11. Production-parity rehearsal

The real producers were run twice against an SQLite backup of `data/analysis.db`,
with `data/osakedata.db` and `data/datacenter_taxonomy_full_v2_1.csv`. All writes
were under `temp/datacenter_weighting_v2_migration_rehearsal/`.

Result: `OK`; 290 dates, 53 groups, and 15,370 DC V2 rows from `2025-08-01` through
`2026-09-25`; zero unexpected chain discontinuities; repeated rebuild identical;
V1 and V2 report selectors each returned 53 rows; 15,370 EC V2 rows projected;
zero DC/EC mismatch; candidate V1 DC and EC unchanged; source database hash and V1
scope unchanged. An injected failure after base also left source and candidate V1
unchanged.

## 12. Tests and checks

Focused suites cover weighting, base/relative/structure, shadow validation,
version-isolated persistence and reports, EC loader/parity, scheduler config/runner,
idempotence, chain boundary, and failure behavior. The final command set and counts
are recorded in the Phase 5 commit response. Python compilation and
`git diff --check` are required before commit.

## 13. Exact future production runbook

Do not run this section until the live migration phase is explicitly approved.

```bash
cd /home/kalle/projects/rawcandle
git show --no-patch --format='%H %s' HEAD
test -z "$(git status --porcelain)"
sqlite3 -readonly data/analysis.db "SELECT calc_version,taxonomy_version,MIN(ohlc_date),MAX(ohlc_date),COUNT(*) FROM dc_group_synthetic_ohlc_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1' GROUP BY calc_version,taxonomy_version;"
sqlite3 -readonly data/analysis.db "PRAGMA quick_check;"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "backups/datacenter-weighting-v2/${STAMP}"
sqlite3 data/analysis.db ".backup backups/datacenter-weighting-v2/${STAMP}/analysis.db"

python3 -m rawcandle.cli.run_datacenter_weighting_v2_candidate_build \
  --analysis-db data/analysis.db --confirm-analysis-db data/analysis.db \
  --price-db data/osakedata.db \
  --taxonomy-csv data/datacenter_taxonomy_full_v2_1.csv \
  --taxonomy-version DC_TAXONOMY_FULL_V2_1 --market usa \
  --chain-start-date 2025-08-01 \
  --confirm-calc-version DC_SWING_OHLC_V2

sqlite3 -readonly data/analysis.db "SELECT MIN(ohlc_date),MAX(ohlc_date),COUNT(*),SUM(synthetic_close IS NULL AND data_quality_status<>'NO_DATA') FROM dc_group_synthetic_ohlc_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1' AND calc_version='DC_SWING_OHLC_V2';"
sqlite3 -readonly data/analysis.db "SELECT COUNT(*) FROM dc_group_synthetic_ohlc_daily WHERE taxonomy_version='DC_TAXONOMY_FULL_V2_1' AND calc_version='DC_SWING_OHLC_V2' AND latest_bos_event_date IS NOT NULL AND latest_reset_event_date IS NOT NULL AND latest_reset_event_date < latest_bos_event_date;"

mkdir -p "temp/datacenter-weighting-v2-reports/${STAMP}"
python3 run_datacenter_daily_signal_report.py --analysis-db data/analysis.db \
  --signal-date 2026-09-25 --taxonomy-version DC_TAXONOMY_FULL_V2_1 \
  --ohlc-calc-version DC_SWING_OHLC_V2 \
  --output-md "temp/datacenter-weighting-v2-reports/${STAMP}/daily.md" \
  --output-csv "temp/datacenter-weighting-v2-reports/${STAMP}/daily.csv"
python3 run_datacenter_rolling_swing_report.py --analysis-db data/analysis.db \
  --end-date 2026-09-25 --taxonomy-version DC_TAXONOMY_FULL_V2_1 \
  --ohlc-calc-version DC_SWING_OHLC_V2 --window-size 20 \
  --output-md "temp/datacenter-weighting-v2-reports/${STAMP}/rolling.md" \
  --output-csv "temp/datacenter-weighting-v2-reports/${STAMP}/rolling.csv"

python3 -m rawcandle.cli.run_datacenter_weighting_v2_ec_projection \
  --source-db data/analysis.db --target-db data/analysis.db \
  --confirm-target-db data/analysis.db --ecosystem DATACENTER \
  --taxonomy-version DC_TAXONOMY_FULL_V2_1 \
  --start-date 2025-08-01 --end-date 2026-09-25 \
  --confirm-calc-version DC_SWING_OHLC_V2

sqlite3 -readonly data/analysis.db "PRAGMA quick_check;"
```

Use the runtime preflight maximum as every later `--end-date`/report date if it has
advanced. After all gates pass, set `datacenter_ohlc_calc_version` to
`DC_SWING_OHLC_V2` in the live scheduler config, validate/restart it using the
normal scheduler procedure, and run one postflight cycle. This switch is last.

Rollback before or after activation: set the scheduler and any manual report calls
back to `DC_SWING_OHLC_V1`. Optional V2 cleanup must be a reviewed transaction
filtering exactly `calc_version='DC_SWING_OHLC_V2'` or
`ohlc_calc_version='DC_SWING_OHLC_V2'`; retain the backup until postflight and the
agreed retention window complete.

## 14. Technical GO prerequisites

- Full-range V2 build succeeds at the runtime V1 boundary.
- V1 remains byte/scope intact before activation; V1/V2 lineage never mixes.
- Chain discontinuities and blocking integrity errors are zero.
- Structure/event stages and focused regressions pass.
- V2 reports resolve only V2.
- EC V2 projection completes with zero DC/EC mismatch.
- Backup and V1 selector rollback are verified.
- Scheduler V2 selection is explicit and performed last.

## 15. Actions intentionally not executed

No live DC or EC rows were written, no V1 rows were overwritten, no report was
published, no scheduler config was changed, no taxonomy/version was activated,
and no production workflow persisted weighting results. Only fixtures and `temp/`
copies were written.

## 16. Separate backlogs

Generic EC calculation, report migration from DC to EC, taxonomy expansion,
persisted generic concentration metadata, size/market-cap weighting, and any future
model tuning remain separate work.
