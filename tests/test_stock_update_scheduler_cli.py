from __future__ import annotations

import pytest

from rawcandle.cli import run_stock_update_scheduler as cli
from rawcandle.scheduler.runner import (
    ScheduledMarketRunResult,
    ScheduledStockUpdateRunResult,
    SchedulerAlreadyRunningError,
    STATUS_FAILED,
    STATUS_OK,
    STATUS_OK_WITH_WARNINGS,
)


def _result(overall_status):
    return ScheduledStockUpdateRunResult(
        started_at_utc="2026-05-16T00:00:00Z",
        finished_at_utc="2026-05-16T00:10:00Z",
        config_path="/tmp/scheduler.json",
        enabled_markets=["omxh", "omxs"],
        market_results=[
            ScheduledMarketRunResult(
                market="omxh",
                started_at_utc="2026-05-16T00:00:00Z",
                finished_at_utc="2026-05-16T00:01:00Z",
                exit_code=0,
                summary_status=STATUS_OK,
                log_path="/tmp/logs/omxh.log",
                summary_lines=["SUMMARY market=omxh"],
            ),
            ScheduledMarketRunResult(
                market="omxs",
                started_at_utc="2026-05-16T00:01:00Z",
                finished_at_utc="2026-05-16T00:02:00Z",
                exit_code=0 if overall_status == STATUS_OK else 1,
                summary_status=overall_status if overall_status != STATUS_OK else STATUS_OK,
                log_path="/tmp/logs/omxs.log",
                summary_lines=["SUMMARY market=omxs"],
            ),
        ],
        overall_status=overall_status,
        summary_json_path="/tmp/logs/summary.json",
        skipped=False,
        skip_reason=None,
        technical_relevance_attempted=0,
        technical_relevance_enabled=False,
        technical_relevance_status="DISABLED",
        technical_relevance_market="NONE",
        technical_relevance_run_id="NONE",
        technical_relevance_ticker_count=0,
        technical_relevance_start_date="NONE",
        technical_relevance_end_date="NONE",
        technical_relevance_records_written=0,
        technical_relevance_relevant_count=0,
        technical_relevance_weak_context_count=0,
        technical_relevance_noise_count=0,
        technical_relevance_unknown_signal_count=0,
        technical_relevance_missing_dow_context_count=0,
        technical_relevance_missing_bar_index_count=0,
        technical_relevance_duration_seconds="0.000",
        technical_relevance_skip_reason="",
        technical_relevance_error="",
        datacenter_pipeline_attempted=0,
        datacenter_pipeline_status="SKIPPED",
        datacenter_pipeline_market="usa",
        datacenter_pipeline_audit_validation_status="SKIPPED",
        datacenter_pipeline_log_path="",
        datacenter_pipeline_signal_date="NONE",
        datacenter_pipeline_signal_date_source="NONE",
        datacenter_pipeline_signal_date_resolution="NONE",
        datacenter_pipeline_requested_calendar_signal_date="NONE",
        datacenter_pipeline_daily_report_path=None,
        datacenter_pipeline_daily_report_csv_path=None,
        datacenter_pipeline_rolling_30_report_path=None,
        datacenter_pipeline_rolling_30_report_csv_path=None,
        datacenter_pipeline_rolling_5_report_path=None,
        datacenter_pipeline_rolling_5_report_csv_path=None,
        datacenter_pipeline_rolling_2_report_path=None,
        datacenter_pipeline_rolling_2_report_csv_path=None,
        datacenter_pipeline_weekly_report_path=None,
        datacenter_pipeline_weekly_report_csv_path=None,
        datacenter_pipeline_error="",
        v3_reports_attempted=0,
        v3_reports_status="SKIPPED",
        v3_reports_run_id="NONE",
        v3_reports_signal_date="NONE",
        v3_reports_output_dir="",
        v3_reports_daily_report_path=None,
        v3_reports_rolling_30_report_path=None,
        v3_reports_rolling_5_report_path=None,
        v3_reports_rolling_2_report_path=None,
        v3_reports_error="",
        datacenter_dashboard_attempted=0,
        datacenter_dashboard_status="SKIPPED",
        datacenter_dashboard_dashboard_db="",
        datacenter_dashboard_report_date="",
        datacenter_dashboard_md_reports_status="SKIPPED",
        datacenter_dashboard_source_reports_available=0,
        datacenter_dashboard_html_output_path="",
        datacenter_dashboard_markdown_output_path="",
        datacenter_dashboard_markdown_render_status="SKIPPED",
        datacenter_dashboard_run_id="",
        datacenter_dashboard_skip_reason="",
        datacenter_dashboard_source_mode="reports",
        datacenter_dashboard_reports_reference_status="SKIPPED",
        datacenter_dashboard_reports_reference_run_id="",
        datacenter_dashboard_reports_reference_dashboard_db="",
        datacenter_dashboard_reports_reference_html_output_path="",
        datacenter_dashboard_reports_reference_markdown_output_path="",
        datacenter_dashboard_reports_reference_markdown_render_status="SKIPPED",
        datacenter_enrichment_attempted=0,
        datacenter_enrichment_status="SKIPPED",
        datacenter_enrichment_readiness="SKIPPED",
        datacenter_enrichment_run_id="",
        datacenter_dashboard_enrichment_export_status="SKIPPED",
        datacenter_dashboard_structured_build_status="SKIPPED",
        datacenter_dashboard_acceptance_report_status="SKIPPED",
        datacenter_dashboard_acceptance_report_blockers="",
        datacenter_dashboard_acceptance_report_recommendation="",
        datacenter_dashboard_fallback_used=0,
        datacenter_dashboard_final_source_mode="reports",
        datacenter_dashboard_error="",
    )


def _skipped_result():
    return ScheduledStockUpdateRunResult(
        started_at_utc="2026-05-16T00:00:00Z",
        finished_at_utc="2026-05-16T00:00:01Z",
        config_path="/tmp/scheduler.json",
        enabled_markets=["omxh", "omxs"],
        market_results=[],
        overall_status=STATUS_OK,
        summary_json_path="/tmp/logs/summary.json",
        skipped=True,
        skip_reason="skip_next_run",
        technical_relevance_attempted=0,
        technical_relevance_enabled=False,
        technical_relevance_status="DISABLED",
        technical_relevance_market="NONE",
        technical_relevance_run_id="NONE",
        technical_relevance_ticker_count=0,
        technical_relevance_start_date="NONE",
        technical_relevance_end_date="NONE",
        technical_relevance_records_written=0,
        technical_relevance_relevant_count=0,
        technical_relevance_weak_context_count=0,
        technical_relevance_noise_count=0,
        technical_relevance_unknown_signal_count=0,
        technical_relevance_missing_dow_context_count=0,
        technical_relevance_missing_bar_index_count=0,
        technical_relevance_duration_seconds="0.000",
        technical_relevance_skip_reason="",
        technical_relevance_error="",
        datacenter_pipeline_attempted=0,
        datacenter_pipeline_status="SKIPPED",
        datacenter_pipeline_market="usa",
        datacenter_pipeline_audit_validation_status="SKIPPED",
        datacenter_pipeline_log_path="",
        datacenter_pipeline_signal_date="NONE",
        datacenter_pipeline_signal_date_source="NONE",
        datacenter_pipeline_signal_date_resolution="NONE",
        datacenter_pipeline_requested_calendar_signal_date="NONE",
        datacenter_pipeline_daily_report_path=None,
        datacenter_pipeline_daily_report_csv_path=None,
        datacenter_pipeline_rolling_30_report_path=None,
        datacenter_pipeline_rolling_30_report_csv_path=None,
        datacenter_pipeline_rolling_5_report_path=None,
        datacenter_pipeline_rolling_5_report_csv_path=None,
        datacenter_pipeline_rolling_2_report_path=None,
        datacenter_pipeline_rolling_2_report_csv_path=None,
        datacenter_pipeline_weekly_report_path=None,
        datacenter_pipeline_weekly_report_csv_path=None,
        datacenter_pipeline_error="",
        v3_reports_attempted=0,
        v3_reports_status="SKIPPED",
        v3_reports_run_id="NONE",
        v3_reports_signal_date="NONE",
        v3_reports_output_dir="",
        v3_reports_daily_report_path=None,
        v3_reports_rolling_30_report_path=None,
        v3_reports_rolling_5_report_path=None,
        v3_reports_rolling_2_report_path=None,
        v3_reports_error="",
        datacenter_dashboard_attempted=0,
        datacenter_dashboard_status="SKIPPED",
        datacenter_dashboard_dashboard_db="",
        datacenter_dashboard_report_date="",
        datacenter_dashboard_md_reports_status="SKIPPED",
        datacenter_dashboard_source_reports_available=0,
        datacenter_dashboard_html_output_path="",
        datacenter_dashboard_markdown_output_path="",
        datacenter_dashboard_markdown_render_status="SKIPPED",
        datacenter_dashboard_run_id="",
        datacenter_dashboard_skip_reason="SKIP_NEXT_RUN",
        datacenter_dashboard_source_mode="reports",
        datacenter_dashboard_reports_reference_status="SKIPPED",
        datacenter_dashboard_reports_reference_run_id="",
        datacenter_dashboard_reports_reference_dashboard_db="",
        datacenter_dashboard_reports_reference_html_output_path="",
        datacenter_dashboard_reports_reference_markdown_output_path="",
        datacenter_dashboard_reports_reference_markdown_render_status="SKIPPED",
        datacenter_enrichment_attempted=0,
        datacenter_enrichment_status="SKIPPED",
        datacenter_enrichment_readiness="SKIPPED",
        datacenter_enrichment_run_id="",
        datacenter_dashboard_enrichment_export_status="SKIPPED",
        datacenter_dashboard_structured_build_status="SKIPPED",
        datacenter_dashboard_acceptance_report_status="SKIPPED",
        datacenter_dashboard_acceptance_report_blockers="",
        datacenter_dashboard_acceptance_report_recommendation="",
        datacenter_dashboard_fallback_used=0,
        datacenter_dashboard_final_source_mode="reports",
        datacenter_dashboard_error="",
    )


def test_scheduler_cli_missing_config_exits_via_parser():
    with pytest.raises(SystemExit):
        cli.main([])


def test_scheduler_cli_successful_run_prints_top_level_summary_lines(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK))

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY scheduler_status=OK" in captured.out
    assert "SUMMARY markets_enabled=omxh,omxs" in captured.out
    assert "SUMMARY summary_json_path=/tmp/logs/summary.json" in captured.out
    assert "SUMMARY scheduler_skipped=0" in captured.out
    assert "SUMMARY scheduler_skip_reason=" in captured.out
    assert "SUMMARY technical_relevance.attempted=0" in captured.out
    assert "SUMMARY technical_relevance.enabled=false" in captured.out
    assert "SUMMARY technical_relevance.status=DISABLED" in captured.out
    assert "SUMMARY technical_relevance.market=NONE" in captured.out
    assert "SUMMARY technical_relevance.run_id=NONE" in captured.out
    assert "SUMMARY technical_relevance.ticker_count=0" in captured.out
    assert "SUMMARY technical_relevance.start_date=NONE" in captured.out
    assert "SUMMARY technical_relevance.end_date=NONE" in captured.out
    assert "SUMMARY technical_relevance.records_written=0" in captured.out
    assert "SUMMARY technical_relevance.relevant_count=0" in captured.out
    assert "SUMMARY technical_relevance.weak_context_count=0" in captured.out
    assert "SUMMARY technical_relevance.noise_count=0" in captured.out
    assert "SUMMARY technical_relevance.unknown_signal_count=0" in captured.out
    assert "SUMMARY technical_relevance.missing_dow_context_count=0" in captured.out
    assert "SUMMARY technical_relevance.missing_bar_index_count=0" in captured.out
    assert "SUMMARY technical_relevance.duration_seconds=0.000" in captured.out
    assert "SUMMARY technical_relevance.skip_reason=" in captured.out
    assert "SUMMARY datacenter_pipeline.attempted=0" in captured.out
    assert "SUMMARY datacenter_pipeline.status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_pipeline.market=usa" in captured.out
    assert "SUMMARY datacenter_pipeline.signal_date=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.signal_date_source=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.signal_date_resolution=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.requested_calendar_signal_date=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.audit_validation_status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_pipeline.log_path=" in captured.out
    assert "SUMMARY datacenter_pipeline.daily_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.daily_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_30_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_30_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_5_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_5_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_2_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.rolling_2_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.weekly_report_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.weekly_report_csv_path=NONE" in captured.out
    assert "SUMMARY datacenter_pipeline.error=" in captured.out
    assert "SUMMARY v3_reports.attempted=0" in captured.out
    assert "SUMMARY v3_reports.status=SKIPPED" in captured.out
    assert "SUMMARY v3_reports.run_id=NONE" in captured.out
    assert "SUMMARY v3_reports.signal_date=NONE" in captured.out
    assert "SUMMARY v3_reports.output_dir=NONE" in captured.out
    assert "SUMMARY v3_reports.daily_report_path=NONE" in captured.out
    assert "SUMMARY v3_reports.rolling_30_report_path=NONE" in captured.out
    assert "SUMMARY v3_reports.rolling_5_report_path=NONE" in captured.out
    assert "SUMMARY v3_reports.rolling_2_report_path=NONE" in captured.out
    assert "SUMMARY v3_reports.error=" in captured.out
    assert "SUMMARY datacenter_dashboard.attempted=0" in captured.out
    assert "SUMMARY datacenter_dashboard.status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_dashboard.dashboard_db=" in captured.out
    assert "SUMMARY datacenter_dashboard.report_date=" in captured.out
    assert "SUMMARY datacenter_dashboard.md_reports_status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_dashboard.source_reports_available=0" in captured.out
    assert "SUMMARY datacenter_dashboard.html_output_path=" in captured.out
    assert "SUMMARY datacenter_dashboard.markdown_output_path=" in captured.out
    assert "SUMMARY datacenter_dashboard.markdown_render_status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_dashboard.run_id=" in captured.out
    assert "SUMMARY datacenter_dashboard.skip_reason=" in captured.out
    assert "SUMMARY datacenter_dashboard_source_mode=reports" in captured.out
    assert "SUMMARY datacenter_dashboard.reports_reference_status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_dashboard.reports_reference_run_id=" in captured.out
    assert "SUMMARY datacenter_dashboard.reports_reference_dashboard_db=" in captured.out
    assert "SUMMARY datacenter_dashboard.reports_reference_html_output_path=" in captured.out
    assert "SUMMARY datacenter_dashboard.reports_reference_markdown_output_path=" in captured.out
    assert (
        "SUMMARY datacenter_dashboard.reports_reference_markdown_render_status=SKIPPED"
        in captured.out
    )
    assert "SUMMARY datacenter_enrichment.attempted=0" in captured.out
    assert "SUMMARY datacenter_enrichment.status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_enrichment.readiness=SKIPPED" in captured.out
    assert "SUMMARY datacenter_enrichment.run_id=" in captured.out
    assert "SUMMARY datacenter_dashboard.enrichment_export_status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_dashboard.structured_build_status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_dashboard.acceptance_report_status=SKIPPED" in captured.out
    assert "SUMMARY datacenter_dashboard.acceptance_report_blockers=" in captured.out
    assert "SUMMARY datacenter_dashboard.acceptance_report_recommendation=" in captured.out
    assert "SUMMARY datacenter_dashboard.fallback_used=0" in captured.out
    assert "SUMMARY datacenter_dashboard.final_source_mode=reports" in captured.out
    assert "SUMMARY datacenter_dashboard.error=" in captured.out


def test_scheduler_cli_ok_overall_status_exits_zero(monkeypatch):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK))
    assert cli.main(["--config", "/tmp/scheduler.json"]) == 0


def test_scheduler_cli_successful_run_prints_reports_reference_summary_when_present(
    monkeypatch, capsys
):
    result = _result(STATUS_OK)
    result.datacenter_dashboard_run_id = "ENRICH_DASH_RUN"
    result.datacenter_dashboard_reports_reference_status = "OK"
    result.datacenter_dashboard_reports_reference_run_id = "REPORTS_REFERENCE_RUN"
    result.datacenter_dashboard_reports_reference_dashboard_db = "/tmp/reference.db"
    result.datacenter_dashboard_reports_reference_html_output_path = (
        "/tmp/reference_html/datacenter_dashboard_reports_reference_2026-05-22.html"
    )
    result.datacenter_dashboard_markdown_output_path = (
        "/tmp/html/datacenter_dashboard_2026-05-22.md"
    )
    result.datacenter_dashboard_markdown_render_status = "OK"
    result.datacenter_dashboard_reports_reference_markdown_output_path = (
        "/tmp/reference_html/datacenter_dashboard_reports_reference_2026-05-22.md"
    )
    result.datacenter_dashboard_reports_reference_markdown_render_status = "OK"
    result.datacenter_dashboard_acceptance_report_status = "OK"
    result.datacenter_dashboard_acceptance_report_blockers = "0"
    result.datacenter_dashboard_acceptance_report_recommendation = (
        "READY_FOR_SCHEDULER_SWITCH_PLANNING"
    )
    result.datacenter_dashboard_final_source_mode = "enrichment"
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: result)

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY datacenter_dashboard.run_id=ENRICH_DASH_RUN" in captured.out
    assert "SUMMARY datacenter_dashboard.reports_reference_status=OK" in captured.out
    assert "SUMMARY datacenter_dashboard.reports_reference_run_id=REPORTS_REFERENCE_RUN" in captured.out
    assert "SUMMARY datacenter_dashboard.reports_reference_dashboard_db=/tmp/reference.db" in captured.out
    assert (
        "SUMMARY datacenter_dashboard.reports_reference_html_output_path="
        "/tmp/reference_html/datacenter_dashboard_reports_reference_2026-05-22.html"
    ) in captured.out
    assert (
        "SUMMARY datacenter_dashboard.markdown_output_path="
        "/tmp/html/datacenter_dashboard_2026-05-22.md"
    ) in captured.out
    assert "SUMMARY datacenter_dashboard.markdown_render_status=OK" in captured.out
    assert (
        "SUMMARY datacenter_dashboard.reports_reference_markdown_output_path="
        "/tmp/reference_html/datacenter_dashboard_reports_reference_2026-05-22.md"
    ) in captured.out
    assert (
        "SUMMARY datacenter_dashboard.reports_reference_markdown_render_status=OK"
        in captured.out
    )
    assert "SUMMARY datacenter_dashboard.acceptance_report_status=OK" in captured.out
    assert "SUMMARY datacenter_dashboard.acceptance_report_blockers=0" in captured.out
    assert (
        "SUMMARY datacenter_dashboard.acceptance_report_recommendation="
        "READY_FOR_SCHEDULER_SWITCH_PLANNING"
    ) in captured.out
    assert "SUMMARY datacenter_dashboard.final_source_mode=enrichment" in captured.out


def test_scheduler_cli_prints_v3_report_summary_when_present(monkeypatch, capsys):
    result = _result(STATUS_OK_WITH_WARNINGS)
    result.v3_reports_attempted = 1
    result.v3_reports_status = "OK"
    result.v3_reports_run_id = "V3_RUN_2026_05_22"
    result.v3_reports_signal_date = "2026-05-22"
    result.v3_reports_output_dir = "/tmp/swing_reports/v3/datacenter/2026-05-22"
    result.v3_reports_daily_report_path = (
        "/tmp/swing_reports/v3/datacenter/2026-05-22/datacenter_v3_daily_2026-05-22.md"
    )
    result.v3_reports_rolling_30_report_path = (
        "/tmp/swing_reports/v3/datacenter/2026-05-22/datacenter_v3_rolling30_2026-05-22.md"
    )
    result.v3_reports_rolling_5_report_path = (
        "/tmp/swing_reports/v3/datacenter/2026-05-22/datacenter_v3_rolling5_2026-05-22.md"
    )
    result.v3_reports_rolling_2_report_path = (
        "/tmp/swing_reports/v3/datacenter/2026-05-22/datacenter_v3_rolling2_2026-05-22.md"
    )
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: result)

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 1
    assert "SUMMARY v3_reports.attempted=1" in captured.out
    assert "SUMMARY v3_reports.status=OK" in captured.out
    assert "SUMMARY v3_reports.run_id=V3_RUN_2026_05_22" in captured.out
    assert "SUMMARY v3_reports.signal_date=2026-05-22" in captured.out
    assert "SUMMARY v3_reports.output_dir=/tmp/swing_reports/v3/datacenter/2026-05-22" in captured.out
    assert (
        "SUMMARY v3_reports.daily_report_path="
        "/tmp/swing_reports/v3/datacenter/2026-05-22/datacenter_v3_daily_2026-05-22.md"
    ) in captured.out
    assert (
        "SUMMARY v3_reports.rolling_30_report_path="
        "/tmp/swing_reports/v3/datacenter/2026-05-22/datacenter_v3_rolling30_2026-05-22.md"
    ) in captured.out
    assert (
        "SUMMARY v3_reports.rolling_5_report_path="
        "/tmp/swing_reports/v3/datacenter/2026-05-22/datacenter_v3_rolling5_2026-05-22.md"
    ) in captured.out
    assert (
        "SUMMARY v3_reports.rolling_2_report_path="
        "/tmp/swing_reports/v3/datacenter/2026-05-22/datacenter_v3_rolling2_2026-05-22.md"
    ) in captured.out


def test_scheduler_cli_prints_v3_error_when_present(monkeypatch, capsys):
    result = _result(STATUS_OK_WITH_WARNINGS)
    result.v3_reports_attempted = 1
    result.v3_reports_status = "FAILED"
    result.v3_reports_error = "write failed"
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: result)

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 1
    assert "SUMMARY v3_reports.status=FAILED" in captured.out
    assert "SUMMARY v3_reports.error=write failed" in captured.out


def test_scheduler_cli_ok_with_warnings_exits_one(monkeypatch):
    monkeypatch.setattr(
        cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK_WITH_WARNINGS)
    )
    assert cli.main(["--config", "/tmp/scheduler.json"]) == 1


def test_scheduler_cli_failed_exits_one(monkeypatch):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_FAILED))
    assert cli.main(["--config", "/tmp/scheduler.json"]) == 1


def test_scheduler_cli_prints_per_market_status_and_log_lines(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _result(STATUS_OK))

    cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert "SUMMARY market.omxh.status=OK" in captured.out
    assert "SUMMARY market.omxh.log_path=/tmp/logs/omxh.log" in captured.out
    assert "SUMMARY market.omxs.status=OK" in captured.out
    assert "SUMMARY market.omxs.log_path=/tmp/logs/omxs.log" in captured.out


def test_scheduler_cli_skipped_run_prints_skip_summary(monkeypatch, capsys):
    monkeypatch.setattr(cli, "run_scheduler_config", lambda config_path: _skipped_result())

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY scheduler_status=OK" in captured.out
    assert "SUMMARY scheduler_skipped=1" in captured.out
    assert "SUMMARY scheduler_skip_reason=skip_next_run" in captured.out
    assert "SUMMARY markets_total=0" in captured.out


def test_scheduler_cli_lock_conflict_prints_failed_summary_and_exits_one(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        cli,
        "run_scheduler_config",
        lambda config_path: (_ for _ in ()).throw(
            SchedulerAlreadyRunningError("already running")
        ),
    )

    code = cli.main(["--config", "/tmp/scheduler.json"])

    captured = capsys.readouterr()
    assert code == 1
    assert "SUMMARY scheduler_status=FAILED" in captured.out
    assert "SUMMARY scheduler_skipped=0" in captured.out
    assert "SUMMARY scheduler_skip_reason=" in captured.out
    assert "SUMMARY error=already running" in captured.out


def test_scheduler_cli_inspect_dashboard_config_prints_required_summary_lines(
    monkeypatch, capsys
):
    class _Inspection:
        enabled = 1
        ecosystem_code = "DATACENTER"
        dashboard_db = "/tmp/ecosystem_dashboard.db"
        reports_dir = "/tmp/swing_reports"
        html_output_dir = "/tmp/html"
        reports_reference_enabled = 0
        reports_reference_db = "/tmp/reports_reference.db"
        reports_reference_html_output_dir = "/tmp/html"
        expected_report_date = "2026-05-22"
        expected_html_output_path = "/tmp/html/datacenter_dashboard_2026-05-22.html"
        reports_reference_expected_html_output_path = (
            "/tmp/html/datacenter_dashboard_reports_reference_2026-05-22.html"
        )
        mode = "replace-date"
        render_html = 1
        usa_enabled = 1
        datacenter_pipeline_enabled = 1
        skip_next_run = 0
        dashboard_source_mode = "reports"
        enrichment_enabled = 0
        enrichment_apply_migrations = 0
        enrichment_taxonomy_version = "DC_TAXONOMY_FULL_V1"
        enrichment_watchlist_file = "/tmp/watchlist.txt"
        enrichment_watchlist_file_status = "OK"
        enrichment_write_mode = "replace-date"
        dashboard_fallback_to_reports = 1
        dashboard_run_acceptance_report = 0
        enrichment_effective_status = "PLANNING_ONLY"
        warnings = ()
        date_status = "OK"
        status = "OK"

    monkeypatch.setattr(
        cli,
        "inspect_scheduler_dashboard_config",
        lambda config_path, effective_today: _Inspection(),
    )
    monkeypatch.setattr(
        cli,
        "run_scheduler_config",
        lambda config_path: (_ for _ in ()).throw(
            AssertionError("run_scheduler_config should not be called in inspect mode")
        ),
    )

    code = cli.main(
        [
            "--config",
            "/tmp/scheduler.json",
            "--inspect-dashboard-config",
            "--effective-date",
            "2026-05-23",
        ]
    )

    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY scheduler_dashboard_config.enabled=1" in captured.out
    assert "SUMMARY scheduler_dashboard_config.ecosystem_code=DATACENTER" in captured.out
    assert "SUMMARY scheduler_dashboard_config.dashboard_db=/tmp/ecosystem_dashboard.db" in captured.out
    assert "SUMMARY scheduler_dashboard_config.reports_dir=/tmp/swing_reports" in captured.out
    assert "SUMMARY scheduler_dashboard_config.html_output_dir=/tmp/html" in captured.out
    assert "SUMMARY scheduler_dashboard_config.reports_reference_enabled=0" in captured.out
    assert "SUMMARY scheduler_dashboard_config.reports_reference_db=/tmp/reports_reference.db" in captured.out
    assert "SUMMARY scheduler_dashboard_config.reports_reference_html_output_dir=/tmp/html" in captured.out
    assert "SUMMARY scheduler_dashboard_config.expected_report_date=2026-05-22" in captured.out
    assert (
        "SUMMARY scheduler_dashboard_config.expected_html_output_path="
        "/tmp/html/datacenter_dashboard_2026-05-22.html"
    ) in captured.out
    assert (
        "SUMMARY scheduler_dashboard_config.reports_reference_expected_html_output_path="
        "/tmp/html/datacenter_dashboard_reports_reference_2026-05-22.html"
    ) in captured.out
    assert "SUMMARY scheduler_dashboard_config.mode=replace-date" in captured.out
    assert "SUMMARY scheduler_dashboard_config.render_html=1" in captured.out
    assert "SUMMARY scheduler_dashboard_config.usa_enabled=1" in captured.out
    assert "SUMMARY scheduler_dashboard_config.datacenter_pipeline_enabled=1" in captured.out
    assert "SUMMARY scheduler_dashboard_config.skip_next_run=0" in captured.out
    assert "SUMMARY scheduler_dashboard_config.dashboard_source_mode=reports" in captured.out
    assert "SUMMARY scheduler_dashboard_config.enrichment_enabled=0" in captured.out
    assert "SUMMARY scheduler_dashboard_config.enrichment_apply_migrations=0" in captured.out
    assert (
        "SUMMARY scheduler_dashboard_config.enrichment_taxonomy_version=DC_TAXONOMY_FULL_V1"
        in captured.out
    )
    assert "SUMMARY scheduler_dashboard_config.enrichment_watchlist_file=/tmp/watchlist.txt" in captured.out
    assert "SUMMARY scheduler_dashboard_config.enrichment_watchlist_file_status=OK" in captured.out
    assert "SUMMARY scheduler_dashboard_config.enrichment_write_mode=replace-date" in captured.out
    assert "SUMMARY scheduler_dashboard_config.dashboard_fallback_to_reports=1" in captured.out
    assert "SUMMARY scheduler_dashboard_config.dashboard_run_acceptance_report=0" in captured.out
    assert "SUMMARY scheduler_dashboard_config.enrichment_effective_status=PLANNING_ONLY" in captured.out
    assert "SUMMARY scheduler_dashboard_config.date_status=OK" in captured.out
    assert "SUMMARY scheduler_dashboard_config.status=OK" in captured.out


def test_scheduler_cli_inspect_dashboard_config_invalid_effective_date_fails(
    monkeypatch, capsys
):
    monkeypatch.setattr(
        cli,
        "inspect_scheduler_dashboard_config",
        lambda config_path, effective_today: (_ for _ in ()).throw(
            ValueError("Invalid isoformat string: 'bad-date'")
        ),
    )

    code = cli.main(
        [
            "--config",
            "/tmp/scheduler.json",
            "--inspect-dashboard-config",
            "--effective-date",
            "bad-date",
        ]
    )

    captured = capsys.readouterr()
    assert code == 2
    assert "SUMMARY scheduler_dashboard_config.status=FAILED" in captured.out
    assert "ERROR: Invalid isoformat string: 'bad-date'" in captured.out


def test_scheduler_cli_inspect_dashboard_config_without_plan_remains_backward_compatible(
    monkeypatch, capsys
):
    class _Inspection:
        enabled = 1
        ecosystem_code = "DATACENTER"
        dashboard_db = "/tmp/ecosystem_dashboard.db"
        reports_dir = "/tmp/swing_reports"
        html_output_dir = "/tmp/html"
        reports_reference_enabled = 0
        reports_reference_db = "/tmp/reports_reference.db"
        reports_reference_html_output_dir = "/tmp/html"
        expected_report_date = "2026-05-22"
        expected_html_output_path = "/tmp/html/datacenter_dashboard_2026-05-22.html"
        reports_reference_expected_html_output_path = (
            "/tmp/html/datacenter_dashboard_reports_reference_2026-05-22.html"
        )
        mode = "replace-date"
        render_html = 1
        usa_enabled = 1
        datacenter_pipeline_enabled = 1
        skip_next_run = 0
        dashboard_source_mode = "reports"
        enrichment_enabled = 0
        enrichment_apply_migrations = 0
        enrichment_taxonomy_version = "DC_TAXONOMY_FULL_V1"
        enrichment_watchlist_file = "/tmp/watchlist.txt"
        enrichment_watchlist_file_status = "OK"
        enrichment_write_mode = "replace-date"
        dashboard_fallback_to_reports = 1
        dashboard_run_acceptance_report = 0
        enrichment_effective_status = "PLANNING_ONLY"
        warnings = ()
        date_status = "OK"
        status = "OK"

    monkeypatch.setattr(
        cli,
        "inspect_scheduler_dashboard_config",
        lambda config_path, effective_today: _Inspection(),
    )
    monkeypatch.setattr(
        cli,
        "inspect_scheduler_enrichment_plan",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("inspect_scheduler_enrichment_plan should not be called")
        ),
    )

    code = cli.main(["--config", "/tmp/scheduler.json", "--inspect-dashboard-config"])
    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY scheduler_dashboard_config.status=OK" in captured.out
    assert "scheduler_enrichment_plan." not in captured.out


def test_scheduler_cli_inspect_dashboard_config_with_plan_prints_plan_lines(
    monkeypatch, capsys
):
    class _Inspection:
        enabled = 1
        ecosystem_code = "DATACENTER"
        dashboard_db = "/tmp/ecosystem_dashboard.db"
        reports_dir = "/tmp/swing_reports"
        html_output_dir = "/tmp/html"
        reports_reference_enabled = 1
        reports_reference_db = "/tmp/reports_reference.db"
        reports_reference_html_output_dir = "/tmp/reference_html"
        expected_report_date = "2026-05-22"
        expected_html_output_path = "/tmp/html/datacenter_dashboard_2026-05-22.html"
        reports_reference_expected_html_output_path = (
            "/tmp/reference_html/datacenter_dashboard_reports_reference_2026-05-22.html"
        )
        mode = "replace-date"
        render_html = 1
        usa_enabled = 1
        datacenter_pipeline_enabled = 1
        skip_next_run = 0
        dashboard_source_mode = "reports"
        enrichment_enabled = 0
        enrichment_apply_migrations = 0
        enrichment_taxonomy_version = "DC_TAXONOMY_FULL_V1"
        enrichment_watchlist_file = "/tmp/watchlist.txt"
        enrichment_watchlist_file_status = "OK"
        enrichment_write_mode = "replace-date"
        dashboard_fallback_to_reports = 1
        dashboard_run_acceptance_report = 0
        enrichment_effective_status = "PLANNING_ONLY"
        warnings = ()
        date_status = "OK"
        status = "OK"

    class _Plan:
        status = "OK"
        source_mode = "reports"
        enrichment_enabled = 0
        effective_status = "PLANNING_ONLY"
        expected_signal_date = "2026-05-22"
        analysis_db = "/tmp/analysis.db"
        analysis_db_status = "OK"
        dashboard_db = "/tmp/ecosystem_dashboard.db"
        reports_dir = "/tmp/swing_reports"
        reports_reference_db = "/tmp/reports_reference.db"
        watchlist_file = "/tmp/watchlist.txt"
        watchlist_file_status = "OK"
        taxonomy_version = "DC_TAXONOMY_FULL_V1"
        write_mode = "replace-date"
        apply_migrations = 0
        fallback_to_reports = 1
        run_acceptance_report = 0
        enrichment_json_output_path = "/tmp/swing_reports/datacenter_dashboard_enrichment_2026-05-22.json"
        html_output_path = "/tmp/html/datacenter_dashboard_2026-05-22.html"
        reports_reference_html_output_path = (
            "/tmp/reference_html/datacenter_dashboard_reports_reference_2026-05-22.html"
        )
        acceptance_report_output_path = ""
        stage_md_reports_generation = "1:DATACENTER_PIPELINE_ENABLED"
        stage_enrichment_write = "0:ENRICHMENT_NOT_ENABLED"
        stage_enrichment_audit = "0:ENRICHMENT_NOT_ENABLED"
        stage_enrichment_export_json = "0:ENRICHMENT_NOT_ENABLED"
        stage_structured_dashboard_build = "0:REPORTS_MODE_REMAINS_ACTIVE"
        stage_reports_reference_build = "1:FOLLOWS_STRUCTURED_BUILD"
        stage_html_render = "1:CURRENT_RENDER_HTML_CONFIG"
        stage_acceptance_report = "0:CONFIG_DISABLED"
        stage_fallback_reports_build = "1:FALLBACK_ENABLED"
        warnings = ()

    monkeypatch.setattr(
        cli,
        "inspect_scheduler_dashboard_config",
        lambda config_path, effective_today: _Inspection(),
    )
    monkeypatch.setattr(
        cli,
        "inspect_scheduler_enrichment_plan",
        lambda config_path, effective_today: _Plan(),
    )
    monkeypatch.setattr(
        cli,
        "run_scheduler_config",
        lambda config_path: (_ for _ in ()).throw(
            AssertionError("run_scheduler_config should not be called in inspect mode")
        ),
    )

    code = cli.main(
        [
            "--config",
            "/tmp/scheduler.json",
            "--inspect-dashboard-config",
            "--show-enrichment-plan",
            "--effective-date",
            "2026-05-23",
        ]
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "SUMMARY scheduler_enrichment_plan.status=OK" in captured.out
    assert "SUMMARY scheduler_enrichment_plan.source_mode=reports" in captured.out
    assert "SUMMARY scheduler_dashboard_config.reports_reference_enabled=1" in captured.out
    assert "SUMMARY scheduler_dashboard_config.reports_reference_db=/tmp/reports_reference.db" in captured.out
    assert "SUMMARY scheduler_dashboard_config.reports_reference_html_output_dir=/tmp/reference_html" in captured.out
    assert (
        "SUMMARY scheduler_dashboard_config.reports_reference_expected_html_output_path="
        "/tmp/reference_html/datacenter_dashboard_reports_reference_2026-05-22.html"
    ) in captured.out
    assert "SUMMARY scheduler_enrichment_plan.reports_reference_db=/tmp/reports_reference.db" in captured.out
    assert (
        "SUMMARY scheduler_enrichment_plan.reports_reference_html_output_path="
        "/tmp/reference_html/datacenter_dashboard_reports_reference_2026-05-22.html"
    ) in captured.out
    assert "SUMMARY scheduler_enrichment_plan.stage.md_reports_generation=1:DATACENTER_PIPELINE_ENABLED" in captured.out
    assert "SUMMARY scheduler_enrichment_plan.stage.enrichment_write=0:ENRICHMENT_NOT_ENABLED" in captured.out
    assert (
        "SUMMARY scheduler_enrichment_plan.stage.reports_reference_build="
        "1:FOLLOWS_STRUCTURED_BUILD"
    ) in captured.out
