from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.run_datacenter_dashboard_pullback_field_flow_diagnosis import main


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE dc_dashboard_ticker_enrichment_daily (
                signal_date TEXT NOT NULL,
                taxonomy_version TEXT NOT NULL,
                ticker TEXT NOT NULL,
                pullback_validity TEXT,
                pullback_reason TEXT,
                entry_readiness TEXT,
                entry_readiness_reason TEXT,
                candidate_priority INTEGER,
                candidate_priority_label TEXT,
                candidate_priority_reason TEXT
            )
            """
        )


def _insert_analysis_rows(path: Path, rows: list[tuple[object, ...]]) -> None:
    with sqlite3.connect(path) as conn:
        conn.executemany(
            """
            INSERT INTO dc_dashboard_ticker_enrichment_daily (
                signal_date, taxonomy_version, ticker, pullback_validity, pullback_reason,
                entry_readiness, entry_readiness_reason, candidate_priority,
                candidate_priority_label, candidate_priority_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
    dashboard_snapshot,
    json_path: Path | None = None,
    adapter_decisions: list[object] | None = None,
):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        return dashboard_snapshot

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_field_flow_diagnosis.load_dashboard_snapshot",
        _fake_load_dashboard_snapshot,
    )
    if adapter_decisions is not None:
        monkeypatch.setattr(
            "dev_tools.run_datacenter_dashboard_pullback_field_flow_diagnosis.build_decisions_from_ticker_enrichment_rows",
            lambda rows: SimpleNamespace(decisions=adapter_decisions),
        )

    argv = [
        "--analysis-db",
        str(analysis_db),
        "--enrichment-dashboard-db",
        "/tmp/enrichment.db",
        "--enrichment-run-id",
        "ENRICH_RUN",
        "--ecosystem-code",
        "DATACENTER",
        "--report-date",
        "2026-05-22",
        "--max-examples",
        "100",
    ]
    if json_path is not None:
        argv.extend(["--enrichment-json", str(json_path)])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_analysis_values_present_but_dashboard_missing_is_likely(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_analysis_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "NO_PULLBACK",
                "NO_PULLBACK_CONTEXT",
                "NOT_READY",
                "NO_PULLBACK",
                5,
                "P5_NOT_READY",
                "NOT_READY",
            )
        ],
    )
    dashboard_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
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
        dashboard_snapshot=dashboard_snapshot,
    )

    assert exit_code == 0
    assert error == ""
    assert (
        "mapping_gap_hypothesis;ANALYSIS_VALUES_PRESENT_BUT_DASHBOARD_MISSING;LIKELY;"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.analysis_semantic_pullback=1"
        in output
    )
    assert (
        "SUMMARY datacenter_dashboard_pullback_field_flow_diagnosis.dashboard_insufficient_pullback=1"
        in output
    )


def test_json_values_present_but_dashboard_missing_is_likely(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    json_path = tmp_path / "enrichment.json"
    _create_analysis_db(analysis_db)
    _insert_analysis_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "INSUFFICIENT_DATA",
                "",
                "INSUFFICIENT_DATA",
                "",
                None,
                "",
                "",
            )
        ],
    )
    json_path.write_text(
        json.dumps(
            {
                "tickers": [
                    {
                        "ticker": "AAA",
                        "pullback_validity": "NO_PULLBACK",
                        "entry_readiness": "NOT_READY",
                        "candidate_priority_label": "P5_NOT_READY",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    dashboard_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
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
        dashboard_snapshot=dashboard_snapshot,
        json_path=json_path,
    )

    assert exit_code == 0
    assert (
        "mapping_gap_hypothesis;JSON_VALUES_PRESENT_BUT_DASHBOARD_MISSING;LIKELY;"
        in output
    )
    assert "field_distribution;json;pullback_validity;NO_PULLBACK;1" in output


def test_adapter_values_present_but_not_persisted_is_likely(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_analysis_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "INSUFFICIENT_DATA",
                "",
                "INSUFFICIENT_DATA",
                "",
                None,
                "",
                "",
            )
        ],
    )
    dashboard_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "pullback_validity": "INSUFFICIENT_DATA",
                "entry_readiness": "INSUFFICIENT_DATA",
                "candidate_priority_label": "",
            }
        ]
    )
    adapter_decisions = [
        SimpleNamespace(
            ticker="AAA",
            pullback_validity="NO_PULLBACK",
            pullback_reason="NO_PULLBACK_CONTEXT",
            entry_readiness="NOT_READY",
            entry_readiness_reason="NO_PULLBACK",
            candidate_priority=5,
            candidate_priority_label="P5_NOT_READY",
            candidate_priority_reason="NOT_READY",
        )
    ]

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        dashboard_snapshot=dashboard_snapshot,
        adapter_decisions=adapter_decisions,
    )

    assert exit_code == 0
    assert (
        "mapping_gap_hypothesis;ADAPTER_VALUES_PRESENT_BUT_NOT_PERSISTED;LIKELY;"
        in output
    )
    assert (
        "mapping_gap_hypothesis;ANALYSIS_VALUES_NOT_UPDATED_AFTER_ADAPTER_FIX;LIKELY;"
        in output
    )


def test_field_distributions_count_values_correctly(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_analysis_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "NO_PULLBACK",
                "NO_PULLBACK_CONTEXT",
                "NOT_READY",
                "NO_PULLBACK",
                5,
                "P5_NOT_READY",
                "NOT_READY",
            ),
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "BBB",
                "EARLY_PULLBACK",
                "WAIT_FOR_BULLISH_CONFIRMATION",
                "EARLY_MONITOR",
                "WAIT_FOR_BULLISH_CONFIRMATION",
                4,
                "P4_EARLY_MONITOR",
                "EARLY_PULLBACK_WAIT_FOR_CONFIRMATION",
            ),
        ],
    )
    dashboard_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "pullback_validity": "INSUFFICIENT_DATA",
                "entry_readiness": "INSUFFICIENT_DATA",
                "candidate_priority_label": "",
            },
            {
                "ticker": "BBB",
                "pullback_validity": "INSUFFICIENT_DATA",
                "entry_readiness": "INSUFFICIENT_DATA",
                "candidate_priority_label": "",
            },
        ]
    )

    exit_code, output, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        dashboard_snapshot=dashboard_snapshot,
    )

    assert exit_code == 0
    assert "field_distribution;analysis;pullback_validity;EARLY_PULLBACK;1" in output
    assert "field_distribution;analysis;pullback_validity;NO_PULLBACK;1" in output
    assert "field_distribution;dashboard;pullback_validity;INSUFFICIENT_DATA;2" in output


def test_cli_is_read_only_for_analysis_db(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    _insert_analysis_rows(
        analysis_db,
        [
            (
                "2026-05-22",
                "DC_TAXONOMY_FULL_V1",
                "AAA",
                "NO_PULLBACK",
                "NO_PULLBACK_CONTEXT",
                "NOT_READY",
                "NO_PULLBACK",
                5,
                "P5_NOT_READY",
                "NOT_READY",
            )
        ],
    )
    dashboard_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "pullback_validity": "INSUFFICIENT_DATA",
                "entry_readiness": "INSUFFICIENT_DATA",
                "candidate_priority_label": "",
            }
        ]
    )
    with sqlite3.connect(analysis_db) as conn:
        before = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]

    exit_code, _output, _error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        dashboard_snapshot=dashboard_snapshot,
    )

    assert exit_code == 0
    with sqlite3.connect(analysis_db) as conn:
        after = conn.execute(
            "SELECT COUNT(*) FROM dc_dashboard_ticker_enrichment_daily"
        ).fetchone()[0]
    assert after == before
