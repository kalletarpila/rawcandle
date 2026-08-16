from __future__ import annotations

import argparse
from typing import List, Optional

from rawcandle.scheduler.runner import (
    SchedulerAlreadyRunningError,
    run_scheduler_config,
)
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
    print(f"SUMMARY ec_source_layer.attempted={result.ec_source_layer_attempted}")
    print(f"SUMMARY ec_source_layer.status={result.ec_source_layer_status}")
    print(
        "SUMMARY ec_source_layer.log_path="
        f"{result.ec_source_layer_log_path or 'NONE'}"
    )
    print(
        "SUMMARY ec_source_layer.signal_date="
        f"{result.ec_source_layer_signal_date or 'NONE'}"
    )
    print(
        "SUMMARY ec_source_layer.refresh_mode="
        f"{result.ec_source_layer_refresh_mode or 'NONE'}"
    )
    print(
        "SUMMARY ec_source_layer.skipped_reason="
        f"{result.ec_source_layer_skipped_reason or 'NONE'}"
    )
    print(
        "SUMMARY ec_source_layer.backup_path="
        f"{result.ec_source_layer_backup_path or 'NONE'}"
    )
    print(
        "SUMMARY ec_source_layer.coverage_status="
        f"{result.ec_source_layer_coverage_status or 'NONE'}"
    )
    print(
        "SUMMARY ec_source_layer.parity_status="
        f"{result.ec_source_layer_parity_status or 'NONE'}"
    )
    print(
        "SUMMARY ec_source_layer.total_mismatch_count="
        f"{result.ec_source_layer_total_mismatch_count}"
    )
    print(f"SUMMARY ec_source_layer.ticker_rows={result.ec_source_layer_ticker_rows}")
    print(
        "SUMMARY ec_source_layer.group_signal_rows="
        f"{result.ec_source_layer_group_signal_rows}"
    )
    print(
        "SUMMARY ec_source_layer.synthetic_ohlc_rows="
        f"{result.ec_source_layer_synthetic_ohlc_rows}"
    )
    print(
        "SUMMARY ec_source_layer.group_index_rows="
        f"{result.ec_source_layer_group_index_rows}"
    )
    print(
        "SUMMARY ec_source_layer.watermark_rows="
        f"{result.ec_source_layer_watermark_rows}"
    )
    print(f"SUMMARY ec_source_layer.error={result.ec_source_layer_error or 'NONE'}")

    print(f"SUMMARY swingmaster_fundamentals.attempted={result.swingmaster_fundamentals_attempted}")
    print(f"SUMMARY swingmaster_fundamentals.result_check_status={result.swingmaster_result_check_status}")
    print(f"SUMMARY swingmaster_fundamentals.result_check_exit_code={result.swingmaster_result_check_exit_code if result.swingmaster_result_check_exit_code is not None else 'NONE'}")
    print(f"SUMMARY swingmaster_fundamentals.result_check_log_path={result.swingmaster_result_check_log_path or 'NONE'}")
    print(f"SUMMARY swingmaster_fundamentals.result_check_plan_json={result.swingmaster_result_check_plan_json}")
    print(f"SUMMARY swingmaster_fundamentals.result_check_candidate_count={result.swingmaster_result_check_candidate_count}")
    print(f"SUMMARY swingmaster_fundamentals.active_tickers={result.swingmaster_active_tickers}")
    print(f"SUMMARY swingmaster_fundamentals.7_day_watch_window_count={result.swingmaster_7_day_watch_window_count}")
    print(f"SUMMARY swingmaster_fundamentals.due_for_result_check={result.swingmaster_due_for_result_check}")
    print(f"SUMMARY swingmaster_fundamentals.future_confirmation_provider_calls_now={result.swingmaster_future_confirmation_provider_calls_now}")
    print(f"SUMMARY swingmaster_fundamentals.failure_retries={result.swingmaster_failure_retries}")
    print(f"SUMMARY swingmaster_fundamentals.maintenance_selected={result.swingmaster_maintenance_selected}")
    print(f"SUMMARY swingmaster_fundamentals.total_unique_provider_check_tickers={result.swingmaster_total_unique_provider_check_tickers}")
    print(f"SUMMARY swingmaster_fundamentals.maintenance_backlog_remaining={result.swingmaster_maintenance_backlog_remaining}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_attempted={result.swingmaster_weekly_update_attempted}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_status={result.swingmaster_weekly_update_status}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_exit_code={result.swingmaster_weekly_update_exit_code if result.swingmaster_weekly_update_exit_code is not None else 'NONE'}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_log_path={result.swingmaster_weekly_update_log_path or 'NONE'}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_plan_json={result.swingmaster_weekly_update_plan_json}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_planned_candidates={result.swingmaster_weekly_update_planned_candidates}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_successful_candidates={result.swingmaster_weekly_update_successful_candidates}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_failed_candidates={result.swingmaster_weekly_update_failed_candidates}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_retryable_candidates={result.swingmaster_weekly_update_retryable_candidates}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_v2_canonical_writes={result.swingmaster_weekly_update_v2_canonical_writes}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_v2_provenance_writes={result.swingmaster_weekly_update_v2_provenance_writes}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_v2_retry={result.swingmaster_weekly_update_v2_retry}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_v2_blocked={result.swingmaster_weekly_update_v2_blocked}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_provider_calls={result.swingmaster_weekly_update_provider_calls}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_source_a_count={result.swingmaster_weekly_update_source_a_count}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_source_b_due_count={result.swingmaster_weekly_update_source_b_due_count}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_source_b_only_count={result.swingmaster_weekly_update_source_b_only_count}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_source_overlap_count={result.swingmaster_weekly_update_source_overlap_count}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_execution_scope_hash={result.swingmaster_weekly_update_execution_scope_hash}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_merged_work_unit_count={result.swingmaster_weekly_update_merged_work_unit_count}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_duplicate_merge_count={result.swingmaster_weekly_update_duplicate_merge_count}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_floor_excluded_count={result.swingmaster_weekly_update_floor_excluded_count}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_executable_after_scope_count={result.swingmaster_weekly_update_executable_after_scope_count}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_followup_metadata_errors={result.swingmaster_weekly_update_followup_metadata_errors}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_integrated_output_json={result.swingmaster_weekly_update_integrated_output_json}")
    print(f"SUMMARY swingmaster_fundamentals.result_check_error={result.swingmaster_result_check_error}")
    print(f"SUMMARY swingmaster_fundamentals.weekly_update_error={result.swingmaster_weekly_update_error}")

    for market_result in result.market_results:
        print(f"SUMMARY market.{market_result.market}.status={market_result.summary_status}")
        print(f"SUMMARY market.{market_result.market}.log_path={market_result.log_path}")

    return 0 if result.overall_status == STATUS_OK else 1


if __name__ == "__main__":
    raise SystemExit(main())
