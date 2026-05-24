from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from typing import Sequence


EMA20_PERIOD = 20
SMA50_PERIOD = 50


@dataclass(frozen=True)
class SwingMaBreakStatusRow:
    ticker: str
    as_of_date: str
    close: float | None
    ema20: float | None
    sma50: float | None
    dist_ema20_pct: float | None
    dist_sma50_pct: float | None
    close_below_ema20: int | None
    ema20_break_pct: float | None
    ema20_break_confirmed: int | None
    consecutive_closes_below_ema20: int | None
    close_below_sma50: int | None
    sma50_break_pct: float | None
    sma50_break_confirmed: int | None
    consecutive_closes_below_sma50: int | None
    ma_break_status: str


def _float_value(value: object | None) -> float | None:
    if value is None:
        return None
    return float(value)


def load_ticker_ma_history_rows(
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
        SELECT signal_date, ticker, close, ema20
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


def _compute_ema_series(closes: Sequence[float], *, period: int) -> list[float | None]:
    values: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return values
    seed = sum(closes[:period]) / period
    values[period - 1] = seed
    alpha = 2.0 / (period + 1.0)
    ema_value = seed
    for index in range(period, len(closes)):
        ema_value = closes[index] * alpha + ema_value * (1.0 - alpha)
        values[index] = ema_value
    return values


def _compute_sma_series(closes: Sequence[float], *, period: int) -> list[float | None]:
    values: list[float | None] = [None] * len(closes)
    if len(closes) < period:
        return values
    rolling_sum = sum(closes[:period])
    values[period - 1] = rolling_sum / period
    for index in range(period, len(closes)):
        rolling_sum += closes[index] - closes[index - period]
        values[index] = rolling_sum / period
    return values


def _count_consecutive_breaks(
    closes: Sequence[float | None],
    moving_averages: Sequence[float | None],
) -> int | None:
    if not closes or not moving_averages:
        return None
    count = 0
    for close_value, moving_average in zip(reversed(closes), reversed(moving_averages)):
        if close_value is None or moving_average is None:
            break
        if close_value < moving_average:
            count += 1
            continue
        break
    return count


def _derive_ma_break_status(
    *,
    close: float | None,
    ema20: float | None,
    sma50: float | None,
    close_below_ema20: int | None,
    ema20_break_confirmed: int | None,
    close_below_sma50: int | None,
    sma50_break_confirmed: int | None,
) -> str:
    if close is None or ema20 is None or sma50 is None:
        return "INSUFFICIENT_DATA"
    if sma50_break_confirmed == 1:
        return "SMA50_CONFIRMED_BREAK"
    if close_below_sma50 == 1:
        return "SMA50_WARNING"
    if ema20_break_confirmed == 1:
        return "EMA20_CONFIRMED_BREAK"
    if close_below_ema20 == 1:
        return "EMA20_WARNING"
    return "OK"


def build_swing_ma_break_status_rows(
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
        ticker_history = history_by_ticker.get(ticker, [])
        closes = [_float_value(row.get("close")) for row in ticker_history]
        valid_closes = [value for value in closes if value is not None]
        ema20_series = _compute_ema_series(valid_closes, period=EMA20_PERIOD)
        sma50_series = _compute_sma_series(valid_closes, period=SMA50_PERIOD)

        close_index = -1
        mapped_ema20: list[float | None] = []
        mapped_sma50: list[float | None] = []
        for history_row in ticker_history:
            close_value = _float_value(history_row.get("close"))
            if close_value is None:
                mapped_ema20.append(None)
                mapped_sma50.append(None)
                continue
            close_index += 1
            mapped_ema20.append(_float_value(history_row.get("ema20")) or ema20_series[close_index])
            mapped_sma50.append(sma50_series[close_index])

        current_close = _float_value(latest_row.get("close"))
        current_ema20 = mapped_ema20[-1] if mapped_ema20 else None
        current_sma50 = mapped_sma50[-1] if mapped_sma50 else None

        dist_ema20_pct = None
        if current_close is not None and current_ema20 not in (None, 0.0):
            dist_ema20_pct = (current_close - current_ema20) / current_ema20

        dist_sma50_pct = None
        if current_close is not None and current_sma50 not in (None, 0.0):
            dist_sma50_pct = (current_close - current_sma50) / current_sma50

        close_below_ema20 = None
        if current_close is not None and current_ema20 is not None:
            close_below_ema20 = 1 if current_close < current_ema20 else 0

        close_below_sma50 = None
        if current_close is not None and current_sma50 is not None:
            close_below_sma50 = 1 if current_close < current_sma50 else 0

        consecutive_closes_below_ema20 = _count_consecutive_breaks(closes, mapped_ema20)
        consecutive_closes_below_sma50 = _count_consecutive_breaks(closes, mapped_sma50)

        ema20_break_pct = None
        if close_below_ema20 == 1:
            ema20_break_pct = dist_ema20_pct
        elif close_below_ema20 == 0:
            ema20_break_pct = 0.0

        sma50_break_pct = None
        if close_below_sma50 == 1:
            sma50_break_pct = dist_sma50_pct
        elif close_below_sma50 == 0:
            sma50_break_pct = 0.0

        ema20_break_confirmed = None
        if close_below_ema20 is not None:
            ema20_break_confirmed = int(
                close_below_ema20 == 1
                and (
                    (current_close is not None and current_ema20 is not None and current_close < current_ema20 * 0.985)
                    or (consecutive_closes_below_ema20 or 0) >= 2
                )
            )

        sma50_break_confirmed = None
        if close_below_sma50 is not None:
            sma50_break_confirmed = int(
                close_below_sma50 == 1
                and (
                    (current_close is not None and current_sma50 is not None and current_close < current_sma50 * 0.98)
                    or (consecutive_closes_below_sma50 or 0) >= 2
                )
            )

        output_rows.append(
            asdict(
                SwingMaBreakStatusRow(
                    ticker=ticker,
                    as_of_date=as_of_date,
                    close=current_close,
                    ema20=current_ema20,
                    sma50=current_sma50,
                    dist_ema20_pct=dist_ema20_pct,
                    dist_sma50_pct=dist_sma50_pct,
                    close_below_ema20=close_below_ema20,
                    ema20_break_pct=ema20_break_pct,
                    ema20_break_confirmed=ema20_break_confirmed,
                    consecutive_closes_below_ema20=consecutive_closes_below_ema20,
                    close_below_sma50=close_below_sma50,
                    sma50_break_pct=sma50_break_pct,
                    sma50_break_confirmed=sma50_break_confirmed,
                    consecutive_closes_below_sma50=consecutive_closes_below_sma50,
                    ma_break_status=_derive_ma_break_status(
                        close=current_close,
                        ema20=current_ema20,
                        sma50=current_sma50,
                        close_below_ema20=close_below_ema20,
                        ema20_break_confirmed=ema20_break_confirmed,
                        close_below_sma50=close_below_sma50,
                        sma50_break_confirmed=sma50_break_confirmed,
                    ),
                )
            )
        )
    return output_rows
