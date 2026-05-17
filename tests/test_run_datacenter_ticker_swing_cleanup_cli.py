from __future__ import annotations

import sqlite3

from analysis.database_manager import DatabaseManager
from run_datacenter_ticker_swing_cleanup import main as run_datacenter_ticker_swing_cleanup_main


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
        conn.commit()


def _create_analysis_db(path):
    DatabaseManager(str(path)).close()


def test_cleanup_cli_dry_run_prints_deterministic_summary_without_deleting(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    with sqlite3.connect(price_db) as conn:
        conn.execute(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("AAA", "2024-01-12", 100, 101, 99, 100, 1000, "usa"),
        )
        conn.commit()
    with sqlite3.connect(analysis_db) as conn:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2024-01-12", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
                ("2024-01-13", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "MISSING_AS_OF_DATE", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
            ],
        )
        conn.commit()

    exit_code = run_datacenter_ticker_swing_cleanup_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--start-date",
            "2024-01-12",
            "--end-date",
            "2024-01-13",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--market",
            "usa",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY start_date=2024-01-12"
    assert lines[1] == "SUMMARY end_date=2024-01-13"
    assert lines[2] == "SUMMARY taxonomy_version=DC_TAXONOMY_V1"
    assert lines[3] == "SUMMARY signal_version=DC_SWING_SIGNAL_V1"
    assert "SUMMARY existing_signal_dates=2" in lines
    assert "SUMMARY valid_trading_dates=1" in lines
    assert "SUMMARY non_trading_signal_dates=1" in lines
    assert "SUMMARY candidate_rows=1" in lines
    assert "SUMMARY deleted_rows=0" in lines
    assert "SUMMARY dry_run=1" in lines
    assert "SUMMARY non_trading_dates=2024-01-13" in lines
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dc_ticker_swing_signal_daily").fetchone()[0]
    assert count == 2


def test_cleanup_cli_apply_deletes_only_candidate_rows(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)
    with sqlite3.connect(price_db) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2024-01-12", 100, 101, 99, 100, 1000, "usa"),
                ("AAA", "2024-01-15", 101, 102, 100, 101, 1000, "usa"),
            ],
        )
        conn.commit()
    with sqlite3.connect(analysis_db) as conn:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, primary_layer, primary_subindustry,
                price_data_status, signal_version, run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("2024-01-12", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
                ("2024-01-13", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "MISSING_AS_OF_DATE", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
                ("2024-01-15", "DC_TAXONOMY_V1", "AAA", "Power", "UPS", "OK", "DC_SWING_SIGNAL_V1", "seed", "2026-05-17T10:00:00Z"),
            ],
        )
        conn.commit()

    exit_code = run_datacenter_ticker_swing_cleanup_main(
        [
            "--analysis-db",
            str(analysis_db),
            "--price-db",
            str(price_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--start-date",
            "2024-01-12",
            "--end-date",
            "2024-01-15",
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--market",
            "usa",
            "--apply",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "SUMMARY candidate_rows=1" in lines
    assert "SUMMARY deleted_rows=1" in lines
    assert "SUMMARY dry_run=0" in lines

    with sqlite3.connect(analysis_db) as conn:
        dates = [
            row[0]
            for row in conn.execute(
                "SELECT signal_date FROM dc_ticker_swing_signal_daily ORDER BY signal_date"
            ).fetchall()
        ]
    assert dates == ["2024-01-12", "2024-01-15"]
