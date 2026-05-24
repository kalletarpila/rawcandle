from __future__ import annotations

from pathlib import Path

import pytest

from dev_tools.datacenter_dashboard_decisions import (
    DatacenterDecisionBatchResult,
    DatacenterDecisionTrace,
    DatacenterTickerDecision,
)
from dev_tools.datacenter_dashboard_inspector import DatacenterTickerInspectorView
from dev_tools.datacenter_dashboard_parser import (
    DatacenterDashboardBatchParseResult,
    DatacenterDashboardReportParseSummary,
    DatacenterDashboardRow,
)
from dev_tools.datacenter_dashboard_support import (
    DatacenterDashboardStatus,
    DatacenterReportStatus,
)
from dev_tools.run_datacenter_dashboard_html import (
    build_parser,
    generate_dashboard_html,
    main,
)


def _fake_dashboard_status(tmp_path: Path) -> DatacenterDashboardStatus:
    return DatacenterDashboardStatus(
        overall_status="READY",
        reports=[
            DatacenterReportStatus(
                horizon="rolling 30d",
                status="OK",
                path=str(tmp_path / "rolling30.csv"),
                modified_at="2026-05-25T00:00:00",
            ),
            DatacenterReportStatus(
                horizon="rolling 5d",
                status="OK",
                path=str(tmp_path / "rolling5.csv"),
                modified_at="2026-05-25T00:00:00",
            ),
            DatacenterReportStatus(
                horizon="rolling 2d",
                status="OK",
                path=str(tmp_path / "rolling2.csv"),
                modified_at="2026-05-25T00:00:00",
            ),
            DatacenterReportStatus(
                horizon="daily",
                status="OK",
                path=str(tmp_path / "daily.csv"),
                modified_at="2026-05-25T00:00:00",
            ),
        ],
    )


def _fake_parse_batch(tmp_path: Path) -> DatacenterDashboardBatchParseResult:
    return DatacenterDashboardBatchParseResult(
        reports=[
            DatacenterDashboardReportParseSummary(
                horizon="rolling 30d",
                source_file=str(tmp_path / "rolling30.csv"),
                row_count=1,
                warning_count=0,
            ),
            DatacenterDashboardReportParseSummary(
                horizon="rolling 5d",
                source_file=str(tmp_path / "rolling5.csv"),
                row_count=1,
                warning_count=0,
            ),
            DatacenterDashboardReportParseSummary(
                horizon="rolling 2d",
                source_file=str(tmp_path / "rolling2.csv"),
                row_count=1,
                warning_count=0,
            ),
            DatacenterDashboardReportParseSummary(
                horizon="daily",
                source_file=str(tmp_path / "daily.csv"),
                row_count=2,
                warning_count=1,
            ),
        ],
        total_row_count=5,
        total_warning_count=1,
    )


def _fake_rows(path: str, horizon: str) -> list[DatacenterDashboardRow]:
    if horizon == "daily":
        return [
            DatacenterDashboardRow(
                ticker="MS&FT",
                horizon=horizon,
                source_file=path,
                section="signals",
                row_kind="row",
                raw_action=None,
                raw_status="BULLISH",
                reason="fresh <entry> & follow-through",
                trend_state="UP",
                latest_structure_label="HL",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                blocking_reasons=None,
                ma_break_status="OK",
                ema20_break_confirmed=0,
                sma50_break_confirmed=0,
                close_below_ema20=0,
                close_below_sma50=0,
                consecutive_closes_below_ema20=0,
                consecutive_closes_below_sma50=0,
                ema20_break_pct=0.0,
                sma50_break_pct=0.0,
                freshness_status="FRESH_BULLISH_SIGNAL",
                structure_warning_overrides_bullish_signal=0,
                latest_bullish_signal_age_td=1,
                latest_bearish_signal_age_td=None,
                latest_bos_up_age_td=1,
                latest_bos_down_age_td=None,
                latest_reset_age_td=None,
                raw_fields={},
            ),
            DatacenterDashboardRow(
                ticker="NV<DA>",
                horizon=horizon,
                source_file=path,
                section="signals",
                row_kind="row",
                raw_action=None,
                raw_status="SELL",
                reason="close_below_ema20 & risk",
                trend_state="DOWN",
                latest_structure_label="LL",
                latest_bos_event_type="BOS_DOWN",
                latest_reset_reason="RESET",
                distance_to_ema20=None,
                high_exit_risk_days_count=2,
                blocking_reasons=None,
                ma_break_status="EMA20_CONFIRMED_BREAK",
                ema20_break_confirmed=1,
                sma50_break_confirmed=0,
                close_below_ema20=1,
                close_below_sma50=0,
                consecutive_closes_below_ema20=3,
                consecutive_closes_below_sma50=0,
                ema20_break_pct=-0.02,
                sma50_break_pct=0.0,
                freshness_status="STRUCTURE_WARNING_OVERRIDES_BULLISH",
                structure_warning_overrides_bullish_signal=1,
                latest_bullish_signal_age_td=None,
                latest_bearish_signal_age_td=0,
                latest_bos_up_age_td=None,
                latest_bos_down_age_td=0,
                latest_reset_age_td=0,
                raw_fields={},
            ),
        ]
    if horizon == "rolling 5d":
        return [
            DatacenterDashboardRow(
                ticker="AMD",
                horizon=horizon,
                source_file=path,
                section="signals",
                row_kind="row",
                raw_action=None,
                raw_status="PULLBACK_CANDIDATE",
                reason="monitor",
                trend_state="UP",
                latest_structure_label="HL",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                blocking_reasons=None,
                ma_break_status="EMA20_WARNING",
                ema20_break_confirmed=0,
                sma50_break_confirmed=0,
                close_below_ema20=0,
                close_below_sma50=0,
                consecutive_closes_below_ema20=0,
                consecutive_closes_below_sma50=0,
                ema20_break_pct=0.0,
                sma50_break_pct=0.0,
                freshness_status="FRESH_BULLISH_SIGNAL",
                structure_warning_overrides_bullish_signal=0,
                latest_bullish_signal_age_td=3,
                latest_bearish_signal_age_td=None,
                latest_bos_up_age_td=2,
                latest_bos_down_age_td=None,
                latest_reset_age_td=None,
                raw_fields={},
            ),
        ]
    if horizon == "rolling 30d":
        return [
            DatacenterDashboardRow(
                ticker="MS&FT",
                horizon=horizon,
                source_file=path,
                section="context",
                row_kind="row",
                raw_action=None,
                raw_status="BUY_ZONE",
                reason="leader",
                trend_state="UP",
                latest_structure_label="HH",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                blocking_reasons=None,
                ma_break_status=None,
                ema20_break_confirmed=None,
                sma50_break_confirmed=None,
                close_below_ema20=None,
                close_below_sma50=None,
                consecutive_closes_below_ema20=None,
                consecutive_closes_below_sma50=None,
                ema20_break_pct=None,
                sma50_break_pct=None,
                freshness_status=None,
                structure_warning_overrides_bullish_signal=None,
                latest_bullish_signal_age_td=None,
                latest_bearish_signal_age_td=None,
                latest_bos_up_age_td=None,
                latest_bos_down_age_td=None,
                latest_reset_age_td=None,
                raw_fields={},
            ),
        ]
    return []


def _fake_decision_result(tmp_path: Path) -> DatacenterDecisionBatchResult:
    return DatacenterDecisionBatchResult(
        decisions=[
            DatacenterTickerDecision(
                ticker="MS&FT",
                action="WATCH",
                severity="LOW",
                primary_reason="VALID_PULLBACK_WAIT_FOR_ENTRY_CONFIRMATION",
                reasons=[],
                blocking_reasons=[],
                horizons_present=["daily", "rolling 30d"],
                horizon_statuses={"daily": "BULLISH", "rolling 30d": "BUY_ZONE"},
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                trend_state="UP",
                latest_structure_label="HL",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                latest_bullish_signal_age_td=1,
                latest_bearish_signal_age_td=None,
                pullback_validity="VALID_PULLBACK",
                pullback_reason="FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK",
                entry_readiness="READY_TO_WATCH",
                entry_readiness_reason="VALID_PULLBACK_NO_STRONG_RISK_ACTION",
                candidate_priority=1,
                candidate_priority_label="P1_READY_TO_WATCH",
                candidate_priority_reason="READY_TO_WATCH",
                source_files=[str(tmp_path / "daily.csv"), str(tmp_path / "rolling30.csv")],
                decision_trace=[
                    DatacenterDecisionTrace(
                        ticker="MS&FT",
                        action="WATCH",
                        matched_rule="WATCH_VALID_PULLBACK",
                        horizon=None,
                        field_name=None,
                        matched_token="VALID_PULLBACK",
                        matched_value="FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK",
                        source_file=None,
                        section=None,
                        row_kind=None,
                    )
                ],
            ),
            DatacenterTickerDecision(
                ticker="AMD",
                action="WATCH",
                severity="LOW",
                primary_reason="EARLY_PULLBACK_MONITOR",
                reasons=[],
                blocking_reasons=[],
                horizons_present=["rolling 5d"],
                horizon_statuses={"rolling 5d": "PULLBACK_CANDIDATE"},
                distance_to_ema20=None,
                high_exit_risk_days_count=None,
                trend_state="UP",
                latest_structure_label="HL",
                latest_bos_event_type="BOS_UP",
                latest_reset_reason="",
                latest_bullish_signal_age_td=3,
                latest_bearish_signal_age_td=None,
                pullback_validity="EARLY_PULLBACK",
                pullback_reason="WAIT_FOR_BULLISH_CONFIRMATION",
                entry_readiness="EARLY_MONITOR",
                entry_readiness_reason="WAIT_FOR_BULLISH_CONFIRMATION",
                candidate_priority=4,
                candidate_priority_label="P4_EARLY_MONITOR",
                candidate_priority_reason="EARLY_PULLBACK_WAIT_FOR_CONFIRMATION",
                source_files=[str(tmp_path / "rolling5.csv")],
                decision_trace=[
                    DatacenterDecisionTrace(
                        ticker="AMD",
                        action="WATCH",
                        matched_rule="WATCH_EARLY_PULLBACK",
                        horizon=None,
                        field_name=None,
                        matched_token="EARLY_PULLBACK",
                        matched_value="WAIT_FOR_BULLISH_CONFIRMATION",
                        source_file=None,
                        section=None,
                        row_kind=None,
                    )
                ],
            ),
            DatacenterTickerDecision(
                ticker="NV<DA>",
                action="SELL",
                severity="CRITICAL",
                primary_reason="SELL_SIGNAL_DETECTED",
                reasons=[],
                blocking_reasons=[],
                horizons_present=["daily"],
                horizon_statuses={"daily": "SELL"},
                distance_to_ema20=None,
                high_exit_risk_days_count=2,
                trend_state="DOWN",
                latest_structure_label="LL",
                latest_bos_event_type="BOS_DOWN",
                latest_reset_reason="RESET",
                latest_bullish_signal_age_td=None,
                latest_bearish_signal_age_td=0,
                pullback_validity="STRUCTURE_BLOCKED_PULLBACK",
                pullback_reason="ACUTE_BOS_DOWN_SELL_CONFIRMATION_BLOCKS_PULLBACK",
                entry_readiness="NOT_READY",
                entry_readiness_reason="STRUCTURE_BLOCKED_PULLBACK",
                candidate_priority=5,
                candidate_priority_label="P5_NOT_READY",
                candidate_priority_reason="NOT_READY",
                source_files=[str(tmp_path / "daily.csv")],
                decision_trace=[
                    DatacenterDecisionTrace(
                        ticker="NV<DA>",
                        action="SELL",
                        matched_rule="SELL_EMA20_CONFIRMED_BREAK",
                        horizon="daily",
                        field_name="ma_break_status",
                        matched_token="EMA20_CONFIRMED_BREAK",
                        matched_value="EMA20_CONFIRMED_BREAK",
                        source_file=str(tmp_path / "daily.csv"),
                        section="signals",
                        row_kind="row",
                    )
                ],
            ),
        ],
        action_counts={
            "SELL": 1,
            "REDUCE": 0,
            "TIGHTEN_STOP": 0,
            "BLOCKED": 0,
            "WAIT_PULLBACK": 0,
            "BUY_NOW": 0,
            "WATCH": 2,
            "NEUTRAL": 0,
        },
        pullback_counts={
            "VALID_PULLBACK": 1,
            "EARLY_PULLBACK": 1,
            "STRUCTURE_BLOCKED_PULLBACK": 1,
            "BREAKDOWN_NOT_PULLBACK": 0,
            "NO_PULLBACK": 0,
            "INSUFFICIENT_DATA": 0,
        },
        pullback_action_counts={
            key: {
                action: 0 for action in (
                    "SELL",
                    "REDUCE",
                    "TIGHTEN_STOP",
                    "BLOCKED",
                    "WAIT_PULLBACK",
                    "BUY_NOW",
                    "WATCH",
                    "NEUTRAL",
                )
            }
            for key in (
                "VALID_PULLBACK",
                "EARLY_PULLBACK",
                "STRUCTURE_BLOCKED_PULLBACK",
                "BREAKDOWN_NOT_PULLBACK",
                "NO_PULLBACK",
                "INSUFFICIENT_DATA",
            )
        },
        entry_readiness_counts={
            "READY_TO_WATCH": 1,
            "NEEDS_STOP_STABILIZATION": 0,
            "NEEDS_RISK_CLEARANCE": 0,
            "EARLY_MONITOR": 1,
            "NOT_READY": 1,
            "INSUFFICIENT_DATA": 0,
        },
        candidate_priority_counts={
            "P1_READY_TO_WATCH": 1,
            "P2_STOP_STABILIZATION": 0,
            "P3_RISK_CLEARANCE": 0,
            "P4_EARLY_MONITOR": 1,
            "P5_NOT_READY": 1,
            "P9_NOT_CANDIDATE": 0,
        },
        warning_count=0,
        warnings=[],
    )


def _fake_inspector_views() -> dict[str, DatacenterTickerInspectorView]:
    return {
        "MS&FT": DatacenterTickerInspectorView(
            ticker="MS&FT",
            action="WATCH",
            severity="LOW",
            primary_reason="VALID_PULLBACK_WAIT_FOR_ENTRY_CONFIRMATION",
            pullback_validity="VALID_PULLBACK",
            pullback_reason="FRESH_BULLISH_PULLBACK_WITH_NO_STRUCTURE_BLOCK",
            supporting_signals=["BOS_UP", "leader"],
            conflicting_signals=[],
            override_explanation=None,
            conflict_detected=False,
        ),
        "AMD": DatacenterTickerInspectorView(
            ticker="AMD",
            action="WATCH",
            severity="LOW",
            primary_reason="EARLY_PULLBACK_MONITOR",
            pullback_validity="EARLY_PULLBACK",
            pullback_reason="WAIT_FOR_BULLISH_CONFIRMATION",
            supporting_signals=["PULLBACK_CANDIDATE"],
            conflicting_signals=[],
            override_explanation=None,
            conflict_detected=False,
        ),
        "NV<DA>": DatacenterTickerInspectorView(
            ticker="NV<DA>",
            action="SELL",
            severity="CRITICAL",
            primary_reason="SELL_SIGNAL_DETECTED",
            pullback_validity="STRUCTURE_BLOCKED_PULLBACK",
            pullback_reason="ACUTE_BOS_DOWN_SELL_CONFIRMATION_BLOCKS_PULLBACK",
            supporting_signals=["close_below_ema20", "risk & reset"],
            conflicting_signals=["PULLBACK_CANDIDATE"],
            override_explanation="Bearish <structure> overrides bullish.",
            conflict_detected=True,
        ),
    }


def _install_pipeline_mocks(monkeypatch, tmp_path: Path) -> None:
    decision_result = _fake_decision_result(tmp_path)
    inspector_views = _fake_inspector_views()
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.discover_datacenter_dashboard_status",
        lambda reports_dir: _fake_dashboard_status(tmp_path),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.parse_datacenter_dashboard_reports",
        lambda reports: _fake_parse_batch(tmp_path),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.parse_datacenter_dashboard_file",
        lambda path, horizon: type("ParseResult", (), {"rows": _fake_rows(path, horizon)})(),
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.build_datacenter_ticker_decisions",
        lambda rows: decision_result,
    )
    monkeypatch.setattr(
        "dev_tools.run_datacenter_dashboard_html.build_datacenter_ticker_inspector_view",
        lambda decision, rows: inspector_views[decision.ticker],
    )


def test_build_parser_requires_reports_dir():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])


def test_generate_dashboard_html_is_deterministic_and_escapes_values(tmp_path, monkeypatch):
    _install_pipeline_mocks(monkeypatch, tmp_path)

    html_one, _status_one, _parse_one, _decisions_one = generate_dashboard_html(
        reports_dir=str(tmp_path),
        title="Custom <Dashboard>",
        ticker="MS&FT",
        max_command_rows=10,
        max_candidate_rows=10,
        generated_at_utc="2026-05-25T00:00:00+00:00",
    )
    html_two, _status_two, _parse_two, _decisions_two = generate_dashboard_html(
        reports_dir=str(tmp_path),
        title="Custom <Dashboard>",
        ticker="MS&FT",
        max_command_rows=10,
        max_candidate_rows=10,
        generated_at_utc="2026-05-25T00:00:00+00:00",
    )

    assert html_one == html_two
    assert "Custom &lt;Dashboard&gt;" in html_one
    assert "MS&amp;FT" in html_one
    assert "NV&lt;DA&gt;" in html_one
    assert "Bearish &lt;structure&gt; overrides bullish." in html_one


def test_html_cli_generates_default_output_and_prints_summaries(tmp_path, monkeypatch, capsys):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)

    exit_code = main(["--reports-dir", str(reports_dir), "--title", "Datacenter Dashboard"])

    assert exit_code == 0
    output_path = reports_dir / "datacenter_dashboard.html"
    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    assert "<h1>Datacenter Dashboard</h1>" in html
    assert "Summary" in html
    assert "Action Counts" in html
    assert "Pullback Counts" in html
    assert "Entry Readiness Counts" in html
    assert "Candidate Priority Counts" in html
    assert "Command Center" in html
    assert "Candidate Pullbacks" in html
    assert "Ticker Inspector / Details" in html
    assert "Source Files / Report Status" in html
    assert "VALID_PULLBACK" in html
    assert "P1_READY_TO_WATCH" in html
    assert "WATCH_VALID_PULLBACK" in html

    stdout = capsys.readouterr().out
    assert f"SUMMARY html_output={output_path}" in stdout
    assert "SUMMARY readiness=READY" in stdout
    assert "SUMMARY decision_total=3" in stdout
    assert "SUMMARY candidate_pullback_rows=2" in stdout


def test_html_cli_custom_output_path_works(tmp_path, monkeypatch):
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    output_path = tmp_path / "custom" / "dashboard.html"
    output_path.parent.mkdir()
    _install_pipeline_mocks(monkeypatch, reports_dir)

    exit_code = main(
        [
            "--reports-dir",
            str(reports_dir),
            "--output",
            str(output_path),
            "--ticker",
            "MS&FT",
        ]
    )

    assert exit_code == 0
    assert output_path.exists()
    html = output_path.read_text(encoding="utf-8")
    assert 'class="ticker-detail selected"' in html
