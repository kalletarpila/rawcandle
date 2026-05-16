from __future__ import annotations

import math
import sqlite3
from datetime import date, timedelta
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

DEFAULT_STOCK_UPDATE_MARKET = "omxh"
FALLBACK_TICKER_MARKET = "usa"
LONG_FETCH_RANGE_THRESHOLD_DAYS = 730
LONG_FETCH_CHUNK_DAYS = 365

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
class StockUpdateTickerCandidate:
    ticker: str
    first_date: str
    last_date: str
    market: Optional[str] = None


@dataclass
class StockUpdateDateRange:
    start_date: str
    end_date_exclusive: str


@dataclass
class StockUpdateTickerPlan:
    candidate: StockUpdateTickerCandidate
    needs_update: bool
    update_start_date: Optional[str] = None
    fetch_until_exclusive: Optional[str] = None
    date_ranges: List[StockUpdateDateRange] = field(default_factory=list)
    skip_reason: Optional[str] = None


@dataclass
class StockOhlcvRow:
    ticker: str
    date: str
    open: Optional[float]
    high: Optional[float]
    low: Optional[float]
    close: Optional[float]
    volume: Optional[int]
    market: str


@dataclass
class StockOhlcvInsertResult:
    ticker: str
    rows_seen: int = 0
    rows_inserted: int = 0
    rows_skipped_existing: int = 0


@dataclass
class StockHistoryFetchResult:
    ticker: str
    histories: List[Any] = field(default_factory=list)
    ranges_requested: int = 0
    ranges_returned: int = 0


@dataclass
class StockTickerOhlcvUpdateResult:
    ticker: str
    needs_update: bool
    skipped: bool = False
    skip_reason: Optional[str] = None
    ranges_requested: int = 0
    ranges_returned: int = 0
    history_objects_seen: int = 0
    ohlcv_rows_converted: int = 0
    ohlcv_rows_seen: int = 0
    ohlcv_rows_inserted: int = 0
    ohlcv_rows_skipped_existing: int = 0


@dataclass
class StockTickerDownstreamResult:
    ticker: str
    split_sync_attempted: bool = False
    split_sync_inserted: int = 0
    split_sync_warning: Optional[str] = None
    split_backfill_attempted: bool = False
    split_backfill_recomputed: bool = False
    divergence_attempted: bool = False
    divergence_skipped_reason: Optional[str] = None
    divergence_success: Optional[bool] = None
    divergence_days: Optional[int] = None
    divergence_error: Optional[str] = None
    candlestick_attempted: bool = False
    candlestick_total: Optional[int] = None
    candlestick_error: Optional[str] = None
    warnings: List[str] = field(default_factory=list)


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
SplitSyncCallable = Callable[[str, Any], int]
SplitBackfillCallable = Callable[[str], bool]
DivergenceUpdateCallable = Callable[[str, bool], tuple]
CandlestickUpdateCallable = Callable[[str, str, str], tuple]


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def _is_missing_ohlcv_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        return math.isnan(value)
    except TypeError:
        return False


def _format_history_index_date(index_value: Any) -> str:
    return index_value.strftime("%Y-%m-%d")


def resolve_stock_update_market(market: Optional[str]) -> str:
    if market is None or not market.strip():
        return DEFAULT_STOCK_UPDATE_MARKET
    return market.strip().lower()


def load_grouped_stock_update_candidates(
    osakedata_db_path: str,
) -> List[StockUpdateTickerCandidate]:
    with sqlite3.connect(osakedata_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT osake, MIN(pvm) as ensimmainen_pvm, MAX(pvm) as viimeisin_pvm, MAX(market) as market
            FROM osakedata
            GROUP BY osake
            ORDER BY osake
            """
        )
        rows = cursor.fetchall()

    return [
        StockUpdateTickerCandidate(
            ticker=ticker,
            first_date=first_date,
            last_date=last_date,
            market=market,
        )
        for ticker, first_date, last_date, market in rows
    ]


def filter_stock_update_candidates_by_market(
    candidates: List[StockUpdateTickerCandidate],
    selected_market: str,
) -> List[StockUpdateTickerCandidate]:
    return [
        candidate
        for candidate in candidates
        if (candidate.market or "").strip().lower() == selected_market
    ]


def load_stock_update_candidates_for_market(
    osakedata_db_path: str,
    market: Optional[str],
) -> List[StockUpdateTickerCandidate]:
    selected_market = resolve_stock_update_market(market)
    candidates = load_grouped_stock_update_candidates(osakedata_db_path)
    return filter_stock_update_candidates_by_market(candidates, selected_market)


def resolve_effective_update_start_date(
    *,
    last_date: str,
    start_override: Optional[str] = None,
) -> str:
    base_update_start = (_parse_iso_date(last_date) + timedelta(days=1)).isoformat()
    if start_override is None or not start_override.strip():
        return base_update_start
    parsed_start_override = _parse_iso_date(start_override.strip()).isoformat()
    return max(base_update_start, parsed_start_override)


def split_fetch_date_range(
    *,
    start_date: str,
    end_date_exclusive: str,
) -> List[StockUpdateDateRange]:
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date_exclusive)
    if start >= end:
        return []

    if (end - start).days <= LONG_FETCH_RANGE_THRESHOLD_DAYS:
        return [
            StockUpdateDateRange(
                start_date=start_date,
                end_date_exclusive=end_date_exclusive,
            )
        ]

    date_ranges: List[StockUpdateDateRange] = []
    current_start = start
    while current_start < end:
        current_end = min(current_start + timedelta(days=LONG_FETCH_CHUNK_DAYS), end)
        date_ranges.append(
            StockUpdateDateRange(
                start_date=current_start.isoformat(),
                end_date_exclusive=current_end.isoformat(),
            )
        )
        current_start = current_end
    return date_ranges


def plan_ticker_update(
    *,
    candidate: StockUpdateTickerCandidate,
    today: str,
    fetch_until_exclusive: str,
    start_override: Optional[str] = None,
) -> StockUpdateTickerPlan:
    needs_update = candidate.last_date < today
    if not needs_update:
        return StockUpdateTickerPlan(
            candidate=candidate,
            needs_update=False,
            skip_reason="already_current",
        )

    update_start_date = resolve_effective_update_start_date(
        last_date=candidate.last_date,
        start_override=start_override,
    )
    date_ranges = split_fetch_date_range(
        start_date=update_start_date,
        end_date_exclusive=fetch_until_exclusive,
    )
    return StockUpdateTickerPlan(
        candidate=candidate,
        needs_update=True,
        update_start_date=update_start_date,
        fetch_until_exclusive=fetch_until_exclusive,
        date_ranges=date_ranges,
        skip_reason=None,
    )


def plan_ticker_updates(
    *,
    candidates: List[StockUpdateTickerCandidate],
    today: str,
    fetch_until_exclusive: str,
    start_override: Optional[str] = None,
) -> List[StockUpdateTickerPlan]:
    return [
        plan_ticker_update(
            candidate=candidate,
            today=today,
            fetch_until_exclusive=fetch_until_exclusive,
            start_override=start_override,
        )
        for candidate in candidates
    ]


def load_existing_ohlcv_dates_for_ticker(
    *,
    osakedata_db_path: str,
    ticker: str,
) -> set[str]:
    with sqlite3.connect(osakedata_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT pvm FROM osakedata WHERE osake = ?", (ticker,))
        return {row[0] for row in cursor.fetchall()}


def insert_missing_ohlcv_rows(
    *,
    osakedata_db_path: str,
    ticker: str,
    rows: List[StockOhlcvRow],
) -> StockOhlcvInsertResult:
    existing_dates = load_existing_ohlcv_dates_for_ticker(
        osakedata_db_path=osakedata_db_path,
        ticker=ticker,
    )
    result = StockOhlcvInsertResult(ticker=ticker)

    with sqlite3.connect(osakedata_db_path) as conn:
        cursor = conn.cursor()
        for row in rows:
            result.rows_seen += 1
            if row.date in existing_dates:
                result.rows_skipped_existing += 1
                continue

            cursor.execute(
                """
                INSERT INTO osakedata
                (osake, pvm, open, high, low, close, volume, market)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row.ticker,
                    row.date,
                    row.open,
                    row.high,
                    row.low,
                    row.close,
                    row.volume,
                    row.market,
                ),
            )
            result.rows_inserted += 1
            existing_dates.add(row.date)

        if result.rows_inserted > 0:
            conn.commit()

    return result


def convert_history_to_ohlcv_rows(
    *,
    history: Any,
    ticker: str,
    market: str,
) -> List[StockOhlcvRow]:
    # Current main.py behavior formats the history index with strftime("%Y-%m-%d")
    # and converts required columns directly by name, using pd.notna-style missing
    # checks only for field-level NaN/None handling.
    if history is None:
        return []
    if getattr(history, "empty", False):
        return []

    rows: List[StockOhlcvRow] = []
    for history_index, row in history.iterrows():
        open_value = row["Open"]
        high_value = row["High"]
        low_value = row["Low"]
        close_value = row["Close"]
        volume_value = row["Volume"]

        rows.append(
            StockOhlcvRow(
                ticker=ticker,
                date=_format_history_index_date(history_index),
                open=None if _is_missing_ohlcv_value(open_value) else float(open_value),
                high=None if _is_missing_ohlcv_value(high_value) else float(high_value),
                low=None if _is_missing_ohlcv_value(low_value) else float(low_value),
                close=None
                if _is_missing_ohlcv_value(close_value)
                else float(close_value),
                volume=None
                if _is_missing_ohlcv_value(volume_value)
                else int(volume_value),
                market=market,
            )
        )
    return rows


def fetch_history_for_date_ranges(
    *,
    stock: Any,
    ticker: str,
    date_ranges: List[StockUpdateDateRange],
) -> StockHistoryFetchResult:
    result = StockHistoryFetchResult(ticker=ticker)
    for date_range in date_ranges:
        result.ranges_requested += 1
        history = stock.history(
            start=date_range.start_date,
            end=date_range.end_date_exclusive,
        )
        result.histories.append(history)
        result.ranges_returned += 1
    return result


def convert_histories_to_ohlcv_rows(
    *,
    histories: List[Any],
    ticker: str,
    market: str,
) -> List[StockOhlcvRow]:
    rows: List[StockOhlcvRow] = []
    for history in histories:
        rows.extend(
            convert_history_to_ohlcv_rows(
                history=history,
                ticker=ticker,
                market=market,
            )
        )
    return rows


def execute_ticker_ohlcv_update_plan(
    *,
    osakedata_db_path: str,
    stock: Any,
    plan: StockUpdateTickerPlan,
    market: str,
) -> StockTickerOhlcvUpdateResult:
    if plan.needs_update is False:
        return StockTickerOhlcvUpdateResult(
            ticker=plan.candidate.ticker,
            needs_update=False,
            skipped=True,
            skip_reason=plan.skip_reason,
        )

    # Empty histories are preserved by fetch_history_for_date_ranges(...), but
    # convert_histories_to_ohlcv_rows(...) turns them into zero rows, so this
    # helper naturally yields zero converted/inserted rows when all histories are empty.
    fetch_result = fetch_history_for_date_ranges(
        stock=stock,
        ticker=plan.candidate.ticker,
        date_ranges=plan.date_ranges,
    )
    converted_rows = convert_histories_to_ohlcv_rows(
        histories=fetch_result.histories,
        ticker=plan.candidate.ticker,
        market=market,
    )
    insert_result = insert_missing_ohlcv_rows(
        osakedata_db_path=osakedata_db_path,
        ticker=plan.candidate.ticker,
        rows=converted_rows,
    )
    return StockTickerOhlcvUpdateResult(
        ticker=plan.candidate.ticker,
        needs_update=True,
        skipped=False,
        skip_reason=None,
        ranges_requested=fetch_result.ranges_requested,
        ranges_returned=fetch_result.ranges_returned,
        history_objects_seen=len(fetch_result.histories),
        ohlcv_rows_converted=len(converted_rows),
        ohlcv_rows_seen=insert_result.rows_seen,
        ohlcv_rows_inserted=insert_result.rows_inserted,
        ohlcv_rows_skipped_existing=insert_result.rows_skipped_existing,
    )


def execute_ticker_downstream_updates(
    *,
    ticker: str,
    stock: Any,
    ohlcv_rows_inserted: int,
    date_ranges: List[StockUpdateDateRange],
    sync_splits: SplitSyncCallable,
    maybe_backfill_splits: SplitBackfillCallable,
    calculate_divergences: DivergenceUpdateCallable,
    run_candlestick_analysis: CandlestickUpdateCallable,
) -> StockTickerDownstreamResult:
    # This helper starts only after outer orchestration has already decided the
    # ticker reached the post-OHLCV downstream section. Empty-history / no-data
    # classification remains outside this helper.
    result = StockTickerDownstreamResult(ticker=ticker)

    result.split_sync_attempted = True
    try:
        result.split_sync_inserted = sync_splits(ticker, stock)
    except Exception as exc:
        warning = f"Splittien paivitys epaonnistui ({ticker}): {exc}"
        result.split_sync_warning = warning
        result.warnings.append(warning)

    result.split_backfill_attempted = True
    result.split_backfill_recomputed = bool(maybe_backfill_splits(ticker))

    if result.split_backfill_recomputed:
        result.divergence_attempted = False
        result.divergence_skipped_reason = "split_backfill_recomputed"
        result.divergence_success = True
        result.divergence_days = 0
        result.divergence_error = ""
    else:
        result.divergence_attempted = True
        div_success, div_days, div_error = calculate_divergences(ticker, True)
        result.divergence_success = div_success
        result.divergence_days = div_days
        result.divergence_error = div_error

    if ohlcv_rows_inserted <= 0:
        return result

    analysis_start = min(date_range.start_date for date_range in date_ranges)
    analysis_end = max(date_range.end_date_exclusive for date_range in date_ranges)

    result.candlestick_attempted = True
    try:
        analysis_total, analysis_error = run_candlestick_analysis(
            ticker,
            analysis_start,
            analysis_end,
        )
        result.candlestick_total = analysis_total
        result.candlestick_error = analysis_error
    except Exception as exc:
        warning = f"Candlestick-analyysi epaonnistui ({ticker}): {exc}"
        result.candlestick_total = 0
        result.candlestick_error = str(exc)
        result.warnings.append(warning)

    return result


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
