from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_group_persistence import (
    persist_datacenter_group_overheat_risk,
    persist_datacenter_group_swing_signals,
)
from run_datacenter_group_swing_signals import main as run_datacenter_group_swing_signals_main


def _write_taxonomy_csv(tmp_path):
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
""",
        encoding="utf-8",
    )
    return path


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()
    with sqlite3.connect(path) as conn:
        for ticker in ["AAA", "BBB", "CCC"]:
            conn.execute(
                """
                INSERT INTO dc_ticker_swing_signal_daily (
                    signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                    above_ma10, above_ema20, ema20_slope_positive, latest_structure_label,
                    price_data_status, signal_version, run_id, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("2024-01-10", "DC_TAXONOMY_V1", ticker, "Power", "UPS", 1, 1, 1, "HH", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
            )
        conn.commit()


def test_cli_writes_rows_and_prints_deterministic_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_analysis_db(analysis_db)

    exit_code = run_datacenter_group_swing_signals_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--signal-date",
            "2024-01-10",
            "--write-mode",
            "upsert",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY signal_date=2024-01-10"
    assert lines[1] == "SUMMARY write_mode=upsert"
    assert lines[2] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dc_group_swing_signal_daily").fetchone()[0]
    assert count == 3


def test_cli_timing_only_updates_existing_rows_and_prints_deterministic_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_analysis_db(analysis_db)

    for ticker in ["AAA", "BBB", "CCC"]:
        with sqlite3.connect(analysis_db) as conn:
            conn.execute(
                """
                UPDATE dc_ticker_swing_signal_daily
                SET above_ma10 = 1, above_ema20 = 1, ema20_slope_positive = 1, latest_structure_label = 'HH', price_data_status = 'OK'
                WHERE ticker = ?
                """,
                (ticker,),
            )
            conn.commit()

    persist_datacenter_group_swing_signals(
        analysis_db_path=analysis_db,
        taxonomy_csv_path=taxonomy_csv,
        signal_date="2024-01-10",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="base-run",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_group_swing_signal_daily
            SET return_5d = 0.02,
                return_10d = 0.03,
                return_20d = 0.10,
                return_60d = 0.20,
                pct_above_ma10 = 82.0,
                pct_above_ema20 = 85.0,
                ema20_breadth_delta_5d = 0.0,
                data_quality_status = 'OK'
            """
        )
        conn.commit()

    exit_code = run_datacenter_group_swing_signals_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            "2024-01-10",
            "--write-mode",
            "update-existing",
            "--timing-only",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY start_date=2024-01-10"
    assert lines[1] == "SUMMARY end_date=2024-01-10"
    assert lines[2] == "SUMMARY write_mode=update-existing"
    assert lines[3] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_group_swing_signal_daily
            WHERE timing_state = 'BUY_ZONE'
            """
        ).fetchone()[0]
    assert count == 3


def test_cli_overheat_only_updates_existing_rows_and_prints_deterministic_summary(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)

    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            INSERT INTO dc_group_swing_signal_daily (
                signal_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, return_5d, return_10d, return_20d, return_60d,
                pct_above_ma10, pct_above_ema20, pct_above_rising_ema20,
                ma10_breadth_delta_5d, ema20_breadth_delta_5d,
                trend_breadth, weakness_breadth, overheat_risk_level,
                timing_state, timing_reason, data_quality_status,
                signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2024-01-10", "DC_TAXONOMY_V1", "layer", "Power",
                5, 5, 0.02, 0.03, 0.10, 0.20,
                82.0, 85.0, None,
                -11.0, -11.0,
                30.0, 20.0, None,
                "BUY_ZONE", "BUY_ZONE:existing", "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        )
        conn.execute(
            """
            INSERT INTO dc_group_index_daily (
                index_date, taxonomy_version, group_type, group_name,
                member_count, eligible_count, ma50_eligible_count, ma200_eligible_count,
                daily_return_equal, median_return, pct_positive, pct_above_ma50, pct_above_ma200,
                index_level_equal, return_20d, return_60d, return_120d,
                volatility_20d, volatility_60d, relative_strength_spy_60d, relative_strength_qqq_60d,
                data_quality_status, calc_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2024-01-10", "DC_TAXONOMY_V1", "layer", "Power",
                5, 5, 0, 0, 0.0, 0.0, 0.0, None, 85.0,
                100.0, None, None, None,
                None, None, None, None,
                "OK", "DC_INDEX_CALC_V1", "seed", "2026-05-17T09:00:00Z",
            ),
        )
        conn.commit()

    exit_code = run_datacenter_group_swing_signals_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--signal-date",
            "2024-01-10",
            "--write-mode",
            "update-existing",
            "--overheat-only",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY start_date=2024-01-10"
    assert lines[1] == "SUMMARY end_date=2024-01-10"
    assert lines[2] == "SUMMARY write_mode=update-existing"
    assert lines[3] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        level = conn.execute(
            """
            SELECT overheat_risk_level
            FROM dc_group_swing_signal_daily
            WHERE signal_date = '2024-01-10'
              AND group_type = 'layer'
              AND group_name = 'Power'
            """
        ).fetchone()[0]
    assert level == "HIGH"
