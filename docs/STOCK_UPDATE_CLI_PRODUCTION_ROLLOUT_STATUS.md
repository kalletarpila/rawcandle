# Stock Update CLI Production Rollout Status

## Current rollout status

- OMXH manual production CLI run: PASSED
- OMXS manual production CLI run: PASSED
- USA manual production CLI run: DEFERRED / not completed
- Service path is not UI default
- Update button still uses legacy path by default
- Scheduled cron/systemd is not installed yet

## OMXH production run result

- `SUMMARY status=OK`
- `tickers_failed=0`
- `warnings=0`
- `errors=0`
- `ohlcv_rows_inserted=0`
- Duplicate check returned no rows
- `latest_pvm` remained `2026-05-15`
- Interpretation: already-current production no-op run succeeded

## OMXS production run result

```text
SUMMARY market=omxs
SUMMARY tickers_checked=291
SUMMARY tickers_updated=289
SUMMARY tickers_skipped=2
SUMMARY tickers_failed=0
SUMMARY ohlcv_rows_inserted=2
SUMMARY dow_structures_updated=16
SUMMARY warnings=0
SUMMARY errors=0
SUMMARY status=OK
```

Post-run checks:

- OMXS row count changed from `570892` to `570894`
- `latest_pvm` by market:
  - `omxh 2026-05-15`
  - `omxs 2026-05-15`
  - `usa 2026-05-15`
- Duplicate check returned no rows
- `ARISE.ST` remained at older `latest_pvm` in sample, likely consistent with Yahoo no-data/delisted warning and not considered a rollout blocker

## USA rollout status

- USA CLI run was started but intentionally interrupted
- No final USA `SUMMARY` result exists
- USA rollout is deferred
- Reason: larger universe, longer runtime, multiple Yahoo no-data/delisted warnings expected
- USA should be handled as a separate rollout with dedicated runtime window and log monitoring

## Scheduling recommendation

- Enable scheduling first only for `omxh` and `omxs`
- Do not schedule `usa` yet
- Avoid overlapping jobs because cross-process locking is not implemented
- Consider separate timers:
  - `stock-update-omxh`
  - `stock-update-omxs`
- Keep USA manual/deferred until separately validated

## Operational next step

- Install or document user-level systemd timers for `omxh` and `omxs` only
- Or run `omxh` and `omxs` manually for a few days before enabling timers
- Keep database backups before first scheduled runs
- Monitor logs and `SUMMARY` status
