import pandas as pd

def is_hammer(row):
    open_ = row['Open']
    close = row['Close']
    high = row['High']
    low = row['Low']
    body = abs(close - open_)
    lower_shadow = min(open_, close) - low
    upper_shadow = high - max(open_, close)
    return (
        body < (high - low) * 0.4 and
        lower_shadow > body * 2 and
        upper_shadow < body
    )

def is_bullish_engulfing(prev_row, row):
    return (
        prev_row['Close'] < prev_row['Open'] and
        row['Close'] > row['Open'] and
        row['Open'] < prev_row['Close'] and
        row['Close'] > prev_row['Open']
    )

def is_piercing_pattern(prev_row, row):
    return (
        prev_row['Close'] < prev_row['Open'] and
        row['Open'] < prev_row['Close'] and
        row['Close'] > (prev_row['Open'] + prev_row['Close']) / 2 and
        row['Close'] < prev_row['Open']
    )

def is_three_white_soldiers(df, idx):
    if idx < 2:
        return False
    r1, r2, r3 = df.iloc[idx-2], df.iloc[idx-1], df.iloc[idx]
    return (
        all(r['Close'] > r['Open'] for r in [r1, r2, r3]) and
        r2['Open'] > r1['Open'] and r2['Close'] > r1['Close'] and
        r3['Open'] > r2['Open'] and r3['Close'] > r2['Close']
    )

def is_morning_star(df, idx):
    if idx < 2:
        return False
    r1, r2, r3 = df.iloc[idx-2], df.iloc[idx-1], df.iloc[idx]
    return (
        r1['Close'] < r1['Open'] and
        abs(r2['Close'] - r2['Open']) < (r1['Open'] - r1['Close']) * 0.5 and
        r3['Close'] > r3['Open'] and
        r3['Close'] > ((r1['Open'] + r1['Close']) / 2)
    )

def is_dragonfly_doji(row):
    open_ = row['Open']
    close = row['Close']
    high = row['High']
    low = row['Low']
    body = abs(close - open_)
    lower_shadow = min(open_, close) - low
    upper_shadow = high - max(open_, close)
    return (
        body < (high - low) * 0.1 and
        lower_shadow > (high - low) * 0.6 and
        upper_shadow < (high - low) * 0.1
    )
