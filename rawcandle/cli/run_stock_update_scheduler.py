from __future__ import annotations

import argparse
import datetime
from typing import List, Optional

from rawcandle.scheduler.runner import (
    SchedulerAlreadyRunningError,
    inspect_scheduler_dashboard_config,
    inspect_scheduler_enrichment_plan,
    run_scheduler_config,
)
from services.stock_update_service import STATUS_FAILED, STATUS_OK, STATUS_OK_WITH_WARNINGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run stock update scheduler config sequentially."
    )
    parser.add_argument("--config", required=True)
    parser.add_argument("--inspect-dashboard-config", action="store_true")
    parser.add_argument("--show-enrichment-plan", action="store_true")
    parser.add_argument("--effective-date")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    if args.inspect_dashboard_config:
        effective_today = args.effective_date
        if effective_today is None:
            effective_today = datetime.datetime.now().strftime("%Y-%m-%d")
        try:
            inspection = inspect_scheduler_dashboard_config(
                config_path=args.config,
                effective_today=effective_today,
            )
            enrichment_plan = None
            if args.show_enrichment_plan:
                enrichment_plan = inspect_scheduler_enrichment_plan(
                    config_path=args.config,
                    effective_today=effective_today,
                )
        except ValueError as exc:
            print("SUMMARY scheduler_dashboard_config.status=FAILED")
            print(f"ERROR: {exc}")
            return 2
        print(f"SUMMARY scheduler_dashboard_config.enabled={inspection.enabled}")
        print(
            "SUMMARY scheduler_dashboard_config.ecosystem_code="
            f"{inspection.ecosystem_code}"
        )
        print(f"SUMMARY scheduler_dashboard_config.dashboard_db={inspection.dashboard_db}")
        print(f"SUMMARY scheduler_dashboard_config.reports_dir={inspection.reports_dir}")
        print(
            "SUMMARY scheduler_dashboard_config.html_output_dir="
            f"{inspection.html_output_dir}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.reports_reference_enabled="
            f"{inspection.reports_reference_enabled}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.reports_reference_db="
            f"{inspection.reports_reference_db}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.reports_reference_html_output_dir="
            f"{inspection.reports_reference_html_output_dir}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.expected_report_date="
            f"{inspection.expected_report_date}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.expected_html_output_path="
            f"{inspection.expected_html_output_path}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.reports_reference_expected_html_output_path="
            f"{inspection.reports_reference_expected_html_output_path}"
        )
        print(f"SUMMARY scheduler_dashboard_config.mode={inspection.mode}")
        print(f"SUMMARY scheduler_dashboard_config.render_html={inspection.render_html}")
        print(f"SUMMARY scheduler_dashboard_config.usa_enabled={inspection.usa_enabled}")
        print(
            "SUMMARY scheduler_dashboard_config.datacenter_pipeline_enabled="
            f"{inspection.datacenter_pipeline_enabled}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.skip_next_run="
            f"{inspection.skip_next_run}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.dashboard_source_mode="
            f"{inspection.dashboard_source_mode}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.enrichment_enabled="
            f"{inspection.enrichment_enabled}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.enrichment_apply_migrations="
            f"{inspection.enrichment_apply_migrations}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.enrichment_taxonomy_version="
            f"{inspection.enrichment_taxonomy_version}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.enrichment_watchlist_file="
            f"{inspection.enrichment_watchlist_file}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.enrichment_watchlist_file_status="
            f"{inspection.enrichment_watchlist_file_status}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.enrichment_write_mode="
            f"{inspection.enrichment_write_mode}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.dashboard_fallback_to_reports="
            f"{inspection.dashboard_fallback_to_reports}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.dashboard_run_acceptance_report="
            f"{inspection.dashboard_run_acceptance_report}"
        )
        print(
            "SUMMARY scheduler_dashboard_config.enrichment_effective_status="
            f"{inspection.enrichment_effective_status}"
        )
        for warning in inspection.warnings:
            print(f"SUMMARY scheduler_dashboard_config.warning={warning}")
        print(f"SUMMARY scheduler_dashboard_config.date_status={inspection.date_status}")
        print(f"SUMMARY scheduler_dashboard_config.status={inspection.status}")
        if enrichment_plan is not None:
            print(f"SUMMARY scheduler_enrichment_plan.status={enrichment_plan.status}")
            print(
                "SUMMARY scheduler_enrichment_plan.source_mode="
                f"{enrichment_plan.source_mode}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.enrichment_enabled="
                f"{enrichment_plan.enrichment_enabled}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.effective_status="
                f"{enrichment_plan.effective_status}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.expected_signal_date="
                f"{enrichment_plan.expected_signal_date}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.analysis_db="
                f"{enrichment_plan.analysis_db}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.analysis_db_status="
                f"{enrichment_plan.analysis_db_status}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.dashboard_db="
                f"{enrichment_plan.dashboard_db}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.reports_dir="
                f"{enrichment_plan.reports_dir}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.reports_reference_db="
                f"{enrichment_plan.reports_reference_db}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.watchlist_file="
                f"{enrichment_plan.watchlist_file}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.watchlist_file_status="
                f"{enrichment_plan.watchlist_file_status}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.taxonomy_version="
                f"{enrichment_plan.taxonomy_version}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.write_mode="
                f"{enrichment_plan.write_mode}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.apply_migrations="
                f"{enrichment_plan.apply_migrations}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.fallback_to_reports="
                f"{enrichment_plan.fallback_to_reports}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.run_acceptance_report="
                f"{enrichment_plan.run_acceptance_report}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.enrichment_json_output_path="
                f"{enrichment_plan.enrichment_json_output_path}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.html_output_path="
                f"{enrichment_plan.html_output_path}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.reports_reference_html_output_path="
                f"{enrichment_plan.reports_reference_html_output_path}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.acceptance_report_output_path="
                f"{enrichment_plan.acceptance_report_output_path}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.stage.md_reports_generation="
                f"{enrichment_plan.stage_md_reports_generation}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.stage.enrichment_write="
                f"{enrichment_plan.stage_enrichment_write}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.stage.enrichment_audit="
                f"{enrichment_plan.stage_enrichment_audit}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.stage.enrichment_export_json="
                f"{enrichment_plan.stage_enrichment_export_json}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.stage.structured_dashboard_build="
                f"{enrichment_plan.stage_structured_dashboard_build}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.stage.reports_reference_build="
                f"{enrichment_plan.stage_reports_reference_build}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.stage.html_render="
                f"{enrichment_plan.stage_html_render}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.stage.acceptance_report="
                f"{enrichment_plan.stage_acceptance_report}"
            )
            print(
                "SUMMARY scheduler_enrichment_plan.stage.fallback_reports_build="
                f"{enrichment_plan.stage_fallback_reports_build}"
            )
            for warning in enrichment_plan.warnings:
                print(f"SUMMARY scheduler_enrichment_plan.warning={warning}")
        return 0
    try:
        result = run_scheduler_config(config_path=args.config)
    except SchedulerAlreadyRunningError as exc:
        print("SUMMARY scheduler_status=FAILED")
        print("SUMMARY scheduler_skipped=0")
        print("SUMMARY scheduler_skip_reason=")
        print(f"SUMMARY error={exc}")
        return 1

    markets_ok = sum(1 for item in result.market_results if item.summary_status == STATUS_OK)
    markets_ok_with_warnings = sum(
        1 for item in result.market_results if item.summary_status == STATUS_OK_WITH_WARNINGS
    )
    markets_failed = sum(
        1 for item in result.market_results if item.summary_status == STATUS_FAILED
    )

    print(f"SUMMARY scheduler_status={result.overall_status}")
    print(f"SUMMARY markets_enabled={','.join(result.enabled_markets)}")
    print(f"SUMMARY markets_total={len(result.market_results)}")
    print(f"SUMMARY markets_ok={markets_ok}")
    print(f"SUMMARY markets_ok_with_warnings={markets_ok_with_warnings}")
    print(f"SUMMARY markets_failed={markets_failed}")
    print(f"SUMMARY summary_json_path={result.summary_json_path}")
    print(f"SUMMARY scheduler_skipped={1 if result.skipped else 0}")
    print(f"SUMMARY scheduler_skip_reason={result.skip_reason or ''}")
    print(f"SUMMARY technical_relevance.attempted={result.technical_relevance_attempted}")
    print(f"SUMMARY technical_relevance.enabled={str(result.technical_relevance_enabled).lower()}")
    print(f"SUMMARY technical_relevance.status={result.technical_relevance_status}")
    print(f"SUMMARY technical_relevance.market={result.technical_relevance_market}")
    print(f"SUMMARY technical_relevance.run_id={result.technical_relevance_run_id}")
    print(f"SUMMARY technical_relevance.ticker_count={result.technical_relevance_ticker_count}")
    print(f"SUMMARY technical_relevance.start_date={result.technical_relevance_start_date}")
    print(f"SUMMARY technical_relevance.end_date={result.technical_relevance_end_date}")
    print(
        "SUMMARY technical_relevance.records_written="
        f"{result.technical_relevance_records_written}"
    )
    print(
        "SUMMARY technical_relevance.relevant_count="
        f"{result.technical_relevance_relevant_count}"
    )
    print(
        "SUMMARY technical_relevance.weak_context_count="
        f"{result.technical_relevance_weak_context_count}"
    )
    print(f"SUMMARY technical_relevance.noise_count={result.technical_relevance_noise_count}")
    print(
        "SUMMARY technical_relevance.unknown_signal_count="
        f"{result.technical_relevance_unknown_signal_count}"
    )
    print(
        "SUMMARY technical_relevance.missing_dow_context_count="
        f"{result.technical_relevance_missing_dow_context_count}"
    )
    print(
        "SUMMARY technical_relevance.missing_bar_index_count="
        f"{result.technical_relevance_missing_bar_index_count}"
    )
    print(
        "SUMMARY technical_relevance.duration_seconds="
        f"{result.technical_relevance_duration_seconds}"
    )
    print(f"SUMMARY technical_relevance.skip_reason={result.technical_relevance_skip_reason}")
    print(f"SUMMARY datacenter_pipeline.attempted={result.datacenter_pipeline_attempted}")
    print(f"SUMMARY datacenter_pipeline.status={result.datacenter_pipeline_status}")
    print(f"SUMMARY datacenter_pipeline.market={result.datacenter_pipeline_market}")
    print(f"SUMMARY datacenter_pipeline.signal_date={result.datacenter_pipeline_signal_date}")
    print(
        "SUMMARY datacenter_pipeline.signal_date_source="
        f"{result.datacenter_pipeline_signal_date_source}"
    )
    print(
        "SUMMARY datacenter_pipeline.signal_date_resolution="
        f"{result.datacenter_pipeline_signal_date_resolution}"
    )
    print(
        "SUMMARY datacenter_pipeline.requested_calendar_signal_date="
        f"{result.datacenter_pipeline_requested_calendar_signal_date}"
    )
    print(
        "SUMMARY datacenter_pipeline.audit_validation_status="
        f"{result.datacenter_pipeline_audit_validation_status}"
    )
    print(f"SUMMARY datacenter_pipeline.log_path={result.datacenter_pipeline_log_path}")
    print(
        "SUMMARY datacenter_pipeline.daily_report_path="
        f"{result.datacenter_pipeline_daily_report_path or 'NONE'}"
    )
    print(
        "SUMMARY datacenter_pipeline.daily_report_csv_path="
        f"{result.datacenter_pipeline_daily_report_csv_path or 'NONE'}"
    )
    print(
        "SUMMARY datacenter_pipeline.rolling_30_report_path="
        f"{result.datacenter_pipeline_rolling_30_report_path or 'NONE'}"
    )
    print(
        "SUMMARY datacenter_pipeline.rolling_30_report_csv_path="
        f"{result.datacenter_pipeline_rolling_30_report_csv_path or 'NONE'}"
    )
    print(
        "SUMMARY datacenter_pipeline.rolling_5_report_path="
        f"{result.datacenter_pipeline_rolling_5_report_path or 'NONE'}"
    )
    print(
        "SUMMARY datacenter_pipeline.rolling_5_report_csv_path="
        f"{result.datacenter_pipeline_rolling_5_report_csv_path or 'NONE'}"
    )
    print(
        "SUMMARY datacenter_pipeline.rolling_2_report_path="
        f"{result.datacenter_pipeline_rolling_2_report_path or 'NONE'}"
    )
    print(
        "SUMMARY datacenter_pipeline.rolling_2_report_csv_path="
        f"{result.datacenter_pipeline_rolling_2_report_csv_path or 'NONE'}"
    )
    print(
        "SUMMARY datacenter_pipeline.weekly_report_path="
        f"{result.datacenter_pipeline_weekly_report_path or 'NONE'}"
    )
    print(
        "SUMMARY datacenter_pipeline.weekly_report_csv_path="
        f"{result.datacenter_pipeline_weekly_report_csv_path or 'NONE'}"
    )
    print(f"SUMMARY datacenter_pipeline.error={result.datacenter_pipeline_error}")
    print(f"SUMMARY v3_reports.attempted={result.v3_reports_attempted}")
    print(f"SUMMARY v3_reports.status={result.v3_reports_status}")
    print(f"SUMMARY v3_reports.run_id={result.v3_reports_run_id}")
    print(f"SUMMARY v3_reports.signal_date={result.v3_reports_signal_date}")
    print(f"SUMMARY v3_reports.output_dir={result.v3_reports_output_dir or 'NONE'}")
    print(
        "SUMMARY v3_reports.daily_report_path="
        f"{result.v3_reports_daily_report_path or 'NONE'}"
    )
    print(
        "SUMMARY v3_reports.rolling_30_report_path="
        f"{result.v3_reports_rolling_30_report_path or 'NONE'}"
    )
    print(
        "SUMMARY v3_reports.rolling_5_report_path="
        f"{result.v3_reports_rolling_5_report_path or 'NONE'}"
    )
    print(
        "SUMMARY v3_reports.rolling_2_report_path="
        f"{result.v3_reports_rolling_2_report_path or 'NONE'}"
    )
    print(f"SUMMARY v3_reports.error={result.v3_reports_error}")
    print(f"SUMMARY datacenter_dashboard.attempted={result.datacenter_dashboard_attempted}")
    print(f"SUMMARY datacenter_dashboard.status={result.datacenter_dashboard_status}")
    print(f"SUMMARY datacenter_dashboard.dashboard_db={result.datacenter_dashboard_dashboard_db}")
    print(f"SUMMARY datacenter_dashboard.report_date={result.datacenter_dashboard_report_date}")
    print(
        "SUMMARY datacenter_dashboard.md_reports_status="
        f"{result.datacenter_dashboard_md_reports_status}"
    )
    print(
        "SUMMARY datacenter_dashboard.source_reports_available="
        f"{result.datacenter_dashboard_source_reports_available}"
    )
    print(
        "SUMMARY datacenter_dashboard.html_output_path="
        f"{result.datacenter_dashboard_html_output_path}"
    )
    print(
        "SUMMARY datacenter_dashboard.markdown_output_path="
        f"{result.datacenter_dashboard_markdown_output_path}"
    )
    print(
        "SUMMARY datacenter_dashboard.markdown_render_status="
        f"{result.datacenter_dashboard_markdown_render_status}"
    )
    print(f"SUMMARY datacenter_dashboard.run_id={result.datacenter_dashboard_run_id}")
    print(f"SUMMARY datacenter_dashboard.skip_reason={result.datacenter_dashboard_skip_reason}")
    print(
        "SUMMARY datacenter_dashboard_source_mode="
        f"{result.datacenter_dashboard_source_mode}"
    )
    print(
        "SUMMARY datacenter_dashboard.reports_reference_status="
        f"{result.datacenter_dashboard_reports_reference_status}"
    )
    print(
        "SUMMARY datacenter_dashboard.reports_reference_run_id="
        f"{result.datacenter_dashboard_reports_reference_run_id}"
    )
    print(
        "SUMMARY datacenter_dashboard.reports_reference_dashboard_db="
        f"{result.datacenter_dashboard_reports_reference_dashboard_db}"
    )
    print(
        "SUMMARY datacenter_dashboard.reports_reference_html_output_path="
        f"{result.datacenter_dashboard_reports_reference_html_output_path}"
    )
    print(
        "SUMMARY datacenter_dashboard.reports_reference_markdown_output_path="
        f"{result.datacenter_dashboard_reports_reference_markdown_output_path}"
    )
    print(
        "SUMMARY datacenter_dashboard.reports_reference_markdown_render_status="
        f"{result.datacenter_dashboard_reports_reference_markdown_render_status}"
    )
    print(
        "SUMMARY datacenter_enrichment.attempted="
        f"{result.datacenter_enrichment_attempted}"
    )
    print(
        "SUMMARY datacenter_enrichment.status="
        f"{result.datacenter_enrichment_status}"
    )
    print(
        "SUMMARY datacenter_enrichment.readiness="
        f"{result.datacenter_enrichment_readiness}"
    )
    print(
        "SUMMARY datacenter_enrichment.run_id="
        f"{result.datacenter_enrichment_run_id}"
    )
    print(
        "SUMMARY datacenter_dashboard.enrichment_export_status="
        f"{result.datacenter_dashboard_enrichment_export_status}"
    )
    print(
        "SUMMARY datacenter_dashboard.structured_build_status="
        f"{result.datacenter_dashboard_structured_build_status}"
    )
    print(
        "SUMMARY datacenter_dashboard.acceptance_report_status="
        f"{result.datacenter_dashboard_acceptance_report_status}"
    )
    print(
        "SUMMARY datacenter_dashboard.acceptance_report_blockers="
        f"{result.datacenter_dashboard_acceptance_report_blockers}"
    )
    print(
        "SUMMARY datacenter_dashboard.acceptance_report_recommendation="
        f"{result.datacenter_dashboard_acceptance_report_recommendation}"
    )
    print(
        "SUMMARY datacenter_dashboard.fallback_used="
        f"{result.datacenter_dashboard_fallback_used}"
    )
    print(
        "SUMMARY datacenter_dashboard.final_source_mode="
        f"{result.datacenter_dashboard_final_source_mode}"
    )
    print(f"SUMMARY datacenter_dashboard.error={result.datacenter_dashboard_error}")

    for market_result in result.market_results:
        print(f"SUMMARY market.{market_result.market}.status={market_result.summary_status}")
        print(f"SUMMARY market.{market_result.market}.log_path={market_result.log_path}")

    return 0 if result.overall_status == STATUS_OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
