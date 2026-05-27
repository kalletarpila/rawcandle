from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.run_datacenter_dashboard_pullback_context_source_audit import main


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                action TEXT,
                primary_reason TEXT,
                pullback_validity TEXT,
                pullback_reason TEXT,
                entry_readiness TEXT,
                entry_readiness_reason TEXT,
                candidate_priority INTEGER,
                candidate_priority_label TEXT,
                candidate_priority_reason TEXT,
                freshness_status TEXT,
                ma_break_status TEXT,
                rolling_5d_status TEXT,
                rolling_2d_status TEXT,
                daily_status TEXT,
                pullback_days INTEGER,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT,
                distance_to_ema20 REAL,
                distance_to_ema20_pct REAL,
                latest_bullish_signal_age_td INTEGER,
                latest_bearish_signal_age_td INTEGER,
                structure_warning_overrides_bullish_signal INTEGER
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
                pullback_days INTEGER,
                bullish_candle_signal INTEGER,
                bullish_divergence_signal INTEGER,
                hidden_bullish_divergence_signal INTEGER,
                latest_bullish_signal_age_td INTEGER,
                latest_bearish_signal_age_td INTEGER,
                freshness_status TEXT,
                structure_warning_overrides_bullish_signal INTEGER,
                ma_break_status TEXT,
                rolling_5d_status TEXT,
                rolling_2d_status TEXT,
                daily_status TEXT,
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT,
                distance_to_ema20 REAL,
                distance_to_ema20_pct REAL
            )
            """
        )


def _insert_enrichment_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, action, primary_reason,
                pullback_validity, pullback_reason, entry_readiness, entry_readiness_reason,
                candidate_priority, candidate_priority_label, candidate_priority_reason,
                freshness_status, ma_break_status, rolling_5d_status, rolling_2d_status,
                daily_status, pullback_days, latest_bos_event_type, latest_reset_reason,
                distance_to_ema20, distance_to_ema20_pct, latest_bullish_signal_age_td,
                latest_bearish_signal_age_td, structure_warning_overrides_bullish_signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _insert_source_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, pullback_signal, breakout_signal,
                pullback_days, bullish_candle_signal, bullish_divergence_signal,
                hidden_bullish_divergence_signal, latest_bullish_signal_age_td,
                latest_bearish_signal_age_td, freshness_status,
                structure_warning_overrides_bullish_signal, ma_break_status,
                rolling_5d_status, rolling_2d_status, daily_status, latest_bos_event_type,
                latest_reset_reason, distance_to_ema20, distance_to_ema20_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _snapshot(tickers: list[dict[str, object]]):
    return SimpleNamespace(tickers=tickers, decision_trace=[], run=None, action_summary=[])


def _run_cli(capsys, monkeypatch, *, analysis_db: Path, reports_snapshot, enrichment_snapshot):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        if dashboard_db.endswith("reports.db"):
            return reports_snapshot
        if dashboard_db.endswith("enrichment.db"):
            return enrichment_snapshot
        raise AssertionError(f"unexpected dashboard_db: {dashboard_db}")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_context_source_audit.load_dashboard_snapshot",
        _fake_load_dashboard_snapshot,
    )

    exit_code = main(
        [
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
            "--max-examples",
            "100",
        ]
    )
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_detects_reports_early_pullback_vs_enrichment_no_pullback_gap(
    tmp_path, monkeypatch, capsys
):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                "OK",
                "NO_PULLBACK",
                "NO_PULLBACK_CONTEXT",
                "NOT_READY",
                "NO_PULLBACK",
                5,
                "P5_NOT_READY",
                "NOT_READY",
                None,
                None,
                None,
                None,
                "WATCH",
                0,
                "BOS_UP",
                None,
                None,
                None,
                None,
                None,
                0,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, None, None, None, 0, None, None, None, None, "BOS_UP", None, None, None)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "pullback_validity": "EARLY_PULLBACK",
                "entry_readiness": "EARLY_MONITOR",
                "candidate_priority_label": "P4_EARLY_MONITOR",
            }
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "pullback_validity": "NO_PULLBACK",
                "entry_readiness": "NOT_READY",
                "candidate_priority_label": "P5_NOT_READY",
            }
        ]
    )

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
    )

    assert exit_code == 0
    assert error == ""
    assert "selected_tickers;AAA;PULLBACK_MISMATCH;EARLY_PULLBACK;NO_PULLBACK;" in output
    assert "gap_group_distribution;EARLY_PULLBACK;NO_PULLBACK;1" in output


def test_detects_missing_pullback_days_and_pullback_signal(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                "OK",
                "NO_PULLBACK",
                "NO_PULLBACK_CONTEXT",
                "NOT_READY",
                "NO_PULLBACK",
                5,
                "P5_NOT_READY",
                "NOT_READY",
                None,
                None,
                None,
                None,
                "WATCH",
                0,
                "BOS_UP",
                None,
                None,
                None,
                None,
                None,
                0,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, None, None, None, 0, None, None, None, None, "BOS_UP", None, None, None)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "pullback_validity": "VALID_PULLBACK",
                "entry_readiness": "EARLY_MONITOR",
                "candidate_priority_label": "P4_EARLY_MONITOR",
                "pullback_days": 3,
            }
        ]
    )
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
    )

    assert exit_code == 0
    assert (
        "hypothesis_summary;ENRICHMENT_MISSING_PULLBACK_DAYS;LIKELY;selected=1|missing_pullback_days=1"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.missing_pullback_days=1"
        in output
    )


def test_detects_missing_bullish_signal_age_for_early_case(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                "OK",
                "NO_PULLBACK",
                "NO_PULLBACK_CONTEXT",
                "NOT_READY",
                "NO_PULLBACK",
                5,
                "P5_NOT_READY",
                "NOT_READY",
                "FRESH_BULLISH_SIGNAL",
                None,
                None,
                None,
                "WATCH",
                0,
                "BOS_UP",
                None,
                None,
                None,
                None,
                None,
                0,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, None, None, "FRESH_BULLISH_SIGNAL", 0, None, None, None, None, "BOS_UP", None, None, None)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "pullback_validity": "EARLY_PULLBACK",
                "entry_readiness": "EARLY_MONITOR",
                "candidate_priority_label": "P4_EARLY_MONITOR",
                "latest_bullish_signal_age_td": 1,
            }
        ]
    )
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
    )

    assert exit_code == 0
    assert (
        "hypothesis_summary;ENRICHMENT_MISSING_BULLISH_SIGNAL_AGE;LIKELY;selected=1|missing_bullish_signal_age=1"
        in output
    )


def test_detects_missing_rolling_5d_status_context(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                "OK",
                "NO_PULLBACK",
                "NO_PULLBACK_CONTEXT",
                "NOT_READY",
                "NO_PULLBACK",
                5,
                "P5_NOT_READY",
                "NOT_READY",
                None,
                None,
                None,
                None,
                "WATCH",
                0,
                "BOS_UP",
                None,
                None,
                None,
                None,
                None,
                0,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, None, None, None, 0, None, None, None, None, "BOS_UP", None, None, None)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "pullback_validity": "EARLY_PULLBACK",
                "entry_readiness": "EARLY_MONITOR",
                "candidate_priority_label": "P4_EARLY_MONITOR",
                "rolling_5d_status": "EARLY_PULLBACK_SETUP",
            }
        ]
    )
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
    )

    assert exit_code == 0
    assert (
        "hypothesis_summary;REPORTS_PULLBACK_USES_ROLLING_5D_CONTEXT;LIKELY;selected=1|missing_rolling_5d_context=1"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_pullback_context_source_audit.needs_rolling_pullback_status=1"
        in output
    )


def test_detects_source_has_pullback_signal_but_not_mapped(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                "OK",
                "NO_PULLBACK",
                "NO_PULLBACK_CONTEXT",
                "NOT_READY",
                "NO_PULLBACK",
                5,
                "P5_NOT_READY",
                "NOT_READY",
                None,
                None,
                None,
                None,
                "WATCH",
                0,
                "BOS_UP",
                None,
                None,
                None,
                None,
                None,
                0,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 2, 1, 0, 0, 1, None, "FRESH_BULLISH_SIGNAL", 0, "OK", None, None, "WATCH", "BOS_UP", None, 1.5, 2.5)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "pullback_validity": "VALID_PULLBACK",
                "entry_readiness": "EARLY_MONITOR",
                "candidate_priority_label": "P4_EARLY_MONITOR",
            }
        ]
    )
    enrichment_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
    )

    assert exit_code == 0
    assert (
        "hypothesis_summary;SOURCE_HAS_PULLBACK_FIELDS_NOT_MAPPED;LIKELY;selected=1|source_has_pullback_fields_not_mapped=1"
        in output
    )


def test_cli_is_read_only_for_analysis_db(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_enrichment_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "WATCH",
                "OK",
                "NO_PULLBACK",
                "NO_PULLBACK_CONTEXT",
                "NOT_READY",
                "NO_PULLBACK",
                5,
                "P5_NOT_READY",
                "NOT_READY",
                None,
                None,
                None,
                None,
                "WATCH",
                0,
                "BOS_UP",
                None,
                None,
                None,
                None,
                None,
                0,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, 0, 0, 0, None, None, None, 0, None, None, None, None, "BOS_UP", None, None, None)],
    )
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "EARLY_PULLBACK"}])
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
    assert "SUMMARY datacenter_dashboard_pullback_context_source_audit.status=OK" in output
    assert after_counts == before_counts
