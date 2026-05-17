from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_group_persistence import (
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
