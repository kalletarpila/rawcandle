from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.run_datacenter_dashboard_pullback_readiness_parity_diagnosis import main


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
                entry_readiness TEXT,
                candidate_priority TEXT,
                candidate_priority_label TEXT,
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
                latest_bos_event_type TEXT,
                latest_reset_reason TEXT,
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
                pullback_validity, entry_readiness, candidate_priority, candidate_priority_label,
                freshness_status, ma_break_status, rolling_5d_status, rolling_2d_status,
                daily_status, pullback_days, latest_bos_event_type, latest_reset_reason,
                distance_to_ema20, distance_to_ema20_pct, latest_bullish_signal_age_td,
                latest_bearish_signal_age_td, structure_warning_overrides_bullish_signal
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _insert_source_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_ticker_swing_signal_daily (
                signal_date, taxonomy_version, ticker, pullback_signal, breakout_signal,
                pullback_days, latest_bos_event_type, latest_reset_reason, distance_to_ema20_pct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )


def _snapshot(tickers: list[dict[str, object]]):
    return SimpleNamespace(tickers=tickers, decision_trace=[], run=None)


def _run_cli(capsys, monkeypatch, *, analysis_db: Path, reports_snapshot, enrichment_snapshot):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        if dashboard_db.endswith("reports.db"):
            return reports_snapshot
        if dashboard_db.endswith("enrichment.db"):
            return enrichment_snapshot
        raise AssertionError(f"unexpected dashboard_db: {dashboard_db}")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_readiness_parity_diagnosis.load_dashboard_snapshot",
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


def test_distribution_comparison_reflects_reports_vs_enrichment_mismatch(tmp_path, monkeypatch, capsys):
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
                "reason",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "WATCH",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, None, None, 1.2)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "VALID_PULLBACK",
                "entry_readiness": "EARLY_MONITOR",
                "candidate_priority_label": "P4_EARLY_MONITOR",
            }
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "INSUFFICIENT_DATA",
                "entry_readiness": "INSUFFICIENT_DATA",
                "candidate_priority_label": "",
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
    assert "pullback_distribution;reports;VALID_PULLBACK;1" in output
    assert "pullback_distribution;enrichment;INSUFFICIENT_DATA;1" in output
    assert (
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.reports_non_insufficient_pullback=1"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.enrichment_insufficient_pullback=1"
        in output
    )


def test_missing_pullback_context_is_likely_for_early_pullback_reports_case(
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
                "reason",
                None,
                None,
                None,
                None,
                "FRESH_BULLISH_SIGNAL",
                "OK",
                None,
                None,
                "WATCH",
                0,
                "BOS_UP",
                None,
                5.0,
                2.0,
                1,
                None,
                0,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, "BOS_UP", None, 2.0)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
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
                "action": "WATCH",
                "pullback_validity": "INSUFFICIENT_DATA",
                "entry_readiness": "INSUFFICIENT_DATA",
                "candidate_priority_label": "",
            }
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
    assert "missing_input_diagnosis;AAA;MISSING_PULLBACK_CONTEXT;LIKELY;" in output
    assert "hypothesis_summary;ENRICHMENT_LACKS_PULLBACK_CONTEXT;LIKELY;" in output


def test_source_fields_exist_but_not_mapped_is_likely_when_source_has_pullback_signal(
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
                "reason",
                None,
                None,
                None,
                None,
                None,
                "OK",
                None,
                None,
                "WATCH",
                0,
                None,
                None,
                None,
                1.0,
                None,
                None,
                0,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 1, 0, 2, None, None, 1.0)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "VALID_PULLBACK",
                "entry_readiness": "READY_TO_WATCH",
                "candidate_priority_label": "P1_READY_TO_WATCH",
            }
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "INSUFFICIENT_DATA",
                "entry_readiness": "INSUFFICIENT_DATA",
                "candidate_priority_label": "",
            }
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
        "hypothesis_summary;SOURCE_FIELDS_EXIST_BUT_NOT_MAPPED;LIKELY;"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_pullback_readiness_parity_diagnosis.source_fields_exist_but_not_mapped=1"
        in output
    )


def test_missing_structure_override_is_likely_for_structure_blocked_case(
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
                "reason",
                None,
                None,
                None,
                None,
                "FRESH_BULLISH_SIGNAL",
                "OK",
                None,
                None,
                "WATCH",
                0,
                None,
                None,
                4.0,
                0.5,
                1,
                None,
                0,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, None, None, 0.5)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "STRUCTURE_BLOCKED_PULLBACK",
                "entry_readiness": "NOT_READY",
                "candidate_priority_label": "P5_NOT_READY",
            }
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "INSUFFICIENT_DATA",
                "entry_readiness": "INSUFFICIENT_DATA",
                "candidate_priority_label": "",
            }
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
    assert "missing_input_diagnosis;AAA;MISSING_STRUCTURE_OVERRIDE;LIKELY;" in output
    assert "hypothesis_summary;ENRICHMENT_LACKS_PULLBACK_BLOCKER_CONTEXT;LIKELY;" in output


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
                "reason",
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
                "WATCH",
                0,
                None,
                None,
                None,
                None,
                None,
                None,
                None,
            )
        ],
    )
    _insert_source_rows(
        analysis_db,
        [("2026-05-22", "DC_TAXONOMY_FULL_V1", "AAA", 0, 0, 0, None, None, None)],
    )
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "NO_PULLBACK",
                "entry_readiness": "NOT_READY",
                "candidate_priority_label": "P5_NOT_READY",
            }
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "INSUFFICIENT_DATA",
                "entry_readiness": "INSUFFICIENT_DATA",
                "candidate_priority_label": "",
            }
        ]
    )
    with sqlite3.connect(analysis_db) as conn:
        before_enrichment = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
        before_source = conn.execute(
            "SELECT COUNT(*) FROM dc_ticker_swing_signal_daily"
        ).fetchone()[0]

    exit_code, _output, _error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
    )

    assert exit_code == 0
    with sqlite3.connect(analysis_db) as conn:
        after_enrichment = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
        after_source = conn.execute(
            "SELECT COUNT(*) FROM dc_ticker_swing_signal_daily"
        ).fetchone()[0]
    assert after_enrichment == before_enrichment
    assert after_source == before_source
