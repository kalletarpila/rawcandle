from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
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
