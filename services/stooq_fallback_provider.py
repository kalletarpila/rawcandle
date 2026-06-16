from __future__ import annotations

import csv
import io
from datetime import date
from typing import Callable, List, Optional, Sequence
from urllib.request import urlopen

from services.stock_update_service import StockOhlcvRow

STOOQ_DAILY_URL_TEMPLATE = "https://stooq.com/q/d/l/?s={symbol}&i=d"


def map_ticker_to_stooq_symbol(ticker: str) -> Optional[str]:
    normalized = (ticker or "").strip()
    if not normalized or "." in normalized:
        return None
    return f"{normalized.lower()}.us"


def build_stooq_daily_url(symbol: str) -> str:
    return STOOQ_DAILY_URL_TEMPLATE.format(symbol=symbol)


def _normalize_missing_dates(missing_dates: Sequence[object]) -> List[str]:
    normalized: List[str] = []
    seen = set()
    for value in missing_dates:
        if isinstance(value, date):
            date_str = value.isoformat()
        else:
            date_str = str(value).strip()
        if not date_str or date_str in seen:
            continue
        normalized.append(date_str)
        seen.add(date_str)
    return normalized


def _parse_float(value: str) -> Optional[float]:
    try:
        stripped = value.strip()
    except AttributeError:
        return None
    if stripped == "":
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def _parse_volume(value: str) -> Optional[int]:
    try:
        stripped = value.strip()
    except AttributeError:
        return None
    if stripped == "":
        return None
    try:
        return int(float(stripped))
    except ValueError:
        return None


def parse_stooq_daily_csv_to_rows(
    *,
    csv_text: str,
    ticker: str,
    market: Optional[str],
    missing_dates: Sequence[object],
) -> List[StockOhlcvRow]:
    if not csv_text:
        return []

    normalized_missing_dates = set(_normalize_missing_dates(missing_dates))
    if not normalized_missing_dates:
        return []

    stripped_csv = csv_text.strip()
    if not stripped_csv or stripped_csv.lower().startswith("no data"):
        return []

    rows: List[StockOhlcvRow] = []
    accepted_dates = set()
    reader = csv.DictReader(io.StringIO(stripped_csv))

    for csv_row in reader:
        date_value = (csv_row.get("Date") or "").strip()
        if not date_value or date_value not in normalized_missing_dates:
            continue
        if date_value in accepted_dates:
            continue

        open_value = _parse_float(csv_row.get("Open", ""))
        high_value = _parse_float(csv_row.get("High", ""))
        low_value = _parse_float(csv_row.get("Low", ""))
        close_value = _parse_float(csv_row.get("Close", ""))
        if None in (open_value, high_value, low_value, close_value):
            continue

        rows.append(
            StockOhlcvRow(
                ticker=ticker,
                date=date_value,
                open=open_value,
                high=high_value,
                low=low_value,
                close=close_value,
                volume=_parse_volume(csv_row.get("Volume", "")),
                market=(market or "usa"),
            )
        )
        accepted_dates.add(date_value)

    return rows


def _default_http_get(url: str) -> str:
    with urlopen(url) as response:
        return response.read().decode("utf-8")


def recover_missing_ohlcv_rows_from_stooq(
    ticker: str,
    market: Optional[str],
    missing_dates: Sequence[object],
    *,
    http_get: Optional[Callable[[str], str]] = None,
) -> Sequence[StockOhlcvRow]:
    symbol = map_ticker_to_stooq_symbol(ticker)
    if symbol is None:
        return []

    normalized_missing_dates = _normalize_missing_dates(missing_dates)
    if not normalized_missing_dates:
        return []

    fetch_text = http_get or _default_http_get
    csv_text = fetch_text(build_stooq_daily_url(symbol))
    return parse_stooq_daily_csv_to_rows(
        csv_text=csv_text,
        ticker=ticker,
        market=market,
        missing_dates=normalized_missing_dates,
    )
