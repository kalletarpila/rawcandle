from __future__ import annotations

import sqlite3
from pathlib import Path

from dev_tools.run_datacenter_dashboard_ticker_signal_coverage_audit import main


def _create_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_ticker_swing_signal_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                breakout_signal INTEGER,
                pullback_signal INTEGER,
                exit_risk_signal INTEGER,
                exit_risk_severity TEXT,
                exit_reason TEXT,
                price_data_status TEXT,
                ticker_trend_state TEXT,
                latest_structure_label TEXT,
                latest_structure_freshness TEXT,
                latest_bos_event_type TEXT,
                latest_bos_freshness TEXT,
                latest_reset_reason TEXT,
                latest_reset_freshness TEXT,
                bullish_candle_signal INTEGER,
                bullish_divergence_signal INTEGER,
                hidden_bullish_divergence_signal INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT,
                current_status TEXT,
                ma_break_status TEXT,
                freshness_status TEXT,
                trend_state TEXT,
                latest_structure_label TEXT,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT,
                daily_status TEXT,
                rolling_2d_status TEXT,
                rolling_5d_status TEXT,
                rolling_30d_status TEXT,
                pullback_validity TEXT,
                data_quality_status TEXT
            )
            """
        )


def _insert_source(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, breakout_signal, pullback_signal,
                exit_risk_signal, exit_risk_severity, exit_reason, price_data_status,
                ticker_trend_state, latest_structure_label, latest_structure_freshness,
                latest_bos_event_type, latest_bos_freshness, latest_reset_reason,
                latest_reset_freshness, bullish_candle_signal, bullish_divergence_signal,
                hidden_bullish_divergence_signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _insert_enrichment(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, action, current_status,
                ma_break_status, freshness_status, trend_state, latest_structure_label,
                latest_bos_event_type, latest_reset_reason, daily_status,
                rolling_2d_status, rolling_5d_status, rolling_30d_status,
                pullback_validity, data_quality_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _run_cli(capsys, db_path: Path, *extra: str):
    exit_code = main(
        [
            "--analysis-db",
            str(db_path),
            "--signal-date",
            "2026-05-22",
            "--taxonomy-version",
            "DC_TAXONOMY_FULL_V1",
            *extra,
        ]
    )
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_basic_field_coverage_marks_source_risk_signals_not_mapped(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db(db_path)
    _insert_source(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                0,
                0,
                1,
                "HIGH",
                "BOS_DOWN",
                "OK",
                "DOWN",
                "LL",
                "FRESH",
                "BOS_DOWN",
                "FRESH",
                "DOUBLE_BOS_DOWN",
                "FRESH",
                0,
                0,
                0,
            )
        ],
    )
    _insert_enrichment(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                None,
                None,
                None,
                None,
                "DOWN",
                "LL",
                "BOS_DOWN",
                "DOUBLE_BOS_DOWN",
                None,
                None,
                None,
                None,
                None,
                "OK",
            )
        ],
    )

    exit_code, output, error = _run_cli(capsys, db_path)

    assert exit_code == 0
    assert error == ""
    assert "field_coverage;exit_risk_severity;1;0;1;0;0;ENRICHMENT_COLUMN_MISSING" in output
    assert (
        "mapping_gap_hypothesis;SOURCE_HAS_RISK_SIGNALS_NOT_MAPPED;LIKELY;"
        in output
    )


def test_source_lacks_decision_signals_is_likely(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db(db_path)
    _insert_source(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                0,
                0,
                0,
                None,
                None,
                "OK",
                "UP",
                "HH",
                None,
                "BOS_UP",
                None,
                None,
                None,
                1,
                0,
                0,
            )
        ],
    )
    _insert_enrichment(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "NEUTRAL",
                "NEUTRAL",
                None,
                None,
                "UP",
                "HH",
                "BOS_UP",
                None,
                None,
                None,
                None,
                None,
                None,
                "OK",
            )
        ],
    )

    exit_code, output, _ = _run_cli(capsys, db_path)

    assert exit_code == 0
    assert "mapping_gap_hypothesis;SOURCE_LACKS_DECISION_SIGNALS;LIKELY;" in output


def test_enrichment_status_fields_missing_is_likely(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db(db_path)
    _insert_source(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                1,
                1,
                1,
                "HIGH",
                "EXIT",
                "WARN",
                "DOWN",
                "LL",
                "FRESH",
                "BOS_DOWN",
                "FRESH",
                "DOUBLE_BOS_DOWN",
                "FRESH",
                0,
                0,
                0,
            )
        ],
    )
    _insert_enrichment(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                None,
                None,
                None,
                None,
                "DOWN",
                "LL",
                "BOS_DOWN",
                "DOUBLE_BOS_DOWN",
                None,
                None,
                None,
                None,
                None,
                "WARN",
            )
        ],
    )

    exit_code, output, _ = _run_cli(capsys, db_path)

    assert exit_code == 0
    assert "mapping_gap_hypothesis;ENRICHMENT_STATUS_FIELDS_MISSING;LIKELY;" in output


def test_mapping_pairs_are_counted_for_trend_and_price_status(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db(db_path)
    _insert_source(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                0,
                0,
                0,
                None,
                None,
                "WARN",
                "UP",
                "HH",
                None,
                "BOS_UP",
                None,
                None,
                None,
                1,
                0,
                0,
            )
        ],
    )
    _insert_enrichment(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "NEUTRAL",
                "NEUTRAL",
                None,
                None,
                "UP",
                "HH",
                "BOS_UP",
                None,
                "NEUTRAL_MONITOR",
                None,
                None,
                None,
                None,
                "WARN",
            )
        ],
    )

    exit_code, output, _ = _run_cli(capsys, db_path)

    assert exit_code == 0
    assert "field_coverage;price_data_status;1;1;1;1;0;BOTH_POPULATED" in output
    assert "field_coverage;ticker_trend_state;1;1;1;1;0;BOTH_POPULATED" in output


def test_ticker_examples_include_missing_mappings(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db(db_path)
    _insert_source(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                1,
                1,
                1,
                "HIGH",
                "EXIT",
                "WARN",
                "DOWN",
                "LL",
                "FRESH",
                "BOS_DOWN",
                "FRESH",
                "DOUBLE_BOS_DOWN",
                "FRESH",
                0,
                0,
                0,
            )
        ],
    )
    _insert_enrichment(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                None,
                None,
                None,
                None,
                "DOWN",
                "LL",
                "BOS_DOWN",
                "DOUBLE_BOS_DOWN",
                None,
                None,
                None,
                None,
                None,
                "WARN",
            )
        ],
    )

    exit_code, output, _ = _run_cli(capsys, db_path, "--tickers", "AAA")

    assert exit_code == 0
    assert "ticker_examples;AAA;SOURCE_RISK_ENRICHMENT_NEUTRAL;" in output


def test_missing_source_or_enrichment_table_fails_clearly(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE dc_ticker_swing_signal_daily (signal_date TEXT)")

    exit_code, output, error = _run_cli(capsys, db_path)

    assert exit_code == 1
    assert output == ""
    assert "missing required enrichment table: dc_dashboard_ticker_enrichment_daily" in error


def test_read_only_behavior_keeps_row_counts_unchanged(tmp_path, capsys):
    db_path = tmp_path / "analysis.db"
    _create_db(db_path)
    _insert_source(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                0,
                0,
                0,
                None,
                None,
                "OK",
                "UP",
                "HH",
                None,
                "BOS_UP",
                None,
                None,
                None,
                1,
                0,
                0,
            )
        ],
    )
    _insert_enrichment(
        db_path,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "NEUTRAL",
                "NEUTRAL",
                None,
                None,
                "UP",
                "HH",
                "BOS_UP",
                None,
                "NEUTRAL_MONITOR",
                None,
                None,
                None,
                None,
                "OK",
            )
        ],
    )
    with sqlite3.connect(db_path) as conn:
        before_source = conn.execute("SELECT COUNT(*) FROM dc_ticker_swing_signal_daily").fetchone()[0]
        before_enrichment = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]

    exit_code, output, error = _run_cli(capsys, db_path)

    with sqlite3.connect(db_path) as conn:
        after_source = conn.execute("SELECT COUNT(*) FROM dc_ticker_swing_signal_daily").fetchone()[0]
        after_enrichment = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_ticker_signal_coverage_audit.status=OK" in output
    assert before_source == after_source
    assert before_enrichment == after_enrichment
