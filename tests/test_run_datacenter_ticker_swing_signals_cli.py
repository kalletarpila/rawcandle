from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from analysis.datacenter_indices.swing_ticker_persistence import (
    persist_datacenter_ticker_swing_snapshots,
)
from run_datacenter_ticker_swing_signals import main as run_datacenter_ticker_swing_signals_main


def _write_taxonomy_csv(tmp_path):
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
""",
        encoding="utf-8",
    )
    return path


def _create_price_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT,
                pvm TEXT,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2024-01-10", 100, 101, 99, 100, 1000, "usa"),
        )
        conn.commit()


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE stock_dow_structure_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                market TEXT NULL,
                event_date TEXT NOT NULL,
                confirmed_as_of_date TEXT NOT NULL,
                event_type TEXT NOT NULL,
                dow_label_high TEXT NULL,
                dow_label_low TEXT NULL,
                trend_state TEXT NULL
            )
            """
        )
        conn.commit()


def test_cli_writes_rows_and_prints_deterministic_summary(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--price-db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--as-of-date",
            "2024-01-10",
            "--market",
            "usa",
            "--write-mode",
            "upsert",
            "--created-at-utc",
            "2026-05-17T12:00:00Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY signal_date=2024-01-10"
    assert lines[1] == "SUMMARY market=usa"
    assert lines[2] == "SUMMARY write_mode=upsert"
    assert lines[3] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dc_ticker_swing_signal_daily").fetchone()[0]
    assert count == 1


def test_cli_scanner_only_updates_existing_rows_and_prints_deterministic_summary(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    persist_datacenter_ticker_swing_snapshots(
        analysis_db_path=analysis_db,
        price_db_path=price_db,
        taxonomy_csv_path=taxonomy_csv,
        as_of_date="2024-01-10",
        market="usa",
        signal_version="DC_SWING_SIGNAL_V1",
        run_id="base-run",
        created_at_utc="2026-05-17T11:00:00Z",
        write_mode="upsert",
    )
    with sqlite3.connect(analysis_db) as conn:
        conn.execute(
            """
            UPDATE dc_ticker_swing_signal_daily
            SET close = 120.0,
                return_5d = 0.02,
                return_10d = 0.03,
                return_20d = 0.10,
                return_60d = 0.20,
                ema10 = 119.0,
                ema20 = 115.0,
                ma10 = 118.0,
                highest_close_20d = 120.0,
                volume_vs_avg20 = 1.6,
                ema10_slope_positive = 1,
                ema20_slope_positive = 1,
                latest_structure_label = 'HH',
                price_data_status = 'OK'
            """
        )
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
                "2024-01-10", "DC_TAXONOMY_V1", "subindustry", "UPS",
                1, 1, 0.02, 0.03, 0.10, 0.20,
                80.0, 85.0, None, 0.0, 0.0, 60.0, 20.0, None,
                "BUY_ZONE", "BUY_ZONE:existing", "OK",
                "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z",
            ),
        )
        conn.commit()

    exit_code = run_datacenter_ticker_swing_signals_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--as-of-date",
            "2024-01-10",
            "--write-mode",
            "update-existing",
            "--scanner-only",
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
        breakout_signal = conn.execute(
            """
            SELECT breakout_signal
            FROM dc_ticker_swing_signal_daily
            WHERE ticker = 'AAA'
              AND signal_date = '2024-01-10'
            """
        ).fetchone()[0]
    assert breakout_signal == 1
