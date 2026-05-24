from __future__ import annotations

import sqlite3

from rawcandle.cli.run_scheduler_technical_relevance_smoke import main
from rawcandle.technical_signal_relevance_persistence import (
    read_relevance_records_for_run,
    read_relevance_run,
)


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_summary(output: str) -> dict[str, str]:
    summary = {}
    for line in output.splitlines():
        if not line.startswith("SUMMARY "):
            continue
        key, value = line[len("SUMMARY ") :].split("=", 1)
        summary[key] = value
    return summary


def _create_analysis_findings(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE analysis_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            pattern TEXT,
            signal_strength REAL,
            rsi14 REAL
        )
        """
    )


def _create_dow_events(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            event_date TEXT NOT NULL,
            confirmed_as_of_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            trend_state TEXT,
            active_bos_high_price REAL,
            active_bos_low_price REAL,
            structure_epoch_id INTEGER
        )
        """
    )


def _create_osakedata(db_path) -> None:
    with sqlite3.connect(db_path) as conn:
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


def _insert_osakedata_rows(db_path, rows) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.executemany(
            """
            INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()


def test_smoke_cli_resolves_conservative_end_date_and_writes_records(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    conn = _connect(analysis_db)
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    conn.executemany(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        [
            ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
            ("BBB", "2024-01-11", "Hammer", 0.7, 45.0),
        ],
    )
    conn.executemany(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            ("AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
            ("BBB", "2024-01-10", "2024-01-11", "PIVOT_LOW", "UP", 1),
        ],
    )
    conn.commit()
    conn.close()
    _create_osakedata(osakedata_db)
    _insert_osakedata_rows(
        osakedata_db,
        [
            ("AAA", "2024-01-10", 10.0, 11.0, 9.0, 10.0, 1000, "usa"),
            ("AAA", "2024-01-12", 10.0, 11.0, 9.0, 10.0, 1000, "usa"),
            ("BBB", "2024-01-11", 10.0, 11.0, 9.0, 10.0, 1000, "usa"),
            ("BBB", "2024-01-12", 10.0, 11.0, 9.0, 10.0, 1000, "usa"),
        ],
    )

    result = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--ticker",
            "BBB,AAA,AAA",
            "--created-at-utc",
            "2026-05-22T10:00:00Z",
        ]
    )

    summary = _parse_summary(capsys.readouterr().out)
    assert result == 0
    assert summary["technical_relevance.status"] == "OK"
    assert summary["technical_relevance.run_id"] == "TECH_SIGNAL_REL_DAILY_USA_2024_01_11"
    assert summary["technical_relevance.ticker_count"] == "2"
    assert summary["technical_relevance.end_date"] == "2024-01-11"
    assert summary["technical_relevance.end_date_source"] == "MIN_LATEST_OHLCV_AND_DOW"
    assert summary["technical_relevance.start_date"] == "2023-11-27"
    conn = _connect(analysis_db)
    assert read_relevance_run(conn, "TECH_SIGNAL_REL_DAILY_USA_2024_01_11") is not None
    assert [row["ticker"] for row in read_relevance_records_for_run(conn, "TECH_SIGNAL_REL_DAILY_USA_2024_01_11")] == ["AAA", "BBB"]
    conn.close()


def test_smoke_cli_explicit_end_date_and_run_id_override(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    conn = _connect(analysis_db)
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
    )
    conn.commit()
    conn.close()
    _create_osakedata(osakedata_db)
    _insert_osakedata_rows(
        osakedata_db,
        [("AAA", "2024-01-20", 10.0, 11.0, 9.0, 10.0, 1000, "usa")],
    )

    result = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--ticker",
            "AAA",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "TECHREL_SMOKE_EXPLICIT",
            "--created-at-utc",
            "2026-05-22T10:00:01Z",
        ]
    )

    summary = _parse_summary(capsys.readouterr().out)
    assert result == 0
    assert summary["technical_relevance.run_id"] == "TECHREL_SMOKE_EXPLICIT"
    assert summary["technical_relevance.end_date"] == "2024-01-31"
    assert summary["technical_relevance.end_date_source"] == "EXPLICIT"
    assert summary["technical_relevance.start_date"] == "2023-12-17"


def test_smoke_cli_duplicate_run_id_maps_to_skipped_existing_run(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    conn = _connect(analysis_db)
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    conn.execute(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-10", "PIVOT_LOW", "UP", 1),
    )
    conn.commit()
    conn.close()
    _create_osakedata(osakedata_db)
    _insert_osakedata_rows(
        osakedata_db,
        [("AAA", "2024-01-10", 10.0, 11.0, 9.0, 10.0, 1000, "usa")],
    )

    args = [
        "--analysis-db",
        str(analysis_db),
        "--market",
        "usa",
        "--ticker",
        "AAA",
        "--end-date",
        "2024-01-10",
        "--run-id",
        "TECHREL_DUPLICATE",
        "--created-at-utc",
        "2026-05-22T10:00:02Z",
    ]
    assert main(args) == 0
    result = main(args)
    summary = _parse_summary(capsys.readouterr().out)
    assert result == 0
    assert summary["technical_relevance.status"] == "SKIPPED_EXISTING_RUN"
    assert summary["technical_relevance.skip_reason"] == "RUN_ID_ALREADY_EXISTS"


def test_smoke_cli_falls_back_to_latest_ohlcv_when_dow_date_is_missing(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    conn = _connect(analysis_db)
    _create_analysis_findings(conn)
    conn.commit()
    conn.close()
    _create_osakedata(osakedata_db)
    _insert_osakedata_rows(
        osakedata_db,
        [
            ("AAA", "2024-01-10", 10.0, 11.0, 9.0, 10.0, 1000, "usa"),
            ("AAA", "2024-01-12", 10.0, 11.0, 9.0, 10.0, 1000, "usa"),
        ],
    )

    result = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--ticker",
            "AAA",
            "--created-at-utc",
            "2026-05-22T10:00:03Z",
        ]
    )

    summary = _parse_summary(capsys.readouterr().out)
    assert result == 0
    assert summary["technical_relevance.status"] == "OK"
    assert summary["technical_relevance.end_date"] == "2024-01-12"
    assert summary["technical_relevance.end_date_source"] == "LATEST_VALID_OHLCV_DATE"


def test_smoke_cli_fails_when_no_valid_ohlcv_date_exists(tmp_path, capsys):
    analysis_db = tmp_path / "analysis.db"
    osakedata_db = tmp_path / "osakedata.db"
    conn = _connect(analysis_db)
    _create_analysis_findings(conn)
    conn.commit()
    conn.close()
    _create_osakedata(osakedata_db)
    _insert_osakedata_rows(
        osakedata_db,
        [("AAA", "2024-01-10", 10.0, 11.0, 9.0, None, 1000, "usa")],
    )

    result = main(
        [
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--ticker",
            "AAA",
        ]
    )

    summary = _parse_summary(capsys.readouterr().out)
    assert result == 1
    assert summary["technical_relevance.status"] == "FAILED"
    assert summary["technical_relevance.error"] == "NO_VALID_OHLCV_DATE_FOR_MARKET"
