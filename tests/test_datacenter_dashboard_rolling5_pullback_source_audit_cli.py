from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.run_datacenter_dashboard_rolling5_pullback_source_audit import main


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
                breakout_signal INTEGER,
                bullish_candle_signal INTEGER,
                bullish_divergence_signal INTEGER,
                hidden_bullish_divergence_signal INTEGER,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT,
                exit_risk_signal INTEGER,
                exit_risk_severity TEXT,
                price_data_status TEXT,
                distance_to_ema20_pct REAL,
                return_5d REAL,
                return_10d REAL,
                rolling_5d_status TEXT,
                pullback_days INTEGER,
                latest_bullish_signal_age_td INTEGER,
                structure_warning_overrides_bullish_signal INTEGER
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
                signal_date, taxonomy_version, ticker, pullback_signal, breakout_signal,
                bullish_candle_signal, bullish_divergence_signal,
                hidden_bullish_divergence_signal, latest_bos_event_type, latest_reset_reason,
                exit_risk_signal, exit_risk_severity, price_data_status, distance_to_ema20_pct,
                return_5d, return_10d, rolling_5d_status, pullback_days,
                latest_bullish_signal_age_td, structure_warning_overrides_bullish_signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _snapshot(tickers: list[dict[str, object]]):
    return SimpleNamespace(tickers=tickers, decision_trace=[], run=None, action_summary=[])


def _run_cli(
    capsys,
    monkeypatch,
    *,
    analysis_db: Path,
    reports_snapshot,
    enrichment_snapshot,
    tickers: str | None = None,
):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        if dashboard_db.endswith("reports.db"):
            return reports_snapshot
        if dashboard_db.endswith("enrichment.db"):
            return enrichment_snapshot
        raise AssertionError(f"unexpected dashboard_db: {dashboard_db}")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_pullback_source_audit.load_dashboard_snapshot",
        _fake_load_dashboard_snapshot,
    )

    argv = [
        "--reports-dashboard-db",
        "/tmp/reports.db",
        "--reports-run-id",
        "REPORTS_RUN",
        "--enrichment-dashboard-db",
        "/tmp/enrichment.db",
        "--enrichment-run-id",
        "ENRICH_RUN",
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


def test_detects_available_source_columns_and_summary_flags(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 1, 0, 0, "BOS_UP", None, 0, "", "OK", 0.2, 1.5, 2.5, "", 1, 0, 0)],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"}])
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
    )

    assert exit_code == 0
    assert error == ""
    assert "source_table_columns;dc_ticker_swing_signal_daily;pullback_signal;1;required_candidate_column" in output
    assert "source_table_columns;dc_ticker_swing_signal_daily;bullish_candle_signal;1;required_candidate_column" in output
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.source_has_pullback_signal=1" in output
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.source_has_bullish_signals=1" in output


def test_candidate_mapping_evaluates_pullback_candidate_failed_and_no_pullback(
    tmp_path, monkeypatch, capsys
):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA"),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "BBB"),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "CCC"),
        ],
    )
    _insert_source_rows(
        analysis_db,
        [
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, "BOS_UP", None, 0, "", "OK", 0.1, 1.0, 1.5, "", 1, None, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 1, 0, 0, "BOS_UP", None, 0, "", "OK", 0.2, 1.5, 2.0, "", 1, 0, 0),
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "BBB", 1, 0, 0, 0, 0, "BOS_DOWN", "DOUBLE_BOS_DOWN", 1, "HIGH", "OK", -0.2, -1.0, -2.0, "", 1, None, 1),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "BBB", 1, 0, 0, 0, 0, "BOS_DOWN", "DOUBLE_BOS_DOWN", 1, "HIGH", "OK", -0.3, -1.2, -2.5, "", 1, None, 1),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "CCC", 0, 0, 0, 0, 0, "BOS_UP", None, 0, "", "OK", 0.0, 0.2, 0.3, "", 0, None, 0),
        ],
    )
    reports_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "EARLY_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "STRUCTURE_BLOCKED_PULLBACK"},
            {"ticker": "CCC", "pullback_validity": "BREAKDOWN_NOT_PULLBACK"},
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "NO_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "NO_PULLBACK"},
            {"ticker": "CCC", "pullback_validity": "NO_PULLBACK"},
        ]
    )

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        tickers="AAA BBB CCC",
    )

    assert exit_code == 0
    assert "candidate_mapping_evaluation;AAA;EARLY_PULLBACK;PULLBACK_CANDIDATE;2;0;0;" in output
    assert "candidate_mapping_evaluation;BBB;STRUCTURE_BLOCKED_PULLBACK;FAILED_PULLBACK;2;;1;" in output
    assert "candidate_mapping_evaluation;CCC;BREAKDOWN_NOT_PULLBACK;NO_PULLBACK;0;;0;" in output


def test_bullish_signal_age_uses_latest_or_earlier_row(tmp_path, monkeypatch, capsys):
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
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, "BOS_UP", None, 0, "", "OK", 0.1, 1.0, 1.0, "", 1, None, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 1, 0, 0, "BOS_UP", None, 0, "", "OK", 0.2, 1.1, 1.1, "", 1, None, 0),
            ("2026-05-20", "DC_TAXONOMY_FULL_V1", "BBB", 0, 0, 1, 0, 0, "BOS_UP", None, 0, "", "OK", 0.0, 0.5, 0.5, "", 0, None, 0),
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "BBB", 0, 0, 0, 0, 0, "BOS_UP", None, 0, "", "OK", 0.0, 0.2, 0.2, "", 0, None, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "BBB", 0, 0, 0, 0, 0, "BOS_UP", None, 0, "", "OK", 0.0, 0.1, 0.1, "", 0, None, 0),
        ],
    )
    reports_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "EARLY_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "EARLY_PULLBACK"},
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "NO_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "NO_PULLBACK"},
        ]
    )

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        tickers="AAA BBB",
    )

    assert exit_code == 0
    assert "candidate_mapping_evaluation;AAA;EARLY_PULLBACK;PULLBACK_CANDIDATE;2;0;0;" in output
    assert "candidate_mapping_evaluation;BBB;EARLY_PULLBACK;NO_PULLBACK;0;2;0;" in output


def test_safe_v0_mapping_recommended_when_reports_correlate_with_candidates(
    tmp_path, monkeypatch, capsys
):
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
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 0, 0, 0, "BOS_UP", None, 0, "", "OK", 0.1, 1.0, 1.2, "", 1, None, 0),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 1, 0, 0, "BOS_UP", None, 0, "", "OK", 0.2, 1.1, 1.3, "", 1, None, 0),
            ("2026-05-21", "DC_TAXONOMY_FULL_V1", "BBB", 1, 0, 0, 0, 0, "BOS_DOWN", "DOUBLE_BOS_DOWN", 1, "HIGH", "OK", -0.2, -0.5, -0.7, "", 1, None, 1),
            ("2026-05-22", "DC_TAXONOMY_FULL_V1", "BBB", 0, 0, 0, 0, 0, "BOS_DOWN", "DOUBLE_BOS_DOWN", 1, "HIGH", "OK", -0.3, -0.6, -0.8, "", 0, None, 1),
        ],
    )
    reports_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "STRUCTURE_BLOCKED_PULLBACK"},
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "NO_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "NO_PULLBACK"},
        ]
    )

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
    )

    assert exit_code == 0
    assert (
        "hypothesis_summary;SAFE_V0_MAPPING_RECOMMENDED;LIKELY;"
        "structured_source_has_inputs=LIKELY|valid_early=LIKELY|structure_blocked=LIKELY"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.safe_v0_mapping_recommended=1"
        in output
    )


def test_cli_is_read_only_for_analysis_db(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA")],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 1, 0, 0, "BOS_UP", None, 0, "", "OK", 0.2, 1.5, 2.5, "", 1, 0, 0)],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"}])
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    with sqlite3.connect(analysis_db) as conn:
        before_counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in (
                "dc_dashboard_ticker_enrichment_daily",
                "dc_ticker_swing_signal_daily",
            )
        }

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
    )

    with sqlite3.connect(analysis_db) as conn:
        after_counts = {
            table: int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in before_counts
        }

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_rolling5_pullback_source_audit.status=OK" in output
    assert after_counts == before_counts
