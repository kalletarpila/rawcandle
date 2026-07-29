from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices import swing_pipeline_orchestrator as orchestrator
from analysis.datacenter_indices.pipeline_plan import (
    Stage2DownstreamPlan,
    Stage2IncrementalPlan,
)
from analysis.datacenter_indices.pipeline_watermark import (
    list_pipeline_watermarks,
    upsert_pipeline_watermark,
)
from analysis.datacenter_indices.technical_relevance_context import (
    load_datacenter_pipeline_technical_relevance_tickers,
)
from rawcandle.technical_signal_relevance_persistence import apply_technical_signal_relevance_migration


def _create_analysis_db(path: Path) -> None:
    DatabaseManager(str(path)).close()


def _insert_ticker_row(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    ticker: str,
    signal_version: str,
    breakout_signal: int = 0,
    pullback_signal: int = 0,
    exit_risk_signal: int = 0,
    bullish_divergence_signal: int = 0,
    bearish_divergence_signal: int = 0,
    hidden_bullish_divergence_signal: int = 0,
    hidden_bearish_divergence_signal: int = 0,
    bullish_candle_signal: int = 0,
    bearish_candle_signal: int = 0,
) -> None:
    conn.execute(
        """
        INSERT INTO dc_ticker_swing_signal_daily (
            signal_date,
            taxonomy_version,
            ticker,
            bullish_divergence_signal,
            bearish_divergence_signal,
            hidden_bullish_divergence_signal,
            hidden_bearish_divergence_signal,
            bullish_candle_signal,
            bearish_candle_signal,
            breakout_signal,
            pullback_signal,
            exit_risk_signal,
            signal_version,
            run_id,
            created_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            signal_date,
            taxonomy_version,
            ticker,
            bullish_divergence_signal,
            bearish_divergence_signal,
            hidden_bullish_divergence_signal,
            hidden_bearish_divergence_signal,
            bullish_candle_signal,
            bearish_candle_signal,
            breakout_signal,
            pullback_signal,
            exit_risk_signal,
            signal_version,
            "RUN_A",
            "2026-05-22T00:00:00Z",
        ),
    )


def _base_kwargs(tmp_path: Path) -> dict[str, object]:
    return {
        "price_db": tmp_path / "osakedata.db",
        "analysis_db": tmp_path / "analysis.db",
        "taxonomy_csv": tmp_path / "taxonomy.csv",
        "taxonomy_version": "DC_TAXONOMY_FULL_V1",
        "market": "usa",
        "signal_date": "2026-05-15",
        "start_date": "2026-01-01",
        "index_base_date": "2020-01-01",
        "output_dir": tmp_path / "reports",
    }


def _stage2_plan(
    *,
    mode: str = "INCREMENTAL",
    materialization_start: str | None = "2026-05-13",
    materialization_end: str | None = "2026-05-15",
    output_dates: list[str] | None = None,
    reason_code: str = "NEW_SIGNAL_DATES_WITH_LOOKBACK_OVERLAP",
) -> Stage2IncrementalPlan:
    output_dates = (
        ["2026-05-13", "2026-05-14", "2026-05-15"]
        if output_dates is None
        else output_dates
    )
    return Stage2IncrementalPlan(
        component="TICKER_SWING_BASE",
        mode=mode,
        requested_start="2026-01-01",
        requested_end="2026-05-15",
        effective_requested_end="2026-05-15",
        watermark_start="2026-01-01",
        watermark_end="2026-05-12",
        materialization_start=materialization_start,
        materialization_end=materialization_end,
        calculation_input_start="2026-01-01" if output_dates else None,
        calculation_input_end=materialization_end,
        overlap_trading_days=5,
        max_valid_price_rows=220,
        write_mode="replace-date",
        reason_code=reason_code,
        reason_details={},
        valid_signal_dates=output_dates,
        output_dates=output_dates,
        downstream_stage_plans=[
            Stage2DownstreamPlan(
                3,
                "GROUP_SWING_BASE",
                "Group swing base metrics",
                True,
                materialization_start or "",
                materialization_end or "",
                "TEST",
            ),
            Stage2DownstreamPlan(
                7,
                "GROUP_TIMING",
                "Group timing states",
                True,
                materialization_start or "",
                materialization_end or "",
                "TEST",
            ),
            Stage2DownstreamPlan(
                8,
                "GROUP_OVERHEAT",
                "Group overheat risk",
                True,
                materialization_start or "",
                materialization_end or "",
                "TEST",
            ),
            Stage2DownstreamPlan(
                9,
                "TICKER_SCANNER",
                "Ticker scanners",
                True,
                materialization_start or "",
                materialization_end or "",
                "TEST",
            ),
        ],
        excluded_stage_plans=[],
    )


def _arg_value(argv: list[str], option: str) -> str:
    return argv[argv.index(option) + 1]


@pytest.fixture(autouse=True)
def _isolate_windows_report_copy_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "WINDOWS_REPORT_COPY_DIR", tmp_path / "windows_reports")


def _insert_technical_relevance_run(
    analysis_db: Path,
    *,
    run_id: str,
    created_at_utc: str = "2026-05-22T00:00:00Z",
) -> None:
    with sqlite3.connect(analysis_db) as conn:
        apply_technical_signal_relevance_migration(conn)
        conn.execute(
            """
            INSERT INTO technical_signal_relevance_runs (
                run_id,
                relevance_rule_version,
                mapping_version,
                reason_version,
                config_snapshot_json,
                created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "TECH_REL_RULES_V1",
                "TECH_REL_MAPPING_V1",
                "TECH_REL_REASON_V1",
                "{}",
                created_at_utc,
            ),
        )
        conn.commit()


def _fake_technical_relevance_summary(run_id: str = "AUTO_REL_RUN") -> dict[str, object]:
    return {
        "summary": {
            "run_id": run_id,
            "ticker_count": 3,
            "start_date": "2026-03-31",
            "end_date": "2026-05-15",
            "observations_seen": 10,
            "records_written": 10,
            "relevant_count": 4,
            "weak_context_count": 3,
            "noise_count": 3,
            "unknown_signal_count": 0,
            "missing_dow_context_count": 0,
            "missing_bar_index_count": 0,
        }
    }


def _make_perf_counter(values: list[float]):
    iterator = iter(values)

    def _fake_perf_counter() -> float:
        return next(iterator)

    return _fake_perf_counter


def test_load_datacenter_pipeline_technical_relevance_tickers_filters_and_orders(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    _insert_ticker_row(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        ticker="BBB",
        signal_version="DC_SWING_SIGNAL_V1",
        breakout_signal=1,
    )
    _insert_ticker_row(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        ticker=" AAA ",
        signal_version="DC_SWING_SIGNAL_V1",
    )
    _insert_ticker_row(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        ticker="AAA",
        signal_version="DC_SWING_SIGNAL_V1",
        exit_risk_signal=1,
    )
    _insert_ticker_row(
        conn,
        signal_date="2026-05-14",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        ticker="ZZZ",
        signal_version="DC_SWING_SIGNAL_V1",
    )
    _insert_ticker_row(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="OTHER_VERSION",
        ticker="YYY",
        signal_version="DC_SWING_SIGNAL_V1",
    )
    _insert_ticker_row(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        ticker="XXX",
        signal_version="OTHER_SIGNAL_VERSION",
    )
    conn.commit()

    tickers = load_datacenter_pipeline_technical_relevance_tickers(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        signal_version="DC_SWING_SIGNAL_V1",
    )

    assert tickers == ["AAA", "BBB"]


def test_load_datacenter_pipeline_technical_relevance_tickers_includes_zero_signal_rows(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    _insert_ticker_row(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        ticker="ZERO",
        signal_version="DC_SWING_SIGNAL_V1",
        breakout_signal=0,
        pullback_signal=0,
        exit_risk_signal=0,
        bullish_divergence_signal=0,
        bearish_divergence_signal=0,
        hidden_bullish_divergence_signal=0,
        hidden_bearish_divergence_signal=0,
        bullish_candle_signal=0,
        bearish_candle_signal=0,
    )
    conn.commit()

    tickers = load_datacenter_pipeline_technical_relevance_tickers(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        signal_version="DC_SWING_SIGNAL_V1",
    )

    assert tickers == ["ZERO"]


def test_compute_datacenter_technical_relevance_date_range_is_signal_date_minus_45_days():
    assert orchestrator.compute_datacenter_technical_relevance_date_range("2026-05-15") == (
        "2026-03-31",
        "2026-05-15",
    )


def test_build_datacenter_technical_relevance_run_id_is_deterministic():
    run_id = orchestrator.build_datacenter_technical_relevance_run_id(
        taxonomy_version="DC TAXONOMY FULL V1",
        signal_date="2026-05-15",
    )
    assert run_id == "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15"
    assert (
        orchestrator.build_datacenter_technical_relevance_run_id(
            taxonomy_version="DC TAXONOMY FULL V1",
            signal_date="2026-05-15",
        )
        == run_id
    )


def test_pipeline_stage_keys_are_stable_and_contain_no_spaces():
    assert orchestrator.PIPELINE_STAGE_KEYS == (
        "datacenter_base_index",
        "ticker_swing_base_snapshots",
        "group_swing_base_metrics",
        "synthetic_ohlc_base",
        "relative_ohlc20",
        "group_structure_bos_reset",
        "group_timing_states",
        "group_overheat_risk",
        "ticker_scanners",
        "pipeline_audit",
        "automatic_technical_relevance",
        "daily_report",
        "rolling_30_report",
        "rolling_5_report",
        "rolling_2_report",
        "windows_report_copy",
    )
    assert all(" " not in key for key in orchestrator.PIPELINE_STAGE_KEYS)


def test_automatic_technical_relevance_stage_fails_on_empty_universe(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    with pytest.raises(RuntimeError, match="ticker universe is empty"):
        orchestrator._run_automatic_technical_relevance_stage(
            analysis_db=analysis_db,
            signal_date="2026-05-15",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            signal_version="DC_SWING_SIGNAL_V1",
            generated_at_utc="2026-05-22T00:00:00Z",
        )


def test_dry_run_auto_mode_uses_existing_db_snapshot_count_when_available(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    _insert_ticker_row(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        ticker="BBB",
        signal_version="DC_SWING_SIGNAL_V1",
    )
    _insert_ticker_row(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        ticker="AAA",
        signal_version="DC_SWING_SIGNAL_V1",
    )
    conn.commit()

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        dry_run=True,
    )

    assert result["summary"]["technical_relevance.mode"] == "auto"
    assert result["summary"]["technical_relevance.ticker_count"] == 2
    assert result["summary"]["technical_relevance.ticker_count_status"] == "EXISTING_DB_SNAPSHOT"
    assert result["summary"]["technical_relevance.status"] == "DRY_RUN"


def test_dry_run_stage_summaries_use_stable_keys_and_zero_durations(tmp_path, monkeypatch):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    monkeypatch.setattr(orchestrator, "perf_counter", _make_perf_counter([10.0, 10.456]))

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        dry_run=True,
        no_technical_relevance=True,
    )

    summary = result["summary"]
    assert summary["pipeline.total_duration_seconds"] == "0.456"
    assert summary["pipeline_stage.datacenter_base_index.status"] == "DRY_RUN"
    assert summary["pipeline_stage.datacenter_base_index.duration_seconds"] == "0.000"
    assert summary["pipeline_stage.automatic_technical_relevance.status"] == "SKIPPED"
    assert summary["pipeline_stage.automatic_technical_relevance.duration_seconds"] == "0.000"


def test_dry_run_stage_2_profile_reports_dry_run_status(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        dry_run=True,
        profile_ticker_swing_snapshots=True,
        no_technical_relevance=True,
    )

    assert result["summary"]["ticker_swing_snapshot_profile.status"] == "DRY_RUN"


def test_dry_run_auto_mode_reports_not_available_when_snapshot_rows_do_not_exist(tmp_path):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        dry_run=True,
    )

    assert result["summary"]["technical_relevance.mode"] == "auto"
    assert result["summary"]["technical_relevance.ticker_count"] == 0
    assert result["summary"]["technical_relevance.ticker_count_status"] == "NOT_AVAILABLE_DRY_RUN"
    assert result["summary"]["technical_relevance.status"] == "DRY_RUN"


def test_default_mode_runs_automatic_technical_relevance_and_threads_generated_run_id(tmp_path, monkeypatch):
    _create_analysis_db(tmp_path / "analysis.db")
    calls: list[tuple[str, object]] = []

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _auto(**kwargs):
        calls.append(("techrel", dict(kwargs)))
        return _fake_technical_relevance_summary("AUTO_GENERATED_RUN")

    def _daily(**kwargs):
        calls.append(("daily", dict(kwargs)))
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily", encoding="utf-8")
        kwargs["output_csv"].write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append(("weekly", dict(kwargs)))
        kwargs["output_md"].write_text("weekly", encoding="utf-8")
        kwargs["output_csv"].write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    perf_values = [0.0]
    stage_start = 1.0
    for _ in range(16):
        perf_values.extend([stage_start, stage_start + 0.25])
        stage_start += 1.0
    perf_values.append(16.25)

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _auto)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(
        orchestrator,
        "perf_counter",
        _make_perf_counter(perf_values),
    )

    result = orchestrator.run_datacenter_swing_pipeline(**_base_kwargs(tmp_path))

    summary = result["summary"]
    assert summary["technical_relevance.mode"] == "auto"
    assert summary["technical_relevance.run_id"] == "AUTO_GENERATED_RUN"
    assert summary["technical_relevance.ticker_count_status"] == "ACTUAL_RUN"
    assert summary["technical_relevance.status"] == "OK"
    assert "technical_relevance.existing_run_reused" not in summary
    assert summary["pipeline.total_duration_seconds"] == "16.250"
    assert summary["pipeline_stage.automatic_technical_relevance.status"] == "OK"
    assert summary["pipeline_stage.automatic_technical_relevance.duration_seconds"] == "0.250"
    assert summary["pipeline_stage.daily_report.duration_seconds"] == "0.250"
    assert summary["pipeline_stage.rolling_30_report.duration_seconds"] == "0.250"
    assert summary["pipeline_stage.rolling_5_report.duration_seconds"] == "0.250"
    assert summary["pipeline_stage.rolling_2_report.duration_seconds"] == "0.250"
    assert summary["pipeline_stage.windows_report_copy.duration_seconds"] == "0.250"
    assert calls[0][0] == "techrel"
    assert calls[1][0] == "daily"
    assert calls[1][1]["technical_relevance_run_id"] == "AUTO_GENERATED_RUN"
    assert calls[2][0] == "weekly"
    assert calls[2][1]["technical_relevance_run_id"] == "AUTO_GENERATED_RUN"
    assert calls[2][1]["window_size"] == 30
    assert calls[3][0] == "weekly"
    assert calls[3][1]["technical_relevance_run_id"] == "AUTO_GENERATED_RUN"
    assert calls[3][1]["window_size"] == 5
    assert calls[4][0] == "weekly"
    assert calls[4][1]["technical_relevance_run_id"] == "AUTO_GENERATED_RUN"
    assert calls[4][1]["window_size"] == 2
    copied_report_dir = tmp_path / "windows_reports"
    assert (copied_report_dir / Path(summary["daily_report_path"]).name).read_text(encoding="utf-8") == "daily"
    assert (copied_report_dir / Path(summary["rolling_30_report_path"]).name).read_text(encoding="utf-8") == "weekly"
    assert (copied_report_dir / Path(summary["rolling_5_report_path"]).name).read_text(encoding="utf-8") == "weekly"
    assert (copied_report_dir / Path(summary["rolling_2_report_path"]).name).read_text(encoding="utf-8") == "weekly"


def test_existing_run_mode_skips_automatic_technical_relevance_and_threads_provided_run_id(tmp_path, monkeypatch):
    _create_analysis_db(tmp_path / "analysis.db")
    calls: list[tuple[str, object]] = []

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _auto(**kwargs):
        raise AssertionError("automatic technical relevance must not run in existing-run mode")

    def _daily(**kwargs):
        calls.append(("daily", dict(kwargs)))
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily", encoding="utf-8")
        kwargs["output_csv"].write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append(("weekly", dict(kwargs)))
        kwargs["output_md"].write_text("weekly", encoding="utf-8")
        kwargs["output_csv"].write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _auto)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        technical_relevance_run_id="EXISTING_RUN",
    )

    assert result["summary"]["technical_relevance.mode"] == "existing_run"
    assert result["summary"]["technical_relevance.ticker_count_status"] == "NOT_APPLICABLE_EXISTING_RUN"
    assert result["summary"]["technical_relevance.status"] == "SKIPPED_EXISTING_RUN"
    assert calls[0][1]["technical_relevance_run_id"] == "EXISTING_RUN"
    assert calls[1][1]["technical_relevance_run_id"] == "EXISTING_RUN"
    assert calls[2][1]["technical_relevance_run_id"] == "EXISTING_RUN"
    assert calls[3][1]["technical_relevance_run_id"] == "EXISTING_RUN"


def test_disabled_mode_skips_automatic_technical_relevance_and_passes_none(tmp_path, monkeypatch):
    _create_analysis_db(tmp_path / "analysis.db")
    calls: list[tuple[str, object]] = []

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _auto(**kwargs):
        raise AssertionError("automatic technical relevance must not run in disabled mode")

    def _daily(**kwargs):
        calls.append(("daily", dict(kwargs)))
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily", encoding="utf-8")
        kwargs["output_csv"].write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append(("weekly", dict(kwargs)))
        kwargs["output_md"].write_text("weekly", encoding="utf-8")
        kwargs["output_csv"].write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _auto)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        no_technical_relevance=True,
    )

    assert result["summary"]["technical_relevance.mode"] == "disabled"
    assert result["summary"]["technical_relevance.ticker_count_status"] == "DISABLED"
    assert result["summary"]["technical_relevance.status"] == "DISABLED"
    assert result["summary"]["pipeline_stage.automatic_technical_relevance.status"] == "SKIPPED"
    assert result["summary"]["pipeline_stage.automatic_technical_relevance.duration_seconds"] == "0.000"
    assert calls[0][1]["technical_relevance_run_id"] is None
    assert calls[1][1]["technical_relevance_run_id"] is None
    assert calls[2][1]["technical_relevance_run_id"] is None
    assert calls[3][1]["technical_relevance_run_id"] is None


def test_automatic_technical_relevance_reuses_existing_run_id_without_recomputing(tmp_path, monkeypatch):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    _insert_ticker_row(
        conn,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        ticker="AAA",
        signal_version="DC_SWING_SIGNAL_V1",
    )
    conn.commit()
    existing_run_id = "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15"
    _insert_technical_relevance_run(
        analysis_db,
        run_id=existing_run_id,
    )

    def _fail_recompute(*args, **kwargs):
        raise AssertionError("existing technical relevance run should be reused without recomputing")

    monkeypatch.setattr(orchestrator, "run_technical_signal_relevance_for_tickers", _fail_recompute)

    result = orchestrator._run_automatic_technical_relevance_stage(
        analysis_db=analysis_db,
        signal_date="2026-05-15",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        signal_version="DC_SWING_SIGNAL_V1",
        generated_at_utc="2026-05-22T00:00:00Z",
    )

    assert result["summary"]["run_id"] == existing_run_id
    assert result["summary"]["existing_run_reused"] == 1
    assert result["summary"]["skip_reason"] == "RUN_ID_ALREADY_EXISTS"
    assert result["summary"]["ticker_count"] == 1
    assert result["summary"]["records_written"] == 0


def test_stage2_incremental_success_wires_planner_range_to_dirty_chain_and_watermarks(
    tmp_path,
    monkeypatch,
):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    calls: list[tuple[str, list[str]]] = []

    def _planner(**kwargs):
        assert kwargs["overlap_trading_days"] == 2
        return _stage2_plan(
            materialization_start="2026-05-13",
            materialization_end="2026-05-15",
        )

    def _index(argv: list[str]) -> int:
        calls.append(("index", list(argv)))
        return 0

    def _ticker(argv: list[str]) -> int:
        calls.append(("ticker", list(argv)))
        return 0

    def _group(argv: list[str]) -> int:
        calls.append(("group", list(argv)))
        return 0

    def _synthetic(argv: list[str]) -> int:
        calls.append(("synthetic", list(argv)))
        return 0

    monkeypatch.setattr(orchestrator, "build_stage2_incremental_plan", _planner)
    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _index)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _ticker)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _group)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _synthetic)

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        stage2_incremental=True,
        stage2_overlap_trading_days=2,
        skip_audit=True,
        skip_reports=True,
        no_technical_relevance=True,
    )

    summary = result["summary"]
    assert summary["stage2_incremental_enabled"] == "true"
    assert summary["stage2_plan_mode"] == "INCREMENTAL"
    assert summary["stage2_planned_materialization_start"] == "2026-05-13"
    assert summary["stage2_execution_status"] == "EXECUTED"
    assert summary["stage2_attempted_dates"] == "2026-05-13,2026-05-14,2026-05-15"
    assert summary["stage2_completed_dates"] == "2026-05-13,2026-05-14,2026-05-15"
    assert summary["downstream_dirty_start"] == "2026-05-13"
    assert summary["downstream_incremental_stages"] == "3,7,8,9"

    ticker_base = calls[1][1]
    group_base = calls[2][1]
    structure = calls[5][1]
    timing = calls[6][1]
    overheat = calls[7][1]
    scanner = calls[8][1]
    assert (_arg_value(ticker_base, "--start-date"), _arg_value(ticker_base, "--end-date")) == (
        "2026-05-13",
        "2026-05-15",
    )
    assert (_arg_value(group_base, "--start-date"), _arg_value(group_base, "--end-date")) == (
        "2026-05-13",
        "2026-05-15",
    )
    assert (_arg_value(timing, "--start-date"), _arg_value(timing, "--end-date")) == (
        "2026-05-13",
        "2026-05-15",
    )
    assert (_arg_value(overheat, "--start-date"), _arg_value(overheat, "--end-date")) == (
        "2026-05-13",
        "2026-05-15",
    )
    assert (_arg_value(scanner, "--start-date"), _arg_value(scanner, "--end-date")) == (
        "2026-05-13",
        "2026-05-15",
    )
    assert (_arg_value(structure, "--start-date"), _arg_value(structure, "--end-date")) == (
        "2026-01-01",
        "2026-05-15",
    )

    watermarks = {
        row["component_name"]: row
        for row in list_pipeline_watermarks(
            analysis_db_path=analysis_db,
            taxonomy_version="DC_TAXONOMY_FULL_V1",
        )
    }
    assert watermarks["TICKER_SWING_BASE"]["start_date"] == "2026-05-13"
    assert watermarks["GROUP_SWING_BASE"]["start_date"] == "2026-05-13"
    assert watermarks["GROUP_TIMING"]["start_date"] == "2026-05-13"
    assert watermarks["GROUP_OVERHEAT"]["start_date"] == "2026-05-13"
    assert watermarks["TICKER_SCANNER"]["start_date"] == "2026-05-13"
    assert watermarks["SYNTHETIC_OHLC_STRUCTURE"]["start_date"] == "2026-01-01"


def test_stage2_incremental_success_preserves_existing_dirty_chain_coverage_start(
    tmp_path,
    monkeypatch,
):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    coverage_components = (
        ("TICKER_SWING_BASE", "usa"),
        ("GROUP_SWING_BASE", ""),
        ("GROUP_TIMING", ""),
        ("GROUP_OVERHEAT", ""),
        ("TICKER_SCANNER", ""),
    )
    for component_name, market in coverage_components:
        upsert_pipeline_watermark(
            analysis_db_path=analysis_db,
            component_name=component_name,
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            market=market,
            signal_version="DC_SWING_SIGNAL_V1",
            start_date="2026-01-01",
            end_date="2026-05-14",
            status="OK",
            last_successful_at_utc="2026-05-18T10:00:00Z",
        )

    def _planner(**kwargs):
        return _stage2_plan(
            materialization_start="2026-05-13",
            materialization_end="2026-05-15",
        )

    monkeypatch.setattr(orchestrator, "build_stage2_incremental_plan", _planner)
    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", lambda argv: 0)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", lambda argv: 0)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", lambda argv: 0)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", lambda argv: 0)

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        stage2_incremental=True,
        skip_audit=True,
        skip_reports=True,
        no_technical_relevance=True,
    )

    assert result["summary"]["stage2_plan_mode"] == "INCREMENTAL"
    assert result["summary"]["stage2_actual_materialized_start"] == "2026-05-13"
    watermarks = {
        row["component_name"]: row
        for row in list_pipeline_watermarks(
            analysis_db_path=analysis_db,
            taxonomy_version="DC_TAXONOMY_FULL_V1",
        )
    }
    for component_name, _market in coverage_components:
        assert watermarks[component_name]["start_date"] == "2026-01-01"
        assert watermarks[component_name]["end_date"] == "2026-05-15"


def test_stage2_incremental_full_mode_uses_planner_materialization_range(
    tmp_path,
    monkeypatch,
):
    _create_analysis_db(tmp_path / "analysis.db")
    calls: list[list[str]] = []

    monkeypatch.setattr(
        orchestrator,
        "build_stage2_incremental_plan",
        lambda **kwargs: _stage2_plan(
            mode="FULL",
            materialization_start="2026-01-01",
            materialization_end="2026-05-15",
            reason_code="MISSING_COMPATIBLE_WATERMARK",
        ),
    )
    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", lambda argv: 0)
    monkeypatch.setattr(
        orchestrator,
        "run_datacenter_ticker_swing_signals_main",
        lambda argv: calls.append(list(argv)) or 0,
    )
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", lambda argv: 0)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", lambda argv: 0)

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        stage2_incremental=True,
        skip_audit=True,
        skip_reports=True,
        no_technical_relevance=True,
    )

    assert result["summary"]["stage2_plan_mode"] == "FULL"
    assert (_arg_value(calls[0], "--start-date"), _arg_value(calls[0], "--end-date")) == (
        "2026-01-01",
        "2026-05-15",
    )


def test_stage2_incremental_skip_skips_only_stage2_dirty_chain_without_watermarks(
    tmp_path,
    monkeypatch,
):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    calls: list[str] = []

    monkeypatch.setattr(
        orchestrator,
        "build_stage2_incremental_plan",
        lambda **kwargs: _stage2_plan(
            mode="SKIP",
            materialization_start=None,
            materialization_end=None,
            output_dates=[],
            reason_code="WATERMARK_COVERS_REQUESTED_TARGET",
        ),
    )
    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", lambda argv: calls.append("index") or 0)
    monkeypatch.setattr(
        orchestrator,
        "run_datacenter_ticker_swing_signals_main",
        lambda argv: (_ for _ in ()).throw(AssertionError("ticker dirty chain must be skipped")),
    )
    monkeypatch.setattr(
        orchestrator,
        "run_datacenter_group_swing_signals_main",
        lambda argv: (_ for _ in ()).throw(AssertionError("group dirty chain must be skipped")),
    )
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", lambda argv: calls.append("synthetic") or 0)

    result = orchestrator.run_datacenter_swing_pipeline(
        **_base_kwargs(tmp_path),
        stage2_incremental=True,
        skip_audit=True,
        skip_reports=True,
        no_technical_relevance=True,
    )

    assert calls == ["index", "synthetic", "synthetic", "synthetic"]
    summary = result["summary"]
    assert summary["stage2_plan_mode"] == "SKIP"
    assert summary["stage2_execution_status"] == "SKIPPED_BY_INCREMENTAL_PLAN"
    assert summary["planner_skipped_stages"] == (
        "ticker_swing_base_snapshots,group_swing_base_metrics,group_timing_states,"
        "group_overheat_risk,ticker_scanners"
    )
    assert summary["pipeline_stage.ticker_swing_base_snapshots.status"] == "SKIPPED"
    assert summary["pipeline_stage.ticker_swing_base_snapshots.execution_status"] == "SKIPPED_BY_INCREMENTAL_PLAN"
    assert summary["pipeline_stage.group_structure_bos_reset.execution_status"] == "EXECUTED"

    watermarks = list_pipeline_watermarks(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )
    dirty_components = {
        "TICKER_SWING_BASE",
        "GROUP_SWING_BASE",
        "GROUP_TIMING",
        "GROUP_OVERHEAT",
        "TICKER_SCANNER",
    }
    assert dirty_components.isdisjoint({row["component_name"] for row in watermarks})


def test_stage2_incremental_stage2_failure_requires_retry_and_writes_no_stage2_watermark(
    tmp_path,
    monkeypatch,
    capsys,
):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    monkeypatch.setattr(orchestrator, "build_stage2_incremental_plan", lambda **kwargs: _stage2_plan())
    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", lambda argv: 0)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", lambda argv: 1)
    monkeypatch.setattr(
        orchestrator,
        "run_datacenter_group_swing_signals_main",
        lambda argv: (_ for _ in ()).throw(AssertionError("downstream must not run")),
    )

    with pytest.raises(RuntimeError, match="Stage failed"):
        orchestrator.run_datacenter_swing_pipeline(
            **_base_kwargs(tmp_path),
            stage2_incremental=True,
            skip_audit=True,
            skip_reports=True,
            no_technical_relevance=True,
        )

    lines = capsys.readouterr().out.splitlines()
    assert "SUMMARY stage2_execution_status=FAILED" in lines
    assert "SUMMARY stage2_retry_required=true" in lines
    watermarks = list_pipeline_watermarks(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )
    assert "TICKER_SWING_BASE" not in {row["component_name"] for row in watermarks}


@pytest.mark.parametrize(
    ("failing_stage", "blocked_later_stage"),
    [
        ("group_swing_base_metrics", "group_timing_states"),
        ("group_timing_states", "group_overheat_risk"),
        ("group_overheat_risk", "ticker_scanners"),
        ("ticker_scanners", None),
    ],
)
def test_stage2_incremental_downstream_failure_stops_later_dirty_chain(
    tmp_path,
    monkeypatch,
    failing_stage: str,
    blocked_later_stage: str | None,
):
    _create_analysis_db(tmp_path / "analysis.db")
    stage_calls: list[str] = []

    def _stage_from_argv(kind: str, argv: list[str]) -> str:
        if kind == "ticker":
            return "ticker_scanners" if "--scanner-only" in argv else "ticker_swing_base_snapshots"
        if "--timing-only" in argv:
            return "group_timing_states"
        if "--overheat-only" in argv:
            return "group_overheat_risk"
        return "group_swing_base_metrics"

    def _ticker(argv: list[str]) -> int:
        stage = _stage_from_argv("ticker", argv)
        stage_calls.append(stage)
        return 1 if stage == failing_stage else 0

    def _group(argv: list[str]) -> int:
        stage = _stage_from_argv("group", argv)
        stage_calls.append(stage)
        return 1 if stage == failing_stage else 0

    monkeypatch.setattr(orchestrator, "build_stage2_incremental_plan", lambda **kwargs: _stage2_plan())
    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", lambda argv: stage_calls.append("index") or 0)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _ticker)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _group)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", lambda argv: stage_calls.append("synthetic") or 0)

    with pytest.raises(RuntimeError, match="Stage failed"):
        orchestrator.run_datacenter_swing_pipeline(
            **_base_kwargs(tmp_path),
            stage2_incremental=True,
            skip_audit=True,
            skip_reports=True,
            no_technical_relevance=True,
        )

    assert failing_stage in stage_calls
    if blocked_later_stage is not None:
        assert blocked_later_stage not in stage_calls


def test_auto_mode_existing_run_reuse_threads_existing_run_id_to_all_reports(tmp_path, monkeypatch):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_technical_relevance_run(
        analysis_db,
        run_id="DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15",
    )
    calls: list[tuple[str, object]] = []

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _auto(**kwargs):
        calls.append(("techrel", dict(kwargs)))
        return {
            "summary": {
                "run_id": "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15",
                "ticker_count": 3,
                "start_date": "2026-03-31",
                "end_date": "2026-05-15",
                "observations_seen": 0,
                "records_written": 0,
                "relevant_count": 0,
                "weak_context_count": 0,
                "noise_count": 0,
                "unknown_signal_count": 0,
                "missing_dow_context_count": 0,
                "missing_bar_index_count": 0,
                "existing_run_reused": 1,
                "skip_reason": "RUN_ID_ALREADY_EXISTS",
            }
        }

    def _daily(**kwargs):
        calls.append(("daily", dict(kwargs)))
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily", encoding="utf-8")
        kwargs["output_csv"].write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append(("weekly", dict(kwargs)))
        kwargs["output_md"].write_text("weekly", encoding="utf-8")
        kwargs["output_csv"].write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _auto)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    result = orchestrator.run_datacenter_swing_pipeline(**_base_kwargs(tmp_path))

    summary = result["summary"]
    assert summary["technical_relevance.mode"] == "auto"
    assert summary["technical_relevance.run_id"] == "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15"
    assert summary["technical_relevance.status"] == "SKIPPED_EXISTING_RUN"
    assert summary["technical_relevance.ticker_count_status"] == "EXISTING_RUN_REUSED"
    assert summary["technical_relevance.existing_run_reused"] == 1
    assert summary["pipeline_stage.automatic_technical_relevance.status"] == "OK"
    assert calls[1][1]["technical_relevance_run_id"] == "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15"
    assert calls[2][1]["technical_relevance_run_id"] == "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15"
    assert calls[3][1]["technical_relevance_run_id"] == "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15"
    assert calls[4][1]["technical_relevance_run_id"] == "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15"
    assert calls[4][1]["technical_relevance_run_id"] == "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15"


def test_windows_report_copy_stage_fails_when_active_report_file_is_missing(tmp_path, monkeypatch):
    _create_analysis_db(tmp_path / "analysis.db")

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _auto(**kwargs):
        return {
            "summary": {
                "run_id": "AUTO_GENERATED_RUN",
                "ticker_count": 3,
                "start_date": "2026-03-31",
                "end_date": "2026-05-15",
                "observations_seen": 10,
                "records_written": 10,
                "relevant_count": 4,
                "weak_context_count": 3,
                "noise_count": 3,
                "unknown_signal_count": 0,
                "missing_dow_context_count": 0,
                "missing_bar_index_count": 0,
            }
        }

    def _daily(**kwargs):
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily", encoding="utf-8")
        kwargs["output_csv"].write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    def _weekly_missing_csv(**kwargs):
        kwargs["output_md"].write_text("weekly", encoding="utf-8")
        if kwargs["window_size"] != 5:
            kwargs["output_csv"].write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _auto)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly_missing_csv)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    with pytest.raises(RuntimeError, match="windows report copy stage missing source files"):
        orchestrator.run_datacenter_swing_pipeline(**_base_kwargs(tmp_path))
