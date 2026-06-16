from __future__ import annotations

from datetime import date
from urllib.error import HTTPError

from services.polygon_massive_grouped_daily_provider import (
    build_polygon_massive_grouped_daily_url,
    fetch_polygon_massive_grouped_daily_ohlcv_by_ticker,
    parse_polygon_massive_grouped_daily_snapshot,
)


def test_build_polygon_massive_grouped_daily_url_includes_expected_parts() -> None:
    url = build_polygon_massive_grouped_daily_url(
        date(2026, 6, 15),
        api_key="abc 123",
    )

    assert "/v2/aggs/grouped/locale/us/market/stocks/2026-06-15" in url
    assert "adjusted=true" in url
    assert "apiKey=abc%20123" in url


def test_fetch_uses_explicit_api_key_over_environment(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("POLYGON_API_KEY", "env-key")

    def fake_http_get(url: str) -> str:
        calls.append(url)
        return '{"status":"OK","results":[{"T":"AAPL","o":1,"h":2,"l":0.5,"c":1.5,"v":10,"t":1781481600000}]}'

    rows = fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
        "usa",
        date(2026, 6, 15),
        api_key="param-key",
        http_get=fake_http_get,
    )

    assert "apiKey=param-key" in calls[0]
    assert list(rows) == ["AAPL"]


def test_fetch_reads_polygon_api_key_from_environment(monkeypatch) -> None:
    calls = []
    monkeypatch.setenv("POLYGON_API_KEY", "polygon-key")
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    def fake_http_get(url: str) -> str:
        calls.append(url)
        return '{"status":"OK","results":[]}'

    rows = fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
        "usa",
        date(2026, 6, 15),
        http_get=fake_http_get,
    )

    assert rows == {}
    assert "apiKey=polygon-key" in calls[0]


def test_fetch_reads_massive_api_key_as_fallback(monkeypatch) -> None:
    calls = []
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.setenv("MASSIVE_API_KEY", "massive-key")

    def fake_http_get(url: str) -> str:
        calls.append(url)
        return '{"status":"OK","results":[]}'

    rows = fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
        "usa",
        date(2026, 6, 15),
        http_get=fake_http_get,
    )

    assert rows == {}
    assert "apiKey=massive-key" in calls[0]


def test_fetch_returns_empty_without_api_key_and_skips_http(monkeypatch) -> None:
    monkeypatch.delenv("POLYGON_API_KEY", raising=False)
    monkeypatch.delenv("MASSIVE_API_KEY", raising=False)

    def fake_http_get(url: str) -> str:
        raise AssertionError("http_get should not be called")

    rows = fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
        "usa",
        date(2026, 6, 15),
        http_get=fake_http_get,
    )

    assert rows == {}


def test_fetch_returns_empty_for_unsupported_market_without_fetch(monkeypatch) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "polygon-key")

    def fake_http_get(url: str) -> str:
        raise AssertionError("http_get should not be called")

    rows = fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
        "omxh",
        date(2026, 6, 15),
        http_get=fake_http_get,
    )

    assert rows == {}


def test_parser_returns_ticker_mapping() -> None:
    payload = """
    {
      "status": "OK",
      "results": [
        {"T": "AAPL", "o": 294.12, "h": 297.78, "l": 291.7, "c": 296.42, "v": 45732573.320234, "t": 1781481600000},
        {"T": "MSFT", "o": 396.795, "h": 401.75, "l": 392.845, "c": 399.76, "v": 32266437.464578, "t": 1781481600000}
      ]
    }
    """

    rows = parse_polygon_massive_grouped_daily_snapshot(
        payload_text=payload,
        market="usa",
        target_date=date(2026, 6, 15),
    )

    assert set(rows) == {"AAPL", "MSFT"}
    assert rows["AAPL"].date == "2026-06-15"
    assert rows["AAPL"].open == 294.12
    assert rows["AAPL"].high == 297.78
    assert rows["AAPL"].low == 291.7
    assert rows["AAPL"].close == 296.42
    assert rows["AAPL"].volume == 45732573
    assert rows["AAPL"].market == "usa"


def test_decimal_volume_is_normalized_to_int() -> None:
    payload = """
    {
      "status": "OK",
      "results": [
        {"T": "AAPL", "o": 294.12, "h": 297.78, "l": 291.7, "c": 296.42, "v": 45732573.320234, "t": 1781481600000}
      ]
    }
    """

    rows = parse_polygon_massive_grouped_daily_snapshot(
        payload_text=payload,
        market="usa",
        target_date=date(2026, 6, 15),
    )

    assert rows["AAPL"].volume == 45732573


def test_parser_allows_missing_volume_when_ohlc_is_complete() -> None:
    payload = """
    {
      "status": "OK",
      "results": [
        {"T": "AAPL", "o": 294.12, "h": 297.78, "l": 291.7, "c": 296.42, "t": 1781481600000}
      ]
    }
    """

    rows = parse_polygon_massive_grouped_daily_snapshot(
        payload_text=payload,
        market="usa",
        target_date=date(2026, 6, 15),
    )

    assert rows["AAPL"].volume is None


def test_parser_skips_incomplete_ohlc_row() -> None:
    payload = """
    {
      "status": "OK",
      "results": [
        {"T": "AAPL", "o": 294.12, "h": 297.78, "l": 291.7, "t": 1781481600000}
      ]
    }
    """

    rows = parse_polygon_massive_grouped_daily_snapshot(
        payload_text=payload,
        market="usa",
        target_date=date(2026, 6, 15),
    )

    assert rows == {}


def test_parser_skips_non_numeric_ohlc_row() -> None:
    payload = """
    {
      "status": "OK",
      "results": [
        {"T": "AAPL", "o": "bad", "h": 297.78, "l": 291.7, "c": 296.42, "t": 1781481600000}
      ]
    }
    """

    rows = parse_polygon_massive_grouped_daily_snapshot(
        payload_text=payload,
        market="usa",
        target_date=date(2026, 6, 15),
    )

    assert rows == {}


def test_parser_returns_empty_on_status_error() -> None:
    rows = parse_polygon_massive_grouped_daily_snapshot(
        payload_text='{"status":"ERROR","results":[{"T":"AAPL"}]}',
        market="usa",
        target_date=date(2026, 6, 15),
    )

    assert rows == {}


def test_fetch_returns_empty_on_http_429(monkeypatch) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "polygon-key")

    def fake_http_get(url: str) -> str:
        raise HTTPError(url, 429, "Too Many Requests", hdrs=None, fp=None)

    rows = fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
        "usa",
        date(2026, 6, 15),
        http_get=fake_http_get,
    )

    assert rows == {}


def test_fetch_returns_empty_on_non_json_response(monkeypatch) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "polygon-key")

    rows = fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
        "usa",
        date(2026, 6, 15),
        http_get=lambda url: "<html>not json</html>",
    )

    assert rows == {}


def test_single_bad_row_does_not_break_snapshot() -> None:
    payload = """
    {
      "status": "OK",
      "results": [
        {"T": "AAPL", "o": 294.12, "h": 297.78, "l": 291.7, "c": 296.42, "v": 45732573.320234, "t": 1781481600000},
        {"T": "BAD", "o": 1, "h": 2, "l": 0.5, "c": null, "v": 10, "t": 1781481600000}
      ]
    }
    """

    rows = parse_polygon_massive_grouped_daily_snapshot(
        payload_text=payload,
        market="usa",
        target_date=date(2026, 6, 15),
    )

    assert set(rows) == {"AAPL"}


def test_fetch_uses_injected_http_get(monkeypatch) -> None:
    monkeypatch.setenv("POLYGON_API_KEY", "polygon-key")
    calls = []

    def fake_http_get(url: str) -> str:
        calls.append(url)
        return '{"status":"OK","results":[{"T":"AAPL","o":1,"h":2,"l":0.5,"c":1.5,"v":10,"t":1781481600000}]}'

    rows = fetch_polygon_massive_grouped_daily_ohlcv_by_ticker(
        "usa",
        date(2026, 6, 15),
        http_get=fake_http_get,
    )

    assert len(calls) == 1
    assert list(rows) == ["AAPL"]
