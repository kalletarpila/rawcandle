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
    progress_callback=None,
):
    """
    Suorittaa valittujen kynttiläkuvioiden analyysin annetulle tickerille ja aikavälille.
    Palauttaa tulokset dict-muodossa: {päivä: [löydetyt_kuviot]}
    """
    import sqlite3
    # setup logger
    try:
        from .logger import setup_logger
        logger = setup_logger()
    except Exception:
        logger = None
    # Prepare date parameters: accept None, str (YYYY-MM-DD) or date/datetime
    def _to_iso(d):
        import datetime as _dt
        if d is None:
            return None
        if isinstance(d, str):
            return d
        if isinstance(d, _dt.date):
            return d.isoformat()
        if isinstance(d, _dt.datetime):
            return d.date().isoformat()
        raise ValueError('start_date/end_date must be str or date/datetime')

    s_iso = _to_iso(start_date)
    e_iso = _to_iso(end_date)

    # Lue data tietokannasta, rakenna SQL dynaamisesti
    with sqlite3.connect(db_path) as conn:
        query = "SELECT pvm, open, high, low, close, volume FROM osakedata WHERE osake = ?"
        params = [ticker]
        if s_iso and e_iso:
            query += " AND pvm >= ? AND pvm <= ?"
            params += [s_iso, e_iso]
        elif s_iso:
            query += " AND pvm >= ?"
            params += [s_iso]
        elif e_iso:
            query += " AND pvm <= ?"
            params += [e_iso]
        df = pd.read_sql_query(query, conn, params=params)
        # Normalize column names to match what the pattern detectors expect.
        # Some databases use lowercase column names (open, high, low, close, volume).
        # The candlestick pattern functions expect 'Open','High','Low','Close','Volume'.
        df.rename(
            columns={
                'open': 'Open',
                'high': 'High',
                'low': 'Low',
                'close': 'Close',
                'volume': 'Volume',
            },
            inplace=True,
        )
        if df.empty:
            return {}
        # Ensure pvm is datetime for correct sorting and comparisons
        df['pvm'] = pd.to_datetime(df['pvm'])
        df = df.sort_values('pvm').reset_index(drop=True)
    results = {}
    total = len(df)
    for i, row in df.iterrows():
        found = []
        # Check each pattern and log the result per pattern
        if "Hammer" in patterns:
            ok = is_hammer(row)
            if ok:
                found.append("Hammer")
                if logger:
                    logger.info(f"{ticker} {row['pvm'].date().isoformat()} Hammer checked - FOUND")
        if i > 0 and "Bullish Engulfing" in patterns:
            ok = is_bullish_engulfing(df.iloc[i-1], row)
            if ok:
                found.append("Bullish Engulfing")
                if logger:
                    logger.info(f"{ticker} {row['pvm'].date().isoformat()} Bullish Engulfing checked - FOUND")
        if i > 0 and "Piercing Pattern" in patterns:
            ok = is_piercing_pattern(df.iloc[i-1], row)
            if ok:
                found.append("Piercing Pattern")
                if logger:
                    logger.info(f"{ticker} {row['pvm'].date().isoformat()} Piercing Pattern checked - FOUND")
        if i >= 2 and "Three White Soldiers" in patterns:
            ok = is_three_white_soldiers(df, i)
            if ok:
                found.append("Three White Soldiers")
                if logger:
                    logger.info(f"{ticker} {row['pvm'].date().isoformat()} Three White Soldiers checked - FOUND")
        if i >= 2 and "Morning Star" in patterns:
            ok = is_morning_star(df, i)
            if ok:
                found.append("Morning Star")
                if logger:
                    logger.info(f"{ticker} {row['pvm'].date().isoformat()} Morning Star checked - FOUND")
        if "Dragonfly Doji" in patterns:
            ok = is_dragonfly_doji(row)
            if ok:
                found.append("Dragonfly Doji")
                if logger:
                    logger.info(f"{ticker} {row['pvm'].date().isoformat()} Dragonfly Doji checked - FOUND")
        if found:
            # store date as ISO string YYYY-MM-DD for consistency with other outputs
            results[row['pvm'].date().isoformat()] = found
        # Call progress callback with fraction (0.0-1.0)
        if progress_callback is not None and total > 0:
            try:
                progress_callback((i + 1) / total)
            except Exception:
                # Don't let callbacks break analysis
                pass
    return results
