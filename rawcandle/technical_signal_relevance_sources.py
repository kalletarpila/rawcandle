from __future__ import annotations

import sqlite3
from datetime import date
from pathlib import Path
from typing import Any

from .technical_signal_relevance import (
    BOS_DOWN,
    BOS_UP,
    CANDLE,
    PIVOT_HIGH,
    PIVOT_LOW,
    RESET,
    RSI,
    TECH_SIGNAL_MAPPING_V1,
    TechnicalSignalDowSnapshot,
    TechnicalSignalEvent,
    TechnicalSignalObservation,
    TechnicalSignalPivot,
)


_SIGNAL_NAME_ALIASES = {
    "Hammer": "Hammer",
    "hammer": "Hammer",
    "Bullish Engulfing": "Bullish Engulfing",
    "bullish_engulfing": "Bullish Engulfing",
    "Piercing Pattern": "Piercing Pattern",
    "piercing_pattern": "Piercing Pattern",
    "Three White Soldiers": "Three White Soldiers",
    "three_white_soldiers": "Three White Soldiers",
    "Morning Star": "Morning Star",
    "morning_star": "Morning Star",
    "Dragonfly Doji": "Dragonfly Doji",
    "dragonfly_doji": "Dragonfly Doji",
    "Bullish Abandoned Baby": "Bullish Abandoned Baby",
    "bullish_abandoned_baby": "Bullish Abandoned Baby",
    "Bullish Flag": "Bullish Flag",
    "bullish_flag": "Bullish Flag",
    "Bull Rectangle": "Bull Rectangle",
    "bull_rectangle": "Bull Rectangle",
    "Ascending Triangle": "Ascending Triangle",
    "ascending_triangle": "Ascending Triangle",
    "Bullish Pennant": "Bullish Pennant",
    "bullish_pennant": "Bullish Pennant",
    "Cup and Handle": "Cup and Handle",
    "cup_and_handle": "Cup and Handle",
    "Bearish Engulfing": "Bearish Engulfing",
    "bearish_engulfing": "Bearish Engulfing",
    "Shooting Star": "Shooting Star",
    "shooting_star": "Shooting Star",
    "Dark Cloud Cover": "Dark Cloud Cover",
    "dark_cloud_cover": "Dark Cloud Cover",
    "Evening Star": "Evening Star",
    "evening_star": "Evening Star",
    "Hanging Man": "Hanging Man",
    "hanging_man": "Hanging Man",
    "Falling Three Methods": "Falling Three Methods",
    "falling_three_methods": "Falling Three Methods",
    "Bearish Flag": "Bearish Flag",
    "bearish_flag": "Bearish Flag",
    "Bear Rectangle": "Bear Rectangle",
    "bear_rectangle": "Bear Rectangle",
    "Descending Triangle": "Descending Triangle",
    "descending_triangle": "Descending Triangle",
    "Bearish Pennant": "Bearish Pennant",
    "bearish_pennant": "Bearish Pennant",
    "Bullish Divergence": "Bullish Divergence",
    "bullish_divergence": "Bullish Divergence",
    "Bearish Divergence": "Bearish Divergence",
    "bearish_divergence": "Bearish Divergence",
    "Hidden Bullish Divergence": "Hidden Bullish Divergence",
    "hidden_bullish_divergence": "Hidden Bullish Divergence",
    "Hidden Bearish Divergence": "Hidden Bearish Divergence",
    "hidden_bearish_divergence": "Hidden Bearish Divergence",
}

MAX_BAR_INDEX_LOOKBACK_BARS = 260


class TechnicalSignalBarIndex:
    def __init__(self, bar_dates: list[str]) -> None:
        self.bar_dates = tuple(bar_dates)
        self._date_to_index = {bar_date: index for index, bar_date in enumerate(self.bar_dates)}

    def bars_since(self, confirmed_as_of_date: str, observation_confirmed_as_of_date: str) -> int | None:
        start_index = self._date_to_index.get(confirmed_as_of_date)
        end_index = self._date_to_index.get(observation_confirmed_as_of_date)
        if start_index is None or end_index is None or end_index < start_index:
            return None
        return end_index - start_index


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def _normalize_iso_dates(values: list[str] | tuple[str, ...], field_name: str) -> list[str]:
    return sorted({_parse_iso_date(value, field_name) for value in values})


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
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _resolve_ohlcv_connection(conn: sqlite3.Connection) -> tuple[sqlite3.Connection | None, bool]:
    if _table_exists(conn, "osakedata"):
        return conn, False

    database_rows = conn.execute("PRAGMA database_list").fetchall()
    main_path = None
    for row in database_rows:
        if str(row[1]) == "main":
            main_path = str(row[2])
            break
    if not main_path:
        return None, False

    sibling_path = Path(main_path).resolve().with_name("osakedata.db")
    if not sibling_path.is_file():
        return None, False

    ohlcv_conn = sqlite3.connect(str(sibling_path))
    ohlcv_conn.row_factory = sqlite3.Row
    return ohlcv_conn, True


def _introspect_ohlcv_schema(conn: sqlite3.Connection) -> tuple[str, str]:
    columns = {
        str(row[1]).lower(): str(row[1])
        for row in conn.execute("PRAGMA table_info(osakedata)").fetchall()
    }
    ticker_column = columns.get("osake") or columns.get("ticker")
    date_column = columns.get("pvm") or columns.get("date")
    if ticker_column is None or date_column is None:
        raise RuntimeError("Missing required OHLCV columns in osakedata")
    return ticker_column, date_column


def _row_value(row: sqlite3.Row | dict[str, Any], field_name: str) -> Any:
    if isinstance(row, sqlite3.Row):
        return row[field_name]
    return row.get(field_name)


def _build_fallback_event_id(
    ticker: str,
    event_type: str,
    event_date: str,
    confirmed_as_of_date: str,
) -> str:
    return f"{ticker}:{event_type}:{event_date}:{confirmed_as_of_date}"


def read_bar_dates(
    conn: sqlite3.Connection,
    ticker: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    lookback_bars: int,
    ohlcv_conn: sqlite3.Connection | None = None,
) -> list[str]:
    del timeframe
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )

    resolved_ohlcv_conn = ohlcv_conn
    should_close = False
    if resolved_ohlcv_conn is None:
        resolved_ohlcv_conn, should_close = _resolve_ohlcv_connection(conn)
    if resolved_ohlcv_conn is None or not _table_exists(resolved_ohlcv_conn, "osakedata"):
        return []

    try:
        ticker_column, date_column = _introspect_ohlcv_schema(resolved_ohlcv_conn)
        rows = resolved_ohlcv_conn.execute(
            f"""
            WITH in_range AS (
                SELECT {date_column} AS bar_date
                FROM osakedata
                WHERE UPPER(TRIM({ticker_column})) = UPPER(TRIM(?))
                  AND {date_column} >= ?
                  AND {date_column} <= ?
                ORDER BY {date_column} ASC
            ),
            lookback AS (
                SELECT {date_column} AS bar_date
                FROM osakedata
                WHERE UPPER(TRIM({ticker_column})) = UPPER(TRIM(?))
                  AND {date_column} < ?
                ORDER BY {date_column} DESC
                LIMIT ?
            )
            SELECT bar_date
            FROM (
                SELECT bar_date FROM lookback
                UNION
                SELECT bar_date FROM in_range
            )
            ORDER BY bar_date ASC
            """,
            (
                ticker,
                normalized_start_date,
                normalized_end_date,
                ticker,
                normalized_start_date,
                int(lookback_bars),
            ),
        ).fetchall()
        return [str(row["bar_date"]) for row in rows]
    finally:
        if should_close:
            ohlcv_conn.close()


def build_bar_index(
    conn: sqlite3.Connection,
    ticker: str,
    timeframe: str,
    start_date: str,
    end_date: str,
    lookback_bars: int,
    ohlcv_conn: sqlite3.Connection | None = None,
) -> TechnicalSignalBarIndex | None:
    bar_dates = read_bar_dates(
        conn,
        ticker,
        timeframe,
        start_date,
        end_date,
        lookback_bars,
        ohlcv_conn=ohlcv_conn,
    )
    if not bar_dates:
        return None
    return TechnicalSignalBarIndex(bar_dates)


def build_context_aware_bar_index(
    conn: sqlite3.Connection,
    ticker: str,
    timeframe: str,
    observation_confirmed_as_of_dates: list[str] | tuple[str, ...],
    candidate_confirmed_as_of_dates: list[str] | tuple[str, ...],
    max_lookback_bars: int = MAX_BAR_INDEX_LOOKBACK_BARS,
    ohlcv_conn: sqlite3.Connection | None = None,
) -> TechnicalSignalBarIndex | None:
    del timeframe
    normalized_observation_dates = _normalize_iso_dates(
        list(observation_confirmed_as_of_dates),
        "observation_confirmed_as_of_dates",
    )
    if not normalized_observation_dates:
        return None
    normalized_candidate_dates = _normalize_iso_dates(
        list(candidate_confirmed_as_of_dates) or list(normalized_observation_dates),
        "candidate_confirmed_as_of_dates",
    )
    earliest_observation_date = normalized_observation_dates[0]
    latest_observation_date = normalized_observation_dates[-1]
    earliest_required_date = min(normalized_candidate_dates[0], earliest_observation_date)

    resolved_ohlcv_conn = ohlcv_conn
    should_close = False
    if resolved_ohlcv_conn is None:
        resolved_ohlcv_conn, should_close = _resolve_ohlcv_connection(conn)
    if resolved_ohlcv_conn is None or not _table_exists(resolved_ohlcv_conn, "osakedata"):
        return None

    try:
        ticker_column, date_column = _introspect_ohlcv_schema(resolved_ohlcv_conn)
        in_range_count_row = resolved_ohlcv_conn.execute(
            f"""
            SELECT COUNT(*) AS row_count
            FROM osakedata
            WHERE UPPER(TRIM({ticker_column})) = UPPER(TRIM(?))
              AND {date_column} >= ?
              AND {date_column} <= ?
            """,
            (
                ticker,
                earliest_observation_date,
                latest_observation_date,
            ),
        ).fetchone()
        in_range_count = 0 if in_range_count_row is None else int(in_range_count_row["row_count"])
        if in_range_count == 0:
            return None

        required_coverage_count_row = resolved_ohlcv_conn.execute(
            f"""
            SELECT COUNT(*) AS row_count
            FROM osakedata
            WHERE UPPER(TRIM({ticker_column})) = UPPER(TRIM(?))
              AND {date_column} >= ?
              AND {date_column} <= ?
            """,
            (
                ticker,
                earliest_required_date,
                latest_observation_date,
            ),
        ).fetchone()
        required_coverage_count = (
            0 if required_coverage_count_row is None else int(required_coverage_count_row["row_count"])
        )
        capped_row_limit = in_range_count + int(max_lookback_bars)
        total_row_limit = min(required_coverage_count, capped_row_limit)
        if total_row_limit <= 0:
            return None

        rows = resolved_ohlcv_conn.execute(
            f"""
            SELECT {date_column} AS bar_date
            FROM (
                SELECT {date_column}
                FROM osakedata
                WHERE UPPER(TRIM({ticker_column})) = UPPER(TRIM(?))
                  AND {date_column} <= ?
                ORDER BY {date_column} DESC
                LIMIT ?
            )
            ORDER BY bar_date ASC
            """,
            (
                ticker,
                latest_observation_date,
                total_row_limit,
            ),
        ).fetchall()
        bar_dates = [str(row["bar_date"]) for row in rows]
        if not bar_dates:
            return None
        return TechnicalSignalBarIndex(bar_dates)
    finally:
        if should_close:
            resolved_ohlcv_conn.close()


def assign_event_bar_distances(
    events: list[TechnicalSignalEvent],
    observation_confirmed_as_of_date: str,
    bar_index: TechnicalSignalBarIndex | None,
) -> list[TechnicalSignalEvent]:
    return [
        TechnicalSignalEvent(
            event_type=event.event_type,
            event_date=event.event_date,
            confirmed_as_of_date=event.confirmed_as_of_date,
            event_id=event.event_id,
            structure_epoch_id=event.structure_epoch_id,
            bars_since_confirmation=(
                None
                if bar_index is None
                else bar_index.bars_since(event.confirmed_as_of_date, observation_confirmed_as_of_date)
            ),
        )
        for event in events
    ]


def assign_pivot_bar_distances(
    pivots: list[TechnicalSignalPivot],
    observation_confirmed_as_of_date: str,
    bar_index: TechnicalSignalBarIndex | None,
) -> list[TechnicalSignalPivot]:
    return [
        TechnicalSignalPivot(
            event_type=pivot.event_type,
            event_date=pivot.event_date,
            confirmed_as_of_date=pivot.confirmed_as_of_date,
            event_id=pivot.event_id,
            structure_epoch_id=pivot.structure_epoch_id,
            bars_since_confirmation=(
                None
                if bar_index is None
                else bar_index.bars_since(pivot.confirmed_as_of_date, observation_confirmed_as_of_date)
            ),
        )
        for pivot in pivots
    ]


def normalize_signal_name(raw_name: str | None) -> str | None:
    if raw_name is None:
        return None
    normalized = _SIGNAL_NAME_ALIASES.get(str(raw_name))
    if normalized is None:
        return None
    return normalized if normalized in TECH_SIGNAL_MAPPING_V1 else None


def _resolve_optional_candlestick_close(
    row: sqlite3.Row | dict[str, Any],
    available_fields: set[str] | None = None,
) -> float | None:
    candidate_fields = ("signal_close_price", "close_price", "close", "price")
    if available_fields is None:
        for field_name in candidate_fields:
            try:
                value = _row_value(row, field_name)
            except (KeyError, IndexError):
                continue
            if value is not None:
                return float(value)
        return None

    for field_name in candidate_fields:
        if field_name in available_fields:
            value = _row_value(row, field_name)
            if value is not None:
                return float(value)
    return None


def read_divergence_observations(
    conn: sqlite3.Connection,
    ticker: str,
    timeframe: str,
    start_date: str,
    end_date: str,
) -> list[TechnicalSignalObservation]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )
    if not _table_exists(conn, "divergence_data"):
        return []

    columns = _table_columns(conn, "divergence_data")
    hidden_bullish_strength_expr = (
        "hidden_bullish_strength"
        if "hidden_bullish_strength" in columns
        else "NULL AS hidden_bullish_strength"
    )
    hidden_bearish_strength_expr = (
        "hidden_bearish_strength"
        if "hidden_bearish_strength" in columns
        else "NULL AS hidden_bearish_strength"
    )
    hidden_bullish_flag_expr = (
        "is_hidden_bullish_divergence_r3"
        if "is_hidden_bullish_divergence_r3" in columns
        else "NULL AS is_hidden_bullish_divergence_r3"
    )
    hidden_bearish_flag_expr = (
        "is_hidden_bearish_divergence_r3"
        if "is_hidden_bearish_divergence_r3" in columns
        else "NULL AS is_hidden_bearish_divergence_r3"
    )
    rows = conn.execute(
        f"""
        SELECT
            ticker,
            date,
            bullish_strength,
            bearish_strength,
            {hidden_bullish_strength_expr},
            {hidden_bearish_strength_expr},
            {hidden_bullish_flag_expr},
            {hidden_bearish_flag_expr}
        FROM divergence_data
        WHERE ticker = ?
          AND date >= ?
          AND date <= ?
        ORDER BY date ASC
        """,
        (ticker, normalized_start_date, normalized_end_date),
    ).fetchall()

    observations: list[TechnicalSignalObservation] = []
    for row in rows:
        signal_date = str(row["date"])
        if (row["bullish_strength"] or 0) > 0:
            observations.append(
                TechnicalSignalObservation(
                    ticker=str(row["ticker"]),
                    timeframe=timeframe,
                    signal_date=signal_date,
                    signal_confirmed_as_of_date=signal_date,
                    signal_name="Bullish Divergence",
                    signal_close_price=None,
                    signal_source_id=RSI,
                )
            )
        if (row["bearish_strength"] or 0) > 0:
            observations.append(
                TechnicalSignalObservation(
                    ticker=str(row["ticker"]),
                    timeframe=timeframe,
                    signal_date=signal_date,
                    signal_confirmed_as_of_date=signal_date,
                    signal_name="Bearish Divergence",
                    signal_close_price=None,
                    signal_source_id=RSI,
                )
            )
        if "hidden_bullish_strength" in columns and (
            (row["hidden_bullish_strength"] or 0) > 0
            or int(row["is_hidden_bullish_divergence_r3"] or 0) == 1
        ):
            observations.append(
                TechnicalSignalObservation(
                    ticker=str(row["ticker"]),
                    timeframe=timeframe,
                    signal_date=signal_date,
                    signal_confirmed_as_of_date=signal_date,
                    signal_name="Hidden Bullish Divergence",
                    signal_close_price=None,
                    signal_source_id=RSI,
                )
            )
        if "hidden_bearish_strength" in columns and (
            (row["hidden_bearish_strength"] or 0) > 0
            or int(row["is_hidden_bearish_divergence_r3"] or 0) == 1
        ):
            observations.append(
                TechnicalSignalObservation(
                    ticker=str(row["ticker"]),
                    timeframe=timeframe,
                    signal_date=signal_date,
                    signal_confirmed_as_of_date=signal_date,
                    signal_name="Hidden Bearish Divergence",
                    signal_close_price=None,
                    signal_source_id=RSI,
                )
            )
    return observations


def normalize_candlestick_observation_row(
    row: sqlite3.Row | dict[str, Any],
    timeframe: str,
) -> TechnicalSignalObservation:
    ticker = _row_value(row, "ticker")
    signal_date = _parse_iso_date(str(_row_value(row, "signal_date")), "signal_date")
    raw_signal_name = _row_value(row, "signal_name")
    signal_name = normalize_signal_name(None if raw_signal_name is None else str(raw_signal_name))
    if signal_name is None:
        raise ValueError(f"Unknown candlestick signal_name: {raw_signal_name}")
    signal_confirmed_as_of_date = _row_value(row, "signal_confirmed_as_of_date")
    if signal_confirmed_as_of_date is None:
        signal_confirmed_as_of_date = signal_date
    else:
        signal_confirmed_as_of_date = _parse_iso_date(
            str(signal_confirmed_as_of_date),
            "signal_confirmed_as_of_date",
        )
    signal_close_price = _resolve_optional_candlestick_close(row)
    return TechnicalSignalObservation(
        ticker=str(ticker),
        timeframe=timeframe,
        signal_date=signal_date,
        signal_confirmed_as_of_date=signal_confirmed_as_of_date,
        signal_name=signal_name,
        signal_close_price=None if signal_close_price is None else float(signal_close_price),
        signal_source_id=CANDLE,
    )


def read_candlestick_observations(
    conn: sqlite3.Connection,
    ticker: str,
    timeframe: str,
    start_date: str,
    end_date: str,
) -> list[TechnicalSignalObservation]:
    normalized_start_date = _parse_iso_date(start_date, "start_date")
    normalized_end_date = _parse_iso_date(end_date, "end_date")
    if normalized_start_date > normalized_end_date:
        raise ValueError(
            f"Invalid date range: start_date {normalized_start_date} is after end_date {normalized_end_date}"
        )
    if not _table_exists(conn, "analysis_findings"):
        return []

    columns = _table_columns(conn, "analysis_findings")
    if not {"ticker", "date", "pattern"}.issubset(columns):
        return []

    close_expr = None
    for candidate in ("signal_close_price", "close_price", "close", "price"):
        if candidate in columns:
            close_expr = candidate
            break
    close_select = (
        f", {close_expr} AS signal_close_price"
        if close_expr is not None
        else ", NULL AS signal_close_price"
    )

    rows = conn.execute(
        f"""
        SELECT
            ticker,
            date,
            pattern AS signal_name,
            date AS signal_date,
            date AS signal_confirmed_as_of_date
            {close_select}
        FROM analysis_findings
        WHERE ticker = ?
          AND date >= ?
          AND date <= ?
        ORDER BY date ASC, pattern ASC, id ASC
        """,
        (ticker, normalized_start_date, normalized_end_date),
    ).fetchall()

    observations: list[TechnicalSignalObservation] = []
    for row in rows:
        normalized_name = normalize_signal_name(
            None if row["signal_name"] is None else str(row["signal_name"])
        )
        if normalized_name is None:
            continue
        mapping_entry = TECH_SIGNAL_MAPPING_V1[normalized_name]
        if mapping_entry.signal_source_type != CANDLE:
            continue
        observations.append(normalize_candlestick_observation_row(row, timeframe))
    return observations


def read_dow_snapshot(
    conn: sqlite3.Connection,
    ticker: str,
    timeframe: str,
    as_of_date: str,
) -> TechnicalSignalDowSnapshot | None:
    del timeframe
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    if not _table_exists(conn, "stock_dow_structure_events"):
        return None
    columns = _table_columns(conn, "stock_dow_structure_events")
    active_bos_high_expr = (
        "active_bos_high_price"
        if "active_bos_high_price" in columns
        else "NULL AS active_bos_high_price"
    )
    active_bos_low_expr = (
        "active_bos_low_price"
        if "active_bos_low_price" in columns
        else "NULL AS active_bos_low_price"
    )
    structure_epoch_expr = (
        "structure_epoch_id"
        if "structure_epoch_id" in columns
        else "NULL AS structure_epoch_id"
    )
    row = conn.execute(
        f"""
        SELECT
            trend_state,
            {active_bos_high_expr},
            {active_bos_low_expr},
            {structure_epoch_expr}
        FROM stock_dow_structure_events
        WHERE ticker = ?
          AND confirmed_as_of_date <= ?
        ORDER BY confirmed_as_of_date DESC, event_date DESC, id DESC
        LIMIT 1
        """,
        (ticker, normalized_as_of_date),
    ).fetchone()
    if row is None:
        return None
    return TechnicalSignalDowSnapshot(
        trend_state=None if row["trend_state"] is None else str(row["trend_state"]),
        dow_context_state=None,
        active_bos_high_price=None if row["active_bos_high_price"] is None else float(row["active_bos_high_price"]),
        active_bos_low_price=None if row["active_bos_low_price"] is None else float(row["active_bos_low_price"]),
        structure_epoch_id=None if row["structure_epoch_id"] is None else int(row["structure_epoch_id"]),
        as_of_date=normalized_as_of_date,
    )


def read_dow_events(
    conn: sqlite3.Connection,
    ticker: str,
    timeframe: str,
    as_of_date: str,
) -> list[TechnicalSignalEvent]:
    del timeframe
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    if not _table_exists(conn, "stock_dow_structure_events"):
        return []
    columns = _table_columns(conn, "stock_dow_structure_events")
    structure_epoch_expr = (
        "structure_epoch_id"
        if "structure_epoch_id" in columns
        else "NULL AS structure_epoch_id"
    )
    rows = conn.execute(
        f"""
        SELECT
            id,
            ticker,
            event_type,
            event_date,
            confirmed_as_of_date,
            {structure_epoch_expr}
        FROM stock_dow_structure_events
        WHERE ticker = ?
          AND confirmed_as_of_date <= ?
          AND event_type IN (?, ?, ?, ?)
        ORDER BY confirmed_as_of_date ASC, event_date ASC, id ASC
        """,
        (ticker, normalized_as_of_date, BOS_UP, BOS_DOWN, RESET, "TREND_CHANGE"),
    ).fetchall()
    return [
        TechnicalSignalEvent(
            event_type=str(row["event_type"]),
            event_date=str(row["event_date"]),
            confirmed_as_of_date=str(row["confirmed_as_of_date"]),
            event_id=(
                row["id"]
                if row["id"] is not None
                else _build_fallback_event_id(
                    str(row["ticker"]),
                    str(row["event_type"]),
                    str(row["event_date"]),
                    str(row["confirmed_as_of_date"]),
                )
            ),
            structure_epoch_id=None if row["structure_epoch_id"] is None else int(row["structure_epoch_id"]),
        )
        for row in rows
    ]


def read_dow_pivots(
    conn: sqlite3.Connection,
    ticker: str,
    timeframe: str,
    as_of_date: str,
) -> list[TechnicalSignalPivot]:
    del timeframe
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    if not _table_exists(conn, "stock_dow_structure_events"):
        return []
    columns = _table_columns(conn, "stock_dow_structure_events")
    structure_epoch_expr = (
        "structure_epoch_id"
        if "structure_epoch_id" in columns
        else "NULL AS structure_epoch_id"
    )
    rows = conn.execute(
        f"""
        SELECT
            id,
            ticker,
            event_type,
            event_date,
            confirmed_as_of_date,
            {structure_epoch_expr}
        FROM stock_dow_structure_events
        WHERE ticker = ?
          AND confirmed_as_of_date <= ?
          AND event_type IN (?, ?)
        ORDER BY confirmed_as_of_date ASC, event_date ASC, id ASC
        """,
        (ticker, normalized_as_of_date, PIVOT_HIGH, PIVOT_LOW),
    ).fetchall()
    return [
        TechnicalSignalPivot(
            event_type=str(row["event_type"]),
            event_date=str(row["event_date"]),
            confirmed_as_of_date=str(row["confirmed_as_of_date"]),
            event_id=(
                row["id"]
                if row["id"] is not None
                else _build_fallback_event_id(
                    str(row["ticker"]),
                    str(row["event_type"]),
                    str(row["event_date"]),
                    str(row["confirmed_as_of_date"]),
                )
            ),
            structure_epoch_id=None if row["structure_epoch_id"] is None else int(row["structure_epoch_id"]),
        )
        for row in rows
    ]


__all__ = [
    "MAX_BAR_INDEX_LOOKBACK_BARS",
    "TechnicalSignalBarIndex",
    "assign_event_bar_distances",
    "assign_pivot_bar_distances",
    "build_bar_index",
    "build_context_aware_bar_index",
    "normalize_candlestick_observation_row",
    "normalize_signal_name",
    "read_bar_dates",
    "read_candlestick_observations",
    "read_divergence_observations",
    "read_dow_events",
    "read_dow_pivots",
    "read_dow_snapshot",
]
