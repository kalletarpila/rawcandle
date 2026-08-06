# DC Carry-Forward Parity Field Policy

## Purpose

DC carry-forward validation compares active-taxonomy source facts with proposed
target-taxonomy facts. It must separate keys, lineage, semantic data, and
operational provenance so recovery decisions do not confuse a successful narrow
repair with unrelated target drift.

## Field Classes

```text
KEY
SEMANTIC
REQUIRED_LINEAGE
OPERATIONAL_METADATA
IGNORED_DIAGNOSTIC
```

`KEY` fields are table-specific uniqueness keys, for example ticker/date/signal
version or group/date/calc version.

`REQUIRED_LINEAGE` includes `taxonomy_version`. Source and target taxonomy
values are expected to differ during carry-forward; validation confirms lineage
by selecting the active source taxonomy and proposed target taxonomy explicitly.

`OPERATIONAL_METADATA` includes `run_id` and `source_run_id`. These identify the
operation that produced or copied the row. They are useful audit provenance but
are not trading-signal semantics.

`IGNORED_DIAGNOSTIC` includes creation/update timestamps and ticker primary
group labels that are rewritten from target taxonomy metadata.

Everything else defaults to `SEMANTIC`. Real signal fields such as
`bullish_divergence_signal` remain blocking when source and target differ.

## Deployment 2 Evidence

The scoped validation preflight for deployment 2 produced:

```text
operational_metadata_drift_count=14694
blocking_semantic_mismatch_count=1

blocking mismatch:
  table=dc_ticker_swing_signal_daily
  key=(2026-08-04, WMS, DC_SWING_SIGNAL_V1)
  field=bullish_divergence_signal
  source=1
  target=0
```

The `run_id` drift is visible and nonblocking. The WMS signal mismatch is
semantic and requires a controlled semantic-row-only repair before complete DC
target validation can pass.
