from __future__ import annotations

import datetime
import errno
import fcntl
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import time
from contextlib import contextmanager, redirect_stdout
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import IO, Iterator, List, Optional
from zoneinfo import ZoneInfo

from main import RawCandleApp, _today_exclusive_end_date
from rawcandle.cli.run_ec_source_layer_backfill import run_ec_source_layer_backfill
from rawcandle.cli.run_ec_source_layer_refresh import run_ec_source_layer_refresh
from rawcandle.cli.plan_ec_source_layer_build import _read_taxonomy_csv
from rawcandle.io_atomic import write_text_atomic
from rawcandle.scheduler.config import (
    StockUpdateSchedulerConfig,
    read_scheduler_config,
    write_scheduler_config,
)
from rawcandle.technical_signal_relevance_persistence import (
    apply_technical_signal_relevance_migration,
    read_relevance_run,
    resolve_created_at_utc,
)
from rawcandle.technical_signal_relevance_service import (
    run_technical_signal_relevance_for_tickers,
)
from services.stock_update_service import (
    STATUS_FAILED,
    STATUS_OK,
    STATUS_OK_WITH_WARNINGS,
    format_stock_update_summary_lines,
)


@dataclass
class ScheduledMarketRunResult:
    market: str
    started_at_utc: str
    finished_at_utc: str
    exit_code: int
    summary_status: str
    log_path: str
    summary_lines: List[str]
    error: Optional[str] = None


@dataclass
class ScheduledStockUpdateRunResult:
    started_at_utc: str
    finished_at_utc: str
    config_path: str
    enabled_markets: List[str]
    market_results: List[ScheduledMarketRunResult] = field(default_factory=list)
    overall_status: str = STATUS_OK
    summary_json_path: str = ""
    skipped: bool = False
    skip_reason: Optional[str] = None
    technical_relevance_attempted: int = 0
    technical_relevance_enabled: bool = False
    technical_relevance_status: str = "DISABLED"
    technical_relevance_market: str = "NONE"
    technical_relevance_run_id: str = "NONE"
    technical_relevance_ticker_count: int = 0
    technical_relevance_start_date: str = "NONE"
    technical_relevance_end_date: str = "NONE"
    technical_relevance_requested_calendar_signal_date: str = "NONE"
    technical_relevance_end_date_source: str = "NONE"
    technical_relevance_end_date_resolution: str = "NONE"
    technical_relevance_end_date_min_price_ticker_count: int = 0
    technical_relevance_end_date_candidate_count: int = 0
    technical_relevance_ticker_valid_date_count: int = 0
    technical_relevance_records_written: int = 0
    technical_relevance_relevant_count: int = 0
    technical_relevance_weak_context_count: int = 0
    technical_relevance_noise_count: int = 0
    technical_relevance_unknown_signal_count: int = 0
    technical_relevance_missing_dow_context_count: int = 0
    technical_relevance_missing_bar_index_count: int = 0
    technical_relevance_duration_seconds: str = "0.000"
    technical_relevance_skip_reason: str = ""
    technical_relevance_error: str = ""
    datacenter_pipeline_attempted: int = 0
    datacenter_pipeline_status: str = "SKIPPED"
    datacenter_pipeline_market: str = "usa"
    datacenter_pipeline_audit_validation_status: str = "SKIPPED"
    datacenter_pipeline_log_path: str = ""
    datacenter_pipeline_signal_date: str = "NONE"
    datacenter_pipeline_signal_date_source: str = "NONE"
    datacenter_pipeline_signal_date_resolution: str = "NONE"
    datacenter_pipeline_requested_calendar_signal_date: str = "NONE"
    datacenter_pipeline_configured_taxonomy_version: str = ""
    datacenter_pipeline_configured_taxonomy_csv: str = ""
    datacenter_pipeline_configured_taxonomy_sha256: str = ""
    datacenter_pipeline_derived_taxonomy_row_count: int = 0
    datacenter_pipeline_derived_ticker_count: int = 0
    datacenter_pipeline_derived_group_count: int = 0
    datacenter_pipeline_derived_synthetic_group_count: int = 0
    datacenter_pipeline_daily_report_path: Optional[str] = None
    datacenter_pipeline_daily_report_csv_path: Optional[str] = None
    datacenter_pipeline_rolling_30_report_path: Optional[str] = None
    datacenter_pipeline_rolling_30_report_csv_path: Optional[str] = None
    datacenter_pipeline_rolling_5_report_path: Optional[str] = None
    datacenter_pipeline_rolling_5_report_csv_path: Optional[str] = None
    datacenter_pipeline_rolling_2_report_path: Optional[str] = None
    datacenter_pipeline_rolling_2_report_csv_path: Optional[str] = None
    datacenter_pipeline_weekly_report_path: Optional[str] = None
    datacenter_pipeline_weekly_report_csv_path: Optional[str] = None
    datacenter_pipeline_error: str = ""
    watchlist_reconciliation_attempted: bool = False
    watchlist_reconciliation_status: str = "SKIPPED"
    watchlist_source_reference: str = "NONE"
    watchlist_source_sha256: str = "NONE"
    watchlist_source_member_count: int = 0
    watchlist_previous_member_count: int = 0
    watchlist_current_member_count: int = 0
    watchlist_added_count: int = 0
    watchlist_removed_count: int = 0
    watchlist_added_tickers: str = "[]"
    watchlist_removed_tickers: str = "[]"
    watchlist_reconciliation_error: str = "NONE"
    ec_source_layer_attempted: int = 0
    ec_source_layer_status: str = "SKIPPED"
    ec_source_layer_log_path: str = ""
    ec_source_layer_signal_date: str = "NONE"
    ec_source_layer_refresh_mode: str = "NONE"
    ec_source_layer_skipped_reason: str = "NONE"
    ec_source_layer_backup_path: str = "NONE"
    ec_source_layer_coverage_status: str = "NONE"
    ec_source_layer_parity_status: str = "NONE"
    ec_source_layer_total_mismatch_count: int = 0
    ec_source_layer_ticker_rows: int = 0
    ec_source_layer_group_signal_rows: int = 0
    ec_source_layer_synthetic_ohlc_rows: int = 0
    ec_source_layer_group_index_rows: int = 0
    ec_source_layer_watermark_rows: int = 0
    ec_source_layer_error: str = "NONE"
    ec_bridge_mode: str = "DISABLED"
    ec_bridge_reason: str = "INCREMENTAL_FEATURE_DISABLED"
    ec_bridge_required_start: str = "NONE"
    ec_bridge_required_end: str = "NONE"
    ec_bridge_status: str = "SKIPPED"
    ec_bridge_load_status: str = "NONE"
    ec_bridge_coverage_status: str = "NONE"
    ec_bridge_parity_status: str = "NONE"
    ec_bridge_retry_required: bool = False
    ec_bridge_exit_code: int | None = None
    ec_bridge_error: str = "NONE"
    ec_bridge_log: str = "NONE"
    ec_bridge_watermark_refresh_performed: bool = False
    ec_bridge_watchlist_membership_status: str = "UNKNOWN"
    ec_bridge_watchlist_sync_required: bool = False
    ec_bridge_watchlist_missing_in_loaded_count: int = 0
    ec_bridge_watchlist_loaded_only_count: int = 0
    datacenter_dc_status: str = "SKIPPED"
    datacenter_ec_status: str = "SKIPPED"
    datacenter_ec_retry_required: bool = False
    datacenter_taxonomy_version: str = ""
    datacenter_failed_component: str = "NONE"
    datacenter_safe_next_action: str = "NONE"
    swingmaster_fundamentals_attempted: int = 0
    swingmaster_result_check_status: str = "DISABLED"
    swingmaster_result_check_exit_code: int | None = None
    swingmaster_result_check_log_path: str = ""
    swingmaster_result_check_plan_json: str = "NONE"
    swingmaster_result_check_candidate_count: int = 0
    swingmaster_result_check_error: str = "NONE"
    swingmaster_active_tickers: int = 0
    swingmaster_7_day_watch_window_count: int = 0
    swingmaster_due_for_result_check: int = 0
    swingmaster_future_confirmation_provider_calls_now: int = 0
    swingmaster_failure_retries: int = 0
    swingmaster_maintenance_selected: int = 0
    swingmaster_total_unique_provider_check_tickers: int = 0
    swingmaster_maintenance_backlog_remaining: int = 0
    swingmaster_weekly_update_attempted: int = 0
    swingmaster_weekly_update_status: str = "SKIPPED"
    swingmaster_weekly_update_exit_code: int | None = None
    swingmaster_weekly_update_log_path: str = ""
    swingmaster_weekly_update_plan_json: str = "NONE"
    swingmaster_weekly_update_planned_candidates: int = 0
    swingmaster_weekly_update_successful_candidates: int = 0
    swingmaster_weekly_update_failed_candidates: int = 0
    swingmaster_weekly_update_retryable_candidates: int = 0
    swingmaster_weekly_update_error: str = "NONE"


class SchedulerAlreadyRunningError(RuntimeError):
    pass


@dataclass(frozen=True)
class DatacenterPostStepConfig:
    market: str
    taxonomy_csv: str
    taxonomy_version: str
    start_date: str
    index_base_date: str
    output_dir: str
    expected_ticker_count: int
    expected_group_count: int
    expected_synthetic_ohlc_count: int
    watchlist_file: str


@dataclass(frozen=True)
class DatacenterSignalDateResolution:
    signal_date: Optional[str]
    requested_calendar_signal_date: str
    signal_date_source: str
    signal_date_resolution: str
    min_price_ticker_count: int
    candidate_count: int
    ticker_valid_date_count: int
    group_valid_date_count: int
    skip_reason: str


@dataclass(frozen=True)
class TechnicalRelevanceEndDateResolution:
    end_date: Optional[str]
    requested_calendar_signal_date: str
    end_date_source: str
    end_date_resolution: str
    min_price_ticker_count: int
    candidate_count: int
    ticker_valid_date_count: int
    skip_reason: str


@dataclass(frozen=True)
class SwingMasterFundamentalsPostStepResult:
    attempted: int = 0
    result_check_status: str = "DISABLED"
    result_check_exit_code: int | None = None
    result_check_log_path: str = ""
    result_check_plan_json: str = "NONE"
    result_check_candidate_count: int = 0
    result_check_error: str = "NONE"
    active_tickers: int = 0
    seven_day_watch_window_count: int = 0
    due_for_result_check: int = 0
    future_confirmation_provider_calls_now: int = 0
    failure_retries: int = 0
    maintenance_selected: int = 0
    total_unique_provider_check_tickers: int = 0
    maintenance_backlog_remaining: int = 0
    weekly_update_attempted: int = 0
    weekly_update_status: str = "SKIPPED"
    weekly_update_exit_code: int | None = None
    weekly_update_log_path: str = ""
    weekly_update_plan_json: str = "NONE"
    weekly_update_planned_candidates: int = 0
    weekly_update_successful_candidates: int = 0
    weekly_update_failed_candidates: int = 0
    weekly_update_retryable_candidates: int = 0
    weekly_update_error: str = "NONE"


@dataclass(frozen=True)
class DatacenterPostStepResult:
    attempted: int
    status: str
    market: str
    audit_validation_status: str = "SKIPPED"
    log_path: str = ""
    signal_date: Optional[str] = None
    signal_date_source: str = "NONE"
    signal_date_resolution: str = "NONE"
    requested_calendar_signal_date: Optional[str] = None
    configured_taxonomy_version: str = ""
    configured_taxonomy_csv: str = ""
    configured_taxonomy_sha256: str = ""
    derived_taxonomy_row_count: int = 0
    derived_ticker_count: int = 0
    derived_group_count: int = 0
    derived_synthetic_group_count: int = 0
    daily_report_path: Optional[str] = None
    daily_report_csv_path: Optional[str] = None
    rolling_30_report_path: Optional[str] = None
    rolling_30_report_csv_path: Optional[str] = None
    rolling_5_report_path: Optional[str] = None
    rolling_5_report_csv_path: Optional[str] = None
    rolling_2_report_path: Optional[str] = None
    rolling_2_report_csv_path: Optional[str] = None
    weekly_report_path: Optional[str] = None
    weekly_report_csv_path: Optional[str] = None
    pipeline_summary: dict[str, str] = field(default_factory=dict)
    watchlist_reconciliation_attempted: bool = False
    watchlist_reconciliation_status: str = "SKIPPED"
    watchlist_source_reference: str = "NONE"
    watchlist_source_sha256: str = "NONE"
    watchlist_source_member_count: int = 0
    watchlist_previous_member_count: int = 0
    watchlist_current_member_count: int = 0
    watchlist_added_count: int = 0
    watchlist_removed_count: int = 0
    watchlist_added_tickers: str = "[]"
    watchlist_removed_tickers: str = "[]"
    watchlist_reconciliation_error: str = "NONE"
    error: Optional[str] = None


@dataclass(frozen=True)
class TechnicalRelevancePostStepResult:
    attempted: int
    enabled: bool
    status: str
    market: str
    run_id: Optional[str] = None
    ticker_count: int = 0
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    requested_calendar_signal_date: Optional[str] = None
    end_date_source: str = "NONE"
    end_date_resolution: str = "NONE"
    min_price_ticker_count: int = 0
    candidate_count: int = 0
    ticker_valid_date_count: int = 0
    records_written: int = 0
    relevant_count: int = 0
    weak_context_count: int = 0
    noise_count: int = 0
    unknown_signal_count: int = 0
    missing_dow_context_count: int = 0
    missing_bar_index_count: int = 0
    duration_seconds: str = "0.000"
    skip_reason: str = ""
    error: Optional[str] = None


@dataclass(frozen=True)
class EcSourceLayerRefreshPostStepResult:
    attempted: int
    status: str
    log_path: str = ""
    signal_date: str = "NONE"
    refresh_mode: str = "NONE"
    skipped_reason: str = "NONE"
    backup_path: str = "NONE"
    coverage_status: str = "NONE"
    parity_status: str = "NONE"
    total_mismatch_count: int = 0
    ticker_rows: int = 0
    group_signal_rows: int = 0
    synthetic_ohlc_rows: int = 0
    group_index_rows: int = 0
    watermark_rows: int = 0
    error: str = "NONE"
    bridge_mode: str = "DISABLED"
    bridge_reason: str = "INCREMENTAL_FEATURE_DISABLED"
    bridge_required_start: str = "NONE"
    bridge_required_end: str = "NONE"
    bridge_status: str = "SKIPPED"
    bridge_load_status: str = "NONE"
    bridge_coverage_status: str = "NONE"
    bridge_parity_status: str = "NONE"
    bridge_retry_required: bool = False
    bridge_exit_code: int | None = None
    bridge_error: str = "NONE"
    bridge_log: str = "NONE"
    bridge_watermark_refresh_performed: bool = False
    bridge_watchlist_membership_status: str = "UNKNOWN"
    bridge_watchlist_sync_required: bool = False
    bridge_watchlist_missing_in_loaded_count: int = 0
    bridge_watchlist_loaded_only_count: int = 0


@dataclass(frozen=True)
class EcBridgeDecision:
    bridge_mode: str
    selected_signal_date: str
    materialized_start: str
    materialized_end: str
    required_refresh_start: str
    required_refresh_end: str
    reason_code: str
    reason_details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class EcBridgeCatchupState:
    dc_latest: str | None
    ec_latest: str | None
    catchup_start: str | None
    catchup_end: str | None
    status: str
    details: dict[str, object] = field(default_factory=dict)


def scheduler_status_path(log_dir: str) -> str:
    return str(Path(log_dir) / "stock_update_scheduler_status.json")


def scheduler_lock_path(log_dir: str) -> str:
    return str(Path(log_dir) / "stock_update_scheduler.lock")


def write_scheduler_status(
    *,
    log_dir: str,
    is_running: bool,
    started_at_utc: str,
    finished_at_utc: Optional[str],
    current_market: Optional[str],
    last_status: str,
    summary_json_path: Optional[str],
    error: Optional[str],
) -> str:
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    status_path = log_dir_path / "stock_update_scheduler_status.json"
    payload = {
        "current_market": current_market,
        "error": error,
        "finished_at_utc": finished_at_utc,
        "is_running": is_running,
        "last_status": last_status,
        "started_at_utc": started_at_utc,
        "summary_json_path": summary_json_path,
    }
    write_text_atomic(
        status_path,
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return str(status_path)


def read_scheduler_status(log_dir: str) -> Optional[dict]:
    status_path = Path(scheduler_status_path(log_dir))
    if not status_path.exists():
        return None
    with status_path.open("r", encoding="utf-8") as status_file:
        return json.load(status_file)


def acquire_scheduler_lock(log_dir: str) -> IO[str]:
    log_dir_path = Path(log_dir)
    log_dir_path.mkdir(parents=True, exist_ok=True)
    lock_path = Path(scheduler_lock_path(log_dir))
    lock_handle = lock_path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        lock_handle.close()
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            raise SchedulerAlreadyRunningError("scheduler run is already active")
        raise
    return lock_handle


def release_scheduler_lock(lock_handle: IO[str]) -> None:
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
    finally:
        lock_handle.close()


@contextmanager
def acquire_scheduler_lock_context(log_dir: str) -> Iterator[IO[str]]:
    lock_handle = acquire_scheduler_lock(log_dir)
    try:
        yield lock_handle
    finally:
        release_scheduler_lock(lock_handle)


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _format_utc_timestamp(value: datetime.datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_utc_filename_timestamp(value: datetime.datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def _format_utc_filename_minute_timestamp(value: datetime.datetime) -> str:
    return value.strftime("%Y%m%dT%H%MZ")


def _format_local_timestamp(
    value: datetime.datetime,
    timezone_name: str,
) -> str:
    local_value = value.astimezone(ZoneInfo(timezone_name))
    return local_value.strftime("%Y-%m-%d %H:%M:%S %Z")


def _derive_overall_status(market_results: List[ScheduledMarketRunResult]) -> str:
    statuses = [market_result.summary_status for market_result in market_results]
    if any(status == STATUS_FAILED for status in statuses):
        return STATUS_FAILED
    if any(status == STATUS_OK_WITH_WARNINGS for status in statuses):
        return STATUS_OK_WITH_WARNINGS
    return STATUS_OK


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _resolve_repo_path(path_value: str) -> Path:
    path = Path(path_value)
    return path if path.is_absolute() else _repo_root() / path


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_datacenter_post_step_config(
    market: str,
    config: StockUpdateSchedulerConfig | None = None,
) -> Optional[DatacenterPostStepConfig]:
    if market != "usa":
        return None
    taxonomy_csv = (
        config.datacenter_taxonomy_csv
        if config is not None
        else "data/datacenter_ecosystem_taxonomy_full_v1.csv"
    )
    taxonomy_version = (
        config.datacenter_taxonomy_version
        if config is not None
        else "DC_TAXONOMY_FULL_V1"
    )
    expected_ticker_count = 236
    expected_group_count = 54
    expected_synthetic_ohlc_count = 53
    if config is not None:
        taxonomy_summary = _read_taxonomy_csv(
            str(_resolve_repo_path(taxonomy_csv)),
            taxonomy_version,
        )
        if taxonomy_summary.get("status") != "OK":
            raise ValueError(str(taxonomy_summary.get("error") or "invalid datacenter taxonomy source"))
        expected_ticker_count = int(taxonomy_summary["distinct_ticker_count"])
        distinct_layer_count = int(taxonomy_summary["distinct_layer_count"])
        distinct_subindustry_count = int(taxonomy_summary["distinct_subindustry_count"])
        expected_group_count = 1 + distinct_layer_count + distinct_subindustry_count
        expected_synthetic_ohlc_count = distinct_layer_count + distinct_subindustry_count
    return DatacenterPostStepConfig(
        market="usa",
        taxonomy_csv=taxonomy_csv,
        taxonomy_version=taxonomy_version,
        start_date="2025-08-01",
        index_base_date="2020-01-01",
        output_dir="/home/kalle/projects/rawcandle/swing_reports",
        expected_ticker_count=expected_ticker_count,
        expected_group_count=expected_group_count,
        expected_synthetic_ohlc_count=expected_synthetic_ohlc_count,
        watchlist_file="watchlists/datacenter_watchlist.txt",
    )


def _previous_calendar_date(value: str) -> str:
    return (datetime.date.fromisoformat(value) - datetime.timedelta(days=1)).isoformat()


def _resolve_latest_valid_ohlcv_date_for_market(
    price_db_path: str,
    market: str,
) -> str | None:
    normalized_market = market.strip().lower()
    try:
        with sqlite3.connect(price_db_path) as conn:
            row = conn.execute(
                """
                SELECT MAX(pvm)
                FROM osakedata
                WHERE market = ?
                  AND close IS NOT NULL
                """,
                (normalized_market,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None or row[0] is None:
        return None
    return str(row[0])


def _count_primary_ticker_prices_for_date(
    *,
    price_db_path: str,
    market: str,
    signal_date: str,
    primary_tickers: list[str],
) -> int:
    if not primary_tickers:
        return 0
    normalized_market = market.strip().lower()
    placeholders = ", ".join("?" for _ in primary_tickers)
    params: list[object] = [signal_date, normalized_market, *primary_tickers]
    with sqlite3.connect(price_db_path) as conn:
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT UPPER(TRIM(osake)))
            FROM osakedata
            WHERE pvm = ?
              AND market = ?
              AND close IS NOT NULL
              AND UPPER(TRIM(osake)) IN ({placeholders})
            """,
            params,
        ).fetchone()
    if row is None or row[0] is None:
        return 0
    return int(row[0])


def _resolve_datacenter_signal_date(
    *,
    price_db_path: str,
    analysis_db_path: str,
    market: str,
    taxonomy_csv_path: str,
    taxonomy_version: str,
    start_date: str,
    requested_calendar_signal_date: str,
    expected_ticker_count: int,
) -> DatacenterSignalDateResolution:
    from analysis.datacenter_indices.swing_group_persistence import (
        _load_valid_group_index_dates,
    )
    from analysis.datacenter_indices.swing_ticker_persistence import (
        _load_primary_tickers_for_taxonomy_version,
        load_valid_price_dates_for_market,
    )

    min_price_ticker_count = max(25, expected_ticker_count // 4)
    signal_date_source = "DOWNSTREAM_VALID_DATE"
    signal_date_resolution = "TICKER_AND_GROUP_VALID_DATE_WITH_MIN_TICKER_COUNT"
    normalized_taxonomy_csv_path = str((_repo_root() / taxonomy_csv_path).resolve())

    ticker_valid_dates = load_valid_price_dates_for_market(
        price_db_path=price_db_path,
        start_date=start_date,
        end_date=requested_calendar_signal_date,
        market=market,
        taxonomy_csv_path=normalized_taxonomy_csv_path,
        taxonomy_version=taxonomy_version,
    )
    group_valid_dates = _load_valid_group_index_dates(
        analysis_db_path=analysis_db_path,
        start_date=start_date,
        end_date=requested_calendar_signal_date,
        taxonomy_versions=[taxonomy_version],
    )
    primary_tickers = _load_primary_tickers_for_taxonomy_version(
        normalized_taxonomy_csv_path,
        taxonomy_version,
    )

    candidate_dates = sorted({str(date_value) for date_value in ticker_valid_dates}, reverse=True)
    for candidate_date in candidate_dates:
        if candidate_date > requested_calendar_signal_date:
            continue
        if (
            _count_primary_ticker_prices_for_date(
                price_db_path=price_db_path,
                market=market,
                signal_date=candidate_date,
                primary_tickers=primary_tickers,
            )
            < min_price_ticker_count
        ):
            continue
        return DatacenterSignalDateResolution(
            signal_date=candidate_date,
            requested_calendar_signal_date=requested_calendar_signal_date,
            signal_date_source=signal_date_source,
            signal_date_resolution=signal_date_resolution,
            min_price_ticker_count=min_price_ticker_count,
            candidate_count=len(candidate_dates),
            ticker_valid_date_count=len(ticker_valid_dates),
            group_valid_date_count=len(group_valid_dates),
            skip_reason="",
        )

    return DatacenterSignalDateResolution(
        signal_date=None,
        requested_calendar_signal_date=requested_calendar_signal_date,
        signal_date_source=signal_date_source,
        signal_date_resolution=signal_date_resolution,
        min_price_ticker_count=min_price_ticker_count,
        candidate_count=len(candidate_dates),
        ticker_valid_date_count=len(ticker_valid_dates),
        group_valid_date_count=len(group_valid_dates),
        skip_reason="NO_DOWNSTREAM_VALID_DATACENTER_SIGNAL_DATE",
    )


def _resolve_technical_relevance_end_date(
    *,
    price_db_path: str,
    market: str,
    taxonomy_csv_path: str,
    taxonomy_version: str,
    requested_calendar_signal_date: str,
    expected_ticker_count: int,
) -> TechnicalRelevanceEndDateResolution:
    from analysis.datacenter_indices.swing_ticker_persistence import (
        _load_primary_tickers_for_taxonomy_version,
        load_valid_price_dates_for_market,
    )

    min_price_ticker_count = max(25, expected_ticker_count // 4)
    end_date_source = "TECHNICAL_RELEVANCE_TAXONOMY_VALID_DATE"
    end_date_resolution = "TAXONOMY_VALID_DATE_WITH_MIN_TICKER_COUNT"
    normalized_taxonomy_csv_path = str((_repo_root() / taxonomy_csv_path).resolve())
    start_date = (
        datetime.date.fromisoformat(requested_calendar_signal_date)
        - datetime.timedelta(days=45)
    ).isoformat()

    ticker_valid_dates = load_valid_price_dates_for_market(
        price_db_path=price_db_path,
        start_date=start_date,
        end_date=requested_calendar_signal_date,
        market=market,
        taxonomy_csv_path=normalized_taxonomy_csv_path,
        taxonomy_version=taxonomy_version,
    )
    primary_tickers = _load_primary_tickers_for_taxonomy_version(
        normalized_taxonomy_csv_path,
        taxonomy_version,
    )
    candidate_dates = sorted({str(date_value) for date_value in ticker_valid_dates}, reverse=True)
    for candidate_date in candidate_dates:
        if candidate_date > requested_calendar_signal_date:
            continue
        if (
            _count_primary_ticker_prices_for_date(
                price_db_path=price_db_path,
                market=market,
                signal_date=candidate_date,
                primary_tickers=primary_tickers,
            )
            < min_price_ticker_count
        ):
            continue
        return TechnicalRelevanceEndDateResolution(
            end_date=candidate_date,
            requested_calendar_signal_date=requested_calendar_signal_date,
            end_date_source=end_date_source,
            end_date_resolution=end_date_resolution,
            min_price_ticker_count=min_price_ticker_count,
            candidate_count=len(candidate_dates),
            ticker_valid_date_count=len(ticker_valid_dates),
            skip_reason="",
        )

    return TechnicalRelevanceEndDateResolution(
        end_date=None,
        requested_calendar_signal_date=requested_calendar_signal_date,
        end_date_source=end_date_source,
        end_date_resolution=end_date_resolution,
        min_price_ticker_count=min_price_ticker_count,
        candidate_count=len(candidate_dates),
        ticker_valid_date_count=len(ticker_valid_dates),
        skip_reason="NO_VALID_TECHNICAL_RELEVANCE_END_DATE",
    )


def _resolve_market_technical_relevance_tickers(
    price_db_path: str,
    market: str,
) -> List[str]:
    normalized_market = market.strip().lower()
    try:
        with sqlite3.connect(price_db_path) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT osake
                FROM osakedata
                WHERE market = ?
                  AND close IS NOT NULL
                ORDER BY osake ASC
                """,
                (normalized_market,),
            ).fetchall()
    except sqlite3.Error:
        return []

    tickers = []
    for row in rows:
        raw_ticker = row[0]
        if raw_ticker is None:
            continue
        ticker = str(raw_ticker).strip()
        if not ticker:
            continue
        tickers.append(ticker)
    return tickers


def _build_technical_relevance_run_id(market: str, effective_signal_date: str) -> str:
    return f"TECH_SIGNAL_REL_DAILY_{market.upper()}_{effective_signal_date.replace('-', '_')}"


def _format_duration_seconds(duration_seconds: float) -> str:
    return f"{duration_seconds:.3f}"


def _parse_summary_value(stdout: str, key: str) -> Optional[str]:
    prefix = f"SUMMARY {key}="
    for line in stdout.splitlines():
        if line.startswith(prefix):
            return line[len(prefix) :]
    return None


def _parse_summary_lines(stdout: str) -> dict[str, str]:
    summary: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.startswith("SUMMARY ") or "=" not in line:
            continue
        key, value = line[len("SUMMARY ") :].split("=", 1)
        if key:
            summary[key] = value
    return summary


def _datacenter_watchlist_reconciliation_fields(
    pipeline_summary: dict[str, str],
) -> dict[str, object]:
    def _int_value(key: str) -> int:
        try:
            return int(pipeline_summary.get(key) or 0)
        except ValueError:
            return 0

    return {
        "watchlist_reconciliation_attempted": _summary_bool(
            pipeline_summary.get("watchlist_reconciliation_attempted")
        ),
        "watchlist_reconciliation_status": pipeline_summary.get(
            "watchlist_reconciliation_status", "SKIPPED"
        ),
        "watchlist_source_reference": pipeline_summary.get(
            "watchlist_source_reference", "NONE"
        ),
        "watchlist_source_sha256": pipeline_summary.get(
            "watchlist_source_sha256", "NONE"
        ),
        "watchlist_source_member_count": _int_value("watchlist_source_member_count"),
        "watchlist_previous_member_count": _int_value("watchlist_previous_member_count"),
        "watchlist_current_member_count": _int_value("watchlist_current_member_count"),
        "watchlist_added_count": _int_value("watchlist_added_count"),
        "watchlist_removed_count": _int_value("watchlist_removed_count"),
        "watchlist_added_tickers": pipeline_summary.get(
            "watchlist_added_tickers", "[]"
        ),
        "watchlist_removed_tickers": pipeline_summary.get(
            "watchlist_removed_tickers", "[]"
        ),
        "watchlist_reconciliation_error": pipeline_summary.get(
            "watchlist_reconciliation_error", "NONE"
        ),
    }


def _parse_datacenter_report_paths(stdout: str) -> dict[str, Optional[str]]:
    keys = (
        "daily_report_path",
        "daily_report_csv_path",
        "rolling_30_report_path",
        "rolling_30_report_csv_path",
        "rolling_5_report_path",
        "rolling_5_report_csv_path",
        "rolling_2_report_path",
        "rolling_2_report_csv_path",
        "weekly_report_path",
        "weekly_report_csv_path",
    )
    return {key: _parse_summary_value(stdout, key) for key in keys}


def _valid_iso_date_or_none(value: str | None) -> str | None:
    if value is None or value == "NONE":
        return None
    try:
        return datetime.date.fromisoformat(value).isoformat()
    except ValueError:
        return None


_EC_BRIDGE_DC_FACT_HEADS: tuple[tuple[str, str], ...] = (
    ("dc_ticker_swing_signal_daily", "signal_date"),
    ("dc_group_swing_signal_daily", "signal_date"),
    ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
    ("dc_group_index_daily", "index_date"),
)

_EC_BRIDGE_EC_FACT_HEADS: tuple[tuple[str, str], ...] = (
    ("ec_ticker_signal_daily", "signal_date"),
    ("ec_group_signal_daily", "signal_date"),
    ("ec_group_synthetic_ohlc_daily", "signal_date"),
    ("ec_group_index_daily", "signal_date"),
)

_EC_BRIDGE_DC_WATERMARK_COMPONENTS: tuple[str, ...] = (
    "TICKER_SWING_BASE",
    "GROUP_SWING_BASE",
    "SYNTHETIC_OHLC_BASE",
    "GROUP_INDEX",
)

_EC_BRIDGE_EC_WATERMARK_SOURCES: tuple[str, ...] = tuple(
    table_name for table_name, _ in _EC_BRIDGE_DC_FACT_HEADS
)


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _resolve_ec_taxonomy_version_id(
    conn: sqlite3.Connection,
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
) -> tuple[int | None, int | None]:
    if not _table_exists(conn, "ec_ecosystem") or not _table_exists(conn, "ec_taxonomy_version"):
        return None, None
    row = conn.execute(
        """
        SELECT e.ecosystem_id, tv.taxonomy_version_id
        FROM ec_ecosystem e
        JOIN ec_taxonomy_version tv ON tv.ecosystem_id = e.ecosystem_id
        WHERE e.ecosystem_code = ?
          AND tv.taxonomy_version_code = ?
        """,
        (ecosystem_code, taxonomy_version_code),
    ).fetchone()
    if row is None:
        return None, None
    return int(row[0]), int(row[1])


def _max_fact_date(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    date_column: str,
    taxonomy_version_code: str | None = None,
    ecosystem_id: int | None = None,
    taxonomy_version_id: int | None = None,
) -> str | None:
    if not _table_exists(conn, table_name):
        return None
    predicates: list[str] = []
    params: list[object] = []
    if taxonomy_version_code is not None:
        predicates.append("taxonomy_version = ?")
        params.append(taxonomy_version_code)
    if ecosystem_id is not None:
        predicates.append("ecosystem_id = ?")
        params.append(ecosystem_id)
    if taxonomy_version_id is not None:
        predicates.append("taxonomy_version_id = ?")
        params.append(taxonomy_version_id)
    where_sql = " WHERE " + " AND ".join(predicates) if predicates else ""
    value = conn.execute(
        f"SELECT MAX({date_column}) FROM {table_name}{where_sql}",
        tuple(params),
    ).fetchone()[0]
    return _valid_iso_date_or_none(str(value)) if value is not None else None


def _minimum_present_date(values: list[str | None]) -> str | None:
    present = [value for value in values if value is not None]
    if len(present) != len(values):
        return None
    return min(present)


def _next_calendar_date(date_text: str) -> str:
    return (datetime.date.fromisoformat(date_text) + datetime.timedelta(days=1)).isoformat()


def _resolve_ec_bridge_catchup_state(
    *,
    analysis_db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
) -> EcBridgeCatchupState:
    details: dict[str, object] = {}
    try:
        conn = sqlite3.connect(f"file:{Path(analysis_db_path).resolve()}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        return EcBridgeCatchupState(
            dc_latest=None,
            ec_latest=None,
            catchup_start=None,
            catchup_end=None,
            status="UNAVAILABLE",
            details={"error": str(exc)},
        )
    try:
        ecosystem_id, taxonomy_version_id = _resolve_ec_taxonomy_version_id(
            conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
        )
        details["ecosystem_id"] = ecosystem_id
        details["taxonomy_version_id"] = taxonomy_version_id
        if ecosystem_id is None or taxonomy_version_id is None:
            return EcBridgeCatchupState(
                dc_latest=None,
                ec_latest=None,
                catchup_start=None,
                catchup_end=None,
                status="UNAVAILABLE",
                details=details,
            )

        dc_fact_heads = {
            table_name: _max_fact_date(
                conn,
                table_name=table_name,
                date_column=date_column,
                taxonomy_version_code=taxonomy_version_code,
            )
            for table_name, date_column in _EC_BRIDGE_DC_FACT_HEADS
        }
        dc_watermark_heads: dict[str, str | None] = {}
        if _table_exists(conn, "dc_pipeline_watermark"):
            for component in _EC_BRIDGE_DC_WATERMARK_COMPONENTS:
                value = conn.execute(
                    """
                    SELECT MAX(end_date)
                    FROM dc_pipeline_watermark
                    WHERE component_name = ?
                      AND taxonomy_version = ?
                      AND status = 'OK'
                    """,
                    (component, taxonomy_version_code),
                ).fetchone()[0]
                dc_watermark_heads[component] = (
                    _valid_iso_date_or_none(str(value)) if value is not None else None
                )
        else:
            dc_watermark_heads = {component: None for component in _EC_BRIDGE_DC_WATERMARK_COMPONENTS}
        dc_latest = _minimum_present_date(
            list(dc_fact_heads.values()) + list(dc_watermark_heads.values())
        )

        ec_fact_heads = {
            table_name: _max_fact_date(
                conn,
                table_name=table_name,
                date_column=date_column,
                ecosystem_id=ecosystem_id,
                taxonomy_version_id=taxonomy_version_id,
            )
            for table_name, date_column in _EC_BRIDGE_EC_FACT_HEADS
        }
        ec_watermark_heads: dict[str, str | None] = {}
        if _table_exists(conn, "ec_pipeline_watermark"):
            for source_table in _EC_BRIDGE_EC_WATERMARK_SOURCES:
                value = conn.execute(
                    """
                    SELECT MAX(latest_signal_date)
                    FROM ec_pipeline_watermark
                    WHERE ecosystem_id = ?
                      AND taxonomy_version_id = ?
                      AND source_table = ?
                      AND status = 'OK'
                    """,
                    (ecosystem_id, taxonomy_version_id, source_table),
                ).fetchone()[0]
                ec_watermark_heads[source_table] = (
                    _valid_iso_date_or_none(str(value)) if value is not None else None
                )
        else:
            ec_watermark_heads = {source_table: None for source_table in _EC_BRIDGE_EC_WATERMARK_SOURCES}
        ec_latest = _minimum_present_date(
            list(ec_fact_heads.values()) + list(ec_watermark_heads.values())
        )

        details.update(
            {
                "dc_fact_heads": dc_fact_heads,
                "dc_watermark_heads": dc_watermark_heads,
                "ec_fact_heads": ec_fact_heads,
                "ec_watermark_heads": ec_watermark_heads,
            }
        )
        if dc_latest is None:
            return EcBridgeCatchupState(
                dc_latest=None,
                ec_latest=ec_latest,
                catchup_start=None,
                catchup_end=None,
                status="NO_VALID_DC_SOURCE_HEAD",
                details=details,
            )
        if ec_latest is None:
            return EcBridgeCatchupState(
                dc_latest=dc_latest,
                ec_latest=None,
                catchup_start=None,
                catchup_end=None,
                status="NO_VALID_EC_SOURCE_HEAD",
                details=details,
            )
        if ec_latest >= dc_latest:
            return EcBridgeCatchupState(
                dc_latest=dc_latest,
                ec_latest=ec_latest,
                catchup_start=None,
                catchup_end=None,
                status="ALIGNED",
                details=details,
            )
        return EcBridgeCatchupState(
            dc_latest=dc_latest,
            ec_latest=ec_latest,
            catchup_start=_next_calendar_date(ec_latest),
            catchup_end=dc_latest,
            status="EC_BEHIND_DC",
            details=details,
        )
    finally:
        conn.close()


def _build_ec_bridge_decision(
    *,
    datacenter_result: DatacenterPostStepResult,
    stage2_incremental_enabled: bool,
    catchup_state: EcBridgeCatchupState | None = None,
) -> EcBridgeDecision:
    selected_signal_date = datacenter_result.signal_date or "NONE"
    if datacenter_result.status != "OK" or not datacenter_result.signal_date:
        return EcBridgeDecision(
            bridge_mode="SKIPPED_NO_MATERIALIZATION",
            selected_signal_date=selected_signal_date,
            materialized_start="NONE",
            materialized_end="NONE",
            required_refresh_start="NONE",
            required_refresh_end="NONE",
            reason_code="DATACENTER_PIPELINE_NOT_SUCCESSFUL",
            reason_details={"datacenter_status": datacenter_result.status},
        )

    if not stage2_incremental_enabled:
        return EcBridgeDecision(
            bridge_mode="LATEST_REFRESH",
            selected_signal_date=selected_signal_date,
            materialized_start=selected_signal_date,
            materialized_end=selected_signal_date,
            required_refresh_start=selected_signal_date,
            required_refresh_end=selected_signal_date,
            reason_code="LEGACY_EC_REFRESH_BEHAVIOR",
            reason_details={"stage2_incremental_enabled": False},
        )

    summary = datacenter_result.pipeline_summary
    execution_status = summary.get("stage2_execution_status")
    materialized_start = _valid_iso_date_or_none(
        summary.get("stage2_actual_materialized_start")
    )
    materialized_end = _valid_iso_date_or_none(
        summary.get("stage2_actual_materialized_end")
    )
    selected_date = _valid_iso_date_or_none(datacenter_result.signal_date)
    if (
        execution_status != "EXECUTED"
        or materialized_start is None
        or materialized_end is None
        or selected_date is None
        or materialized_start > materialized_end
        or not (materialized_start <= selected_date <= materialized_end)
    ):
        if catchup_state is not None:
            if (
                catchup_state.status == "EC_BEHIND_DC"
                and catchup_state.catchup_start is not None
                and catchup_state.catchup_end is not None
            ):
                return EcBridgeDecision(
                    bridge_mode="HISTORICAL_BACKFILL",
                    selected_signal_date=selected_signal_date,
                    materialized_start=catchup_state.dc_latest or "NONE",
                    materialized_end=catchup_state.dc_latest or "NONE",
                    required_refresh_start=catchup_state.catchup_start,
                    required_refresh_end=catchup_state.catchup_end,
                    reason_code="EC_CATCHUP_REQUIRED",
                    reason_details={
                        "stage2_execution_status": execution_status or "MISSING",
                        "dc_latest": catchup_state.dc_latest or "NONE",
                        "ec_latest": catchup_state.ec_latest or "NONE",
                        **catchup_state.details,
                    },
                )
            if catchup_state.status == "ALIGNED":
                return EcBridgeDecision(
                    bridge_mode="SKIPPED_NO_MATERIALIZATION",
                    selected_signal_date=selected_signal_date,
                    materialized_start=catchup_state.dc_latest or "NONE",
                    materialized_end=catchup_state.dc_latest or "NONE",
                    required_refresh_start="NONE",
                    required_refresh_end="NONE",
                    reason_code="NO_EC_CATCHUP_NEEDED",
                    reason_details={
                        "stage2_execution_status": execution_status or "MISSING",
                        "dc_latest": catchup_state.dc_latest or "NONE",
                        "ec_latest": catchup_state.ec_latest or "NONE",
                        **catchup_state.details,
                    },
                )
            if catchup_state.status == "NO_VALID_DC_SOURCE_HEAD":
                return EcBridgeDecision(
                    bridge_mode="SKIPPED_NO_MATERIALIZATION",
                    selected_signal_date=selected_signal_date,
                    materialized_start="NONE",
                    materialized_end="NONE",
                    required_refresh_start="NONE",
                    required_refresh_end="NONE",
                    reason_code="NO_VALID_DC_SOURCE_HEAD",
                    reason_details={
                        "stage2_execution_status": execution_status or "MISSING",
                        **catchup_state.details,
                    },
                )
        return EcBridgeDecision(
            bridge_mode="SKIPPED_NO_MATERIALIZATION",
            selected_signal_date=selected_signal_date,
            materialized_start=materialized_start or "NONE",
            materialized_end=materialized_end or "NONE",
            required_refresh_start="NONE",
            required_refresh_end="NONE",
            reason_code="NO_SUCCESSFUL_MATERIALIZATION",
            reason_details={
                "stage2_execution_status": execution_status or "MISSING",
                "stage2_actual_materialized_start": summary.get(
                    "stage2_actual_materialized_start", "MISSING"
                ),
                "stage2_actual_materialized_end": summary.get(
                    "stage2_actual_materialized_end", "MISSING"
                ),
            },
        )

    if materialized_start == selected_date and materialized_end == selected_date:
        return EcBridgeDecision(
            bridge_mode="LATEST_REFRESH",
            selected_signal_date=selected_signal_date,
            materialized_start=materialized_start,
            materialized_end=materialized_end,
            required_refresh_start=selected_signal_date,
            required_refresh_end=selected_signal_date,
            reason_code="SINGLE_DATE_MATERIALIZATION",
            reason_details={"stage2_execution_status": execution_status},
        )

    return EcBridgeDecision(
        bridge_mode="HISTORICAL_BACKFILL",
        selected_signal_date=selected_signal_date,
        materialized_start=materialized_start,
        materialized_end=materialized_end,
        required_refresh_start=materialized_start,
        required_refresh_end=materialized_end,
        reason_code="MULTI_DATE_MATERIALIZATION",
        reason_details={"stage2_execution_status": execution_status},
    )


def _bridge_failure_statuses() -> set[str]:
    return {
        "REFRESH_REFUSED",
        "REFRESH_FAILED_BEFORE_WRITE",
        "REFRESH_FAILED",
        "BACKFILL_REFUSED",
        "BACKFILL_FAILED_BEFORE_WRITE",
        "BACKFILL_FAILED",
        "BACKFILL_SKIPPED",
        "UNKNOWN",
    }


def _aggregate_backfill_audit_status(
    per_date_results: object,
    field_name: str,
) -> str:
    if not isinstance(per_date_results, list) or not per_date_results:
        return "NONE"
    statuses: list[str] = []
    for item in per_date_results:
        if not isinstance(item, dict):
            return "MALFORMED"
        value = item.get(field_name)
        if not isinstance(value, str) or not value:
            return "MALFORMED"
        statuses.append(value)
    if any(status not in {"OK", "OK_WITH_WARNINGS"} for status in statuses):
        return "FAILED"
    if any(status == "OK_WITH_WARNINGS" for status in statuses):
        return "OK_WITH_WARNINGS"
    return "OK"


def _aggregate_backfill_row_counts(per_date_results: object) -> dict[str, int]:
    totals = {
        "ticker_rows": 0,
        "group_signal_rows": 0,
        "synthetic_ohlc_rows": 0,
        "group_index_rows": 0,
    }
    if not isinstance(per_date_results, list):
        return totals
    for item in per_date_results:
        if not isinstance(item, dict):
            continue
        row_counts = item.get("row_counts")
        if not isinstance(row_counts, dict):
            continue
        for key in totals:
            totals[key] += int(row_counts.get(key) or 0)
    return totals


def _summary_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _build_datacenter_log_path(log_dir: Path, market: str, started_at: datetime.datetime) -> Path:
    minute_timestamp = _format_utc_filename_minute_timestamp(started_at)
    base_name = f"datacenter_pipeline_{market}_{minute_timestamp}"
    candidate = log_dir / f"{base_name}.txt"
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = log_dir / f"{base_name}_{suffix}.txt"
        if not candidate.exists():
            return candidate
        suffix += 1


def _build_ec_source_layer_log_path(
    log_dir: Path, market: str, started_at: datetime.datetime
) -> Path:
    minute_timestamp = _format_utc_filename_minute_timestamp(started_at)
    base_name = f"ec_source_layer_{market}_{minute_timestamp}"
    candidate = log_dir / f"{base_name}.txt"
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = log_dir / f"{base_name}_{suffix}.txt"
        if not candidate.exists():
            return candidate
        suffix += 1


def _run_python_cli_main(cli_main, args: list[str]) -> tuple[int, str]:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        exit_code = cli_main(args)
    stdout = buffer.getvalue()
    if stdout:
        sys.stdout.write(stdout)
    return int(exit_code), stdout


def _run_technical_relevance_post_step(
    *,
    config: StockUpdateSchedulerConfig,
    target_market: str,
    market_update_phase_status: str,
    effective_today: str,
) -> TechnicalRelevancePostStepResult:
    if not config.technical_relevance_enabled:
        return TechnicalRelevancePostStepResult(
            attempted=0,
            enabled=False,
            status="DISABLED",
            market="NONE",
            skip_reason="",
        )

    if target_market not in config.enabled_markets:
        return TechnicalRelevancePostStepResult(
            attempted=0,
            enabled=True,
            status="SKIPPED",
            market=target_market,
            skip_reason="USA_NOT_ENABLED",
        )

    if market_update_phase_status not in (STATUS_OK, STATUS_OK_WITH_WARNINGS):
        return TechnicalRelevancePostStepResult(
            attempted=0,
            enabled=True,
            status="SKIPPED",
            market=target_market,
            skip_reason="MARKET_UPDATE_FAILED",
        )

    try:
        resolved = _resolve_datacenter_post_step_config(target_market, config)
    except TypeError:
        resolved = _resolve_datacenter_post_step_config(target_market)
    if resolved is None:
        return TechnicalRelevancePostStepResult(
            attempted=0,
            enabled=True,
            status="SKIPPED",
            market=target_market,
            skip_reason="NO_VALID_TECHNICAL_RELEVANCE_END_DATE",
        )

    requested_calendar_signal_date = _previous_calendar_date(effective_today)
    end_date_resolution = _resolve_technical_relevance_end_date(
        price_db_path=config.osakedata_db_path,
        market=resolved.market,
        taxonomy_csv_path=resolved.taxonomy_csv,
        taxonomy_version=resolved.taxonomy_version,
        requested_calendar_signal_date=requested_calendar_signal_date,
        expected_ticker_count=resolved.expected_ticker_count,
    )
    end_date = end_date_resolution.end_date
    if end_date is None:
        return TechnicalRelevancePostStepResult(
            attempted=0,
            enabled=True,
            status="SKIPPED",
            market=target_market,
            requested_calendar_signal_date=requested_calendar_signal_date,
            end_date_source=end_date_resolution.end_date_source,
            end_date_resolution=end_date_resolution.end_date_resolution,
            min_price_ticker_count=end_date_resolution.min_price_ticker_count,
            candidate_count=end_date_resolution.candidate_count,
            ticker_valid_date_count=end_date_resolution.ticker_valid_date_count,
            skip_reason="NO_VALID_TECHNICAL_RELEVANCE_END_DATE",
        )

    tickers = _resolve_market_technical_relevance_tickers(
        config.osakedata_db_path,
        target_market,
    )
    if not tickers:
        return TechnicalRelevancePostStepResult(
            attempted=0,
            enabled=True,
            status="SKIPPED",
            market=target_market,
            end_date=end_date,
            requested_calendar_signal_date=requested_calendar_signal_date,
            end_date_source=end_date_resolution.end_date_source,
            end_date_resolution=end_date_resolution.end_date_resolution,
            min_price_ticker_count=end_date_resolution.min_price_ticker_count,
            candidate_count=end_date_resolution.candidate_count,
            ticker_valid_date_count=end_date_resolution.ticker_valid_date_count,
            skip_reason="NO_TICKERS_FOR_MARKET",
        )

    start_date = (
        datetime.date.fromisoformat(end_date) - datetime.timedelta(days=45)
    ).isoformat()
    run_id = _build_technical_relevance_run_id(target_market, end_date)
    started_at = time.perf_counter()

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(config.analysis_db_path)
        conn.row_factory = sqlite3.Row
        apply_technical_signal_relevance_migration(conn)
        if read_relevance_run(conn, run_id) is not None:
            return TechnicalRelevancePostStepResult(
                attempted=1,
                enabled=True,
                status="SKIPPED_EXISTING_RUN",
                market=target_market,
                run_id=run_id,
                ticker_count=len(tickers),
                start_date=start_date,
                end_date=end_date,
                requested_calendar_signal_date=requested_calendar_signal_date,
                end_date_source=end_date_resolution.end_date_source,
                end_date_resolution=end_date_resolution.end_date_resolution,
                min_price_ticker_count=end_date_resolution.min_price_ticker_count,
                candidate_count=end_date_resolution.candidate_count,
                ticker_valid_date_count=end_date_resolution.ticker_valid_date_count,
                duration_seconds=_format_duration_seconds(time.perf_counter() - started_at),
                skip_reason="RUN_ID_ALREADY_EXISTS",
            )

        summary = run_technical_signal_relevance_for_tickers(
            conn=conn,
            tickers=tickers,
            timeframe="1d",
            start_date=start_date,
            end_date=end_date,
            run_id=run_id,
            created_at_utc=resolve_created_at_utc(None),
        )
        conn.commit()
        return TechnicalRelevancePostStepResult(
            attempted=1,
            enabled=True,
            status="OK",
            market=target_market,
            run_id=run_id,
            ticker_count=len(tickers),
            start_date=start_date,
            end_date=end_date,
            requested_calendar_signal_date=requested_calendar_signal_date,
            end_date_source=end_date_resolution.end_date_source,
            end_date_resolution=end_date_resolution.end_date_resolution,
            min_price_ticker_count=end_date_resolution.min_price_ticker_count,
            candidate_count=end_date_resolution.candidate_count,
            ticker_valid_date_count=end_date_resolution.ticker_valid_date_count,
            records_written=summary.records_written,
            relevant_count=summary.relevant_count,
            weak_context_count=summary.weak_context_count,
            noise_count=summary.noise_count,
            unknown_signal_count=summary.unknown_signal_count,
            missing_dow_context_count=summary.missing_dow_context_count,
            missing_bar_index_count=summary.missing_bar_index_count,
            duration_seconds=_format_duration_seconds(time.perf_counter() - started_at),
        )
    except sqlite3.IntegrityError as exc:
        if conn is not None:
            conn.rollback()
        error_text = str(exc)
        if "technical_signal_relevance_runs.run_id" in error_text or "UNIQUE constraint failed" in error_text:
            return TechnicalRelevancePostStepResult(
                attempted=1,
                enabled=True,
                status="SKIPPED_EXISTING_RUN",
                market=target_market,
                run_id=run_id,
                ticker_count=len(tickers),
                start_date=start_date,
                end_date=end_date,
                duration_seconds=_format_duration_seconds(time.perf_counter() - started_at),
                skip_reason="RUN_ID_ALREADY_EXISTS",
            )
        return TechnicalRelevancePostStepResult(
            attempted=1,
            enabled=True,
            status="FAILED",
            market=target_market,
            run_id=run_id,
            ticker_count=len(tickers),
            start_date=start_date,
            end_date=end_date,
            requested_calendar_signal_date=requested_calendar_signal_date,
            end_date_source=end_date_resolution.end_date_source,
            end_date_resolution=end_date_resolution.end_date_resolution,
            min_price_ticker_count=end_date_resolution.min_price_ticker_count,
            candidate_count=end_date_resolution.candidate_count,
            ticker_valid_date_count=end_date_resolution.ticker_valid_date_count,
            duration_seconds=_format_duration_seconds(time.perf_counter() - started_at),
            error=error_text,
        )
    except Exception as exc:
        if conn is not None:
            conn.rollback()
        return TechnicalRelevancePostStepResult(
            attempted=1,
            enabled=True,
            status="FAILED",
            market=target_market,
            run_id=run_id,
            ticker_count=len(tickers),
            start_date=start_date,
            end_date=end_date,
            requested_calendar_signal_date=requested_calendar_signal_date,
            end_date_source=end_date_resolution.end_date_source,
            end_date_resolution=end_date_resolution.end_date_resolution,
            min_price_ticker_count=end_date_resolution.min_price_ticker_count,
            candidate_count=end_date_resolution.candidate_count,
            ticker_valid_date_count=end_date_resolution.ticker_valid_date_count,
            duration_seconds=_format_duration_seconds(time.perf_counter() - started_at),
            error=str(exc),
        )
    finally:
        if conn is not None:
            conn.close()


def _run_datacenter_post_step(
    *,
    config: StockUpdateSchedulerConfig,
    target_market: str,
    effective_today: str,
) -> DatacenterPostStepResult:
    try:
        resolved = _resolve_datacenter_post_step_config(target_market, config)
    except TypeError:
        resolved = _resolve_datacenter_post_step_config(target_market)
    if resolved is None:
        return DatacenterPostStepResult(
            attempted=0,
            status="SKIPPED",
            market=target_market,
        )

    started_at = _utc_now()
    requested_calendar_signal_date = _previous_calendar_date(effective_today)
    signal_date_resolution = _resolve_datacenter_signal_date(
        price_db_path=config.osakedata_db_path,
        analysis_db_path=config.analysis_db_path,
        market=resolved.market,
        taxonomy_csv_path=resolved.taxonomy_csv,
        taxonomy_version=resolved.taxonomy_version,
        start_date=resolved.start_date,
        requested_calendar_signal_date=requested_calendar_signal_date,
        expected_ticker_count=resolved.expected_ticker_count,
    )
    signal_date = signal_date_resolution.signal_date
    taxonomy_csv_path = _resolve_repo_path(resolved.taxonomy_csv)
    taxonomy_source_sha256 = _file_sha256(taxonomy_csv_path)
    taxonomy_summary = _read_taxonomy_csv(str(taxonomy_csv_path), resolved.taxonomy_version)
    if taxonomy_summary.get("status") != "OK":
        raise ValueError(str(taxonomy_summary.get("error") or "invalid datacenter taxonomy source"))
    derived_taxonomy_row_count = int(taxonomy_summary["row_count"])
    derived_ticker_count = int(taxonomy_summary["distinct_ticker_count"])
    derived_group_count = (
        1
        + int(taxonomy_summary["distinct_layer_count"])
        + int(taxonomy_summary["distinct_subindustry_count"])
    )
    derived_synthetic_group_count = (
        int(taxonomy_summary["distinct_layer_count"])
        + int(taxonomy_summary["distinct_subindustry_count"])
    )
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _build_datacenter_log_path(log_dir, resolved.market, started_at)
    if signal_date is None:
        finished_at = _utc_now()
        log_lines = [
            f"run_started_at_local={_format_local_timestamp(started_at, config.timezone)}",
            f"run_finished_at_local={_format_local_timestamp(finished_at, config.timezone)}",
            f"market={resolved.market}",
            f"requested_calendar_signal_date={requested_calendar_signal_date}",
            "signal_date=NONE",
            f"signal_date_source={signal_date_resolution.signal_date_source}",
            f"signal_date_resolution={signal_date_resolution.signal_date_resolution}",
            f"signal_date_min_price_ticker_count={signal_date_resolution.min_price_ticker_count}",
            f"signal_date_candidate_count={signal_date_resolution.candidate_count}",
            f"ticker_valid_date_count={signal_date_resolution.ticker_valid_date_count}",
            f"group_valid_date_count={signal_date_resolution.group_valid_date_count}",
            f"taxonomy_csv_path={taxonomy_csv_path}",
            f"taxonomy_version={resolved.taxonomy_version}",
            f"taxonomy_source_sha256={taxonomy_source_sha256}",
            f"derived_taxonomy_row_count={derived_taxonomy_row_count}",
            f"derived_ticker_count={derived_ticker_count}",
            f"derived_group_count={derived_group_count}",
            f"derived_synthetic_group_count={derived_synthetic_group_count}",
            f"osakedata_db_path={config.osakedata_db_path}",
            f"analysis_db_path={config.analysis_db_path}",
            f"skip_reason={signal_date_resolution.skip_reason}",
        ]
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return DatacenterPostStepResult(
            attempted=0,
            status="SKIPPED",
            market=resolved.market,
            audit_validation_status="SKIPPED",
            log_path=str(log_path),
            signal_date=None,
            signal_date_source=signal_date_resolution.signal_date_source,
            signal_date_resolution=signal_date_resolution.signal_date_resolution,
            requested_calendar_signal_date=requested_calendar_signal_date,
            configured_taxonomy_version=resolved.taxonomy_version,
            configured_taxonomy_csv=str(taxonomy_csv_path),
            configured_taxonomy_sha256=taxonomy_source_sha256,
            derived_taxonomy_row_count=derived_taxonomy_row_count,
            derived_ticker_count=derived_ticker_count,
            derived_group_count=derived_group_count,
            derived_synthetic_group_count=derived_synthetic_group_count,
            error=signal_date_resolution.skip_reason,
        )
    command = [
        "python3",
        "run_datacenter_swing_pipeline.py",
        "--price-db",
        config.osakedata_db_path,
        "--analysis-db",
        config.analysis_db_path,
        "--taxonomy-csv",
        resolved.taxonomy_csv,
        "--taxonomy-version",
        resolved.taxonomy_version,
        "--market",
        resolved.market,
        "--signal-date",
        signal_date,
        "--start-date",
        resolved.start_date,
        "--index-base-date",
        resolved.index_base_date,
        "--output-dir",
        resolved.output_dir,
        "--expected-ticker-count",
        str(resolved.expected_ticker_count),
        "--expected-group-count",
        str(resolved.expected_group_count),
        "--expected-synthetic-ohlc-count",
        str(resolved.expected_synthetic_ohlc_count),
    ]
    watchlist_file = config.ec_source_layer_watchlist or resolved.watchlist_file
    if watchlist_file:
        command.extend(["--watchlist-file", watchlist_file])
    if config.datacenter_stage2_incremental_enabled:
        command.extend(
            [
                "--stage2-incremental",
                "--stage2-overlap-trading-days",
                str(config.datacenter_stage2_overlap_trading_days),
            ]
        )
    started_log_lines = [
        f"run_started_at_local={_format_local_timestamp(started_at, config.timezone)}",
        "run_finished_at_local=NONE",
        f"market={resolved.market}",
        f"requested_calendar_signal_date={requested_calendar_signal_date}",
        f"signal_date={signal_date}",
        f"signal_date_source={signal_date_resolution.signal_date_source}",
        f"signal_date_resolution={signal_date_resolution.signal_date_resolution}",
        f"taxonomy_csv_path={taxonomy_csv_path}",
        f"taxonomy_version={resolved.taxonomy_version}",
        f"taxonomy_source_sha256={taxonomy_source_sha256}",
        f"osakedata_db_path={config.osakedata_db_path}",
        f"analysis_db_path={config.analysis_db_path}",
        f"command={' '.join(command)}",
        "status=STARTED",
    ]
    write_text_atomic(log_path, "\n".join(started_log_lines) + "\n", encoding="utf-8")
    completed = subprocess.run(
        command,
        cwd=str(_repo_root()),
        check=False,
        capture_output=True,
        text=True,
    )
    finished_at = _utc_now()
    log_lines = [
        f"run_started_at_local={_format_local_timestamp(started_at, config.timezone)}",
        f"run_finished_at_local={_format_local_timestamp(finished_at, config.timezone)}",
        f"market={resolved.market}",
        f"requested_calendar_signal_date={requested_calendar_signal_date}",
        f"signal_date={signal_date}",
        f"signal_date_source={signal_date_resolution.signal_date_source}",
        f"signal_date_resolution={signal_date_resolution.signal_date_resolution}",
        f"signal_date_min_price_ticker_count={signal_date_resolution.min_price_ticker_count}",
        f"signal_date_candidate_count={signal_date_resolution.candidate_count}",
        f"ticker_valid_date_count={signal_date_resolution.ticker_valid_date_count}",
        f"group_valid_date_count={signal_date_resolution.group_valid_date_count}",
        f"taxonomy_csv_path={taxonomy_csv_path}",
        f"taxonomy_version={resolved.taxonomy_version}",
        f"taxonomy_source_sha256={taxonomy_source_sha256}",
        f"derived_taxonomy_row_count={derived_taxonomy_row_count}",
        f"derived_ticker_count={derived_ticker_count}",
        f"derived_group_count={derived_group_count}",
        f"derived_synthetic_group_count={derived_synthetic_group_count}",
        f"osakedata_db_path={config.osakedata_db_path}",
        f"analysis_db_path={config.analysis_db_path}",
        f"command={' '.join(command)}",
        f"returncode={completed.returncode}",
        "=== STDOUT ===",
        completed.stdout.rstrip(),
        "=== STDERR ===",
        completed.stderr.rstrip(),
    ]
    write_text_atomic(log_path, "\n".join(log_lines).rstrip() + "\n", encoding="utf-8")
    audit_validation_status = _parse_summary_value(
        completed.stdout or "", "audit_validation_status"
    )
    pipeline_summary = _parse_summary_lines(completed.stdout or "")
    watchlist_reconciliation_fields = _datacenter_watchlist_reconciliation_fields(pipeline_summary)
    parsed_report_paths = _parse_datacenter_report_paths(completed.stdout or "")
    if completed.returncode != 0:
        return DatacenterPostStepResult(
            attempted=1,
            status="FAILED",
            market=resolved.market,
            audit_validation_status=audit_validation_status or "UNKNOWN",
            log_path=str(log_path),
            signal_date=signal_date,
            signal_date_source=signal_date_resolution.signal_date_source,
            signal_date_resolution=signal_date_resolution.signal_date_resolution,
            requested_calendar_signal_date=requested_calendar_signal_date,
            configured_taxonomy_version=resolved.taxonomy_version,
            configured_taxonomy_csv=str(taxonomy_csv_path),
            configured_taxonomy_sha256=taxonomy_source_sha256,
            derived_taxonomy_row_count=derived_taxonomy_row_count,
            derived_ticker_count=derived_ticker_count,
            derived_group_count=derived_group_count,
            derived_synthetic_group_count=derived_synthetic_group_count,
            daily_report_path=parsed_report_paths["daily_report_path"],
            daily_report_csv_path=parsed_report_paths["daily_report_csv_path"],
            rolling_30_report_path=parsed_report_paths["rolling_30_report_path"],
            rolling_30_report_csv_path=parsed_report_paths["rolling_30_report_csv_path"],
            rolling_5_report_path=parsed_report_paths["rolling_5_report_path"],
            rolling_5_report_csv_path=parsed_report_paths["rolling_5_report_csv_path"],
            rolling_2_report_path=parsed_report_paths["rolling_2_report_path"],
            rolling_2_report_csv_path=parsed_report_paths["rolling_2_report_csv_path"],
            weekly_report_path=parsed_report_paths["weekly_report_path"],
            weekly_report_csv_path=parsed_report_paths["weekly_report_csv_path"],
            pipeline_summary=pipeline_summary,
            **watchlist_reconciliation_fields,
            error=f"datacenter pipeline exited with code {completed.returncode}",
        )
    return DatacenterPostStepResult(
        attempted=1,
        status="OK",
        market=resolved.market,
        audit_validation_status=audit_validation_status or "UNKNOWN",
        log_path=str(log_path),
        signal_date=signal_date,
        signal_date_source=signal_date_resolution.signal_date_source,
        signal_date_resolution=signal_date_resolution.signal_date_resolution,
        requested_calendar_signal_date=requested_calendar_signal_date,
        configured_taxonomy_version=resolved.taxonomy_version,
        configured_taxonomy_csv=str(taxonomy_csv_path),
        configured_taxonomy_sha256=taxonomy_source_sha256,
        derived_taxonomy_row_count=derived_taxonomy_row_count,
        derived_ticker_count=derived_ticker_count,
        derived_group_count=derived_group_count,
        derived_synthetic_group_count=derived_synthetic_group_count,
        daily_report_path=parsed_report_paths["daily_report_path"],
        daily_report_csv_path=parsed_report_paths["daily_report_csv_path"],
        rolling_30_report_path=parsed_report_paths["rolling_30_report_path"],
        rolling_30_report_csv_path=parsed_report_paths["rolling_30_report_csv_path"],
        rolling_5_report_path=parsed_report_paths["rolling_5_report_path"],
        rolling_5_report_csv_path=parsed_report_paths["rolling_5_report_csv_path"],
        rolling_2_report_path=parsed_report_paths["rolling_2_report_path"],
        rolling_2_report_csv_path=parsed_report_paths["rolling_2_report_csv_path"],
        weekly_report_path=parsed_report_paths["weekly_report_path"],
        weekly_report_csv_path=parsed_report_paths["weekly_report_csv_path"],
        pipeline_summary=pipeline_summary,
        **watchlist_reconciliation_fields,
    )


def _run_ec_source_layer_refresh_post_step(
    *,
    config: StockUpdateSchedulerConfig,
    target_market: str,
    datacenter_result: DatacenterPostStepResult,
) -> EcSourceLayerRefreshPostStepResult:
    started_at = _utc_now()
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _build_ec_source_layer_log_path(log_dir, target_market, started_at)

    def _write_log(result: EcSourceLayerRefreshPostStepResult) -> EcSourceLayerRefreshPostStepResult:
        finished_at = _utc_now()
        lines = [
            f"run_started_at_local={_format_local_timestamp(started_at, config.timezone)}",
            f"run_finished_at_local={_format_local_timestamp(finished_at, config.timezone)}",
            f"market={target_market}",
            f"ecosystem={config.ec_source_layer_ecosystem}",
            f"ec_source_layer_enabled={str(config.ec_source_layer_enabled).lower()}",
            f"attempted={result.attempted}",
            f"status={result.status}",
            f"signal_date={result.signal_date}",
            f"refresh_mode={result.refresh_mode}",
            f"skipped_reason={result.skipped_reason}",
            f"backup_path={result.backup_path}",
            f"coverage_status={result.coverage_status}",
            f"parity_status={result.parity_status}",
            f"total_mismatch_count={result.total_mismatch_count}",
            f"ticker_rows={result.ticker_rows}",
            f"group_signal_rows={result.group_signal_rows}",
            f"synthetic_ohlc_rows={result.synthetic_ohlc_rows}",
            f"group_index_rows={result.group_index_rows}",
            f"watermark_rows={result.watermark_rows}",
            f"error={result.error}",
            f"ec_bridge_mode={result.bridge_mode}",
            f"ec_bridge_reason={result.bridge_reason}",
            f"ec_bridge_required_start={result.bridge_required_start}",
            f"ec_bridge_required_end={result.bridge_required_end}",
            f"ec_bridge_status={result.bridge_status}",
            f"ec_bridge_load_status={result.bridge_load_status}",
            f"ec_bridge_coverage_status={result.bridge_coverage_status}",
            f"ec_bridge_parity_status={result.bridge_parity_status}",
            f"ec_bridge_retry_required={str(result.bridge_retry_required).lower()}",
            f"ec_bridge_exit_code={result.bridge_exit_code}",
            f"ec_bridge_error={result.bridge_error}",
            f"ec_bridge_log={result.bridge_log}",
            "ec_bridge_watermark_refresh_performed="
            f"{str(result.bridge_watermark_refresh_performed).lower()}",
            f"ec_bridge_watchlist_membership_status={result.bridge_watchlist_membership_status}",
            "ec_bridge_watchlist_sync_required="
            f"{str(result.bridge_watchlist_sync_required).lower()}",
            "ec_bridge_watchlist_missing_in_loaded_count="
            f"{result.bridge_watchlist_missing_in_loaded_count}",
            "ec_bridge_watchlist_loaded_only_count="
            f"{result.bridge_watchlist_loaded_only_count}",
            f"analysis_db_path={config.analysis_db_path}",
        ]
        log_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return EcSourceLayerRefreshPostStepResult(
            attempted=result.attempted,
            status=result.status,
            log_path=str(log_path),
            signal_date=result.signal_date,
            refresh_mode=result.refresh_mode,
            skipped_reason=result.skipped_reason,
            backup_path=result.backup_path,
            coverage_status=result.coverage_status,
            parity_status=result.parity_status,
            total_mismatch_count=result.total_mismatch_count,
            ticker_rows=result.ticker_rows,
            group_signal_rows=result.group_signal_rows,
            synthetic_ohlc_rows=result.synthetic_ohlc_rows,
            group_index_rows=result.group_index_rows,
            watermark_rows=result.watermark_rows,
            error=result.error,
            bridge_mode=result.bridge_mode,
            bridge_reason=result.bridge_reason,
            bridge_required_start=result.bridge_required_start,
            bridge_required_end=result.bridge_required_end,
            bridge_status=result.bridge_status,
            bridge_load_status=result.bridge_load_status,
            bridge_coverage_status=result.bridge_coverage_status,
            bridge_parity_status=result.bridge_parity_status,
            bridge_retry_required=result.bridge_retry_required,
            bridge_exit_code=result.bridge_exit_code,
            bridge_error=result.bridge_error,
            bridge_log=str(log_path),
            bridge_watermark_refresh_performed=result.bridge_watermark_refresh_performed,
            bridge_watchlist_membership_status=result.bridge_watchlist_membership_status,
            bridge_watchlist_sync_required=result.bridge_watchlist_sync_required,
            bridge_watchlist_missing_in_loaded_count=result.bridge_watchlist_missing_in_loaded_count,
            bridge_watchlist_loaded_only_count=result.bridge_watchlist_loaded_only_count,
        )

    if not config.ec_source_layer_enabled:
        return _write_log(
            EcSourceLayerRefreshPostStepResult(
                attempted=0,
                status="SKIPPED",
                skipped_reason="DISABLED",
                bridge_mode="DISABLED",
                bridge_reason="EC_SOURCE_LAYER_DISABLED",
                bridge_status="SKIPPED",
            )
        )
    if target_market not in config.enabled_markets:
        return _write_log(
            EcSourceLayerRefreshPostStepResult(
                attempted=0,
                status="SKIPPED",
                skipped_reason="MARKET_NOT_ENABLED",
                bridge_mode="DISABLED",
                bridge_reason="MARKET_NOT_ENABLED",
                bridge_status="SKIPPED",
            )
        )

    catchup_state = (
        _resolve_ec_bridge_catchup_state(
            analysis_db_path=config.analysis_db_path,
            ecosystem_code=config.ec_source_layer_ecosystem,
            taxonomy_version_code=config.ec_source_layer_taxonomy_version,
        )
        if datacenter_result.status == "OK" and datacenter_result.signal_date
        else None
    )
    bridge_decision = _build_ec_bridge_decision(
        datacenter_result=datacenter_result,
        stage2_incremental_enabled=config.datacenter_stage2_incremental_enabled,
        catchup_state=catchup_state,
    )
    if datacenter_result.status != "OK" or not datacenter_result.signal_date:
        return _write_log(
            EcSourceLayerRefreshPostStepResult(
                attempted=0,
                status="SKIPPED",
                skipped_reason="LEGACY_DATACENTER_NOT_READY",
                signal_date=datacenter_result.signal_date or "NONE",
                bridge_mode=bridge_decision.bridge_mode,
                bridge_reason=bridge_decision.reason_code,
                bridge_required_start=bridge_decision.required_refresh_start,
                bridge_required_end=bridge_decision.required_refresh_end,
                bridge_status="SKIPPED",
            )
        )
    if config.ec_source_layer_require_legacy_reports_success and datacenter_result.status != "OK":
        return _write_log(
            EcSourceLayerRefreshPostStepResult(
                attempted=0,
                status="SKIPPED",
                skipped_reason="LEGACY_REPORTS_NOT_SUCCESSFUL",
                signal_date=datacenter_result.signal_date,
                bridge_mode=bridge_decision.bridge_mode,
                bridge_reason=bridge_decision.reason_code,
                bridge_required_start=bridge_decision.required_refresh_start,
                bridge_required_end=bridge_decision.required_refresh_end,
                bridge_status="SKIPPED",
            )
        )

    if bridge_decision.bridge_mode == "SKIPPED_NO_MATERIALIZATION":
        return _write_log(
            EcSourceLayerRefreshPostStepResult(
                attempted=0,
                status="SKIPPED",
                skipped_reason=bridge_decision.reason_code,
                signal_date=datacenter_result.signal_date,
                bridge_mode=bridge_decision.bridge_mode,
                bridge_reason=bridge_decision.reason_code,
                bridge_required_start=bridge_decision.required_refresh_start,
                bridge_required_end=bridge_decision.required_refresh_end,
                bridge_status="SKIPPED",
            )
        )

    if bridge_decision.bridge_mode == "HISTORICAL_BACKFILL":
        try:
            backfill_summary = run_ec_source_layer_backfill(
                db_path=config.analysis_db_path,
                ecosystem_code=config.ec_source_layer_ecosystem,
                taxonomy_version_code=config.ec_source_layer_taxonomy_version,
                date_from=bridge_decision.required_refresh_start,
                date_to=bridge_decision.required_refresh_end,
                taxonomy_csv_path=config.ec_source_layer_taxonomy_csv or "",
                watchlist_path=config.ec_source_layer_watchlist or "",
                backup_dir=config.ec_source_layer_backup_dir or "",
                confirm_db=config.analysis_db_path,
                confirm_ecosystem=config.ec_source_layer_ecosystem,
                confirm_taxonomy_version=config.ec_source_layer_taxonomy_version,
                allow_replace_existing=True,
                reconcile_watchlist=False,
            )
        except Exception as exc:
            return _write_log(
                EcSourceLayerRefreshPostStepResult(
                    attempted=1,
                    status="BACKFILL_FAILED",
                    signal_date=datacenter_result.signal_date,
                    refresh_mode="historical_backfill",
                    error=str(exc),
                    bridge_mode=bridge_decision.bridge_mode,
                    bridge_reason=bridge_decision.reason_code,
                    bridge_required_start=bridge_decision.required_refresh_start,
                    bridge_required_end=bridge_decision.required_refresh_end,
                    bridge_status="FAILED",
                    bridge_load_status="EXCEPTION",
                    bridge_retry_required=True,
                    bridge_exit_code=1,
                    bridge_error=str(exc),
                    bridge_watermark_refresh_performed=False,
                )
            )

        backfill_status = str(backfill_summary.get("status") or "UNKNOWN")
        coverage_status = _aggregate_backfill_audit_status(
            backfill_summary.get("per_date_results"), "coverage_status"
        )
        parity_status = _aggregate_backfill_audit_status(
            backfill_summary.get("per_date_results"), "parity_status"
        )
        row_counts = _aggregate_backfill_row_counts(
            backfill_summary.get("per_date_results")
        )
        total_mismatch_count = int(backfill_summary.get("total_mismatch_count") or 0)
        bridge_watermark_refresh_performed = _summary_bool(
            backfill_summary.get("watermark_refresh_performed")
        )
        bridge_ok = (
            backfill_status == "BACKFILL_COMPLETED"
            and coverage_status in {"OK", "OK_WITH_WARNINGS"}
            and parity_status in {"OK", "OK_WITH_WARNINGS"}
            and total_mismatch_count == 0
            and bridge_watermark_refresh_performed
        )
        return _write_log(
            EcSourceLayerRefreshPostStepResult(
                attempted=1,
                status=backfill_status,
                signal_date=datacenter_result.signal_date,
                refresh_mode="historical_backfill",
                skipped_reason=str(backfill_summary.get("skipped_reason") or "NONE"),
                backup_path=str(backfill_summary.get("backup_path") or "NONE"),
                coverage_status=coverage_status,
                parity_status=parity_status,
                total_mismatch_count=total_mismatch_count,
                ticker_rows=row_counts["ticker_rows"],
                group_signal_rows=row_counts["group_signal_rows"],
                synthetic_ohlc_rows=row_counts["synthetic_ohlc_rows"],
                group_index_rows=row_counts["group_index_rows"],
                watermark_rows=int(backfill_summary.get("watermark_rows_total") or 0),
                error=str(backfill_summary.get("error") or "NONE"),
                bridge_mode=bridge_decision.bridge_mode,
                bridge_reason=bridge_decision.reason_code,
                bridge_required_start=bridge_decision.required_refresh_start,
                bridge_required_end=bridge_decision.required_refresh_end,
                bridge_status="OK" if bridge_ok else "FAILED",
                bridge_load_status=backfill_status,
                bridge_coverage_status=coverage_status,
                bridge_parity_status=parity_status,
                bridge_retry_required=not bridge_ok,
                bridge_exit_code=0 if bridge_ok else 1,
                bridge_error="NONE" if bridge_ok else str(backfill_summary.get("error") or backfill_status),
                bridge_watermark_refresh_performed=bridge_watermark_refresh_performed,
                bridge_watchlist_membership_status=str(
                    backfill_summary.get("watchlist_membership_status") or "UNKNOWN"
                ),
                bridge_watchlist_sync_required=_summary_bool(
                    backfill_summary.get("watchlist_sync_required")
                ),
                bridge_watchlist_missing_in_loaded_count=int(
                    backfill_summary.get("watchlist_missing_in_loaded_count") or 0
                ),
                bridge_watchlist_loaded_only_count=int(
                    backfill_summary.get("watchlist_loaded_only_count") or 0
                ),
            )
        )

    try:
        refresh_summary = run_ec_source_layer_refresh(
            db_path=config.analysis_db_path,
            ecosystem_code=config.ec_source_layer_ecosystem,
            taxonomy_version_code=config.ec_source_layer_taxonomy_version,
            taxonomy_csv_path=config.ec_source_layer_taxonomy_csv or "",
            watchlist_path=config.ec_source_layer_watchlist or "",
            backup_dir=config.ec_source_layer_backup_dir or "",
            confirm_db=config.analysis_db_path,
            confirm_ecosystem=config.ec_source_layer_ecosystem,
            confirm_taxonomy_version=config.ec_source_layer_taxonomy_version,
            signal_date=datacenter_result.signal_date,
            allow_replace_date=not config.ec_source_layer_only_on_new_signal_date,
            reconcile_watchlist=False,
        )
    except Exception as exc:
        return _write_log(
            EcSourceLayerRefreshPostStepResult(
                attempted=1,
                status="REFRESH_FAILED",
                signal_date=datacenter_result.signal_date,
                refresh_mode="scheduler_post_step",
                error=str(exc),
                bridge_mode=bridge_decision.bridge_mode,
                bridge_reason=bridge_decision.reason_code,
                bridge_required_start=bridge_decision.required_refresh_start,
                bridge_required_end=bridge_decision.required_refresh_end,
                bridge_status="FAILED",
                bridge_load_status="EXCEPTION",
                bridge_retry_required=True,
                bridge_exit_code=1,
                bridge_error=str(exc),
                bridge_watermark_refresh_performed=False,
            )
        )

    refresh_status = str(refresh_summary.get("status") or "UNKNOWN")
    bridge_ok = refresh_status == "REFRESH_COMPLETED"
    bridge_status = "OK" if bridge_ok else ("NOT_REQUIRED" if refresh_status == "REFRESH_SKIPPED" else "FAILED")
    return _write_log(
        EcSourceLayerRefreshPostStepResult(
            attempted=1 if refresh_summary.get("attempted") else 0,
            status=refresh_status,
            signal_date=str(refresh_summary.get("signal_date") or "NONE"),
            refresh_mode=str(refresh_summary.get("refresh_mode") or "NONE"),
            skipped_reason=str(refresh_summary.get("skipped_reason") or "NONE"),
            backup_path=str(refresh_summary.get("backup_path") or "NONE"),
            coverage_status=str(refresh_summary.get("coverage_status") or "NONE"),
            parity_status=str(refresh_summary.get("parity_status") or "NONE"),
            total_mismatch_count=int(refresh_summary.get("total_mismatch_count") or 0),
            ticker_rows=int(refresh_summary.get("ticker_rows") or 0),
            group_signal_rows=int(refresh_summary.get("group_signal_rows") or 0),
            synthetic_ohlc_rows=int(refresh_summary.get("synthetic_ohlc_rows") or 0),
            group_index_rows=int(refresh_summary.get("group_index_rows") or 0),
            watermark_rows=int(refresh_summary.get("watermark_rows") or 0),
            error=str(refresh_summary.get("error") or "NONE"),
            bridge_mode=bridge_decision.bridge_mode,
            bridge_reason=bridge_decision.reason_code,
            bridge_required_start=bridge_decision.required_refresh_start,
            bridge_required_end=bridge_decision.required_refresh_end,
            bridge_status=bridge_status,
            bridge_load_status=refresh_status,
            bridge_coverage_status=str(refresh_summary.get("coverage_status") or "NONE"),
            bridge_parity_status=str(refresh_summary.get("parity_status") or "NONE"),
            bridge_retry_required=bridge_status == "FAILED",
            bridge_exit_code=0 if bridge_status != "FAILED" else 1,
            bridge_error="NONE" if bridge_status != "FAILED" else str(refresh_summary.get("error") or refresh_status),
            bridge_watermark_refresh_performed=refresh_status == "REFRESH_COMPLETED",
            bridge_watchlist_membership_status=str(
                refresh_summary.get("watchlist_membership_status") or "UNKNOWN"
            ),
            bridge_watchlist_sync_required=_summary_bool(
                refresh_summary.get("watchlist_sync_required")
            ),
            bridge_watchlist_missing_in_loaded_count=int(
                refresh_summary.get("watchlist_missing_in_loaded_count") or 0
            ),
            bridge_watchlist_loaded_only_count=int(
                refresh_summary.get("watchlist_loaded_only_count") or 0
            ),
        )
    )


def _build_app(config: StockUpdateSchedulerConfig) -> RawCandleApp:
    osakedata_db_path = Path(config.osakedata_db_path)
    app = object.__new__(RawCandleApp)
    app.osakedata_db_path = config.osakedata_db_path
    app.analysis_db_path = config.analysis_db_path
    app.data_dir = str(osakedata_db_path.resolve().parent)
    return app


def _write_summary_json(
    *,
    config: StockUpdateSchedulerConfig,
    run_started_at: datetime.datetime,
    result: ScheduledStockUpdateRunResult,
) -> None:
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    summary_json_path = log_dir / (
        "stock_update_scheduler_summary_"
        f"{_format_utc_filename_timestamp(run_started_at)}.json"
    )
    result.summary_json_path = str(summary_json_path)
    summary_payload = asdict(result)
    summary_payload["summary_json_path"] = str(summary_json_path)
    summary_json_path.write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_market_log(
    *,
    log_path: Path,
    market: str,
    started_at_local: str,
    finished_at_local: str,
    config: StockUpdateSchedulerConfig,
    summary_lines: List[str],
    ui_summary: str,
    error: Optional[str],
) -> None:
    lines = [
        f"run_started_at_local={started_at_local}",
        f"run_finished_at_local={finished_at_local}",
        f"market={market}",
        f"osakedata_db_path={config.osakedata_db_path}",
        f"analysis_db_path={config.analysis_db_path}",
    ]
    lines.extend(summary_lines)
    if error is not None:
        lines.append(f"SUMMARY error={error}")
    lines.append("=== UI SUMMARY ===")
    lines.append(ui_summary)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _build_market_log_path(log_dir: Path, market: str, started_at: datetime.datetime) -> Path:
    minute_timestamp = _format_utc_filename_minute_timestamp(started_at)
    base_name = f"stock_update_{market}_{minute_timestamp}"
    candidate = log_dir / f"{base_name}.txt"
    if not candidate.exists():
        return candidate

    suffix = 2
    while True:
        candidate = log_dir / f"{base_name}_{suffix}.txt"
        if not candidate.exists():
            return candidate
        suffix += 1


def _resolve_swingmaster_repo_path(config: StockUpdateSchedulerConfig) -> Path:
    return Path(config.swingmaster_repo_path).expanduser().resolve()


def _resolve_swingmaster_python_path(config: StockUpdateSchedulerConfig) -> Path:
    repo_path = _resolve_swingmaster_repo_path(config)
    if config.swingmaster_python_path:
        python_path = Path(config.swingmaster_python_path).expanduser()
        if python_path.is_absolute():
            return python_path
        return repo_path / python_path
    return repo_path / ".venv" / "bin" / "python"


def _resolve_swingmaster_fundamentals_db_path(config: StockUpdateSchedulerConfig) -> Path:
    repo_path = _resolve_swingmaster_repo_path(config)
    if config.swingmaster_fundamentals_db_path:
        db_path = Path(config.swingmaster_fundamentals_db_path).expanduser()
        if db_path.is_absolute():
            return db_path.resolve()
        return (repo_path / db_path).resolve()
    return (repo_path / "fundamentals_usa.db").resolve()


def _swingmaster_subprocess_env(repo_path: Path) -> dict[str, str]:
    env = os.environ.copy()
    repo_path_text = str(repo_path)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        repo_path_text
        if not existing_pythonpath
        else repo_path_text + os.pathsep + existing_pythonpath
    )
    return env


def _build_swingmaster_log_path(log_dir: Path, name: str, started_at: datetime.datetime) -> Path:
    minute_timestamp = _format_utc_filename_minute_timestamp(started_at)
    base_name = f"swingmaster_{name}_{minute_timestamp}"
    candidate = log_dir / f"{base_name}.txt"
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = log_dir / f"{base_name}_{suffix}.txt"
        if not candidate.exists():
            return candidate
        suffix += 1


def _write_swingmaster_process_log(
    *,
    log_path: Path,
    command: list[str],
    cwd: Path,
    started_at_utc: str,
    finished_at_utc: str,
    exit_code: int | None,
    stdout: str,
    stderr: str,
    error: str | None = None,
) -> None:
    lines = [
        f"run_started_at_utc={started_at_utc}",
        f"run_finished_at_utc={finished_at_utc}",
        f"cwd={cwd}",
        "command=" + json.dumps(command),
        f"exit_code={exit_code if exit_code is not None else 'NONE'}",
    ]
    if error:
        lines.append(f"error={error}")
    lines.append("=== STDOUT ===")
    lines.append(stdout.rstrip())
    lines.append("=== STDERR ===")
    lines.append(stderr.rstrip())
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _extract_last_json_object(text: str) -> dict:
    decoder = json.JSONDecoder()
    for index in range(len(text) - 1, -1, -1):
        if text[index] != "{":
            continue
        candidate = text[index:].strip()
        try:
            value, end_index = decoder.raw_decode(candidate)
        except json.JSONDecodeError:
            continue
        if candidate[end_index:].strip() == "" and isinstance(value, dict):
            return value
    raise ValueError("No JSON object found in SwingMaster stdout")


def _parse_summary_lines(stdout: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.startswith("SUMMARY ") or "=" not in line:
            continue
        key, value = line.removeprefix("SUMMARY ").split("=", 1)
        parsed[key] = value
    return parsed


def _json_list_len(value: str | None) -> int:
    if not value:
        return 0
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return 0
    return len(parsed) if isinstance(parsed, list) else 0


def _int_summary(summary: dict, *keys: str) -> int:
    for key in keys:
        value = summary.get(key)
        if value is None or value == "":
            continue
        return int(value)
    return 0


def _run_swingmaster_fundamentals_post_step(
    *,
    config: StockUpdateSchedulerConfig,
    decision_date: str,
) -> SwingMasterFundamentalsPostStepResult:
    if not config.swingmaster_fundamentals_enabled:
        return SwingMasterFundamentalsPostStepResult(attempted=0, result_check_status="DISABLED")

    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    repo_path = _resolve_swingmaster_repo_path(config)
    python_path = _resolve_swingmaster_python_path(config)
    fundamentals_db_path = _resolve_swingmaster_fundamentals_db_path(config)
    osakedata_db_path = Path(config.osakedata_db_path).expanduser().resolve()
    check_started_at = _utc_now()
    check_started_at_utc = _format_utc_timestamp(check_started_at)
    check_log_path = _build_swingmaster_log_path(log_dir, "usa_result_check", check_started_at)
    check_command = [
        str(python_path),
        str(repo_path / "swingmaster" / "cli" / "check_fundamental_new_results.py"),
        "--fundamentals-db",
        str(fundamentals_db_path),
        "--ohlcv-db",
        str(osakedata_db_path),
        "--decision-date",
        decision_date,
        "--ohlcv-stale-days",
        str(config.swingmaster_ohlcv_stale_days),
        "--event-watch-days-after",
        str(config.swingmaster_event_watch_days_after),
        "--calendar-confirmation-days-before",
        str(config.swingmaster_calendar_confirmation_days_before),
        "--calendar-maintenance-limit",
        str(config.swingmaster_calendar_maintenance_limit),
        "--calendar-stale-days",
        str(config.swingmaster_calendar_stale_days),
        "--calendar-failure-retry-days",
        str(config.swingmaster_calendar_failure_retry_days),
        "--json",
    ]

    if not repo_path.exists() or not python_path.exists():
        missing_path = repo_path if not repo_path.exists() else python_path
        error = f"Missing SwingMaster dependency: {missing_path}"
        _write_swingmaster_process_log(
            log_path=check_log_path,
            command=check_command,
            cwd=repo_path,
            started_at_utc=check_started_at_utc,
            finished_at_utc=_format_utc_timestamp(_utc_now()),
            exit_code=None,
            stdout="",
            stderr="",
            error=error,
        )
        return SwingMasterFundamentalsPostStepResult(
            attempted=1,
            result_check_status="FAILED",
            result_check_log_path=str(check_log_path),
            result_check_error=error,
        )

    try:
        check_process = subprocess.run(
            check_command,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            env=_swingmaster_subprocess_env(repo_path),
        )
        _write_swingmaster_process_log(
            log_path=check_log_path,
            command=check_command,
            cwd=repo_path,
            started_at_utc=check_started_at_utc,
            finished_at_utc=_format_utc_timestamp(_utc_now()),
            exit_code=check_process.returncode,
            stdout=check_process.stdout,
            stderr=check_process.stderr,
        )
        payload = _extract_last_json_object(check_process.stdout)
        summary = payload.get("summary", {}) if isinstance(payload.get("summary"), dict) else {}
        result_check_status = str(payload.get("check_status") or "FAILED")
        result_check_error = (
            "NONE"
            if check_process.returncode in (0, 2) and result_check_status != "FAILED"
            else check_process.stderr.strip() or result_check_status
        )
    except Exception as exc:
        stdout = check_process.stdout if "check_process" in locals() else ""
        stderr = check_process.stderr if "check_process" in locals() else ""
        exit_code = check_process.returncode if "check_process" in locals() else None
        _write_swingmaster_process_log(
            log_path=check_log_path,
            command=check_command,
            cwd=repo_path,
            started_at_utc=check_started_at_utc,
            finished_at_utc=_format_utc_timestamp(_utc_now()),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            error=str(exc),
        )
        return SwingMasterFundamentalsPostStepResult(
            attempted=1,
            result_check_status="FAILED",
            result_check_exit_code=exit_code,
            result_check_log_path=str(check_log_path),
            result_check_error=str(exc),
        )

    candidate_count = _int_summary(summary, "candidate_count")
    plan_json = str(summary.get("plan_json") or "NONE")
    base = {
        "attempted": 1,
        "result_check_status": result_check_status,
        "result_check_exit_code": check_process.returncode,
        "result_check_log_path": str(check_log_path),
        "result_check_plan_json": plan_json,
        "result_check_candidate_count": candidate_count,
        "result_check_error": result_check_error,
        "active_tickers": _int_summary(summary, "active_fetch_count", "active_tickers"),
        "seven_day_watch_window_count": _int_summary(summary, "due_for_confirmation_watch_count"),
        "due_for_result_check": _int_summary(summary, "due_for_result_check_count"),
        "future_confirmation_provider_calls_now": _int_summary(summary, "due_for_confirmation_count"),
        "failure_retries": _int_summary(summary, "failure_retry_count", "failure_retries"),
        "maintenance_selected": _int_summary(summary, "maintenance_selected_count"),
        "total_unique_provider_check_tickers": _int_summary(summary, "unique_provider_check_ticker_count"),
        "maintenance_backlog_remaining": _int_summary(summary, "maintenance_backlog_remaining"),
    }
    if check_process.returncode not in (0, 2) or result_check_status == "FAILED":
        return SwingMasterFundamentalsPostStepResult(**base)

    decision = datetime.date.fromisoformat(decision_date)
    if decision.weekday() != 6 or candidate_count <= 0:
        return SwingMasterFundamentalsPostStepResult(**base)

    update_started_at = _utc_now()
    update_started_at_utc = _format_utc_timestamp(update_started_at)
    update_log_path = _build_swingmaster_log_path(log_dir, "usa_weekly_update", update_started_at)
    update_command = [
        str(python_path),
        str(repo_path / "swingmaster" / "cli" / "run_fundamental_quarter_update.py"),
        "--db",
        str(fundamentals_db_path),
        "--osakedata-db",
        str(osakedata_db_path),
        "--run-id",
        f"USA_QUARTER_UPDATE_{decision_date}__QUARTERLY",
        "--market",
        "usa",
        "--decision-date",
        decision_date,
        "--quarter-refresh-plan-json",
        plan_json,
    ]
    try:
        update_process = subprocess.run(
            update_command,
            cwd=str(repo_path),
            capture_output=True,
            text=True,
            env=_swingmaster_subprocess_env(repo_path),
        )
        _write_swingmaster_process_log(
            log_path=update_log_path,
            command=update_command,
            cwd=repo_path,
            started_at_utc=update_started_at_utc,
            finished_at_utc=_format_utc_timestamp(_utc_now()),
            exit_code=update_process.returncode,
            stdout=update_process.stdout,
            stderr=update_process.stderr,
        )
        update_summary = _parse_summary_lines(update_process.stdout)
        failed_candidates = _json_list_len(update_summary.get("failed_candidates_json"))
        planned_candidates = int(update_summary.get("plan_candidate_count") or candidate_count)
        successful_candidates = int(update_summary.get("tickers_succeeded") or max(planned_candidates - failed_candidates, 0))
        update_error = "NONE" if update_process.returncode == 0 else update_process.stderr.strip() or "WEEKLY_UPDATE_FAILED"
        return SwingMasterFundamentalsPostStepResult(
            **base,
            weekly_update_attempted=1,
            weekly_update_status="SUCCESS" if update_process.returncode == 0 else "FAILED",
            weekly_update_exit_code=update_process.returncode,
            weekly_update_log_path=str(update_log_path),
            weekly_update_plan_json=plan_json,
            weekly_update_planned_candidates=planned_candidates,
            weekly_update_successful_candidates=successful_candidates,
            weekly_update_failed_candidates=failed_candidates,
            weekly_update_retryable_candidates=failed_candidates,
            weekly_update_error=update_error,
        )
    except Exception as exc:
        stdout = update_process.stdout if "update_process" in locals() else ""
        stderr = update_process.stderr if "update_process" in locals() else ""
        exit_code = update_process.returncode if "update_process" in locals() else None
        _write_swingmaster_process_log(
            log_path=update_log_path,
            command=update_command,
            cwd=repo_path,
            started_at_utc=update_started_at_utc,
            finished_at_utc=_format_utc_timestamp(_utc_now()),
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            error=str(exc),
        )
        return SwingMasterFundamentalsPostStepResult(
            **base,
            weekly_update_attempted=1,
            weekly_update_status="FAILED",
            weekly_update_exit_code=exit_code,
            weekly_update_log_path=str(update_log_path),
            weekly_update_plan_json=plan_json,
            weekly_update_planned_candidates=candidate_count,
            weekly_update_error=str(exc),
        )


def _preflight_validate_config(config: StockUpdateSchedulerConfig) -> None:
    osakedata_db_path = Path(config.osakedata_db_path)
    if not osakedata_db_path.exists():
        raise ValueError(f"Missing osakedata db: {osakedata_db_path}")
    if not osakedata_db_path.is_file():
        raise ValueError(f"osakedata db is not a file: {osakedata_db_path}")

    analysis_db_path = Path(config.analysis_db_path)
    if not analysis_db_path.exists():
        raise ValueError(f"Missing analysis db: {analysis_db_path}")
    if not analysis_db_path.is_file():
        raise ValueError(f"analysis db is not a file: {analysis_db_path}")

    if osakedata_db_path.resolve().parent != analysis_db_path.resolve().parent:
        raise ValueError(
            "osakedata db and analysis db must be in the same directory for data_dir"
        )
    if not config.enabled_markets:
        raise ValueError("enabled_markets must not be empty")
    if not config.log_dir:
        raise ValueError("log_dir must be non-empty")


def _run_one_market(
    *,
    config: StockUpdateSchedulerConfig,
    market: str,
    run_started_at_utc: str,
    effective_today: str,
    effective_fetch_until_exclusive: str,
) -> ScheduledMarketRunResult:
    market_started_at = _utc_now()
    started_at_utc = _format_utc_timestamp(market_started_at)
    started_at_local = _format_local_timestamp(market_started_at, config.timezone)
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = _build_market_log_path(log_dir, market, market_started_at)

    app = _build_app(config)
    error: Optional[str] = None
    ui_summary = ""

    try:
        result = app._run_stock_update_via_service(
            market=market,
            start_override=None,
            today=effective_today,
            fetch_until_exclusive=effective_fetch_until_exclusive,
        )
        summary_lines = format_stock_update_summary_lines(result)
        summary_status = result.status
        exit_code = 0 if result.status == STATUS_OK else 1
        ui_summary = app._format_stock_update_service_result_for_ui(result)
    except Exception as exc:
        error = str(exc)
        summary_lines = [
            "SUMMARY status=FAILED",
            f"SUMMARY error={error}",
        ]
        summary_status = STATUS_FAILED
        exit_code = 1
        ui_summary = error

    market_finished_at = _utc_now()
    finished_at_utc = _format_utc_timestamp(market_finished_at)
    finished_at_local = _format_local_timestamp(market_finished_at, config.timezone)
    _write_market_log(
        log_path=log_path,
        market=market,
        started_at_local=started_at_local,
        finished_at_local=finished_at_local,
        config=config,
        summary_lines=summary_lines,
        ui_summary=ui_summary,
        error=error,
    )

    return ScheduledMarketRunResult(
        market=market,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
        exit_code=exit_code,
        summary_status=summary_status,
        log_path=str(log_path),
        summary_lines=summary_lines,
        error=error,
    )


def run_scheduler_config(
    *,
    config_path: str,
) -> ScheduledStockUpdateRunResult:
    run_started_at = _utc_now()
    started_at_utc = _format_utc_timestamp(run_started_at)
    config = read_scheduler_config(config_path)
    _preflight_validate_config(config)
    status_initialized = False

    with acquire_scheduler_lock_context(config.log_dir):
        try:
            write_scheduler_status(
                log_dir=config.log_dir,
                is_running=True,
                started_at_utc=started_at_utc,
                current_market=None,
                finished_at_utc=None,
                last_status="RUNNING",
                summary_json_path=None,
                error=None,
            )
            status_initialized = True

            if config.skip_next_run:
                reset_config = replace(config, skip_next_run=False)
                write_scheduler_config(config_path, reset_config)

                result = ScheduledStockUpdateRunResult(
                    started_at_utc=started_at_utc,
                    finished_at_utc=_format_utc_timestamp(_utc_now()),
                    config_path=config_path,
                    enabled_markets=list(config.enabled_markets),
                    market_results=[],
                    overall_status=STATUS_OK,
                    skipped=True,
                    skip_reason="skip_next_run",
                    technical_relevance_attempted=0,
                    technical_relevance_enabled=config.technical_relevance_enabled,
                    technical_relevance_status="DISABLED"
                    if not config.technical_relevance_enabled
                    else "SKIPPED",
                    technical_relevance_market="NONE"
                    if not config.technical_relevance_enabled
                    else "usa",
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
                    technical_relevance_skip_reason="skip_next_run"
                    if config.technical_relevance_enabled
                    else "",
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
                    ec_source_layer_log_path="",
                )
                _write_summary_json(config=config, run_started_at=run_started_at, result=result)
                write_scheduler_status(
                    log_dir=config.log_dir,
                    is_running=False,
                    started_at_utc=started_at_utc,
                    finished_at_utc=result.finished_at_utc,
                    current_market=None,
                    last_status=STATUS_OK,
                    summary_json_path=result.summary_json_path,
                    error=None,
                )
                return result

            effective_today = datetime.datetime.now().strftime("%Y-%m-%d")
            effective_fetch_until_exclusive = _today_exclusive_end_date()

            market_results: List[ScheduledMarketRunResult] = []
            for market in config.enabled_markets:
                write_scheduler_status(
                    log_dir=config.log_dir,
                    is_running=True,
                    started_at_utc=started_at_utc,
                    finished_at_utc=None,
                    current_market=market,
                    last_status="RUNNING",
                    summary_json_path=None,
                    error=None,
                )
                market_results.append(
                    _run_one_market(
                        config=config,
                        market=market,
                        run_started_at_utc=started_at_utc,
                        effective_today=effective_today,
                        effective_fetch_until_exclusive=effective_fetch_until_exclusive,
                    )
                )

            market_update_phase_status = _derive_overall_status(market_results)
            technical_relevance_result = _run_technical_relevance_post_step(
                config=config,
                target_market="usa",
                market_update_phase_status=market_update_phase_status,
                effective_today=effective_today,
            )
            datacenter_result = DatacenterPostStepResult(
                attempted=0,
                status="SKIPPED",
                market="usa",
            )
            ec_source_layer_result = EcSourceLayerRefreshPostStepResult(
                attempted=0,
                status="SKIPPED",
                skipped_reason="MARKET_PHASE_FAILED"
                if market_update_phase_status not in (STATUS_OK, STATUS_OK_WITH_WARNINGS)
                else "MARKET_NOT_ENABLED"
                if datacenter_result.market not in config.enabled_markets
                else "NOT_RUN",
            )
            if (
                market_update_phase_status in (STATUS_OK, STATUS_OK_WITH_WARNINGS)
                and datacenter_result.market in config.enabled_markets
            ):
                datacenter_result = _run_datacenter_post_step(
                    config=config,
                    target_market=datacenter_result.market,
                    effective_today=effective_today,
                )
                ec_source_layer_result = _run_ec_source_layer_refresh_post_step(
                    config=config,
                    target_market=datacenter_result.market,
                    datacenter_result=datacenter_result,
                )
            swingmaster_result = _run_swingmaster_fundamentals_post_step(
                config=config,
                decision_date=effective_today,
            )
            overall_status = (
                STATUS_FAILED
                if technical_relevance_result.status == "FAILED"
                or datacenter_result.status == "FAILED"
                or swingmaster_result.result_check_status == "FAILED"
                or swingmaster_result.weekly_update_status == "FAILED"
                else market_update_phase_status
            )
            if (
                overall_status == STATUS_OK
                and (
                    ec_source_layer_result.status in _bridge_failure_statuses()
                    or ec_source_layer_result.bridge_status == "FAILED"
                )
            ):
                overall_status = STATUS_OK_WITH_WARNINGS
            ec_failed = (
                ec_source_layer_result.status in _bridge_failure_statuses()
                or ec_source_layer_result.bridge_status == "FAILED"
            )
            datacenter_failed_component = (
                "DATACENTER_PIPELINE"
                if datacenter_result.status == "FAILED"
                else "EC_BRIDGE"
                if ec_failed
                else "NONE"
            )
            datacenter_safe_next_action = (
                "RUN_CONTROLLED_EC_BRIDGE_RECOVERY"
                if ec_source_layer_result.bridge_retry_required
                else "INSPECT_DATACENTER_PIPELINE_FAILURE"
                if datacenter_result.status == "FAILED"
                else "NONE"
            )

            log_dir = Path(config.log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            summary_json_path = log_dir / (
                "stock_update_scheduler_summary_"
                f"{_format_utc_filename_timestamp(run_started_at)}.json"
            )
            finished_at_utc = _format_utc_timestamp(_utc_now())

            result = ScheduledStockUpdateRunResult(
                started_at_utc=started_at_utc,
                finished_at_utc=finished_at_utc,
                config_path=config_path,
                enabled_markets=list(config.enabled_markets),
                market_results=market_results,
                overall_status=overall_status,
                skipped=False,
                skip_reason=None,
                technical_relevance_attempted=technical_relevance_result.attempted,
                technical_relevance_enabled=technical_relevance_result.enabled,
                technical_relevance_status=technical_relevance_result.status,
                technical_relevance_market=technical_relevance_result.market,
                technical_relevance_run_id=technical_relevance_result.run_id or "NONE",
                technical_relevance_ticker_count=technical_relevance_result.ticker_count,
                technical_relevance_start_date=technical_relevance_result.start_date or "NONE",
                technical_relevance_end_date=technical_relevance_result.end_date or "NONE",
                technical_relevance_requested_calendar_signal_date=technical_relevance_result.requested_calendar_signal_date
                or "NONE",
                technical_relevance_end_date_source=technical_relevance_result.end_date_source,
                technical_relevance_end_date_resolution=technical_relevance_result.end_date_resolution,
                technical_relevance_end_date_min_price_ticker_count=technical_relevance_result.min_price_ticker_count,
                technical_relevance_end_date_candidate_count=technical_relevance_result.candidate_count,
                technical_relevance_ticker_valid_date_count=technical_relevance_result.ticker_valid_date_count,
                technical_relevance_records_written=technical_relevance_result.records_written,
                technical_relevance_relevant_count=technical_relevance_result.relevant_count,
                technical_relevance_weak_context_count=technical_relevance_result.weak_context_count,
                technical_relevance_noise_count=technical_relevance_result.noise_count,
                technical_relevance_unknown_signal_count=technical_relevance_result.unknown_signal_count,
                technical_relevance_missing_dow_context_count=technical_relevance_result.missing_dow_context_count,
                technical_relevance_missing_bar_index_count=technical_relevance_result.missing_bar_index_count,
                technical_relevance_duration_seconds=technical_relevance_result.duration_seconds,
                technical_relevance_skip_reason=technical_relevance_result.skip_reason,
                technical_relevance_error=technical_relevance_result.error or "",
                datacenter_pipeline_attempted=datacenter_result.attempted,
                datacenter_pipeline_status=datacenter_result.status,
                datacenter_pipeline_market=datacenter_result.market,
                datacenter_pipeline_audit_validation_status=datacenter_result.audit_validation_status,
                datacenter_pipeline_log_path=datacenter_result.log_path,
                datacenter_pipeline_signal_date=datacenter_result.signal_date or "NONE",
                datacenter_pipeline_signal_date_source=datacenter_result.signal_date_source,
                datacenter_pipeline_signal_date_resolution=datacenter_result.signal_date_resolution,
                datacenter_pipeline_requested_calendar_signal_date=(
                    datacenter_result.requested_calendar_signal_date or "NONE"
                ),
                datacenter_pipeline_configured_taxonomy_version=(
                    datacenter_result.configured_taxonomy_version
                ),
                datacenter_pipeline_configured_taxonomy_csv=(
                    datacenter_result.configured_taxonomy_csv
                ),
                datacenter_pipeline_configured_taxonomy_sha256=(
                    datacenter_result.configured_taxonomy_sha256
                ),
                datacenter_pipeline_derived_taxonomy_row_count=(
                    datacenter_result.derived_taxonomy_row_count
                ),
                datacenter_pipeline_derived_ticker_count=(
                    datacenter_result.derived_ticker_count
                ),
                datacenter_pipeline_derived_group_count=(
                    datacenter_result.derived_group_count
                ),
                datacenter_pipeline_derived_synthetic_group_count=(
                    datacenter_result.derived_synthetic_group_count
                ),
                datacenter_pipeline_daily_report_path=datacenter_result.daily_report_path,
                datacenter_pipeline_daily_report_csv_path=datacenter_result.daily_report_csv_path,
                datacenter_pipeline_rolling_30_report_path=datacenter_result.rolling_30_report_path,
                datacenter_pipeline_rolling_30_report_csv_path=datacenter_result.rolling_30_report_csv_path,
                datacenter_pipeline_rolling_5_report_path=datacenter_result.rolling_5_report_path,
                datacenter_pipeline_rolling_5_report_csv_path=datacenter_result.rolling_5_report_csv_path,
                datacenter_pipeline_rolling_2_report_path=datacenter_result.rolling_2_report_path,
                datacenter_pipeline_rolling_2_report_csv_path=datacenter_result.rolling_2_report_csv_path,
                datacenter_pipeline_weekly_report_path=datacenter_result.weekly_report_path,
                datacenter_pipeline_weekly_report_csv_path=datacenter_result.weekly_report_csv_path,
                datacenter_pipeline_error=datacenter_result.error or "",
                watchlist_reconciliation_attempted=(
                    datacenter_result.watchlist_reconciliation_attempted
                ),
                watchlist_reconciliation_status=(
                    datacenter_result.watchlist_reconciliation_status
                ),
                watchlist_source_reference=datacenter_result.watchlist_source_reference,
                watchlist_source_sha256=datacenter_result.watchlist_source_sha256,
                watchlist_source_member_count=datacenter_result.watchlist_source_member_count,
                watchlist_previous_member_count=datacenter_result.watchlist_previous_member_count,
                watchlist_current_member_count=datacenter_result.watchlist_current_member_count,
                watchlist_added_count=datacenter_result.watchlist_added_count,
                watchlist_removed_count=datacenter_result.watchlist_removed_count,
                watchlist_added_tickers=datacenter_result.watchlist_added_tickers,
                watchlist_removed_tickers=datacenter_result.watchlist_removed_tickers,
                watchlist_reconciliation_error=datacenter_result.watchlist_reconciliation_error,
                ec_source_layer_attempted=ec_source_layer_result.attempted,
                ec_source_layer_status=ec_source_layer_result.status,
                ec_source_layer_log_path=ec_source_layer_result.log_path,
                ec_source_layer_signal_date=ec_source_layer_result.signal_date,
                ec_source_layer_refresh_mode=ec_source_layer_result.refresh_mode,
                ec_source_layer_skipped_reason=ec_source_layer_result.skipped_reason,
                ec_source_layer_backup_path=ec_source_layer_result.backup_path,
                ec_source_layer_coverage_status=ec_source_layer_result.coverage_status,
                ec_source_layer_parity_status=ec_source_layer_result.parity_status,
                ec_source_layer_total_mismatch_count=ec_source_layer_result.total_mismatch_count,
                ec_source_layer_ticker_rows=ec_source_layer_result.ticker_rows,
                ec_source_layer_group_signal_rows=ec_source_layer_result.group_signal_rows,
                ec_source_layer_synthetic_ohlc_rows=ec_source_layer_result.synthetic_ohlc_rows,
                ec_source_layer_group_index_rows=ec_source_layer_result.group_index_rows,
                ec_source_layer_watermark_rows=ec_source_layer_result.watermark_rows,
                ec_source_layer_error=ec_source_layer_result.error,
                ec_bridge_mode=ec_source_layer_result.bridge_mode,
                ec_bridge_reason=ec_source_layer_result.bridge_reason,
                ec_bridge_required_start=ec_source_layer_result.bridge_required_start,
                ec_bridge_required_end=ec_source_layer_result.bridge_required_end,
                ec_bridge_status=ec_source_layer_result.bridge_status,
                ec_bridge_load_status=ec_source_layer_result.bridge_load_status,
                ec_bridge_coverage_status=ec_source_layer_result.bridge_coverage_status,
                ec_bridge_parity_status=ec_source_layer_result.bridge_parity_status,
                ec_bridge_retry_required=ec_source_layer_result.bridge_retry_required,
                ec_bridge_exit_code=ec_source_layer_result.bridge_exit_code,
                ec_bridge_error=ec_source_layer_result.bridge_error,
                ec_bridge_log=ec_source_layer_result.bridge_log,
                ec_bridge_watermark_refresh_performed=(
                    ec_source_layer_result.bridge_watermark_refresh_performed
                ),
                ec_bridge_watchlist_membership_status=(
                    ec_source_layer_result.bridge_watchlist_membership_status
                ),
                ec_bridge_watchlist_sync_required=(
                    ec_source_layer_result.bridge_watchlist_sync_required
                ),
                ec_bridge_watchlist_missing_in_loaded_count=(
                    ec_source_layer_result.bridge_watchlist_missing_in_loaded_count
                ),
                ec_bridge_watchlist_loaded_only_count=(
                    ec_source_layer_result.bridge_watchlist_loaded_only_count
                ),
                datacenter_dc_status=datacenter_result.status,
                datacenter_ec_status=ec_source_layer_result.bridge_status
                or ec_source_layer_result.status,
                datacenter_ec_retry_required=(
                    ec_source_layer_result.bridge_retry_required
                ),
                datacenter_taxonomy_version=(
                    datacenter_result.configured_taxonomy_version
                    or config.datacenter_taxonomy_version
                ),
                datacenter_failed_component=datacenter_failed_component,
                datacenter_safe_next_action=datacenter_safe_next_action,
                swingmaster_fundamentals_attempted=swingmaster_result.attempted,
                swingmaster_result_check_status=swingmaster_result.result_check_status,
                swingmaster_result_check_exit_code=swingmaster_result.result_check_exit_code,
                swingmaster_result_check_log_path=swingmaster_result.result_check_log_path,
                swingmaster_result_check_plan_json=swingmaster_result.result_check_plan_json,
                swingmaster_result_check_candidate_count=swingmaster_result.result_check_candidate_count,
                swingmaster_result_check_error=swingmaster_result.result_check_error,
                swingmaster_active_tickers=swingmaster_result.active_tickers,
                swingmaster_7_day_watch_window_count=swingmaster_result.seven_day_watch_window_count,
                swingmaster_due_for_result_check=swingmaster_result.due_for_result_check,
                swingmaster_future_confirmation_provider_calls_now=(
                    swingmaster_result.future_confirmation_provider_calls_now
                ),
                swingmaster_failure_retries=swingmaster_result.failure_retries,
                swingmaster_maintenance_selected=swingmaster_result.maintenance_selected,
                swingmaster_total_unique_provider_check_tickers=(
                    swingmaster_result.total_unique_provider_check_tickers
                ),
                swingmaster_maintenance_backlog_remaining=(
                    swingmaster_result.maintenance_backlog_remaining
                ),
                swingmaster_weekly_update_attempted=swingmaster_result.weekly_update_attempted,
                swingmaster_weekly_update_status=swingmaster_result.weekly_update_status,
                swingmaster_weekly_update_exit_code=swingmaster_result.weekly_update_exit_code,
                swingmaster_weekly_update_log_path=swingmaster_result.weekly_update_log_path,
                swingmaster_weekly_update_plan_json=swingmaster_result.weekly_update_plan_json,
                swingmaster_weekly_update_planned_candidates=(
                    swingmaster_result.weekly_update_planned_candidates
                ),
                swingmaster_weekly_update_successful_candidates=(
                    swingmaster_result.weekly_update_successful_candidates
                ),
                swingmaster_weekly_update_failed_candidates=(
                    swingmaster_result.weekly_update_failed_candidates
                ),
                swingmaster_weekly_update_retryable_candidates=(
                    swingmaster_result.weekly_update_retryable_candidates
                ),
                swingmaster_weekly_update_error=swingmaster_result.weekly_update_error,
            )
            _write_summary_json(config=config, run_started_at=run_started_at, result=result)
            write_scheduler_status(
                log_dir=config.log_dir,
                is_running=False,
                started_at_utc=started_at_utc,
                finished_at_utc=result.finished_at_utc,
                current_market=None,
                last_status=result.overall_status,
                summary_json_path=result.summary_json_path,
                error=None,
            )
            return result
        except BaseException as exc:
            if status_initialized:
                error = str(exc)
                if not error:
                    error = exc.__class__.__name__
                write_scheduler_status(
                    log_dir=config.log_dir,
                    is_running=False,
                    started_at_utc=started_at_utc,
                    finished_at_utc=_format_utc_timestamp(_utc_now()),
                    current_market=None,
                    last_status=STATUS_FAILED,
                    summary_json_path=None,
                    error=error,
                )
            raise
