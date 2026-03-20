from __future__ import annotations

import csv
from datetime import date
from datetime import datetime
from datetime import timedelta
import os
import sqlite3
from statistics import median
from typing import Any


VALID_EVENT_CLASSES = {"R2", "R3", "R2_ONLY", "R3_ONLY", "R2_AND_R3"}
VALID_SORT_COLUMNS = {
    "ticker",
    "date",
    "event_class",
    "combo_pattern",
    "combo_offset",
    "pivot2_date_r2",
    "pivot2_date_r3",
    "anchor_type",
    "anchor_date",
    "pivot_gap_r2",
    "pivot_drop_pct_r2",
    "pivot_gap_r3",
    "pivot_drop_pct_r3",
    "rsi",
    "ret_5d",
    "ret_10d",
    "ret_20d",
    "ret_30d",
}
EXPORT_COLUMNS = [
    "ticker",
    "date",
    "event_class",
    "is_bullish_divergence_r2",
    "is_bullish_divergence_r3",
    "pivot_gap_r2",
    "pivot_drop_pct_r2",
    "pivot2_date_r2",
    "pivot_gap_r3",
    "pivot_drop_pct_r3",
    "pivot2_date_r3",
    "combo_pattern",
    "combo_offset",
    "anchor_type",
    "anchor_date",
    "rsi",
    "bullish_strength",
    "bearish_strength",
    "ret_5d",
    "ret_10d",
    "ret_20d",
    "ret_30d",
]
VALID_TREND_FILTERS = {"all", "downtrend_only"}
VALID_ANCHORS = {"event", "pivot2"}
VALID_COMBO_PATTERNS = {
    "ALL",
    "BullDiv & Hammer",
    "BullDiv & Piercing Pattern",
    "BullDiv & Bullish Engulfing",
}


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


def _validate_trend_filter(trend_filter: str) -> str:
    if trend_filter not in VALID_TREND_FILTERS:
        raise ValueError(f"Unsupported trend filter: {trend_filter}")
    return trend_filter


def _validate_anchor(anchor: str) -> str:
    if anchor not in VALID_ANCHORS:
        raise ValueError(f"Unsupported anchor: {anchor}")
    return anchor


def _geometry_scope(event_class: str | None) -> str:
    if event_class in {"R2", "R2_ONLY"}:
        return "R2"
    if event_class in {"R3", "R3_ONLY"}:
        return "R3"
    return "BOTH"


def _anchor_date_sql(event_class: str | None, anchor: str) -> str:
    _validate_anchor(anchor)
    if anchor == "event":
        return "d.date"

    geometry_scope = _geometry_scope(event_class)
    if geometry_scope == "R2":
        return "d.pivot2_date_r2"
    if geometry_scope == "R3":
        return "d.pivot2_date_r3"
    return "COALESCE(d.pivot2_date_r2, d.pivot2_date_r3)"


def _select_anchor_date(row: dict[str, Any], event_class: str | None, anchor: str) -> str | None:
    _validate_anchor(anchor)
    if anchor == "event":
        return str(row["date"])

    geometry_scope = _geometry_scope(event_class)
    if geometry_scope == "R2":
        value = row.get("pivot2_date_r2")
        return None if value is None else str(value)
    if geometry_scope == "R3":
        value = row.get("pivot2_date_r3")
        return None if value is None else str(value)
    value = row.get("pivot2_date_r2")
    if value is not None:
        return str(value)
    value = row.get("pivot2_date_r3")
    return None if value is None else str(value)


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


def _has_analysis_findings_table(db_path: str) -> bool:
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = 'analysis_findings'
            """
        ).fetchone()
    return row is not None


def _build_where_clause(
    event_class: str | None,
    anchor: str,
    min_gap: int,
    max_gap: int,
    min_drop: float,
    max_drop: float,
    min_rsi: float,
    max_rsi: float,
    market: str | None,
    start_date: str | None,
    end_date: str | None,
    exclude_active_tickers: bool,
) -> tuple[str, list[Any]]:
    if event_class is not None and event_class not in VALID_EVENT_CLASSES:
        raise ValueError(f"Unsupported event class: {event_class}")
    _validate_anchor(anchor)
    market_value = (market or "").strip().lower() or None
    start_date_value = _validate_date_value(start_date)
    end_date_value = _validate_date_value(end_date)

    class_sql = _classification_sql()
    anchor_date_sql = _anchor_date_sql(event_class, anchor)
    clauses = ["(d.is_bullish_divergence_r2 = 1 OR d.is_bullish_divergence_r3 = 1)"]
    params: list[Any] = []

    if exclude_active_tickers:
        clauses.append(
            "NOT EXISTS (SELECT 1 FROM excluded_tickers x WHERE x.ticker = d.ticker AND x.active = 1)"
        )

    clauses.extend(["d.rsi >= ?", "d.rsi <= ?"])
    params.extend([min_rsi, max_rsi])

    geometry_scope = _geometry_scope(event_class)
    if geometry_scope == "R2":
        clauses.extend(
            [
                "d.pivot_gap_r2 >= ?",
                "d.pivot_gap_r2 <= ?",
                "d.pivot_drop_pct_r2 >= ?",
                "d.pivot_drop_pct_r2 <= ?",
            ]
        )
        params.extend([min_gap, max_gap, min_drop, max_drop])
    elif geometry_scope == "R3":
        clauses.extend(
            [
                "d.pivot_gap_r3 >= ?",
                "d.pivot_gap_r3 <= ?",
                "d.pivot_drop_pct_r3 >= ?",
                "d.pivot_drop_pct_r3 <= ?",
            ]
        )
        params.extend([min_gap, max_gap, min_drop, max_drop])
    else:
        clauses.append(
            """
            (
                (d.pivot_gap_r2 >= ? AND d.pivot_gap_r2 <= ? AND d.pivot_drop_pct_r2 >= ? AND d.pivot_drop_pct_r2 <= ?)
                OR
                (d.pivot_gap_r3 >= ? AND d.pivot_gap_r3 <= ? AND d.pivot_drop_pct_r3 >= ? AND d.pivot_drop_pct_r3 <= ?)
            )
            """
        )
        params.extend(
            [
                min_gap,
                max_gap,
                min_drop,
                max_drop,
                min_gap,
                max_gap,
                min_drop,
                max_drop,
            ]
        )

    if event_class == "R2":
        clauses.append("d.is_bullish_divergence_r2 = 1")
    elif event_class == "R3":
        clauses.append("d.is_bullish_divergence_r3 = 1")
    elif event_class is not None:
        clauses.append(f"{class_sql} = ?")
        params.append(event_class)

    if anchor == "pivot2":
        clauses.append(f"{anchor_date_sql} IS NOT NULL")
    if start_date_value is not None:
        clauses.append(f"{anchor_date_sql} >= ?")
        params.append(start_date_value)
    if end_date_value is not None:
        clauses.append(f"{anchor_date_sql} <= ?")
        params.append(end_date_value)
    if market_value is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM marketdb.osakedata m WHERE m.osake = d.ticker AND m.pvm = d.date AND LOWER(m.market) = ?)"
        )
        params.append(market_value)
    return " AND ".join(clauses), params


def _chunked(values: list[str], size: int = 500) -> list[list[str]]:
    return [values[idx : idx + size] for idx in range(0, len(values), size)]


def _parse_iso_date(value: str) -> date:
    return date.fromisoformat(str(value))


def _fetch_base_divergence_rows(
    db_path: str,
    *,
    event_class: str | None,
    anchor: str,
    min_gap: int,
    max_gap: int,
    min_drop: float,
    max_drop: float,
    min_rsi: float,
    max_rsi: float,
    market: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    stock_db_path: str | None = None,
) -> list[dict[str, Any]]:
    stock_path = _resolve_stock_db_path(db_path, stock_db_path)
    exclude_active_tickers = _has_excluded_tickers_table(db_path)
    where_sql, params = _build_where_clause(
        event_class,
        anchor,
        min_gap,
        max_gap,
        min_drop,
        max_drop,
        min_rsi,
        max_rsi,
        market,
        start_date,
        end_date,
        exclude_active_tickers,
    )
    class_sql = _classification_sql()
    query = f"""
        SELECT
            d.ticker,
            d.date,
            {class_sql} AS event_class,
            d.is_bullish_divergence_r2,
            d.is_bullish_divergence_r3,
            d.pivot_gap_r2,
            d.pivot_drop_pct_r2,
            d.pivot2_date_r2,
            d.pivot_gap_r3,
            d.pivot_drop_pct_r3,
            d.pivot2_date_r3,
            d.rsi,
            d.bullish_strength,
            d.bearish_strength
        FROM divergence_data d
        WHERE {where_sql}
    """

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("ATTACH DATABASE ? AS marketdb", (stock_path,))
        try:
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.execute("DETACH DATABASE marketdb")
    return [dict(row) for row in rows]


def _fetch_price_history(
    stock_db_path: str,
    tickers: list[str],
    start_date: str,
    end_date: str,
) -> list[sqlite3.Row]:
    if not tickers:
        return []
    result: list[sqlite3.Row] = []
    with sqlite3.connect(stock_db_path) as conn:
        conn.row_factory = sqlite3.Row
        for ticker_chunk in _chunked(sorted(tickers)):
            placeholders = ",".join("?" for _ in ticker_chunk)
            query = f"""
                SELECT osake AS ticker, pvm AS date, close
                FROM osakedata
                WHERE osake IN ({placeholders})
                  AND pvm >= ?
                  AND pvm <= ?
                ORDER BY osake, pvm
            """
            result.extend(conn.execute(query, [*ticker_chunk, start_date, end_date]).fetchall())
    return result


def _attach_downtrend_flags(
    rows: list[dict[str, Any]],
    stock_db_path: str,
) -> list[dict[str, Any]]:
    if not rows:
        return []

    min_event_date = min(_parse_iso_date(row["date"]) for row in rows)
    max_event_date = max(_parse_iso_date(row["date"]) for row in rows)
    price_rows = _fetch_price_history(
        stock_db_path,
        tickers=sorted({str(row["ticker"]) for row in rows}),
        start_date=(min_event_date - timedelta(days=60)).isoformat(),
        end_date=max_event_date.isoformat(),
    )

    by_ticker: dict[str, list[tuple[str, float]]] = {}
    for price_row in price_rows:
        close_value = price_row["close"]
        if close_value is None:
            continue
        by_ticker.setdefault(str(price_row["ticker"]), []).append(
            (str(price_row["date"]), float(close_value))
        )

    downtrend_flags: dict[tuple[str, str], bool] = {}
    for ticker, series in by_ticker.items():
        closes = [close_value for _date_value, close_value in series]
        dates = [date_value for date_value, _close_value in series]
        for idx, date_value in enumerate(dates):
            qualified = False
            if idx >= 10:
                t0 = closes[idx]
                t_2 = closes[idx - 2]
                t_5 = closes[idx - 5]
                t_10 = closes[idx - 10]
                if t_10 > 0 and t_10 > t_5 > t_2 > t0:
                    decline_percent = ((t_10 - t0) / t_10) * 100.0
                    if decline_percent >= 3.0:
                        ma5 = sum(closes[idx - 4 : idx + 1]) / 5.0
                        ma10 = sum(closes[idx - 9 : idx + 1]) / 10.0
                        if t0 < ma10 and ma5 < ma10:
                            qualified = True
            downtrend_flags[(ticker, date_value)] = qualified

    result: list[dict[str, Any]] = []
    for row in rows:
        row_copy = dict(row)
        row_copy["is_downtrend_qualified"] = bool(
            downtrend_flags.get((str(row["ticker"]), str(row["date"])), False)
        )
        result.append(row_copy)
    return result


def _apply_trend_filter(
    rows: list[dict[str, Any]],
    trend_filter: str,
) -> list[dict[str, Any]]:
    _validate_trend_filter(trend_filter)
    if trend_filter == "all":
        return rows
    return [row for row in rows if row.get("is_downtrend_qualified") is True]


def _attach_anchor_fields(
    rows: list[dict[str, Any]],
    *,
    event_class: str | None,
    anchor: str,
) -> list[dict[str, Any]]:
    _validate_anchor(anchor)
    result: list[dict[str, Any]] = []
    for row in rows:
        row_copy = dict(row)
        row_copy["anchor_type"] = anchor
        row_copy["anchor_date"] = _select_anchor_date(row_copy, event_class, anchor)
        result.append(row_copy)
    return result


def _attach_combo_fields(
    rows: list[dict[str, Any]],
    db_path: str,
    stock_db_path: str,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    if not _has_analysis_findings_table(db_path):
        return [{**row, "combo_pattern": None, "combo_offset": None} for row in rows]

    combo_map: dict[tuple[str, str], str] = {}
    tickers = sorted({str(row["ticker"]) for row in rows})
    dates = sorted({str(row["date"]) for row in rows})
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        for ticker_chunk in _chunked(tickers):
            ticker_placeholders = ",".join("?" for _ in ticker_chunk)
            for date_chunk in _chunked(dates):
                date_placeholders = ",".join("?" for _ in date_chunk)
                query = f"""
                    SELECT ticker, date, pattern
                    FROM analysis_findings
                    WHERE ticker IN ({ticker_placeholders})
                      AND date IN ({date_placeholders})
                      AND pattern LIKE 'BullDiv & %'
                    ORDER BY ticker, date, pattern ASC
                """
                combo_rows = conn.execute(
                    query, [*ticker_chunk, *date_chunk]
                ).fetchall()
                for combo_row in combo_rows:
                    key = (str(combo_row["ticker"]), str(combo_row["date"]))
                    combo_map.setdefault(key, str(combo_row["pattern"]))

    combo_rows = [
        row
        for row in rows
        if combo_map.get((str(row["ticker"]), str(row["date"]))) is not None
        and row.get("pivot2_date_r3") is not None
    ]
    if combo_rows:
        min_index_date = min(
            min(_parse_iso_date(str(row["date"])), _parse_iso_date(str(row["pivot2_date_r3"])))
            for row in combo_rows
        )
        max_index_date = max(
            max(_parse_iso_date(str(row["date"])), _parse_iso_date(str(row["pivot2_date_r3"])))
            for row in combo_rows
        )
        price_rows = _fetch_price_history(
            stock_db_path,
            tickers=sorted({str(row["ticker"]) for row in combo_rows}),
            start_date=min_index_date.isoformat(),
            end_date=max_index_date.isoformat(),
        )
    else:
        price_rows = []

    positions_by_ticker: dict[str, dict[str, int]] = {}
    for price_row in price_rows:
        ticker = str(price_row["ticker"])
        positions = positions_by_ticker.setdefault(ticker, {})
        positions[str(price_row["date"])] = len(positions)

    result: list[dict[str, Any]] = []
    for row in rows:
        row_copy = dict(row)
        combo_pattern = combo_map.get((str(row["ticker"]), str(row["date"])))
        row_copy["combo_pattern"] = combo_pattern
        combo_offset: int | None = None
        if combo_pattern is not None:
            pivot2_date_r3 = row.get("pivot2_date_r3")
            if pivot2_date_r3 is not None:
                ticker_positions = positions_by_ticker.get(str(row["ticker"]), {})
                combo_idx = ticker_positions.get(str(row["date"]))
                pivot_idx = ticker_positions.get(str(pivot2_date_r3))
                if combo_idx is not None and pivot_idx is not None:
                    combo_offset = combo_idx - pivot_idx
        row_copy["combo_offset"] = combo_offset
        result.append(row_copy)
    return result


def _apply_combo_filters(
    rows: list[dict[str, Any]],
    combo_pattern: str | None,
    combo_offset_min: int | None,
    combo_offset_max: int | None,
) -> list[dict[str, Any]]:
    if combo_pattern not in {None, "ALL"} and combo_pattern not in VALID_COMBO_PATTERNS:
        raise ValueError(f"Unsupported combo pattern: {combo_pattern}")

    result = rows
    if combo_pattern not in {None, "ALL"}:
        result = [row for row in result if row.get("combo_pattern") == combo_pattern]

    if combo_offset_min is not None or combo_offset_max is not None:
        filtered: list[dict[str, Any]] = []
        for row in result:
            combo_offset = row.get("combo_offset")
            if combo_offset is None:
                continue
            if combo_offset_min is not None and combo_offset < combo_offset_min:
                continue
            if combo_offset_max is not None and combo_offset > combo_offset_max:
                continue
            filtered.append(row)
        result = filtered
    return result


def _attach_forward_returns(
    rows: list[dict[str, Any]],
    stock_db_path: str,
) -> list[dict[str, Any]]:
    anchored_rows = [row for row in rows if row.get("anchor_date") is not None]
    if not anchored_rows:
        return []

    min_event_date = min(_parse_iso_date(str(row["anchor_date"])) for row in anchored_rows)
    max_event_date = max(_parse_iso_date(str(row["anchor_date"])) for row in anchored_rows)
    price_rows = _fetch_price_history(
        stock_db_path,
        tickers=sorted({str(row["ticker"]) for row in anchored_rows}),
        start_date=min_event_date.isoformat(),
        end_date=(max_event_date + timedelta(days=60)).isoformat(),
    )

    price_index: dict[str, dict[str, Any]] = {}
    for price_row in price_rows:
        ticker = str(price_row["ticker"])
        close_value = price_row["close"]
        if close_value is None:
            continue
        ticker_state = price_index.setdefault(
            ticker,
            {"dates": [], "closes": [], "positions": {}},
        )
        date_value = str(price_row["date"])
        ticker_state["positions"][date_value] = len(ticker_state["dates"])
        ticker_state["dates"].append(date_value)
        ticker_state["closes"].append(float(close_value))

    def calc_return(closes: list[float], start_idx: int, offset: int) -> float | None:
        future_idx = start_idx + offset
        if future_idx >= len(closes):
            return None
        start_close = closes[start_idx]
        future_close = closes[future_idx]
        if start_close == 0:
            return None
        return ((future_close / start_close) - 1.0) * 100.0

    result: list[dict[str, Any]] = []
    for row in anchored_rows:
        row_copy = dict(row)
        ticker_state = price_index.get(str(row["ticker"]))
        if ticker_state is None:
            row_copy["ret_5d"] = None
            row_copy["ret_10d"] = None
            row_copy["ret_20d"] = None
            row_copy["ret_30d"] = None
            result.append(row_copy)
            continue
        start_idx = ticker_state["positions"].get(str(row["anchor_date"]))
        if start_idx is None:
            row_copy["ret_5d"] = None
            row_copy["ret_10d"] = None
            row_copy["ret_20d"] = None
            row_copy["ret_30d"] = None
            result.append(row_copy)
            continue
        closes = ticker_state["closes"]
        row_copy["ret_5d"] = calc_return(closes, start_idx, 5)
        row_copy["ret_10d"] = calc_return(closes, start_idx, 10)
        row_copy["ret_20d"] = calc_return(closes, start_idx, 20)
        row_copy["ret_30d"] = calc_return(closes, start_idx, 30)
        result.append(row_copy)
    return result


def _finalize_filtered_rows(
    db_path: str,
    *,
    event_class: str | None,
    anchor: str = "event",
    min_gap: int,
    max_gap: int,
    min_drop: float,
    max_drop: float,
    min_rsi: float,
    max_rsi: float,
    market: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    trend_filter: str = "all",
    combo_pattern: str | None = None,
    combo_offset_min: int | None = None,
    combo_offset_max: int | None = None,
    stock_db_path: str | None = None,
) -> list[dict[str, Any]]:
    _validate_anchor(anchor)
    stock_path = _resolve_stock_db_path(db_path, stock_db_path)
    rows = _fetch_base_divergence_rows(
        db_path,
        event_class=event_class,
        anchor=anchor,
        min_gap=min_gap,
        max_gap=max_gap,
        min_drop=min_drop,
        max_drop=max_drop,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        market=market,
        start_date=start_date,
        end_date=end_date,
        stock_db_path=stock_path,
    )
    rows = _attach_downtrend_flags(rows, stock_path)
    rows = _apply_trend_filter(rows, trend_filter)
    rows = _attach_anchor_fields(rows, event_class=event_class, anchor=anchor)
    rows = _attach_combo_fields(rows, db_path, stock_path)
    rows = _apply_combo_filters(rows, combo_pattern, combo_offset_min, combo_offset_max)
    return _attach_forward_returns(rows, stock_path)


def _sort_rows(
    rows: list[dict[str, Any]],
    sort_by: str,
    sort_desc: bool,
) -> list[dict[str, Any]]:
    sort_key_name = sort_by if sort_by in VALID_SORT_COLUMNS else "date"

    def sort_key(row: dict[str, Any]) -> tuple[int, Any, str, str]:
        value = row.get(sort_key_name)
        if value is None:
            normalized: Any = ""
            marker = 1
        else:
            marker = 0
            normalized = value.lower() if isinstance(value, str) else float(value)
        return (marker, normalized, str(row["ticker"]), str(row["date"]))

    return sorted(rows, key=sort_key, reverse=sort_desc)


def fetch_divergence_events(
    db_path: str,
    event_class: str | None = None,
    anchor: str = "event",
    min_gap: int = 5,
    max_gap: int = 24,
    min_drop: float = 0.0,
    max_drop: float = 50.0,
    min_rsi: float = 1.0,
    max_rsi: float = 100.0,
    market: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    trend_filter: str = "all",
    combo_pattern: str | None = None,
    combo_offset_min: int | None = None,
    combo_offset_max: int | None = None,
    limit: int = 500,
    offset: int = 0,
    sort_by: str = "date",
    sort_desc: bool = True,
    stock_db_path: str | None = None,
) -> list[dict[str, Any]]:
    rows = _finalize_filtered_rows(
        db_path,
        event_class=event_class,
        anchor=anchor,
        min_gap=min_gap,
        max_gap=max_gap,
        min_drop=min_drop,
        max_drop=max_drop,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        market=market,
        start_date=start_date,
        end_date=end_date,
        trend_filter=trend_filter,
        combo_pattern=combo_pattern,
        combo_offset_min=combo_offset_min,
        combo_offset_max=combo_offset_max,
        stock_db_path=stock_db_path,
    )
    sorted_rows = _sort_rows(rows, sort_by, sort_desc)
    return sorted_rows[offset : offset + limit]


def summarize_divergence_events(
    db_path: str,
    event_class: str | None = None,
    anchor: str = "event",
    min_gap: int = 5,
    max_gap: int = 24,
    min_drop: float = 0.0,
    max_drop: float = 50.0,
    min_rsi: float = 1.0,
    max_rsi: float = 100.0,
    market: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    trend_filter: str = "all",
    combo_pattern: str | None = None,
    combo_offset_min: int | None = None,
    combo_offset_max: int | None = None,
    stock_db_path: str | None = None,
) -> dict[str, Any]:
    rows = _finalize_filtered_rows(
        db_path,
        event_class=event_class,
        anchor=anchor,
        min_gap=min_gap,
        max_gap=max_gap,
        min_drop=min_drop,
        max_drop=max_drop,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        market=market,
        start_date=start_date,
        end_date=end_date,
        trend_filter=trend_filter,
        combo_pattern=combo_pattern,
        combo_offset_min=combo_offset_min,
        combo_offset_max=combo_offset_max,
        stock_db_path=stock_db_path,
    )
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
    anchor: str = "event",
    min_gap: int = 5,
    max_gap: int = 24,
    min_drop: float = 0.0,
    max_drop: float = 50.0,
    min_rsi: float = 1.0,
    max_rsi: float = 100.0,
    market: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    trend_filter: str = "all",
    combo_pattern: str | None = None,
    combo_offset_min: int | None = None,
    combo_offset_max: int | None = None,
    stock_db_path: str | None = None,
) -> list[dict[str, Any]]:
    geometry_scope = _geometry_scope(event_class)
    rows = _finalize_filtered_rows(
        db_path,
        event_class=event_class,
        anchor=anchor,
        min_gap=min_gap,
        max_gap=max_gap,
        min_drop=min_drop,
        max_drop=max_drop,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        market=market,
        start_date=start_date,
        end_date=end_date,
        trend_filter=trend_filter,
        combo_pattern=combo_pattern,
        combo_offset_min=combo_offset_min,
        combo_offset_max=combo_offset_max,
        stock_db_path=stock_db_path,
    )
    grouped: dict[tuple[int, int], list[float]] = {}
    for row in rows:
        ret_30d = row["ret_30d"]
        if ret_30d is None:
            continue
        geometry_values: list[tuple[Any, Any]] = []
        if geometry_scope in {"R2", "BOTH"}:
            geometry_values.append((row["pivot_gap_r2"], row["pivot_drop_pct_r2"]))
        if geometry_scope in {"R3", "BOTH"}:
            geometry_values.append((row["pivot_gap_r3"], row["pivot_drop_pct_r3"]))
        for gap_value, drop_value in geometry_values:
            if gap_value is None or drop_value is None:
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
                "winsor_ret_30d": sum(
                    max(-50.0, min(50.0, value)) for value in values
                )
                / len(values),
                "n": len(values),
            }
        )
    return result


def export_divergence_events_csv(
    db_path: str,
    event_class: str | None = None,
    anchor: str = "event",
    min_gap: int = 5,
    max_gap: int = 24,
    min_drop: float = 0.0,
    max_drop: float = 50.0,
    min_rsi: float = 1.0,
    max_rsi: float = 100.0,
    market: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    trend_filter: str = "all",
    combo_pattern: str | None = None,
    combo_offset_min: int | None = None,
    combo_offset_max: int | None = None,
    export_path: str | None = None,
    stock_db_path: str | None = None,
) -> str:
    rows = fetch_divergence_events(
        db_path,
        event_class=event_class,
        anchor=anchor,
        min_gap=min_gap,
        max_gap=max_gap,
        min_drop=min_drop,
        max_drop=max_drop,
        min_rsi=min_rsi,
        max_rsi=max_rsi,
        market=market,
        start_date=start_date,
        end_date=end_date,
        trend_filter=trend_filter,
        combo_pattern=combo_pattern,
        combo_offset_min=combo_offset_min,
        combo_offset_max=combo_offset_max,
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
