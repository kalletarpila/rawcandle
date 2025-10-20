import csv
import sqlite3
import threading
import traceback
from pathlib import Path
from statistics import mean, stdev
from typing import List, Optional, Tuple

import flet as ft
import numpy as np
import pandas as pd


def _identify_columns(cur, table_name: str):
    cols = [r[1] for r in cur.execute(f"PRAGMA table_info({table_name})").fetchall()]
    lower = {c.lower(): c for c in cols}
    return cols, lower


def _calculate_relative_stdev(values: List[float]) -> Optional[float]:
    """Laskee suhteellisen standardipoikkeaman (% keskiarvosta)"""
    try:
        if len(values) < 2:
            return None
        values = [v for v in values if v is not None]
        if len(values) < 2:
            return None
        avg = mean(values)
        if avg == 0:
            return None
        std = stdev(values)
        return (std / avg) * 100.0
    except Exception:
        return None


def _calculate_moving_average(
    df: pd.DataFrame, ccol: str, idx: int, days: int
) -> Optional[float]:
    """Laskee liukuvan keskiarvon annetusta indeksistä taaksepäin"""
    try:
        if idx - days + 1 < 0:
            return None
        subset = df.iloc[idx - days + 1 : idx + 1]
        values = [
            float(row[ccol]) for _, row in subset.iterrows() if pd.notna(row[ccol])
        ]
        if len(values) != days:
            return None
        return mean(values)
    except Exception:
        return None


def _is_in_downtrend(
    df: pd.DataFrame,
    ccol: str,
    vcol: str,
    idx: int,
    min_decline_percent: float = 3.0,
    use_ma_filter: bool = True,
    use_volume_filter: bool = False,
) -> bool:
    """Tarkistaa onko kynttilä laskutrendissä annettujen kriteerien mukaan"""
    try:
        # Tarvitaan vähintään 10 päivää historiaa
        if idx < 10:
            return False

        def safe_get(row_idx, col):
            if row_idx < 0 or row_idx >= len(df):
                return None
            try:
                val = df.iloc[row_idx][col]
                return float(val) if pd.notna(val) else None
            except Exception:
                return None

        # 1. Peruskriteeri: Porrastava lasku t-10 > t-5 > t-2 > t0
        t0 = safe_get(idx, ccol)
        t_2 = safe_get(idx - 2, ccol)
        t_5 = safe_get(idx - 5, ccol)
        t_10 = safe_get(idx - 10, ccol)

        if not all([t0, t_2, t_5, t_10]):
            return False

        if not (t_10 > t_5 > t_2 > t0):
            return False

        # 2. Minimalasku: vähintään X% laskua 10 päivässä
        decline_percent = ((t_10 - t0) / t_10) * 100
        if decline_percent < min_decline_percent:
            return False

        # 3. Liukuva keskiarvo -suodatin (valinnainen)
        if use_ma_filter:
            ma5 = _calculate_moving_average(df, ccol, idx, 5)
            ma10 = _calculate_moving_average(df, ccol, idx, 10)

            if ma5 is None or ma10 is None:
                return False

            # Kurssi alle MA(10) ja MA(5) < MA(10)
            if not (t0 < ma10 and ma5 < ma10):
                return False

        # 4. Volyymi-suodatin (valinnainen)
        if use_volume_filter:
            try:
                # Keskivolyymi viimeisen 5 päivän ajalta
                recent_volumes = []
                for i in range(max(0, idx - 4), idx + 1):
                    vol = safe_get(i, vcol)
                    if vol and vol > 0:
                        recent_volumes.append(vol)

                # Keskivolyymi 20 päivän historiasta (päivät -25 ... -5)
                historical_volumes = []
                for i in range(max(0, idx - 25), max(0, idx - 4)):
                    vol = safe_get(i, vcol)
                    if vol and vol > 0:
                        historical_volumes.append(vol)

                if not recent_volumes or not historical_volumes:
                    return False

                recent_avg = mean(recent_volumes)
                historical_avg = mean(historical_volumes)

                # Volyymi vähintään 1.2x normaalia
                if recent_avg < 1.2 * historical_avg:
                    return False

            except Exception:
                # Jos volyymitarkistus epäonnistuu, hyväksytään kuitenkin
                pass

        return True

    except Exception:
        return False


def _calculate_volume_ratio(
    df: pd.DataFrame, vcol: str, idx: int, days_range: Tuple[int, int]
) -> Optional[float]:
    """Laskee volyymin suhteen 100 päivän keskiarvoon"""
    try:
        start_offset, end_offset = days_range
        start_idx = idx + start_offset
        end_idx = idx + end_offset

        if start_idx < 0 or end_idx >= len(df):
            return None

        # Laske keskivolyymi annetulta aikaväliltä
        subset = df.iloc[start_idx : end_idx + 1]
        volumes = [
            float(row[vcol])
            for _, row in subset.iterrows()
            if pd.notna(row[vcol]) and row[vcol] > 0
        ]
        if not volumes:
            return None
        avg_volume = mean(volumes)

        # Laske 100 päivän keskiarvo ennen indeksiä
        hundred_start = max(0, idx - 100)
        hundred_subset = df.iloc[hundred_start:idx]
        hundred_volumes = [
            float(row[vcol])
            for _, row in hundred_subset.iterrows()
            if pd.notna(row[vcol]) and row[vcol] > 0
        ]
        if not hundred_volumes:
            return None
        hundred_avg = mean(hundred_volumes)

        if hundred_avg == 0:
            return None

        return avg_volume / hundred_avg
    except Exception:
        return None


def _get_index_data(
    oconn, ticker: str, date: str, offset: int, data_type: str = "close"
) -> Optional[float]:
    """Hakee indeksi-tietoja tietokannasta"""
    try:
        # Hae indeksin data
        df = pd.read_sql_query(
            "SELECT pvm, open, high, low, close FROM osakedata WHERE osake = ? ORDER BY pvm ASC",
            oconn,
            params=(ticker,),
        )
        if df.empty:
            return None

        df["pvm"] = pd.to_datetime(df["pvm"]).dt.strftime("%Y-%m-%d")
        date_to_idx = {str(row["pvm"]): idx for idx, row in df.iterrows()}

        if date not in date_to_idx:
            return None

        target_idx = date_to_idx[date] + offset
        if target_idx < 0 or target_idx >= len(df):
            return None

        row = df.iloc[target_idx]
        return float(row[data_type]) if pd.notna(row[data_type]) else None
    except Exception:
        return None


def _build_output_rows(
    analysis_db: Path,
    osake_db: Path,
    downtrend_filter: bool = False,
    min_decline_percent: float = 3.0,
    use_ma_filter: bool = True,
    use_volume_filter: bool = False,
):
    """Synchronous builder for output rows according to spec.

    Returns (header, output_rows).

    Args:
        downtrend_filter: Jos True, suodatetaan vain laskutrendien kynttilät
        min_decline_percent: Minimalasku prosentteina
        use_ma_filter: Käytetäänkö liukuva keskiarvo -suodatinta
        use_volume_filter: Käytetäänkö volyymi-suodatinta
    """

    # Candlestick pattern to integer mapping
    # Kynttilöiden numerointi:
    # 1 = Hammer
    # 2 = Bullish Engulfing
    # 3 = Piercing Pattern
    # 4 = Three White Soldiers
    # 5 = Morning Star
    # 6 = Dragonfly Doji
    CANDLE_MAPPING = {
        "Hammer": 1,
        "Bullish Engulfing": 2,
        "Piercing Pattern": 3,
        "Three White Soldiers": 4,
        "Morning Star": 5,
        "Dragonfly Doji": 6,
    }

    # --- read analysis rows ---
    with sqlite3.connect(analysis_db) as aconn:
        acur = aconn.cursor()
        tbls = [
            r[0]
            for r in acur.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        ]
        candidates = ["analysis_findings", "analysis", "findings", "analysis_rows"]
        table_name = next((c for c in candidates if c in tbls), None)
        if table_name is None:
            # fallback heuristic
            for t in tbls:
                info = acur.execute(f"PRAGMA table_info({t})").fetchall()
                cols = [r[1].lower() for r in info]
                if any(x in cols for x in ("date", "pvm")) and any(
                    x in cols for x in ("ticker", "osake", "symbol")
                ):
                    table_name = t
                    break
        if table_name is None:
            raise RuntimeError("analysis table not found in analysis.db")

        info = acur.execute(f"PRAGMA table_info({table_name})").fetchall()
        col_names = [r[1] for r in info]
        lower = {c.lower(): c for c in col_names}
        date_col = lower.get("date") or lower.get("pvm")
        ticker_col = lower.get("ticker") or lower.get("osake") or lower.get("symbol")
        candle_col = (
            lower.get("candle")
            or lower.get("kynttila")
            or lower.get("pattern")
            or lower.get("pattern_name")
        )
        if not date_col or not ticker_col:
            raise RuntimeError(
                f"Cannot find date/ticker columns in {table_name}: {col_names}"
            )

        q = f'SELECT "{date_col}", "{ticker_col}"'
        if candle_col:
            q += f', "{candle_col}"'
        q += f' FROM "{table_name}"'
        acur.execute(q)
        rows = acur.fetchall()

    # Define the complete header with all new columns
    header = [
        "osake",
        "pvm",
        "kynttila",
        "t_1",
        "t0",
        "t1",  # Existing normalized columns
        # New historical prices (normalized by stock t0_low)
        "t_2",
        "t_5",
        "t_10",
        "t_15",
        "t_20",
        # New future prices (normalized by stock t0_low)
        "t2",
        "t5",
        "t10",
        "t20",
        # Volatility columns (relative standard deviation, no normalization)
        "t_2_hajonta",
        "t_5_hajonta",
        "t_10_hajonta",
        "t_15_hajonta",
        "t_20_hajonta",
        # Volume columns (relative to 100-day average, no normalization)
        "t_2_volyymi",
        "t_5_volyymi",
        "t_10_volyymi",
        "t_15_volyymi",
        "t_20_volyymi",
        "t0_volyymi",
        "t2_volyymi",
        "t5_volyymi",
        "t10_volyymi",
        "t20_volyymi",
        # Moving averages (normalized by stock t0_low)
        "t2_5p_liukuva",
        "t2_10p_liukuva",
        "t2_20p_liukuva",
        "t5_5p_liukuva",
        "t5_10p_liukuva",
        "t5_20p_liukuva",
        "t10_5p_liukuva",
        "t10_10p_liukuva",
        "t10_20p_liukuva",
        "t15_5p_liukuva",
        "t15_10p_liukuva",
        "t15_20p_liukuva",
        "t20_5p_liukuva",
        "t20_10p_liukuva",
        "t20_20p_liukuva",
        "t50_50p_liukuva",
        "t200_200p_liukuva",
        # S&P 500 index (normalized by ^GSPC t0_low)
        "SPX_0",
        "SPX_2",
        "SPX_5",
        "SPX_10",
        "SPX_15",
        "SPX_20",
        "SPX2",
        "SPX5",
        "SPX10",
        "SPX15",
        "SPX20",
        # Nasdaq 100 index (normalized by ^IXIC t0_low)
        "NDX_0",
        "NDX_2",
        "NDX_5",
        "NDX_10",
        "NDX_15",
        "NDX_20",
        "NDX2",
        "NDX5",
        "NDX10",
        "NDX15",
        "NDX20",
    ]

    if not rows:
        return header, []

    by_ticker = {}
    for rec in rows:
        if len(rec) == 3:
            date, ticker, candle = rec
        elif len(rec) == 2:
            date, ticker = rec
            candle = ""
        else:
            continue
        if not ticker:
            continue
        by_ticker.setdefault(str(ticker), []).append((str(date), candle))

    output_rows = []

    # --- read osakedata per ticker ---
    with sqlite3.connect(osake_db) as oconn:
        ocur = oconn.cursor()
        cols, lower = _identify_columns(ocur, "osakedata")
        tcol = lower.get("osake") or lower.get("ticker") or lower.get("symbol")
        pcol = lower.get("pvm") or lower.get("date")
        ocol = lower.get("open")
        hcol = lower.get("high")
        lcol = lower.get("low")
        ccol = lower.get("close")
        vcol = lower.get("volume")

        if (
            not tcol
            or not pcol
            or not ocol
            or not hcol
            or not lcol
            or not ccol
            or not vcol
        ):
            raise RuntimeError("osakedata table missing expected column names")

        total_tickers = len(by_ticker)
        for ticker_idx, (ticker, items) in enumerate(by_ticker.items()):
            # Progress indicator every 10 tickers
            if ticker_idx % 10 == 0:
                print(
                    f"📊 Käsitellään ticker {ticker_idx + 1}/{total_tickers}: {ticker}"
                )

            try:
                df = pd.read_sql_query(
                    f'SELECT * FROM osakedata WHERE "{tcol}" = ? ORDER BY "{pcol}" ASC',
                    oconn,
                    params=(ticker,),
                )
            except Exception:
                df = pd.read_sql_query(
                    f'SELECT * FROM osakedata ORDER BY "{pcol}" ASC', oconn
                )
                if tcol in df.columns:
                    df = df[df[tcol] == ticker]

            if df.empty:
                continue

            try:
                df[pcol] = pd.to_datetime(df[pcol]).dt.strftime("%Y-%m-%d")
            except Exception:
                pass

            df = df.reset_index(drop=True)
            date_to_idx = {str(r[pcol]): idx for idx, r in df.iterrows()}

            def safe_get(row, col):
                try:
                    v = row[col]
                    if pd.isna(v):
                        return None
                    return float(v)
                except Exception:
                    return None

            for date, candle in items:
                if date not in date_to_idx:
                    continue
                idx = date_to_idx[date]

                # Check if we have enough data for all calculations (except t200_200p_liukuva)
                if idx < 20 or idx + 20 >= len(df):
                    continue

                # Laskutrendi-suodatus
                if downtrend_filter:
                    if not _is_in_downtrend(
                        df,
                        ccol,
                        vcol,
                        idx,
                        min_decline_percent,
                        use_ma_filter,
                        use_volume_filter,
                    ):
                        continue  # Ohita kynttilät jotka eivät ole laskutrendissä

                # Get t0 values for normalization
                r0 = df.loc[idx]
                t0_low = safe_get(r0, lcol)
                t0_close = safe_get(
                    r0, ccol
                )  # Added: get t0_close for MA normalization
                if t0_low is None or t0_low <= 0 or t0_close is None or t0_close <= 0:
                    continue

                # Calculate existing normalized values (already implemented)
                r_m1 = df.loc[idx - 1] if idx > 0 else None
                r1 = df.loc[idx + 1] if idx + 1 < len(df) else None

                t_minus1 = (
                    (safe_get(r_m1, ccol) / t0_low * 100)
                    if r_m1 is not None and safe_get(r_m1, ccol)
                    else None
                )
                t0 = 100.0  # t0_low / t0_low * 100 = 100.0 (base normalization as 100%)
                t_plus1 = (
                    (safe_get(r1, ccol) / t0_low * 100)
                    if r1 is not None and safe_get(r1, ccol)
                    else None
                )

                # Calculate new historical prices (normalized)
                def get_normalized_close(offset):
                    target_idx = idx + offset
                    if target_idx < 0 or target_idx >= len(df):
                        return None
                    target_row = df.loc[target_idx]
                    close_val = safe_get(target_row, ccol)
                    return (close_val / t0_low * 100) if close_val is not None else None

                t_2 = get_normalized_close(-2)
                t_5 = get_normalized_close(-5)
                t_10 = get_normalized_close(-10)
                t_15 = get_normalized_close(-15)
                t_20 = get_normalized_close(-20)

                t2 = get_normalized_close(2)
                t5 = get_normalized_close(5)
                t10 = get_normalized_close(10)
                t20 = get_normalized_close(20)

                # Calculate volatility (relative standard deviation)
                def calc_volatility(days_back):
                    if idx - days_back < 0:
                        return None
                    start_idx = idx - days_back
                    end_idx = idx  # Changed: include t0 (not t-1)
                    subset = df.iloc[start_idx : end_idx + 1]
                    values = [safe_get(row, ccol) for _, row in subset.iterrows()]
                    values = [v for v in values if v is not None]
                    return _calculate_relative_stdev(values)

                t_2_hajonta = calc_volatility(2)
                t_5_hajonta = calc_volatility(5)
                t_10_hajonta = calc_volatility(10)
                t_15_hajonta = calc_volatility(15)
                t_20_hajonta = calc_volatility(20)

                # Calculate volume ratios
                def calc_volume_ratio(days_range):
                    return _calculate_volume_ratio(df, vcol, idx, days_range)

                t_2_volyymi = calc_volume_ratio((-4, -2))  # 3 days centered at t-3
                t_5_volyymi = calc_volume_ratio((-7, -3))  # 5 days centered at t-5
                t_10_volyymi = calc_volume_ratio((-12, -8))  # 5 days centered at t-10
                t_15_volyymi = calc_volume_ratio((-17, -13))  # 5 days centered at t-15
                t_20_volyymi = calc_volume_ratio((-22, -18))  # 5 days centered at t-20

                # t0 volume ratio
                t0_volume = safe_get(r0, vcol)
                hundred_start = max(0, idx - 100)
                hundred_subset = df.iloc[hundred_start:idx]
                hundred_volumes = [
                    safe_get(row, vcol)
                    for _, row in hundred_subset.iterrows()
                    if safe_get(row, vcol)
                ]
                hundred_avg = mean(hundred_volumes) if hundred_volumes else None
                t0_volyymi = (
                    t0_volume / hundred_avg
                    if t0_volume and hundred_avg and hundred_avg > 0
                    else None
                )

                t2_volyymi = calc_volume_ratio((1, 3))  # 3 days centered at t+2
                t5_volyymi = calc_volume_ratio((3, 7))  # 5 days centered at t+5
                t10_volyymi = calc_volume_ratio((8, 12))  # 5 days centered at t+10
                t20_volyymi = calc_volume_ratio((18, 22))  # 5 days centered at t+20

                # Calculate moving averages (normalized by t0_close)
                def calc_ma_normalized(days_offset, ma_period):
                    target_idx = idx + days_offset
                    ma_val = _calculate_moving_average(df, ccol, target_idx, ma_period)
                    return (ma_val / t0_close * 100) if ma_val is not None else None

                t2_5p_liukuva = calc_ma_normalized(-2, 5)
                t2_10p_liukuva = calc_ma_normalized(-2, 10)
                t2_20p_liukuva = calc_ma_normalized(-2, 20)

                t5_5p_liukuva = calc_ma_normalized(-5, 5)
                t5_10p_liukuva = calc_ma_normalized(-5, 10)
                t5_20p_liukuva = calc_ma_normalized(-5, 20)

                t10_5p_liukuva = calc_ma_normalized(-10, 5)
                t10_10p_liukuva = calc_ma_normalized(-10, 10)
                t10_20p_liukuva = calc_ma_normalized(-10, 20)

                t15_5p_liukuva = calc_ma_normalized(-15, 5)
                t15_10p_liukuva = calc_ma_normalized(-15, 10)
                t15_20p_liukuva = calc_ma_normalized(-15, 20)

                t20_5p_liukuva = calc_ma_normalized(-20, 5)
                t20_10p_liukuva = calc_ma_normalized(-20, 10)
                t20_20p_liukuva = calc_ma_normalized(-20, 20)

                t50_50p_liukuva = calc_ma_normalized(-50, 50)

                # Special case for t200_200p_liukuva - set to 0 if not enough data
                t200_200p_liukuva = calc_ma_normalized(-200, 200)
                if t200_200p_liukuva is None:
                    t200_200p_liukuva = 0

                # Calculate index data (S&P 500)
                def get_index_normalized(index_ticker, offset, data_type="close"):
                    # Get the index's t0_low for normalization
                    index_t0_low = _get_index_data(oconn, index_ticker, date, 0, "low")
                    if index_t0_low is None or index_t0_low <= 0:
                        return None

                    index_value = _get_index_data(
                        oconn, index_ticker, date, offset, data_type
                    )
                    return (
                        (index_value / index_t0_low * 100)
                        if index_value is not None
                        else None
                    )

                # S&P 500 data
                SPX_0 = get_index_normalized("^GSPC", 0, "low")  # This should be 100.0
                if SPX_0 is not None:
                    SPX_0 = 100.0  # Force to 100.0 since it's the normalization base

                SPX_2 = get_index_normalized("^GSPC", -2)
                SPX_5 = get_index_normalized("^GSPC", -5)
                SPX_10 = get_index_normalized("^GSPC", -10)
                SPX_15 = get_index_normalized("^GSPC", -15)
                SPX_20 = get_index_normalized("^GSPC", -20)

                SPX2 = get_index_normalized("^GSPC", 2)
                SPX5 = get_index_normalized("^GSPC", 5)
                SPX10 = get_index_normalized("^GSPC", 10)
                SPX15 = get_index_normalized("^GSPC", 15)
                SPX20 = get_index_normalized("^GSPC", 20)

                # Nasdaq 100 data
                NDX_0 = get_index_normalized("^IXIC", 0, "low")
                if NDX_0 is not None:
                    NDX_0 = 100.0  # Force to 100.0 since it's the normalization base

                NDX_2 = get_index_normalized("^IXIC", -2)
                NDX_5 = get_index_normalized("^IXIC", -5)
                NDX_10 = get_index_normalized("^IXIC", -10)
                NDX_15 = get_index_normalized("^IXIC", -15)
                NDX_20 = get_index_normalized("^IXIC", -20)

                NDX2 = get_index_normalized("^IXIC", 2)
                NDX5 = get_index_normalized("^IXIC", 5)
                NDX10 = get_index_normalized("^IXIC", 10)
                NDX15 = get_index_normalized("^IXIC", 15)
                NDX20 = get_index_normalized("^IXIC", 20)

                # Convert candle name to integer using mapping
                candle_int = CANDLE_MAPPING.get(candle, 0)  # 0 for unknown patterns

                # Format values for output
                def fmt_val(v, decimals=6):
                    if v is None:
                        return ""
                    if isinstance(v, (int, float)):
                        return round(v, decimals)
                    return v

                # Build output row with all columns
                out = [
                    ticker,
                    date,
                    candle_int,  # candle as integer
                    # Existing normalized columns
                    fmt_val(t_minus1),
                    fmt_val(t0),
                    fmt_val(t_plus1),
                    # New historical prices
                    fmt_val(t_2),
                    fmt_val(t_5),
                    fmt_val(t_10),
                    fmt_val(t_15),
                    fmt_val(t_20),
                    # New future prices
                    fmt_val(t2),
                    fmt_val(t5),
                    fmt_val(t10),
                    fmt_val(t20),
                    # Volatility
                    fmt_val(t_2_hajonta),
                    fmt_val(t_5_hajonta),
                    fmt_val(t_10_hajonta),
                    fmt_val(t_15_hajonta),
                    fmt_val(t_20_hajonta),
                    # Volume ratios
                    fmt_val(t_2_volyymi),
                    fmt_val(t_5_volyymi),
                    fmt_val(t_10_volyymi),
                    fmt_val(t_15_volyymi),
                    fmt_val(t_20_volyymi),
                    fmt_val(t0_volyymi),
                    fmt_val(t2_volyymi),
                    fmt_val(t5_volyymi),
                    fmt_val(t10_volyymi),
                    fmt_val(t20_volyymi),
                    # Moving averages
                    fmt_val(t2_5p_liukuva),
                    fmt_val(t2_10p_liukuva),
                    fmt_val(t2_20p_liukuva),
                    fmt_val(t5_5p_liukuva),
                    fmt_val(t5_10p_liukuva),
                    fmt_val(t5_20p_liukuva),
                    fmt_val(t10_5p_liukuva),
                    fmt_val(t10_10p_liukuva),
                    fmt_val(t10_20p_liukuva),
                    fmt_val(t15_5p_liukuva),
                    fmt_val(t15_10p_liukuva),
                    fmt_val(t15_20p_liukuva),
                    fmt_val(t20_5p_liukuva),
                    fmt_val(t20_10p_liukuva),
                    fmt_val(t20_20p_liukuva),
                    fmt_val(t50_50p_liukuva),
                    fmt_val(t200_200p_liukuva),
                    # S&P 500 index
                    fmt_val(SPX_0),
                    fmt_val(SPX_2),
                    fmt_val(SPX_5),
                    fmt_val(SPX_10),
                    fmt_val(SPX_15),
                    fmt_val(SPX_20),
                    fmt_val(SPX2),
                    fmt_val(SPX5),
                    fmt_val(SPX10),
                    fmt_val(SPX15),
                    fmt_val(SPX20),
                    # Nasdaq 100 index
                    fmt_val(NDX_0),
                    fmt_val(NDX_2),
                    fmt_val(NDX_5),
                    fmt_val(NDX_10),
                    fmt_val(NDX_15),
                    fmt_val(NDX_20),
                    fmt_val(NDX2),
                    fmt_val(NDX5),
                    fmt_val(NDX10),
                    fmt_val(NDX15),
                    fmt_val(NDX20),
                ]

                output_rows.append(out)

    return header, output_rows


def paivita_results_csv(page: ft.Page, app=None):
    """Starts a background job that builds/updates data/results.csv and shows a SnackBar when done."""

    def worker():
        try:
            base = Path(__file__).resolve().parents[1]
            analysis_db = base / "analysis" / "analysis.db"
            osake_db = base / "data" / "osakedata.db"
            csv_path = base / "data" / "results.csv"

            if not analysis_db.exists():
                sb = ft.SnackBar(
                    ft.Text("❌ analysis.db ei löytynyt."),
                    bgcolor=ft.Colors.RED_600,
                    duration=3000,
                )
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()
                return
            if not osake_db.exists():
                sb = ft.SnackBar(
                    ft.Text("❌ osakedata.db ei löytynyt."),
                    bgcolor=ft.Colors.RED_600,
                    duration=3000,
                )
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()
                return

            # Lue laskutrendi-suodatin asetukset
            downtrend_filter = False
            min_decline_percent = 3.0
            use_ma_filter = True
            use_volume_filter = False

            if app and hasattr(app, "results_downtrend_filter"):
                try:
                    downtrend_filter = app.results_downtrend_filter.value or False

                    try:
                        min_decline_percent = float(
                            app.results_min_decline_percent.value or "3.0"
                        )
                    except (ValueError, AttributeError):
                        min_decline_percent = 3.0

                    use_ma_filter = getattr(app.results_ma_filter, "value", True)
                    use_volume_filter = getattr(
                        app.results_volume_filter, "value", False
                    )
                except Exception:
                    pass  # Käytä oletusarvoja

            # Näytä käytettävät asetukset
            filter_info = ""
            if downtrend_filter:
                filter_info = f" (🔻 Laskutrendi: {min_decline_percent}%, MA={use_ma_filter}, Vol={use_volume_filter})"

            header, output_rows = _build_output_rows(
                analysis_db,
                osake_db,
                downtrend_filter,
                min_decline_percent,
                use_ma_filter,
                use_volume_filter,
            )

            csv_path.parent.mkdir(parents=True, exist_ok=True)

            # write header if missing
            if not csv_path.exists():
                with open(csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(header)

            added = 0
            if output_rows:
                with open(csv_path, "a", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    for r in output_rows:
                        writer.writerow(r)
                        added += 1

            sb = ft.SnackBar(
                ft.Text(f"✅ Lisätty {added} riviä results.csv:ään{filter_info}"),
                bgcolor=ft.Colors.GREEN_600,
                duration=4000,
            )
            if sb not in page.overlay:
                page.overlay.append(sb)
            sb.open = True
            page.update()

        except Exception as ex:
            tb = traceback.format_exc()
            try:
                sb = ft.SnackBar(
                    ft.Text(f"❌ Virhe: {str(ex)}"),
                    bgcolor=ft.Colors.RED_600,
                    duration=4000,
                )
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()
            except Exception:
                pass
            print(tb)

    threading.Thread(target=worker, daemon=True).start()


def paivita_results_csv_click(e):
    try:
        page = e.page
    except Exception:
        try:
            page = e.control.page
        except Exception:
            page = None
    if page is not None:
        # Etsitään app instanssi
        app = None
        for attr_name in dir(page):
            attr = getattr(page, attr_name)
            if hasattr(attr, "results_downtrend_filter"):
                app = attr
                break
        paivita_results_csv(page, app)


def generate_results_now(
    write: bool = True,
    downtrend_filter: bool = False,
    min_decline_percent: float = 3.0,
    use_ma_filter: bool = True,
    use_volume_filter: bool = False,
):
    """Generoi results.csv tiedosto

    Args:
        write: Kirjoitetaanko tiedostoon vai palautetaanko vain rivimäärä
        downtrend_filter: Suodatetaanko vain laskutrendien kynttilät
        min_decline_percent: Minimalasku prosentteina
        use_ma_filter: Käytetäänkö liukuva keskiarvo -suodatinta
        use_volume_filter: Käytetäänkö volyymi-suodatinta
    """
    base = Path(__file__).resolve().parents[1]
    analysis_db = base / "analysis" / "analysis.db"
    osake_db = base / "data" / "osakedata.db"
    csv_path = base / "data" / "results.csv"

    header, output_rows = _build_output_rows(
        analysis_db,
        osake_db,
        downtrend_filter,
        min_decline_percent,
        use_ma_filter,
        use_volume_filter,
    )

    if not output_rows:
        return 0

    csv_path.parent.mkdir(parents=True, exist_ok=True)

    if write and not csv_path.exists():
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)

    added = 0
    if write:
        with open(csv_path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            for r in output_rows:
                writer.writerow(r)
                added += 1
    else:
        added = len(output_rows)

    return added
