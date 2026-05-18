from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from run_datacenter_swing_pipeline_audit import main as run_datacenter_swing_pipeline_audit_main


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def _seed_ok_fixture(path):
    with sqlite3.connect(path) as conn:
        for signal_date in ("2026-05-11", "2026-05-12", "2026-05-13", "2026-05-14", "2026-05-15"):
            conn.execute(
                """
                INSERT INTO dc_ticker_swing_signal_daily (
                    signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                    latest_structure_label, latest_structure_freshness, ticker_trend_state,
                    breakout_signal, fast_ema10_pullback_signal, conservative_ema20_pullback_signal,
                    pullback_signal, exit_risk_signal, exit_reason, exit_risk_severity,
                    price_data_status, signal_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_date, "DC_TAXONOMY_FULL_V1", "AAA", "LayerA", "SubA",
                    "HH", "FRESH", "UP",
                    0, 0, 0, 0, 0, None, None,
                    "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-18T10:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO dc_group_swing_signal_daily (
                    signal_date, taxonomy_version, group_type, group_name,
                    return_5d, return_10d, return_20d, return_60d, pct_above_ema20,
                    ema20_breadth_delta_5d, overheat_risk_level, timing_state, data_quality_status,
                    signal_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_date, "DC_TAXONOMY_FULL_V1", "subindustry", "SubA",
                    0.01, 0.02, 0.03, 0.04, 60.0,
                    5.0, "LOW", "BUY_ZONE", "OK",
                    "DC_SWING_SIGNAL_V1", "seed", "2026-05-18T10:00:00Z",
                ),
            )
            conn.execute(
                """
                INSERT INTO dc_group_synthetic_ohlc_daily (
                    ohlc_date, taxonomy_version, group_type, group_name,
                    synthetic_close, ema20, relative_close_20, latest_structure_label,
                    latest_structure_age_trading_days, latest_structure_freshness,
                    trend_classification, data_quality_status, calc_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    signal_date, "DC_TAXONOMY_FULL_V1", "subindustry", "SubA",
                    100.0, 98.0, 1.02, "HH", 0, "FRESH",
                    "UP", "OK", "DC_SWING_OHLC_V1", "seed", "2026-05-18T10:00:00Z",
                ),
            )
        conn.commit()


def test_cli_prints_deterministic_summary_lines(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _seed_ok_fixture(analysis_db)

    exit_code = run_datacenter_swing_pipeline_audit_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            "2026-05-15",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY signal_date=2026-05-15"
    assert lines[1] == "SUMMARY taxonomy_version=DC_TAXONOMY_FULL_V1"
    assert lines[2] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[-1] == "SUMMARY validation_status=OK"


def test_cli_exit_code_is_nonzero_on_fail(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    with sqlite3.connect(analysis_db) as conn:
        conn.execute("CREATE TABLE dc_ticker_swing_signal_daily (signal_date TEXT)")
        conn.commit()

    exit_code = run_datacenter_swing_pipeline_audit_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            "2026-05-15",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
        ]
    )

    assert exit_code != 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY validation_status=FAIL" in lines
