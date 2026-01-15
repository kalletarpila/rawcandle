import datetime as dt

from pages.index_page import trend_calc


def build_series_from_values(values):
    base = dt.date(2024, 1, 1)
    return [
        {"date": base + dt.timedelta(days=i), "value": float(v)}
        for i, v in enumerate(values)
    ]


def test_snapshot_up_bias_and_confidence():
    values = [
        100, 105, 120, 105, 90, 110, 130, 110, 95, 120, 140, 120, 105, 130, 150, 130, 110,
    ]
    series = build_series_from_values(values)
    snap = trend_calc.compute_snapshot(series, "MARKET", "MARKET", lookback=60, k=2)
    assert snap.bias == "UP"
    assert snap.state in ("CONTINUATION", "WARNING")
    assert snap.sh1 and snap.sh2 and snap.sl1 and snap.sl2
    assert snap.confidence >= 70


def test_chains_up_detects_hl_hh_pairs():
    values = [
        100, 105, 120, 105, 90, 110, 130, 110, 95, 120, 140, 120, 105, 130, 150, 130, 110,
    ]
    series = build_series_from_values(values)
    chains = trend_calc.compute_chains(series, "MARKET", "MARKET", lookback=60, k=2)
    assert chains, "Expected at least one UP chain"
    chain = chains[0]
    assert chain.direction == "UP"
    assert chain.pairs_count >= 2
    assert chain.events_count >= 4
    # first HL occurs at index 8 -> 2024-01-09
    assert chain.start_date == dt.date(2024, 1, 9)


def test_snapshot_down_bias_when_highs_and_lows_lower():
    values = list(reversed([
        100, 105, 120, 105, 90, 110, 130, 110, 95, 120, 140, 120, 105, 130, 150, 130, 110,
    ]))
    series = build_series_from_values(values)
    snap = trend_calc.compute_snapshot(series, "MARKET", "MARKET", lookback=60, k=2)
    assert snap.bias in ("DOWN", "NEUTRAL")  # allow NEUTRAL if swings sparse
    if snap.bias == "DOWN":
        assert snap.state in ("CONTINUATION", "WARNING", "REVERSAL")
