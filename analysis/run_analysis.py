from pathlib import Path

import pandas as pd

from .candlestick_patterns import (
    calculate_rsi,
    is_bearish_divergence,
    is_bullish_divergence,
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
    downtrend_filter: bool = False,
    min_decline_percent: float = 3.0,
    use_ma_filter: bool = True,
    use_volume_filter: bool = False,
):
    """
    Suorittaa valittujen kynttiläkuvioiden analyysin annetulle tickerille ja aikavälille.
    Palauttaa tulokset dict-muodossa: {päivä: [löydetyt_kuviot]}

    Args:
        db_path: Polku osakedata-tietokantaan
        ticker: Osakkeen tunniste
        patterns: Lista analysoitavista kuvioista
        start_date: Alkupäivämäärä (valinnainen)
        end_date: Loppupäivämäärä (valinnainen)
        progress_callback: Edistymisen seurantafunktio (valinnainen)
        downtrend_filter: Jos True, suodatetaan vain laskutrendien kynttilät
        min_decline_percent: Minimalasku prosentteina (oletuksena 3.0)
        use_ma_filter: Käytetäänkö liukuvan keskiarvon suodatinta (oletuksena True)
        use_volume_filter: Käytetäänkö volyymi-suodatinta (oletuksena False)
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
            if logger:
                logger.warning(
                    f"Ei dataa tickerille: {ticker} (aikaväli: {s_iso or 'alku'} - {e_iso or 'loppu'})"
                )
            return {}
        # Ensure pvm is datetime for correct sorting and comparisons
        df["pvm"] = pd.to_datetime(df["pvm"])
        df = df.sort_values("pvm").reset_index(drop=True)

    # Laske RSI jos divergenssejä tarkistetaan
    if "Bullish Divergence" in patterns or "Bearish Divergence" in patterns:
        df = calculate_rsi(df, period=14, close_col="Close")
        df = df.sort_values("pvm").reset_index(drop=True)

    # Lisää apufunktiot downtrend-tarkistukseen
    from statistics import mean

    def _calculate_moving_average_local(df_local, ccol, idx, days):
        """Laskee liukuvan keskiarvon"""
        try:
            if idx - days + 1 < 0:
                return None
            subset = df_local.iloc[idx - days + 1 : idx + 1]
            values = [
                float(row[ccol]) for _, row in subset.iterrows() if pd.notna(row[ccol])
            ]
            if len(values) != days:
                return None
            return mean(values)
        except Exception:
            return None

    def _is_in_downtrend_local(df_local, ccol, vcol, idx):
        """Tarkistaa onko kynttilä laskutrendissä"""
        try:
            if idx < 10:
                return False

            def safe_get(row_idx, col):
                if row_idx < 0 or row_idx >= len(df_local):
                    return None
                try:
                    val = df_local.iloc[row_idx][col]
                    return float(val) if pd.notna(val) else None
                except Exception:
                    return None

            # 1. Porrastava lasku
            t0 = safe_get(idx, ccol)
            t_2 = safe_get(idx - 2, ccol)
            t_5 = safe_get(idx - 5, ccol)
            t_10 = safe_get(idx - 10, ccol)

            if not all([t0, t_2, t_5, t_10]):
                return False

            if not (t_10 > t_5 > t_2 > t0):
                return False

            # 2. Minimalasku
            decline_percent = ((t_10 - t0) / t_10) * 100
            if decline_percent < min_decline_percent:
                return False

            # 3. MA-suodatin
            if use_ma_filter:
                ma5 = _calculate_moving_average_local(df_local, ccol, idx, 5)
                ma10 = _calculate_moving_average_local(df_local, ccol, idx, 10)

                if ma5 is None or ma10 is None:
                    return False

                if not (t0 < ma10 and ma5 < ma10):
                    return False

            # 4. Volyymi-suodatin
            if use_volume_filter:
                try:
                    recent_volumes = []
                    for i_vol in range(max(0, idx - 4), idx + 1):
                        vol = safe_get(i_vol, vcol)
                        if vol and vol > 0:
                            recent_volumes.append(vol)

                    historical_volumes = []
                    for i_vol in range(max(0, idx - 25), max(0, idx - 4)):
                        vol = safe_get(i_vol, vcol)
                        if vol and vol > 0:
                            historical_volumes.append(vol)

                    if not recent_volumes or not historical_volumes:
                        return False

                    recent_avg = mean(recent_volumes)
                    historical_avg = mean(historical_volumes)

                    if recent_avg < 1.2 * historical_avg:
                        return False
                except Exception:
                    pass

            return True
        except Exception:
            return False

    results = {}
    total = len(df)
    for i, row in df.iterrows():
        # Downtrend-suodatus
        if downtrend_filter:
            if not _is_in_downtrend_local(df, "Close", "Volume", i):
                continue  # Ohita kynttilät jotka eivät ole laskutrendissä

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
                found.append({"pattern": "Bullish Engulfing", "strength": strength})
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
                found.append({"pattern": "Three White Soldiers", "strength": strength})
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

        # Divergenssit - tarkista vain jos RSI on laskettu
        if "Bullish Divergence" in patterns and "RSI" in df.columns:
            divergence_result = is_bullish_divergence(
                df, i, lookback_days=30, min_rsi_gain=3.0, min_days_between=3
            )
            if divergence_result and divergence_result.get("found"):
                found.append(
                    {
                        "pattern": "Bullish Divergence",
                        "strength": divergence_result["strength"],
                    }
                )
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bullish Divergence checked - FOUND "
                        f"(strength {divergence_result['strength']}, price: {divergence_result['price_change']}%, "
                        f"RSI: +{divergence_result['rsi_change']})"
                    )

        if "Bearish Divergence" in patterns and "RSI" in df.columns:
            divergence_result = is_bearish_divergence(
                df, i, lookback_days=30, min_rsi_drop=3.0, min_days_between=3
            )
            if divergence_result and divergence_result.get("found"):
                found.append(
                    {
                        "pattern": "Bearish Divergence",
                        "strength": divergence_result["strength"],
                    }
                )
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bearish Divergence checked - FOUND "
                        f"(strength {divergence_result['strength']}, price: +{divergence_result['price_change']}%, "
                        f"RSI: {divergence_result['rsi_change']})"
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
