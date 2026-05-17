from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from math import isfinite
from typing import Sequence


EMA10_SLOPE_LOOKBACK = 3
EMA20_SLOPE_LOOKBACK = 5

PRICE_DATA_STATUS_OK = "OK"
PRICE_DATA_STATUS_MISSING_AS_OF_DATE = "MISSING_AS_OF_DATE"
PRICE_DATA_STATUS_MISSING_CLOSE_AS_OF_DATE = "MISSING_CLOSE_AS_OF_DATE"
PRICE_DATA_STATUS_INSUFFICIENT_HISTORY = "INSUFFICIENT_HISTORY"


@dataclass(frozen=True)
class TickerOhlcvRow:
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


@dataclass(frozen=True)
class TickerSwingMetrics:
    close: float | None
    volume: float | None
    return_5d: float | None
    return_10d: float | None
    return_20d: float | None
    return_60d: float | None
    ma10: float | None
    ema10: float | None
    ema20: float | None
    distance_to_ma10_pct: float | None
    distance_to_ema10_pct: float | None
    distance_to_ema20_pct: float | None
    above_ma10: int | None
    above_ema10: int | None
    above_ema20: int | None
    ema10_slope_positive: int | None
    ema20_slope_positive: int | None
    ema10_slope_lookback: int
    ema20_slope_lookback: int
    highest_close_20d: float | None
    volume_avg_20d: float | None
    volume_vs_avg20: float | None
    price_data_status: str


@dataclass(frozen=True)
class _NormalizedTickerOhlcvRow:
    date: str
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: float | None


def _parse_iso_date(value: str, field_name: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc


def _normalize_optional_float(value: float | int | None, field_name: str) -> float | None:
    if value is None:
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: {value}") from exc
    if not isfinite(normalized):
        raise ValueError(f"Invalid {field_name}: {value}")
    return normalized


def _normalize_rows(rows: Sequence[TickerOhlcvRow]) -> list[_NormalizedTickerOhlcvRow]:
    normalized_rows: list[_NormalizedTickerOhlcvRow] = []
    seen_dates: set[str] = set()
    for row in rows:
        normalized_date = _parse_iso_date(str(row.date), "ohlcv row date")
        if normalized_date in seen_dates:
            raise ValueError(f"Duplicate OHLCV row for date {normalized_date}")
        seen_dates.add(normalized_date)
        normalized_rows.append(
            _NormalizedTickerOhlcvRow(
                date=normalized_date,
                open=_normalize_optional_float(row.open, "open"),
                high=_normalize_optional_float(row.high, "high"),
                low=_normalize_optional_float(row.low, "low"),
                close=_normalize_optional_float(row.close, "close"),
                volume=_normalize_optional_float(row.volume, "volume"),
            )
        )
    return sorted(normalized_rows, key=lambda item: item.date)


def _empty_metrics(status: str) -> TickerSwingMetrics:
    return TickerSwingMetrics(
        close=None,
        volume=None,
        return_5d=None,
        return_10d=None,
        return_20d=None,
        return_60d=None,
        ma10=None,
        ema10=None,
        ema20=None,
        distance_to_ma10_pct=None,
        distance_to_ema10_pct=None,
        distance_to_ema20_pct=None,
        above_ma10=None,
        above_ema10=None,
        above_ema20=None,
        ema10_slope_positive=None,
        ema20_slope_positive=None,
        ema10_slope_lookback=EMA10_SLOPE_LOOKBACK,
        ema20_slope_lookback=EMA20_SLOPE_LOOKBACK,
        highest_close_20d=None,
        volume_avg_20d=None,
        volume_vs_avg20=None,
        price_data_status=status,
    )


def _calculate_return(valid_closes: Sequence[float], lookback: int) -> float | None:
    if len(valid_closes) <= lookback:
        return None
    previous_close = valid_closes[-(lookback + 1)]
    if previous_close == 0:
        return None
    return (valid_closes[-1] / previous_close) - 1.0


def _calculate_sma(valid_closes: Sequence[float], window: int) -> float | None:
    if len(valid_closes) < window:
        return None
    return sum(valid_closes[-window:]) / float(window)


def _calculate_ema_series(valid_closes: Sequence[float], window: int) -> list[float]:
    if len(valid_closes) < window:
        return []

    ema_values: list[float] = []
    alpha = 2.0 / float(window + 1)
    ema = sum(valid_closes[:window]) / float(window)
    ema_values.append(ema)
    for close in valid_closes[window:]:
        ema = (close * alpha) + (ema * (1.0 - alpha))
        ema_values.append(ema)
    return ema_values


def _distance_pct(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0:
        return None
    return (numerator / denominator) - 1.0


def _strict_above(left: float | None, right: float | None) -> int | None:
    if left is None or right is None:
        return None
    return int(left > right)


def _positive_slope(
    ema_values: Sequence[float],
    lookback: int,
) -> int | None:
    if len(ema_values) <= lookback:
        return None
    return int(ema_values[-1] > ema_values[-(lookback + 1)])


def calculate_ticker_swing_metrics(
    rows: Sequence[TickerOhlcvRow],
    as_of_date: str,
) -> TickerSwingMetrics:
    normalized_as_of_date = _parse_iso_date(as_of_date, "as_of_date")
    normalized_rows = _normalize_rows(rows)
    rows_by_date = {row.date: row for row in normalized_rows}
    as_of_row = rows_by_date.get(normalized_as_of_date)
    if as_of_row is None:
        return _empty_metrics(PRICE_DATA_STATUS_MISSING_AS_OF_DATE)

    if as_of_row.close is None:
        return _empty_metrics(PRICE_DATA_STATUS_MISSING_CLOSE_AS_OF_DATE)

    relevant_rows = [row for row in normalized_rows if row.date <= normalized_as_of_date]
    valid_close_rows = [row for row in relevant_rows if row.close is not None]
    valid_closes = [row.close for row in valid_close_rows if row.close is not None]
    valid_volumes = [row.volume for row in relevant_rows if row.volume is not None]

    close_today = as_of_row.close
    volume_today = as_of_row.volume

    return_5d = _calculate_return(valid_closes, 5)
    return_10d = _calculate_return(valid_closes, 10)
    return_20d = _calculate_return(valid_closes, 20)
    return_60d = _calculate_return(valid_closes, 60)

    ma10 = _calculate_sma(valid_closes, 10)
    ema10_values = _calculate_ema_series(valid_closes, 10)
    ema20_values = _calculate_ema_series(valid_closes, 20)
    ema10 = ema10_values[-1] if ema10_values else None
    ema20 = ema20_values[-1] if ema20_values else None
    highest_close_20d = max(valid_closes[-20:]) if len(valid_closes) >= 20 else None

    volume_avg_20d = (
        sum(valid_volumes[-20:]) / 20.0 if len(valid_volumes) >= 20 else None
    )
    volume_vs_avg20 = (
        None
        if volume_today is None or volume_avg_20d is None or volume_avg_20d == 0
        else volume_today / volume_avg_20d
    )

    price_data_status = PRICE_DATA_STATUS_OK
    if len(valid_closes) < 10:
        price_data_status = PRICE_DATA_STATUS_INSUFFICIENT_HISTORY

    return TickerSwingMetrics(
        close=close_today,
        volume=volume_today,
        return_5d=return_5d,
        return_10d=return_10d,
        return_20d=return_20d,
        return_60d=return_60d,
        ma10=ma10,
        ema10=ema10,
        ema20=ema20,
        distance_to_ma10_pct=_distance_pct(close_today, ma10),
        distance_to_ema10_pct=_distance_pct(close_today, ema10),
        distance_to_ema20_pct=_distance_pct(close_today, ema20),
        above_ma10=_strict_above(close_today, ma10),
        above_ema10=_strict_above(close_today, ema10),
        above_ema20=_strict_above(close_today, ema20),
        ema10_slope_positive=_positive_slope(ema10_values, EMA10_SLOPE_LOOKBACK),
        ema20_slope_positive=_positive_slope(ema20_values, EMA20_SLOPE_LOOKBACK),
        ema10_slope_lookback=EMA10_SLOPE_LOOKBACK,
        ema20_slope_lookback=EMA20_SLOPE_LOOKBACK,
        highest_close_20d=highest_close_20d,
        volume_avg_20d=volume_avg_20d,
        volume_vs_avg20=volume_vs_avg20,
        price_data_status=price_data_status,
    )
