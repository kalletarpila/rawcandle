from __future__ import annotations

import sqlite3

from run_datacenter_group_synthetic_ohlc import main as run_datacenter_group_synthetic_ohlc_main


def _write_taxonomy_csv(tmp_path):
    path = tmp_path / "taxonomy.csv"
    path.write_text(
        """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Cooling,Chillers,CORE,1,1.0,
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
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("AAA", "2024-01-01", 100, 101, 99, 100, 1000, "usa"),
                ("AAA", "2024-01-02", 101, 102, 100, 101, 1100, "usa"),
                ("BBB", "2024-01-01", 200, 202, 198, 200, 900, "usa"),
                ("BBB", "2024-01-02", 202, 204, 201, 203, 950, "usa"),
                ("CCC", "2024-01-01", 300, 303, 297, 300, 800, "usa"),
                ("CCC", "2024-01-02", 303, 306, 300, 304, 850, "usa"),
            ],
        )
        conn.commit()


def test_cli_writes_rows_and_prints_deterministic_summary(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_price_db(price_db)

    exit_code = run_datacenter_group_synthetic_ohlc_main(
        [
            "--price-db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-02",
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
    assert lines[0] == "SUMMARY start_date=2024-01-01"
    assert lines[1] == "SUMMARY end_date=2024-01-02"
    assert lines[2] == "SUMMARY market=usa"
    assert lines[-1] == "SUMMARY validation_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dc_group_synthetic_ohlc_daily").fetchone()[0]
    assert count == 8
