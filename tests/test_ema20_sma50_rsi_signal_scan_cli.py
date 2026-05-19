from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from rawcandle.cli.run_ema20_sma50_rsi_signal_scan import main as signal_scan_main


def _create_price_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT NOT NULL,
                pvm TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                market TEXT NOT NULL,
                PRIMARY KEY (osake, pvm)
            )
            """
        )
        conn.commit()


def _create_analysis_db(path):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE divergence_data (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                bullish_strength REAL DEFAULT 0,
                bearish_strength REAL DEFAULT 0,
                hidden_bullish_strength REAL DEFAULT 0,
                hidden_bearish_strength REAL DEFAULT 0,
                rsi REAL
            )
            """
        )
        conn.commit()


def _insert_price_series(path, ticker, market, closes, start_date="2024-01-01"):
    start = date.fromisoformat(start_date)
    with sqlite3.connect(path) as conn:
        for idx, close in enumerate(closes):
            current_date = (start + timedelta(days=idx)).isoformat()
            conn.execute(
                """
                INSERT INTO osakedata (osake, pvm, open, high, low, close, volume, market)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ticker, current_date, close, close, close, close, 1000, market),
            )
        conn.commit()


def _insert_rsi(path, ticker, row_date, rsi):
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO divergence_data (
                ticker, date, bullish_strength, bearish_strength,
                hidden_bullish_strength, hidden_bearish_strength, rsi
            )
            VALUES (?, ?, 0, 0, 0, 0, ?)
            """,
            (ticker, row_date, rsi),
        )
        conn.commit()


def _base_cross_series():
    return [100.0] * 60 + [101.0, 102.0, 103.0, 104.0, 105.0]


def _downward_cross_series():
    return [100.0] * 60 + [99.0, 98.0, 97.0, 96.0, 95.0]


def _already_above_series():
    return [100.0] * 50 + [101.0] * 15


def _base_cross_series_with_forward_prices():
    return _base_cross_series() + [110.0, 90.0, 110.0, 95.0]


def _single_signal_with_no_future_series():
    return [100.0] * 60 + [101.0]


def _single_signal_with_immediate_forward_prices():
    return [100.0] * 60 + [101.0, 110.0, 90.0, 110.0, 95.0]


def test_cli_csv_output_detects_expected_rows_and_limit_ordering(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    _insert_price_series(price_db, "AAA", "usa", _base_cross_series())
    _insert_price_series(price_db, "AAB", "usa", _base_cross_series())
    _insert_price_series(price_db, "BBB", "usa", _base_cross_series())
    _insert_price_series(price_db, "CCC", "usa", _downward_cross_series())
    _insert_price_series(price_db, "DDD", "usa", _already_above_series())
    _insert_price_series(price_db, "FIN", "omxh", _base_cross_series())

    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)
    _insert_rsi(analysis_db, "AAB", "2024-03-01", 65.0)
    _insert_rsi(analysis_db, "BBB", "2024-03-01", 50.0)
    _insert_rsi(analysis_db, "CCC", "2024-03-01", 70.0)
    _insert_rsi(analysis_db, "DDD", "2024-03-01", 75.0)
    _insert_rsi(analysis_db, "FIN", "2024-03-01", 80.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-02-28",
            "--end-date",
            "2024-03-05",
            "--limit",
            "1",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "ticker;date;ema20;sma50;rsi"
    assert lines[1] == "AAA;2024-03-01;100.0952;100.0200;55.0000"
    assert "AAB;2024-03-01;100.0952;100.0200;65.0000" not in lines
    assert "BBB;2024-03-01;100.0952;100.0200;50.0000" not in lines
    assert "DDD;2024-03-01;100.5238;100.3000;75.0000" not in lines
    assert "FIN;2024-03-01;100.0952;100.0200;80.0000" not in lines
    assert lines[-7:] == [
        "SUMMARY market=usa",
        "SUMMARY start_date=2024-02-28",
        "SUMMARY end_date=2024-03-05",
        "SUMMARY min_rsi=50.0000",
        "SUMMARY limit=1",
        "SUMMARY candidates=2",
        "SUMMARY returned=1",
    ]


def test_cli_summary_output_prints_only_summary_lines_and_respects_date_filter(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    _insert_price_series(price_db, "AAA", "usa", _base_cross_series())
    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-03-02",
            "--end-date",
            "2024-03-05",
            "--output-format",
            "summary",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert all(line.startswith("SUMMARY ") for line in lines)
    assert lines == [
        "SUMMARY market=usa",
        "SUMMARY start_date=2024-03-02",
        "SUMMARY end_date=2024-03-05",
        "SUMMARY min_rsi=50.0000",
        "SUMMARY limit=100",
        "SUMMARY candidates=0",
        "SUMMARY returned=0",
    ]


def test_cli_end_date_filter_excludes_cross_after_selected_range(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    _insert_price_series(price_db, "AAA", "usa", _base_cross_series())
    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-02-28",
            "--end-date",
            "2024-02-29",
            "--output-format",
            "summary",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines == [
        "SUMMARY market=usa",
        "SUMMARY start_date=2024-02-28",
        "SUMMARY end_date=2024-02-29",
        "SUMMARY min_rsi=50.0000",
        "SUMMARY limit=100",
        "SUMMARY candidates=0",
        "SUMMARY returned=0",
    ]


def test_cli_no_lookahead_requires_history_before_start_date(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    full_series = _base_cross_series()
    truncated_series = full_series[-15:]
    _insert_price_series(price_db, "AAA", "usa", full_series)
    _insert_price_series(price_db, "ZZZ", "usa", truncated_series, start_date="2024-02-16")
    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)
    _insert_rsi(analysis_db, "ZZZ", "2024-03-01", 60.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-03-01",
            "--end-date",
            "2024-03-01",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert "AAA;2024-03-01;100.0952;100.0200;55.0000" in lines
    assert not any(line.startswith("ZZZ;2024-03-01;") for line in lines)
    assert "SUMMARY candidates=1" in lines


def test_cli_respects_min_rsi_strictly_above_threshold(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    _insert_price_series(price_db, "AAA", "usa", _base_cross_series())
    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-02-28",
            "--end-date",
            "2024-03-05",
            "--min-rsi",
            "55",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "ticker;date;ema20;sma50;rsi"
    assert lines[1:] == [
        "SUMMARY market=usa",
        "SUMMARY start_date=2024-02-28",
        "SUMMARY end_date=2024-03-05",
        "SUMMARY min_rsi=55.0000",
        "SUMMARY limit=100",
        "SUMMARY candidates=0",
        "SUMMARY returned=0",
    ]


def test_cli_forward_returns_default_output_stays_unchanged(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    _insert_price_series(price_db, "AAA", "usa", _single_signal_with_immediate_forward_prices())
    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-02-28",
            "--end-date",
            "2024-03-05",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[0] == "ticker;date;ema20;sma50;rsi"
    assert not any("forward_returns" in line for line in lines)
    assert lines[1] == "AAA;2024-03-01;100.0952;100.0200;55.0000"


def test_cli_forward_returns_adds_csv_columns_and_uses_earliest_ties(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    _insert_price_series(price_db, "AAA", "usa", _single_signal_with_immediate_forward_prices())
    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-02-28",
            "--end-date",
            "2024-03-05",
            "--include-forward-returns",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert (
        lines[0]
        == "ticker;date;ema20;sma50;rsi;max_forward_return_pct;max_forward_return_days;min_forward_return_pct;min_forward_return_days"
    )
    assert lines[1] == "AAA;2024-03-01;100.0952;100.0200;55.0000;8.9109;1;-10.8911;2"
    assert lines[-4:] == [
        "SUMMARY forward_returns_included=1",
        "SUMMARY forward_window=60",
        "SUMMARY forward_returns_rows_with_data=1",
        "SUMMARY forward_returns_rows_without_data=0",
    ]


def test_cli_forward_returns_respects_custom_window(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    _insert_price_series(price_db, "AAA", "usa", _single_signal_with_immediate_forward_prices())
    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-02-28",
            "--end-date",
            "2024-03-05",
            "--include-forward-returns",
            "--forward-window",
            "1",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[1] == "AAA;2024-03-01;100.0952;100.0200;55.0000;8.9109;1;8.9109;1"
    assert "SUMMARY forward_window=1" in lines


def test_cli_forward_returns_handles_missing_future_data_and_summary_only(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    _insert_price_series(price_db, "AAA", "usa", _single_signal_with_no_future_series())
    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-03-01",
            "--end-date",
            "2024-03-01",
            "--include-forward-returns",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[1] == "AAA;2024-03-01;100.0952;100.0200;55.0000;;;;"
    assert lines[-4:] == [
        "SUMMARY forward_returns_included=1",
        "SUMMARY forward_window=60",
        "SUMMARY forward_returns_rows_with_data=0",
        "SUMMARY forward_returns_rows_without_data=1",
    ]

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-03-01",
            "--end-date",
            "2024-03-01",
            "--include-forward-returns",
            "--output-format",
            "summary",
        ]
    )

    assert exit_code == 0
    summary_lines = capsys.readouterr().out.strip().splitlines()
    assert all(line.startswith("SUMMARY ") for line in summary_lines)
    assert summary_lines[-4:] == [
        "SUMMARY forward_returns_included=1",
        "SUMMARY forward_window=60",
        "SUMMARY forward_returns_rows_with_data=0",
        "SUMMARY forward_returns_rows_without_data=1",
    ]


def test_cli_forward_returns_limit_counts_returned_rows_only(tmp_path, capsys):
    price_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"
    _create_price_db(price_db)
    _create_analysis_db(analysis_db)

    _insert_price_series(price_db, "AAA", "usa", _single_signal_with_immediate_forward_prices())
    _insert_price_series(price_db, "AAB", "usa", _single_signal_with_no_future_series())
    _insert_rsi(analysis_db, "AAA", "2024-03-01", 55.0)
    _insert_rsi(analysis_db, "AAB", "2024-03-01", 65.0)

    exit_code = signal_scan_main(
        [
            "--db",
            str(price_db),
            "--analysis-db",
            str(analysis_db),
            "--market",
            "usa",
            "--start-date",
            "2024-03-01",
            "--end-date",
            "2024-03-01",
            "--limit",
            "1",
            "--include-forward-returns",
        ]
    )

    assert exit_code == 0
    lines = capsys.readouterr().out.strip().splitlines()
    assert lines[1].startswith("AAA;2024-03-01;")
    assert "SUMMARY candidates=2" in lines
    assert "SUMMARY returned=1" in lines
    assert "SUMMARY forward_returns_rows_with_data=1" in lines
    assert "SUMMARY forward_returns_rows_without_data=0" in lines
