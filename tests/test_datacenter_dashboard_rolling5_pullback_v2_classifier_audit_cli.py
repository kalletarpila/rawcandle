from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.run_datacenter_dashboard_rolling5_pullback_v2_classifier_audit import main


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
                ma_break_status TEXT,
                return_10d_lt_minus_8pct INTEGER,
                close_below_ema20 INTEGER
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
                distance_to_ema20_pct, return_10d, ma_break_status,
                return_10d_lt_minus_8pct, close_below_ema20
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _snapshot(tickers: list[dict[str, object]]):
    return SimpleNamespace(tickers=tickers, decision_trace=[], run=None, action_summary=[])


def _run_cli(capsys, monkeypatch, *, analysis_db: Path, reports_snapshot, tickers: str | None = None):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        return reports_snapshot

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_pullback_v2_classifier_audit.load_dashboard_snapshot",
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


def test_v2_does_not_infer_breakdown_from_numeric_return_10d_alone(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.10, -0.09, None, 0, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.12, -0.10, None, 0, 0),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "EARLY_PULLBACK"}])

    exit_code, output, error = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert error == ""
    assert "v1_confusion_matrix;EARLY_PULLBACK;BREAKDOWN_NOT_PULLBACK;1" in output
    assert "v2_confusion_matrix;EARLY_PULLBACK;EARLY_PULLBACK;1" in output


def test_v2_does_not_infer_breakdown_from_distance_to_ema20_pct_alone(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 1, -0.10, 0.01, None, 0, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 1, -0.15, 0.02, None, 0, 0),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "EARLY_PULLBACK"}])

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "v1_confusion_matrix;EARLY_PULLBACK;BREAKDOWN_NOT_PULLBACK;1" in output
    assert "v2_confusion_matrix;EARLY_PULLBACK;EARLY_PULLBACK;1" in output


def test_v2_still_maps_explicit_ma_break_status_to_breakdown(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.05, 0.01, "EMA20_CONFIRMED_BREAK", 0, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.06, 0.02, "EMA20_CONFIRMED_BREAK", 0, 0),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "BREAKDOWN_NOT_PULLBACK"}])

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "v2_distribution;BREAKDOWN_NOT_PULLBACK_CONTEXT;BREAKDOWN_NOT_PULLBACK;1" in output


def test_v2_improvement_accounting_is_deterministic(tmp_path, monkeypatch, capsys):
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
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.10, -0.09, None, 0, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.11, -0.10, None, 0, 0),
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "BBB", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.10, 0.01, "EMA20_CONFIRMED_BREAK", 0, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "BBB", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.11, 0.02, "EMA20_CONFIRMED_BREAK", 0, 0),
        ],
    )
    reports_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "EARLY_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "BREAKDOWN_NOT_PULLBACK"},
        ]
    )

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "classifier_comparison_summary;exact_matches;1;2;1" in output
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v2_improvements=1" in output
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v2_regressions=0" in output


def test_v2_regression_accounting_is_deterministic(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.10, 0.01, None, 0, 1),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.11, 0.02, None, 0, 1),
        ],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "v1_confusion_matrix;NO_PULLBACK;NO_PULLBACK;1" in output
    assert "v2_confusion_matrix;NO_PULLBACK;BREAKDOWN_NOT_PULLBACK;1" in output
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.v2_regressions=1" in output


def test_cli_is_read_only_for_analysis_db(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(analysis_db, [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")])
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.10, 0.01, None, 0, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, "BOS_UP", None, 0, 0.11, 0.02, None, 0, 0),
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
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_v2_classifier_audit.status=OK" in output
    assert after_counts == before_counts
