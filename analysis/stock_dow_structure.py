from __future__ import annotations

import sqlite3
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

DEFAULT_ANALYSIS_DB_PATH = Path("data/analysis.db")
DEFAULT_OSAKEDATA_DB_PATH = Path("data/osakedata.db")
DEFAULT_PIVOT_RADIUS = 3
DEFAULT_RECALC_TAIL_TRADING_DAYS = 30
DEFAULT_BOUNDED_INITIAL_FROM_DATE = "2024-01-01"
PRICE_SOURCE_CLOSE = "close"
CALC_VERSION = "stock_dow_v1"

EVENT_TYPES = {
    "PIVOT_HIGH",
    "PIVOT_LOW",
    "BOS_UP",
    "BOS_DOWN",
    "RESET",
    "TREND_CHANGE",
}
TREND_STATES = {"UP", "DOWN", "NEUTRAL"}
HIGH_LABELS = {"H", "HH", "LH"}
LOW_LABELS = {"L", "HL", "LL"}
BREAK_SIGNALS = {"UP", "DOWN"}
RESET_REASONS = {"DOUBLE_BOS_UP", "DOUBLE_BOS_DOWN"}


@dataclass(frozen=True)
class PriceBar:
    ticker: str
    market: str | None
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: int | None


@dataclass(frozen=True)
class PivotCandidate:
    event_type: str
    event_index: int
    confirmed_index: int


@dataclass
class DowStructureState:
    trend_state: str = "NEUTRAL"
    active_bos_high_date: str | None = None
    active_bos_high_price: float | None = None
    active_bos_low_date: str | None = None
    active_bos_low_price: float | None = None
    last_high_label: str | None = None
    last_high_label_date: str | None = None
    last_high_label_price: float | None = None
    last_low_label: str | None = None
    last_low_label_date: str | None = None
    last_low_label_price: float | None = None
    bos_up_count: int = 0
    bos_down_count: int = 0
    structure_epoch_id: int = 1
    structure_epoch_start_date: str | None = None

    def clone(self) -> "DowStructureState":
        return DowStructureState(
            trend_state=self.trend_state,
            active_bos_high_date=self.active_bos_high_date,
            active_bos_high_price=self.active_bos_high_price,
            active_bos_low_date=self.active_bos_low_date,
            active_bos_low_price=self.active_bos_low_price,
            last_high_label=self.last_high_label,
            last_high_label_date=self.last_high_label_date,
            last_high_label_price=self.last_high_label_price,
            last_low_label=self.last_low_label,
            last_low_label_date=self.last_low_label_date,
            last_low_label_price=self.last_low_label_price,
            bos_up_count=self.bos_up_count,
            bos_down_count=self.bos_down_count,
            structure_epoch_id=self.structure_epoch_id,
            structure_epoch_start_date=self.structure_epoch_start_date,
        )


@dataclass
class TickerRunResult:
    ticker: str
    market: str | None
    recalculation_mode: str
    explicit_recalc_applied: bool
    rows_deleted: int
    event_rows: list[dict[str, Any]]
    calculated_from_date: str | None
    calculated_through_date: str | None
    latest_event_date: str | None
    latest_event_confirmed_as_of_date: str | None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def generate_run_id() -> str:
    return f"stock-dow-{uuid.uuid4().hex[:12]}"


def _connect_sqlite(db_path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    columns: set[str] = set()
    for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall():
        if isinstance(row, sqlite3.Row):
            columns.add(str(row["name"]))
        else:
            columns.add(str(row[1]))
    return columns


def _create_stock_dow_structure_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE stock_dow_structure_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            market TEXT NULL,
            event_date TEXT NOT NULL,
            confirmed_as_of_date TEXT NOT NULL,
            open REAL NULL,
            high REAL NULL,
            low REAL NULL,
            close REAL NOT NULL,
            volume INTEGER NULL,
            price_source TEXT NOT NULL DEFAULT 'close',
            structure_price REAL NOT NULL,
            pivot_radius INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            is_pivot_high INTEGER NOT NULL DEFAULT 0,
            is_pivot_low INTEGER NOT NULL DEFAULT 0,
            pivot_high_date TEXT NULL,
            pivot_high_price REAL NULL,
            pivot_low_date TEXT NULL,
            pivot_low_price REAL NULL,
            dow_label_high TEXT NULL,
            dow_label_low TEXT NULL,
            trend_state TEXT NOT NULL,
            active_bos_high_date TEXT NULL,
            active_bos_high_price REAL NULL,
            active_bos_low_date TEXT NULL,
            active_bos_low_price REAL NULL,
            last_high_label TEXT NULL,
            last_high_label_date TEXT NULL,
            last_high_label_price REAL NULL,
            last_low_label TEXT NULL,
            last_low_label_date TEXT NULL,
            last_low_label_price REAL NULL,
            bos_up_count INTEGER NOT NULL DEFAULT 0,
            bos_down_count INTEGER NOT NULL DEFAULT 0,
            break_signal TEXT NULL,
            break_level_date TEXT NULL,
            break_level_price REAL NULL,
            break_close_price REAL NULL,
            reset_marker TEXT NULL,
            reset_reason TEXT NULL,
            structure_epoch_id INTEGER NOT NULL DEFAULT 1,
            structure_epoch_start_date TEXT NULL,
            calc_version TEXT NOT NULL,
            run_id TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            UNIQUE(
                ticker,
                confirmed_as_of_date,
                event_type,
                event_date,
                pivot_radius,
                price_source
            )
        )
        """)


def _create_stock_dow_structure_status_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS stock_dow_structure_status (
            ticker TEXT NOT NULL,
            market TEXT NULL,
            price_source TEXT NOT NULL,
            pivot_radius INTEGER NOT NULL,
            calculated_from_date TEXT NULL,
            calculated_through_date TEXT NOT NULL,
            latest_ohlcv_date_at_run TEXT NOT NULL,
            latest_event_date TEXT NULL,
            latest_event_confirmed_as_of_date TEXT NULL,
            last_run_id TEXT NOT NULL,
            last_run_mode TEXT NOT NULL,
            last_rows_deleted INTEGER NOT NULL DEFAULT 0,
            last_rows_inserted INTEGER NOT NULL DEFAULT 0,
            last_status TEXT NOT NULL DEFAULT 'OK',
            last_error_message TEXT NULL,
            updated_at_utc TEXT NOT NULL,
            PRIMARY KEY (ticker, price_source, pivot_radius)
        )
        """)


def _migrate_stock_dow_structure_table_if_needed(conn: sqlite3.Connection) -> None:
    table_name = "stock_dow_structure_events"
    old_columns = {
        "structural_high_date",
        "structural_high_price",
        "structural_low_date",
        "structural_low_price",
    }
    new_columns = {
        "active_bos_high_date",
        "active_bos_high_price",
        "active_bos_low_date",
        "active_bos_low_price",
    }

    if not _table_exists(conn, table_name):
        _create_stock_dow_structure_table(conn)
        return

    columns = _table_columns(conn, table_name)
    has_old = bool(columns & old_columns)
    has_new = bool(columns & new_columns)

    if has_old and has_new:
        raise RuntimeError(
            "Ambiguous stock_dow_structure_events schema: both structural_* and "
            "active_bos_* columns exist"
        )

    if has_new:
        if not new_columns.issubset(columns):
            raise RuntimeError(
                "Incomplete stock_dow_structure_events schema: missing active_bos_* columns"
            )
        return

    if has_old:
        if not old_columns.issubset(columns):
            raise RuntimeError(
                "Incomplete stock_dow_structure_events schema: missing structural_* columns"
            )
        conn.execute("""
            ALTER TABLE stock_dow_structure_events
            RENAME COLUMN structural_high_date TO active_bos_high_date
            """)
        conn.execute("""
            ALTER TABLE stock_dow_structure_events
            RENAME COLUMN structural_high_price TO active_bos_high_price
            """)
        conn.execute("""
            ALTER TABLE stock_dow_structure_events
            RENAME COLUMN structural_low_date TO active_bos_low_date
            """)
        conn.execute("""
            ALTER TABLE stock_dow_structure_events
            RENAME COLUMN structural_low_price TO active_bos_low_price
            """)
        return

    raise RuntimeError(
        "Unsupported stock_dow_structure_events schema: missing both structural_* and "
        "active_bos_* columns"
    )


def ensure_stock_dow_structure_schema(conn: sqlite3.Connection) -> None:
    _migrate_stock_dow_structure_table_if_needed(conn)
    _create_stock_dow_structure_status_table(conn)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_dow_events_ticker_confirmed
        ON stock_dow_structure_events(ticker, confirmed_as_of_date)
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_dow_events_ticker_event
        ON stock_dow_structure_events(ticker, event_date)
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_dow_events_event_type
        ON stock_dow_structure_events(event_type)
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_dow_status_market
        ON stock_dow_structure_status(market)
        """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_stock_dow_status_calculated_through
        ON stock_dow_structure_status(calculated_through_date)
        """)
    conn.commit()


def _introspect_ohlcv_schema(conn: sqlite3.Connection) -> dict[str, str]:
    columns = {
        str(row["name"]).lower(): str(row["name"])
        for row in conn.execute("PRAGMA table_info(osakedata)").fetchall()
    }
    mapping: dict[str, str] = {}
    for key in ("osake", "ticker"):
        if key in columns:
            mapping["ticker"] = columns[key]
            break
    for key in ("pvm", "date"):
        if key in columns:
            mapping["date"] = columns[key]
            break
    for key in ("open",):
        if key in columns:
            mapping["open"] = columns[key]
            break
    for key in ("high",):
        if key in columns:
            mapping["high"] = columns[key]
            break
    for key in ("low",):
        if key in columns:
            mapping["low"] = columns[key]
            break
    for key in ("close",):
        if key in columns:
            mapping["close"] = columns[key]
            break
    for key in ("volume",):
        if key in columns:
            mapping["volume"] = columns[key]
            break
    for key in ("market",):
        if key in columns:
            mapping["market"] = columns[key]
            break
    required = {"ticker", "date", "close"}
    missing = required - set(mapping)
    if missing:
        raise RuntimeError(f"Missing OHLCV columns in osakedata: {sorted(missing)}")
    return mapping


def fetch_price_bars(
    conn: sqlite3.Connection,
    ticker: str,
) -> list[PriceBar]:
    schema = _introspect_ohlcv_schema(conn)
    open_expr = schema.get("open", "NULL")
    high_expr = schema.get("high", "NULL")
    low_expr = schema.get("low", "NULL")
    volume_expr = schema.get("volume", "NULL")
    market_expr = schema.get("market", "NULL")
    query = f"""
        SELECT
            {schema['ticker']} AS ticker,
            {market_expr} AS market,
            {schema['date']} AS event_date,
            {open_expr} AS open_value,
            {high_expr} AS high_value,
            {low_expr} AS low_value,
            {schema['close']} AS close_value,
            {volume_expr} AS volume_value
        FROM osakedata
        WHERE {schema['ticker']} = ?
        ORDER BY {schema['date']} ASC
    """
    rows = conn.execute(query, (ticker,)).fetchall()
    bars: list[PriceBar] = []
    for row in rows:
        if row["close_value"] is None or row["event_date"] is None:
            continue
        bars.append(
            PriceBar(
                ticker=str(row["ticker"]).strip().upper(),
                market=(
                    None
                    if row["market"] is None
                    else str(row["market"]).strip().lower()
                ),
                date=str(row["event_date"]),
                open=None if row["open_value"] is None else float(row["open_value"]),
                high=None if row["high_value"] is None else float(row["high_value"]),
                low=None if row["low_value"] is None else float(row["low_value"]),
                close=float(row["close_value"]),
                volume=(
                    None if row["volume_value"] is None else int(row["volume_value"])
                ),
            )
        )
    return bars


def fetch_tickers_for_market(
    conn: sqlite3.Connection,
    market: str,
) -> list[str]:
    schema = _introspect_ohlcv_schema(conn)
    market_col = schema.get("market")
    if not market_col:
        return []
    rows = conn.execute(
        f"""
        SELECT DISTINCT {schema['ticker']} AS ticker
        FROM osakedata
        WHERE LOWER({market_col}) = LOWER(?)
        ORDER BY {schema['ticker']} ASC
        """,
        (market,),
    ).fetchall()
    return [str(row["ticker"]).strip().upper() for row in rows if row["ticker"]]


def fetch_all_tickers(
    conn: sqlite3.Connection,
) -> list[str]:
    schema = _introspect_ohlcv_schema(conn)
    rows = conn.execute(f"""
        SELECT DISTINCT {schema['ticker']} AS ticker
        FROM osakedata
        ORDER BY {schema['ticker']} ASC
        """).fetchall()
    return [str(row["ticker"]).strip().upper() for row in rows if row["ticker"]]


def fetch_latest_ohlcv_dates(
    conn: sqlite3.Connection,
    market: str | None = None,
) -> dict[str, str]:
    schema = _introspect_ohlcv_schema(conn)
    params: list[str] = []
    where_conditions = [f"{schema['close']} IS NOT NULL"]
    market_col = schema.get("market")
    if market:
        if not market_col:
            return {}
        where_conditions.append(f"LOWER({market_col}) = LOWER(?)")
        params.append(market)
    where_clause = f"WHERE {' AND '.join(where_conditions)}"
    rows = conn.execute(
        f"""
        SELECT
            {schema['ticker']} AS ticker,
            MAX({schema['date']}) AS latest_date
        FROM osakedata
        {where_clause}
        GROUP BY {schema['ticker']}
        ORDER BY {schema['ticker']} ASC
        """,
        params,
    ).fetchall()
    latest_dates: dict[str, str] = {}
    for row in rows:
        ticker = row["ticker"]
        latest_date = row["latest_date"]
        if ticker and latest_date:
            latest_dates[str(ticker).strip().upper()] = str(latest_date)
    return latest_dates


def _fetch_all_tickers_in_scope(
    conn: sqlite3.Connection,
    market: str | None = None,
) -> set[str]:
    """Return all tickers present in osakedata for a given market scope, regardless of NULL close rows."""
    schema = _introspect_ohlcv_schema(conn)
    params: list[str] = []
    market_col = schema.get("market")
    where_clause = ""
    if market:
        if not market_col:
            return set()
        where_clause = f"WHERE LOWER({market_col}) = LOWER(?)"
        params.append(market)
    rows = conn.execute(
        f"""
        SELECT DISTINCT {schema['ticker']} AS ticker
        FROM osakedata
        {where_clause}
        """,
        params,
    ).fetchall()
    return {str(row["ticker"]).strip().upper() for row in rows if row["ticker"]}


def _build_pivot_candidates(
    bars: list[PriceBar],
    pivot_radius: int,
) -> dict[int, list[PivotCandidate]]:
    candidates: dict[int, list[PivotCandidate]] = defaultdict(list)
    closes = [bar.close for bar in bars]
    n_bars = len(closes)
    for idx in range(pivot_radius, n_bars - pivot_radius):
        window = closes[idx - pivot_radius : idx + pivot_radius + 1]
        center = closes[idx]
        max_value = max(window)
        min_value = min(window)
        if center == max_value and window.count(max_value) == 1:
            candidates[idx + pivot_radius].append(
                PivotCandidate(
                    event_type="PIVOT_HIGH",
                    event_index=idx,
                    confirmed_index=idx + pivot_radius,
                )
            )
        if center == min_value and window.count(min_value) == 1:
            candidates[idx + pivot_radius].append(
                PivotCandidate(
                    event_type="PIVOT_LOW",
                    event_index=idx,
                    confirmed_index=idx + pivot_radius,
                )
            )
    for confirmed_index in candidates:
        candidates[confirmed_index].sort(
            key=lambda item: (item.event_index, item.event_type)
        )
    return candidates


def _compute_recalc_start_date(
    bars: list[PriceBar],
    latest_confirmed_as_of_date: str,
    recalc_tail_trading_days: int,
) -> str:
    trading_dates = [bar.date for bar in bars]
    latest_idx = None
    for idx, date_value in enumerate(trading_dates):
        if date_value <= latest_confirmed_as_of_date:
            latest_idx = idx
        else:
            break
    if latest_idx is None:
        return trading_dates[0]
    start_idx = max(0, latest_idx - max(0, recalc_tail_trading_days))
    return trading_dates[start_idx]


def _find_first_trading_date_on_or_after(
    bars: list[PriceBar],
    boundary_date: str,
) -> str | None:
    for bar in bars:
        if bar.date >= boundary_date:
            return bar.date
    return None


def _fetch_latest_confirmed_as_of_date(
    conn: sqlite3.Connection,
    ticker: str,
    pivot_radius: int,
    price_source: str,
) -> str | None:
    row = conn.execute(
        """
        SELECT MAX(confirmed_as_of_date) AS confirmed_as_of_date
        FROM stock_dow_structure_events
        WHERE ticker = ?
          AND pivot_radius = ?
          AND price_source = ?
        """,
        (ticker, pivot_radius, price_source),
    ).fetchone()
    if not row:
        return None
    value = row["confirmed_as_of_date"]
    return None if value is None else str(value)


def _fetch_status_coverage_row(
    conn: sqlite3.Connection,
    ticker: str,
    pivot_radius: int,
    price_source: str,
) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT *
        FROM stock_dow_structure_status
        WHERE ticker = ?
          AND pivot_radius = ?
          AND price_source = ?
        """,
        (ticker, pivot_radius, price_source),
    ).fetchone()


def _has_event_rows(
    conn: sqlite3.Connection,
    ticker: str,
    pivot_radius: int,
    price_source: str,
) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM stock_dow_structure_events
        WHERE ticker = ?
          AND pivot_radius = ?
          AND price_source = ?
        LIMIT 1
        """,
        (ticker, pivot_radius, price_source),
    ).fetchone()
    return row is not None


def _initialize_selection_summary(
    *,
    pivot_radius: int,
    dry_run: bool,
    recalc_tail_trading_days: int,
    bounded_initial_from_date: str,
) -> dict[str, int | str]:
    return {
        "tickers_checked": 0,
        "tickers_missing": 0,
        "tickers_registered_without_status": 0,
        "tickers_outdated": 0,
        "tickers_up_to_date": 0,
        "tickers_no_valid_close_data": 0,
        "tickers_processed": 0,
        "tickers_bounded_initial_recalculated": 0,
        "tickers_incremental_recalculated": 0,
        "tickers_fallback_full_recalculated": 0,
        "rows_deleted": 0,
        "rows_inserted": 0,
        "pivot_high_events": 0,
        "pivot_low_events": 0,
        "bos_up_events": 0,
        "bos_down_events": 0,
        "reset_events": 0,
        "trend_change_events": 0,
        "pivot_radius": pivot_radius,
        "price_source": PRICE_SOURCE_CLOSE,
        "bounded_initial_from_date": bounded_initial_from_date,
        "recalc_tail_trading_days": recalc_tail_trading_days,
        "dry_run": 1 if dry_run else 0,
        "errors": 0,
        "error_tickers": "",
    }


def _upsert_status_row(
    conn: sqlite3.Connection,
    *,
    ticker: str,
    market: str | None,
    pivot_radius: int,
    calculated_from_date: str | None,
    calculated_through_date: str,
    latest_ohlcv_date_at_run: str,
    latest_event_date: str | None,
    latest_event_confirmed_as_of_date: str | None,
    last_run_id: str,
    last_run_mode: str,
    last_rows_deleted: int,
    last_rows_inserted: int,
    last_status: str,
    last_error_message: str | None,
    updated_at_utc: str,
) -> None:
    conn.execute(
        """
        INSERT INTO stock_dow_structure_status (
            ticker,
            market,
            price_source,
            pivot_radius,
            calculated_from_date,
            calculated_through_date,
            latest_ohlcv_date_at_run,
            latest_event_date,
            latest_event_confirmed_as_of_date,
            last_run_id,
            last_run_mode,
            last_rows_deleted,
            last_rows_inserted,
            last_status,
            last_error_message,
            updated_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, price_source, pivot_radius) DO UPDATE SET
            market = excluded.market,
            calculated_from_date = excluded.calculated_from_date,
            calculated_through_date = excluded.calculated_through_date,
            latest_ohlcv_date_at_run = excluded.latest_ohlcv_date_at_run,
            latest_event_date = excluded.latest_event_date,
            latest_event_confirmed_as_of_date = excluded.latest_event_confirmed_as_of_date,
            last_run_id = excluded.last_run_id,
            last_run_mode = excluded.last_run_mode,
            last_rows_deleted = excluded.last_rows_deleted,
            last_rows_inserted = excluded.last_rows_inserted,
            last_status = excluded.last_status,
            last_error_message = excluded.last_error_message,
            updated_at_utc = excluded.updated_at_utc
        """,
        (
            ticker,
            market,
            PRICE_SOURCE_CLOSE,
            pivot_radius,
            calculated_from_date,
            calculated_through_date,
            latest_ohlcv_date_at_run,
            latest_event_date,
            latest_event_confirmed_as_of_date,
            last_run_id,
            last_run_mode,
            last_rows_deleted,
            last_rows_inserted,
            last_status,
            last_error_message,
            updated_at_utc,
        ),
    )


def _run_bounded_initial_ticker_calculation(
    price_conn: sqlite3.Connection,
    *,
    ticker: str,
    pivot_radius: int,
    initial_from_date: str,
    run_id: str,
    created_at_utc: str,
) -> TickerRunResult:
    normalized_ticker = (ticker or "").strip().upper()
    bars = fetch_price_bars(price_conn, normalized_ticker)
    if not bars:
        return TickerRunResult(
            ticker=normalized_ticker,
            market=None,
            recalculation_mode="skipped",
            explicit_recalc_applied=False,
            rows_deleted=0,
            event_rows=[],
            calculated_from_date=None,
            calculated_through_date=None,
            latest_event_date=None,
            latest_event_confirmed_as_of_date=None,
        )

    bounded_bars = [bar for bar in bars if bar.date >= initial_from_date]
    if not bounded_bars:
        return TickerRunResult(
            ticker=normalized_ticker,
            market=bars[-1].market,
            recalculation_mode="bounded_initial",
            explicit_recalc_applied=False,
            rows_deleted=0,
            event_rows=[],
            calculated_from_date=None,
            calculated_through_date=bars[-1].date,
            latest_event_date=None,
            latest_event_confirmed_as_of_date=None,
        )

    event_rows = calculate_ticker_events(
        bounded_bars,
        pivot_radius=pivot_radius,
        start_confirmed_as_of_date=bounded_bars[0].date,
        initial_state=None,
        run_id=run_id,
        created_at_utc=created_at_utc,
    )
    return TickerRunResult(
        ticker=normalized_ticker,
        market=bounded_bars[-1].market,
        recalculation_mode="bounded_initial",
        explicit_recalc_applied=False,
        rows_deleted=0,
        event_rows=event_rows,
        calculated_from_date=bounded_bars[0].date,
        calculated_through_date=bars[-1].date,
        latest_event_date=None if not event_rows else str(event_rows[-1]["event_date"]),
        latest_event_confirmed_as_of_date=(
            None if not event_rows else str(event_rows[-1]["confirmed_as_of_date"])
        ),
    )


def _state_from_row(row: sqlite3.Row) -> DowStructureState:
    return DowStructureState(
        trend_state=str(row["trend_state"]),
        active_bos_high_date=(
            None
            if row["active_bos_high_date"] is None
            else str(row["active_bos_high_date"])
        ),
        active_bos_high_price=(
            None
            if row["active_bos_high_price"] is None
            else float(row["active_bos_high_price"])
        ),
        active_bos_low_date=(
            None
            if row["active_bos_low_date"] is None
            else str(row["active_bos_low_date"])
        ),
        active_bos_low_price=(
            None
            if row["active_bos_low_price"] is None
            else float(row["active_bos_low_price"])
        ),
        last_high_label=(
            None if row["last_high_label"] is None else str(row["last_high_label"])
        ),
        last_high_label_date=(
            None
            if row["last_high_label_date"] is None
            else str(row["last_high_label_date"])
        ),
        last_high_label_price=(
            None
            if row["last_high_label_price"] is None
            else float(row["last_high_label_price"])
        ),
        last_low_label=(
            None if row["last_low_label"] is None else str(row["last_low_label"])
        ),
        last_low_label_date=(
            None
            if row["last_low_label_date"] is None
            else str(row["last_low_label_date"])
        ),
        last_low_label_price=(
            None
            if row["last_low_label_price"] is None
            else float(row["last_low_label_price"])
        ),
        bos_up_count=int(row["bos_up_count"] or 0),
        bos_down_count=int(row["bos_down_count"] or 0),
        structure_epoch_id=int(row["structure_epoch_id"] or 1),
        structure_epoch_start_date=(
            None
            if row["structure_epoch_start_date"] is None
            else str(row["structure_epoch_start_date"])
        ),
    )


def _state_is_reconstructable(state: DowStructureState) -> bool:
    if state.trend_state not in TREND_STATES:
        return False
    if state.structure_epoch_id < 1:
        return False
    if state.trend_state == "UP":
        return (
            state.last_low_label == "HL"
            and state.active_bos_low_date is not None
            and state.active_bos_low_price is not None
        )
    if state.trend_state == "DOWN":
        return (
            state.last_high_label == "LH"
            and state.active_bos_high_date is not None
            and state.active_bos_high_price is not None
        )
    return True


def _load_latest_state_before(
    conn: sqlite3.Connection,
    ticker: str,
    recalc_start_date: str,
    pivot_radius: int,
    price_source: str,
) -> DowStructureState | None:
    row = conn.execute(
        """
        SELECT *
        FROM stock_dow_structure_events
        WHERE ticker = ?
          AND pivot_radius = ?
          AND price_source = ?
          AND confirmed_as_of_date < ?
        ORDER BY confirmed_as_of_date DESC, event_date DESC, id DESC
        LIMIT 1
        """,
        (ticker, pivot_radius, price_source, recalc_start_date),
    ).fetchone()
    if row is None:
        return None
    state = _state_from_row(row)
    if not _state_is_reconstructable(state):
        return None
    return state


def _delete_rows_from_date(
    conn: sqlite3.Connection,
    ticker: str,
    recalc_start_date: str,
    pivot_radius: int,
    price_source: str,
) -> int:
    cursor = conn.execute(
        """
        DELETE FROM stock_dow_structure_events
        WHERE ticker = ?
          AND pivot_radius = ?
          AND price_source = ?
          AND confirmed_as_of_date >= ?
        """,
        (ticker, pivot_radius, price_source, recalc_start_date),
    )
    return int(cursor.rowcount or 0)


def _delete_all_rows_for_ticker(
    conn: sqlite3.Connection,
    ticker: str,
    pivot_radius: int,
    price_source: str,
) -> int:
    cursor = conn.execute(
        """
        DELETE FROM stock_dow_structure_events
        WHERE ticker = ?
          AND pivot_radius = ?
          AND price_source = ?
        """,
        (ticker, pivot_radius, price_source),
    )
    return int(cursor.rowcount or 0)


def _determine_high_label(
    state: DowStructureState,
    pivot_price: float,
) -> str:
    if state.last_high_label_price is None:
        return "H"
    if pivot_price > state.last_high_label_price:
        return "HH"
    return "LH"


def _determine_low_label(
    state: DowStructureState,
    pivot_price: float,
) -> str:
    if state.last_low_label_price is None:
        return "L"
    if pivot_price > state.last_low_label_price:
        return "HL"
    return "LL"


def _compute_trend_state(state: DowStructureState) -> str:
    if state.last_high_label == "HH" and state.last_low_label == "HL":
        return "UP"
    if state.last_high_label == "LH" and state.last_low_label == "LL":
        return "DOWN"
    return "NEUTRAL"


def _sync_active_bos_levels(state: DowStructureState) -> None:
    if state.trend_state == "UP" and state.last_low_label == "HL":
        state.active_bos_low_date = state.last_low_label_date
        state.active_bos_low_price = state.last_low_label_price
        state.active_bos_high_date = None
        state.active_bos_high_price = None
    elif state.trend_state == "DOWN" and state.last_high_label == "LH":
        state.active_bos_high_date = state.last_high_label_date
        state.active_bos_high_price = state.last_high_label_price
        state.active_bos_low_date = None
        state.active_bos_low_price = None
    else:
        state.active_bos_high_date = None
        state.active_bos_high_price = None
        state.active_bos_low_date = None
        state.active_bos_low_price = None


def _build_event_row(
    *,
    state: DowStructureState,
    bar: PriceBar,
    confirmed_as_of_date: str,
    event_type: str,
    pivot_radius: int,
    run_id: str,
    created_at_utc: str,
    pivot_high_date: str | None = None,
    pivot_high_price: float | None = None,
    pivot_low_date: str | None = None,
    pivot_low_price: float | None = None,
    dow_label_high: str | None = None,
    dow_label_low: str | None = None,
    break_signal: str | None = None,
    break_level_date: str | None = None,
    break_level_price: float | None = None,
    break_close_price: float | None = None,
    reset_marker: str | None = None,
    reset_reason: str | None = None,
) -> dict[str, Any]:
    if event_type not in EVENT_TYPES:
        raise ValueError(f"Unsupported event_type: {event_type}")
    return {
        "ticker": bar.ticker,
        "market": bar.market,
        "event_date": bar.date,
        "confirmed_as_of_date": confirmed_as_of_date,
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
        "price_source": PRICE_SOURCE_CLOSE,
        "structure_price": bar.close,
        "pivot_radius": pivot_radius,
        "event_type": event_type,
        "is_pivot_high": 1 if event_type == "PIVOT_HIGH" else 0,
        "is_pivot_low": 1 if event_type == "PIVOT_LOW" else 0,
        "pivot_high_date": pivot_high_date,
        "pivot_high_price": pivot_high_price,
        "pivot_low_date": pivot_low_date,
        "pivot_low_price": pivot_low_price,
        "dow_label_high": dow_label_high,
        "dow_label_low": dow_label_low,
        "trend_state": state.trend_state,
        "active_bos_high_date": state.active_bos_high_date,
        "active_bos_high_price": state.active_bos_high_price,
        "active_bos_low_date": state.active_bos_low_date,
        "active_bos_low_price": state.active_bos_low_price,
        "last_high_label": state.last_high_label,
        "last_high_label_date": state.last_high_label_date,
        "last_high_label_price": state.last_high_label_price,
        "last_low_label": state.last_low_label,
        "last_low_label_date": state.last_low_label_date,
        "last_low_label_price": state.last_low_label_price,
        "bos_up_count": state.bos_up_count,
        "bos_down_count": state.bos_down_count,
        "break_signal": break_signal,
        "break_level_date": break_level_date,
        "break_level_price": break_level_price,
        "break_close_price": break_close_price,
        "reset_marker": reset_marker,
        "reset_reason": reset_reason,
        "structure_epoch_id": state.structure_epoch_id,
        "structure_epoch_start_date": state.structure_epoch_start_date,
        "calc_version": CALC_VERSION,
        "run_id": run_id,
        "created_at_utc": created_at_utc,
    }


def _make_initial_state(bars: list[PriceBar]) -> DowStructureState:
    epoch_start_date = bars[0].date if bars else None
    return DowStructureState(
        structure_epoch_id=1, structure_epoch_start_date=epoch_start_date
    )


def _reset_state(
    state: DowStructureState,
    reset_event_date: str,
) -> DowStructureState:
    return DowStructureState(
        trend_state="NEUTRAL",
        active_bos_high_date=None,
        active_bos_high_price=None,
        active_bos_low_date=None,
        active_bos_low_price=None,
        last_high_label=None,
        last_high_label_date=None,
        last_high_label_price=None,
        last_low_label=None,
        last_low_label_date=None,
        last_low_label_price=None,
        bos_up_count=0,
        bos_down_count=0,
        structure_epoch_id=state.structure_epoch_id + 1,
        structure_epoch_start_date=reset_event_date,
    )


def _append_trend_change_event(
    event_rows: list[dict[str, Any]],
    *,
    state: DowStructureState,
    bar: PriceBar,
    confirmed_as_of_date: str,
    pivot_radius: int,
    run_id: str,
    created_at_utc: str,
) -> None:
    event_rows.append(
        _build_event_row(
            state=state,
            bar=bar,
            confirmed_as_of_date=confirmed_as_of_date,
            event_type="TREND_CHANGE",
            pivot_radius=pivot_radius,
            run_id=run_id,
            created_at_utc=created_at_utc,
        )
    )


def calculate_ticker_events(
    bars: list[PriceBar],
    *,
    pivot_radius: int,
    start_confirmed_as_of_date: str,
    initial_state: DowStructureState | None,
    run_id: str,
    created_at_utc: str,
) -> list[dict[str, Any]]:
    if not bars:
        return []

    event_rows: list[dict[str, Any]] = []
    candidates_by_confirm_index = _build_pivot_candidates(bars, pivot_radius)
    date_to_index = {bar.date: idx for idx, bar in enumerate(bars)}
    start_idx = date_to_index[start_confirmed_as_of_date]
    state = (
        initial_state.clone()
        if initial_state is not None
        else _make_initial_state(bars)
    )

    if state.structure_epoch_start_date is None:
        state.structure_epoch_start_date = bars[0].date

    for confirmed_idx in range(start_idx, len(bars)):
        confirmed_bar = bars[confirmed_idx]
        confirmed_date = confirmed_bar.date

        for candidate in candidates_by_confirm_index.get(confirmed_idx, []):
            pivot_bar = bars[candidate.event_index]
            previous_trend = state.trend_state
            if candidate.event_type == "PIVOT_HIGH":
                high_label = _determine_high_label(state, pivot_bar.close)
                state.last_high_label = high_label
                state.last_high_label_date = pivot_bar.date
                state.last_high_label_price = pivot_bar.close
                state.trend_state = _compute_trend_state(state)
                _sync_active_bos_levels(state)
                event_rows.append(
                    _build_event_row(
                        state=state,
                        bar=pivot_bar,
                        confirmed_as_of_date=confirmed_date,
                        event_type="PIVOT_HIGH",
                        pivot_radius=pivot_radius,
                        run_id=run_id,
                        created_at_utc=created_at_utc,
                        pivot_high_date=pivot_bar.date,
                        pivot_high_price=pivot_bar.close,
                        dow_label_high=high_label,
                    )
                )
            else:
                low_label = _determine_low_label(state, pivot_bar.close)
                state.last_low_label = low_label
                state.last_low_label_date = pivot_bar.date
                state.last_low_label_price = pivot_bar.close
                state.trend_state = _compute_trend_state(state)
                _sync_active_bos_levels(state)
                event_rows.append(
                    _build_event_row(
                        state=state,
                        bar=pivot_bar,
                        confirmed_as_of_date=confirmed_date,
                        event_type="PIVOT_LOW",
                        pivot_radius=pivot_radius,
                        run_id=run_id,
                        created_at_utc=created_at_utc,
                        pivot_low_date=pivot_bar.date,
                        pivot_low_price=pivot_bar.close,
                        dow_label_low=low_label,
                    )
                )
            if state.trend_state != previous_trend:
                _append_trend_change_event(
                    event_rows,
                    state=state,
                    bar=pivot_bar,
                    confirmed_as_of_date=confirmed_date,
                    pivot_radius=pivot_radius,
                    run_id=run_id,
                    created_at_utc=created_at_utc,
                )

        if state.trend_state == "UP":
            state.bos_up_count = 0
            if (
                state.active_bos_low_price is not None
                and confirmed_bar.close < state.active_bos_low_price
            ):
                if state.bos_down_count == 0:
                    state.bos_down_count = 1
                    event_rows.append(
                        _build_event_row(
                            state=state,
                            bar=confirmed_bar,
                            confirmed_as_of_date=confirmed_date,
                            event_type="BOS_DOWN",
                            pivot_radius=pivot_radius,
                            run_id=run_id,
                            created_at_utc=created_at_utc,
                            break_signal="DOWN",
                            break_level_date=state.active_bos_low_date,
                            break_level_price=state.active_bos_low_price,
                            break_close_price=confirmed_bar.close,
                        )
                    )
                else:
                    break_level_date = state.active_bos_low_date
                    break_level_price = state.active_bos_low_price
                    previous_trend = state.trend_state
                    state = _reset_state(state, confirmed_date)
                    event_rows.append(
                        _build_event_row(
                            state=state,
                            bar=confirmed_bar,
                            confirmed_as_of_date=confirmed_date,
                            event_type="RESET",
                            pivot_radius=pivot_radius,
                            run_id=run_id,
                            created_at_utc=created_at_utc,
                            break_signal="DOWN",
                            break_level_date=break_level_date,
                            break_level_price=break_level_price,
                            break_close_price=confirmed_bar.close,
                            reset_marker="R",
                            reset_reason="DOUBLE_BOS_DOWN",
                        )
                    )
                    if state.trend_state != previous_trend:
                        _append_trend_change_event(
                            event_rows,
                            state=state,
                            bar=confirmed_bar,
                            confirmed_as_of_date=confirmed_date,
                            pivot_radius=pivot_radius,
                            run_id=run_id,
                            created_at_utc=created_at_utc,
                        )
            else:
                state.bos_down_count = 0
        elif state.trend_state == "DOWN":
            state.bos_down_count = 0
            if (
                state.active_bos_high_price is not None
                and confirmed_bar.close > state.active_bos_high_price
            ):
                if state.bos_up_count == 0:
                    state.bos_up_count = 1
                    event_rows.append(
                        _build_event_row(
                            state=state,
                            bar=confirmed_bar,
                            confirmed_as_of_date=confirmed_date,
                            event_type="BOS_UP",
                            pivot_radius=pivot_radius,
                            run_id=run_id,
                            created_at_utc=created_at_utc,
                            break_signal="UP",
                            break_level_date=state.active_bos_high_date,
                            break_level_price=state.active_bos_high_price,
                            break_close_price=confirmed_bar.close,
                        )
                    )
                else:
                    break_level_date = state.active_bos_high_date
                    break_level_price = state.active_bos_high_price
                    previous_trend = state.trend_state
                    state = _reset_state(state, confirmed_date)
                    event_rows.append(
                        _build_event_row(
                            state=state,
                            bar=confirmed_bar,
                            confirmed_as_of_date=confirmed_date,
                            event_type="RESET",
                            pivot_radius=pivot_radius,
                            run_id=run_id,
                            created_at_utc=created_at_utc,
                            break_signal="UP",
                            break_level_date=break_level_date,
                            break_level_price=break_level_price,
                            break_close_price=confirmed_bar.close,
                            reset_marker="R",
                            reset_reason="DOUBLE_BOS_UP",
                        )
                    )
                    if state.trend_state != previous_trend:
                        _append_trend_change_event(
                            event_rows,
                            state=state,
                            bar=confirmed_bar,
                            confirmed_as_of_date=confirmed_date,
                            pivot_radius=pivot_radius,
                            run_id=run_id,
                            created_at_utc=created_at_utc,
                        )
            else:
                state.bos_up_count = 0
        else:
            state.bos_up_count = 0
            state.bos_down_count = 0

    return event_rows


def _event_insert_columns() -> list[str]:
    return [
        "ticker",
        "market",
        "event_date",
        "confirmed_as_of_date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "price_source",
        "structure_price",
        "pivot_radius",
        "event_type",
        "is_pivot_high",
        "is_pivot_low",
        "pivot_high_date",
        "pivot_high_price",
        "pivot_low_date",
        "pivot_low_price",
        "dow_label_high",
        "dow_label_low",
        "trend_state",
        "active_bos_high_date",
        "active_bos_high_price",
        "active_bos_low_date",
        "active_bos_low_price",
        "last_high_label",
        "last_high_label_date",
        "last_high_label_price",
        "last_low_label",
        "last_low_label_date",
        "last_low_label_price",
        "bos_up_count",
        "bos_down_count",
        "break_signal",
        "break_level_date",
        "break_level_price",
        "break_close_price",
        "reset_marker",
        "reset_reason",
        "structure_epoch_id",
        "structure_epoch_start_date",
        "calc_version",
        "run_id",
        "created_at_utc",
    ]


def insert_event_rows(
    conn: sqlite3.Connection,
    event_rows: Iterable[dict[str, Any]],
) -> int:
    rows = list(event_rows)
    if not rows:
        return 0
    columns = _event_insert_columns()
    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f"""
        INSERT OR REPLACE INTO stock_dow_structure_events
        ({", ".join(columns)})
        VALUES ({placeholders})
        """,
        [tuple(row.get(column) for column in columns) for row in rows],
    )
    return len(rows)


def _initialize_summary(
    *,
    pivot_radius: int,
    dry_run: bool,
    recalc_from_date: str | None,
) -> dict[str, int | str]:
    return {
        "tickers_requested": 0,
        "tickers_processed": 0,
        "tickers_full_recalculated": 0,
        "tickers_incremental_recalculated": 0,
        "tickers_fallback_full_recalculated": 0,
        "recalc_from_date": recalc_from_date or "none",
        "explicit_recalc_requested": 1 if recalc_from_date else 0,
        "tickers_explicit_recalculated": 0,
        "rows_deleted": 0,
        "rows_inserted": 0,
        "pivot_high_events": 0,
        "pivot_low_events": 0,
        "bos_up_events": 0,
        "bos_down_events": 0,
        "reset_events": 0,
        "trend_change_events": 0,
        "pivot_radius": pivot_radius,
        "price_source": PRICE_SOURCE_CLOSE,
        "dry_run": 1 if dry_run else 0,
        "errors": 0,
    }


def _accumulate_event_counts(
    summary: dict[str, int | str],
    event_rows: Iterable[dict[str, Any]],
) -> None:
    for row in event_rows:
        event_type = row["event_type"]
        if event_type == "PIVOT_HIGH":
            summary["pivot_high_events"] = int(summary["pivot_high_events"]) + 1
        elif event_type == "PIVOT_LOW":
            summary["pivot_low_events"] = int(summary["pivot_low_events"]) + 1
        elif event_type == "BOS_UP":
            summary["bos_up_events"] = int(summary["bos_up_events"]) + 1
        elif event_type == "BOS_DOWN":
            summary["bos_down_events"] = int(summary["bos_down_events"]) + 1
        elif event_type == "RESET":
            summary["reset_events"] = int(summary["reset_events"]) + 1
        elif event_type == "TREND_CHANGE":
            summary["trend_change_events"] = int(summary["trend_change_events"]) + 1


def run_ticker_calculation(
    analysis_conn: sqlite3.Connection,
    price_conn: sqlite3.Connection,
    *,
    ticker: str,
    pivot_radius: int,
    recalc_tail_trading_days: int,
    recalc_from_date: str | None,
    force_full: bool,
    run_id: str,
    created_at_utc: str,
) -> TickerRunResult:
    normalized_ticker = (ticker or "").strip().upper()
    bars = fetch_price_bars(price_conn, normalized_ticker)
    if not bars:
        return TickerRunResult(
            ticker=normalized_ticker,
            market=None,
            recalculation_mode="skipped",
            explicit_recalc_applied=False,
            rows_deleted=0,
            event_rows=[],
            calculated_from_date=None,
            calculated_through_date=None,
            latest_event_date=None,
            latest_event_confirmed_as_of_date=None,
        )

    if force_full:
        rows_deleted = _delete_all_rows_for_ticker(
            analysis_conn,
            normalized_ticker,
            pivot_radius,
            PRICE_SOURCE_CLOSE,
        )
        event_rows = calculate_ticker_events(
            bars,
            pivot_radius=pivot_radius,
            start_confirmed_as_of_date=bars[0].date,
            initial_state=None,
            run_id=run_id,
            created_at_utc=created_at_utc,
        )
        return TickerRunResult(
            ticker=normalized_ticker,
            market=bars[-1].market,
            recalculation_mode="full",
            explicit_recalc_applied=False,
            rows_deleted=rows_deleted,
            event_rows=event_rows,
            calculated_from_date=bars[0].date,
            calculated_through_date=bars[-1].date,
            latest_event_date=(
                None if not event_rows else str(event_rows[-1]["event_date"])
            ),
            latest_event_confirmed_as_of_date=(
                None if not event_rows else str(event_rows[-1]["confirmed_as_of_date"])
            ),
        )

    if recalc_from_date is not None:
        first_bar_date = bars[0].date
        latest_bar_date = bars[-1].date

        if recalc_from_date > latest_bar_date:
            return TickerRunResult(
                ticker=normalized_ticker,
                market=bars[-1].market,
                recalculation_mode="explicit_noop",
                explicit_recalc_applied=True,
                rows_deleted=0,
                event_rows=[],
                calculated_from_date=recalc_from_date,
                calculated_through_date=latest_bar_date,
                latest_event_date=None,
                latest_event_confirmed_as_of_date=None,
            )

        if recalc_from_date < first_bar_date:
            rows_deleted = _delete_all_rows_for_ticker(
                analysis_conn,
                normalized_ticker,
                pivot_radius,
                PRICE_SOURCE_CLOSE,
            )
            event_rows = calculate_ticker_events(
                bars,
                pivot_radius=pivot_radius,
                start_confirmed_as_of_date=bars[0].date,
                initial_state=None,
                run_id=run_id,
                created_at_utc=created_at_utc,
            )
            return TickerRunResult(
                ticker=normalized_ticker,
                market=bars[-1].market,
                recalculation_mode="full",
                explicit_recalc_applied=False,
                rows_deleted=rows_deleted,
                event_rows=event_rows,
                calculated_from_date=bars[0].date,
                calculated_through_date=bars[-1].date,
                latest_event_date=(
                    None if not event_rows else str(event_rows[-1]["event_date"])
                ),
                latest_event_confirmed_as_of_date=(
                    None
                    if not event_rows
                    else str(event_rows[-1]["confirmed_as_of_date"])
                ),
            )

        start_confirmed_as_of_date = _find_first_trading_date_on_or_after(
            bars,
            recalc_from_date,
        )
        if start_confirmed_as_of_date is None:
            return TickerRunResult(
                ticker=normalized_ticker,
                market=bars[-1].market,
                recalculation_mode="explicit_noop",
                explicit_recalc_applied=True,
                rows_deleted=0,
                event_rows=[],
                calculated_from_date=start_confirmed_as_of_date,
                calculated_through_date=latest_bar_date,
                latest_event_date=None,
                latest_event_confirmed_as_of_date=None,
            )

        state = _load_latest_state_before(
            analysis_conn,
            normalized_ticker,
            recalc_from_date,
            pivot_radius,
            PRICE_SOURCE_CLOSE,
        )
        if state is None:
            rows_deleted = _delete_all_rows_for_ticker(
                analysis_conn,
                normalized_ticker,
                pivot_radius,
                PRICE_SOURCE_CLOSE,
            )
            event_rows = calculate_ticker_events(
                bars,
                pivot_radius=pivot_radius,
                start_confirmed_as_of_date=bars[0].date,
                initial_state=None,
                run_id=run_id,
                created_at_utc=created_at_utc,
            )
            return TickerRunResult(
                ticker=normalized_ticker,
                market=bars[-1].market,
                recalculation_mode="fallback_full",
                explicit_recalc_applied=False,
                rows_deleted=rows_deleted,
                event_rows=event_rows,
                calculated_from_date=bars[0].date,
                calculated_through_date=bars[-1].date,
                latest_event_date=(
                    None if not event_rows else str(event_rows[-1]["event_date"])
                ),
                latest_event_confirmed_as_of_date=(
                    None
                    if not event_rows
                    else str(event_rows[-1]["confirmed_as_of_date"])
                ),
            )

        rows_deleted = _delete_rows_from_date(
            analysis_conn,
            normalized_ticker,
            recalc_from_date,
            pivot_radius,
            PRICE_SOURCE_CLOSE,
        )
        event_rows = calculate_ticker_events(
            bars,
            pivot_radius=pivot_radius,
            start_confirmed_as_of_date=start_confirmed_as_of_date,
            initial_state=state,
            run_id=run_id,
            created_at_utc=created_at_utc,
        )
        return TickerRunResult(
            ticker=normalized_ticker,
            market=bars[-1].market,
            recalculation_mode="explicit",
            explicit_recalc_applied=True,
            rows_deleted=rows_deleted,
            event_rows=event_rows,
            calculated_from_date=start_confirmed_as_of_date,
            calculated_through_date=latest_bar_date,
            latest_event_date=(
                None if not event_rows else str(event_rows[-1]["event_date"])
            ),
            latest_event_confirmed_as_of_date=(
                None if not event_rows else str(event_rows[-1]["confirmed_as_of_date"])
            ),
        )

    latest_confirmed_as_of_date = _fetch_latest_confirmed_as_of_date(
        analysis_conn,
        normalized_ticker,
        pivot_radius,
        PRICE_SOURCE_CLOSE,
    )
    if latest_confirmed_as_of_date is None:
        event_rows = calculate_ticker_events(
            bars,
            pivot_radius=pivot_radius,
            start_confirmed_as_of_date=bars[0].date,
            initial_state=None,
            run_id=run_id,
            created_at_utc=created_at_utc,
        )
        return TickerRunResult(
            ticker=normalized_ticker,
            market=bars[-1].market,
            recalculation_mode="full",
            explicit_recalc_applied=False,
            rows_deleted=0,
            event_rows=event_rows,
            calculated_from_date=bars[0].date,
            calculated_through_date=bars[-1].date,
            latest_event_date=(
                None if not event_rows else str(event_rows[-1]["event_date"])
            ),
            latest_event_confirmed_as_of_date=(
                None if not event_rows else str(event_rows[-1]["confirmed_as_of_date"])
            ),
        )

    recalc_start_date = _compute_recalc_start_date(
        bars,
        latest_confirmed_as_of_date,
        recalc_tail_trading_days,
    )
    state = _load_latest_state_before(
        analysis_conn,
        normalized_ticker,
        recalc_start_date,
        pivot_radius,
        PRICE_SOURCE_CLOSE,
    )
    if state is None and recalc_start_date != bars[0].date:
        rows_deleted = _delete_all_rows_for_ticker(
            analysis_conn,
            normalized_ticker,
            pivot_radius,
            PRICE_SOURCE_CLOSE,
        )
        event_rows = calculate_ticker_events(
            bars,
            pivot_radius=pivot_radius,
            start_confirmed_as_of_date=bars[0].date,
            initial_state=None,
            run_id=run_id,
            created_at_utc=created_at_utc,
        )
        return TickerRunResult(
            ticker=normalized_ticker,
            market=bars[-1].market,
            recalculation_mode="fallback_full",
            explicit_recalc_applied=False,
            rows_deleted=rows_deleted,
            event_rows=event_rows,
            calculated_from_date=bars[0].date,
            calculated_through_date=bars[-1].date,
            latest_event_date=(
                None if not event_rows else str(event_rows[-1]["event_date"])
            ),
            latest_event_confirmed_as_of_date=(
                None if not event_rows else str(event_rows[-1]["confirmed_as_of_date"])
            ),
        )

    rows_deleted = _delete_rows_from_date(
        analysis_conn,
        normalized_ticker,
        recalc_start_date,
        pivot_radius,
        PRICE_SOURCE_CLOSE,
    )
    event_rows = calculate_ticker_events(
        bars,
        pivot_radius=pivot_radius,
        start_confirmed_as_of_date=recalc_start_date,
        initial_state=state,
        run_id=run_id,
        created_at_utc=created_at_utc,
    )
    return TickerRunResult(
        ticker=normalized_ticker,
        market=bars[-1].market,
        recalculation_mode="incremental",
        explicit_recalc_applied=False,
        rows_deleted=rows_deleted,
        event_rows=event_rows,
        calculated_from_date=recalc_start_date,
        calculated_through_date=bars[-1].date,
        latest_event_date=None if not event_rows else str(event_rows[-1]["event_date"]),
        latest_event_confirmed_as_of_date=(
            None if not event_rows else str(event_rows[-1]["confirmed_as_of_date"])
        ),
    )


def run_stock_dow_structure(
    *,
    analysis_db_path: Path | str = DEFAULT_ANALYSIS_DB_PATH,
    osakedata_db_path: Path | str = DEFAULT_OSAKEDATA_DB_PATH,
    ticker: str | None = None,
    market: str | None = None,
    pivot_radius: int = DEFAULT_PIVOT_RADIUS,
    recalc_tail_trading_days: int = DEFAULT_RECALC_TAIL_TRADING_DAYS,
    recalc_from_date: str | None = None,
    mode: str = "upsert",
    force_full: bool = False,
    dry_run: bool = False,
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> dict[str, int | str]:
    if mode != "upsert":
        raise ValueError(f"Unsupported mode: {mode}")
    if ticker and market:
        raise ValueError("Use either ticker or market, not both")
    if not ticker and not market:
        raise ValueError("Either ticker or market is required")
    if pivot_radius <= 0:
        raise ValueError("pivot_radius must be positive")
    if recalc_tail_trading_days < 0:
        raise ValueError("recalc_tail_trading_days must be non-negative")

    summary = _initialize_summary(
        pivot_radius=pivot_radius,
        dry_run=dry_run,
        recalc_from_date=recalc_from_date,
    )
    run_id = run_id or generate_run_id()
    created_at_utc = created_at_utc or utc_now_iso()

    with _connect_sqlite(analysis_db_path) as analysis_conn, _connect_sqlite(
        osakedata_db_path
    ) as price_conn:
        ensure_stock_dow_structure_schema(analysis_conn)

        if ticker:
            tickers = [(ticker or "").strip().upper()]
        else:
            tickers = fetch_tickers_for_market(
                price_conn, (market or "").strip().lower()
            )

        summary["tickers_requested"] = len(tickers)

        for normalized_ticker in tickers:
            try:
                result = run_ticker_calculation(
                    analysis_conn,
                    price_conn,
                    ticker=normalized_ticker,
                    pivot_radius=pivot_radius,
                    recalc_tail_trading_days=recalc_tail_trading_days,
                    recalc_from_date=recalc_from_date,
                    force_full=force_full,
                    run_id=run_id,
                    created_at_utc=created_at_utc,
                )
                if result.recalculation_mode == "skipped":
                    continue

                summary["tickers_processed"] = int(summary["tickers_processed"]) + 1
                if result.recalculation_mode == "full":
                    summary["tickers_full_recalculated"] = (
                        int(summary["tickers_full_recalculated"]) + 1
                    )
                elif result.recalculation_mode == "incremental":
                    summary["tickers_incremental_recalculated"] = (
                        int(summary["tickers_incremental_recalculated"]) + 1
                    )
                elif result.recalculation_mode == "fallback_full":
                    summary["tickers_fallback_full_recalculated"] = (
                        int(summary["tickers_fallback_full_recalculated"]) + 1
                    )
                if result.explicit_recalc_applied:
                    summary["tickers_explicit_recalculated"] = (
                        int(summary["tickers_explicit_recalculated"]) + 1
                    )

                summary["rows_deleted"] = (
                    int(summary["rows_deleted"]) + result.rows_deleted
                )
                _accumulate_event_counts(summary, result.event_rows)

                if dry_run:
                    inserted = len(result.event_rows)
                    summary["rows_inserted"] = int(summary["rows_inserted"]) + inserted
                else:
                    inserted = insert_event_rows(analysis_conn, result.event_rows)
                    summary["rows_inserted"] = int(summary["rows_inserted"]) + inserted
                    if result.calculated_through_date is not None:
                        _upsert_status_row(
                            analysis_conn,
                            ticker=result.ticker,
                            market=result.market,
                            pivot_radius=pivot_radius,
                            calculated_from_date=result.calculated_from_date,
                            calculated_through_date=result.calculated_through_date,
                            latest_ohlcv_date_at_run=result.calculated_through_date,
                            latest_event_date=result.latest_event_date,
                            latest_event_confirmed_as_of_date=result.latest_event_confirmed_as_of_date,
                            last_run_id=run_id,
                            last_run_mode=result.recalculation_mode,
                            last_rows_deleted=result.rows_deleted,
                            last_rows_inserted=inserted,
                            last_status="OK",
                            last_error_message=None,
                            updated_at_utc=created_at_utc,
                        )
            except Exception:
                summary["errors"] = int(summary["errors"]) + 1
                raise

        if dry_run:
            analysis_conn.rollback()
        else:
            analysis_conn.commit()

    return summary


def format_summary_lines(summary: dict[str, int | str]) -> list[str]:
    ordered_keys = [
        "tickers_requested",
        "tickers_processed",
        "tickers_full_recalculated",
        "tickers_incremental_recalculated",
        "tickers_fallback_full_recalculated",
        "recalc_from_date",
        "explicit_recalc_requested",
        "tickers_explicit_recalculated",
        "rows_deleted",
        "rows_inserted",
        "pivot_high_events",
        "pivot_low_events",
        "bos_up_events",
        "bos_down_events",
        "reset_events",
        "trend_change_events",
        "pivot_radius",
        "price_source",
        "dry_run",
        "errors",
    ]
    return [f"SUMMARY {key}={summary[key]}" for key in ordered_keys]


def calculate_missing_or_outdated_stock_dow_structures(
    *,
    analysis_db_path: Path | str = DEFAULT_ANALYSIS_DB_PATH,
    osakedata_db_path: Path | str = DEFAULT_OSAKEDATA_DB_PATH,
    market: str | None = None,
    pivot_radius: int = DEFAULT_PIVOT_RADIUS,
    bounded_initial_from_date: str = DEFAULT_BOUNDED_INITIAL_FROM_DATE,
    recalc_tail_trading_days: int = DEFAULT_RECALC_TAIL_TRADING_DAYS,
    dry_run: bool = False,
    run_id: str | None = None,
    created_at_utc: str | None = None,
) -> dict[str, int | str]:
    if pivot_radius <= 0:
        raise ValueError("pivot_radius must be positive")
    if recalc_tail_trading_days < 0:
        raise ValueError("recalc_tail_trading_days must be non-negative")

    normalized_market = (market or "").strip().lower() or None
    summary = _initialize_selection_summary(
        pivot_radius=pivot_radius,
        dry_run=dry_run,
        recalc_tail_trading_days=recalc_tail_trading_days,
        bounded_initial_from_date=bounded_initial_from_date,
    )
    run_id = run_id or generate_run_id()
    created_at_utc = created_at_utc or utc_now_iso()
    error_tickers: list[str] = []

    with _connect_sqlite(analysis_db_path) as analysis_conn, _connect_sqlite(
        osakedata_db_path
    ) as price_conn:
        ensure_stock_dow_structure_schema(analysis_conn)

        all_tickers_in_scope = _fetch_all_tickers_in_scope(
            price_conn, normalized_market
        )
        latest_ohlcv_dates = fetch_latest_ohlcv_dates(price_conn, normalized_market)
        no_valid_close = all_tickers_in_scope - set(latest_ohlcv_dates)
        summary["tickers_checked"] = len(all_tickers_in_scope)
        summary["tickers_no_valid_close_data"] = len(no_valid_close)

        for normalized_ticker in sorted(latest_ohlcv_dates):
            latest_ohlcv_date = latest_ohlcv_dates[normalized_ticker]
            status_row = _fetch_status_coverage_row(
                analysis_conn,
                normalized_ticker,
                pivot_radius,
                PRICE_SOURCE_CLOSE,
            )
            if status_row is None:
                if _has_event_rows(
                    analysis_conn,
                    normalized_ticker,
                    pivot_radius,
                    PRICE_SOURCE_CLOSE,
                ):
                    summary["tickers_registered_without_status"] = (
                        int(summary["tickers_registered_without_status"]) + 1
                    )
                    classification = "registered_without_status"
                else:
                    summary["tickers_missing"] = int(summary["tickers_missing"]) + 1
                    classification = "missing"
            elif latest_ohlcv_date > str(status_row["calculated_through_date"]):
                summary["tickers_outdated"] = int(summary["tickers_outdated"]) + 1
                classification = "outdated"
            else:
                summary["tickers_up_to_date"] = int(summary["tickers_up_to_date"]) + 1
                classification = "up_to_date"

            if classification == "up_to_date":
                continue

            try:
                if classification == "missing":
                    result = _run_bounded_initial_ticker_calculation(
                        price_conn,
                        ticker=normalized_ticker,
                        pivot_radius=pivot_radius,
                        initial_from_date=bounded_initial_from_date,
                        run_id=run_id,
                        created_at_utc=created_at_utc,
                    )
                else:
                    result = run_ticker_calculation(
                        analysis_conn,
                        price_conn,
                        ticker=normalized_ticker,
                        pivot_radius=pivot_radius,
                        recalc_tail_trading_days=recalc_tail_trading_days,
                        recalc_from_date=None,
                        force_full=False,
                        run_id=run_id,
                        created_at_utc=created_at_utc,
                    )
                if result.recalculation_mode == "skipped":
                    continue

                summary["tickers_processed"] = int(summary["tickers_processed"]) + 1
                if result.recalculation_mode == "bounded_initial":
                    summary["tickers_bounded_initial_recalculated"] = (
                        int(summary["tickers_bounded_initial_recalculated"]) + 1
                    )
                elif result.recalculation_mode == "incremental":
                    summary["tickers_incremental_recalculated"] = (
                        int(summary["tickers_incremental_recalculated"]) + 1
                    )
                elif result.recalculation_mode == "fallback_full":
                    summary["tickers_fallback_full_recalculated"] = (
                        int(summary["tickers_fallback_full_recalculated"]) + 1
                    )

                summary["rows_deleted"] = (
                    int(summary["rows_deleted"]) + result.rows_deleted
                )
                _accumulate_event_counts(summary, result.event_rows)

                if dry_run:
                    inserted = len(result.event_rows)
                    summary["rows_inserted"] = int(summary["rows_inserted"]) + inserted
                else:
                    inserted = insert_event_rows(analysis_conn, result.event_rows)
                    summary["rows_inserted"] = int(summary["rows_inserted"]) + inserted
                    if result.calculated_through_date is not None:
                        _upsert_status_row(
                            analysis_conn,
                            ticker=result.ticker,
                            market=result.market,
                            pivot_radius=pivot_radius,
                            calculated_from_date=result.calculated_from_date,
                            calculated_through_date=result.calculated_through_date,
                            latest_ohlcv_date_at_run=result.calculated_through_date,
                            latest_event_date=result.latest_event_date,
                            latest_event_confirmed_as_of_date=result.latest_event_confirmed_as_of_date,
                            last_run_id=run_id,
                            last_run_mode=result.recalculation_mode,
                            last_rows_deleted=result.rows_deleted,
                            last_rows_inserted=inserted,
                            last_status="OK",
                            last_error_message=None,
                            updated_at_utc=created_at_utc,
                        )
            except Exception:
                summary["errors"] = int(summary["errors"]) + 1
                error_tickers.append(normalized_ticker)
                continue

        if dry_run:
            analysis_conn.rollback()
        else:
            analysis_conn.commit()

    if error_tickers:
        summary["error_tickers"] = ",".join(error_tickers[:10])
    return summary
