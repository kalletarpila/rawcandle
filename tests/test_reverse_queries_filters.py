from __future__ import annotations

from reverse import queries


def test_build_universe_query_adds_new_filters():
    params = {
        "market": "usa",
        "bullish_only": True,
        "exclude_blackout": True,
        "exclude_crisis": True,
        "only_candle_days": True,
        "exclude_from_regression_only": True,
        "sector": "tech",
        "rsi_min": 30,
        "rsi_max": 70,
        "vola_min": 0.5,
        "vola_max": 2.0,
        "max_rows": 123,
    }
    sql, sql_params = queries.build_universe_query(params)
    assert "is_candle_day" in sql
    assert "exclude_from_regression" in sql
    assert "sector = ?" in sql
    assert "RSI14_t0 >=" in sql and "RSI14_t0 <=" in sql
    assert "ATR_ratio_14 >=" in sql and "ATR_ratio_14 <=" in sql
    assert "LIMIT" in sql.upper()
    # order of params should follow filter additions
    expected_params = [
        "usa",
        30.0,
        70.0,
        0.5,
        2.0,
        123,
    ]
    for exp in expected_params:
        assert exp in sql_params
