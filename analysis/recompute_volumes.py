from __future__ import annotations

"""
Recompute volume ratio fields in results_data using osakedata volume history.

Fields updated:
- t_2_volyymi, t_5_volyymi, t_10_volyymi, t_15_volyymi, t_20_volyymi
- t0_volyymi, t2_volyymi, t5_volyymi, t10_volyymi, t20_volyymi

Default mode is dry-run; use --apply to write updates.
"""

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd


VOLUME_FIELDS = [
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
]


@dataclass
class VolumeUpdate:
    row_id: int
    values: Dict[str, Optional[float]]


def _safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def compute_volume_ratio(
    volumes: List[float], date_index: int, window: int, offset: int
) -> Optional[float]:
    """
    volumes: list of positive volumes sorted by date ascending
    date_index: index of t0 in volumes
    window: window length in days
    offset: offset of window end relative to t0 (e.g. -1 = t-1, 0 = t0, 2 = t+2)
    returns: (period_avg / baseline_avg) * 100 or None if not computable
    """
    end_idx = date_index + offset
    start_idx = end_idx - window + 1
    if start_idx < 0 or end_idx >= len(volumes):
        return None
    period_vals = [v for v in volumes[start_idx : end_idx + 1] if v is not None and v > 0]
    if not period_vals:
        return None
    period_avg = mean(period_vals)

    baseline_end = start_idx - 1
    baseline_start = baseline_end - 99
    if baseline_start < 0 or baseline_end >= len(volumes):
        return None
    baseline_vals = [
        v for v in volumes[baseline_start : baseline_end + 1] if v is not None and v > 0
    ]
    if not baseline_vals:
        return None
    baseline_avg = mean(baseline_vals)
    if baseline_avg <= 0:
        return None
    return (period_avg / baseline_avg) * 100.0


def recompute_for_ticker(
    stock_df: pd.DataFrame, result_rows: Iterable[Tuple[int, str]]
) -> List[VolumeUpdate]:
    """
    stock_df: DataFrame with columns ["pvm","volume"] sorted ascending for ticker
    result_rows: iterable of (id, date_str) tuples for this ticker
    """
    updates: List[VolumeUpdate] = []
    if stock_df.empty:
        return updates
    stock_df = stock_df.copy()
    stock_df["pvm"] = pd.to_datetime(stock_df["pvm"])
    stock_df = stock_df.sort_values("pvm").reset_index(drop=True)
    volumes_list = [_safe_float(v) for v in stock_df["volume"].tolist()]
    date_to_idx = {d.date(): i for i, d in enumerate(stock_df["pvm"])}

    for row_id, date_str in result_rows:
        date_dt = pd.to_datetime(date_str, errors="coerce")
        if pd.isna(date_dt):
            continue
        idx = date_to_idx.get(date_dt.date())
        if idx is None:
            continue
        values = {
            "t_2_volyymi": compute_volume_ratio(volumes_list, idx, 2, -1),
            "t_5_volyymi": compute_volume_ratio(volumes_list, idx, 5, -1),
            "t_10_volyymi": compute_volume_ratio(volumes_list, idx, 10, -1),
            "t_15_volyymi": compute_volume_ratio(volumes_list, idx, 15, -1),
            "t_20_volyymi": compute_volume_ratio(volumes_list, idx, 20, -1),
            "t0_volyymi": compute_volume_ratio(volumes_list, idx, 1, 0),
            "t2_volyymi": compute_volume_ratio(volumes_list, idx, 1, 2),
            "t5_volyymi": compute_volume_ratio(volumes_list, idx, 1, 5),
            "t10_volyymi": compute_volume_ratio(volumes_list, idx, 1, 10),
            "t20_volyymi": compute_volume_ratio(volumes_list, idx, 1, 20),
        }
        updates.append(VolumeUpdate(row_id=row_id, values=values))
    return updates


def fetch_results_grouped(conn: sqlite3.Connection) -> Dict[str, List[Tuple[int, str]]]:
    cursor = conn.cursor()
    cursor.execute("SELECT id, ticker, date FROM results_data")
    grouped: Dict[str, List[Tuple[int, str]]] = {}
    for row_id, ticker, date_str in cursor.fetchall():
        grouped.setdefault(ticker, []).append((row_id, date_str))
    return grouped


def apply_updates(conn: sqlite3.Connection, updates: List[VolumeUpdate]) -> int:
    cursor = conn.cursor()
    for upd in updates:
        set_clause = ", ".join(f"{col} = ?" for col in upd.values.keys())
        params = list(upd.values.values()) + [upd.row_id]
        cursor.execute(f"UPDATE results_data SET {set_clause} WHERE id = ?", params)
    conn.commit()
    return len(updates)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recompute volume ratios in results_data from osakedata."
    )
    parser.add_argument("--analysis-db", type=Path, default=Path("data/analysis.db"))
    parser.add_argument("--osake-db", type=Path, default=Path("data/osakedata.db"))
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write updates to database (default is dry-run).",
    )
    parser.add_argument(
        "--max-tickers",
        type=int,
        default=None,
        help="Optional limit of tickers to process (for testing).",
    )
    args = parser.parse_args()

    if not args.analysis_db.exists():
        raise FileNotFoundError(f"analysis_db not found: {args.analysis_db}")
    if not args.osake_db.exists():
        raise FileNotFoundError(f"osake_db not found: {args.osake_db}")

    with sqlite3.connect(args.analysis_db) as res_conn, sqlite3.connect(
        args.osake_db
    ) as stock_conn:
        grouped = fetch_results_grouped(res_conn)
        tickers = sorted(grouped.keys())
        if args.max_tickers:
            tickers = tickers[: args.max_tickers]

        total_updates = 0
        for ticker in tickers:
            stock_df = pd.read_sql_query(
                "SELECT pvm, volume FROM osakedata WHERE osake = ? ORDER BY pvm",
                stock_conn,
                params=[ticker],
            )
            updates = recompute_for_ticker(stock_df, grouped[ticker])
            if args.apply:
                total_updates += apply_updates(res_conn, updates)
        if args.apply:
            print(f"Updated {total_updates} rows across {len(tickers)} tickers.")
        else:
            est_rows = sum(len(v) for v in grouped.values() if v)
            print(
                f"Dry-run complete. Would process {len(tickers)} tickers, ~{est_rows} rows."
            )


if __name__ == "__main__":
    main()
