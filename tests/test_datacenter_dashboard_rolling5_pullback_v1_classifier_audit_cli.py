from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.run_datacenter_dashboard_rolling5_pullback_v1_classifier_audit import main


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                pullback_signal INTEGER,
                conservative_ema20_pullback_signal INTEGER,
                fast_ema10_pullback_signal INTEGER,
                bullish_candle_signal INTEGER,
                bullish_divergence_signal INTEGER,
                hidden_bullish_divergence_signal INTEGER,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT,
                exit_risk_signal INTEGER,
                distance_to_ema20_pct REAL,
                return_10d REAL,
                ma_break_status TEXT
            )
            """
        )


def _insert_enrichment_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker
            ) VALUES (?, ?, ?)
            """,
            rows,
        )


def _insert_source_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, pullback_signal,
                conservative_ema20_pullback_signal, fast_ema10_pullback_signal,
                bullish_candle_signal, bullish_divergence_signal, hidden_bullish_divergence_signal,
                latest_bos_event_type, latest_reset_reason, exit_risk_signal,
                distance_to_ema20_pct, return_10d, ma_break_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _snapshot(tickers: list[dict[str, object]]):
    return SimpleNamespace(tickers=tickers, decision_trace=[], run=None, action_summary=[])


def _run_cli(capsys, monkeypatch, *, analysis_db: Path, reports_snapshot, tickers: str | None = None):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        return reports_snapshot

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_pullback_v1_classifier_audit.load_dashboard_snapshot",
        _fake_load_dashboard_snapshot,
    )

    argv = [
        "--reports-dashboard-db",
        "/tmp/reports.db",
        "--reports-run-id",
        "REPORTS_RUN",
        "--analysis-db",
        str(analysis_db),
        "--ecosystem-code",
        "DATACENTER",
        "--report-date",
        "2026-05-22",
        "--lookback-rows",
        "5",
        "--max-examples",
        "100",
    ]
    if tickers:
        argv.extend(["--tickers", tickers])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_classifier_maps_pullback_plus_fresh_bullish_signal_to_valid(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.1, 0.2, None),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 1, 0, 0, "BOS_UP", None, 0, 0.2, 0.3, None),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"}])

    exit_code, output, error = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert error == ""
    assert "classifier_distribution;VALID_PULLBACK_CONTEXT;VALID_PULLBACK;1" in output


def test_classifier_maps_pullback_plus_old_or_missing_bullish_signal_to_early(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-20", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 1, 0, 0, "BOS_UP", None, 0, 0.1, 0.2, None),
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.2, 0.3, None),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.3, 0.4, None),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "EARLY_PULLBACK"}])

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "classifier_distribution;EARLY_PULLBACK_CONTEXT;EARLY_PULLBACK;1" in output


def test_classifier_maps_pullback_plus_bos_down_to_structure_blocked(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_DOWN", "DOUBLE_BOS_DOWN", 0, 0.1, 0.2, None),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.2, 0.3, None),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "STRUCTURE_BLOCKED_PULLBACK"}])

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "classifier_distribution;STRUCTURE_BLOCKED_PULLBACK_CONTEXT;STRUCTURE_BLOCKED_PULLBACK;1" in output


def test_classifier_maps_breakdown_context_to_breakdown(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 1, -0.2, -0.09, "EMA20_CONFIRMED_BREAK"),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 1, -0.3, -0.10, "EMA20_CONFIRMED_BREAK"),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "BREAKDOWN_NOT_PULLBACK"}])

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "classifier_distribution;BREAKDOWN_NOT_PULLBACK_CONTEXT;BREAKDOWN_NOT_PULLBACK;1" in output


def test_classifier_maps_no_pullback_to_no_pullback(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.1, 0.2, None),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.2, 0.3, None),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "classifier_distribution;NO_PULLBACK_CONTEXT;NO_PULLBACK;1" in output


def test_classifier_maps_insufficient_rows_to_insufficient_data(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 1, 0, 0, "BOS_UP", None, 0, 0.2, 0.3, None),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "INSUFFICIENT_DATA"}])

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "classifier_distribution;INSUFFICIENT_DATA;INSUFFICIENT_DATA;1" in output


def test_confusion_matrix_and_exact_match_rate_are_deterministic(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA"),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "BBB"),
        ],
    )
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.1, 0.2, None),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 1, 0, 0, "BOS_UP", None, 0, 0.2, 0.3, None),
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "BBB", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.1, 0.2, None),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "BBB", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.2, 0.3, None),
        ],
    )
    reports_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "EARLY_PULLBACK"},
        ]
    )

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "confusion_matrix;VALID_PULLBACK;VALID_PULLBACK;1" in output
    assert "confusion_matrix;EARLY_PULLBACK;NO_PULLBACK;1" in output
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.exact_matches=1" in output
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.exact_match_rate=0.5000" in output


def test_cli_is_read_only_for_analysis_db(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.1, 0.2, None),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.2, 0.3, None),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    with sqlite3.connect(analysis_db) as conn:
        before_counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "dc_dashboard_ticker_enrichment_daily",
                "dc_ticker_swing_signal_daily",
            )
        }

    exit_code, output, error = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    with sqlite3.connect(analysis_db) as conn:
        after_counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in before_counts
        }

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_v1_classifier_audit.status=OK" in output
    assert after_counts == before_counts
