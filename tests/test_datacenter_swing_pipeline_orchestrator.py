from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices import swing_pipeline_orchestrator as orchestrator
from analysis.datacenter_indices.technical_relevance_context import (
    load_datacenter_pipeline_technical_relevance_tickers,
)


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
        "weekly_swing_report",
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
    for _ in range(13):
        perf_values.extend([stage_start, stage_start + 0.25])
        stage_start += 1.0
    perf_values.append(13.25)

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
    assert summary["pipeline.total_duration_seconds"] == "13.250"
    assert summary["pipeline_stage.automatic_technical_relevance.status"] == "OK"
    assert summary["pipeline_stage.automatic_technical_relevance.duration_seconds"] == "0.250"
    assert summary["pipeline_stage.daily_report.duration_seconds"] == "0.250"
    assert summary["pipeline_stage.weekly_swing_report.duration_seconds"] == "0.250"
    assert calls[0][0] == "techrel"
    assert calls[1][0] == "daily"
    assert calls[1][1]["technical_relevance_run_id"] == "AUTO_GENERATED_RUN"
    assert calls[2][0] == "weekly"
    assert calls[2][1]["technical_relevance_run_id"] == "AUTO_GENERATED_RUN"


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


def test_automatic_duplicate_run_failure_propagates_clearly(tmp_path, monkeypatch):
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

    def _raise_duplicate(*args, **kwargs):
        raise sqlite3.IntegrityError("UNIQUE constraint failed: technical_signal_relevance_runs.run_id")

    monkeypatch.setattr(orchestrator, "run_technical_signal_relevance_for_tickers", _raise_duplicate)

    with pytest.raises(sqlite3.IntegrityError, match="technical_signal_relevance_runs.run_id"):
        orchestrator._run_automatic_technical_relevance_stage(
            analysis_db=analysis_db,
            signal_date="2026-05-15",
            taxonomy_version="DC_TAXONOMY_FULL_V1",
            signal_version="DC_SWING_SIGNAL_V1",
            generated_at_utc="2026-05-22T00:00:00Z",
        )
