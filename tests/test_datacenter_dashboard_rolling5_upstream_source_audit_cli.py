from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit import main


def _snapshot(tickers: list[dict[str, object]]):
    return SimpleNamespace(tickers=tickers, decision_trace=[], run=None, action_summary=[])


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO marker (value) VALUES ('ok')")


def _run_cli(
    capsys,
    monkeypatch,
    *,
    analysis_db: Path,
    reports_snapshot,
    tickers: str | None = None,
    taxonomy_version: str | None = None,
):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        return reports_snapshot

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit.load_dashboard_snapshot",
        _fake_load_dashboard_snapshot,
    )

    argv = [
        "--analysis-db",
        str(analysis_db),
        "--reports-dashboard-db",
        "/tmp/reports.db",
        "--reports-run-id",
        "REPORTS_RUN",
        "--ecosystem-code",
        "DATACENTER",
        "--report-date",
        "2026-05-22",
        "--max-examples",
        "100",
    ]
    if tickers:
        argv.extend(["--tickers", tickers])
    if taxonomy_version is not None:
        argv.extend(["--taxonomy-version", taxonomy_version])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err


def test_builder_callable_success_path_with_monkeypatched_rows(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "NO_PULLBACK"},
        ]
    )

    def _fake_extract_upstream_source_rows(*, analysis_db, report_date, taxonomy_version):
        assert taxonomy_version == "DC_TAXONOMY_FULL_V1"
        return (
            1,
            "_build_rolling_5_pullback_rows",
            "",
            [
                {
                    "ticker": "AAA",
                    "rolling_5_pullback_state": "PULLBACK_CANDIDATE",
                    "pullback_days": 2,
                    "fast_ema10_pullback_days": 1,
                    "conservative_ema20_pullback_days": 1,
                    "latest_bos_event_type": "BOS_UP",
                    "latest_bos_freshness": "FRESH",
                    "latest_reset_reason": "",
                    "latest_reset_freshness": "",
                    "latest_bullish_relevance_class": "RELEVANT",
                    "latest_bearish_relevance_class": "",
                    "primary_reason": "CONFIRMED_EMA20_PULLBACK_CONTEXT",
                    "blocking_reason": "",
                    "next_action": "REVIEW_FOR_DAILY_TRIGGER",
                },
                {
                    "ticker": "BBB",
                    "rolling_5_pullback_state": "NO_PULLBACK",
                    "pullback_days": 0,
                    "fast_ema10_pullback_days": 0,
                    "conservative_ema20_pullback_days": 0,
                    "latest_bos_event_type": "",
                    "latest_bos_freshness": "",
                    "latest_reset_reason": "",
                    "latest_reset_freshness": "",
                    "latest_bullish_relevance_class": "",
                    "latest_bearish_relevance_class": "",
                    "primary_reason": "NO_MEANINGFUL_PULLBACK_EVIDENCE",
                    "blocking_reason": "",
                    "next_action": "NONE",
                },
            ],
            [],
        )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit._extract_upstream_source_rows",
        _fake_extract_upstream_source_rows,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit._build_v2_baseline_map",
        lambda **kwargs: {"AAA": "EARLY_PULLBACK", "BBB": "NO_PULLBACK"},
    )

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert exit_code == 0
    assert error == ""
    assert "upstream_builder_status;taxonomy_version;DC_TAXONOMY_FULL_V1;" in output
    assert "upstream_builder_status;builder_callable;1;" in output
    assert "upstream_builder_status;rows_extracted;2;" in output
    assert "upstream_field_coverage;rolling_5_pullback_state;1;2" in output
    assert "SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.builder_callable=1" in output
    assert (
        "SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.taxonomy_version=DC_TAXONOMY_FULL_V1"
        in output
    )


def test_builder_not_callable_path_reports_needs_helper_extraction(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    def _boom(*, analysis_db, report_date, taxonomy_version):
        assert taxonomy_version is None
        raise RuntimeError("builder requires broader report object")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit._extract_upstream_source_rows",
        _boom,
    )

    exit_code, output, error = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert error == ""
    assert "upstream_builder_status;builder_callable;0;builder requires broader report object" in output
    assert "mapping_recommendation;NEEDS_HELPER_EXTRACTION;LIKELY;" in output
    assert "SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.needs_helper_extraction=1" in output
    assert "SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.taxonomy_version=" in output


def test_matrix_compares_upstream_rows_to_reports_pullback_validity(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [
            {"ticker": "AAA", "pullback_validity": "VALID_PULLBACK"},
            {"ticker": "BBB", "pullback_validity": "STRUCTURE_BLOCKED_PULLBACK"},
        ]
    )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit._extract_upstream_source_rows",
        lambda **kwargs: (
            1,
            "_build_rolling_5_pullback_rows",
            "",
            [
                {
                    "ticker": "AAA",
                    "rolling_5_pullback_state": "PULLBACK_CANDIDATE",
                    "pullback_days": 2,
                    "fast_ema10_pullback_days": 1,
                    "conservative_ema20_pullback_days": 1,
                    "latest_bos_event_type": "BOS_UP",
                    "latest_bos_freshness": "FRESH",
                    "latest_reset_reason": "",
                    "latest_reset_freshness": "",
                    "latest_bullish_relevance_class": "RELEVANT",
                    "latest_bearish_relevance_class": "",
                    "primary_reason": "CONFIRMED_EMA20_PULLBACK_CONTEXT",
                    "blocking_reason": "",
                    "next_action": "REVIEW_FOR_DAILY_TRIGGER",
                },
                {
                    "ticker": "BBB",
                    "rolling_5_pullback_state": "FAILED_PULLBACK",
                    "pullback_days": 1,
                    "fast_ema10_pullback_days": 1,
                    "conservative_ema20_pullback_days": 0,
                    "latest_bos_event_type": "BOS_DOWN",
                    "latest_bos_freshness": "FRESH",
                    "latest_reset_reason": "DOUBLE_BOS_DOWN",
                    "latest_reset_freshness": "FRESH",
                    "latest_bullish_relevance_class": "",
                    "latest_bearish_relevance_class": "RELEVANT",
                    "primary_reason": "PULLBACK_SETUP_BLOCKED",
                    "blocking_reason": "recent_bos_down",
                    "next_action": "REMOVE_FROM_PULLBACK_LIST",
                },
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit._build_v2_baseline_map",
        lambda **kwargs: {"AAA": "NO_PULLBACK", "BBB": "NO_PULLBACK"},
    )

    exit_code, output, _ = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    assert exit_code == 0
    assert "upstream_vs_reports_matrix;VALID_PULLBACK;PULLBACK_CANDIDATE;1" in output
    assert "upstream_vs_reports_matrix;STRUCTURE_BLOCKED_PULLBACK;FAILED_PULLBACK;1" in output
    assert "mapping_recommendation;UPSTREAM_ROWS_MATCH_REPORTS_BETTER_THAN_V2;LIKELY;" in output


def test_cli_is_read_only_for_analysis_db(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit._extract_upstream_source_rows",
        lambda **kwargs: (
            1,
            "_build_rolling_5_pullback_rows",
            "",
            [
                {
                    "ticker": "AAA",
                    "rolling_5_pullback_state": "NO_PULLBACK",
                    "pullback_days": 0,
                    "fast_ema10_pullback_days": 0,
                    "conservative_ema20_pullback_days": 0,
                    "latest_bos_event_type": "",
                    "latest_bos_freshness": "",
                    "latest_reset_reason": "",
                    "latest_reset_freshness": "",
                    "latest_bullish_relevance_class": "",
                    "latest_bearish_relevance_class": "",
                    "primary_reason": "NO_MEANINGFUL_PULLBACK_EVIDENCE",
                    "blocking_reason": "",
                    "next_action": "NONE",
                },
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit._build_v2_baseline_map",
        lambda **kwargs: {"AAA": "NO_PULLBACK"},
    )

    with sqlite3.connect(analysis_db) as conn:
        before_count = int(conn.execute("SELECT COUNT(*) FROM marker").fetchone()[0])

    exit_code, output, error = _run_cli(capsys, monkeypatch, analysis_db=analysis_db, reports_snapshot=reports_snapshot)

    with sqlite3.connect(analysis_db) as conn:
        after_count = int(conn.execute("SELECT COUNT(*) FROM marker").fetchone()[0])

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.status=OK" in output
    assert before_count == after_count


def test_cli_passes_taxonomy_version_to_builder_when_supplied(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])
    captured = {}

    def _fake_extract_upstream_source_rows(*, analysis_db, report_date, taxonomy_version):
        captured["taxonomy_version"] = taxonomy_version
        return (1, "_build_rolling_5_pullback_rows", "", [], [])

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit._extract_upstream_source_rows",
        _fake_extract_upstream_source_rows,
    )

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        taxonomy_version="DC_TAXONOMY_FULL_V1",
    )

    assert exit_code == 0
    assert error == ""
    assert captured["taxonomy_version"] == "DC_TAXONOMY_FULL_V1"
    assert "upstream_builder_status;taxonomy_version;DC_TAXONOMY_FULL_V1;" in output


def test_ambiguity_without_taxonomy_version_preserves_diagnostic_path(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot([{"ticker": "AAA", "pullback_validity": "NO_PULLBACK"}])

    def _boom(*, analysis_db, report_date, taxonomy_version):
        assert taxonomy_version is None
        raise ValueError(
            "Multiple taxonomy_version values exist for the selected weekly window and signal_version; pass --taxonomy-version explicitly"
        )

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_rolling5_upstream_source_audit._extract_upstream_source_rows",
        _boom,
    )

    exit_code, output, error = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
    )

    assert exit_code == 0
    assert error == ""
    assert "upstream_builder_status;builder_callable;0;Multiple taxonomy_version values exist" in output
    assert "mapping_recommendation;NEEDS_HELPER_EXTRACTION;LIKELY;" in output
    assert "SUMMARY datacenter_dashboard_rolling5_upstream_source_audit.needs_helper_extraction=1" in output
