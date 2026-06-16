from __future__ import annotations

from datetime import date

from services.stooq_fallback_provider import (
    build_stooq_daily_url,
    map_ticker_to_stooq_symbol,
    parse_stooq_daily_csv_to_rows,
    recover_missing_ohlcv_rows_from_stooq,
)


def test_map_ticker_to_stooq_symbol_maps_usa_ticker() -> None:
    assert map_ticker_to_stooq_symbol("AAPL") == "aapl.us"


def test_map_ticker_to_stooq_symbol_rejects_suffix_tickers() -> None:
    assert map_ticker_to_stooq_symbol("NOKIA.HE") is None
    assert map_ticker_to_stooq_symbol("NOBI.ST") is None


def test_build_stooq_daily_url_uses_daily_csv_template() -> None:
    assert build_stooq_daily_url("aapl.us") == "https://stooq.com/q/d/l/?s=aapl.us&i=d"


def test_parse_stooq_daily_csv_returns_only_requested_day() -> None:
    csv_text = """Date,Open,High,Low,Close,Volume
2026-06-14,190,191,189,190.5,1000
2026-06-15,195,198,194,197.5,123456
2026-06-16,198,199,196,198.5,654321
"""

    rows = parse_stooq_daily_csv_to_rows(
        csv_text=csv_text,
        ticker="AAPL",
        market="usa",
        missing_dates=["2026-06-15"],
    )

    assert len(rows) == 1
    assert rows[0].ticker == "AAPL"
    assert rows[0].date == "2026-06-15"
    assert rows[0].open == 195.0
    assert rows[0].high == 198.0
    assert rows[0].low == 194.0
    assert rows[0].close == 197.5
    assert rows[0].volume == 123456


def test_parse_stooq_daily_csv_ignores_extra_days() -> None:
    csv_text = """Date,Open,High,Low,Close,Volume
2026-06-14,190,191,189,190.5,1000
2026-06-15,195,198,194,197.5,123456
"""

    rows = parse_stooq_daily_csv_to_rows(
        csv_text=csv_text,
        ticker="AAPL",
        market="usa",
        missing_dates=["2026-06-14"],
    )

    assert [row.date for row in rows] == ["2026-06-14"]


def test_parse_stooq_daily_csv_skips_incomplete_ohlc_row() -> None:
    csv_text = """Date,Open,High,Low,Close,Volume
2026-06-15,195,198,194,,123456
"""

    rows = parse_stooq_daily_csv_to_rows(
        csv_text=csv_text,
        ticker="AAPL",
        market="usa",
        missing_dates=["2026-06-15"],
    )

    assert rows == []


def test_parse_stooq_daily_csv_allows_missing_volume() -> None:
    csv_text = """Date,Open,High,Low,Close,Volume
2026-06-15,195,198,194,197.5,
"""

    rows = parse_stooq_daily_csv_to_rows(
        csv_text=csv_text,
        ticker="AAPL",
        market="usa",
        missing_dates=["2026-06-15"],
    )

    assert len(rows) == 1
    assert rows[0].volume is None


def test_parse_stooq_daily_csv_handles_no_data_response() -> None:
    rows = parse_stooq_daily_csv_to_rows(
        csv_text="No data",
        ticker="AAPL",
        market="usa",
        missing_dates=["2026-06-15"],
    )

    assert rows == []


def test_recover_missing_ohlcv_rows_from_stooq_uses_injected_http_get() -> None:
    calls = []

    def fake_http_get(url: str) -> str:
        calls.append(url)
        return """Date,Open,High,Low,Close,Volume
2026-06-15,195,198,194,197.5,123456
"""

    rows = recover_missing_ohlcv_rows_from_stooq(
        "AAPL",
        "usa",
        [date(2026, 6, 15)],
        http_get=fake_http_get,
    )

    assert calls == ["https://stooq.com/q/d/l/?s=aapl.us&i=d"]
    assert len(rows) == 1
    assert rows[0].date == "2026-06-15"


def test_recover_missing_ohlcv_rows_from_stooq_rejects_unsupported_ticker_without_fetch() -> None:
    def fake_http_get(url: str) -> str:
        raise AssertionError("http_get should not be called")

    rows = recover_missing_ohlcv_rows_from_stooq(
        "NOKIA.HE",
        "omxh",
        ["2026-06-15"],
        http_get=fake_http_get,
    )

    assert rows == []
