from __future__ import annotations

import sqlite3
from datetime import date
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


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


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
    "normalize_candlestick_observation_row",
    "normalize_signal_name",
    "read_candlestick_observations",
    "read_divergence_observations",
    "read_dow_events",
    "read_dow_pivots",
    "read_dow_snapshot",
]
