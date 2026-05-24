from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Sequence


BULLISH_CANDLE_WINDOW = 5
BEARISH_CANDLE_WINDOW = 5
BULLISH_DIVERGENCE_WINDOW = 20
BEARISH_DIVERGENCE_WINDOW = 20
HIDDEN_BULLISH_DIVERGENCE_WINDOW = 20
HIDDEN_BEARISH_DIVERGENCE_WINDOW = 20
BOS_UP_WINDOW = 30
BOS_DOWN_WINDOW = 30
RESET_WINDOW = 40


@dataclass(frozen=True)
class SwingSignalFreshnessRow:
    ticker: str
    as_of_date: str
    latest_bullish_candle: str
    bullish_candle_age_td: int | None
    latest_bearish_candle: str
    bearish_candle_age_td: int | None
    latest_bullish_divergence: int
    bullish_divergence_age_td: int | None
    latest_bearish_divergence: int
    bearish_divergence_age_td: int | None
    latest_hidden_bullish_divergence: int
    hidden_bullish_divergence_age_td: int | None
    latest_hidden_bearish_divergence: int
    hidden_bearish_divergence_age_td: int | None
    latest_bos_up_age_td: int | None
    latest_bos_down_age_td: int | None
    latest_reset_age_td: int | None
    latest_bullish_signal_age_td: int | None
    latest_bearish_signal_age_td: int | None
    structure_warning_overrides_bullish_signal: int
    freshness_status: str


def load_ticker_signal_freshness_history_rows(
    conn: sqlite3.Connection,
    *,
    tickers: Sequence[str],
    as_of_date: str,
    signal_version: str,
    taxonomy_version: str | None,
) -> list[dict[str, object]]:
    if not tickers or taxonomy_version is None:
        return []
    placeholders = ", ".join("?" for _ in tickers)
    rows = conn.execute(
        f"""
        SELECT
            signal_date,
            ticker,
            bullish_divergence_signal,
            bearish_divergence_signal,
            hidden_bullish_divergence_signal,
            hidden_bearish_divergence_signal,
            bullish_candle_signal,
            bearish_candle_signal,
            latest_bos_event_type,
            latest_bos_event_date,
            latest_bos_age_trading_days,
            latest_reset_reason,
            latest_reset_event_date,
            latest_reset_age_trading_days
        FROM dc_ticker_swing_signal_daily
        WHERE signal_date <= ?
          AND signal_version = ?
          AND taxonomy_version = ?
          AND ticker IN ({placeholders})
        ORDER BY ticker ASC, signal_date ASC
        """,
        (as_of_date, signal_version, taxonomy_version, *tickers),
    ).fetchall()
    return [{key: row[key] for key in row.keys()} for row in rows]


def _int_value(value: object | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _find_latest_flag_age(
    rows: Sequence[dict[str, object]],
    *,
    field_name: str,
) -> int | None:
    if not rows:
        return None
    last_index = len(rows) - 1
    for index in range(last_index, -1, -1):
        if _int_value(rows[index].get(field_name)) == 1:
            return last_index - index
    return None


def _find_date_age(
    rows: Sequence[dict[str, object]],
    *,
    date_field: str,
) -> int | None:
    if not rows:
        return None
    event_date = rows[-1].get(date_field)
    if event_date is None:
        return None
    event_date_str = str(event_date)
    last_index = len(rows) - 1
    for index in range(last_index, -1, -1):
        if str(rows[index].get("signal_date") or "") == event_date_str:
            return last_index - index
    return None


def _resolved_bos_age(rows: Sequence[dict[str, object]], *, bos_type: str) -> int | None:
    if not rows:
        return None
    latest_row = rows[-1]
    if str(latest_row.get("latest_bos_event_type") or "") != bos_type:
        return None
    stored_age = _int_value(latest_row.get("latest_bos_age_trading_days"))
    if stored_age is not None:
        return stored_age
    return _find_date_age(rows, date_field="latest_bos_event_date")


def _resolved_reset_age(rows: Sequence[dict[str, object]]) -> int | None:
    if not rows:
        return None
    latest_row = rows[-1]
    if latest_row.get("latest_reset_reason") is None:
        return None
    stored_age = _int_value(latest_row.get("latest_reset_age_trading_days"))
    if stored_age is not None:
        return stored_age
    return _find_date_age(rows, date_field="latest_reset_event_date")


def _is_fresh(age: int | None, *, window: int) -> bool:
    return age is not None and 0 <= age <= window


def _derive_freshness_status(
    *,
    has_required_context: bool,
    structure_warning_overrides_bullish_signal: int,
    fresh_bullish_signal: bool,
    fresh_bearish_signal: bool,
) -> str:
    if not has_required_context:
        return "INSUFFICIENT_DATA"
    if structure_warning_overrides_bullish_signal == 1:
        return "STRUCTURE_WARNING_OVERRIDES_BULLISH"
    if fresh_bullish_signal and fresh_bearish_signal:
        return "MIXED_SIGNALS"
    if fresh_bullish_signal:
        return "FRESH_BULLISH_SIGNAL"
    if fresh_bearish_signal:
        return "FRESH_BEARISH_SIGNAL"
    return "NO_RECENT_SIGNAL"


def build_swing_signal_freshness_rows(
    *,
    latest_rows: Sequence[dict[str, object]],
    history_rows: Sequence[dict[str, object]],
    as_of_date: str,
) -> list[dict[str, object]]:
    history_by_ticker: dict[str, list[dict[str, object]]] = {}
    for row in history_rows:
        ticker = str(row.get("ticker") or "")
        if not ticker:
            continue
        history_by_ticker.setdefault(ticker, []).append(row)
    for rows in history_by_ticker.values():
        rows.sort(key=lambda row: str(row.get("signal_date") or ""))

    output_rows: list[dict[str, object]] = []
    for latest_row in sorted(latest_rows, key=lambda row: str(row.get("ticker") or "")):
        ticker = str(latest_row.get("ticker") or "")
        if not ticker:
            continue
        rows = history_by_ticker.get(ticker, [])
        has_required_context = bool(rows) and bool(str(latest_row.get("signal_date") or "") or as_of_date)

        bullish_candle_age = _find_latest_flag_age(rows, field_name="bullish_candle_signal")
        bearish_candle_age = _find_latest_flag_age(rows, field_name="bearish_candle_signal")
        bullish_divergence_age = _find_latest_flag_age(rows, field_name="bullish_divergence_signal")
        bearish_divergence_age = _find_latest_flag_age(rows, field_name="bearish_divergence_signal")
        hidden_bullish_divergence_age = _find_latest_flag_age(rows, field_name="hidden_bullish_divergence_signal")
        hidden_bearish_divergence_age = _find_latest_flag_age(rows, field_name="hidden_bearish_divergence_signal")
        bos_up_age = _resolved_bos_age(rows, bos_type="BOS_UP")
        bos_down_age = _resolved_bos_age(rows, bos_type="BOS_DOWN")
        reset_age = _resolved_reset_age(rows)

        fresh_bullish_ages = [
            age
            for age, window in (
                (bullish_candle_age, BULLISH_CANDLE_WINDOW),
                (bullish_divergence_age, BULLISH_DIVERGENCE_WINDOW),
                (hidden_bullish_divergence_age, HIDDEN_BULLISH_DIVERGENCE_WINDOW),
                (bos_up_age, BOS_UP_WINDOW),
            )
            if _is_fresh(age, window=window)
        ]
        fresh_bearish_ages = [
            age
            for age, window in (
                (bearish_candle_age, BEARISH_CANDLE_WINDOW),
                (bearish_divergence_age, BEARISH_DIVERGENCE_WINDOW),
                (hidden_bearish_divergence_age, HIDDEN_BEARISH_DIVERGENCE_WINDOW),
                (bos_down_age, BOS_DOWN_WINDOW),
                (reset_age, RESET_WINDOW),
            )
            if _is_fresh(age, window=window)
        ]

        latest_bullish_signal_age = min(fresh_bullish_ages) if fresh_bullish_ages else None
        latest_bearish_signal_age = min(fresh_bearish_ages) if fresh_bearish_ages else None

        structure_warning_overrides_bullish_signal = int(
            latest_bullish_signal_age is not None
            and any(
                age is not None and age < latest_bullish_signal_age
                for age, window in (
                    (bos_down_age, BOS_DOWN_WINDOW),
                    (reset_age, RESET_WINDOW),
                )
                if _is_fresh(age, window=window)
            )
        )

        fresh_bullish_signal = latest_bullish_signal_age is not None
        fresh_bearish_signal = latest_bearish_signal_age is not None

        output_rows.append(
            asdict(
                SwingSignalFreshnessRow(
                    ticker=ticker,
                    as_of_date=as_of_date,
                    latest_bullish_candle="" if bullish_candle_age is None else "BULLISH_CANDLE",
                    bullish_candle_age_td=bullish_candle_age,
                    latest_bearish_candle="" if bearish_candle_age is None else "BEARISH_CANDLE",
                    bearish_candle_age_td=bearish_candle_age,
                    latest_bullish_divergence=int(_is_fresh(bullish_divergence_age, window=BULLISH_DIVERGENCE_WINDOW)),
                    bullish_divergence_age_td=bullish_divergence_age,
                    latest_bearish_divergence=int(_is_fresh(bearish_divergence_age, window=BEARISH_DIVERGENCE_WINDOW)),
                    bearish_divergence_age_td=bearish_divergence_age,
                    latest_hidden_bullish_divergence=int(
                        _is_fresh(hidden_bullish_divergence_age, window=HIDDEN_BULLISH_DIVERGENCE_WINDOW)
                    ),
                    hidden_bullish_divergence_age_td=hidden_bullish_divergence_age,
                    latest_hidden_bearish_divergence=int(
                        _is_fresh(hidden_bearish_divergence_age, window=HIDDEN_BEARISH_DIVERGENCE_WINDOW)
                    ),
                    hidden_bearish_divergence_age_td=hidden_bearish_divergence_age,
                    latest_bos_up_age_td=bos_up_age,
                    latest_bos_down_age_td=bos_down_age,
                    latest_reset_age_td=reset_age,
                    latest_bullish_signal_age_td=latest_bullish_signal_age,
                    latest_bearish_signal_age_td=latest_bearish_signal_age,
                    structure_warning_overrides_bullish_signal=structure_warning_overrides_bullish_signal,
                    freshness_status=_derive_freshness_status(
                        has_required_context=has_required_context,
                        structure_warning_overrides_bullish_signal=structure_warning_overrides_bullish_signal,
                        fresh_bullish_signal=fresh_bullish_signal,
                        fresh_bearish_signal=fresh_bearish_signal,
                    ),
                )
            )
        )
    return output_rows
