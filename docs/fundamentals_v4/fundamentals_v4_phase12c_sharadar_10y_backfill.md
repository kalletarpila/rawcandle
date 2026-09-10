# Fundamentals V4 Phase 12C Sharadar 10-Year Raw Backfill

## Outcome

Phase 12C completed the provider-only Sharadar Fundamentals ten-year backfill.
The request was `GET /data/fundamentals?years=10`; the API key existed only in
the process environment and is absent from commands, logs, manifests and
committed files. The snapshot contained 1,036,805 rows and all six upstream
dimensions. Production retained the established target-universe `ARQ` and
`MRQ` scope.

No canonical, TTM, Score, Lifecycle, Valuation, Delta, Relative Position,
Diagnostic, Snapshot, market, taxonomy, Scheduler or report calculation ran.
Phase 12B was not rerun. The history remains a currently revised provider
snapshot, not point-in-time history. Prospective PIT collection is excluded.

## Source and staging

- ZIP: 235,876,508 bytes; SHA-256
  `dc9d3f729830c1881873d10dec2dc2a3e7035d2a247e1737983bdb64cd0e0d36`.
- CSV: 802,067,611 bytes; SHA-256
  `3a5cf6af14a0257ca00cab18469112eb2b51381b97e1271d28d2c6a9147e5f6c`.
- Global ARQ range: 2014-12-31 through 2026-09-30.
- Imported ARQ range: 2015-06-30 through 2026-09-30.
- Imported MRQ range: 2016-06-30 through 2026-09-30.
- Target-universe ARQ/MRQ staged rows: 178,933.
- Exact duplicate rows: 0; malformed required numerics: 0.
- Revision-key extra rows: 1,549. These are distinct provider filing/revision
  observations and are retained by the existing observation identity policy.

Staging classified 76,758 rows as new periods, 891 as revisions and 101,284
as unchanged. The 84 previously stored base-period keys absent from the new
snapshot were preserved under the append-only provider snapshot policy.
Upstream blanks remained NULL rather than economic zeroes.

## Production import

| Measure | Before | After | Change |
|---|---:|---:|---:|
| Provider observations | 102,204 | 179,853 | 77,649 |
| ARQ | 51,476 | 89,432 | 37,956 |
| MRQ | 50,728 | 90,421 | 39,693 |
| Database bytes | 551,792,640 | 922,521,600 | 370,728,960 |
| SQLite pages | 134,715 | 225,225 | 90,510 |

The production apply took approximately 85 seconds from the preflight artifact
to the completed result artifact. This is filesystem-timestamp evidence rather
than separately instrumented runtime telemetry. The staged ZIP and CSV consumed
1,037,944,119 bytes; the verified backup consumed 551,792,640 bytes.

The schema hash remained
`0d973d20903107a28244e25f38946ca0e1ea476d7c28fda6273f7cd13dae7eaf`.
The provider SHA-256 changed from
`1905d09cf93901622ae178e7b472e571bc872ba2b243ff3b02a5957f9b6e2c14`
to `0205b9b05c18a4fbd28f6f82a22d2805eade443fab2e3cdedee0ff8b567149e8`.
Post-import `quick_check` is `ok`; foreign-key violations, exact observation-ID
duplicates and normalized orphans are all zero. The freelist is zero and no
WAL or SHM sidecar remains.

An identical replay inserted zero rows. Size, mtime, page count, freelist,
SHA-256 and sidecar state all remained unchanged.

## Backup and rollback

The verified online backup is
`backups/fundamentals_provider.phase12c.20260910T133756Z.db`. It is independently
openable, 551,792,640 bytes, and has SHA-256
`4e9a0df1283383337363e4f7e035120341336261c8dfbc1746403150b67e686b`.
It matches the source schema and relevant row counts, has `quick_check=ok`, zero
foreign-key violations and no WAL dependency.

Rollback procedure: stop provider writers, retain the failed database, open the
verified backup read-only, create a new database with
`sqlite3.Connection.backup()`, verify schema, row counts, quick check and foreign
keys, and only then atomically replace production. This was rehearsed on a safe
copy. An injected import failure rolled back to the exact pre-transaction hash;
a restore from backup was byte-identical.

## Isolation

The combined non-provider production fingerprint was identical before and after:
`deb823fa0ee18457ce575da4b3dcbffe1fd3049037f168dedfa7177957f53447`.

- canonical: `f553639e7f25ce75fed51af0c2127121a96573cd88728c2eafa84b9dfdc087da`;
- analysis: `4e7bc02191a705a73942d7df40cecc92ed5719633091bcd7b4e4a7c92146df97`;
- market: `38078094058004539dcb155df8b4172cb6822dc20c465c02cd7468710a1d1cdd`;
- taxonomy: `b9dfe08535e4889bf93282ce3b34f9aac4b4c4348e183f8dc960bf72b9513728`.

All existing files beneath `fundamental_reports` retained their hashes.

## Tests

The focused Phase 12C suite passed with 7 tests. The final broad command
`pytest -q tests/test_fundamentals_v4*.py tests/test_phase12c_sharadar_backfill.py`
passed all 811 tests in 108.01 seconds. `python3 -m compileall -q rawcandle` and
`git diff --check` also passed.

No downstream economic recalculation tests were run because this phase neither
changed nor invoked canonical or analysis engines. Production isolation was
instead established with byte hashes before and after the provider-only write.

## Raw warmup feasibility

The latest filing per ticker and fiscal period gives 9,157 raw ARQ endpoints in
fiscal 2021. Of these, 8,410 have a contiguous four-quarter window, 7,518 have
eight contiguous raw quarters, and 7,379 have the eight-quarter chain plus
Revenue, Operating Income, FCF, endpoint Cash/Debt/Shares and prior-year Shares.
Those 7,379 endpoints cover 1,909 tickers.

The raw data is sufficient to attempt pre-2021 TTM warmup, 2021 YoY growth,
Operating Margin Direction, Dilution and five-snapshot Trajectory. This is only
a raw feasibility conclusion; no canonical or Score result was calculated.

## Evidence and next phase

Detailed evidence is under
`temp/fundamentals_v4_phase12c/20260910T_APPLY_10Y_A/`. Key files are
`preflight.json`, `staged_validation.json`,
`staged_provider_reconciliation.json`, `backup_manifest.json`,
`first_import.json`, `second_import.json`, `rollback_rehearsal.json`,
`raw_warmup_feasibility.json`, the production-isolation inventories and
`post_import.json`.

The next separately authorized phase should canonicalize the accepted ten-year
ARQ history, rebuild TTM and downstream revised history in dependency order, and
then rerun the unchanged locked Phase 12B contract. It must preserve the original
development, validation and confirmation periods and must not add prospective
PIT work.
