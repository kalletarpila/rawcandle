from pathlib import Path

import pandas as pd

from .candlestick_patterns import (
    is_bullish_engulfing,
    is_dragonfly_doji,
    is_hammer,
    is_morning_star,
    is_piercing_pattern,
    is_three_white_soldiers,
)


def _calculate_signal_strength(
    pattern: str,
    open_price: float,
    high: float,
    low: float,
    close: float,
    volume: int = None,
) -> float:
    """Peilaa analysis.analyzer.Analyzer.calculate_signal_strength -logiikkaa."""
    if high == low:
        return 0.0

    total_range = high - low
    body_size = abs(close - open_price)

    base_strength = 0.5

    if pattern == "Doji":
        if total_range > 0:
            base_strength = 1.0 - (body_size / total_range)
    elif pattern == "Hammer":
        body_bottom = min(open_price, close)
        lower_shadow = body_bottom - low
        if body_size > 0:
            shadow_to_body_ratio = lower_shadow / body_size
            base_strength = min(0.9, shadow_to_body_ratio / 3.0)
    elif pattern == "Shooting Star":
        body_top = max(open_price, close)
        upper_shadow = high - body_top
        if body_size > 0:
            shadow_to_body_ratio = upper_shadow / body_size
            base_strength = min(0.9, shadow_to_body_ratio / 3.0)
    elif pattern == "Engulfing":
        base_strength = 0.8

    if volume and volume > 100000:
        base_strength = min(1.0, base_strength * 1.1)

    return round(max(0.0, min(1.0, base_strength)), 3)


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
        raise ValueError("start_date/end_date must be str or date/datetime")

    s_iso = _to_iso(start_date)
    e_iso = _to_iso(end_date)

    # Lue data tietokannasta, rakenna SQL dynaamisesti
    with sqlite3.connect(db_path) as conn:
        query = (
            "SELECT pvm, open, high, low, close, volume FROM osakedata WHERE osake = ?"
        )
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
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "volume": "Volume",
            },
            inplace=True,
        )
        if df.empty:
            return {}
        # Ensure pvm is datetime for correct sorting and comparisons
        df["pvm"] = pd.to_datetime(df["pvm"])
        df = df.sort_values("pvm").reset_index(drop=True)
    results = {}
    total = len(df)
    for i, row in df.iterrows():
        found = []
        # Check each pattern and log the result per pattern
        if "Hammer" in patterns and is_hammer(row):
            strength = _calculate_signal_strength(
                "Hammer",
                row["Open"],
                row["High"],
                row["Low"],
                row["Close"],
                row.get("Volume"),
            )
            found.append({"pattern": "Hammer", "strength": strength})
            if logger:
                logger.info(
                    f"{ticker} {row['pvm'].date().isoformat()} Hammer checked - FOUND (strength {strength})"
                )

        if i > 0 and "Bullish Engulfing" in patterns:
            prev_row = df.iloc[i - 1]
            ok = is_bullish_engulfing(prev_row, row)
            if ok:
                strength = _calculate_signal_strength(
                    "Engulfing",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append(
                    {"pattern": "Bullish Engulfing", "strength": strength}
                )
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bullish Engulfing checked - FOUND (strength {strength})"
                    )

        if i > 0 and "Piercing Pattern" in patterns:
            prev_row = df.iloc[i - 1]
            if is_piercing_pattern(prev_row, row):
                strength = _calculate_signal_strength(
                    "Piercing Pattern",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Piercing Pattern", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Piercing Pattern checked - FOUND (strength {strength})"
                    )

        if i >= 2 and "Three White Soldiers" in patterns:
            if is_three_white_soldiers(df, i):
                strength = _calculate_signal_strength(
                    "Three White Soldiers",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append(
                    {"pattern": "Three White Soldiers", "strength": strength}
                )
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Three White Soldiers checked - FOUND (strength {strength})"
                    )

        if i >= 2 and "Morning Star" in patterns:
            if is_morning_star(df, i):
                strength = _calculate_signal_strength(
                    "Morning Star",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Morning Star", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Morning Star checked - FOUND (strength {strength})"
                    )

        if "Dragonfly Doji" in patterns and is_dragonfly_doji(row):
            strength = _calculate_signal_strength(
                "Doji",
                row["Open"],
                row["High"],
                row["Low"],
                row["Close"],
                row.get("Volume"),
            )
            found.append({"pattern": "Dragonfly Doji", "strength": strength})
            if logger:
                logger.info(
                    f"{ticker} {row['pvm'].date().isoformat()} Dragonfly Doji checked - FOUND (strength {strength})"
                )
        if found:
            key = f"{ticker}|{row['pvm'].date().isoformat()}"
            bucket = results.setdefault(key, [])
            bucket.extend(found)
        # Call progress callback with fraction (0.0-1.0)
        if progress_callback is not None and total > 0:
            try:
                progress_callback((i + 1) / total)
            except Exception:
                # Don't let callbacks break analysis
                pass
    return results
