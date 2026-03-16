from __future__ import annotations

import csv
from datetime import date
from datetime import datetime
import os
import sqlite3
from statistics import median
from typing import Any


VALID_EVENT_CLASSES = {"R2", "R3", "R2_ONLY", "R3_ONLY", "R2_AND_R3"}
VALID_RADII = {"ALL", "R2", "R3"}
VALID_SORT_COLUMNS = {
    "ticker": "e.ticker",
    "date": "e.date",
    "event_class": "e.event_class",
    "pivot_gap_r2": "e.pivot_gap_r2",
    "pivot_drop_pct_r2": "e.pivot_drop_pct_r2",
    "pivot_gap_r3": "e.pivot_gap_r3",
    "pivot_drop_pct_r3": "e.pivot_drop_pct_r3",
    "rsi": "e.rsi",
    "ret_5d": "ret_5d",
    "ret_10d": "ret_10d",
    "ret_20d": "ret_20d",
    "ret_30d": "ret_30d",
}
EXPORT_COLUMNS = [
    "ticker",
    "date",
    "event_class",
    "is_bullish_divergence_r2",
    "is_bullish_divergence_r3",
    "pivot_gap_r2",
    "pivot_drop_pct_r2",
    "pivot_gap_r3",
    "pivot_drop_pct_r3",
    "rsi",
    "bullish_strength",
    "bearish_strength",
    "ret_5d",
    "ret_10d",
    "ret_20d",
    "ret_30d",
]


def _resolve_stock_db_path(db_path: str, stock_db_path: str | None = None) -> str:
    if stock_db_path:
        return stock_db_path
    return os.path.join(os.path.dirname(os.path.abspath(db_path)), "osakedata.db")


def _resolve_export_path(db_path: str, export_path: str | None = None) -> str:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"divergence_export_{timestamp}.csv"
    if export_path:
        abs_path = os.path.abspath(export_path)
        if abs_path.lower().endswith(".csv"):
            directory = os.path.dirname(abs_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            return abs_path
        os.makedirs(abs_path, exist_ok=True)
        return os.path.join(abs_path, filename)
    export_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)), "..", "exports")
    export_dir = os.path.abspath(export_dir)
    os.makedirs(export_dir, exist_ok=True)
    return os.path.join(export_dir, filename)


def _classification_sql() -> str:
    return """
        CASE
            WHEN d.is_bullish_divergence_r2 = 1 AND d.is_bullish_divergence_r3 = 0 THEN 'R2_ONLY'
            WHEN d.is_bullish_divergence_r2 = 0 AND d.is_bullish_divergence_r3 = 1 THEN 'R3_ONLY'
            WHEN d.is_bullish_divergence_r2 = 1 AND d.is_bullish_divergence_r3 = 1 THEN 'R2_AND_R3'
        END
    """


def _validate_date_value(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    date.fromisoformat(stripped)
    return stripped


def _has_excluded_tickers_table(db_path: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'excluded_tickers'
            """
        ).fetchone()
    return row is not None


def _build_where_clause(
    event_class: str | None,
    radius: str,
    min_gap: int,
    max_gap: int,
    min_drop: float,
    max_drop: float,
    min_rsi: float,
    max_rsi: float,
    start_date: str | None,
    end_date: str | None,
    exclude_active_tickers: bool,
) -> tuple[str, list[Any]]:
    radius_value = radius.upper()
    if radius_value not in VALID_RADII:
        raise ValueError(f"Unsupported radius: {radius}")
    if event_class is not None and event_class not in VALID_EVENT_CLASSES:
        raise ValueError(f"Unsupported event class: {event_class}")
    start_date_value = _validate_date_value(start_date)
    end_date_value = _validate_date_value(end_date)

    class_sql = _classification_sql()

    clauses = ["(d.is_bullish_divergence_r2 = 1 OR d.is_bullish_divergence_r3 = 1)"]
    params: list[Any] = []
    if exclude_active_tickers:
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM excluded_tickers x WHERE x.ticker = d.ticker AND x.active = 1)"
        )
    clauses.extend(
        [
            "d.rsi >= ?",
            "d.rsi <= ?",
        ]
    )
    params.extend([min_rsi, max_rsi])
    if radius_value != "ALL":
        gap_col = "d.pivot_gap_r2" if radius_value == "R2" else "d.pivot_gap_r3"
        drop_col = "d.pivot_drop_pct_r2" if radius_value == "R2" else "d.pivot_drop_pct_r3"
        clauses.extend(
            [
                f"{gap_col} >= ?",
                f"{gap_col} <= ?",
                f"{drop_col} >= ?",
                f"{drop_col} <= ?",
            ]
        )
        params.extend([min_gap, max_gap, min_drop, max_drop])
    if event_class == "R2":
        clauses.append("d.is_bullish_divergence_r2 = 1")
    elif event_class == "R3":
        clauses.append("d.is_bullish_divergence_r3 = 1")
    elif event_class is not None:
        clauses.append(f"{class_sql} = ?")
        params.append(event_class)
    if start_date_value is not None:
        clauses.append("d.date >= ?")
        params.append(start_date_value)
    if end_date_value is not None:
        clauses.append("d.date <= ?")
        params.append(end_date_value)
    return " AND ".join(clauses), params


def _fetch_event_rows(
    db_path: str,
    *,
    event_class: str | None,
    radius: str,
    min_gap: int,
    max_gap: int,
    min_drop: float,
    max_drop: float,
    min_rsi: float,
    max_rsi: float,
    start_date: str | None = None,
    end_date: str | None = None,
    stock_db_path: str | None = None,
    extra_select: str = "",
    order_by: str = "",
    limit_clause: str = "",
    params_tail: list[Any] | None = None,
) -> list[sqlite3.Row]:
    stock_path = _resolve_stock_db_path(db_path, stock_db_path)
    exclude_active_tickers = _has_excluded_tickers_table(db_path)
    where_sql, where_params = _build_where_clause(
        event_class,
        radius,
        min_gap,
        max_gap,
        min_drop,
        max_drop,
        min_rsi,
        max_rsi,
        start_date,
        end_date,
        exclude_active_tickers,
    )
    class_sql = _classification_sql()
    params = list(where_params)
    if params_tail:
        params.extend(params_tail)

    query = f"""
        ATTACH DATABASE ? AS marketdb;

        WITH prices AS (
            SELECT
                osake AS ticker,
                pvm AS date,
                close,
                ROW_NUMBER() OVER (PARTITION BY osake ORDER BY pvm) AS rn
            FROM marketdb.osakedata
        ),
        events AS (
            SELECT
                d.ticker,
                d.date,
                {class_sql} AS event_class,
                d.is_bullish_divergence_r2,
                d.is_bullish_divergence_r3,
                d.pivot_gap_r2,
                d.pivot_drop_pct_r2,
                d.pivot_gap_r3,
                d.pivot_drop_pct_r3,
                d.rsi,
                d.bullish_strength,
                d.bearish_strength
            FROM divergence_data d
            WHERE {where_sql}
        )
        SELECT
            e.ticker,
            e.date,
            e.event_class,
            e.is_bullish_divergence_r2,
            e.is_bullish_divergence_r3,
            e.pivot_gap_r2,
            e.pivot_drop_pct_r2,
            e.pivot_gap_r3,
            e.pivot_drop_pct_r3,
            e.rsi,
            e.bullish_strength,
            e.bearish_strength,
            ((p5.close / p0.close) - 1.0) * 100.0 AS ret_5d,
            ((p10.close / p0.close) - 1.0) * 100.0 AS ret_10d,
            ((p20.close / p0.close) - 1.0) * 100.0 AS ret_20d,
            ((p30.close / p0.close) - 1.0) * 100.0 AS ret_30d
            {extra_select}
        FROM events e
        JOIN prices p0
          ON p0.ticker = e.ticker
         AND p0.date = e.date
        LEFT JOIN prices p5
          ON p5.ticker = e.ticker
         AND p5.rn = p0.rn + 5
        LEFT JOIN prices p10
          ON p10.ticker = e.ticker
         AND p10.rn = p0.rn + 10
        LEFT JOIN prices p20
          ON p20.ticker = e.ticker
         AND p20.rn = p0.rn + 20
        LEFT JOIN prices p30
          ON p30.ticker = e.ticker
         AND p30.rn = p0.rn + 30
        {order_by}
        {limit_clause}
    """

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.executescript("PRAGMA temp_store = MEMORY;")
        conn.execute("ATTACH DATABASE ? AS marketdb", (stock_path,))
        try:
            sql = query.replace("ATTACH DATABASE ? AS marketdb;", "")
            return conn.execute(sql, params).fetchall()
        finally:
            conn.execute("DETACH DATABASE marketdb")


def fetch_divergence_events(
    db_path: str,
    event_class: str | None = None,
    radius: str = "ALL",
    min_gap: int = 5,
    max_gap: int = 24,
    min_drop: float = 0.0,
    max_drop: float = 50.0,
    min_rsi: float = 1.0,
    max_rsi: float = 100.0,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 500,
    offset: int = 0,
    sort_by: str = "date",
    sort_desc: bool = True,
    stock_db_path: str | None = None,
) -> list[dict[str, Any]]:
    sort_col = VALID_SORT_COLUMNS.get(sort_by, "e.date")
    direction = "DESC" if sort_desc else "ASC"
    rows = _fetch_event_rows(
        db_path,
        event_class=event_class,
        radius=radius,
        min_gap=min_gap,
        max_gap=max_gap,
        min_drop=min_drop,
        max_drop=max_drop,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        start_date=start_date,
        end_date=end_date,
        stock_db_path=stock_db_path,
        order_by=f"ORDER BY {sort_col} {direction}, e.ticker ASC, e.date ASC",
        limit_clause="LIMIT ? OFFSET ?",
        params_tail=[limit, offset],
    )
    return [dict(row) for row in rows]


def summarize_divergence_events(
    db_path: str,
    event_class: str | None = None,
    radius: str = "ALL",
    min_gap: int = 5,
    max_gap: int = 24,
    min_drop: float = 0.0,
    max_drop: float = 50.0,
    min_rsi: float = 1.0,
    max_rsi: float = 100.0,
    start_date: str | None = None,
    end_date: str | None = None,
    stock_db_path: str | None = None,
) -> dict[str, Any]:
    rows = [
        dict(row)
        for row in _fetch_event_rows(
            db_path,
            event_class=event_class,
            radius=radius,
            min_gap=min_gap,
            max_gap=max_gap,
            min_drop=min_drop,
            max_drop=max_drop,
            min_rsi=min_rsi,
            max_rsi=max_rsi,
            start_date=start_date,
            end_date=end_date,
            stock_db_path=stock_db_path,
        )
    ]
    ret30_values = [row["ret_30d"] for row in rows if row["ret_30d"] is not None]
    if not rows:
        return {
            "n": 0,
            "winrate_30d": None,
            "mean_ret_30d": None,
            "median_ret_30d": None,
            "winsor_30d": None,
        }
    if not ret30_values:
        return {
            "n": len(rows),
            "winrate_30d": None,
            "mean_ret_30d": None,
            "median_ret_30d": None,
            "winsor_30d": None,
        }
    return {
        "n": len(rows),
        "winrate_30d": sum(1 for value in ret30_values if value > 0) / len(ret30_values),
        "mean_ret_30d": sum(ret30_values) / len(ret30_values),
        "median_ret_30d": median(ret30_values),
        "winsor_30d": sum(max(-50.0, min(50.0, value)) for value in ret30_values)
        / len(ret30_values),
    }


def fetch_divergence_heatmap(
    db_path: str,
    event_class: str | None = None,
    radius: str = "R3",
    min_gap: int = 5,
    max_gap: int = 24,
    min_drop: float = 0.0,
    max_drop: float = 50.0,
    min_rsi: float = 1.0,
    max_rsi: float = 100.0,
    start_date: str | None = None,
    end_date: str | None = None,
    stock_db_path: str | None = None,
) -> list[dict[str, Any]]:
    radius_value = radius.upper()
    gap_col = "pivot_gap_r2" if radius_value == "R2" else "pivot_gap_r3"
    drop_col = "pivot_drop_pct_r2" if radius_value == "R2" else "pivot_drop_pct_r3"
    rows = _fetch_event_rows(
        db_path,
        event_class=event_class,
        radius=radius_value,
        min_gap=min_gap,
        max_gap=max_gap,
        min_drop=min_drop,
        max_drop=max_drop,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        start_date=start_date,
        end_date=end_date,
        stock_db_path=stock_db_path,
        extra_select="",
    )
    grouped: dict[tuple[int, int], list[float]] = {}
    for row in rows:
        gap_value = row[gap_col]
        drop_value = row[drop_col]
        ret_30d = row["ret_30d"]
        if gap_value is None or drop_value is None or ret_30d is None:
            continue
        key = (int(gap_value), int(drop_value))
        grouped.setdefault(key, []).append(float(ret_30d))
    result = []
    for (gap_value, drop_value), values in sorted(grouped.items()):
        result.append(
            {
                "gap": gap_value,
                "drop": drop_value,
                "avg_ret_30d": sum(values) / len(values),
                "n": len(values),
            }
        )
    return result


def export_divergence_events_csv(
    db_path: str,
    event_class: str | None = None,
    radius: str = "R3",
    min_gap: int = 5,
    max_gap: int = 24,
    min_drop: float = 0.0,
    max_drop: float = 50.0,
    min_rsi: float = 1.0,
    max_rsi: float = 100.0,
    start_date: str | None = None,
    end_date: str | None = None,
    export_path: str | None = None,
    stock_db_path: str | None = None,
) -> str:
    rows = fetch_divergence_events(
        db_path,
        event_class=event_class,
        radius=radius,
        min_gap=min_gap,
        max_gap=max_gap,
        min_drop=min_drop,
        max_drop=max_drop,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        start_date=start_date,
        end_date=end_date,
        limit=1_000_000_000,
        offset=0,
        sort_by="date",
        sort_desc=True,
        stock_db_path=stock_db_path,
    )
    target_path = _resolve_export_path(db_path, export_path)
    with open(target_path, "w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=EXPORT_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) for column in EXPORT_COLUMNS})
    return target_path
