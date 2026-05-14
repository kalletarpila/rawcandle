import os
import sqlite3
from pathlib import Path

import pandas as pd

from .candlestick_patterns import (
    is_bearish_engulfing,
    is_bullish_abandoned_baby,
    is_bullish_divergence,
    is_bullish_engulfing,
    is_dark_cloud_cover,
    is_dragonfly_doji,
    is_hammer,
    is_falling_three_methods,
    is_hanging_man,
    is_evening_star,
    is_morning_star,
    is_piercing_pattern,
    is_shooting_star,
    is_three_white_soldiers,
)
from .chart_patterns import (
    is_cup_and_handle,
    is_bear_rectangle,
    is_bearish_pennant,
    is_bearish_flag,
    is_bull_rectangle,
    is_bullish_pennant,
    is_bullish_flag,
    is_ascending_triangle,
    is_descending_triangle,
)
from .divergence_v1 import compute_rsi_wilder


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
    elif pattern == "Hanging Man":
        body_bottom = min(open_price, close)
        lower_shadow = body_bottom - low
        if body_size > 0:
            shadow_to_body_ratio = lower_shadow / body_size
            base_strength = min(0.9, shadow_to_body_ratio / 3.0)
    elif pattern == "Engulfing":
        base_strength = 0.8
    elif pattern == "Dark Cloud Cover":
        body_midpoint = open_price + (close - open_price) * 0.5
        penetration = abs(close - body_midpoint) / total_range
        base_strength = min(0.9, 0.6 + penetration)
    elif pattern == "Evening Star":
        base_strength = 0.8
    elif pattern == "Bullish Abandoned Baby":
        base_strength = 0.85
    elif pattern == "Falling Three Methods":
        base_strength = 0.82
    elif pattern == "Bullish Flag":
        base_strength = 0.81
    elif pattern == "Bearish Flag":
        base_strength = 0.81
    elif pattern == "Bull Rectangle":
        base_strength = 0.79
    elif pattern == "Bear Rectangle":
        base_strength = 0.79
    elif pattern == "Ascending Triangle":
        base_strength = 0.8
    elif pattern == "Descending Triangle":
        base_strength = 0.8
    elif pattern == "Bullish Pennant":
        base_strength = 0.82
    elif pattern == "Bearish Pennant":
        base_strength = 0.82
    elif pattern == "Cup and Handle":
        base_strength = 0.84

    if volume and volume > 100000:
        base_strength = min(1.0, base_strength * 1.1)

    return round(max(0.0, min(1.0, base_strength)), 3)


BASE_CANDLE_ORDER = [
    "Hammer",
    "Bullish Engulfing",
    "Piercing Pattern",
    "Three White Soldiers",
    "Morning Star",
    "Dragonfly Doji",
    "Bullish Abandoned Baby",
    "Bullish Flag",
    "Bull Rectangle",
    "Ascending Triangle",
    "Bullish Pennant",
    "Cup and Handle",
]

COMBO_PATTERN_MAP = {
    "Hammer": "BullDiv & Hammer",
    "Bullish Engulfing": "BullDiv & Bullish Engulfing",
    "Piercing Pattern": "BullDiv & Piercing Pattern",
    "Three White Soldiers": "BullDiv & Three White Soldiers",
    "Morning Star": "BullDiv & Morning Star",
    "Dragonfly Doji": "BullDiv & Dragonfly Doji",
}


def _load_bullish_divergence_dates(ticker: str, analysis_db_path: str) -> set[str]:
    """
    Palauta päivämäärät joille divergence_data-taulu sisältää Bullish Divergence -havaintoja.
    """
    if not ticker or not analysis_db_path:
        return set()

    try:
        db_path = Path(analysis_db_path)
        if not db_path.exists():
            return set()

        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT date
                FROM divergence_data
                WHERE ticker = ?
                  AND COALESCE(bullish_strength, 0) > 0
                """,
                (ticker,),
            )
            return {str(row[0]) for row in cur.fetchall() if row and row[0]}
    except Exception:
        # Jos divergenssidataa ei saada, käsitellään kuin sitä ei olisi
        return set()


def _load_divergence_snapshot(
    ticker: str,
    analysis_db_path: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> tuple[
    dict[str, dict[str, float]],
    dict[str, float | None],
    set[str],
    set[str],
    dict[str, str | None],
    set[str],
    set[str],
    set[str],
]:
    """
    Load divergence strengths and event flags from divergence_data for the candles flow.
    """
    if not ticker or not analysis_db_path:
        return {}, {}, set(), set(), {}, set(), set(), set()

    try:
        db_path = Path(analysis_db_path)
        if not db_path.exists():
            return {}, {}, set(), set(), {}, set(), set(), set()

        with sqlite3.connect(db_path) as conn:
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(divergence_data)").fetchall()
            }
            if not columns:
                return {}, {}, set(), set(), {}, set(), set(), set()

            def _select_expr(column: str, default: str = "0") -> str:
                return column if column in columns else default

            query = """
                SELECT
                    date,
                    bullish_strength,
                    bearish_strength,
                    {hidden_bullish_strength},
                    {hidden_bearish_strength},
                    rsi,
                    {bullish_r3},
                    {bearish_r3},
                    {hidden_bullish_r3},
                    {hidden_bearish_r3},
                    {pivot2_date_r3}
                FROM divergence_data
                WHERE ticker = ?
            """.format(
                hidden_bullish_strength=_select_expr("hidden_bullish_strength"),
                hidden_bearish_strength=_select_expr("hidden_bearish_strength"),
                bullish_r3=_select_expr("is_bullish_divergence_r3"),
                bearish_r3=_select_expr("is_bearish_divergence_r3"),
                hidden_bullish_r3=_select_expr("is_hidden_bullish_divergence_r3"),
                hidden_bearish_r3=_select_expr("is_hidden_bearish_divergence_r3"),
                pivot2_date_r3=_select_expr("pivot2_date_r3", "NULL"),
            )
            params = [ticker]
            if start_date and end_date:
                query += " AND date >= ? AND date <= ?"
                params += [start_date, end_date]
            elif start_date:
                query += " AND date >= ?"
                params.append(start_date)
            elif end_date:
                query += " AND date <= ?"
                params.append(end_date)

            rows = conn.execute(query, params).fetchall()

        divergence_strength_map: dict[str, dict[str, float]] = {}
        rsi_map: dict[str, float | None] = {}
        bullish_event_dates: set[str] = set()
        bullish_combo_dates: set[str] = set()
        bearish_event_dates: set[str] = set()
        hidden_bullish_event_dates: set[str] = set()
        hidden_bearish_event_dates: set[str] = set()
        pivot2_date_map: dict[str, str | None] = {}
        for (
            date_value,
            bullish_strength,
            bearish_strength,
            hidden_bullish_strength,
            hidden_bearish_strength,
            rsi,
            is_bullish_divergence_r3,
            is_bearish_divergence_r3,
            is_hidden_bullish_divergence_r3,
            is_hidden_bearish_divergence_r3,
            pivot2_date_r3,
        ) in rows:
            date_key = str(date_value)
            divergence_strength_map[date_key] = {
                "Bullish Divergence": float(bullish_strength or 0.0),
                "Bearish Divergence": float(bearish_strength or 0.0),
                "Hidden Bullish Divergence": float(hidden_bullish_strength or 0.0),
                "Hidden Bearish Divergence": float(hidden_bearish_strength or 0.0),
            }
            rsi_map[date_key] = None if rsi is None else float(rsi)
            pivot2_date_map[date_key] = None if pivot2_date_r3 is None else str(pivot2_date_r3)
            if float(bullish_strength or 0.0) > 0.0:
                bullish_combo_dates.add(date_key)
            if float(bearish_strength or 0.0) > 0.0:
                bearish_event_dates.add(date_key)
            if float(hidden_bullish_strength or 0.0) > 0.0:
                hidden_bullish_event_dates.add(date_key)
            if float(hidden_bearish_strength or 0.0) > 0.0:
                hidden_bearish_event_dates.add(date_key)
            if int(is_bullish_divergence_r3 or 0) == 1:
                bullish_event_dates.add(date_key)
                bullish_combo_dates.add(date_key)
            if int(is_bearish_divergence_r3 or 0) == 1:
                bearish_event_dates.add(date_key)
            if int(is_hidden_bullish_divergence_r3 or 0) == 1:
                hidden_bullish_event_dates.add(date_key)
            if int(is_hidden_bearish_divergence_r3 or 0) == 1:
                hidden_bearish_event_dates.add(date_key)
        return (
            divergence_strength_map,
            rsi_map,
            bullish_event_dates,
            bullish_combo_dates,
            pivot2_date_map,
            bearish_event_dates,
            hidden_bullish_event_dates,
            hidden_bearish_event_dates,
        )
    except Exception:
        return {}, {}, set(), set(), {}, set(), set(), set()


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
    analysis_db_path: str = "data/analysis.db",
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
        analysis_db_path: Polku analysis.db-tietokantaan (divergence_data tarkistusta varten)
    """
    # Normalisoi ticker: isot kirjaimet, trimmattu
    ticker = (ticker or "").strip().upper()

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
            return None  # None = ei dataa, {} = ei kuvioita
        # Ensure pvm is datetime for correct sorting and comparisons
        df["pvm"] = pd.to_datetime(df["pvm"])
        df = df.sort_values("pvm").reset_index(drop=True)

    (
        divergence_strength_map,
        divergence_rsi_map,
        divergence_dates,
        combo_divergence_dates,
        divergence_pivot2_map,
        bearish_divergence_dates,
        hidden_bullish_divergence_dates,
        hidden_bearish_divergence_dates,
    ) = _load_divergence_snapshot(
        ticker, analysis_db_path, s_iso, e_iso
    )
    date_to_index = {
        pvm.date().isoformat(): idx for idx, pvm in enumerate(df["pvm"])
    }
    combo_eligible_dates = set(combo_divergence_dates)
    for event_date in combo_divergence_dates:
        pivot2_date = divergence_pivot2_map.get(event_date)
        pivot2_idx = date_to_index.get(pivot2_date) if pivot2_date else None
        if pivot2_idx is None:
            continue
        start_idx = max(0, pivot2_idx - 3)
        end_idx = min(len(df) - 1, pivot2_idx + 3)
        for window_idx in range(start_idx, end_idx + 1):
            combo_eligible_dates.add(df.iloc[window_idx]["pvm"].date().isoformat())

    # Täytä RSI ensisijaisesti divergence_data-taulusta, muutoin laske
    if divergence_rsi_map:
        df["RSI"] = df["pvm"].dt.strftime("%Y-%m-%d").map(divergence_rsi_map)

    # Laske puuttuvat RSI-arvot Wilder RSI(14) -menetelmällä.
    if "RSI" not in df.columns or df["RSI"].isna().any():
        calc_rsi = pd.Series(
            compute_rsi_wilder(df["Close"].astype(float).tolist(), period=14),
            index=df.index,
            dtype="float64",
        )
        if "RSI" in df.columns:
            df["RSI"] = df["RSI"].fillna(calc_rsi)
        else:
            df["RSI"] = calc_rsi
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
        current_date = row["pvm"].date().isoformat()

        current_in_downtrend = True
        if downtrend_filter:
            current_in_downtrend = _is_in_downtrend_local(df, "Close", "Volume", i)

        found = []
        # Check each pattern and log the result per pattern
        if current_in_downtrend and "Hammer" in patterns and is_hammer(row):
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

        if current_in_downtrend and i > 0 and "Bullish Engulfing" in patterns:
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

        if current_in_downtrend and i > 0 and "Piercing Pattern" in patterns:
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

        if current_in_downtrend and i >= 2 and "Three White Soldiers" in patterns:
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

        if current_in_downtrend and i >= 2 and "Morning Star" in patterns:
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

        if current_in_downtrend and "Dragonfly Doji" in patterns and is_dragonfly_doji(row):
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

        if current_in_downtrend and i >= 2 and "Bullish Abandoned Baby" in patterns:
            if is_bullish_abandoned_baby(df, i):
                strength = _calculate_signal_strength(
                    "Bullish Abandoned Baby",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Bullish Abandoned Baby", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bullish Abandoned Baby checked - FOUND (strength {strength})"
                    )

        if current_in_downtrend and i >= 5 and "Bullish Flag" in patterns:
            if is_bullish_flag(df, i):
                strength = _calculate_signal_strength(
                    "Bullish Flag",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Bullish Flag", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bullish Flag checked - FOUND (strength {strength})"
                    )

        if current_in_downtrend and i >= 6 and "Bull Rectangle" in patterns:
            if is_bull_rectangle(df, i):
                strength = _calculate_signal_strength(
                    "Bull Rectangle",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Bull Rectangle", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bull Rectangle checked - FOUND (strength {strength})"
                    )

        if current_in_downtrend and i >= 6 and "Ascending Triangle" in patterns:
            if is_ascending_triangle(df, i):
                strength = _calculate_signal_strength(
                    "Ascending Triangle",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Ascending Triangle", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Ascending Triangle checked - FOUND (strength {strength})"
                    )

        if current_in_downtrend and i >= 6 and "Bullish Pennant" in patterns:
            if is_bullish_pennant(df, i):
                strength = _calculate_signal_strength(
                    "Bullish Pennant",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Bullish Pennant", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bullish Pennant checked - FOUND (strength {strength})"
                    )

        if current_in_downtrend and i >= 204 and "Cup and Handle" in patterns:
            if is_cup_and_handle(df, i):
                strength = _calculate_signal_strength(
                    "Cup and Handle",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Cup and Handle", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Cup and Handle checked - FOUND (strength {strength})"
                    )

        if i > 0 and "Bearish Engulfing" in patterns:
            prev_row = df.iloc[i - 1]
            if is_bearish_engulfing(prev_row, row):
                strength = _calculate_signal_strength(
                    "Engulfing",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Bearish Engulfing", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bearish Engulfing checked - FOUND (strength {strength})"
                    )

        if "Shooting Star" in patterns and is_shooting_star(row):
            strength = _calculate_signal_strength(
                "Shooting Star",
                row["Open"],
                row["High"],
                row["Low"],
                row["Close"],
                row.get("Volume"),
            )
            found.append({"pattern": "Shooting Star", "strength": strength})
            if logger:
                logger.info(
                    f"{ticker} {row['pvm'].date().isoformat()} Shooting Star checked - FOUND (strength {strength})"
                )

        if i > 0 and "Dark Cloud Cover" in patterns:
            prev_row = df.iloc[i - 1]
            if is_dark_cloud_cover(prev_row, row):
                strength = _calculate_signal_strength(
                    "Dark Cloud Cover",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Dark Cloud Cover", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Dark Cloud Cover checked - FOUND (strength {strength})"
                    )

        if i >= 2 and "Evening Star" in patterns:
            if is_evening_star(df, i):
                strength = _calculate_signal_strength(
                    "Evening Star",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Evening Star", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Evening Star checked - FOUND (strength {strength})"
                    )

        if "Hanging Man" in patterns and is_hanging_man(row):
            strength = _calculate_signal_strength(
                "Hanging Man",
                row["Open"],
                row["High"],
                row["Low"],
                row["Close"],
                row.get("Volume"),
            )
            found.append({"pattern": "Hanging Man", "strength": strength})
            if logger:
                logger.info(
                    f"{ticker} {row['pvm'].date().isoformat()} Hanging Man checked - FOUND (strength {strength})"
                )

        if i >= 4 and "Falling Three Methods" in patterns:
            if is_falling_three_methods(df, i):
                strength = _calculate_signal_strength(
                    "Falling Three Methods",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Falling Three Methods", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Falling Three Methods checked - FOUND (strength {strength})"
                    )

        if i >= 5 and "Bearish Flag" in patterns:
            if is_bearish_flag(df, i):
                strength = _calculate_signal_strength(
                    "Bearish Flag",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Bearish Flag", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bearish Flag checked - FOUND (strength {strength})"
                    )

        if i >= 6 and "Bear Rectangle" in patterns:
            if is_bear_rectangle(df, i):
                strength = _calculate_signal_strength(
                    "Bear Rectangle",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Bear Rectangle", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bear Rectangle checked - FOUND (strength {strength})"
                    )

        if i >= 6 and "Descending Triangle" in patterns:
            if is_descending_triangle(df, i):
                strength = _calculate_signal_strength(
                    "Descending Triangle",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Descending Triangle", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Descending Triangle checked - FOUND (strength {strength})"
                    )

        if i >= 6 and "Bearish Pennant" in patterns:
            if is_bearish_pennant(df, i):
                strength = _calculate_signal_strength(
                    "Bearish Pennant",
                    row["Open"],
                    row["High"],
                    row["Low"],
                    row["Close"],
                    row.get("Volume"),
                )
                found.append({"pattern": "Bearish Pennant", "strength": strength})
                if logger:
                    logger.info(
                        f"{ticker} {row['pvm'].date().isoformat()} Bearish Pennant checked - FOUND (strength {strength})"
                    )

        if "Bullish Divergence" in patterns:
            if current_date in divergence_dates:
                divergence_in_downtrend = True
                if downtrend_filter:
                    pivot2_date = divergence_pivot2_map.get(current_date)
                    pivot2_idx = date_to_index.get(pivot2_date) if pivot2_date else None
                    divergence_in_downtrend = (
                        pivot2_idx is not None
                        and _is_in_downtrend_local(df, "Close", "Volume", pivot2_idx)
                    )
                if divergence_in_downtrend:
                    strength = divergence_strength_map.get(current_date, {}).get(
                        "Bullish Divergence", 0.0
                    )
                    found.append(
                        {
                            "pattern": "Bullish Divergence",
                            "strength": strength,
                        }
                    )
                    if logger:
                        logger.info(
                            f"{ticker} {row['pvm'].date().isoformat()} Bullish Divergence checked - FOUND (strength {strength})"
                        )

        if "Bearish Divergence" in patterns and current_date in bearish_divergence_dates:
            strength = divergence_strength_map.get(current_date, {}).get(
                "Bearish Divergence", 0.0
            )
            found.append(
                {
                    "pattern": "Bearish Divergence",
                    "strength": strength,
                }
            )
            if logger:
                logger.info(
                    f"{ticker} {row['pvm'].date().isoformat()} Bearish Divergence checked - FOUND (strength {strength})"
                )

        if (
            "Hidden Bullish Divergence" in patterns
            and current_date in hidden_bullish_divergence_dates
        ):
            strength = divergence_strength_map.get(current_date, {}).get(
                "Hidden Bullish Divergence", 0.0
            )
            found.append(
                {
                    "pattern": "Hidden Bullish Divergence",
                    "strength": strength,
                }
            )
            if logger:
                logger.info(
                    f"{ticker} {row['pvm'].date().isoformat()} Hidden Bullish Divergence checked - FOUND (strength {strength})"
                )

        if (
            "Hidden Bearish Divergence" in patterns
            and current_date in hidden_bearish_divergence_dates
        ):
            strength = divergence_strength_map.get(current_date, {}).get(
                "Hidden Bearish Divergence", 0.0
            )
            found.append(
                {
                    "pattern": "Hidden Bearish Divergence",
                    "strength": strength,
                }
            )
            if logger:
                logger.info(
                    f"{ticker} {row['pvm'].date().isoformat()} Hidden Bearish Divergence checked - FOUND (strength {strength})"
                )

        # Yhdistelmäkuviot: jos päivä on comboikkunassa ja samalla päivällä on
        # Bullish Divergence + yksi tai useampi peruskynttilä:
        # - kun Bullish Divergence on pyydetty mukaan, säilytä peruskuviot ja lisää
        #   kaikki kelvolliset combo-rivit
        # - muuten korvaa korkein prioriteetti combo-kynttilällä
        if found and current_date in combo_eligible_dates:
            if "Bullish Divergence" in patterns:
                existing_patterns = {
                    str(entry.get("pattern"))
                    for entry in found
                    if entry.get("pattern") is not None
                }
                combo_entries = []
                for entry in found:
                    base_pattern = entry.get("pattern")
                    if base_pattern not in BASE_CANDLE_ORDER:
                        continue
                    combo_name = COMBO_PATTERN_MAP.get(base_pattern)
                    if not combo_name or combo_name in existing_patterns:
                        continue
                    combo_entry = dict(entry)
                    combo_entry["pattern"] = combo_name
                    if "description" in combo_entry and isinstance(
                        combo_entry["description"], str
                    ):
                        combo_entry["description"] = combo_entry[
                            "description"
                        ].replace(str(base_pattern), combo_name)
                    combo_entries.append(combo_entry)
                    existing_patterns.add(combo_name)
                found.extend(combo_entries)
            else:
                combo_index = None
                combo_name = None
                base_pattern = None
                for candidate in BASE_CANDLE_ORDER:
                    for idx_found, entry in enumerate(found):
                        if entry.get("pattern") != candidate:
                            continue
                        mapped_name = COMBO_PATTERN_MAP.get(candidate)
                        if mapped_name:
                            combo_index = idx_found
                            combo_name = mapped_name
                            base_pattern = candidate
                            break
                    if combo_index is not None:
                        break

                if (
                    combo_index is not None
                    and combo_name is not None
                    and base_pattern is not None
                ):
                    combo_entry = dict(found[combo_index])
                    combo_entry["pattern"] = combo_name
                    if "description" in combo_entry and isinstance(
                        combo_entry["description"], str
                    ):
                        combo_entry["description"] = combo_entry[
                            "description"
                        ].replace(str(base_pattern), combo_name)
                    found[combo_index] = combo_entry

        if found:
            # Lisää RSI-arvo jokaiseen löydökseen
            rsi_value = row.get("RSI") if "RSI" in df.columns else None
            for item in found:
                item["rsi14"] = rsi_value

            key = f"{ticker}|{current_date}"
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
