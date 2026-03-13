import pandas as pd
import pytest
from statistics import mean

# Kopioidaan safe_get testin sisään, koska sitä ei voi tuoda generate_results.py:stä


def safe_get(row, col):
    try:
        return row[col]
    except Exception:
        return None


# Luo testidata, jossa on 210 päivää, jotta 200 päivän liukuva voidaan laskea


def make_test_df():
    data = {
        "pvm": pd.date_range("2024-01-01", periods=210, freq="D").strftime("%Y-%m-%d"),
        "close": [100 + i for i in range(210)],
        "low": [99 + i for i in range(210)],
    }
    return pd.DataFrame(data)


def test_calc_ma_normalized_spec_idx():
    df = make_test_df()
    # Oletetaan, että t0 on 2024-07-28 (viimeinen päivä datassa)
    t0_pvm = "2024-07-28"
    t0_idx = df.index[df["pvm"] == t0_pvm][0]
    ccol = "close"
    lcol = "low"
    r0 = df.iloc[t0_idx]

    # Kopioidaan funktio testin sisään, koska se on generate_results.py:n sisällä
    def calc_ma_normalized_spec_idx(idx, days_offset, ma_period):
        end_idx = idx + days_offset
        start_idx = end_idx - ma_period + 1
        if start_idx < 0 or end_idx < 0 or end_idx >= len(df):
            return None
        subset = df.iloc[start_idx : end_idx + 1]
        values = [safe_get(row, ccol) for _, row in subset.iterrows()]
        values = [v for v in values if v is not None]
        if len(values) != ma_period:
            return None
        ma_val = mean(values)
        t0_low = safe_get(r0, lcol)
        return (ma_val / t0_low * 100) if t0_low and t0_low > 0 else None

    # Lasketaan 200 päivän liukuva t0:n kohdalta (offset=0, period=200)
    result = calc_ma_normalized_spec_idx(t0_idx, 0, 200)
    # Manuaalinen tarkistus: close-arvot 10...209, low t0=99+199=298
    expected_ma = mean([100 + i for i in range(10, 210)])
    expected_low = 99 + t0_idx
    expected = expected_ma / expected_low * 100
    assert abs(result - expected) < 1e-6, f"Expected {expected}, got {result}"
