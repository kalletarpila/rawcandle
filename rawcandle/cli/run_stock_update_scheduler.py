from __future__ import annotations

import argparse
from typing import List, Optional

from rawcandle.scheduler.runner import SchedulerAlreadyRunningError, run_scheduler_config
from services.stock_update_service import STATUS_FAILED, STATUS_OK, STATUS_OK_WITH_WARNINGS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run stock update scheduler config sequentially."
    )
    parser.add_argument("--config", required=True)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
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
    print(f"SUMMARY datacenter_dashboard.run_id={result.datacenter_dashboard_run_id}")
    print(f"SUMMARY datacenter_dashboard.skip_reason={result.datacenter_dashboard_skip_reason}")
    print(f"SUMMARY datacenter_dashboard.error={result.datacenter_dashboard_error}")

    for market_result in result.market_results:
        print(f"SUMMARY market.{market_result.market}.status={market_result.summary_status}")
        print(f"SUMMARY market.{market_result.market}.log_path={market_result.log_path}")

    return 0 if result.overall_status == STATUS_OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
