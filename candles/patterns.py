"""
Candlestick pattern analysis logic for RawCandleApp.
Implements pattern detection functions for:
- Hammer
- Bullish Engulfing
- Piercing Pattern
- Three White Soldiers
- Morning Star
- Dragonfly Doji

All functions expect a pandas.DataFrame with columns:
['open', 'high', 'low', 'close'] (case-insensitive)
"""
import pandas as pd

def is_hammer(df: pd.DataFrame) -> pd.Series:
    """Detect Hammer pattern. Returns boolean Series."""
    o, h, l, c = df['open'], df['high'], df['low'], df['close']
    body = (c - o).abs()
    lower_shadow = o - l
    upper_shadow = h - c
    return (
        (body < (h - l) * 0.3) &
        (lower_shadow > body * 2) &
        (upper_shadow < body)
    )

def is_bullish_engulfing(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'], df['high'], df['low'], df['close']
    prev_o, prev_c = o.shift(1), c.shift(1)
    return (
        (prev_c < prev_o) & (c > o) &
        (c > prev_o) & (o < prev_c)
    )

def is_piercing_pattern(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'], df['high'], df['low'], df['close']
    prev_o, prev_c = o.shift(1), c.shift(1)
    midpoint = (prev_o + prev_c) / 2
    return (
        (prev_c < prev_o) & (c > o) &
        (o < prev_c) & (c > midpoint) & (o < prev_c)
    )

def is_three_white_soldiers(df: pd.DataFrame) -> pd.Series:
    o, c = df['open'], df['close']
    cond1 = (c > o)
    cond2 = cond1 & cond1.shift(1) & cond1.shift(2)
    return cond2

def is_morning_star(df: pd.DataFrame) -> pd.Series:
    o, c = df['open'], df['close']
    prev_o, prev_c = o.shift(1), c.shift(1)
    prev2_o, prev2_c = o.shift(2), c.shift(2)
    return (
        (prev2_c < prev2_o) &
        (abs(prev_c - prev_o) < (prev2_o - prev2_c) * 0.3) &
        (c > ((prev2_o + prev2_c) / 2))
    )

def is_dragonfly_doji(df: pd.DataFrame) -> pd.Series:
    o, h, l, c = df['open'], df['high'], df['low'], df['close']
    body = (c - o).abs()
    return (
        (body < (h - l) * 0.1) &
        ((h - l) > 0) &
        ((o - l) > (h - l) * 0.6) &
        ((h - c) < (h - l) * 0.2)
    )
