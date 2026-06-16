from __future__ import annotations

import csv
import io
from datetime import date
from typing import Callable, List, Optional, Sequence
from urllib.request import Request, urlopen

from services.stock_update_service import StockOhlcvRow

DEFAULT_STOOQ_BASE_URL = "https://stooq.com"
STOOQ_DAILY_URL_TEMPLATE = "{base_url}/q/d/l/?s={symbol}&d1={start_date}&d2={end_date}&i=d"


def map_ticker_to_stooq_symbol(ticker: str) -> Optional[str]:
    normalized = (ticker or "").strip()
    if not normalized or "." in normalized:
        return None
    return f"{normalized.lower()}.us"


def _format_stooq_date_param(value: object) -> str:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    return str(value).strip().replace("-", "")


def build_stooq_daily_csv_url(
    symbol: str,
    start_date: object,
    end_date: object,
    *,
    base_url: str = DEFAULT_STOOQ_BASE_URL,
) -> str:
    return STOOQ_DAILY_URL_TEMPLATE.format(
        base_url=base_url.rstrip("/"),
        symbol=symbol,
        start_date=_format_stooq_date_param(start_date),
        end_date=_format_stooq_date_param(end_date),
    )


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
    lower_csv = stripped_csv.lower()
    if (
        not stripped_csv
        or lower_csv.startswith("no data")
        or lower_csv.startswith("<!doctype html")
        or lower_csv.startswith("<html")
        or "browser verification" in lower_csv
        or "requires javascript" in lower_csv
    ):
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
    request = Request(url, headers={"User-Agent": "RawCandle/1.0"})
    with urlopen(request) as response:
        return response.read().decode("utf-8")


def recover_missing_ohlcv_rows_from_stooq(
    ticker: str,
    market: Optional[str],
    missing_dates: Sequence[object],
    *,
    http_get: Optional[Callable[[str], str]] = None,
    base_url: str = DEFAULT_STOOQ_BASE_URL,
) -> Sequence[StockOhlcvRow]:
    symbol = map_ticker_to_stooq_symbol(ticker)
    if symbol is None:
        return []

    normalized_missing_dates = _normalize_missing_dates(missing_dates)
    if not normalized_missing_dates:
        return []

    start_date = min(normalized_missing_dates)
    end_date = max(normalized_missing_dates)

    fetch_text = http_get or _default_http_get
    csv_text = fetch_text(
        build_stooq_daily_csv_url(
            symbol,
            start_date,
            end_date,
            base_url=base_url,
        )
    )
    return parse_stooq_daily_csv_to_rows(
        csv_text=csv_text,
        ticker=ticker,
        market=market,
        missing_dates=normalized_missing_dates,
    )
