#!/usr/bin/env python3
"""
Recompute history-normalized fields in results_data using t0_low as the base.

Affected columns (normalized to t0_low instead of t0_close):
- t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour
- t_2, t_5, t_10, t_15, t_20
- t_2_hajonta, t_5_hajonta, t_10_hajonta, t_15_hajonta, t_20_hajonta
- t_2_5p_liukuva, t_2_10p_liukuva, t_2_20p_liukuva, t_5_5p_liukuva, t_5_10p_liukuva,
  t_5_20p_liukuva, t_10_5p_liukuva, t_10_10p_liukuva, t_10_20p_liukuva,
  t_15_5p_liukuva, t_15_10p_liukuva, t_15_20p_liukuva,
  t_20_5p_liukuva, t_20_10p_liukuva, t_20_20p_liukuva,
  t0_20p_liukuva, t0_50p_liukuva, t0_200p_liukuva
- Price_slope_5, Price_slope_10, Price_acceleration_5_10
- Volatility_ratio_10_20
- t0_50p_slope, t0_200p_slope
- ATR_ratio_14
- Gap_down_strength (nyt (open_t0 - close_t-1) / t0_low * 100, neg gap -> >0, muutoin 0)

Default mode is dry-run; use --apply to write updates.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

HISTORY_COLUMNS = [
    "t_1_alin",
    "t_1_ylin",
    "t_1_bodi",
    "t_1_bodi_colour",
    "t_2",
    "t_5",
    "t_10",
    "t_15",
    "t_20",
    "t_2_hajonta",
    "t_5_hajonta",
    "t_10_hajonta",
    "t_15_hajonta",
    "t_20_hajonta",
    "t_2_5p_liukuva",
    "t_2_10p_liukuva",
    "t_2_20p_liukuva",
    "t_5_5p_liukuva",
    "t_5_10p_liukuva",
    "t_5_20p_liukuva",
    "t_10_5p_liukuva",
    "t_10_10p_liukuva",
    "t_10_20p_liukuva",
    "t_15_5p_liukuva",
    "t_15_10p_liukuva",
    "t_15_20p_liukuva",
    "t_20_5p_liukuva",
    "t_20_10p_liukuva",
    "t_20_20p_liukuva",
    "t0_20p_liukuva",
    "t0_50p_liukuva",
    "t0_200p_liukuva",
    "Price_slope_5",
    "Price_slope_10",
    "Price_acceleration_5_10",
    "Volatility_ratio_10_20",
    "t0_50p_slope",
    "t0_200p_slope",
    "ATR_ratio_14",
    "Gap_down_strength",
]


@dataclass
class RowUpdate:
    row_id: int
    values: Dict[str, Optional[float]]


def _safe_float(value: object) -> Optional[float]:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _pstdev_safe(values: List[float]) -> Optional[float]:
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    try:
        return pstdev(vals)
    except Exception:
        return None


def _calc_candle_details(row, base_norm: Optional[float]) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[int]]:
    if row is None:
        return None, None, None, None
    low = _safe_float(row.get("low"))
    high = _safe_float(row.get("high"))
    open_val = _safe_float(row.get("open"))
    close_val = _safe_float(row.get("close"))
    if any(x is None for x in (low, high, open_val, close_val)):
        return None, None, None, None
    norm_low = (low / base_norm * 100) if base_norm and base_norm > 0 else None
    norm_high = (high / base_norm * 100) if base_norm and base_norm > 0 else None
    candle_range = high - low
    body_size = abs(close_val - open_val)
    body_percent = (body_size / candle_range * 100) if candle_range > 0 else 0
    color = 1 if close_val > open_val else 0
    return norm_low, norm_high, body_percent, color


def _calc_ma_series(closes: List[Optional[float]], end_idx: int, period: int) -> Optional[float]:
    start_idx = end_idx - period + 1
    if start_idx < 0 or end_idx >= len(closes):
        return None
    window = closes[start_idx : end_idx + 1]
    window = [v for v in window if v is not None]
    if len(window) != period:
        return None
    return mean(window)


def _calc_ma_normalized(closes: List[Optional[float]], end_idx: int, period: int, base_low: Optional[float]) -> Optional[float]:
    ma_val = _calc_ma_series(closes, end_idx, period)
    if ma_val is None or not base_low or base_low <= 0:
        return None
    return (ma_val / base_low) * 100.0


def _calc_slope(closes: List[Optional[float]], end_idx: int, period: int, base_low: Optional[float], lookback: int = 5) -> Optional[float]:
    if end_idx - lookback < 0:
        return None
    ma_today = _calc_ma_series(closes, end_idx, period)
    ma_prev = _calc_ma_series(closes, end_idx - lookback, period)
    if ma_today is None or ma_prev is None or not base_low or base_low <= 0:
        return None
    return ((ma_today - ma_prev) / lookback) / base_low * 100.0


def _calc_atr(stock_df: pd.DataFrame, end_idx: int, period: int = 14) -> Optional[float]:
    if end_idx - period < 0:
        return None
    trs: List[float] = []
    for i in range(end_idx - period + 1, end_idx + 1):
        if i <= 0:
            continue
        curr = stock_df.iloc[i]
        prev = stock_df.iloc[i - 1]
        curr_high = _safe_float(curr["high"])
        curr_low = _safe_float(curr["low"])
        prev_close = _safe_float(prev["close"])
        if curr_high is None or curr_low is None or prev_close is None:
            continue
        tr = max(
            curr_high - curr_low,
            abs(curr_high - prev_close),
            abs(curr_low - prev_close),
        )
        trs.append(tr)
    if len(trs) < period * 0.7:
        return None
    return mean(trs)


def _calc_volatility(closes: List[Optional[float]], idx: int, days_back: int, base_low: Optional[float]) -> Optional[float]:
    if idx - days_back < 0 or not base_low or base_low <= 0:
        return None
    start_idx = idx - days_back
    end_idx = idx - 1
    subset = closes[start_idx : end_idx + 1]
    norm = []
    for v in subset:
        if v is None:
            continue
        norm.append((v / base_low) * 100)
    return _pstdev_safe(norm)


def _calc_gap(prev_close: Optional[float], t0_open: Optional[float], t0_low: Optional[float]) -> Optional[float]:
    if prev_close is None or prev_close <= 0 or t0_open is None or t0_low is None or t0_low <= 0:
        return None
    gap_value = ((t0_open - prev_close) / t0_low) * 100.0
    return abs(gap_value) if gap_value < 0 else 0.0


def _calc_price_slope(norm_value: Optional[float], horizon: int) -> Optional[float]:
    if norm_value is None or horizon <= 0:
        return None
    try:
        return (100.0 - float(norm_value)) / float(horizon)
    except Exception:
        return None


def recompute_for_ticker(stock_df: pd.DataFrame, result_rows: Iterable[Tuple[int, str]]) -> List[RowUpdate]:
    """
    stock_df: DataFrame osakedatasta yhdelle tickerille, sarakkeet [pvm, open, high, low, close] sorted ascending
    result_rows: iterable of (id, date_str) for results_data
    """
    updates: List[RowUpdate] = []
    if stock_df.empty:
        return updates
    stock_df = stock_df.copy()
    stock_df["pvm"] = pd.to_datetime(stock_df["pvm"])
    stock_df = stock_df.sort_values("pvm").reset_index(drop=True)
    date_to_idx = {d.date(): i for i, d in enumerate(stock_df["pvm"])}
    closes = [_safe_float(v) for v in stock_df["close"].tolist()]

    for row_id, date_str in result_rows:
        date_dt = pd.to_datetime(date_str, errors="coerce")
        if pd.isna(date_dt):
            continue
        idx = date_to_idx.get(date_dt.date())
        if idx is None:
            continue
        t0_row = stock_df.iloc[idx]
        t0_low = _safe_float(t0_row["low"])
        t0_close = _safe_float(t0_row["close"])
        if t0_low is None or t0_low <= 0 or t0_close is None or t0_close <= 0:
            continue

        # t-1 candle
        r_m1 = stock_df.iloc[idx - 1] if idx > 0 else None
        t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour = _calc_candle_details(
            r_m1, t0_low
        )

        def get_close(offset: int) -> Optional[float]:
            target = idx + offset
            if target < 0 or target >= len(stock_df):
                return None
            return _safe_float(stock_df.iloc[target]["close"])

        t_2 = (get_close(-2) / t0_low * 100) if get_close(-2) is not None else None
        t_5 = (get_close(-5) / t0_low * 100) if get_close(-5) is not None else None
        t_10 = (get_close(-10) / t0_low * 100) if get_close(-10) is not None else None
        t_15 = (get_close(-15) / t0_low * 100) if get_close(-15) is not None else None
        t_20 = (get_close(-20) / t0_low * 100) if get_close(-20) is not None else None

        t_2_hajonta = _calc_volatility(closes, idx, 2, t0_low)
        t_5_hajonta = _calc_volatility(closes, idx, 5, t0_low)
        t_10_hajonta = _calc_volatility(closes, idx, 10, t0_low)
        t_15_hajonta = _calc_volatility(closes, idx, 15, t0_low)
        t_20_hajonta = _calc_volatility(closes, idx, 20, t0_low)

        def ma_norm(days_offset: int, period: int) -> Optional[float]:
            end_idx = idx + days_offset
            return _calc_ma_normalized(closes, end_idx, period, t0_low)

        t_2_5p_liukuva = ma_norm(-2, 5)
        t_2_10p_liukuva = ma_norm(-2, 10)
        t_2_20p_liukuva = ma_norm(-2, 20)
        t_5_5p_liukuva = ma_norm(-5, 5)
        t_5_10p_liukuva = ma_norm(-5, 10)
        t_5_20p_liukuva = ma_norm(-5, 20)
        t_10_5p_liukuva = ma_norm(-10, 5)
        t_10_10p_liukuva = ma_norm(-10, 10)
        t_10_20p_liukuva = ma_norm(-10, 20)
        t_15_5p_liukuva = ma_norm(-15, 5)
        t_15_10p_liukuva = ma_norm(-15, 10)
        t_15_20p_liukuva = ma_norm(-15, 20)
        t_20_5p_liukuva = ma_norm(-20, 5)
        t_20_10p_liukuva = ma_norm(-20, 10)
        t_20_20p_liukuva = ma_norm(-20, 20)
        t0_20p_liukuva = ma_norm(0, 20)
        t0_50p_liukuva = ma_norm(0, 50)
        t0_200p_liukuva = ma_norm(0, 200)

        price_slope_5 = _calc_price_slope(t_5, 5)
        price_slope_10 = _calc_price_slope(t_10, 10)
        price_acceleration_5_10 = (
            price_slope_5 - price_slope_10
            if price_slope_5 is not None and price_slope_10 is not None
            else None
        )

        volatility_ratio_10_20 = (
            t_10_hajonta / t_20_hajonta
            if t_10_hajonta is not None and t_20_hajonta not in (None, 0)
            else None
        )

        t0_50p_slope = _calc_slope(closes, idx - 1, 50, t0_low, lookback=5)
        t0_200p_slope = _calc_slope(closes, idx - 1, 200, t0_low, lookback=5)

        atr_14 = _calc_atr(stock_df, idx - 1, period=14)
        atr_ratio_14 = (atr_14 / t0_low) * 100.0 if atr_14 is not None and t0_low else None

        prev_close = get_close(-1)
        t0_open = _safe_float(t0_row["open"])
        gap_down_strength = _calc_gap(prev_close, t0_open, t0_low)

        updates.append(
            RowUpdate(
                row_id=row_id,
                values={
                    "t_1_alin": t_1_alin,
                    "t_1_ylin": t_1_ylin,
                    "t_1_bodi": t_1_bodi,
                    "t_1_bodi_colour": t_1_bodi_colour,
                    "t_2": t_2,
                    "t_5": t_5,
                    "t_10": t_10,
                    "t_15": t_15,
                    "t_20": t_20,
                    "t_2_hajonta": t_2_hajonta,
                    "t_5_hajonta": t_5_hajonta,
                    "t_10_hajonta": t_10_hajonta,
                    "t_15_hajonta": t_15_hajonta,
                    "t_20_hajonta": t_20_hajonta,
                    "t_2_5p_liukuva": t_2_5p_liukuva,
                    "t_2_10p_liukuva": t_2_10p_liukuva,
                    "t_2_20p_liukuva": t_2_20p_liukuva,
                    "t_5_5p_liukuva": t_5_5p_liukuva,
                    "t_5_10p_liukuva": t_5_10p_liukuva,
                    "t_5_20p_liukuva": t_5_20p_liukuva,
                    "t_10_5p_liukuva": t_10_5p_liukuva,
                    "t_10_10p_liukuva": t_10_10p_liukuva,
                    "t_10_20p_liukuva": t_10_20p_liukuva,
                    "t_15_5p_liukuva": t_15_5p_liukuva,
                    "t_15_10p_liukuva": t_15_10p_liukuva,
                    "t_15_20p_liukuva": t_15_20p_liukuva,
                    "t_20_5p_liukuva": t_20_5p_liukuva,
                    "t_20_10p_liukuva": t_20_10p_liukuva,
                    "t_20_20p_liukuva": t_20_20p_liukuva,
                    "t0_20p_liukuva": t0_20p_liukuva,
                    "t0_50p_liukuva": t0_50p_liukuva,
                    "t0_200p_liukuva": t0_200p_liukuva,
                    "Price_slope_5": price_slope_5,
                    "Price_slope_10": price_slope_10,
                    "Price_acceleration_5_10": price_acceleration_5_10,
                    "Volatility_ratio_10_20": volatility_ratio_10_20,
                    "t0_50p_slope": t0_50p_slope,
                    "t0_200p_slope": t0_200p_slope,
                    "ATR_ratio_14": atr_ratio_14,
                    "Gap_down_strength": gap_down_strength,
                },
            )
        )

    return updates


def fetch_results_grouped(conn: sqlite3.Connection) -> Dict[str, List[Tuple[int, str]]]:
    cursor = conn.cursor()
    cursor.execute("SELECT id, ticker, date FROM results_data")
    grouped: Dict[str, List[Tuple[int, str]]] = {}
    for row_id, ticker, date_str in cursor.fetchall():
        grouped.setdefault(ticker, []).append((row_id, date_str))
    return grouped


def apply_updates(conn: sqlite3.Connection, updates: List[RowUpdate]) -> int:
    if not updates:
        return 0
    cursor = conn.cursor()
    cols = HISTORY_COLUMNS
    set_clause = ", ".join(f"{col} = ?" for col in cols)
    total = 0
    for upd in updates:
        params = [upd.values.get(col) for col in cols]
        params.append(upd.row_id)
        cursor.execute(f"UPDATE results_data SET {set_clause} WHERE id = ?", params)
        total += cursor.rowcount
    conn.commit()
    return total


def load_stock_data(conn: sqlite3.Connection, tickers: List[str]) -> Dict[str, pd.DataFrame]:
    if not tickers:
        return {}
    placeholders = ",".join("?" for _ in tickers)
    query = f"""
        SELECT osake AS ticker, pvm, open, high, low, close
        FROM osakedata
        WHERE osake IN ({placeholders})
    """
    df = pd.read_sql_query(query, conn, params=tickers)
    if df.empty:
        return {}
    df["pvm"] = pd.to_datetime(df["pvm"], errors="coerce")
    df = df.dropna(subset=["pvm"])
    grouped: Dict[str, pd.DataFrame] = {}
    for ticker, sub in df.groupby("ticker"):
        grouped[str(ticker)] = sub.sort_values("pvm").reset_index(drop=True)
    return grouped


def backfill(db_path: Path, stock_db_path: Path, apply: bool = False) -> int:
    results_conn = sqlite3.connect(db_path)
    grouped_rows = fetch_results_grouped(results_conn)
    tickers = list(grouped_rows.keys())
    stock_conn = sqlite3.connect(stock_db_path)
    stock_data = load_stock_data(stock_conn, tickers)

    updates: List[RowUpdate] = []
    for ticker, rows in grouped_rows.items():
        stock_df = stock_data.get(ticker)
        if stock_df is None:
            continue
        updates.extend(recompute_for_ticker(stock_df, rows))

    if not apply:
        print(
            f"Kuivaharjoitus: {len(updates)} riviä tarvitsee päivityksen "
            f"({sum(len(rows) for rows in grouped_rows.values())} riviä luettu). "
            "Käytä --apply kirjoittaaksesi muutokset."
        )
        return 0

    applied = apply_updates(results_conn, updates)
    print(f"Päivitettiin {applied} riviä ({len(updates)} laskettu päivitys).")
    return applied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Recompute history-normalized fields in results_data using t0_low."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/analysis.db"),
        help="Polku analysis.db tietokantaan",
    )
    parser.add_argument(
        "--stock-db",
        type=Path,
        default=Path("data/osakedata.db"),
        help="Polku osakedata.db tietokantaan",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Kirjoita muutokset (oletus: dry-run)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backfill(args.db, args.stock_db, apply=args.apply)


if __name__ == "__main__":
    main()
