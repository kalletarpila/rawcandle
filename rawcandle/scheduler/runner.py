from __future__ import annotations

import datetime
import errno
import fcntl
import json
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import IO, Iterator, List, Optional
from zoneinfo import ZoneInfo

from main import RawCandleApp, _today_exclusive_end_date
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
    datacenter_dashboard_attempted: int = 0
    datacenter_dashboard_status: str = "SKIPPED"
    datacenter_dashboard_dashboard_db: str = ""
    datacenter_dashboard_report_date: str = ""
    datacenter_dashboard_md_reports_status: str = "SKIPPED"
    datacenter_dashboard_source_reports_available: int = 0
    datacenter_dashboard_html_output_path: str = ""
    datacenter_dashboard_run_id: str = ""
    datacenter_dashboard_skip_reason: str = ""
    datacenter_dashboard_error: str = ""


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
class DatacenterDashboardPostStepResult:
    attempted: int
    status: str
    dashboard_db: str = ""
    report_date: str = ""
    md_reports_status: str = "SKIPPED"
    source_reports_available: int = 0
    html_output_path: str = ""
    run_id: str = ""
    skip_reason: str = ""
    error: Optional[str] = None


@dataclass(frozen=True)
class SchedulerDashboardConfigInspection:
    enabled: int
    ecosystem_code: str
    dashboard_db: str
    reports_dir: str
    html_output_dir: str
    expected_report_date: str
    expected_html_output_path: str
    mode: str
    render_html: int
    usa_enabled: int
    datacenter_pipeline_enabled: int
    skip_next_run: int
    date_status: str
    status: str


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
    status_path.write_text(
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


def _resolve_datacenter_post_step_config(market: str) -> Optional[DatacenterPostStepConfig]:
    if market != "usa":
        return None
    return DatacenterPostStepConfig(
        market="usa",
        taxonomy_csv="data/datacenter_ecosystem_taxonomy_full_v1.csv",
        taxonomy_version="DC_TAXONOMY_FULL_V1",
        start_date="2025-08-01",
        index_base_date="2020-01-01",
        output_dir="/home/kalle/projects/rawcandle/swing_reports",
        expected_ticker_count=236,
        expected_group_count=54,
        expected_synthetic_ohlc_count=53,
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


def _default_datacenter_dashboard_result(
    *,
    config: StockUpdateSchedulerConfig,
    status: str = "SKIPPED",
    report_date: str = "",
    md_reports_status: str = "SKIPPED",
    skip_reason: str = "",
    error: str | None = None,
) -> DatacenterDashboardPostStepResult:
    return DatacenterDashboardPostStepResult(
        attempted=0,
        status=status,
        dashboard_db=config.datacenter_dashboard_db,
        report_date=report_date,
        md_reports_status=md_reports_status,
        source_reports_available=0,
        html_output_path="",
        run_id="",
        skip_reason=skip_reason,
        error=error,
    )


def _resolve_datacenter_dashboard_html_output_path(
    config: StockUpdateSchedulerConfig,
    report_date: str,
) -> str:
    return str(
        Path(config.datacenter_dashboard_html_output_dir)
        / f"datacenter_dashboard_{report_date}.html"
    )


def inspect_scheduler_dashboard_config(
    *,
    config_path: str,
    effective_today: str | None = None,
) -> SchedulerDashboardConfigInspection:
    config = read_scheduler_config(config_path)
    resolved_post_step = _resolve_datacenter_post_step_config("usa")
    reports_dir = resolved_post_step.output_dir if resolved_post_step is not None else ""
    date_status = "UNAVAILABLE"
    expected_report_date = ""
    expected_html_output_path = ""
    if effective_today is not None:
        expected_report_date = _previous_calendar_date(effective_today)
        expected_html_output_path = _resolve_datacenter_dashboard_html_output_path(
            config,
            expected_report_date,
        )
        date_status = "OK"

    return SchedulerDashboardConfigInspection(
        enabled=1 if config.datacenter_dashboard_enabled else 0,
        ecosystem_code="DATACENTER",
        dashboard_db=config.datacenter_dashboard_db,
        reports_dir=reports_dir,
        html_output_dir=config.datacenter_dashboard_html_output_dir,
        expected_report_date=expected_report_date,
        expected_html_output_path=expected_html_output_path,
        mode="replace-date",
        render_html=1,
        usa_enabled=1 if "usa" in config.enabled_markets else 0,
        datacenter_pipeline_enabled=1 if resolved_post_step is not None else 0,
        skip_next_run=1 if config.skip_next_run else 0,
        date_status=date_status,
        status="OK",
    )


def _run_datacenter_dashboard_post_step(
    *,
    config: StockUpdateSchedulerConfig,
    reports_dir: str,
    report_date: str,
    render_html: bool,
    html_output: str,
) -> DatacenterDashboardPostStepResult:
    from dev_tools.datacenter_dashboard_support import discover_datacenter_dashboard_status
    from dev_tools.run_datacenter_dashboard_html import generate_datacenter_dashboard_html_file
    from dev_tools.run_ecosystem_dashboard_build import generate_ecosystem_dashboard_build

    if not config.datacenter_dashboard_enabled:
        return _default_datacenter_dashboard_result(
            config=config,
            report_date=report_date,
            skip_reason="DATACENTER_DASHBOARD_DISABLED",
        )

    dashboard_status = discover_datacenter_dashboard_status(
        reports_dir,
        report_date=report_date,
    )
    source_reports_available = sum(
        1 for report in dashboard_status.reports if report.status == "OK"
    )
    if dashboard_status.overall_status != "READY":
        return DatacenterDashboardPostStepResult(
            attempted=0,
            status="FAILED",
            dashboard_db=config.datacenter_dashboard_db,
            report_date=report_date,
            md_reports_status="MISSING",
            source_reports_available=source_reports_available,
            html_output_path=html_output,
            run_id="",
            skip_reason="DATACENTER_MD_REPORTS_MISSING",
            error=f"missing dashboard source reports for report_date={report_date}",
        )

    try:
        built_run_id, _summary_lines = generate_ecosystem_dashboard_build(
            dashboard_db=config.datacenter_dashboard_db,
            ecosystem_code="DATACENTER",
            reports_dir=reports_dir,
            report_date=report_date,
            mode="replace-date",
            run_id=None,
        )
    except Exception as exc:
        return DatacenterDashboardPostStepResult(
            attempted=1,
            status="FAILED",
            dashboard_db=config.datacenter_dashboard_db,
            report_date=report_date,
            md_reports_status="OK",
            source_reports_available=source_reports_available,
            html_output_path=html_output,
            run_id="",
            skip_reason="DASHBOARD_BUILD_FAILED",
            error=str(exc),
        )

    if render_html:
        try:
            generate_datacenter_dashboard_html_file(
                dashboard_db=config.datacenter_dashboard_db,
                ecosystem_code="DATACENTER",
                run_id=built_run_id,
                output=html_output,
                report_date=None,
                title=None,
            )
        except Exception as exc:
            return DatacenterDashboardPostStepResult(
                attempted=1,
                status="FAILED",
                dashboard_db=config.datacenter_dashboard_db,
                report_date=report_date,
                md_reports_status="OK",
                source_reports_available=source_reports_available,
                html_output_path=html_output,
                run_id=built_run_id,
                skip_reason="DASHBOARD_HTML_RENDER_FAILED",
                error=str(exc),
            )

    return DatacenterDashboardPostStepResult(
        attempted=1,
        status="OK",
        dashboard_db=config.datacenter_dashboard_db,
        report_date=report_date,
        md_reports_status="OK",
        source_reports_available=source_reports_available,
        html_output_path=html_output,
        run_id=built_run_id,
        skip_reason="",
        error=None,
    )


def _run_technical_relevance_post_step(
    *,
    config: StockUpdateSchedulerConfig,
    target_market: str,
    market_update_phase_status: str,
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

    end_date = _resolve_latest_valid_ohlcv_date_for_market(
        config.osakedata_db_path,
        target_market,
    )
    if end_date is None:
        return TechnicalRelevancePostStepResult(
            attempted=0,
            enabled=True,
            status="SKIPPED",
            market=target_market,
            skip_reason="NO_VALID_OHLCV_DATE_FOR_MARKET",
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
    resolved = _resolve_datacenter_post_step_config(target_market)
    if resolved is None:
        return DatacenterPostStepResult(
            attempted=0,
            status="SKIPPED",
            market=target_market,
        )

    started_at = _utc_now()
    requested_calendar_signal_date = _previous_calendar_date(effective_today)
    signal_date = _resolve_latest_valid_ohlcv_date_for_market(
        config.osakedata_db_path,
        resolved.market,
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
            "signal_date_source=LATEST_VALID_OHLCV_DATE",
            "signal_date_resolution=LATEST_VALID_OHLCV_DATE",
            f"osakedata_db_path={config.osakedata_db_path}",
            f"analysis_db_path={config.analysis_db_path}",
            "skip_reason=NO_VALID_OHLCV_DATE_FOR_MARKET",
        ]
        log_path.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
        return DatacenterPostStepResult(
            attempted=0,
            status="SKIPPED",
            market=resolved.market,
            audit_validation_status="SKIPPED",
            log_path=str(log_path),
            signal_date=None,
            signal_date_source="LATEST_VALID_OHLCV_DATE",
            signal_date_resolution="LATEST_VALID_OHLCV_DATE",
            requested_calendar_signal_date=requested_calendar_signal_date,
            error="NO_VALID_OHLCV_DATE_FOR_MARKET",
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
        "signal_date_source=LATEST_VALID_OHLCV_DATE",
        "signal_date_resolution=LATEST_VALID_OHLCV_DATE",
        f"osakedata_db_path={config.osakedata_db_path}",
        f"analysis_db_path={config.analysis_db_path}",
        f"command={' '.join(command)}",
        f"returncode={completed.returncode}",
        "=== STDOUT ===",
        completed.stdout.rstrip(),
        "=== STDERR ===",
        completed.stderr.rstrip(),
    ]
    log_path.write_text("\n".join(log_lines).rstrip() + "\n", encoding="utf-8")
    audit_validation_status = _parse_summary_value(
        completed.stdout or "", "audit_validation_status"
    )
    parsed_report_paths = _parse_datacenter_report_paths(completed.stdout or "")
    if completed.returncode != 0:
        return DatacenterPostStepResult(
            attempted=1,
            status="FAILED",
            market=resolved.market,
            audit_validation_status=audit_validation_status or "UNKNOWN",
            log_path=str(log_path),
            signal_date=signal_date,
            signal_date_source="LATEST_VALID_OHLCV_DATE",
            signal_date_resolution="LATEST_VALID_OHLCV_DATE",
            requested_calendar_signal_date=requested_calendar_signal_date,
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
            error=f"datacenter pipeline exited with code {completed.returncode}",
        )
    return DatacenterPostStepResult(
        attempted=1,
        status="OK",
        market=resolved.market,
        audit_validation_status=audit_validation_status or "UNKNOWN",
        log_path=str(log_path),
        signal_date=signal_date,
        signal_date_source="LATEST_VALID_OHLCV_DATE",
        signal_date_resolution="LATEST_VALID_OHLCV_DATE",
        requested_calendar_signal_date=requested_calendar_signal_date,
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
                reset_config = StockUpdateSchedulerConfig(
                    enabled_markets=list(config.enabled_markets),
                    run_time=config.run_time,
                    osakedata_db_path=config.osakedata_db_path,
                    analysis_db_path=config.analysis_db_path,
                    log_dir=config.log_dir,
                    timezone=config.timezone,
                    skip_next_run=False,
                    technical_relevance_enabled=config.technical_relevance_enabled,
                    datacenter_dashboard_enabled=config.datacenter_dashboard_enabled,
                    datacenter_dashboard_db=config.datacenter_dashboard_db,
                    datacenter_dashboard_html_output_dir=config.datacenter_dashboard_html_output_dir,
                )
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
                    datacenter_dashboard_attempted=0,
                    datacenter_dashboard_status="SKIPPED",
                    datacenter_dashboard_dashboard_db=config.datacenter_dashboard_db,
                    datacenter_dashboard_report_date="",
                    datacenter_dashboard_md_reports_status="SKIPPED",
                    datacenter_dashboard_source_reports_available=0,
                    datacenter_dashboard_html_output_path="",
                    datacenter_dashboard_run_id="",
                    datacenter_dashboard_skip_reason="SKIP_NEXT_RUN",
                    datacenter_dashboard_error="",
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

            finished_at_utc = _format_utc_timestamp(_utc_now())
            market_update_phase_status = _derive_overall_status(market_results)
            technical_relevance_result = _run_technical_relevance_post_step(
                config=config,
                target_market="usa",
                market_update_phase_status=market_update_phase_status,
            )
            datacenter_result = DatacenterPostStepResult(
                attempted=0,
                status="SKIPPED",
                market="usa",
            )
            datacenter_dashboard_result = _default_datacenter_dashboard_result(
                config=config,
                skip_reason="USA_NOT_ENABLED"
                if "usa" not in config.enabled_markets
                else "MARKET_PHASE_FAILED"
                if market_update_phase_status not in (STATUS_OK, STATUS_OK_WITH_WARNINGS)
                else "",
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
                if datacenter_result.status == "OK" and datacenter_result.signal_date:
                    datacenter_dashboard_result = _run_datacenter_dashboard_post_step(
                        config=config,
                        reports_dir=_resolve_datacenter_post_step_config(
                            datacenter_result.market
                        ).output_dir,
                        report_date=datacenter_result.signal_date,
                        render_html=True,
                        html_output=_resolve_datacenter_dashboard_html_output_path(
                            config,
                            datacenter_result.signal_date,
                        ),
                    )
                elif datacenter_result.status == "FAILED":
                    datacenter_dashboard_result = _default_datacenter_dashboard_result(
                        config=config,
                        report_date=datacenter_result.signal_date or "",
                        md_reports_status="FAILED",
                        skip_reason="DATACENTER_PIPELINE_FAILED",
                        error=datacenter_result.error,
                    )
                else:
                    datacenter_dashboard_result = _default_datacenter_dashboard_result(
                        config=config,
                        report_date=datacenter_result.signal_date or "",
                        md_reports_status="SKIPPED",
                        skip_reason="DATACENTER_PIPELINE_SKIPPED",
                        error=datacenter_result.error,
                    )
            overall_status = (
                STATUS_FAILED
                if technical_relevance_result.status == "FAILED"
                or datacenter_result.status == "FAILED"
                or datacenter_dashboard_result.status == "FAILED"
                else market_update_phase_status
            )

            log_dir = Path(config.log_dir)
            log_dir.mkdir(parents=True, exist_ok=True)
            summary_json_path = log_dir / (
                "stock_update_scheduler_summary_"
                f"{_format_utc_filename_timestamp(run_started_at)}.json"
            )

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
                datacenter_dashboard_attempted=datacenter_dashboard_result.attempted,
                datacenter_dashboard_status=datacenter_dashboard_result.status,
                datacenter_dashboard_dashboard_db=datacenter_dashboard_result.dashboard_db,
                datacenter_dashboard_report_date=datacenter_dashboard_result.report_date,
                datacenter_dashboard_md_reports_status=datacenter_dashboard_result.md_reports_status,
                datacenter_dashboard_source_reports_available=(
                    datacenter_dashboard_result.source_reports_available
                ),
                datacenter_dashboard_html_output_path=datacenter_dashboard_result.html_output_path,
                datacenter_dashboard_run_id=datacenter_dashboard_result.run_id,
                datacenter_dashboard_skip_reason=datacenter_dashboard_result.skip_reason,
                datacenter_dashboard_error=datacenter_dashboard_result.error or "",
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
        except Exception as exc:
            if status_initialized:
                write_scheduler_status(
                    log_dir=config.log_dir,
                    is_running=False,
                    started_at_utc=started_at_utc,
                    finished_at_utc=_format_utc_timestamp(_utc_now()),
                    current_market=None,
                    last_status=STATUS_FAILED,
                    summary_json_path=None,
                    error=str(exc),
                )
            raise
