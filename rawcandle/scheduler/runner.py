from __future__ import annotations

import datetime
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from main import RawCandleApp, _today_exclusive_end_date
from rawcandle.scheduler.config import (
    StockUpdateSchedulerConfig,
    read_scheduler_config,
    write_scheduler_config,
)
from services.stock_update_service import (
    STATUS_FAILED,
    STATUS_OK,
    STATUS_OK_WITH_WARNINGS,
    StockUpdateResult,
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


def _utc_now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _format_utc_timestamp(value: datetime.datetime) -> str:
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_utc_filename_timestamp(value: datetime.datetime) -> str:
    return value.strftime("%Y%m%dT%H%M%SZ")


def _derive_overall_status(market_results: List[ScheduledMarketRunResult]) -> str:
    statuses = [market_result.summary_status for market_result in market_results]
    if any(status == STATUS_FAILED for status in statuses):
        return STATUS_FAILED
    if any(status == STATUS_OK_WITH_WARNINGS for status in statuses):
        return STATUS_OK_WITH_WARNINGS
    return STATUS_OK


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
    started_at_utc: str,
    finished_at_utc: str,
    config: StockUpdateSchedulerConfig,
    summary_lines: List[str],
    ui_summary: str,
    error: Optional[str],
) -> None:
    lines = [
        f"run_started_at_utc={started_at_utc}",
        f"run_finished_at_utc={finished_at_utc}",
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
    log_dir = Path(config.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / (
        f"stock_update_{market}_{_format_utc_filename_timestamp(market_started_at)}.log"
    )

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

    finished_at_utc = _format_utc_timestamp(_utc_now())
    _write_market_log(
        log_path=log_path,
        market=market,
        started_at_utc=started_at_utc,
        finished_at_utc=finished_at_utc,
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

    if config.skip_next_run:
        reset_config = StockUpdateSchedulerConfig(
            enabled_markets=list(config.enabled_markets),
            run_time=config.run_time,
            osakedata_db_path=config.osakedata_db_path,
            analysis_db_path=config.analysis_db_path,
            log_dir=config.log_dir,
            timezone=config.timezone,
            skip_next_run=False,
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
        )
        _write_summary_json(config=config, run_started_at=run_started_at, result=result)
        return result

    effective_today = datetime.datetime.now().strftime("%Y-%m-%d")
    effective_fetch_until_exclusive = _today_exclusive_end_date()

    market_results: List[ScheduledMarketRunResult] = []
    for market in config.enabled_markets:
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
    overall_status = _derive_overall_status(market_results)

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
    )
    _write_summary_json(config=config, run_started_at=run_started_at, result=result)
    return result
