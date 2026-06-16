from __future__ import annotations

import json
import math
import os
from datetime import date, datetime, timezone
from typing import Callable, Mapping, Optional
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

from services.stock_update_service import StockOhlcvRow

DEFAULT_POLYGON_BASE_URL = "https://api.polygon.io"
SUPPORTED_USA_MARKETS = {"usa", "us"}


def build_polygon_massive_grouped_daily_url(
    target_date: date,
    *,
    api_key: str,
    base_url: str = DEFAULT_POLYGON_BASE_URL,
) -> str:
    return (
        f"{base_url.rstrip('/')}/v2/aggs/grouped/locale/us/market/stocks/"
        f"{target_date.isoformat()}?adjusted=true&apiKey={quote(api_key, safe='')}"
    )


def _resolve_api_key(api_key: Optional[str]) -> Optional[str]:
    if api_key:
        return api_key
    for env_name in ("POLYGON_API_KEY", "MASSIVE_API_KEY"):
        value = os.environ.get(env_name)
        if value:
            return value
    return None


def _default_http_get(url: str) -> str:
    request = Request(url, headers={"User-Agent": "RawCandle/1.0"})
    with urlopen(request) as response:
        return response.read().decode("utf-8")


def _parse_numeric_ohlc(value: object) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return numeric


def _normalize_volume(value: object) -> Optional[int]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(numeric):
        return None
    return int(round(numeric))


def _timestamp_matches_target_date(timestamp_ms: object, target_date: date) -> bool:
    if timestamp_ms is None:
        return True
    try:
        timestamp = float(timestamp_ms)
    except (TypeError, ValueError):
        return False
    if math.isnan(timestamp):
        return False
    parsed_date = datetime.fromtimestamp(
        timestamp / 1000.0,
        tz=timezone.utc,
    ).date()
    return parsed_date == target_date


def parse_polygon_massive_grouped_daily_snapshot(
    *,
    payload_text: str,
    market: str,
    target_date: date,
) -> Mapping[str, StockOhlcvRow]:
    if not payload_text:
        return {}

    try:
        payload = json.loads(payload_text)
    except json.JSONDecodeError:
        return {}

    if not isinstance(payload, dict):
        return {}
    if payload.get("status") != "OK":
        return {}

    results = payload.get("results")
    if not isinstance(results, list) or not results:
        return {}

    rows_by_ticker: dict[str, StockOhlcvRow] = {}
    target_date_str = target_date.isoformat()
    normalized_market = (market or "usa").lower()

    for result in results:
        if not isinstance(result, dict):
            continue
        ticker = str(result.get("T") or "").strip()
        if not ticker:
            continue
        open_value = _parse_numeric_ohlc(result.get("o"))
        high_value = _parse_numeric_ohlc(result.get("h"))
        low_value = _parse_numeric_ohlc(result.get("l"))
        close_value = _parse_numeric_ohlc(result.get("c"))
        if None in (open_value, high_value, low_value, close_value):
            continue
        if not _timestamp_matches_target_date(result.get("t"), target_date):
            continue

        rows_by_ticker[ticker] = StockOhlcvRow(
            ticker=ticker,
            date=target_date_str,
            open=open_value,
            high=high_value,
            low=low_value,
            close=close_value,
            volume=_normalize_volume(result.get("v")),
            market=normalized_market,
        )

    return rows_by_ticker


def fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
    market: str,
    target_date: date,
    *,
    api_key: Optional[str] = None,
    http_get: Optional[Callable[[str], str]] = None,
    base_url: str = DEFAULT_POLYGON_BASE_URL,
) -> Mapping[str, StockOhlcvRow]:
    if (market or "").strip().lower() not in SUPPORTED_USA_MARKETS:
        return {}

    resolved_api_key = _resolve_api_key(api_key)
    if not resolved_api_key:
        return {}

    fetch_text = http_get or _default_http_get
    url = build_polygon_massive_grouped_daily_url(
        target_date,
        api_key=resolved_api_key,
        base_url=base_url,
    )
    try:
        payload_text = fetch_text(url)
    except HTTPError as exc:
        if exc.code in (403, 404, 429):
            return {}
        return {}
    except Exception:
        return {}

    return parse_polygon_massive_grouped_daily_snapshot(
        payload_text=payload_text,
        market=market,
        target_date=target_date,
    )
