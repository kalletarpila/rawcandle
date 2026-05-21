"""
CLI smoke verification note for technical signal relevance.

Local manual smoke command example:

PYTHONPATH=. python3 -m rawcandle.cli.run_technical_signal_relevance \
  --analysis-db /home/kalle/projects/rawcandle/analysis.db \
  --ticker NVDA,AMD \
  --timeframe 1d \
  --start-date 2026-05-01 \
  --end-date 2026-05-21 \
  --run-id TECH_SIGNAL_REL_SMOKE_2026_05_21 \
  --created-at-utc 2026-05-21T00:00:00Z

Deterministic SQL verification queries:

SELECT * FROM technical_signal_relevance_runs WHERE run_id = '<RUN_ID>';

SELECT relevance_class, COUNT(*)
FROM technical_signal_relevance
WHERE run_id = '<RUN_ID>'
GROUP BY relevance_class
ORDER BY relevance_class;

SELECT relevance_reason, COUNT(*)
FROM technical_signal_relevance
WHERE run_id = '<RUN_ID>'
GROUP BY relevance_reason
ORDER BY relevance_reason;

SELECT ticker, timeframe, signal_date, signal_name, relevance_class, relevance_reason
FROM technical_signal_relevance
WHERE run_id = '<RUN_ID>'
ORDER BY ticker, timeframe, signal_date, signal_name
LIMIT 50;
"""

import sqlite3

from rawcandle.cli.run_technical_signal_relevance import main
from rawcandle.technical_signal_relevance_persistence import (
    read_relevance_records_for_run,
    read_relevance_run,
)


def _connect(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


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


def _create_divergence_data(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE divergence_data (
            ticker TEXT,
            date TEXT,
            bullish_strength REAL DEFAULT 0,
            bearish_strength REAL DEFAULT 0,
            hidden_bullish_strength REAL DEFAULT 0,
            hidden_bearish_strength REAL DEFAULT 0,
            rsi REAL,
            is_hidden_bullish_divergence_r3 INTEGER DEFAULT 0,
            is_hidden_bearish_divergence_r3 INTEGER DEFAULT 0
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


def _db_path(tmp_path):
    return tmp_path / "analysis_cli.db"


def _parse_summary(output: str) -> dict[str, str]:
    summary = {}
    for line in output.splitlines():
        if not line.startswith("SUMMARY "):
            continue
        key, value = line[len("SUMMARY ") :].split("=", 1)
        summary[key] = value
    return summary


def test_cli_runs_successfully_for_one_ticker_with_one_candlestick_observation(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
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

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            "AAA",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "RUN_CLI_001",
            "--created-at-utc",
            "2026-05-21T14:00:00Z",
        ]
    )

    captured = capsys.readouterr().out
    assert result == 0
    assert "SUMMARY technical_signal_relevance.status=OK" in captured
    conn = _connect(db_path)
    assert read_relevance_run(conn, "RUN_CLI_001") is not None
    records = read_relevance_records_for_run(conn, "RUN_CLI_001")
    assert len(records) == 1
    assert records[0]["signal_name"] == "Hammer"
    conn.close()


def test_cli_runs_successfully_for_one_ticker_with_one_divergence_observation(tmp_path):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _create_divergence_data(conn)
    _create_dow_events(conn)
    conn.execute(
        "INSERT INTO divergence_data (ticker, date, bullish_strength, bearish_strength, rsi) VALUES (?, ?, ?, ?, ?)",
        ("AAA", "2024-01-10", 1.0, 0.0, 30.0),
    )
    conn.execute(
        """
        INSERT INTO stock_dow_structure_events (
            ticker, event_date, confirmed_as_of_date, event_type, trend_state, structure_epoch_id
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        ("AAA", "2024-01-09", "2024-01-10", "BOS_UP", "UP", 1),
    )
    conn.commit()
    conn.close()

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            "AAA",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "RUN_CLI_002",
            "--created-at-utc",
            "2026-05-21T14:00:01Z",
        ]
    )

    assert result == 0
    conn = _connect(db_path)
    records = read_relevance_records_for_run(conn, "RUN_CLI_002")
    assert len(records) == 1
    assert records[0]["signal_name"] == "Bullish Divergence"
    conn.close()


def test_cli_prints_all_required_summary_lines(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _create_analysis_findings(conn)
    conn.commit()
    conn.close()

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            "AAA",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "RUN_CLI_003",
            "--created-at-utc",
            "2026-05-21T14:00:02Z",
        ]
    )

    output_lines = set(capsys.readouterr().out.strip().splitlines())
    assert result == 0
    assert "SUMMARY technical_signal_relevance.run_id=RUN_CLI_003" in output_lines
    assert "SUMMARY technical_signal_relevance.timeframe=1d" in output_lines
    assert "SUMMARY technical_signal_relevance.start_date=2024-01-01" in output_lines
    assert "SUMMARY technical_signal_relevance.end_date=2024-01-31" in output_lines
    assert "SUMMARY technical_signal_relevance.ticker_count=1" in output_lines
    assert "SUMMARY technical_signal_relevance.observations_seen=0" in output_lines
    assert "SUMMARY technical_signal_relevance.records_written=0" in output_lines
    assert "SUMMARY technical_signal_relevance.relevant_count=0" in output_lines
    assert "SUMMARY technical_signal_relevance.weak_context_count=0" in output_lines
    assert "SUMMARY technical_signal_relevance.noise_count=0" in output_lines
    assert "SUMMARY technical_signal_relevance.unknown_signal_count=0" in output_lines
    assert "SUMMARY technical_signal_relevance.missing_dow_context_count=0" in output_lines
    assert "SUMMARY technical_signal_relevance.missing_bar_index_count=0" in output_lines
    assert "SUMMARY technical_signal_relevance.status=OK" in output_lines


def test_cli_supports_comma_separated_tickers(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
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

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            "BBB,AAA,AAA",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "RUN_CLI_004",
            "--created-at-utc",
            "2026-05-21T14:00:03Z",
        ]
    )

    output = capsys.readouterr().out
    assert result == 0
    assert "SUMMARY technical_signal_relevance.ticker_count=2" in output
    conn = _connect(db_path)
    records = read_relevance_records_for_run(conn, "RUN_CLI_004")
    assert [row["ticker"] for row in records] == ["AAA", "BBB"]
    conn.close()


def test_cli_succeeds_with_no_observations_and_writes_one_run_row_plus_zero_relevance_rows(
    tmp_path,
):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _create_analysis_findings(conn)
    conn.commit()
    conn.close()

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            "AAA",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "RUN_CLI_005",
            "--created-at-utc",
            "2026-05-21T14:00:04Z",
        ]
    )

    assert result == 0
    conn = _connect(db_path)
    assert read_relevance_run(conn, "RUN_CLI_005") is not None
    assert read_relevance_records_for_run(conn, "RUN_CLI_005") == []
    conn.close()


def test_cli_fails_on_duplicate_run_id(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _create_analysis_findings(conn)
    conn.commit()
    conn.close()

    args = [
        "--analysis-db",
        str(db_path),
        "--ticker",
        "AAA",
        "--start-date",
        "2024-01-01",
        "--end-date",
        "2024-01-31",
        "--run-id",
        "RUN_CLI_006",
        "--created-at-utc",
        "2026-05-21T14:00:05Z",
    ]
    assert main(args) == 0
    assert main(args) == 1
    assert "SUMMARY technical_signal_relevance.status=FAILED" in capsys.readouterr().out


def test_cli_validates_start_date_less_than_or_equal_to_end_date(tmp_path, capsys):
    db_path = _db_path(tmp_path)

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            "AAA",
            "--start-date",
            "2024-02-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "RUN_CLI_007",
        ]
    )

    assert result == 1
    assert "SUMMARY technical_signal_relevance.status=FAILED" in capsys.readouterr().out


def test_cli_validates_non_empty_run_id(tmp_path, capsys):
    db_path = _db_path(tmp_path)

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            "AAA",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "   ",
        ]
    )

    assert result == 1
    assert "SUMMARY technical_signal_relevance.status=FAILED" in capsys.readouterr().out


def test_cli_validates_non_empty_ticker_list(tmp_path, capsys):
    db_path = _db_path(tmp_path)

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            " ,  , ",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "RUN_CLI_008",
        ]
    )

    assert result == 1
    assert "SUMMARY technical_signal_relevance.status=FAILED" in capsys.readouterr().out


def test_cli_fails_on_duplicate_relevance_primary_key(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    conn.executemany(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        [
            ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
            ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
        ],
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

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            "AAA",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "RUN_CLI_009",
            "--created-at-utc",
            "2026-05-21T14:00:06Z",
        ]
    )

    assert result == 1
    assert "SUMMARY technical_signal_relevance.status=FAILED" in capsys.readouterr().out


def test_cli_summary_counts_match_written_rows_via_sql_queries(tmp_path, capsys):
    db_path = _db_path(tmp_path)
    conn = _connect(db_path)
    _create_analysis_findings(conn)
    _create_dow_events(conn)
    conn.executemany(
        "INSERT INTO analysis_findings (ticker, date, pattern, signal_strength, rsi14) VALUES (?, ?, ?, ?, ?)",
        [
            ("AAA", "2024-01-10", "Hammer", 0.8, 50.0),
            ("BBB", "2024-01-11", "Hammer", 0.8, 50.0),
            ("CCC", "2024-01-12", "Bearish Flag", 0.8, 50.0),
            ("DDD", "2024-01-13", "not_a_real_pattern", 0.8, 50.0),
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
            ("CCC", "2024-01-11", "2024-01-12", "PIVOT_LOW", "UP", 1),
        ],
    )
    conn.commit()
    conn.close()

    result = main(
        [
            "--analysis-db",
            str(db_path),
            "--ticker",
            "AAA,BBB,CCC,DDD",
            "--start-date",
            "2024-01-01",
            "--end-date",
            "2024-01-31",
            "--run-id",
            "RUN_CLI_010",
            "--created-at-utc",
            "2026-05-21T14:00:07Z",
        ]
    )

    output = capsys.readouterr().out
    summary = _parse_summary(output)
    assert result == 0

    conn = _connect(db_path)
    run_count = conn.execute(
        "SELECT COUNT(*) FROM technical_signal_relevance_runs WHERE run_id = ?",
        ("RUN_CLI_010",),
    ).fetchone()[0]
    assert run_count == 1

    run_row = conn.execute(
        "SELECT * FROM technical_signal_relevance_runs WHERE run_id = ?",
        ("RUN_CLI_010",),
    ).fetchone()
    assert run_row is not None
    assert run_row["config_snapshot_json"]

    result_columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(technical_signal_relevance)").fetchall()
    }
    assert "config_snapshot_json" not in result_columns

    written_count = conn.execute(
        "SELECT COUNT(*) FROM technical_signal_relevance WHERE run_id = ?",
        ("RUN_CLI_010",),
    ).fetchone()[0]
    assert written_count == 3
    assert int(summary["technical_signal_relevance.records_written"]) == written_count
    assert int(summary["technical_signal_relevance.observations_seen"]) == written_count

    class_counts = {
        row[0]: row[1]
        for row in conn.execute(
            """
            SELECT relevance_class, COUNT(*)
            FROM technical_signal_relevance
            WHERE run_id = ?
            GROUP BY relevance_class
            ORDER BY relevance_class
            """,
            ("RUN_CLI_010",),
        ).fetchall()
    }
    assert int(summary["technical_signal_relevance.relevant_count"]) == class_counts.get(
        "RELEVANT", 0
    )
    assert int(summary["technical_signal_relevance.weak_context_count"]) == class_counts.get(
        "WEAK_CONTEXT", 0
    )
    assert int(summary["technical_signal_relevance.noise_count"]) == class_counts.get(
        "NOISE", 0
    )

    unknown_signal_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM technical_signal_relevance
        WHERE run_id = ? AND relevance_reason = 'UNKNOWN_SIGNAL_NAME'
        """,
        ("RUN_CLI_010",),
    ).fetchone()[0]
    assert int(summary["technical_signal_relevance.unknown_signal_count"]) == unknown_signal_count

    missing_dow_context_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM technical_signal_relevance
        WHERE run_id = ? AND rule_trace LIKE '%missing_dow_context=true%'
        """,
        ("RUN_CLI_010",),
    ).fetchone()[0]
    assert int(summary["technical_signal_relevance.missing_dow_context_count"]) == (
        missing_dow_context_count
    )

    missing_bar_index_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM technical_signal_relevance
        WHERE run_id = ? AND rule_trace LIKE '%missing_bar_index=true%'
        """,
        ("RUN_CLI_010",),
    ).fetchone()[0]
    assert int(summary["technical_signal_relevance.missing_bar_index_count"]) == (
        missing_bar_index_count
    )
    conn.close()
