from __future__ import annotations

import json
from pathlib import Path

from analysis.datacenter_indices import swing_pipeline_orchestrator as orchestrator
from dev_tools.datacenter_dashboard_structured_export import (
    DatacenterStructuredExportReport,
    build_datacenter_dashboard_input_from_pipeline_reports,
    write_datacenter_dashboard_input_json_from_pipeline_reports,
)
from dev_tools.ecosystem_dashboard_persistence import persist_ecosystem_dashboard_input
from dev_tools.ecosystem_dashboard_read_model import load_dashboard_snapshot
from dev_tools.ecosystem_dashboard_structured_json import (
    load_ecosystem_dashboard_input_json,
)
from run_datacenter_swing_pipeline import main as run_datacenter_swing_pipeline_main


def _base_args(tmp_path: Path) -> list[str]:
    return [
        "--price-db",
        str(tmp_path / "osakedata.db"),
        "--analysis-db",
        str(tmp_path / "analysis.db"),
        "--taxonomy-csv",
        str(tmp_path / "taxonomy.csv"),
        "--taxonomy-version",
        "DC_TAXONOMY_FULL_V1",
        "--market",
        "usa",
        "--signal-date",
        "2026-05-22",
        "--start-date",
        "2026-01-01",
        "--index-base-date",
        "2020-01-01",
        "--output-dir",
        str(tmp_path / "reports"),
    ]


def _daily_csv_text() -> str:
    return "\n".join(
        [
            "section;ticker;action;status;reason;current_watchlist_status;trend_state;latest_structure_label;latest_bos_event_type;latest_reset_reason;ma_break_status;freshness_status;latest_bullish_signal_age_td;latest_bearish_signal_age_td;latest_bos_up_age_td;latest_bos_down_age_td;latest_reset_age_td;latest_candle;latest_candle_age_td;latest_divergence;latest_divergence_age_td;latest_chart_pattern;latest_chart_pattern_age_td;pullback_days",
            "Watchlist Summary;NVDA;BUY_NOW;BUY_NOW;buy_now;BREAKOUT_CANDIDATE;UP;HH;BOS_UP;;OK;FRESH_BULLISH_SIGNAL;1;;2;;;Hammer;1;Bullish Divergence;2;Bull Flag;3;1",
        ]
    )


def _rolling_30_csv_text() -> str:
    return "\n".join(
        [
            "section;ticker;action;status;reason;current_watchlist_status;window_watchlist_status;trend_state;latest_structure_label;latest_bos_event_type;ma_break_status;freshness_status;pullback_days",
            "Watchlist Summary;NVDA;WATCH;BUY_ZONE;buy_zone;BREAKOUT_CANDIDATE;BREAKOUT_CANDIDATE;UP;HH;BOS_UP;OK;FRESH_BULLISH_SIGNAL;1",
        ]
    )


def _rolling_5_csv_text() -> str:
    return "\n".join(
        [
            "section;ticker;action;status;reason;current_watchlist_status;window_watchlist_status;trend_state;latest_structure_label;latest_bos_event_type;ma_break_status;freshness_status;pullback_days",
            "Watchlist Summary;NVDA;WAIT_PULLBACK;PULLBACK_CANDIDATE;pullback_candidate;PULLBACK_CANDIDATE;PULLBACK_CANDIDATE;UP;HH;BOS_UP;OK;FRESH_BULLISH_SIGNAL;1",
        ]
    )


def _rolling_2_csv_text() -> str:
    return "\n".join(
        [
            "section;ticker;action;status;reason;current_watchlist_status;window_watchlist_status;trend_state;latest_structure_label;latest_bos_event_type;ma_break_status;freshness_status",
            "Watchlist Summary;NVDA;WATCH;NO_EMERGENCY;no_emergency;NEUTRAL_MONITOR;NEUTRAL_MONITOR;UP;HH;BOS_UP;OK;FRESH_BULLISH_SIGNAL",
        ]
    )


def _daily_report_data() -> dict[str, object]:
    return {
        "group_rows": [
            {
                "group_type": "ecosystem",
                "group_name": "DC_ECOSYSTEM_TOTAL",
                "timing_state": "BUY_ZONE",
                "overheat_risk_level": "LOW",
                "pct_above_ema20": 62.5,
                "pct_above_ma10": 58.0,
                "ema20_breadth_delta_5d": 4.0,
                "return_5d": 0.12,
                "return_10d": 0.18,
                "return_20d": 0.25,
                "return_60d": 0.44,
            },
            {
                "group_type": "layer",
                "group_name": "Infrastructure",
                "timing_state": "BUY_ZONE",
                "overheat_risk_level": "LOW",
                "pct_above_ema20": 60.0,
                "pct_above_ma10": 55.0,
                "ema20_breadth_delta_5d": 3.0,
                "return_5d": 0.10,
                "return_10d": 0.17,
                "return_20d": 0.24,
                "return_60d": 0.40,
            },
            {
                "group_type": "subindustry",
                "group_name": "AI Accelerators",
                "timing_state": "BUY_ZONE",
                "overheat_risk_level": "LOW",
                "pct_above_ema20": 64.0,
                "pct_above_ma10": 59.0,
                "ema20_breadth_delta_5d": 5.0,
                "return_5d": 0.14,
                "return_10d": 0.20,
                "return_20d": 0.27,
                "return_60d": 0.46,
            },
        ],
        "ticker_rows": [
            {
                "ticker": "NVDA",
                "primary_layer": "Infrastructure",
                "primary_subindustry": "AI Accelerators",
            }
        ],
    }


def _fake_export_reports(tmp_path: Path) -> tuple[
    DatacenterStructuredExportReport,
    DatacenterStructuredExportReport,
    DatacenterStructuredExportReport,
    DatacenterStructuredExportReport,
]:
    daily = DatacenterStructuredExportReport(
        horizon="daily",
        markdown_path=str(tmp_path / "datacenter_daily_2026-05-22_0000_full.md"),
        csv_text=_daily_csv_text(),
        report_data=_daily_report_data(),
    )
    rolling_30 = DatacenterStructuredExportReport(
        horizon="rolling 30d",
        markdown_path=str(tmp_path / "datacenter_rolling_30_2026-05-22_0000_full.md"),
        csv_text=_rolling_30_csv_text(),
        report_data={},
    )
    rolling_5 = DatacenterStructuredExportReport(
        horizon="rolling 5d",
        markdown_path=str(tmp_path / "datacenter_rolling_5_2026-05-22_0000_full.md"),
        csv_text=_rolling_5_csv_text(),
        report_data={},
    )
    rolling_2 = DatacenterStructuredExportReport(
        horizon="rolling 2d",
        markdown_path=str(tmp_path / "datacenter_rolling_2_2026-05-22_0000_full.md"),
        csv_text=_rolling_2_csv_text(),
        report_data={},
    )
    return daily, rolling_30, rolling_5, rolling_2


def _fake_pipeline_report_result(*, output_md: Path, output_csv: Path, csv_text: str, report_data: dict[str, object]) -> dict[str, object]:
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("placeholder markdown\n", encoding="utf-8")
    output_csv.write_text(csv_text + "\n", encoding="utf-8")
    return {
        "markdown": "placeholder markdown\n",
        "csv": csv_text + "\n",
        "report_data": report_data,
        "summary": {
            "output_markdown": str(output_md),
            "output_csv": str(output_csv),
            "validation_status": "OK",
        },
    }


def test_exporter_builds_ecosystem_dashboard_input_from_fake_pipeline_reports(monkeypatch, tmp_path):
    daily, rolling_30, rolling_5, rolling_2 = _fake_export_reports(tmp_path)
    monkeypatch.setattr(
        "dev_tools.datacenter_dashboard_parser.parse_datacenter_dashboard_file",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("markdown/file parsing should not be used")),
    )

    dashboard_input, summary_lines = build_datacenter_dashboard_input_from_pipeline_reports(
        ecosystem_code="DATACENTER",
        report_date="2026-05-22",
        reports_dir=str(tmp_path),
        daily_report=daily,
        rolling_30_report=rolling_30,
        rolling_5_report=rolling_5,
        rolling_2_report=rolling_2,
    )

    assert dashboard_input.ecosystem_code == "DATACENTER"
    assert dashboard_input.report_date == "2026-05-22"
    assert len(dashboard_input.source_reports) == 4
    assert len(dashboard_input.action_summary) == 8
    assert len(dashboard_input.market_map) == 3
    assert len(dashboard_input.watchlist) == 1
    assert len(dashboard_input.tickers) == 1
    assert len(dashboard_input.decision_trace) == 3
    assert dashboard_input.watchlist[0].ticker == "NVDA"
    assert dashboard_input.watchlist[0].action_bucket == "BUY_NOW"
    assert dashboard_input.watchlist[0].watchlist_reason == "MULTI_HORIZON_ALIGNMENT"
    assert dashboard_input.tickers[0].ticker == "NVDA"
    assert dashboard_input.market_map[0].dominant_action_bucket == "BUY_ZONE"
    assert dashboard_input.market_map[0].avg_return_20d == 0.25
    assert "SUMMARY datacenter_dashboard_structured_export.watchlist=1" in summary_lines
    assert "SUMMARY datacenter_dashboard_structured_export.decision_trace=3" in summary_lines


def test_exporter_writes_json_round_trips_and_persists_to_temp_dashboard_db(tmp_path):
    daily, rolling_30, rolling_5, rolling_2 = _fake_export_reports(tmp_path)
    output_json = tmp_path / "dashboard_input.json"

    dashboard_input, summary_lines = write_datacenter_dashboard_input_json_from_pipeline_reports(
        ecosystem_code="DATACENTER",
        report_date="2026-05-22",
        reports_dir=str(tmp_path),
        output_json=str(output_json),
        daily_report=daily,
        rolling_30_report=rolling_30,
        rolling_5_report=rolling_5,
        rolling_2_report=rolling_2,
    )

    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["ecosystem_code"] == "DATACENTER"
    assert len(payload["source_reports"]) == 4
    assert len(payload["action_summary"]) == 8
    assert len(payload["market_map"]) == 3
    assert len(payload["watchlist"]) == 1
    assert len(payload["tickers"]) == 1
    assert len(payload["decision_trace"]) == 3
    assert f"SUMMARY datacenter_dashboard_structured_export.output_json={output_json}" in summary_lines

    loaded = load_ecosystem_dashboard_input_json(str(output_json))
    assert loaded == dashboard_input

    dashboard_db = tmp_path / "ecosystem_dashboard.db"
    run_id = persist_ecosystem_dashboard_input(
        dashboard_db=str(dashboard_db),
        dashboard_input=loaded,
        mode="replace-date",
        run_id="TEST_EXPORT_RUN",
    )
    snapshot = load_dashboard_snapshot(
        dashboard_db=str(dashboard_db),
        ecosystem_code="DATACENTER",
        run_id=run_id,
    )
    assert snapshot.run.run_id == "TEST_EXPORT_RUN"
    assert len(snapshot.watchlist) == 1
    assert len(snapshot.tickers) == 1
    assert len(snapshot.decision_trace) == 3


def test_pipeline_cli_export_option_writes_json_and_summary_counts(monkeypatch, tmp_path, capsys):
    export_json = tmp_path / "datacenter_dashboard_input.json"

    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _daily(**kwargs):
        return _fake_pipeline_report_result(
            output_md=kwargs["output_md"],
            output_csv=kwargs["output_csv"],
            csv_text=_daily_csv_text(),
            report_data=_daily_report_data(),
        )

    def _weekly(**kwargs):
        if kwargs["window_size"] == 30:
            csv_text = _rolling_30_csv_text()
        elif kwargs["window_size"] == 5:
            csv_text = _rolling_5_csv_text()
        elif kwargs["window_size"] == 2:
            csv_text = _rolling_2_csv_text()
        else:
            csv_text = _rolling_30_csv_text()
        return _fake_pipeline_report_result(
            output_md=kwargs["output_md"],
            output_csv=kwargs["output_csv"],
            csv_text=csv_text,
            report_data={},
        )

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_write_stage_watermark", lambda **kwargs: None)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path)
        + [
            "--no-technical-relevance",
            "--export-dashboard-input-json",
            str(export_json),
        ]
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    payload = json.loads(export_json.read_text(encoding="utf-8"))
    assert "SUMMARY datacenter_dashboard_structured_export.status=OK" in output
    assert "SUMMARY datacenter_dashboard_structured_export.ecosystem_code=DATACENTER" in output
    assert "SUMMARY datacenter_dashboard_structured_export.report_date=2026-05-22" in output
    assert f"SUMMARY datacenter_dashboard_structured_export.output_json={export_json}" in output
    assert f"SUMMARY datacenter_dashboard_structured_export.source_reports={len(payload['source_reports'])}" in output
    assert f"SUMMARY datacenter_dashboard_structured_export.action_summary={len(payload['action_summary'])}" in output
    assert f"SUMMARY datacenter_dashboard_structured_export.market_map={len(payload['market_map'])}" in output
    assert f"SUMMARY datacenter_dashboard_structured_export.watchlist={len(payload['watchlist'])}" in output
    assert f"SUMMARY datacenter_dashboard_structured_export.tickers={len(payload['tickers'])}" in output
    assert f"SUMMARY datacenter_dashboard_structured_export.decision_trace={len(payload['decision_trace'])}" in output
    assert not (tmp_path / "ecosystem_dashboard.db").exists()
    assert not list((tmp_path / "reports").glob("*.html"))


def test_pipeline_without_export_option_keeps_reports_mode_compatible_with_summary_only_results(monkeypatch, tmp_path):
    def _runner(argv: list[str]) -> int:
        return 0

    def _audit(**kwargs):
        return {"summary": {"validation_status": "OK"}}

    def _daily(**kwargs):
        kwargs["output_md"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["output_md"].write_text("daily\n", encoding="utf-8")
        kwargs["output_csv"].write_text("daily\n", encoding="utf-8")
        return {
            "summary": {
                "output_markdown": str(kwargs["output_md"]),
                "output_csv": str(kwargs["output_csv"]),
                "validation_status": "OK",
            }
        }

    def _weekly(**kwargs):
        kwargs["output_md"].write_text("weekly\n", encoding="utf-8")
        kwargs["output_csv"].write_text("weekly\n", encoding="utf-8")
        return {
            "summary": {
                "output_markdown": str(kwargs["output_md"]),
                "output_csv": str(kwargs["output_csv"]),
                "validation_status": "OK",
            }
        }

    monkeypatch.setattr(orchestrator, "run_datacenter_indices_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_ticker_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_swing_signals_main", _runner)
    monkeypatch.setattr(orchestrator, "run_datacenter_group_synthetic_ohlc_main", _runner)
    monkeypatch.setattr(orchestrator, "load_swing_pipeline_audit", _audit)
    monkeypatch.setattr(orchestrator, "_write_stage_watermark", lambda **kwargs: None)
    monkeypatch.setattr(orchestrator, "write_daily_swing_signal_report", _daily)
    monkeypatch.setattr(orchestrator, "write_weekly_swing_report", _weekly)
    monkeypatch.setattr(orchestrator, "format_swing_pipeline_audit_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_daily_swing_report_summary_lines", lambda summary: [])
    monkeypatch.setattr(orchestrator, "format_weekly_swing_report_summary_lines", lambda summary: [])

    exit_code = run_datacenter_swing_pipeline_main(
        _base_args(tmp_path) + ["--no-technical-relevance"]
    )

    assert exit_code == 0
