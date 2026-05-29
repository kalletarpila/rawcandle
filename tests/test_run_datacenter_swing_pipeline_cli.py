from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from analysis.datacenter_indices import swing_pipeline_orchestrator as orchestrator
from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.pipeline_watermark import list_pipeline_watermarks
from run_datacenter_swing_pipeline import main as run_datacenter_swing_pipeline_main


def _base_args(tmp_path: Path) -> list[str]:
    return [
        "--price-db",
        str(tmp_path / "osakedata.db"),
        "--analysis-db",
        str(tmp_path / "analysis.db"),
        "--taxonomy-csv",
        str(tmp_path / "taxonomy.csv"),
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--market",
        "usa",
        "--signal-date",
        "2026-05-15",
        "--start-date",
        "2026-01-01",
        "--index-base-date",
        "2020-01-01",
        "--output-dir",
        str(tmp_path / "reports"),
    ]


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


def _seed_persisted_ticker_rows(
    analysis_db: Path,
    *,
    signal_date: str = "2026-05-15",
    taxonomy_version: str = "DC_TAXONOMY_FULL_V1",
    signal_version: str = orchestrator.DEFAULT_SIGNAL_VERSION,
    tickers: list[str],
) -> None:
    DatabaseManager(str(analysis_db)).close()
    with sqlite3.connect(analysis_db) as conn:
        for ticker in dict.fromkeys(tickers):
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
                ) VALUES (?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, ?, ?)
                """,
                (
                    signal_date,
                    taxonomy_version,
                    ticker,
                    signal_version,
                    "RUN_A",
                    "2026-05-22T00:00:00Z",
                ),
            )
        conn.commit()


def _make_perf_counter(values: list[float]):
    iterator = iter(values)

    def _fake_perf_counter() -> float:
        return next(iterator)

    return _fake_perf_counter


@pytest.fixture(autouse=True)
def _isolate_windows_report_copy_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "WINDOWS_REPORT_COPY_DIR", tmp_path / "windows_reports")


def test_dry_run_prints_planned_stages_and_does_not_call_stage_runners(tmp_path, monkeypatch, capsys):
    def _fail(*args, **kwargs):
        raise AssertionError("stage runner should not be called in dry-run")

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _fail)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _fail)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _fail)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _fail)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _fail)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _fail)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _fail)
    monkeypatch.setattr(orchestrator, "perf_counter", _make_perf_counter([0.0, 0.125]))

    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path) + ["--dry-run"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "=== Stage 1/16: Datacenter base index ==="
    assert lines[1].startswith("PLAN --ohlcv-db ")
    assert any("Automatic technical relevance" in line for line in lines)
    assert any(line == "=== Stage 16/16: Windows report copy ===" for line in lines)
    assert "SUMMARY pipeline_stage.automatic_technical_relevance.status=DRY_RUN" in lines
    assert "SUMMARY pipeline_stage.automatic_technical_relevance.duration_seconds=0.000" in lines
    assert "SUMMARY technical_relevance.status=DRY_RUN" in lines
    assert "SUMMARY pipeline.total_duration_seconds=0.125" in lines
    assert lines[-1] == "SUMMARY pipeline_status=DRY_RUN"
    assert not (tmp_path / "reports").exists()


def test_pipeline_default_weekly_window_size_is_20_and_used_in_dry_run(tmp_path, capsys):
    _seed_persisted_ticker_rows(
        tmp_path / "analysis.db",
        tickers=["BBB", "AAA", "AAA"],
    )
    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path) + ["--dry-run"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert any("--weekly-window-size 20" in line for line in lines if line.startswith("PLAN "))
    assert any(
        f"--watchlist-file {orchestrator.DEFAULT_WATCHLIST_FILE}" in line
        for line in lines
        if line.startswith("PLAN ")
    )
    assert any("Automatic technical relevance" in line for line in lines)
    assert not any("--no-taxonomy-listing" in line for line in lines if line.startswith("PLAN "))
    assert lines[-1] == "SUMMARY pipeline_status=DRY_RUN"
    assert "SUMMARY technical_relevance.enabled=true" in lines
    assert "SUMMARY technical_relevance.mode=auto" in lines
    assert "SUMMARY technical_relevance.run_id=DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15" in lines
    assert "SUMMARY technical_relevance.ticker_count=2" in lines
    assert "SUMMARY technical_relevance.ticker_count_status=EXISTING_DB_SNAPSHOT" in lines
    assert "SUMMARY technical_relevance_run_id=DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15" in lines
    assert not any(line.startswith("SUMMARY technical_relevance_profile.") for line in lines)


def test_pipeline_accepts_technical_relevance_run_id_and_threads_it_to_dry_run_plans(tmp_path, capsys):
    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--dry-run", "--technical-relevance-run-id", "REL_PIPE_A"]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert any(
        line.startswith("PLAN ") and "--technical-relevance-run-id REL_PIPE_A" in line
        for line in lines
    )
    assert not any("Automatic technical relevance" in line for line in lines)
    assert "SUMMARY technical_relevance.enabled=true" in lines
    assert "SUMMARY technical_relevance.mode=existing_run" in lines
    assert "SUMMARY technical_relevance.run_id=REL_PIPE_A" in lines
    assert "SUMMARY technical_relevance.ticker_count_status=NOT_APPLICABLE_EXISTING_RUN" in lines
    assert "SUMMARY technical_relevance.status=SKIPPED_EXISTING_RUN" in lines
    assert "SUMMARY technical_relevance_run_id=REL_PIPE_A" in lines


def test_pipeline_accepts_profile_technical_relevance_in_dry_run(tmp_path, capsys):
    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--dry-run", "--profile-technical-relevance"]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert any(
        line.startswith("PLAN ") and "--profile-technical-relevance" in line
        for line in lines
    )
    assert "SUMMARY technical_relevance_profile.status=DRY_RUN" in lines


def test_pipeline_accepts_profile_ticker_swing_snapshots_in_dry_run(tmp_path, capsys):
    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--dry-run", "--profile-ticker-swing-snapshots"]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    profiled_plan_lines = [line for line in lines if line.startswith("PLAN ") and "--profile" in line]
    assert len(profiled_plan_lines) == 1
    assert "SUMMARY ticker_swing_snapshot_profile.status=DRY_RUN" in lines


def test_pipeline_accepts_no_technical_relevance_and_shows_disabled_mode_in_dry_run(tmp_path, capsys):
    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--dry-run", "--no-technical-relevance"]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert not any("Automatic technical relevance" in line for line in lines)
    assert not any(
        line.startswith("PLAN ") and "--technical-relevance-run-id" in line
        for line in lines
    )
    assert "SUMMARY technical_relevance.enabled=false" in lines
    assert "SUMMARY technical_relevance.mode=disabled" in lines
    assert "SUMMARY technical_relevance.run_id=NONE" in lines
    assert "SUMMARY technical_relevance.ticker_count_status=DISABLED" in lines
    assert "SUMMARY technical_relevance.status=DISABLED" in lines
    assert "SUMMARY pipeline_stage.automatic_technical_relevance.status=SKIPPED" in lines
    assert "SUMMARY pipeline_stage.automatic_technical_relevance.duration_seconds=0.000" in lines


def test_pipeline_dry_run_auto_reports_not_available_when_no_persisted_ticker_snapshot_exists(tmp_path, capsys):
    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path) + ["--dry-run"])

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY technical_relevance.ticker_count=0" in lines
    assert "SUMMARY technical_relevance.ticker_count_status=NOT_AVAILABLE_DRY_RUN" in lines
    assert "SUMMARY technical_relevance.status=DRY_RUN" in lines


def test_pipeline_calls_stages_in_correct_order_and_uses_index_base_date(tmp_path, monkeypatch, capsys):
    calls: list[tuple[str, list[str] | dict[str, object]]] = []
    DatabaseManager(str(tmp_path / "analysis.db")).close()

    def _make_cli(name: str):
        def _runner(argv: list[str]) -> int:
            calls.append((name, list(argv)))
            if name == "ticker" and "--profile" in argv and "--scanner-only" not in argv:
                print("SUMMARY ticker_swing_snapshot_profile.ticker_count=236")
                print("SUMMARY ticker_swing_snapshot_profile.signal_date_count=1")
                print("SUMMARY ticker_swing_snapshot_profile.total_seconds=12.345")
            return 0

        return _runner

    def _audit(**kwargs):
        calls.append(("audit", dict(kwargs)))
        return {"summary": {"validation_status": "OK"}}

    def _technical_relevance(**kwargs):
        calls.append(("techrel", dict(kwargs)))
        return {
            **_fake_technical_relevance_summary(),
            "profile_summary": {
                "technical_relevance_profile.ticker_count": 3,
                "technical_relevance_profile.observations_seen": 10,
                "technical_relevance_profile.records_written": 10,
                "technical_relevance_profile.candlestick_observation_count": 4,
                "technical_relevance_profile.divergence_observation_count": 6,
                "technical_relevance_profile.read_candlestick_observations_calls": 3,
                "technical_relevance_profile.read_divergence_observations_calls": 3,
                "technical_relevance_profile.read_dow_snapshot_calls": 10,
                "technical_relevance_profile.read_dow_events_calls": 10,
                "technical_relevance_profile.read_dow_pivots_calls": 10,
                "technical_relevance_profile.read_bar_dates_calls": 3,
                "technical_relevance_profile.build_bar_index_calls": 3,
                "technical_relevance_profile.total_seconds": "12.345",
                "technical_relevance_profile.read_observations_seconds": "1.100",
                "technical_relevance_profile.read_dow_context_seconds": "2.200",
                "technical_relevance_profile.bar_index_seconds": "3.300",
                "technical_relevance_profile.classification_seconds": "4.400",
                "technical_relevance_profile.persistence_seconds": "1.345",
                "technical_relevance_profile.tickers_with_observations": 3,
                "technical_relevance_profile.max_observations_per_ticker": 5,
                "technical_relevance_profile.avg_observations_per_ticker": "3.333",
                "technical_relevance_profile.slowest_ticker.1": "AAA|seconds=5.000|observations=5|records=5",
            },
        }

    def _daily(**kwargs):
        calls.append(("daily", dict(kwargs)))
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text("daily", encoding="utf-8")
        output_csv.write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append((f"weekly_{kwargs['window_size']}", dict(kwargs)))
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.write_text("weekly", encoding="utf-8")
        output_csv.write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _make_cli("index"))
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _make_cli("ticker"))
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _make_cli("group"))
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _make_cli("synthetic"))
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _technical_relevance)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path)
        + [
            "--expected-ticker-count",
            "236",
            "--expected-group-count",
            "54",
            "--expected-synthetic-ohlc-count",
            "53",
            "--weekly-window-size",
            "3",
            "--profile-technical-relevance",
            "--profile-ticker-swing-snapshots",
        ]
    )

    assert exit_code == 0
    assert [name for name, _ in calls] == [
        "index",
        "ticker",
        "group",
        "synthetic",
        "synthetic",
        "synthetic",
        "group",
        "group",
        "ticker",
        "audit",
        "techrel",
        "daily",
        "weekly_30",
        "weekly_5",
        "weekly_2",
    ]
    index_argv = calls[0][1]
    assert index_argv[index_argv.index("--start-date") + 1] == "2020-01-01"
    scanner_argv = calls[8][1]
    assert scanner_argv[scanner_argv.index("--taxonomy-version") + 1] == "DC_TAXONOMY_FULL_V1"
    assert "--profile" in calls[1][1]
    assert "--profile" not in scanner_argv
    audit_kwargs = calls[9][1]
    assert audit_kwargs["expected_ticker_count"] == 236
    assert audit_kwargs["expected_group_count"] == 54
    assert audit_kwargs["expected_synthetic_ohlc_count"] == 53
    assert audit_kwargs["weekly_window_size"] == 3
    techrel_kwargs = calls[10][1]
    daily_kwargs = calls[11][1]
    rolling_30_kwargs = calls[12][1]
    rolling_5_kwargs = calls[13][1]
    rolling_2_kwargs = calls[14][1]
    assert techrel_kwargs["signal_date"] == "2026-05-15"
    assert techrel_kwargs["taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
    assert techrel_kwargs["signal_version"] == orchestrator.DEFAULT_SIGNAL_VERSION
    assert techrel_kwargs["profile_technical_relevance"] is True
    assert str(daily_kwargs["watchlist_file"]) == orchestrator.DEFAULT_WATCHLIST_FILE
    assert daily_kwargs["technical_relevance_run_id"] == "AUTO_REL_RUN"
    assert rolling_30_kwargs["window_size"] == 30
    assert rolling_30_kwargs["technical_relevance_run_id"] == "AUTO_REL_RUN"
    assert rolling_5_kwargs["window_size"] == 5
    assert rolling_5_kwargs["technical_relevance_run_id"] == "AUTO_REL_RUN"
    assert rolling_2_kwargs["window_size"] == 2
    assert rolling_2_kwargs["technical_relevance_run_id"] == "AUTO_REL_RUN"
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY technical_relevance.enabled=true" in lines
    assert "SUMMARY technical_relevance.mode=auto" in lines
    assert "SUMMARY technical_relevance.run_id=AUTO_REL_RUN" in lines
    assert "SUMMARY technical_relevance.observations_seen=10" in lines
    assert "SUMMARY technical_relevance.records_written=10" in lines
    assert "SUMMARY technical_relevance.relevant_count=4" in lines
    assert "SUMMARY technical_relevance.weak_context_count=3" in lines
    assert "SUMMARY technical_relevance.noise_count=3" in lines
    assert "SUMMARY technical_relevance.unknown_signal_count=0" in lines
    assert "SUMMARY technical_relevance.missing_dow_context_count=0" in lines
    assert "SUMMARY technical_relevance.missing_bar_index_count=0" in lines
    assert "SUMMARY technical_relevance.status=OK" in lines
    assert "SUMMARY technical_relevance_profile.ticker_count=3" in lines
    assert "SUMMARY ticker_swing_snapshot_profile.ticker_count=236" in lines
    assert "SUMMARY ticker_swing_snapshot_profile.signal_date_count=1" in lines
    assert "SUMMARY ticker_swing_snapshot_profile.total_seconds=12.345" in lines
    assert "SUMMARY technical_relevance_profile.read_dow_snapshot_calls=10" in lines
    assert "SUMMARY technical_relevance_profile.classification_seconds=4.400" in lines
    assert "SUMMARY technical_relevance_profile.slowest_ticker.1=AAA|seconds=5.000|observations=5|records=5" in lines
    assert "SUMMARY audit_validation_status=OK" in lines
    total_duration_line = next(
        line for line in lines if line.startswith("SUMMARY pipeline.total_duration_seconds=")
    )
    total_duration_value = total_duration_line.split("=", 1)[1]
    assert total_duration_value.count(".") == 1
    assert len(total_duration_value.rsplit(".", 1)[1]) == 3
    assert "SUMMARY pipeline_stage.automatic_technical_relevance.status=OK" in lines
    assert "SUMMARY pipeline_stage.automatic_technical_relevance.duration_seconds=0.000" in lines
    assert any(line.startswith("SUMMARY rolling_30_report_path=") for line in lines)
    assert any(line.startswith("SUMMARY rolling_5_report_path=") for line in lines)
    assert any(line.startswith("SUMMARY rolling_2_report_path=") for line in lines)
    assert any("datacenter_rolling_30_" in line for line in lines)
    assert any("datacenter_rolling_5_" in line for line in lines)
    assert any("datacenter_rolling_2_" in line for line in lines)
    assert "SUMMARY pipeline_stage.rolling_30_report.status=OK" in lines
    assert "SUMMARY pipeline_stage.rolling_5_report.status=OK" in lines
    assert "SUMMARY pipeline_stage.rolling_2_report.status=OK" in lines
    assert "SUMMARY pipeline_stage.windows_report_copy.status=OK" in lines
    assert any(line.startswith("SUMMARY windows_report_copy.destination_dir=") for line in lines)
    assert any(line.startswith("SUMMARY windows_report_copy.copied_file_count=8") for line in lines)
    assert lines[-1] == "SUMMARY pipeline_status=OK"


def test_pipeline_threads_technical_relevance_run_id_to_daily_and_weekly_report_stages(tmp_path, monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    DatabaseManager(str(tmp_path / "analysis.db")).close()

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _fail_technical_relevance(**kwargs):
        raise AssertionError("automatic technical relevance must not run in existing-run mode")

    def _daily(**kwargs):
        calls.append(("daily", dict(kwargs)))
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily", encoding="utf-8")
        kwargs["output_csv"].write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append((f"weekly_{kwargs['window_size']}", dict(kwargs)))
        kwargs["output_md"].write_text("weekly", encoding="utf-8")
        kwargs["output_csv"].write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _fail_technical_relevance)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--technical-relevance-run-id", "REL_PIPE_B"]
    )

    assert exit_code == 0
    assert calls[0][0] == "daily"
    assert calls[0][1]["technical_relevance_run_id"] == "REL_PIPE_B"
    assert calls[1][0] == "weekly_30"
    assert calls[1][1]["technical_relevance_run_id"] == "REL_PIPE_B"
    assert calls[2][0] == "weekly_5"
    assert calls[2][1]["technical_relevance_run_id"] == "REL_PIPE_B"
    assert calls[3][0] == "weekly_2"
    assert calls[3][1]["technical_relevance_run_id"] == "REL_PIPE_B"
    assert len(calls) == 4
    assert any((tmp_path / "windows_reports").glob("datacenter_daily_2026-05-15_*_full.md"))


def test_pipeline_auto_technical_relevance_existing_run_reuse_is_reported_and_threaded(tmp_path, monkeypatch, capsys):
    calls: list[tuple[str, dict[str, object]]] = []
    DatabaseManager(str(tmp_path / "analysis.db")).close()

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _auto(**kwargs):
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
        calls.append((f"weekly_{kwargs['window_size']}", dict(kwargs)))
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

    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path))

    assert exit_code == 0
    assert all(
        call[1]["technical_relevance_run_id"] == "DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15"
        for call in calls
    )
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY technical_relevance.status=SKIPPED_EXISTING_RUN" in lines
    assert "SUMMARY technical_relevance.run_id=DATACENTER_TECH_REL_DC_TAXONOMY_FULL_V1_2026_05_15" in lines
    assert "SUMMARY technical_relevance.existing_run_reused=1" in lines
    assert lines[-1] == "SUMMARY pipeline_status=OK"


def test_pipeline_profiling_disabled_by_default_does_not_print_profile_lines_in_auto_mode(tmp_path, monkeypatch, capsys):
    DatabaseManager(str(tmp_path / "analysis.db")).close()

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _technical_relevance(**kwargs):
        return _fake_technical_relevance_summary()

    def _daily(**kwargs):
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily", encoding="utf-8")
        kwargs["output_csv"].write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    def _weekly(**kwargs):
        kwargs["output_md"].write_text("weekly", encoding="utf-8")
        kwargs["output_csv"].write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _technical_relevance)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path))

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert not any(line.startswith("SUMMARY technical_relevance_profile.") for line in lines)
    assert not any(line.startswith("SUMMARY ticker_swing_snapshot_profile.") for line in lines)


def test_pipeline_watchlist_override_is_passed_to_daily_and_weekly_report_stages(tmp_path, monkeypatch):
    calls: list[tuple[str, dict[str, object]]] = []
    DatabaseManager(str(tmp_path / "analysis.db")).close()
    watchlist_file = tmp_path / "watchlist.txt"
    watchlist_file.write_text("AAA\n", encoding="utf-8")

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _technical_relevance(**kwargs):
        return _fake_technical_relevance_summary()

    def _daily(**kwargs):
        calls.append(("daily", dict(kwargs)))
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily", encoding="utf-8")
        kwargs["output_csv"].write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append((f"weekly_{kwargs['window_size']}", dict(kwargs)))
        kwargs["output_md"].write_text("weekly", encoding="utf-8")
        kwargs["output_csv"].write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _technical_relevance)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--watchlist-file", str(watchlist_file)]
    )

    assert exit_code == 0
    assert str(calls[0][1]["watchlist_file"]) == str(watchlist_file)
    assert all(str(call[1]["watchlist_file"]) == str(watchlist_file) for call in calls)
    assert all(call[1]["technical_relevance_run_id"] == "AUTO_REL_RUN" for call in calls)


def test_pipeline_no_taxonomy_listing_flag_is_passed_to_daily_and_weekly_report_stages(tmp_path, monkeypatch, capsys):
    calls: list[tuple[str, dict[str, object]]] = []
    DatabaseManager(str(tmp_path / "analysis.db")).close()

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _technical_relevance(**kwargs):
        return _fake_technical_relevance_summary()

    def _daily(**kwargs):
        calls.append(("daily", dict(kwargs)))
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily", encoding="utf-8")
        kwargs["output_csv"].write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append((f"weekly_{kwargs['window_size']}", dict(kwargs)))
        kwargs["output_md"].write_text("weekly", encoding="utf-8")
        kwargs["output_csv"].write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(kwargs["output_md"]), "output_csv": str(kwargs["output_csv"]), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _technical_relevance)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--no-taxonomy-listing"]
    )

    assert exit_code == 0
    assert calls[0][1]["include_taxonomy_listing"] is False
    assert all(call[1]["include_taxonomy_listing"] is False for call in calls)

    dry_run_exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--dry-run", "--no-taxonomy-listing"]
    )
    assert dry_run_exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert any(
        line.startswith("PLAN ") and "--no-taxonomy-listing" in line
        for line in lines
    )


def test_pipeline_blank_technical_relevance_run_id_fails_validation(tmp_path, capsys):
    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--technical-relevance-run-id", "   "]
    )

    assert exit_code == 1
    assert "ERROR technical-relevance-run-id must be non-empty when provided" in capsys.readouterr().err


def test_pipeline_no_technical_relevance_and_existing_run_id_fails_validation(tmp_path, capsys):
    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--no-technical-relevance", "--technical-relevance-run-id", "REL_BAD"]
    )

    assert exit_code == 1
    assert "--no-technical-relevance and --technical-relevance-run-id cannot be used together" in capsys.readouterr().err


def test_pipeline_generates_reports_on_audit_warn(tmp_path, monkeypatch, capsys):
    DatabaseManager(str(tmp_path / "analysis.db")).close()

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "WARN"}}

    def _technical_relevance(**kwargs):
        return _fake_technical_relevance_summary()

    def _daily(**kwargs):
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text("daily", encoding="utf-8")
        output_csv.write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    def _weekly(**kwargs):
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.write_text("weekly", encoding="utf-8")
        output_csv.write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _technical_relevance)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path))

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY audit_validation_status=WARN" in lines
    assert any(line.startswith("SUMMARY rolling_30_report_path=") for line in lines)
    assert any(line.startswith("SUMMARY rolling_5_report_path=") for line in lines)
    assert any(line.startswith("SUMMARY rolling_2_report_path=") for line in lines)
    assert lines[-1] == "SUMMARY pipeline_status=WARN"


def test_pipeline_stops_before_reports_on_audit_fail(tmp_path, monkeypatch, capsys):
    calls: list[str] = []
    DatabaseManager(str(tmp_path / "analysis.db")).close()

    def _runner(argv: list[str]) -> int:
        calls.append("stage")
        return 0

    def _audit(**kwargs):
        calls.append("audit")
        return {"summary": {"validation_status": "FAIL"}}

    def _fail_technical_relevance(**kwargs):
        raise AssertionError("automatic technical relevance must not run after audit FAIL")

    def _fail_report(**kwargs):
        raise AssertionError("reports must not run after audit FAIL")

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _fail_technical_relevance)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _fail_report)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _fail_report)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(_base_args(tmp_path))

    assert exit_code != 0
    assert calls[-1] == "audit"
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY audit_validation_status=FAIL" in lines
    assert lines[-1] == "SUMMARY pipeline_status=FAIL"


def test_skip_audit_and_skip_reports_reduce_stage_count(tmp_path, monkeypatch, capsys):
    DatabaseManager(str(tmp_path / "analysis.db")).close()

    def _runner(argv: list[str]) -> int:
        return 0

    def _technical_relevance(**kwargs):
        return _fake_technical_relevance_summary()

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _technical_relevance)

    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--skip-audit", "--skip-reports"]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY pipeline_stage_count=10" in lines
    assert "SUMMARY audit_validation_status=SKIPPED" in lines


def test_successful_orchestrator_writes_watermarks(tmp_path, monkeypatch):
    analysis_db = tmp_path / "analysis.db"
    DatabaseManager(str(analysis_db)).close()

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _technical_relevance(**kwargs):
        return _fake_technical_relevance_summary()

    def _daily(**kwargs):
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text("daily", encoding="utf-8")
        output_csv.write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    def _weekly(**kwargs):
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.write_text("weekly", encoding="utf-8")
        output_csv.write_text("weekly", encoding="utf-8")
        return {
            "summary": {
                "output_markdown": str(output_md),
                "output_csv": str(output_csv),
                "validation_status": "OK",
                "window_start_date": "2026-05-11",
            }
        }

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _technical_relevance)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(
        [
            "--price-db",
            str(tmp_path / "osakedata.db"),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(tmp_path / "taxonomy.csv"),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--market",
            "usa",
            "--signal-date",
            "2026-05-15",
            "--start-date",
            "2026-01-01",
            "--index-base-date",
            "2020-01-01",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    rows = list_pipeline_watermarks(
        analysis_db_path=analysis_db,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )
    component_names = [row["component_name"] for row in rows]
    assert "GROUP_INDEX" in component_names
    assert "TICKER_SCANNER" in component_names
    assert "PIPELINE_AUDIT" in component_names
    assert "DAILY_REPORT" in component_names
    assert "ROLLING_REPORT_30" in component_names
    assert "ROLLING_REPORT_5" in component_names
    assert "ROLLING_REPORT_2" in component_names


def test_existing_watermark_does_not_skip_any_stage(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    DatabaseManager(str(analysis_db)).close()
    calls: list[str] = []

    def _make_runner(name: str):
        def _runner(argv: list[str]) -> int:
            calls.append(name)
            return 0

        return _runner

    def _audit(**kwargs):
        calls.append("audit")
        return {"summary": {"validation_status": "OK"}}

    def _technical_relevance(**kwargs):
        calls.append("techrel")
        return _fake_technical_relevance_summary()

    def _daily(**kwargs):
        calls.append("daily")
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text("daily", encoding="utf-8")
        output_csv.write_text("daily", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    def _weekly(**kwargs):
        calls.append(f"weekly_{kwargs['window_size']}")
        output_md = kwargs["output_md"]
        output_csv = kwargs["output_csv"]
        output_md.write_text("weekly", encoding="utf-8")
        output_csv.write_text("weekly", encoding="utf-8")
        return {"summary": {"output_markdown": str(output_md), "output_csv": str(output_csv), "validation_status": "OK"}}

    orchestrator.upsert_pipeline_watermark(
        analysis_db_path=analysis_db,
        component_name="GROUP_INDEX",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        market="usa",
        start_date="2020-01-01",
        end_date="2026-05-14",
        status="OK",
        last_successful_at_utc="2026-05-18T10:00:00Z",
    )

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _make_runner("index"))
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _make_runner("ticker"))
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _make_runner("group"))
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _make_runner("synthetic"))
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_run_automatic_technical_relevance_stage", _technical_relevance)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(
        [
            "--price-db",
            str(tmp_path / "osakedata.db"),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(tmp_path / "taxonomy.csv"),
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            "--market",
            "usa",
            "--signal-date",
            "2026-05-15",
            "--start-date",
            "2026-01-01",
            "--index-base-date",
            "2020-01-01",
            "--output-dir",
            str(tmp_path / "reports"),
        ]
    )

    assert exit_code == 0
    assert calls == [
        "index",
        "ticker",
        "group",
        "synthetic",
        "synthetic",
        "synthetic",
        "group",
        "group",
        "ticker",
        "audit",
        "techrel",
        "daily",
        "weekly_30",
        "weekly_5",
        "weekly_2",
    ]
