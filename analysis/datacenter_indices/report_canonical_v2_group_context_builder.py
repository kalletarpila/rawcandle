from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Iterable

ALLOWED_HORIZONS = ("daily", "rolling2", "rolling5", "rolling30")
HORIZON_WINDOW_SIZES = {
    "daily": 1,
    "rolling2": 2,
    "rolling5": 5,
    "rolling30": 30,
}
DEFAULT_GROUP_CONTEXT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
DEFAULT_GROUP_CONTEXT_OHLC_CALC_VERSION = "DC_SWING_OHLC_V1"

# Keep the same severity ordering used by the current weekly report path.
ROLLING_GROUP_STATUS_PRIORITY = {
    "EXIT_ZONE": 0,
    "TRIM_WATCH": 1,
    "ADD_ON_PULLBACK": 2,
    "BUY_ZONE": 3,
    "NEUTRAL": 4,
    None: 5,
}

RISK_TIMING_STATES = {"EXIT_ZONE", "TRIM_WATCH"}
RISK_OVERHEAT_LEVELS = {"HIGH", "EXTREME"}
GROUP_BREADTH_FIELDS = (
    "ema20_breadth_delta_5d",
    "ma10_breadth_delta_5d",
    "trend_breadth",
    "weakness_breadth",
    "strength_breadth",
)
SYNTHETIC_EMA_DISTANCE_FIELDS = (
    "distance_to_ema10_pct",
    "distance_to_ema20_pct",
    "distance_to_ema50_pct",
    "distance_to_ema200_pct",
    "synthetic_distance_to_ema10_pct",
    "synthetic_distance_to_ema20_pct",
    "synthetic_distance_to_ema50_pct",
    "synthetic_distance_to_ema200_pct",
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _row_to_dict(row: sqlite3.Row) -> dict[str, object]:
    return {key: row[key] for key in row.keys()}


def _get_table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def _ensure_run_exists(conn: sqlite3.Connection, run_id: str) -> None:
    row = conn.execute(
        "SELECT 1 FROM dc_report_run_v2 WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"dc_report_run_v2 row not found for run_id={run_id}")


def _normalize_horizons(horizons: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(horizon) for horizon in horizons))
    invalid = [horizon for horizon in normalized if horizon not in ALLOWED_HORIZONS]
    if invalid:
        raise ValueError(f"Unsupported horizons: {', '.join(invalid)}")
    return normalized


def _build_filter_sql(
    *,
    table_columns: set[str],
    date_field: str,
    selected_dates: tuple[str, ...],
    taxonomy_version: str,
    market: str | None,
    version_field: str,
    version_value: str | None,
) -> tuple[str, tuple[object, ...]]:
    placeholders = ", ".join("?" for _ in selected_dates)
    where_clauses = [f"{date_field} IN ({placeholders})", "taxonomy_version = ?"]
    params: list[object] = [*selected_dates, taxonomy_version]
    if market is not None and "market" in table_columns:
        where_clauses.append("market = ?")
        params.append(market)
    if version_value is not None and version_field in table_columns:
        where_clauses.append(f"{version_field} = ?")
        params.append(version_value)
    return " AND ".join(where_clauses), tuple(params)


def _load_valid_signal_dates(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    signal_version: str | None,
    limit: int,
) -> list[str]:
    table_columns = _get_table_columns(conn, "dc_group_swing_signal_daily")
    where_clauses = ["signal_date <= ?", "taxonomy_version = ?"]
    params: list[object] = [signal_date, taxonomy_version]
    if market is not None and "market" in table_columns:
        where_clauses.append("market = ?")
        params.append(market)
    if signal_version is not None and "signal_version" in table_columns:
        where_clauses.append("signal_version = ?")
        params.append(signal_version)
    rows = conn.execute(
        f"""
        SELECT DISTINCT signal_date
        FROM dc_group_swing_signal_daily
        WHERE {' AND '.join(where_clauses)}
        ORDER BY signal_date DESC
        LIMIT ?
        """,
        tuple(params) + (limit,),
    ).fetchall()
    return sorted(str(row[0]) for row in rows)


def _load_group_rows_for_dates(
    conn: sqlite3.Connection,
    *,
    selected_dates: tuple[str, ...],
    taxonomy_version: str,
    market: str | None,
    signal_version: str | None,
) -> list[dict[str, object]]:
    if not selected_dates:
        return []
    table_columns = _get_table_columns(conn, "dc_group_swing_signal_daily")
    where_sql, params = _build_filter_sql(
        table_columns=table_columns,
        date_field="signal_date",
        selected_dates=selected_dates,
        taxonomy_version=taxonomy_version,
        market=market,
        version_field="signal_version",
        version_value=signal_version,
    )
    rows = conn.execute(
        f"""
        SELECT *
        FROM dc_group_swing_signal_daily
        WHERE {where_sql}
        ORDER BY signal_date ASC, group_type ASC, group_name ASC
        """,
        params,
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _load_synthetic_rows_for_dates(
    conn: sqlite3.Connection,
    *,
    selected_dates: tuple[str, ...],
    taxonomy_version: str,
    market: str | None,
    ohlc_calc_version: str | None,
) -> list[dict[str, object]]:
    if not selected_dates:
        return []
    table_columns = _get_table_columns(conn, "dc_group_synthetic_ohlc_daily")
    where_sql, params = _build_filter_sql(
        table_columns=table_columns,
        date_field="ohlc_date",
        selected_dates=selected_dates,
        taxonomy_version=taxonomy_version,
        market=market,
        version_field="calc_version",
        version_value=ohlc_calc_version,
    )
    rows = conn.execute(
        f"""
        SELECT *
        FROM dc_group_synthetic_ohlc_daily
        WHERE {where_sql}
        ORDER BY ohlc_date ASC, group_type ASC, group_name ASC
        """,
        params,
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def _json_or_none(values: dict[str, object]) -> str | None:
    filtered = {key: value for key, value in values.items() if value is not None}
    if not filtered:
        return None
    return json.dumps(filtered, sort_keys=True)


def _build_breadth_json(group_row: dict[str, object]) -> str | None:
    return _json_or_none({field: group_row.get(field) for field in GROUP_BREADTH_FIELDS})


def _build_synthetic_ema_distance_json(synthetic_row: dict[str, object]) -> str | None:
    return _json_or_none({field: synthetic_row.get(field) for field in SYNTHETIC_EMA_DISTANCE_FIELDS})


def _group_context_risk_status(*, timing_state: object | None, overheat_risk_level: object | None) -> str:
    has_risk = timing_state in RISK_TIMING_STATES or overheat_risk_level in RISK_OVERHEAT_LEVELS
    return "YES" if has_risk else "NO"


def _group_context_readiness_status(
    *,
    current_group_row: dict[str, object] | None,
    synthetic_row: dict[str, object] | None,
    valid_signal_dates: int | None,
    expected_window_size: int,
) -> str:
    if current_group_row is None:
        return "MISSING_GROUP_SOURCE"
    if synthetic_row is None:
        return "MISSING_SYNTHETIC_SOURCE"
    if valid_signal_dates is not None and valid_signal_dates < expected_window_size:
        return "PARTIAL_WINDOW"
    return "OK"


def _most_severe_group_status(group_rows: list[dict[str, object]]) -> object | None:
    if not group_rows:
        return None
    return min(
        (row.get("timing_state") for row in group_rows),
        key=lambda value: ROLLING_GROUP_STATUS_PRIORITY.get(value, 6),
    )


def _status_change(first_row: dict[str, object] | None, last_row: dict[str, object] | None) -> str | None:
    first_status = None if first_row is None else first_row.get("timing_state")
    last_status = None if last_row is None else last_row.get("timing_state")
    if not first_status or not last_status or first_status == last_status:
        return None
    return f"{first_status} -> {last_status}"


def _write_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
    horizons: tuple[str, ...],
    rows: list[dict[str, object]],
) -> None:
    placeholders = ", ".join("?" for _ in horizons)
    if market is None:
        conn.execute(
            f"""
            DELETE FROM dc_report_context_group_v2
            WHERE signal_date = ?
              AND taxonomy_version = ?
              AND horizon IN ({placeholders})
            """,
            (signal_date, taxonomy_version, *horizons),
        )
    else:
        conn.execute(
            f"""
            DELETE FROM dc_report_context_group_v2
            WHERE signal_date = ?
              AND taxonomy_version = ?
              AND horizon IN ({placeholders})
              AND market = ?
            """,
            (signal_date, taxonomy_version, *horizons, market),
        )
    if not rows:
        return
    conn.executemany(
        """
        INSERT INTO dc_report_context_group_v2 (
            signal_date,
            taxonomy_version,
            market,
            horizon,
            group_type,
            group_name,
            parent_group_type,
            parent_group_name,
            timing_state,
            overheat_risk_level,
            return_2d,
            return_5d,
            return_30d,
            breadth_json,
            synthetic_close,
            synthetic_ema_distance_json,
            synthetic_trend_classification,
            synthetic_latest_structure_label,
            synthetic_latest_bos_event_type,
            synthetic_latest_bos_freshness,
            synthetic_latest_reset_reason,
            synthetic_latest_reset_freshness,
            group_context_risk_status,
            group_context_readiness_status,
            group_current_status,
            group_window_status,
            group_status_change,
            window_start_date,
            window_end_date,
            valid_signal_dates,
            run_id,
            created_at_utc
        ) VALUES (
            :signal_date,
            :taxonomy_version,
            :market,
            :horizon,
            :group_type,
            :group_name,
            :parent_group_type,
            :parent_group_name,
            :timing_state,
            :overheat_risk_level,
            :return_2d,
            :return_5d,
            :return_30d,
            :breadth_json,
            :synthetic_close,
            :synthetic_ema_distance_json,
            :synthetic_trend_classification,
            :synthetic_latest_structure_label,
            :synthetic_latest_bos_event_type,
            :synthetic_latest_bos_freshness,
            :synthetic_latest_reset_reason,
            :synthetic_latest_reset_freshness,
            :group_context_risk_status,
            :group_context_readiness_status,
            :group_current_status,
            :group_window_status,
            :group_status_change,
            :window_start_date,
            :window_end_date,
            :valid_signal_dates,
            :run_id,
            :created_at_utc
        )
        """,
        rows,
    )


def build_report_group_context_v2(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    run_id: str,
    market: str | None = None,
    horizons: tuple[str, ...] = ("daily", "rolling2", "rolling5", "rolling30"),
    signal_version: str | None = DEFAULT_GROUP_CONTEXT_SIGNAL_VERSION,
    ohlc_calc_version: str | None = DEFAULT_GROUP_CONTEXT_OHLC_CALC_VERSION,
    calculation_version: str = "REPORT_CANONICAL_GROUP_CONTEXT_V2_1",
    created_at_utc: str | None = None,
) -> dict[str, int]:
    del calculation_version
    conn.row_factory = sqlite3.Row
    _ensure_run_exists(conn, run_id)
    normalized_horizons = _normalize_horizons(horizons)
    created_at_value = created_at_utc or _utc_now_iso()

    rows_to_write: list[dict[str, object]] = []
    source_group_rows_read = 0
    source_synthetic_rows_read = 0
    written_counts = {
        "daily_rows_written": 0,
        "rolling2_rows_written": 0,
        "rolling5_rows_written": 0,
        "rolling30_rows_written": 0,
    }

    for horizon in normalized_horizons:
        expected_window_size = HORIZON_WINDOW_SIZES[horizon]
        selected_dates = (
            [signal_date]
            if horizon == "daily"
            else _load_valid_signal_dates(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                market=market,
                signal_version=signal_version,
                limit=expected_window_size,
            )
        )
        if horizon == "daily" and not selected_dates:
            selected_dates = _load_valid_signal_dates(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
                market=market,
                signal_version=signal_version,
                limit=1,
            )
        selected_dates_tuple = tuple(selected_dates)
        group_rows = _load_group_rows_for_dates(
            conn,
            selected_dates=selected_dates_tuple,
            taxonomy_version=taxonomy_version,
            market=market,
            signal_version=signal_version,
        )
        synthetic_rows = _load_synthetic_rows_for_dates(
            conn,
            selected_dates=selected_dates_tuple,
            taxonomy_version=taxonomy_version,
            market=market,
            ohlc_calc_version=ohlc_calc_version,
        )
        source_group_rows_read += len(group_rows)
        source_synthetic_rows_read += len(synthetic_rows)

        group_rows_by_key: dict[tuple[str, str], list[dict[str, object]]] = {}
        for row in group_rows:
            key = (str(row.get("group_type") or ""), str(row.get("group_name") or ""))
            if not key[0] or not key[1]:
                continue
            group_rows_by_key.setdefault(key, []).append(row)
        for grouped_rows in group_rows_by_key.values():
            grouped_rows.sort(key=lambda row: str(row.get("signal_date") or ""))

        synthetic_rows_by_key = {
            (
                str(row.get("ohlc_date") or ""),
                str(row.get("group_type") or ""),
                str(row.get("group_name") or ""),
            ): row
            for row in synthetic_rows
        }

        valid_signal_dates = None if horizon == "daily" else len(selected_dates_tuple)
        window_start_date = None if horizon == "daily" else (selected_dates_tuple[0] if selected_dates_tuple else None)
        window_end_date = signal_date if horizon == "daily" else (selected_dates_tuple[-1] if selected_dates_tuple else signal_date)

        for (group_type, group_name), grouped_rows in sorted(group_rows_by_key.items()):
            first_row = grouped_rows[0] if grouped_rows else None
            last_row = grouped_rows[-1] if grouped_rows else None
            current_group_row = None
            for row in reversed(grouped_rows):
                if str(row.get("signal_date") or "") == window_end_date:
                    current_group_row = row
                    break
            snapshot_row = current_group_row or last_row
            synthetic_row = synthetic_rows_by_key.get((window_end_date, group_type, group_name), {})
            readiness_status = _group_context_readiness_status(
                current_group_row=current_group_row,
                synthetic_row=synthetic_row if synthetic_row else None,
                valid_signal_dates=valid_signal_dates,
                expected_window_size=expected_window_size,
            )
            rows_to_write.append(
                {
                    "signal_date": signal_date,
                    "taxonomy_version": taxonomy_version,
                    "market": market if market is not None else snapshot_row.get("market") if snapshot_row else None,
                    "horizon": horizon,
                    "group_type": group_type,
                    "group_name": group_name,
                    "parent_group_type": snapshot_row.get("parent_group_type") if snapshot_row else None,
                    "parent_group_name": snapshot_row.get("parent_group_name") if snapshot_row else None,
                    "timing_state": snapshot_row.get("timing_state") if snapshot_row else None,
                    "overheat_risk_level": snapshot_row.get("overheat_risk_level") if snapshot_row else None,
                    "return_2d": snapshot_row.get("return_2d") if snapshot_row else None,
                    "return_5d": snapshot_row.get("return_5d") if snapshot_row else None,
                    "return_30d": snapshot_row.get("return_30d") if snapshot_row else None,
                    "breadth_json": _build_breadth_json(snapshot_row or {}),
                    "synthetic_close": synthetic_row.get("synthetic_close"),
                    "synthetic_ema_distance_json": _build_synthetic_ema_distance_json(synthetic_row),
                    "synthetic_trend_classification": synthetic_row.get("trend_classification"),
                    "synthetic_latest_structure_label": synthetic_row.get("latest_structure_label"),
                    "synthetic_latest_bos_event_type": synthetic_row.get("latest_bos_event_type"),
                    "synthetic_latest_bos_freshness": synthetic_row.get("latest_bos_freshness"),
                    "synthetic_latest_reset_reason": synthetic_row.get("latest_reset_reason"),
                    "synthetic_latest_reset_freshness": synthetic_row.get("latest_reset_freshness"),
                    "group_context_risk_status": _group_context_risk_status(
                        timing_state=snapshot_row.get("timing_state") if snapshot_row else None,
                        overheat_risk_level=snapshot_row.get("overheat_risk_level") if snapshot_row else None,
                    ),
                    "group_context_readiness_status": readiness_status,
                    "group_current_status": snapshot_row.get("timing_state") if horizon == "daily" and snapshot_row else current_group_row.get("timing_state") if current_group_row else None,
                    "group_window_status": None if horizon == "daily" else _most_severe_group_status(grouped_rows),
                    "group_status_change": None if horizon == "daily" else _status_change(first_row, last_row),
                    "window_start_date": window_start_date,
                    "window_end_date": window_end_date,
                    "valid_signal_dates": valid_signal_dates,
                    "run_id": run_id,
                    "created_at_utc": created_at_value,
                }
            )
            written_counts[f"{horizon}_rows_written"] += 1

    _write_rows(
        conn,
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        market=market,
        horizons=normalized_horizons,
        rows=rows_to_write,
    )
    conn.commit()

    return {
        **written_counts,
        "total_rows_written": sum(written_counts.values()),
        "source_group_rows_read": source_group_rows_read,
        "source_synthetic_rows_read": source_synthetic_rows_read,
    }
