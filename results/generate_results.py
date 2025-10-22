import sqlite3
import threading
import traceback
from pathlib import Path
from statistics import mean, stdev
from typing import List, Optional, Tuple
import locale

import flet as ft
import numpy as np
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment
from openpyxl.utils.dataframe import dataframe_to_rows

# Uusi optimoitu cache-järjestelmä
from .excel_cache import ExcelResultsCache


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


def _format_finnish_number(value):
    """Muotoilee numeron suomalaiseen muotoon: pilkku desimaalimerkkinä, ei tuhateroittimia"""
    if value is None or value == "":
        return ""
    try:
        if isinstance(value, (int, float)):
            # Pyöristetään 4 desimaaliin ja vaihdetaan piste pilkkuun
            formatted = f"{float(value):.4f}".rstrip("0").rstrip(".")
            return formatted.replace(".", ",")
        return str(value).replace(".", ",")
    except (ValueError, TypeError):
        return str(value)


def _create_excel_file(
    header: List[str],
    output_rows: List[List],
    excel_path: Path,
    downtrend_filter: bool = False,
):
    """Luo Excel-tiedoston suomalaisilla asetuksilla ja kauniilla muotoilulla"""
    try:
        # Luodaan DataFrame (säilytetään alkuperäiset numerot)
        df = pd.DataFrame(output_rows, columns=header)

        # Luodaan workbook ja worksheet
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Kynttilätulokset"

        # Suomalainen numeromuotoilu Excelille
        finnish_number_format = "#,##0.0000"
        finnish_number_format = (
            finnish_number_format.replace(",", " ").replace(".", ",").replace(" ", ".")
        )

        # Lisätään data
        for r_idx, row in enumerate(dataframe_to_rows(df, index=False, header=True), 1):
            for c_idx, value in enumerate(row, 1):
                cell = ws.cell(row=r_idx, column=c_idx, value=value)

                # Muotoilu otsikoille
                if r_idx == 1:
                    cell.font = Font(bold=True, color="FFFFFF")
                    cell.fill = PatternFill(
                        start_color="366092", end_color="366092", fill_type="solid"
                    )
                    cell.alignment = Alignment(horizontal="center", vertical="center")

                # Numeromuotoilu numerotyyppisille soluille (sarakkeet 4 alkaen)
                elif r_idx > 1 and c_idx >= 4:  # Data-rivit, numerosarakkeet
                    if isinstance(value, (int, float)) and value is not None:
                        cell.number_format = "#,##0.00;[RED]-#,##0.00"

                # Muotoilu trendisarakkeelle jos käytössä
                elif downtrend_filter and c_idx == 3:  # Kynttilä-sarake
                    if "downtrend" in str(value).lower():
                        cell.fill = PatternFill(
                            start_color="FFE6E6", end_color="FFE6E6", fill_type="solid"
                        )

        # Automaattinen sarakkeiden leveyden säätö
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 25)  # Max 25 merkkiä
            ws.column_dimensions[column_letter].width = adjusted_width

        # Tallennetaan
        excel_path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(excel_path)
        return True

    except Exception as e:
        print(f"Virhe Excel-tiedoston luonnissa: {e}")
        return False


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
    progress_callback=None,
):
    """Synchronous builder for output rows according to spec.

    Returns (header, output_rows).

    Args:
        downtrend_filter: Jos True, suodatetaan vain laskutrendien kynttilät
        min_decline_percent: Minimalasku prosentteina
        use_ma_filter: Käytetäänkö liukuva keskiarvo -suodatinta
        use_volume_filter: Käytetäänkö volyymi-suodatinta
        progress_callback: Callback-funktio edistymisen raportointiin
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
        # Uudet sarakkeet
        signal_strength_col = lower.get("signal_strength") or lower.get("strength")
        price_col = lower.get("price") or lower.get("hinta")
        volume_col = lower.get("volume") or lower.get("volyymi")
        description_col = lower.get("description") or lower.get("kuvaus")

        if not date_col or not ticker_col:
            raise RuntimeError(
                f"Cannot find date/ticker columns in {table_name}: {col_names}"
            )

        q = f'SELECT "{date_col}", "{ticker_col}"'
        if candle_col:
            q += f', "{candle_col}"'
        if signal_strength_col:
            q += f', "{signal_strength_col}"'
        if price_col:
            q += f', "{price_col}"'
        if volume_col:
            q += f', "{volume_col}"'
        if description_col:
            q += f', "{description_col}"'
        q += f' FROM "{table_name}"'
        acur.execute(q)
        rows = acur.fetchall()

    # Define the complete header with all new columns
    header = [
        "osake",
        "pvm",
        "kynttila",
        "signal_strength",
        "price",
        "volume_analysis",
        "description",
        # New detailed candle data
        "t_1_alin",
        "t_1_ylin",
        "t_1_bodi",
        "t_1_bodi_colour",
        "t0_alin",
        "t0_ylin",
        "t0_bodi",
        "t0_bodi_colour",
        "t1_alin",
        "t1_ylin",
        "t1_bodi",
        "t1_bodi_colour",
        # New historical prices (normalized by stock t0_alin)
        "t_2",
        "t_5",
        "t_10",
        "t_15",
        "t_20",
        # New future prices (normalized by stock t0_alin)
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
        # Moving averages (normalized by stock t0_alin)
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
        # S&P 500 index (normalized by ^GSPC t0_alin)
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
        # Nasdaq 100 index (normalized by ^NDX t0_alin)
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
        # Handle different numbers of columns based on what was selected
        if len(rec) >= 7:  # Full data with all new columns
            (
                date,
                ticker,
                candle,
                signal_strength,
                price,
                volume_analysis,
                description,
            ) = rec[:7]
        elif len(rec) >= 6:  # Missing description
            date, ticker, candle, signal_strength, price, volume_analysis = rec[:6]
            description = ""
        elif len(rec) >= 5:  # Missing volume and description
            date, ticker, candle, signal_strength, price = rec[:5]
            volume_analysis = None
            description = ""
        elif len(rec) >= 4:  # Missing price, volume and description
            date, ticker, candle, signal_strength = rec[:4]
            price = None
            volume_analysis = None
            description = ""
        elif len(rec) == 3:  # Legacy format
            date, ticker, candle = rec
            signal_strength = None
            price = None
            volume_analysis = None
            description = ""
        elif len(rec) == 2:  # Legacy format without candle
            date, ticker = rec
            candle = ""
            signal_strength = None
            price = None
            volume_analysis = None
            description = ""
        else:
            continue

        if not ticker:
            continue

        by_ticker.setdefault(str(ticker), []).append(
            (str(date), candle, signal_strength, price, volume_analysis, description)
        )

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
            # Progress indicator
            progress = (
                0.2 + (ticker_idx / total_tickers) * 0.6
            )  # 20% - 80% of total progress

            if ticker_idx % 10 == 0:
                print(
                    f"📊 Käsitellään ticker {ticker_idx + 1}/{total_tickers}: {ticker}"
                )

            if progress_callback:
                progress_callback(
                    f"📊 Käsitellään osake {ticker_idx + 1}/{total_tickers}: {ticker}",
                    progress,
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

            for (
                date,
                candle,
                signal_strength,
                price,
                volume_analysis,
                description,
            ) in items:
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
                t0_high = safe_get(r0, hcol)
                t0_open = safe_get(r0, ocol)
                t0_close = safe_get(r0, ccol)

                if t0_low is None or t0_low <= 0 or t0_close is None or t0_close <= 0:
                    continue

                # Helper function to calculate body percentage and color
                def calc_candle_details(row_data):
                    if row_data is None:
                        return None, None, None, None

                    low = safe_get(row_data, lcol)
                    high = safe_get(row_data, hcol)
                    open_val = safe_get(row_data, ocol)
                    close_val = safe_get(row_data, ccol)

                    if any(x is None for x in [low, high, open_val, close_val]):
                        return None, None, None, None

                    # Normalize to t0_low
                    norm_low = (low / t0_low * 100) if t0_low > 0 else None
                    norm_high = (high / t0_low * 100) if t0_low > 0 else None

                    # Body percentage of total candle
                    candle_range = high - low
                    body_size = abs(close_val - open_val)
                    body_percent = (
                        (body_size / candle_range * 100) if candle_range > 0 else 0
                    )

                    # Color: 1=green (close > open), 0=red (close <= open)
                    color = 1 if close_val > open_val else 0

                    return norm_low, norm_high, body_percent, color

                # Calculate detailed candle data for t-1, t0, t1
                r_m1 = df.loc[idx - 1] if idx > 0 else None
                r1 = df.loc[idx + 1] if idx + 1 < len(df) else None

                # T-1 (previous day)
                t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour = calc_candle_details(
                    r_m1
                )

                # T0 (current day - candle day)
                t0_alin, t0_ylin, t0_bodi, t0_bodi_colour = calc_candle_details(r0)

                # T1 (next day)
                t1_alin, t1_ylin, t1_bodi, t1_bodi_colour = calc_candle_details(r1)

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
                NDX_0 = get_index_normalized("^NDX", 0, "low")
                if NDX_0 is not None:
                    NDX_0 = 100.0  # Force to 100.0 since it's the normalization base

                NDX_2 = get_index_normalized("^NDX", -2)
                NDX_5 = get_index_normalized("^NDX", -5)
                NDX_10 = get_index_normalized("^NDX", -10)
                NDX_15 = get_index_normalized("^NDX", -15)
                NDX_20 = get_index_normalized("^NDX", -20)

                NDX2 = get_index_normalized("^NDX", 2)
                NDX5 = get_index_normalized("^NDX", 5)
                NDX10 = get_index_normalized("^NDX", 10)
                NDX15 = get_index_normalized("^NDX", 15)
                NDX20 = get_index_normalized("^NDX", 20)

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
                    fmt_val(signal_strength) if signal_strength is not None else "",
                    fmt_val(price) if price is not None else "",
                    fmt_val(volume_analysis) if volume_analysis is not None else "",
                    description if description else "",
                    # New detailed candle data
                    fmt_val(t_1_alin),
                    fmt_val(t_1_ylin),
                    fmt_val(t_1_bodi),
                    fmt_val(t_1_bodi_colour),
                    fmt_val(t0_alin),
                    fmt_val(t0_ylin),
                    fmt_val(t0_bodi),
                    fmt_val(t0_bodi_colour),
                    fmt_val(t1_alin),
                    fmt_val(t1_ylin),
                    fmt_val(t1_bodi),
                    fmt_val(t1_bodi_colour),
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
    """Starts a background job that builds/updates data/results.xlsx using optimized cache system."""

    def worker():
        try:
            base = Path(__file__).resolve().parents[1]
            analysis_db = base / "analysis" / "analysis.db"
            osake_db = base / "data" / "osakedata.db"
            excel_path = base / "data" / "results.xlsx"

            if not analysis_db.exists():
                sb = ft.SnackBar(
                    ft.Text("❌ analysis.db ei löytynyt."),
                    bgcolor=ft.Colors.RED_600,
                    action="OK",
                    action_color=ft.Colors.WHITE,
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
                    action="OK",
                    action_color=ft.Colors.WHITE,
                )
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()
                return

            # Lue generointi-asetukset
            force_rebuild = False
            if app and hasattr(app, "results_force_rebuild"):
                try:
                    force_rebuild = app.results_force_rebuild.value or False
                except Exception:
                    force_rebuild = False

            # Lue ticker-filteritieto
            ticker_filter = None
            print(f"🔍 Debug ticker-lukeminen: app={app is not None}")
            if app:
                print(
                    f"🔍 Debug: hasattr ticker_field={hasattr(app, 'results_ticker_field')}"
                )
                print(
                    f"🔍 Debug: hasattr radio_group={hasattr(app, 'results_radio_group')}"
                )

            if (
                app
                and hasattr(app, "results_ticker_field")
                and hasattr(app, "results_radio_group")
            ):
                try:
                    ticker_mode = app.results_radio_group.value
                    ticker = app.results_ticker_field.value.strip().upper()
                    print(f"🔍 Debug: ticker_mode={ticker_mode}, ticker='{ticker}'")
                    if ticker_mode == "single" and ticker:
                        ticker_filter = ticker
                        print(f"🎯 Käyttäjä valitsi ticker-filterin: {ticker_filter}")
                    else:
                        print("🌐 Käyttäjä valitsi kaikki osakkeet")
                except Exception as ex:
                    print(f"Virhe ticker-filterin lukemisessa: {ex}")
            else:
                print("❌ App-objekti tai kentät puuttuvat ticker-filtterille")

            # Lue laskutrendi-suodatin asetukset (vaikka nyt teemme kaiken dataan)
            filter_info = ""
            if ticker_filter:
                filter_info = f" ({ticker_filter})"

            # Luo progress indicator
            progress_bar = ft.ProgressBar(value=0, width=400)
            mode_text = "🔄 Kokonaan uusi" if force_rebuild else "⚡ Inkrementaalinen"
            progress_text = ft.Text(
                f"🔍 Aloitetaan optimoitu analyysi ({mode_text})..."
            )

            # Luo progress dialog
            dialog_title = "🚀 Generoidaan tuloksia (optimoitu)"
            if force_rebuild:
                dialog_title += " - Kokonaan uusi"
            else:
                dialog_title += " - Inkrementaalinen päivitys"

            progress_dlg = ft.AlertDialog(
                modal=True,
                title=ft.Text(dialog_title),
                content=ft.Container(
                    ft.Column(
                        [
                            progress_text,
                            progress_bar,
                        ],
                        tight=True,
                    ),
                    width=400,
                    height=100,
                ),
                actions=[],  # Ei sulje-nappia - pakottaa odottamaan
            )

            def progress_callback(message, current, total):
                def update_progress():
                    try:
                        progress_text.value = message
                        progress_bar.value = current / total if total > 0 else 0
                        page.update()
                    except Exception as ex:
                        print(f"Virhe progress-päivityksessä: {ex}")

                try:
                    page.run_thread(update_progress)
                except Exception as ex:
                    print(f"Virhe progress-threadin käynnistämisessä: {ex}")

            # Näytä progress dialog
            def show_progress():
                try:
                    page.overlay.append(progress_dlg)
                    progress_dlg.open = True
                    page.update()
                except Exception as ex:
                    print(f"Virhe progress-dialogin näyttämisessä: {ex}")

            try:
                page.run_thread(show_progress)
            except Exception as ex:
                print(f"Virhe progress-threadin käynnistämisessä: {ex}")

            # Määritä dialogi-sulkija
            def close_progress_dialog():
                try:
                    progress_dlg.open = False
                    if progress_dlg in page.overlay:
                        page.overlay.remove(progress_dlg)
                    page.update()
                except Exception as ex:
                    print(f"Virhe dialogi-sulkemisessa: {ex}")

            # Käytä optimoitua generointi-funktiota erillisessä threadissa
            def run_generation():
                try:
                    return generate_excel_optimized(
                        excel_path=str(excel_path),
                        progress_callback=progress_callback,
                        analysis_db=str(analysis_db),
                        osake_db=str(osake_db),
                        force_rebuild=force_rebuild,  # Käyttäjän valinta
                        ticker_filter=ticker_filter,  # Käyttäjän ticker-filtteri
                    )
                except Exception as ex:
                    print(f"Virhe Excel-generoinnissa: {ex}")
                    return 0

            # Aja generointi taustalla
            import threading

            result_container = {"added": 0, "done": False, "error": None}

            def generation_thread():
                try:
                    result_container["added"] = run_generation()
                except Exception as ex:
                    result_container["error"] = ex
                finally:
                    result_container["done"] = True

            gen_thread = threading.Thread(target=generation_thread)
            gen_thread.daemon = True
            gen_thread.start()

            # Yksinkertainen polling thread
            def simple_monitor():
                import time

                timeout = 120  # 2 minuuttia
                start_time = time.time()

                while (
                    not result_container["done"]
                    and (time.time() - start_time) < timeout
                ):
                    time.sleep(0.5)

                # UI-päivitys
                if result_container["error"]:
                    progress_dlg.open = False
                    page.update()
                    print(f"❌ Virhe: {result_container['error']}")
                elif result_container["done"]:
                    added = result_container["added"]
                    progress_text.value = f"✅ Analyysi valmis! ({added} löydöstä)"
                    progress_bar.value = 1.0

                    def simple_close(e):
                        progress_dlg.open = False
                        page.update()

                    ok_button = ft.TextButton("OK", on_click=simple_close)
                    progress_dlg.actions = [ok_button]
                    page.update()

            # Käynnistä yksinkertainen monitor
            monitor_thread = threading.Thread(target=simple_monitor, daemon=True)
            monitor_thread.start()

        except Exception as e:
            # Virhe - näytä virheilmoitus
            def show_error():
                # Sulje progress dialog jos auki
                try:
                    if "progress_dlg" in locals() and progress_dlg.open:
                        progress_dlg.open = False
                        if progress_dlg in page.overlay:
                            page.overlay.remove(progress_dlg)
                except:
                    pass

                sb = ft.SnackBar(
                    ft.Text(f"❌ Virhe: {str(e)}"),
                    bgcolor=ft.Colors.RED_600,
                    action="OK",
                    action_color=ft.Colors.WHITE,
                )
                if sb not in page.overlay:
                    page.overlay.append(sb)
                sb.open = True
                page.update()

            try:
                page.run_thread(show_error)
            except Exception as ex:
                print(f"Virhe error-threadin käynnistämisessä: {ex}")

    # Aja worker thread
    worker_thread = threading.Thread(target=worker, daemon=True)
    worker_thread.start()

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
        print("🔍 Debug: Etsitään app-objektia page-objektista...")

        # Kokeile ensin page.app (suora tallennus)
        if hasattr(page, "app") and hasattr(page.app, "results_downtrend_filter"):
            app = page.app
            print("🔍 Debug: App löytyi page.app:sta")
        # Kokeile page.data
        elif hasattr(page, "data") and hasattr(page.data, "results_downtrend_filter"):
            app = page.data
            print("🔍 Debug: App löytyi page.data:sta")
        else:
            # Etsi kaikista page-objektin attribuuteista
            for attr_name in dir(page):
                try:
                    attr = getattr(page, attr_name)
                    if hasattr(attr, "results_downtrend_filter"):
                        app = attr
                        print(f"🔍 Debug: App löytyi {attr_name}-attribuutista")
                        break
                except Exception:
                    continue

        if app is None:
            print("❌ Debug: App-objektia ei löytynyt!")
        else:
            print(f"🔍 Debug: App-objekti löytyi: {type(app)}")

        paivita_results_csv(page, app)


def generate_results_now(
    write: bool = True,
    downtrend_filter: bool = False,
    min_decline_percent: float = 3.0,
    use_ma_filter: bool = True,
    use_volume_filter: bool = False,
    progress_callback=None,
):
    """Generoi results.xlsx tiedosto

    Args:
        write: Kirjoitetaanko tiedostoon vai palautetaanko vain rivimäärä
        downtrend_filter: Suodatetaanko vain laskutrendien kynttilät
        min_decline_percent: Minimalasku prosentteina
        use_ma_filter: Käytetäänkö liukuva keskiarvo -suodatinta
        use_volume_filter: Käytetäänkö volyymi-suodatinta
        progress_callback: Callback-funktio edistymisen raportointiin
    """
    base = Path(__file__).resolve().parents[1]
    analysis_db = base / "analysis" / "analysis.db"
    osake_db = base / "data" / "osakedata.db"
    excel_path = base / "data" / "results.xlsx"

    if progress_callback:
        progress_callback("🔍 Analysoidaan tietoja...", 0.1)

    header, output_rows = _build_output_rows(
        analysis_db,
        osake_db,
        downtrend_filter,
        min_decline_percent,
        use_ma_filter,
        use_volume_filter,
        progress_callback,
    )

    if not output_rows:
        return 0

    added = len(output_rows)

    if write:
        if progress_callback:
            progress_callback("📊 Luodaan Excel-tiedostoa...", 0.8)

        # Luodaan Excel-tiedosto
        success = _create_excel_file(header, output_rows, excel_path, downtrend_filter)

        if success:
            print(f"✅ Excel-tiedosto luotu: {excel_path}")
        else:
            print("❌ Excel-tiedoston luonti epäonnistui")

        if progress_callback:
            progress_callback("✅ Valmis!", 1.0)

    return added


def generate_excel_optimized(
    excel_path: str = "data/results.xlsx",
    progress_callback=None,
    analysis_db: str = "analysis/analysis.db",
    osake_db: str = "data/osakedata.db",
    force_rebuild: bool = False,
    limit_rows: int = None,
    ticker_filter: str = None,
) -> int:
    """
    Optimoitu Excel-generointi staging-tietokannan avulla.

    Args:
        excel_path: Polku Excel-tiedostoon
        progress_callback: Funktio progress-päivityksille
        analysis_db: Polku analysis.db tietokantaan
        osake_db: Polku osakedata.db tietokantaan
        force_rebuild: Pakota staging-taulun uudelleenrakennus
        limit_rows: Rajoita rivien määrä (None = ei rajoitusta, testikäyttöön)
        ticker_filter: Rajoita tiettyyn tickeriin (None = kaikki tickerit)

    Returns:
        int: Löydösten määrä
    """

    try:
        # Luo cache-objekti
        cache = ExcelResultsCache(
            analysis_db_path=analysis_db,
            osake_db_path=osake_db,
            results_db_path="data/results.db",
        )

        # Tarkista onko cache tuore (mutta pakota rebuild jos ticker-filtteri käytössä)
        cache_is_fresh = not force_rebuild and cache.is_cache_fresh()
        print(
            f"🔍 Debug: force_rebuild={force_rebuild}, cache.is_cache_fresh()={cache.is_cache_fresh()}"
        )

        # Jos ticker-filtteri on käytössä, pakota rebuild
        if ticker_filter:
            print(
                f"🎯 Ticker-filtteri ({ticker_filter}) aktiivinen - pakotetaan rebuild"
            )
            cache_is_fresh = False

        print(f"🔍 Debug: cache_is_fresh={cache_is_fresh}")

        if cache_is_fresh:
            if progress_callback:
                progress_callback("📊 Käytetään cache-dataa...", 50, 100)

            # Nopea export staging-taulusta
            success = cache.export_to_excel_fast(
                excel_path, limit_rows=limit_rows, ticker_filter=ticker_filter
            )

            if success:
                stats = cache.get_staging_stats()
                if progress_callback:
                    progress_callback("✅ Valmis!", 100, 100)
                return stats.get("total_rows", 0)
            else:
                # Jos nopea export epäonnistui, rebuild cache
                force_rebuild = True

        if force_rebuild or not cache.is_cache_fresh():
            if progress_callback:
                progress_callback("🔄 Rakennetaan cache...", 10, 100)

            # Rebuild staging-taulu
            def cache_progress(step, current, total):
                # Skaalaa progress 10-90% välille
                scaled_progress = 10 + int((current / total) * 80)
                if progress_callback:
                    progress_callback(step, scaled_progress, 100)

            cache.rebuild_staging_optimized(
                cache_progress, limit_rows=limit_rows, ticker_filter=ticker_filter
            )

            if progress_callback:
                progress_callback("📊 Luodaan Excel-tiedostoa...", 90, 100)

            # Export Exceliin
            success = cache.export_to_excel_fast(
                excel_path, limit_rows=limit_rows, ticker_filter=ticker_filter
            )

            if success:
                stats = cache.get_staging_stats()
                if progress_callback:
                    progress_callback("✅ Valmis!", 100, 100)
                return stats.get("total_rows", 0)
            else:
                if progress_callback:
                    progress_callback("❌ Excel-generointi epäonnistui", 100, 100)
                return 0

        return 0

    except Exception as e:
        error_msg = f"❌ Virhe optimoidussa Excel-generoinnissa: {e}"
        print(error_msg)
        if progress_callback:
            progress_callback(error_msg, 100, 100)

        # Fallback: käytä vanhaa algoritmia
        print("🔄 Yritetään vanhaa algoritmia...")

        # Vanhan algoritmin progress callback on erilainen
        def old_progress_callback(message, progress):
            if progress_callback:
                # Muunna progress (0.0-1.0) -> (current, total) muotoon
                current = int(progress * 100)
                total = 100
                progress_callback(message, current, total)

        return generate_results_now(
            write=True,
            downtrend_filter=True,
            min_decline_percent=1.0,
            use_ma_filter=False,
            use_volume_filter=False,
            progress_callback=old_progress_callback,
        )
