from __future__ import annotations

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from dev_tools.datacenter_dashboard_parser import DatacenterDashboardParseResult, DatacenterDashboardRow
from dev_tools.run_datacenter_dashboard_pullback_decision_trace_parity import main


def _snapshot(tickers: list[dict[str, object]]):
    return SimpleNamespace(tickers=tickers, decision_trace=[], run=None, action_summary=[])


def _create_analysis_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE marker (id INTEGER PRIMARY KEY, value TEXT)")
        conn.execute("INSERT INTO marker (value) VALUES ('ok')")


def _row(
    *,
    ticker: str,
    horizon: str,
    raw_status: str | None = None,
    raw_action: str | None = None,
    reason: str | None = None,
    blocking_reasons: str | None = None,
    ma_break_status: str | None = None,
    freshness_status: str | None = None,
    latest_bos_event_type: str | None = None,
    latest_reset_reason: str | None = None,
    raw_fields: dict[str, str] | None = None,
) -> DatacenterDashboardRow:
    return DatacenterDashboardRow(
        ticker=ticker,
        horizon=horizon,
        source_file=f"/tmp/{ticker}_{horizon}.md",
        section="watchlist",
        row_kind="ticker",
        raw_action=raw_action,
        raw_status=raw_status,
        reason=reason,
        trend_state=None,
        latest_structure_label=None,
        latest_bos_event_type=latest_bos_event_type,
        latest_reset_reason=latest_reset_reason,
        distance_to_ema20=None,
        high_exit_risk_days_count=None,
        blocking_reasons=blocking_reasons,
        ma_break_status=ma_break_status,
        ema20_break_confirmed=None,
        sma50_break_confirmed=None,
        close_below_ema20=None,
        close_below_sma50=None,
        consecutive_closes_below_ema20=None,
        consecutive_closes_below_sma50=None,
        ema20_break_pct=None,
        sma50_break_pct=None,
        freshness_status=freshness_status,
        structure_warning_overrides_bullish_signal=None,
        latest_bullish_signal_age_td=None,
        latest_bearish_signal_age_td=None,
        latest_bos_up_age_td=None,
        latest_bos_down_age_td=None,
        latest_reset_age_td=None,
        raw_fields=raw_fields or {},
    )


def _run_cli(
    capsys,
    monkeypatch,
    *,
    analysis_db: Path,
    reports_snapshot,
    enrichment_snapshot,
    reports_rows: list[DatacenterDashboardRow],
    enrichment_source_rows: list[dict[str, object]],
    enrichment_adapter_rows: list[DatacenterDashboardRow],
    reports_decision_result,
    enrichment_decision_result,
    tickers: str | None = None,
):
    def _fake_load_dashboard_snapshot(*, dashboard_db, ecosystem_code, report_date, run_id):
        if dashboard_db.endswith("reports.db"):
            return reports_snapshot
        if dashboard_db.endswith("enrichment.db"):
            return enrichment_snapshot
        raise AssertionError(f"unexpected dashboard_db: {dashboard_db}")

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_decision_trace_parity.load_dashboard_snapshot",
        _fake_load_dashboard_snapshot,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_decision_trace_parity.discover_datacenter_dashboard_status",
        lambda reports_dir, report_date=None: SimpleNamespace(
            reports=[SimpleNamespace(horizon="rolling 5d", path="/tmp/report.md")]
        ),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_decision_trace_parity.parse_datacenter_dashboard_file",
        lambda path, horizon: DatacenterDashboardParseResult(rows=reports_rows, warnings=[]),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_decision_trace_parity._taxonomy_version_for_report_date",
        lambda analysis_db, report_date: "DC_TAXONOMY_FULL_V1",
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_decision_trace_parity.load_ticker_enrichment_rows",
        lambda analysis_db, report_date, taxonomy_version: enrichment_source_rows,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_decision_trace_parity.build_dashboard_rows_from_ticker_enrichment_rows",
        lambda rows: enrichment_adapter_rows,
    )

    build_calls = {"count": 0}

    def _fake_build_reports_decisions(rows):
        build_calls["count"] += 1
        return reports_decision_result

    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_decision_trace_parity.build_datacenter_ticker_decisions",
        _fake_build_reports_decisions,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_pullback_decision_trace_parity.build_decisions_from_ticker_enrichment_rows",
        lambda rows: enrichment_decision_result,
    )

    argv = [
        "--reports-dir",
        "/tmp/reports",
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
    if tickers is not None:
        argv.extend(["--tickers", tickers])
    exit_code = main(argv)
    captured = capsys.readouterr()
    return exit_code, captured.out, captured.err, build_calls["count"]


def _decision(
    *,
    ticker: str,
    pullback_validity: str,
    pullback_reason: str,
    entry_readiness: str,
    entry_readiness_reason: str,
    candidate_priority: int,
    candidate_priority_label: str,
    candidate_priority_reason: str,
    action: str = "WATCH",
    primary_reason: str = "reason",
    reasons: list[str] | None = None,
    blocking_reasons: list[str] | None = None,
):
    return SimpleNamespace(
        ticker=ticker,
        action=action,
        primary_reason=primary_reason,
        pullback_validity=pullback_validity,
        pullback_reason=pullback_reason,
        entry_readiness=entry_readiness,
        entry_readiness_reason=entry_readiness_reason,
        candidate_priority=candidate_priority,
        candidate_priority_label=candidate_priority_label,
        candidate_priority_reason=candidate_priority_reason,
        reasons=reasons or [pullback_reason],
        blocking_reasons=blocking_reasons or [],
    )


def test_detects_factual_mismatch_and_marks_switch_unsafe(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "VALID_PULLBACK",
                "entry_readiness": "READY_TO_WATCH",
                "candidate_priority": 1,
                "candidate_priority_label": "P1_READY_TO_WATCH",
                "primary_reason": "CONFIRMED_EMA20_PULLBACK_CONTEXT",
            }
        ]
    )
    enrichment_snapshot = _snapshot(
        [
            {
                "ticker": "AAA",
                "action": "WATCH",
                "pullback_validity": "NO_PULLBACK",
                "entry_readiness": "NOT_READY",
                "candidate_priority": 5,
                "candidate_priority_label": "P5_NOT_READY",
                "primary_reason": "NO_MEANINGFUL_PULLBACK_EVIDENCE",
            }
        ]
    )
    reports_rows = [
        _row(
            ticker="AAA",
            horizon="rolling 5d",
            raw_status="PULLBACK_CANDIDATE",
            reason="CONFIRMED_EMA20_PULLBACK_CONTEXT",
            raw_fields={"pullback_days": "3"},
        )
    ]
    enrichment_adapter_rows = [
        _row(
            ticker="AAA",
            horizon="rolling 5d",
            raw_status="NO_PULLBACK",
            reason="NO_MEANINGFUL_PULLBACK_EVIDENCE",
        )
    ]
    reports_decisions = SimpleNamespace(
        decisions=[
            _decision(
                ticker="AAA",
                pullback_validity="VALID_PULLBACK",
                pullback_reason="PULLBACK_CONFIRMED",
                entry_readiness="READY_TO_WATCH",
                entry_readiness_reason="READY_ACTION",
                candidate_priority=1,
                candidate_priority_label="P1_READY_TO_WATCH",
                candidate_priority_reason="READINESS_MAPPING",
            )
        ]
    )
    enrichment_decisions = SimpleNamespace(
        decisions=[
            _decision(
                ticker="AAA",
                pullback_validity="NO_PULLBACK",
                pullback_reason="NO_PULLBACK_CONTEXT",
                entry_readiness="NOT_READY",
                entry_readiness_reason="NOT_ACTIONABLE",
                candidate_priority=5,
                candidate_priority_label="P5_NOT_READY",
                candidate_priority_reason="READINESS_MAPPING",
            )
        ]
    )

    exit_code, output, error, build_calls = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_source_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=enrichment_adapter_rows,
        reports_decision_result=reports_decisions,
        enrichment_decision_result=enrichment_decisions,
    )

    assert exit_code == 0
    assert error == ""
    assert build_calls == 1
    assert "factual_parity_counts;pullback_validity;0;1;0;0" in output
    assert (
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.final_field_parity_not_safe_for_switch=1"
        in output
    )


def test_detects_token_under_different_name(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "EARLY_MONITOR", "candidate_priority_label": "P4_EARLY_MONITOR"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "EARLY_MONITOR", "candidate_priority_label": "P4_EARLY_MONITOR"}]
    )
    reports_rows = [_row(ticker="AAA", horizon="rolling 5d", raw_status="PULLBACK_CANDIDATE")]
    enrichment_adapter_rows = [
        _row(
            ticker="AAA",
            horizon="rolling 5d",
            raw_status=None,
            raw_fields={"rolling_5d_status": "PULLBACK_CANDIDATE"},
        )
    ]
    decisions = SimpleNamespace(
        decisions=[
            _decision(
                ticker="AAA",
                pullback_validity="VALID_PULLBACK",
                pullback_reason="PULLBACK_CONFIRMED",
                entry_readiness="EARLY_MONITOR",
                entry_readiness_reason="EARLY_ACTION",
                candidate_priority=4,
                candidate_priority_label="P4_EARLY_MONITOR",
                candidate_priority_reason="READINESS_MAPPING",
            )
        ]
    )

    exit_code, output, _, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_source_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=enrichment_adapter_rows,
        reports_decision_result=decisions,
        enrichment_decision_result=decisions,
        tickers="AAA",
    )

    assert exit_code == 0
    assert "token_field_presence_delta;AAA;pullback_candidate;1;1;pullback_candidate;pullback_candidate;DIFFERENT_FIELD_NAME" in output
    assert "hypothesis_summary;ENRICHMENT_HAS_PULLBACK_CONTEXT_UNDER_DIFFERENT_NAME;LIKELY;" in output
    assert (
        "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.adapter_shape_fix_recommended=1"
        in output
    )


def test_detects_missing_freshness_context(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "EARLY_PULLBACK", "entry_readiness": "EARLY_MONITOR", "candidate_priority_label": "P4_EARLY_MONITOR"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "NO_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"}]
    )
    reports_rows = [
        _row(
            ticker="AAA",
            horizon="daily",
            freshness_status="FRESH_BULLISH_SIGNAL",
            raw_fields={"latest_bos_freshness": "FRESH"},
        )
    ]
    enrichment_adapter_rows = [_row(ticker="AAA", horizon="daily")]
    reports_decisions = SimpleNamespace(
        decisions=[
            _decision(
                ticker="AAA",
                pullback_validity="EARLY_PULLBACK",
                pullback_reason="EARLY_PULLBACK_CONTEXT",
                entry_readiness="EARLY_MONITOR",
                entry_readiness_reason="EARLY_ACTION",
                candidate_priority=4,
                candidate_priority_label="P4_EARLY_MONITOR",
                candidate_priority_reason="READINESS_MAPPING",
            )
        ]
    )
    enrichment_decisions = SimpleNamespace(
        decisions=[
            _decision(
                ticker="AAA",
                pullback_validity="NO_PULLBACK",
                pullback_reason="NO_PULLBACK_CONTEXT",
                entry_readiness="NOT_READY",
                entry_readiness_reason="NOT_ACTIONABLE",
                candidate_priority=5,
                candidate_priority_label="P5_NOT_READY",
                candidate_priority_reason="READINESS_MAPPING",
            )
        ]
    )

    exit_code, output, _, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_source_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=enrichment_adapter_rows,
        reports_decision_result=reports_decisions,
        enrichment_decision_result=enrichment_decisions,
    )

    assert exit_code == 0
    assert "hypothesis_summary;REPORTS_HAS_FRESHNESS_CONTEXT_ENRICHMENT_LACKS;LIKELY;" in output


def test_detects_acute_row_context_difference(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "STRUCTURE_BLOCKED_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "NO_PULLBACK", "entry_readiness": "NOT_READY", "candidate_priority_label": "P5_NOT_READY"}]
    )
    reports_rows = [_row(ticker="AAA", horizon="daily", ma_break_status="EMA20_BREAK_CONFIRMED")]
    enrichment_adapter_rows = [_row(ticker="AAA", horizon="daily")]
    reports_decisions = SimpleNamespace(
        decisions=[
            _decision(
                ticker="AAA",
                pullback_validity="STRUCTURE_BLOCKED_PULLBACK",
                pullback_reason="ACUTE_BREAK",
                entry_readiness="NOT_READY",
                entry_readiness_reason="BLOCKED",
                candidate_priority=5,
                candidate_priority_label="P5_NOT_READY",
                candidate_priority_reason="READINESS_MAPPING",
                blocking_reasons=["ma_break"],
            )
        ]
    )
    enrichment_decisions = SimpleNamespace(
        decisions=[
            _decision(
                ticker="AAA",
                pullback_validity="NO_PULLBACK",
                pullback_reason="NO_PULLBACK_CONTEXT",
                entry_readiness="NOT_READY",
                entry_readiness_reason="NOT_ACTIONABLE",
                candidate_priority=5,
                candidate_priority_label="P5_NOT_READY",
                candidate_priority_reason="READINESS_MAPPING",
            )
        ]
    )

    exit_code, output, _, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=reports_rows,
        enrichment_source_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=enrichment_adapter_rows,
        reports_decision_result=reports_decisions,
        enrichment_decision_result=enrichment_decisions,
    )

    assert exit_code == 0
    assert "hypothesis_summary;ACUTE_ROW_CONTEXT_DIFFERS;LIKELY;" in output


def test_cli_is_read_only_for_analysis_db(tmp_path, monkeypatch, capsys):
    analysis_db = tmp_path / "analysis.db"
    _create_analysis_db(analysis_db)
    reports_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"}]
    )
    enrichment_snapshot = _snapshot(
        [{"ticker": "AAA", "pullback_validity": "VALID_PULLBACK", "entry_readiness": "READY_TO_WATCH", "candidate_priority_label": "P1_READY_TO_WATCH"}]
    )
    rows = [_row(ticker="AAA", horizon="rolling 5d", raw_status="PULLBACK_CANDIDATE")]
    decisions = SimpleNamespace(
        decisions=[
            _decision(
                ticker="AAA",
                pullback_validity="VALID_PULLBACK",
                pullback_reason="PULLBACK_CONFIRMED",
                entry_readiness="READY_TO_WATCH",
                entry_readiness_reason="READY_ACTION",
                candidate_priority=1,
                candidate_priority_label="P1_READY_TO_WATCH",
                candidate_priority_reason="READINESS_MAPPING",
            )
        ]
    )

    exit_code, output, error, _ = _run_cli(
        capsys,
        monkeypatch,
        analysis_db=analysis_db,
        reports_snapshot=reports_snapshot,
        enrichment_snapshot=enrichment_snapshot,
        reports_rows=rows,
        enrichment_source_rows=[{"ticker": "AAA"}],
        enrichment_adapter_rows=rows,
        reports_decision_result=decisions,
        enrichment_decision_result=decisions,
    )

    assert exit_code == 0
    assert error == ""
    assert "SUMMARY datacenter_dashboard_pullback_decision_trace_parity.status=OK" in output
    with sqlite3.connect(analysis_db) as conn:
        value = conn.execute("SELECT value FROM marker").fetchone()[0]
    assert value == "ok"
