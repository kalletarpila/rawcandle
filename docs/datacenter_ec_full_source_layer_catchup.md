# Datacenter EC full source-layer catch-up

## Run

- Starting HEAD: `555a4d93f316710ad06723aa03defb8506f586b4`
- Runtime scope: `DATACENTER`, taxonomy `DC_TAXONOMY_FULL_V2_1`
- Explicit synthetic OHLC version: `DC_SWING_OHLC_V2`
- Planner-derived overlap: `2026-09-24..2026-10-02` (7 trading days)
- Backfill result: `BACKFILL_COMPLETED`; all dates completed, zero mismatches
- Audit artifacts: `temp/datacenter_ec_full_catchup/20261003T135234Z/`

## Coverage

Latest-date rows are shown in parentheses; totals cover each table's loaded
history for the active taxonomy and, for synthetic OHLC, V2 only.

| Fact family | DC pre/post | EC before | EC after |
| --- | --- | --- | --- |
| Ticker | 2026-10-02 (257), total 75,815 | 2026-09-25 (257), total 74,530 | 2026-10-02 (257), total 75,815 |
| Group signal | 2026-10-02 (54), total 15,930 | 2026-09-25 (54), total 15,411 | 2026-10-02 (54), total 15,681 |
| Synthetic OHLC V2 | 2026-10-02 (53), total 15,635 | 2026-10-02 (53), total 15,635 | 2026-10-02 (53), total 15,635 |
| Group index | 2026-10-02 (54), total 91,638 | 2026-09-25 (54), total 15,411 | 2026-10-02 (54), total 15,681 |

The normal historical-backfill path replaced the two overlap dates and filled
five partial dates. It loaded ticker, group signal, synthetic OHLC, and group
index facts, then advanced the four canonical source-layer watermarks once.

## Backup

- Path: `temp/analysis__ec_source_layer_backfill__DATACENTER__DC_TAXONOMY_FULL_V2_1__20260924_20261002__20261003T135514Z.sqlite`
- Size: 11,827,834,880 bytes
- Backup `PRAGMA quick_check`: `ok`
- Backup retained for rollback.

## Validation

- Every backfill date: coverage/parity `OK_WITH_WARNINGS`, zero mismatches.
- Latest full source-layer parity: 257 ticker, 54 group signal, 53 synthetic
  V2, and 54 group index rows on both sides; zero mismatches, zero blocking
  mismatches, and zero required-lineage mismatches.
- Latest lineage points to the corresponding four `dc_*` source tables.
- Duplicate target keys: zero for every fact family.
- Unexpected synthetic calc versions: zero; latest non-V2 synthetic rows: zero.
- Four canonical EC source-layer watermarks: `OK` at `2026-10-02`.
- Live database postflight `PRAGMA quick_check`: `ok`.
- Scheduler selection remained `DC_SWING_OHLC_V2`.

DC V1 remained at 51,029 rows with SHA-256
`727d784acdbe1205d74d6cd1451cc3fd27f08a6bcae392d8993dc66bfa4c7b95`.
EC V1 remained at 15,370 rows with SHA-256
`b5c9665dc546066fafbbe06c64ae953ae33310d99b4329bacf808244825b8f74`.

## Deviation

The optional global pipeline-watermark parity remains failed by ten legacy or
report watermark dates at `2026-07-28` plus a target-only `WEEKLY_REPORT` row.
These are outside the historical backfill's canonical four-watermark contract.
All fact-family and canonical source-layer watermark checks are clean.

## Stability Baseline

`V2_STABILITY_BASELINE_ESTABLISHED`

This starts the observation window; it does not satisfy the required 3-5 clean
normal scheduler runs or preferred full trading week.
