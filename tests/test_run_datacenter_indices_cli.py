from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from run_datacenter_indices import main as run_datacenter_indices_main


TAXONOMY_CSV = """taxonomy_version,ticker,layer,subindustry,report_group_status,is_primary,role_weight,notes
DC_TAXONOMY_V1,AAA,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,BBB,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,CCC,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,DDD,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,EEE,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,FFF,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,GGG,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,HHH,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,III,Power,UPS,CORE,1,1.0,
DC_TAXONOMY_V1,JJJ,Power,UPS,CORE,1,1.0,
"""


def _write_taxonomy_csv(tmp_path):
    path = tmp_path / "taxonomy.csv"
    path.write_text(TAXONOMY_CSV, encoding="utf-8")
    return path


def _create_ohlcv_db(path):
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
    from analysis.database_manager import DatabaseManager

    DatabaseManager(str(path)).close()


def _insert_ohlcv_rows(path, rows):
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def _build_cli_dataset_rows(*, include_spy: bool = True, include_qqq: bool = True, include_bbb: bool = True):
    rows = []
    start = date(2024, 1, 1)
    taxonomy_tickers = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF", "GGG", "HHH", "III", "JJJ"]
    for offset in range(70):
        current_date = (start + timedelta(days=offset)).isoformat()
        for idx, ticker in enumerate(taxonomy_tickers):
            if ticker == "BBB" and not include_bbb:
                continue
            close = 100.0 + (idx * 10.0) + offset
            rows.append((ticker, current_date, close, close, close, close, 1000, "usa"))
        if include_spy:
            spy_close = 300.0 + (offset * 0.25)
            rows.append(("SPY", current_date, spy_close, spy_close, spy_close, spy_close, 1000, "usa"))
        if include_qqq:
            qqq_close = 400.0 + (offset * 0.3)
            rows.append(("QQQ", current_date, qqq_close, qqq_close, qqq_close, qqq_close, 1000, "usa"))
    return rows


def test_cli_rejects_unsupported_write_mode(tmp_path, capsys):
    ohlcv_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_ohlcv_db(ohlcv_db)
    _create_analysis_db(analysis_db)

    exit_code = run_datacenter_indices_main(
        [
            "--ohlcv-db",
            str(ohlcv_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--market",
            "usa",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--write-mode",
            "upsert",
        ]
    )

    assert exit_code == 1
    assert "Unsupported write_mode" in capsys.readouterr().err


def test_cli_writes_rows_and_prints_deterministic_summary(tmp_path, capsys):
    ohlcv_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_ohlcv_db(ohlcv_db)
    _create_analysis_db(analysis_db)
    _insert_ohlcv_rows(ohlcv_db, _build_cli_dataset_rows())

    exit_code = run_datacenter_indices_main(
        [
            "--ohlcv-db",
            str(ohlcv_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--market",
            "usa",
            "--start-date",
            "2024-03-01",
            "--end-date",
            "2024-03-10",
            "--write-mode",
            "replace-range",
            "--created-at-utc",
            "2026-05-15T01:02:03Z",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "SUMMARY taxonomy_version=DC_TAXONOMY_V1"
    assert lines[4] == "SUMMARY write_mode=replace-range"
    assert lines[-1] == "SUMMARY write_status=OK"

    with sqlite3.connect(analysis_db) as conn:
        count = conn.execute("SELECT COUNT(*) FROM dc_group_index_daily").fetchone()[0]
        rs_non_null = conn.execute(
            "SELECT COUNT(*) FROM dc_group_index_daily WHERE relative_strength_spy_60d IS NOT NULL"
        ).fetchone()[0]
    assert count > 0
    assert rs_non_null > 0


def test_cli_replace_range_is_idempotent_and_respects_explicit_run_id(tmp_path):
    ohlcv_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_ohlcv_db(ohlcv_db)
    _create_analysis_db(analysis_db)
    _insert_ohlcv_rows(ohlcv_db, _build_cli_dataset_rows())

    argv = [
        "--ohlcv-db",
        str(ohlcv_db),
        "--analysis-db",
        str(analysis_db),
        "--taxonomy-csv",
        str(taxonomy_csv),
        "--taxonomy-version",
        "DC_TAXONOMY_V1",
        "--market",
        "usa",
        "--start-date",
        "2024-03-01",
        "--end-date",
        "2024-03-10",
        "--write-mode",
        "replace-range",
        "--run-id",
        "explicit_run",
        "--created-at-utc",
        "2026-05-15T01:02:03Z",
    ]
    assert run_datacenter_indices_main(argv) == 0
    assert run_datacenter_indices_main(argv) == 0

    with sqlite3.connect(analysis_db) as conn:
        total_rows = conn.execute("SELECT COUNT(*) FROM dc_group_index_daily").fetchone()[0]
        distinct_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM (
                SELECT index_date, taxonomy_version, group_type, group_name
                FROM dc_group_index_daily
                GROUP BY index_date, taxonomy_version, group_type, group_name
            )
            """
        ).fetchone()[0]
        run_ids = {
            row[0]
            for row in conn.execute("SELECT DISTINCT run_id FROM dc_group_index_daily").fetchall()
        }
    assert total_rows == distinct_rows
    assert run_ids == {"explicit_run"}


def test_cli_missing_spy_or_qqq_or_taxonomy_prices_does_not_fail(tmp_path):
    ohlcv_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    taxonomy_csv = _write_taxonomy_csv(tmp_path)
    _create_ohlcv_db(ohlcv_db)
    _create_analysis_db(analysis_db)
    _insert_ohlcv_rows(
        ohlcv_db,
        _build_cli_dataset_rows(include_spy=False, include_qqq=False, include_bbb=False),
    )

    exit_code = run_datacenter_indices_main(
        [
            "--ohlcv-db",
            str(ohlcv_db),
            "--analysis-db",
            str(analysis_db),
            "--taxonomy-csv",
            str(taxonomy_csv),
            "--taxonomy-version",
            "DC_TAXONOMY_V1",
            "--market",
            "usa",
            "--start-date",
            "2024-03-01",
            "--end-date",
            "2024-03-10",
            "--write-mode",
            "replace-range",
            "--created-at-utc",
            "2026-05-15T01:02:03Z",
        ]
    )

    assert exit_code == 0
    with sqlite3.connect(analysis_db) as conn:
        rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM dc_group_index_daily
            WHERE index_date < '2024-03-01' OR index_date > '2024-03-10'
            """
        ).fetchone()[0]
    assert rows == 0
