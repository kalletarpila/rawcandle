import pandas as pd
from pathlib import Path
from .candlestick_patterns import (
    is_hammer,
    is_bullish_engulfing,
    is_piercing_pattern,
    is_three_white_soldiers,
    is_morning_star,
    is_dragonfly_doji,
)

def run_candlestick_analysis(
    db_path: str,
    ticker: str,
    patterns: list,
    start_date: str = None,
    end_date: str = None,
):
    """
    Suorittaa valittujen kynttiläkuvioiden analyysin annetulle tickerille ja aikavälille.
    Palauttaa tulokset dict-muodossa: {päivä: [löydetyt_kuviot]}
    """
    import sqlite3
    # Lue data tietokannasta
    with sqlite3.connect(db_path) as conn:
        query = "SELECT pvm, open, high, low, close, volume FROM osakedata WHERE osake = ?"
        params = [ticker]
        if start_date and end_date:
            query += " AND pvm >= ? AND pvm <= ?"
            params += [start_date, end_date]
        df = pd.read_sql_query(query, conn, params=params)
    if df.empty:
        return {}
    df = df.sort_values("pvm").reset_index(drop=True)
    results = {}
    for i, row in df.iterrows():
        found = []
        if "Hammer" in patterns and is_hammer(row):
            found.append("Hammer")
        if i > 0 and "Bullish Engulfing" in patterns and is_bullish_engulfing(df.iloc[i-1], row):
            found.append("Bullish Engulfing")
        if i > 0 and "Piercing Pattern" in patterns and is_piercing_pattern(df.iloc[i-1], row):
            found.append("Piercing Pattern")
        if i >= 2 and "Three White Soldiers" in patterns and is_three_white_soldiers(df, i):
            found.append("Three White Soldiers")
        if i >= 2 and "Morning Star" in patterns and is_morning_star(df, i):
            found.append("Morning Star")
        if "Dragonfly Doji" in patterns and is_dragonfly_doji(row):
            found.append("Dragonfly Doji")
        if found:
            results[row['pvm']] = found
    return results
