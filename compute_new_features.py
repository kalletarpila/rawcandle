#!/usr/bin/env python3
"""
compute_new_features.py

Laskee uudet feature-sarakkeet results_data-tauluun ja tallentaa ne analysis.db-kantaan.

Featuret:
  1. RSI_slope_5
  2. Price_slope_5
  3. Price_slope_10
  4. Price_acceleration_5_10
  5. Volatility_ratio_10_20
  6. Gap_down_strength
  7. Body_ratio
  8. Shadow_ratio
  9. SPX_volatility_10
 10. NDX_volatility_10
 11. Volume_impulse
 12. Reversal_Context_Score

Puuttuvat lähtösarakkeet eivät kaada skriptiä: niistä logitetaan varoitus
ja kyseinen feature jää NaN-arvoihin.
"""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent
DB_PATH = PROJECT_ROOT / "data" / "analysis.db"
STOCK_DB_PATH = PROJECT_ROOT / "data" / "osakedata.db"
RESULTS_TABLE = "results_data"
DIVERGENCE_TABLE = "divergence_data"
OSAKEDATA_TABLE = "osakedata"
INDEX_TICKERS = {"SPX": "^GSPC", "NDX": "^NDX"}
BULLISH_COLUMNS = [
    "BullDiv_recent_strength",
    "bullish_divergence",
    "Bullish Divergence",
]

NEW_COLUMNS = {
    "RSI_slope_5": "REAL",
    "Price_slope_5": "REAL",
    "Price_slope_10": "REAL",
    "Price_acceleration_5_10": "REAL",
    "Volatility_ratio_10_20": "REAL",
    "Gap_down_strength": "REAL",
    "Body_ratio": "REAL",
    "Shadow_ratio": "REAL",
    "SPX_volatility_10": "REAL",
    "NDX_volatility_10": "REAL",
    "Volume_impulse": "REAL",
    "Reversal_Context_Score": "REAL",
    "BullDiv_strength": "REAL",
    "BullDiv_recent_strength": "REAL",
    "BullDiv_recent_offset": "INTEGER",
    "Has_BullDiv_recent": "INTEGER",
}


@dataclass
class FeatureEnrichmentSummary:
    total_rows: int
    updated_columns: List[str]
    backup_path: Optional[str] = None


def backup_database(db_path: Path) -> Path:
    backup_dir = db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"analysis_backup_{timestamp}.db"
    shutil.copy2(db_path, backup_path)
    print(f"Varmuuskopio luotu: {backup_path}")
    return backup_path


def ensure_columns(conn: sqlite3.Connection, columns: Dict[str, str]) -> None:
    """Lisää puuttuvat sarakkeet results_data-tauluun."""
    cursor = conn.execute(f"PRAGMA table_info({RESULTS_TABLE})")
    existing = {row[1] for row in cursor.fetchall()}

    for column, ddl in columns.items():
        if column not in existing:
            print(f"Lisätään sarake {column} tauluun {RESULTS_TABLE}...")
            conn.execute(f"ALTER TABLE {RESULTS_TABLE} ADD COLUMN {column} {ddl}")
            conn.commit()


def load_results(conn: sqlite3.Connection) -> pd.DataFrame:
    query = f"SELECT * FROM {RESULTS_TABLE}"
    df = pd.read_sql_query(query, conn)
    if "date" not in df.columns:
        raise ValueError("results_data taulusta puuttuu date-sarake.")
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def load_divergence(conn: sqlite3.Connection) -> pd.DataFrame:
    query = f"""
        SELECT ticker, date, rsi
        FROM {DIVERGENCE_TABLE}
    """
    df = pd.read_sql_query(query, conn)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def load_divergence_strengths(conn: sqlite3.Connection) -> pd.DataFrame:
    query = f"""
        SELECT ticker, date, bullish_strength
        FROM {DIVERGENCE_TABLE}
    """
    df = pd.read_sql_query(query, conn)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["bullish_strength"] = df["bullish_strength"].fillna(0.0)
    return df


def compute_rsi_slope(df_results: pd.DataFrame, df_div: pd.DataFrame) -> pd.Series:
    """Palauta RSI_slope_5 sarake."""
    if "RSI14_t0" not in df_results.columns:
        print("⚠️ Sarake RSI14_t0 puuttuu results_data-taulusta. RSI_slope_5 jätetään NaN-arvoihin.")
        return pd.Series(np.nan, index=df_results.index)

    if df_div.empty:
        print("⚠️ divergence_data taulu on tyhjä. RSI_slope_5 jätetään NaN-arvoihin.")
        return pd.Series(np.nan, index=df_results.index)

    div_sorted = df_div.sort_values(["ticker", "date"]).copy()
    div_sorted["RSI14_t_minus5"] = div_sorted.groupby("ticker")["rsi"].shift(5)
    lookup = div_sorted[["ticker", "date", "RSI14_t_minus5"]]

    base = df_results[["ticker", "date", "RSI14_t0"]].copy()
    base["_row_id"] = df_results.index

    merged = base.merge(lookup, on=["ticker", "date"], how="left")
    merged = merged.set_index("_row_id").reindex(df_results.index)

    slope = merged["RSI14_t0"] - merged["RSI14_t_minus5"]
    slope.name = "RSI_slope_5"
    return slope


def compute_price_slope(df_results: pd.DataFrame, column: str, horizon: int) -> pd.Series:
    """Laske (100 - t_h) / h, palauttaa NaN jos sarake puuttuu."""
    if column not in df_results.columns:
        print(f"⚠️ Sarake {column} puuttuu results_data-taulusta. Jätetään Price_slope_{horizon} NaN:ksi.")
        return pd.Series(np.nan, index=df_results.index)
    slope = (100.0 - df_results[column]) / float(horizon)
    slope.name = f"Price_slope_{horizon}"
    return slope


def compute_price_acceleration(df: pd.DataFrame) -> pd.Series:
    if "Price_slope_5" not in df.columns or "Price_slope_10" not in df.columns:
        print("⚠️ Price_slope_5 tai Price_slope_10 puuttuu. Price_acceleration_5_10 jää NaN:ksi.")
        return pd.Series(np.nan, index=df.index)
    accel = df["Price_slope_5"] - df["Price_slope_10"]
    accel.name = "Price_acceleration_5_10"
    return accel


def compute_volatility_ratio(df: pd.DataFrame) -> pd.Series:
    if "t_10_hajonta" not in df.columns or "t_20_hajonta" not in df.columns:
        print("⚠️ Volatiliteettisarakkeita puuttuu. Volatility_ratio_10_20 jää NaN:ksi.")
        return pd.Series(np.nan, index=df.index)
    denom = df["t_20_hajonta"].replace(0, np.nan)
    ratio = df["t_10_hajonta"] / denom
    ratio.name = "Volatility_ratio_10_20"
    return ratio


def fetch_raw_price_history(
    conn: sqlite3.Connection,
    tickers: List[str],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    if not tickers:
        return pd.DataFrame()

    frames = []
    chunk_size = 500
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")

    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        placeholders = ",".join("?" * len(chunk))
        query = f"""
            SELECT osake AS ticker, pvm AS date, open, high, low, close, volume
            FROM {OSAKEDATA_TABLE}
            WHERE osake IN ({placeholders})
              AND pvm BETWEEN ? AND ?
        """
        params = chunk + [start_str, end_str]
        frame = pd.read_sql_query(query, conn, params=params)
        frames.append(frame)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values(["ticker", "date"])
    return df


def load_price_history(
    conn: sqlite3.Connection,
    tickers: List[str],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> pd.DataFrame:
    raw = fetch_raw_price_history(conn, tickers, start_date, end_date)
    if raw.empty:
        return raw
    raw["prev_close"] = raw.groupby("ticker")["close"].shift(1)
    raw["prev10_avg_volume"] = (
        raw.groupby("ticker")["volume"]
        .transform(lambda s: s.shift(1).rolling(window=10, min_periods=10).mean())
    )
    return raw


def merge_price_features(df_results: pd.DataFrame, df_price: pd.DataFrame) -> pd.DataFrame:
    if df_price.empty:
        print("⚠️ osakedata-taulusta ei löytynyt hintahistoriaa. Gap/volyymi featuret jäävät NaN:ksi.")
        for col in ["open_raw", "high_raw", "low_raw", "close_raw", "volume_raw", "prev_close_raw", "prev10_avg_volume"]:
            df_results[col] = np.nan
        return df_results

    price = df_price.rename(
        columns={
            "open": "open_raw",
            "high": "high_raw",
            "low": "low_raw",
            "close": "close_raw",
            "volume": "volume_raw",
            "prev_close": "prev_close_raw",
        }
    )
    merged = df_results.merge(
        price[["ticker", "date", "open_raw", "high_raw", "low_raw", "close_raw", "volume_raw", "prev_close_raw", "prev10_avg_volume"]],
        on=["ticker", "date"],
        how="left",
    )
    return merged


def compute_gap_body_shadow(df: pd.DataFrame) -> None:
    open_raw = df["open_raw"]
    close_raw = df["close_raw"]
    low_raw = df["low_raw"]
    high_raw = df["high_raw"]
    prev_close = df["prev_close_raw"]

    # Gap: log1p-asteikolla ja suojauksella
    eps = 1e-6
    gap = (open_raw - prev_close) / (prev_close + eps)
    log_gap = np.log1p(np.abs(gap)) * np.sign(gap)
    df["Gap_down_strength"] = log_gap

    range_val = high_raw - low_raw
    body = (close_raw - open_raw).abs()
    df["Body_ratio"] = body / range_val.replace(0, np.nan)

    upper = high_raw - np.maximum(open_raw, close_raw)
    lower = np.minimum(open_raw, close_raw) - low_raw
    eps = 1e-6
    ratio_raw = lower / (upper + eps)
    df["Shadow_ratio"] = np.log1p(ratio_raw)


def compute_index_volatility_from_history(
    df_results: pd.DataFrame,
    history: pd.DataFrame,
    name: str,
) -> pd.Series:
    if history.empty:
        print(f"⚠️ {name}: indeksihistoria puuttuu. Jätetään NaN:ksi.")
        return pd.Series(np.nan, index=df_results.index)

    history = history.sort_values("date").copy()
    history["volatility_10"] = (
        history.groupby("ticker")["close"]
        .transform(lambda s: s.shift(1).rolling(window=10, min_periods=10).std(ddof=0))
    )

    merged = df_results[["date"]].merge(
        history[["date", "volatility_10"]],
        on="date",
        how="left",
    )
    return merged["volatility_10"].rename(name)


def compute_volume_impulse(df: pd.DataFrame) -> pd.Series:
    vol = df["volume_raw"]
    avg = df["prev10_avg_volume"]
    impulse = vol / avg.replace(0, np.nan)
    impulse.name = "Volume_impulse"
    return impulse


def compute_reversal_context(df: pd.DataFrame) -> pd.Series:
    divergence_col = next((col for col in BULLISH_COLUMNS if col in df.columns), None)
    if divergence_col is None:
        print(
            "⚠️ Bullish divergence -sarake puuttuu. Reversal_Context_Score jää NaN:ksi."
        )
        return pd.Series(np.nan, index=df.index)

    required = ["t_10", divergence_col, "t_10_hajonta"]
    for col in required:
        if col not in df.columns:
            print(f"⚠️ Sarake {col} puuttuu. Reversal_Context_Score jää NaN:ksi.")
            return pd.Series(np.nan, index=df.index)
    drop_10 = 100.0 - df["t_10"]
    score = 0.4 * drop_10 + 0.4 * df[divergence_col] - 0.2 * df["t_10_hajonta"]
    score.name = "Reversal_Context_Score"
    return score


def compute_bull_divergence_features(
    df_results: pd.DataFrame, df_divergence: pd.DataFrame
) -> pd.DataFrame:
    """Laske BullDiv_* sarakkeet divergence_data:n perusteella (0..5 pv taakse)."""
    columns = [
        "BullDiv_strength",
        "BullDiv_recent_strength",
        "BullDiv_recent_offset",
        "Has_BullDiv_recent",
    ]
    if df_results.empty:
        for col in columns:
            if col not in df_results:
                df_results[col] = []
        return df_results

    defaults = {
        "BullDiv_strength": 0.0,
        "BullDiv_recent_strength": 0.0,
        "BullDiv_recent_offset": -1,
        "Has_BullDiv_recent": 0,
    }

    if df_divergence.empty:
        for col, default in defaults.items():
            df_results[col] = default
        return df_results

    df_results = df_results.copy()
    df_results["date"] = pd.to_datetime(df_results["date"], errors="coerce")

    df_div = df_divergence.dropna(subset=["date"]).copy()
    df_div["date"] = pd.to_datetime(df_div["date"], errors="coerce")
    df_div = df_div.dropna(subset=["date"])
    df_div["BullDiv_strength"] = df_div["bullish_strength"].fillna(0.0)

    # Alusta oletusarvot
    for col, default in defaults.items():
        df_results[col] = default

    if df_div.empty:
        df_results["BullDiv_recent_offset"] = df_results["BullDiv_recent_offset"].astype(int)
        df_results["Has_BullDiv_recent"] = df_results["Has_BullDiv_recent"].astype(int)
        return df_results

    # Laske jokaiselle riville: sama päivän strength, 0..5 pv takaisen max strength ja offset lähimpään divergenssiin
    window_days = 5
    for ticker, res_grp in df_results.groupby("ticker"):
        res_idx = res_grp.index
        res_dates = res_grp["date"].sort_values()
        div_grp = df_div[df_div["ticker"] == ticker].sort_values("date")
        if div_grp.empty:
            continue

        div_dates = div_grp["date"].to_numpy()
        div_strengths = div_grp["BullDiv_strength"].to_numpy()

        # Käytetään liukuvaa ikkunaa (pointers) eteenpäin
        from collections import deque

        window = deque()
        d_idx = 0
        window_start = pd.Timedelta(days=window_days)

        # Tallennetaan tulokset väliaikaisiin listoihin (index -> value)
        same_day_strength = {}
        recent_strength = {}
        recent_offset = {}

        for res_date in res_dates:
            # Lisää ikkunaan kaikki divergenssit päivään res_date asti
            while d_idx < len(div_dates) and div_dates[d_idx] <= res_date:
                window.append((div_dates[d_idx], div_strengths[d_idx]))
                d_idx += 1

            # Poista ikkunasta divergenssit, jotka ovat yli window_days vanhoja
            while window and (res_date - window[0][0]) > window_start:
                window.popleft()

            # Sama päivän strength
            same_day_strength[res_date] = 0.0
            if window and window[-1][0] == res_date:
                same_day_strength[res_date] = window[-1][1]

            # Max strength ja offset (lähin menneisyydessä)
            positives = [(res_date - dt).days for dt, s in window if s and s > 0]
            if positives:
                offsets = [(res_date - dt).days for dt, s in window if s and s > 0]
                nearest_offset = min(offsets)
                max_strength = max(s for _, s in window if s and s > 0)
                recent_strength[res_date] = max_strength
                recent_offset[res_date] = nearest_offset
            else:
                recent_strength[res_date] = 0.0
                recent_offset[res_date] = -1

        # Kirjoita tulokset takaisin df_results tickerin riveille
        res_dates_series = res_grp["date"]
        df_results.loc[res_idx, "BullDiv_strength"] = res_dates_series.map(
            lambda d: same_day_strength.get(d, 0.0)
        ).fillna(0.0)
        df_results.loc[res_idx, "BullDiv_recent_strength"] = res_dates_series.map(
            lambda d: recent_strength.get(d, 0.0)
        ).fillna(0.0)
        df_results.loc[res_idx, "BullDiv_recent_offset"] = res_dates_series.map(
            lambda d: recent_offset.get(d, -1)
        ).fillna(-1)
        df_results.loc[res_idx, "Has_BullDiv_recent"] = (
            df_results.loc[res_idx, "BullDiv_recent_strength"] > 0
        ).astype(int)

    df_results["BullDiv_recent_offset"] = df_results["BullDiv_recent_offset"].astype(int)
    df_results["Has_BullDiv_recent"] = df_results["Has_BullDiv_recent"].astype(int)
    return df_results


def update_features(conn: sqlite3.Connection, df: pd.DataFrame, columns: Iterable[str]) -> None:
    """Päivitä annetut sarakkeet results_data-tauluun."""
    placeholders = ", ".join(f"{col} = ?" for col in columns)
    sql = f"UPDATE {RESULTS_TABLE} SET {placeholders} WHERE id = ?"

    values = df[list(columns)].assign(id=df["id"]).values.tolist()
    with conn:
        conn.executemany(sql, values)


def run_feature_enrichment(
    analysis_db_path: str | Path = DB_PATH,
    stock_db_path: str | Path = STOCK_DB_PATH,
    *,
    create_backup: bool = True,
    verbose: bool = True,
) -> FeatureEnrichmentSummary:
    analysis_path = Path(analysis_db_path)
    if not analysis_path.exists():
        raise FileNotFoundError(f"SQLite-kantaa ei löydy: {analysis_path}")

    backup_path = backup_database(analysis_path) if create_backup else None
    conn = sqlite3.connect(analysis_path)
    price_conn = None
    ensure_columns(conn, NEW_COLUMNS)

    df_results = load_results(conn)
    if df_results.empty:
        conn.close()
        if price_conn:
            price_conn.close()
        return FeatureEnrichmentSummary(
            total_rows=0,
            updated_columns=list(NEW_COLUMNS.keys()),
            backup_path=str(backup_path) if backup_path else None,
        )

    df_div = load_divergence(conn)
    df_div_strengths = load_divergence_strengths(conn)
    min_date = df_results["date"].min() - timedelta(days=30)
    max_date = df_results["date"].max()

    stock_path = Path(stock_db_path) if stock_db_path else None
    if stock_path and stock_path.exists():
        price_conn = sqlite3.connect(stock_path)
        price_source = price_conn
    else:
        if verbose:
            print(
                f"⚠️ Osakedata-kantaa ei löytynyt polusta {stock_db_path}. Gap/volyymi featuret jäävät NaN:ksi."
            )
        price_source = conn

    df_price = load_price_history(
        price_source,
        df_results["ticker"].dropna().unique().tolist(),
        min_date,
        max_date,
    )
    df_results = merge_price_features(df_results, df_price)

    index_histories = {}
    for key, ticker in INDEX_TICKERS.items():
        history = fetch_raw_price_history(
            price_source, [ticker], min_date - timedelta(days=5), max_date
        )
        index_histories[key] = history

    df_results["RSI_slope_5"] = compute_rsi_slope(df_results, df_div)
    df_results["Price_slope_5"] = compute_price_slope(df_results, "t_5", 5)
    df_results["Price_slope_10"] = compute_price_slope(df_results, "t_10", 10)
    df_results["Price_acceleration_5_10"] = compute_price_acceleration(df_results)
    df_results["Volatility_ratio_10_20"] = compute_volatility_ratio(df_results)

    compute_gap_body_shadow(df_results)
    df_results["SPX_volatility_10"] = compute_index_volatility_from_history(
        df_results, index_histories.get("SPX", pd.DataFrame()), "SPX_volatility_10"
    )
    df_results["NDX_volatility_10"] = compute_index_volatility_from_history(
        df_results, index_histories.get("NDX", pd.DataFrame()), "NDX_volatility_10"
    )
    df_results["Volume_impulse"] = compute_volume_impulse(df_results)
    df_results["Reversal_Context_Score"] = compute_reversal_context(df_results)
    df_results = compute_bull_divergence_features(df_results, df_div_strengths)

    update_cols = list(NEW_COLUMNS.keys())
    if verbose:
        print("Päivitetään uudet feature-sarakkeet kantaan...")
    update_features(conn, df_results, update_cols)

    summary = FeatureEnrichmentSummary(
        total_rows=len(df_results),
        updated_columns=update_cols,
        backup_path=str(backup_path) if backup_path else None,
    )

    if verbose:
        print("Valmis.")
        print(f"Rivejä: {summary.total_rows}")
        print(f"Lisätyt sarakkeet: {', '.join(summary.updated_columns)}")
        if summary.backup_path:
            print(f"Varmuuskopio: {summary.backup_path}")

    conn.close()
    if price_conn:
        price_conn.close()

    return summary


def main() -> None:
    run_feature_enrichment()


if __name__ == "__main__":
    main()
