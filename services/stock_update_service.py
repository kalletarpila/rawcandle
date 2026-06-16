from __future__ import annotations

import math
import sqlite3
import time
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
class StockTickerUpdateFlowResult:
    ticker: str
    skipped: bool = False
    skip_reason: Optional[str] = None
    ohlcv_result: Optional[StockTickerOhlcvUpdateResult] = None
    downstream_result: Optional[StockTickerDownstreamResult] = None
    quarter_state_outcome: Optional[Dict[str, Any]] = None
    quarter_state_error: bool = False


@dataclass
class StockUpdateBatchExecutionResult:
    market: str
    ticker_results: List[StockTickerUpdateFlowResult] = field(default_factory=list)
    tickers_checked: int = 0
    tickers_updated: int = 0
    tickers_skipped: int = 0
    tickers_failed: int = 0
    ohlcv_rows_inserted: int = 0
    quarter_state_checked: int = 0
    quarter_state_new_detected: int = 0
    quarter_state_detection_missing: int = 0
    quarter_state_rows_updated: int = 0
    quarter_state_errors: int = 0
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class StockUpdateDowResult:
    attempted: bool = False
    success: bool = False
    dow_summary: Optional[Dict[str, Any]] = None
    warning: Optional[str] = None


@dataclass
class StockUpdateOrchestrationResult:
    batch_result: StockUpdateBatchExecutionResult
    dow_result: Optional[StockUpdateDowResult] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


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
    quarter_state_checked: int = 0
    quarter_state_new_detected: int = 0
    quarter_state_detection_missing: int = 0
    quarter_state_rows_updated: int = 0
    quarter_state_errors: int = 0
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
StockFactory = Callable[[str], Any]
DowUpdateCallable = Callable[..., Dict[str, Any]]
SplitSyncCallable = Callable[[str, Any], int]
SplitBackfillCallable = Callable[[str], bool]
DivergenceUpdateCallable = Callable[[str, bool], tuple]
CandlestickUpdateCallable = Callable[[str, str, str], tuple]
QuarterStateUpdateCallable = Callable[[str, str, Any], Any]

# Still intentionally conservative, but reduced to shorten USA overnight runs.
YAHOO_SHORT_BRANCH_SLEEP_SECONDS = 0.1
YAHOO_SUCCESS_LARGE_INSERT_SLEEP_SECONDS = 0.25
YAHOO_SUCCESS_SMALL_INSERT_SLEEP_SECONDS = 0.25
YAHOO_LARGE_BATCH_SLEEP_SECONDS = 5.0
YAHOO_LARGE_BATCH_INTERVAL = 500


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def _is_missing_ohlcv_value(value: Any) -> bool:
    if value is None:
        return True
    try:
        return math.isnan(value)
    except TypeError:
        return False


def _has_complete_ohlc_values(
    open_value: Any,
    high_value: Any,
    low_value: Any,
    close_value: Any,
) -> bool:
    return not any(
        _is_missing_ohlcv_value(value)
        for value in (open_value, high_value, low_value, close_value)
    )


def _format_history_index_date(index_value: Any) -> str:
    return index_value.strftime("%Y-%m-%d")


def _sleep_yahoo_after_history_range() -> None:
    time.sleep(YAHOO_SHORT_BRANCH_SLEEP_SECONDS)


def _sleep_yahoo_after_ticker(rows_added: Optional[int]) -> None:
    if rows_added is None:
        time.sleep(YAHOO_SHORT_BRANCH_SLEEP_SECONDS)
        return
    if rows_added >= 50:
        time.sleep(YAHOO_SUCCESS_LARGE_INSERT_SLEEP_SECONDS)
        return
    time.sleep(YAHOO_SUCCESS_SMALL_INSERT_SLEEP_SECONDS)


def _sleep_yahoo_large_batch_if_needed(processed_count: int) -> None:
    if processed_count % YAHOO_LARGE_BATCH_INTERVAL == 0:
        time.sleep(YAHOO_LARGE_BATCH_SLEEP_SECONDS)


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
        if not _has_complete_ohlc_values(
            open_value,
            high_value,
            low_value,
            close_value,
        ):
            continue

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
        _sleep_yahoo_after_history_range()
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


def execute_ticker_update_flow(
    *,
    osakedata_db_path: str,
    stock: Any,
    plan: StockUpdateTickerPlan,
    market: str,
    sync_splits: SplitSyncCallable,
    maybe_backfill_splits: SplitBackfillCallable,
    calculate_divergences: DivergenceUpdateCallable,
    run_candlestick_analysis: CandlestickUpdateCallable,
    maybe_update_quarter_state: Optional[QuarterStateUpdateCallable] = None,
) -> StockTickerUpdateFlowResult:
    if plan.needs_update is False:
        return StockTickerUpdateFlowResult(
            ticker=plan.candidate.ticker,
            skipped=True,
            skip_reason=plan.skip_reason,
            ohlcv_result=None,
            downstream_result=None,
        )

    ohlcv_result = execute_ticker_ohlcv_update_plan(
        osakedata_db_path=osakedata_db_path,
        stock=stock,
        plan=plan,
        market=market,
    )

    quarter_state_outcome: Optional[Dict[str, Any]] = None
    quarter_state_error = False
    if maybe_update_quarter_state is not None:
        try:
            quarter_state_outcome = maybe_update_quarter_state(
                plan.candidate.ticker,
                market,
                stock,
            )
        except Exception:
            quarter_state_error = True

    if ohlcv_result.ohlcv_rows_converted == 0:
        return StockTickerUpdateFlowResult(
            ticker=plan.candidate.ticker,
            skipped=True,
            skip_reason="no_history_data",
            ohlcv_result=ohlcv_result,
            downstream_result=None,
            quarter_state_outcome=quarter_state_outcome,
            quarter_state_error=quarter_state_error,
        )

    downstream_result = execute_ticker_downstream_updates(
        ticker=plan.candidate.ticker,
        stock=stock,
        ohlcv_rows_inserted=ohlcv_result.ohlcv_rows_inserted,
        date_ranges=plan.date_ranges,
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
    )
    return StockTickerUpdateFlowResult(
        ticker=plan.candidate.ticker,
        skipped=False,
        skip_reason=None,
        ohlcv_result=ohlcv_result,
        downstream_result=downstream_result,
        quarter_state_outcome=quarter_state_outcome,
        quarter_state_error=quarter_state_error,
    )


def execute_stock_update_batch(
    *,
    osakedata_db_path: str,
    market: str,
    plans: List[StockUpdateTickerPlan],
    stock_factory: StockFactory,
    sync_splits: SplitSyncCallable,
    maybe_backfill_splits: SplitBackfillCallable,
    calculate_divergences: DivergenceUpdateCallable,
    run_candlestick_analysis: CandlestickUpdateCallable,
    maybe_update_quarter_state: Optional[QuarterStateUpdateCallable] = None,
) -> StockUpdateBatchExecutionResult:
    result = StockUpdateBatchExecutionResult(market=market)

    for plan in plans:
        result.tickers_checked += 1
        ticker_terminal_rows_added: Optional[int] = None
        try:
            if plan.needs_update is False:
                stock = object()
            else:
                stock = stock_factory(plan.candidate.ticker)

            ticker_result = execute_ticker_update_flow(
                osakedata_db_path=osakedata_db_path,
                stock=stock,
                plan=plan,
                market=market,
                sync_splits=sync_splits,
                maybe_backfill_splits=maybe_backfill_splits,
                calculate_divergences=calculate_divergences,
                run_candlestick_analysis=run_candlestick_analysis,
                maybe_update_quarter_state=maybe_update_quarter_state,
            )
            result.ticker_results.append(ticker_result)

            if ticker_result.skipped:
                result.tickers_skipped += 1
            else:
                result.tickers_updated += 1
                if ticker_result.ohlcv_result is not None:
                    ticker_terminal_rows_added = (
                        ticker_result.ohlcv_result.ohlcv_rows_inserted
                    )

            if ticker_result.ohlcv_result is not None:
                result.ohlcv_rows_inserted += (
                    ticker_result.ohlcv_result.ohlcv_rows_inserted
                )
            if ticker_result.downstream_result is not None:
                result.warnings.extend(ticker_result.downstream_result.warnings)
            if ticker_result.quarter_state_error:
                result.quarter_state_errors += 1
            outcome = ticker_result.quarter_state_outcome or {}
            if outcome.get("checked"):
                result.quarter_state_checked += 1
            if outcome.get("new_detected"):
                result.quarter_state_new_detected += 1
            if outcome.get("detection_missing"):
                result.quarter_state_detection_missing += 1
            if outcome.get("row_updated"):
                result.quarter_state_rows_updated += 1
        except Exception as exc:
            result.tickers_failed += 1
            result.errors.append(
                f"Ticker update failed ({plan.candidate.ticker}): {exc}"
            )
        finally:
            _sleep_yahoo_after_ticker(ticker_terminal_rows_added)
            _sleep_yahoo_large_batch_if_needed(result.tickers_checked)

    return result


def execute_final_dow_update(
    *,
    calculate_dow_structures: DowUpdateCallable,
    analysis_db_path: str,
    osakedata_db_path: str,
    market: Optional[str],
    pivot_radius: Any,
    bounded_initial_from_date: Any,
    recalc_tail_trading_days: Any,
    dry_run: bool = False,
    run_id: Optional[str] = None,
    created_at_utc: Optional[str] = None,
) -> StockUpdateDowResult:
    kwargs: Dict[str, Any] = {
        "analysis_db_path": analysis_db_path,
        "osakedata_db_path": osakedata_db_path,
        "market": market,
        "pivot_radius": pivot_radius,
        "bounded_initial_from_date": bounded_initial_from_date,
        "recalc_tail_trading_days": recalc_tail_trading_days,
        "dry_run": dry_run,
    }
    if run_id is not None:
        kwargs["run_id"] = run_id
    if created_at_utc is not None:
        kwargs["created_at_utc"] = created_at_utc

    try:
        summary = calculate_dow_structures(**kwargs)
        return StockUpdateDowResult(
            attempted=True,
            success=True,
            dow_summary=summary,
            warning=None,
        )
    except Exception as exc:
        return StockUpdateDowResult(
            attempted=True,
            success=False,
            dow_summary=None,
            warning=f"Dow-rakenteiden paivitys epaonnistui: {exc}",
        )


def execute_stock_update_orchestration(
    *,
    osakedata_db_path: str,
    analysis_db_path: str,
    market: str,
    plans: List[StockUpdateTickerPlan],
    stock_factory: StockFactory,
    sync_splits: SplitSyncCallable,
    maybe_backfill_splits: SplitBackfillCallable,
    calculate_divergences: DivergenceUpdateCallable,
    run_candlestick_analysis: CandlestickUpdateCallable,
    maybe_update_quarter_state: Optional[QuarterStateUpdateCallable],
    calculate_dow_structures: DowUpdateCallable,
    pivot_radius: Any,
    bounded_initial_from_date: Any,
    recalc_tail_trading_days: Any,
    dow_dry_run: bool = False,
    dow_run_id: Optional[str] = None,
    dow_created_at_utc: Optional[str] = None,
) -> StockUpdateOrchestrationResult:
    batch_result = execute_stock_update_batch(
        osakedata_db_path=osakedata_db_path,
        market=market,
        plans=plans,
        stock_factory=stock_factory,
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
        maybe_update_quarter_state=maybe_update_quarter_state,
    )
    dow_result = execute_final_dow_update(
        calculate_dow_structures=calculate_dow_structures,
        analysis_db_path=analysis_db_path,
        osakedata_db_path=osakedata_db_path,
        market=market,
        pivot_radius=pivot_radius,
        bounded_initial_from_date=bounded_initial_from_date,
        recalc_tail_trading_days=recalc_tail_trading_days,
        dry_run=dow_dry_run,
        run_id=dow_run_id,
        created_at_utc=dow_created_at_utc,
    )

    warnings = list(batch_result.warnings)
    if dow_result.warning is not None:
        warnings.append(dow_result.warning)
    errors = list(batch_result.errors)

    return StockUpdateOrchestrationResult(
        batch_result=batch_result,
        dow_result=dow_result,
        warnings=warnings,
        errors=errors,
    )


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
        f"SUMMARY quarter_state_checked={result.quarter_state_checked}",
        f"SUMMARY quarter_state_new_detected={result.quarter_state_new_detected}",
        f"SUMMARY quarter_state_detection_missing={result.quarter_state_detection_missing}",
        f"SUMMARY quarter_state_rows_updated={result.quarter_state_rows_updated}",
        f"SUMMARY quarter_state_errors={result.quarter_state_errors}",
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
    today: str,
    fetch_until_exclusive: str,
    stock_factory: StockFactory,
    sync_splits: SplitSyncCallable,
    maybe_backfill_splits: SplitBackfillCallable,
    calculate_divergences: DivergenceUpdateCallable,
    run_candlestick_analysis: CandlestickUpdateCallable,
    maybe_update_quarter_state: Optional[QuarterStateUpdateCallable] = None,
    calculate_dow_structures: DowUpdateCallable,
    pivot_radius: Any,
    bounded_initial_from_date: Any,
    recalc_tail_trading_days: Any,
    dow_dry_run: bool = False,
    dow_run_id: Optional[str] = None,
    dow_created_at_utc: Optional[str] = None,
    progress_callback: ProgressCallback = None,
) -> StockUpdateResult:
    selected_market = resolve_stock_update_market(market)
    candidates = load_grouped_stock_update_candidates(osakedata_db_path)
    filtered_candidates = filter_stock_update_candidates_by_market(
        candidates,
        selected_market,
    )
    plans = plan_ticker_updates(
        candidates=filtered_candidates,
        today=today,
        fetch_until_exclusive=fetch_until_exclusive,
        start_override=start_override,
    )
    orchestration_result = execute_stock_update_orchestration(
        osakedata_db_path=osakedata_db_path,
        analysis_db_path=analysis_db_path,
        market=selected_market,
        plans=plans,
        stock_factory=stock_factory,
        sync_splits=sync_splits,
        maybe_backfill_splits=maybe_backfill_splits,
        calculate_divergences=calculate_divergences,
        run_candlestick_analysis=run_candlestick_analysis,
        maybe_update_quarter_state=maybe_update_quarter_state,
        calculate_dow_structures=calculate_dow_structures,
        pivot_radius=pivot_radius,
        bounded_initial_from_date=bounded_initial_from_date,
        recalc_tail_trading_days=recalc_tail_trading_days,
        dow_dry_run=dow_dry_run,
        dow_run_id=dow_run_id,
        dow_created_at_utc=dow_created_at_utc,
    )
    dow_summary = (
        orchestration_result.dow_result.dow_summary
        if orchestration_result.dow_result is not None
        else None
    )
    dow_structures_updated = None
    if isinstance(dow_summary, dict):
        if "updated" in dow_summary:
            dow_structures_updated = dow_summary["updated"]
        elif "inserted" in dow_summary:
            dow_structures_updated = dow_summary["inserted"]
        elif "rows_inserted" in dow_summary:
            dow_structures_updated = dow_summary["rows_inserted"]

    warnings = list(orchestration_result.warnings)
    errors = list(orchestration_result.errors)
    status = (
        STATUS_OK_WITH_WARNINGS
        if orchestration_result.batch_result.tickers_failed > 0 or warnings
        else STATUS_OK
    )
    return StockUpdateResult(
        market=selected_market,
        tickers_checked=orchestration_result.batch_result.tickers_checked,
        tickers_updated=orchestration_result.batch_result.tickers_updated,
        tickers_skipped=orchestration_result.batch_result.tickers_skipped,
        tickers_failed=orchestration_result.batch_result.tickers_failed,
        ohlcv_rows_inserted=orchestration_result.batch_result.ohlcv_rows_inserted,
        quarter_state_checked=orchestration_result.batch_result.quarter_state_checked,
        quarter_state_new_detected=orchestration_result.batch_result.quarter_state_new_detected,
        quarter_state_detection_missing=orchestration_result.batch_result.quarter_state_detection_missing,
        quarter_state_rows_updated=orchestration_result.batch_result.quarter_state_rows_updated,
        quarter_state_errors=orchestration_result.batch_result.quarter_state_errors,
        splits_synced=0,
        divergences_updated=0,
        candlesticks_updated=0,
        dow_structures_updated=dow_structures_updated,
        dow_summary=dow_summary,
        warnings=warnings,
        errors=errors,
        status=status,
    )
