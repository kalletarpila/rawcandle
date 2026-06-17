# Canonical Report V2 archive

Canonical Report V2 / `dc_report_*_v2` has been retired.

Documents in this directory are historical only. They are not current architecture, runbooks, or operational instructions.

Current preserved paths are:

- Current `dc_*` source facts, including `dc_ticker_swing_signal_daily`, `dc_group_swing_signal_daily`, `dc_group_synthetic_ohlc_daily`, `dc_group_index_daily`, and `dc_pipeline_watermark`.
- Current legacy Datacenter reports over `dc_*`.
- Current `ec_*` sidecar tables/loaders/planners.
- `ec_source_layer`.

The `dev_tools/run_report_canonical_v2_*.py` entrypoints are retained only as retired stubs for compatibility and discoverability. They produce deterministic retirement errors, return exit code `2`, do not open databases, do not write outputs, and do not import removed V2 core modules.

Migrations `004`-`014` are not changed by this documentation archive phase. They remain a separate migration strategy decision.

Database cleanup is also a separate later phase. Dropping any `dc_report_*_v2` tables requires a read-only preflight, a verified backup, and an explicit drop plan.

Do not use these archived documents as current architecture.
