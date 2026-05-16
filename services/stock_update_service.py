from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


STATUS_OK = "OK"
STATUS_OK_WITH_WARNINGS = "OK_WITH_WARNINGS"
STATUS_FAILED = "FAILED"
STATUS_SKIPPED_ALREADY_RUNNING = "SKIPPED_ALREADY_RUNNING"
STATUS_DRY_RUN = "DRY_RUN"

VALID_STOCK_UPDATE_STATUSES = (
    STATUS_OK,
    STATUS_OK_WITH_WARNINGS,
    STATUS_FAILED,
    STATUS_SKIPPED_ALREADY_RUNNING,
    STATUS_DRY_RUN,
)

EVENT_STARTED = "started"
EVENT_TICKER_STARTED = "ticker_started"
EVENT_TICKER_SKIPPED = "ticker_skipped"
EVENT_TICKER_UPDATED = "ticker_updated"
EVENT_TICKER_ERROR = "ticker_error"
EVENT_PAUSE_STARTED = "pause_started"
EVENT_PAUSE_COMPLETED = "pause_completed"
EVENT_DOW_STARTED = "dow_started"
EVENT_DOW_COMPLETED = "dow_completed"
EVENT_COMPLETED = "completed"
EVENT_WARNING = "warning"

VALID_STOCK_UPDATE_EVENT_TYPES = (
    EVENT_STARTED,
    EVENT_TICKER_STARTED,
    EVENT_TICKER_SKIPPED,
    EVENT_TICKER_UPDATED,
    EVENT_TICKER_ERROR,
    EVENT_PAUSE_STARTED,
    EVENT_PAUSE_COMPLETED,
    EVENT_DOW_STARTED,
    EVENT_DOW_COMPLETED,
    EVENT_COMPLETED,
    EVENT_WARNING,
)


@dataclass
class StockUpdateProgressEvent:
    event_type: str
    message: Optional[str] = None
    ticker: Optional[str] = None
    index: Optional[int] = None
    total: Optional[int] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type not in VALID_STOCK_UPDATE_EVENT_TYPES:
            raise ValueError(f"Invalid stock update event_type: {self.event_type}")


@dataclass
class StockUpdateResult:
    market: str
    tickers_checked: int = 0
    tickers_updated: int = 0
    tickers_skipped: int = 0
    tickers_failed: int = 0
    ohlcv_rows_inserted: int = 0
    splits_synced: int = 0
    divergences_updated: int = 0
    candlesticks_updated: int = 0
    dow_structures_updated: Optional[int] = None
    dow_summary: Optional[Dict[str, Any]] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    status: str = STATUS_OK

    def __post_init__(self) -> None:
        if self.status not in VALID_STOCK_UPDATE_STATUSES:
            raise ValueError(f"Invalid stock update status: {self.status}")


ProgressCallback = Optional[Callable[[StockUpdateProgressEvent], None]]


def format_stock_update_summary_lines(result: StockUpdateResult) -> List[str]:
    dow_structures_updated = (
        "" if result.dow_structures_updated is None else result.dow_structures_updated
    )
    return [
        f"SUMMARY market={result.market}",
        f"SUMMARY tickers_checked={result.tickers_checked}",
        f"SUMMARY tickers_updated={result.tickers_updated}",
        f"SUMMARY tickers_skipped={result.tickers_skipped}",
        f"SUMMARY tickers_failed={result.tickers_failed}",
        f"SUMMARY ohlcv_rows_inserted={result.ohlcv_rows_inserted}",
        f"SUMMARY splits_synced={result.splits_synced}",
        f"SUMMARY divergences_updated={result.divergences_updated}",
        f"SUMMARY candlesticks_updated={result.candlesticks_updated}",
        f"SUMMARY dow_structures_updated={dow_structures_updated}",
        f"SUMMARY warnings={len(result.warnings)}",
        f"SUMMARY errors={len(result.errors)}",
        f"SUMMARY status={result.status}",
    ]


def run_stock_data_update(
    *,
    osakedata_db_path: str,
    analysis_db_path: str,
    market: Optional[str] = None,
    start_override: Optional[str] = None,
    progress_callback: ProgressCallback = None,
) -> StockUpdateResult:
    raise NotImplementedError(
        "run_stock_data_update is not implemented yet; extraction will be done in a later step."
    )
