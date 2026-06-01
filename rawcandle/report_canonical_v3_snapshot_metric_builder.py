from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict


ALLOWED_FRESHNESS = {"FRESH", "AGING", "STALE", "EXPIRED", "MISSING", "UNKNOWN"}
WINDOW_SOURCE_MAP = {
    "daily": "daily",
    "rolling2": "rolling2",
    "rolling5": "rolling5",
    "rolling30": "rolling30",
}
GROUP_TYPE_BY_ENTITY_TYPE = {
    "LAYER": "layer",
    "SUBINDUSTRY": "subindustry",
}


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _fetch_one(
    conn: sqlite3.Connection,
    query: str,
    params: tuple[object, ...],
) -> sqlite3.Row | None:
    return conn.execute(query, params).fetchone()


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _resolve_run(conn: sqlite3.Connection, run_id: str) -> sqlite3.Row:
    row = _fetch_one(
        conn,
        """
        SELECT
            rr.run_id,
            rr.ecosystem_id,
            ee.ecosystem_code,
            rr.taxonomy_version_id,
            tv.version_code,
            rr.signal_date
        FROM eco_report_run rr
        JOIN eco_ecosystem ee ON ee.ecosystem_id = rr.ecosystem_id
        JOIN eco_taxonomy_version tv ON tv.taxonomy_version_id = rr.taxonomy_version_id
        WHERE rr.run_id = ?
        """,
        (run_id,),
    )
    if row is None:
        raise ValueError(f"Missing eco_report_run for run_id '{run_id}'")
    return row


def _load_coverage_rows(conn: sqlite3.Connection, run_id: str) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT
            c.run_id,
            c.ecosystem_id,
            c.signal_date,
            c.taxonomy_version_id,
            c.window_code,
            c.entity_id,
            c.in_taxonomy,
            c.in_watchlist,
            c.has_instrument,
            c.has_price_data,
            c.has_daily_signal,
            c.has_window_context,
            c.coverage_status,
            c.source_row_count,
            c.missing_component_count,
            c.coverage_notes,
            e.entity_type,
            e.entity_code,
            e.entity_name,
            e.ticker,
            e.status AS entity_status
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
        ORDER BY c.entity_id, c.window_code
        """,
        (run_id,),
    ).fetchall()
    if not rows:
        raise ValueError(f"Missing eco_entity_coverage rows for run_id '{run_id}'")
    return rows


def _load_quality_rows(conn: sqlite3.Connection, run_id: str) -> dict[tuple[str, str], sqlite3.Row]:
    return {
        (row["window_code"], row["quality_scope"]): row
        for row in conn.execute(
            """
            SELECT *
            FROM eco_quality_summary
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchall()
    }


def _normalize_freshness(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    if text in ALLOWED_FRESHNESS:
        return text
    return None


def _load_daily_ticker_context(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> dict[str, sqlite3.Row]:
    if not _table_exists(conn, "dc_report_context_daily_v2"):
        return {}
    rows = conn.execute(
        """
        SELECT
            ticker,
            trend_state,
            context_readiness_status,
            freshness_status,
            return_5d,
            return_10d,
            return_20d,
            return_60d,
            distance_to_ema10_pct,
            distance_to_ema20_pct,
            latest_structure_age_trading_days,
            latest_bos_age_trading_days,
            latest_reset_age_trading_days,
            run_id
        FROM dc_report_context_daily_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version_code),
    ).fetchall()
    return {str(row["ticker"]): row for row in rows}


def _load_window_ticker_context(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> dict[tuple[str, str], sqlite3.Row]:
    if not _table_exists(conn, "dc_report_context_window_v2"):
        return {}
    rows = conn.execute(
        """
        SELECT
            ticker,
            horizon,
            trend_state,
            context_readiness_status,
            freshness_status,
            breakout_days,
            pullback_days,
            exit_risk_days,
            high_exit_risk_days,
            medium_exit_risk_days,
            valid_signal_dates,
            distance_to_ema20_pct,
            run_id
        FROM dc_report_context_window_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version_code),
    ).fetchall()
    return {(str(row["ticker"]), str(row["horizon"])): row for row in rows}


def _load_group_context(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> dict[tuple[str, str, str], sqlite3.Row]:
    if not _table_exists(conn, "dc_report_context_group_v2"):
        return {}
    rows = conn.execute(
        """
        SELECT
            horizon,
            group_type,
            group_name,
            timing_state,
            synthetic_trend_classification,
            group_current_status,
            group_window_status,
            synthetic_latest_bos_freshness,
            synthetic_latest_reset_freshness,
            return_2d,
            return_5d,
            return_30d,
            synthetic_close,
            pct_above_ema20,
            trend_breadth,
            weakness_breadth,
            strength_breadth,
            valid_signal_dates,
            window_end_date,
            run_id,
            data_quality_status
        FROM dc_report_context_group_v2
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version_code),
    ).fetchall()
    return {
        (str(row["group_type"]), str(row["group_name"]), str(row["horizon"])): row
        for row in rows
    }


def _load_classifications(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> dict[tuple[str, str], str | None]:
    if not _table_exists(conn, "dc_report_classification_v2"):
        return {}
    rows = conn.execute(
        """
        SELECT ticker, horizon, classification_type, classification_state
        FROM dc_report_classification_v2
        WHERE signal_date = ? AND taxonomy_version = ? AND classification_status = 'OK'
        ORDER BY ticker, horizon, classification_type
        """,
        (signal_date, taxonomy_version_code),
    ).fetchall()
    grouped: dict[tuple[str, str], list[str]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["ticker"]), str(row["horizon"]))].append(str(row["classification_state"]))
    resolved: dict[tuple[str, str], str | None] = {}
    for key, states in grouped.items():
        resolved[key] = states[0] if len(states) == 1 else None
    return resolved


def _quality_status_from_coverage(coverage_status: str, source_exists: bool) -> str:
    if coverage_status == "WATCHLIST_ONLY":
        return "WARN"
    if not source_exists:
        return "MISSING"
    if coverage_status == "OK":
        return "OK"
    if coverage_status == "MISSING_DAILY_SIGNAL":
        return "MISSING"
    return "WARN"


def _snapshot_status_from_coverage(coverage_status: str, source_exists: bool) -> str:
    if coverage_status == "WATCHLIST_ONLY":
        return "WARN"
    if not source_exists:
        return "MISSING"
    return "OK"


def _append_numeric_metric(
    metric_rows: list[dict[str, object]],
    *,
    base_row: sqlite3.Row,
    metric_name: str,
    metric_value: object,
) -> None:
    if metric_value is None:
        return
    metric_rows.append(
        {
            "run_id": base_row["run_id"],
            "ecosystem_id": base_row["ecosystem_id"],
            "signal_date": base_row["signal_date"],
            "taxonomy_version_id": base_row["taxonomy_version_id"],
            "window_code": base_row["window_code"],
            "entity_id": base_row["entity_id"],
            "metric_name": metric_name,
            "metric_value_num": metric_value,
            "metric_value_text": None,
            "metric_unit": None,
            "value_status": "OK",
            "source_run_id": None,
        }
    )


def _build_ecosystem_rows(
    coverage_row: sqlite3.Row,
    *,
    window_rows: list[sqlite3.Row],
    quality_row: sqlite3.Row | None,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    if not window_rows:
        snapshot_status = "MISSING"
        quality_status = "MISSING"
    elif quality_row is not None and quality_row["quality_status"] == "WARN":
        snapshot_status = "WARN"
        quality_status = "WARN"
    else:
        snapshot_status = "OK"
        quality_status = "OK"

    ok_coverage_count = sum(1 for row in window_rows if row["coverage_status"] == "OK")
    watchlist_only_count = sum(1 for row in window_rows if row["coverage_status"] == "WATCHLIST_ONLY")
    missing_coverage_count = sum(1 for row in window_rows if row["coverage_status"] != "OK")
    warning_count = sum(
        1
        for row in window_rows
        if row["coverage_status"] in {"WATCHLIST_ONLY", "MISSING_DAILY_SIGNAL", "UNKNOWN"}
    )
    selected_entity_count = len(window_rows)

    snapshot_row = {
        "run_id": coverage_row["run_id"],
        "ecosystem_id": coverage_row["ecosystem_id"],
        "signal_date": coverage_row["signal_date"],
        "taxonomy_version_id": coverage_row["taxonomy_version_id"],
        "window_code": coverage_row["window_code"],
        "entity_id": coverage_row["entity_id"],
        "snapshot_status": snapshot_status,
        "timing_state": None,
        "trend_state": None,
        "summary_state": None,
        "classification_state": None,
        "freshness_status": None,
        "quality_status": quality_status,
        "asof_observed_at": coverage_row["signal_date"],
        "source_run_id": None,
    }

    metric_rows: list[dict[str, object]] = []
    for metric_name, metric_value in (
        ("selected_entity_count", selected_entity_count),
        ("ok_coverage_count", ok_coverage_count),
        ("watchlist_only_count", watchlist_only_count),
        ("missing_coverage_count", missing_coverage_count),
        ("warning_count", warning_count),
    ):
        _append_numeric_metric(metric_rows, base_row=coverage_row, metric_name=metric_name, metric_value=metric_value)
    return snapshot_row, metric_rows


def _build_ticker_rows(
    coverage_row: sqlite3.Row,
    *,
    daily_context: dict[str, sqlite3.Row],
    window_context: dict[tuple[str, str], sqlite3.Row],
    classifications: dict[tuple[str, str], str | None],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    ticker = str(coverage_row["ticker"] or coverage_row["entity_code"])
    window_code = str(coverage_row["window_code"])
    source_row = (
        daily_context.get(ticker)
        if window_code == "daily"
        else window_context.get((ticker, WINDOW_SOURCE_MAP[window_code]))
    )
    source_exists = source_row is not None
    classification_state = classifications.get((ticker, window_code))
    snapshot_row = {
        "run_id": coverage_row["run_id"],
        "ecosystem_id": coverage_row["ecosystem_id"],
        "signal_date": coverage_row["signal_date"],
        "taxonomy_version_id": coverage_row["taxonomy_version_id"],
        "window_code": coverage_row["window_code"],
        "entity_id": coverage_row["entity_id"],
        "snapshot_status": _snapshot_status_from_coverage(str(coverage_row["coverage_status"]), source_exists),
        "timing_state": None,
        "trend_state": source_row["trend_state"] if source_exists else None,
        "summary_state": source_row["context_readiness_status"] if source_exists else None,
        "classification_state": classification_state,
        "freshness_status": _normalize_freshness(source_row["freshness_status"]) if source_exists else None,
        "quality_status": _quality_status_from_coverage(str(coverage_row["coverage_status"]), source_exists),
        "asof_observed_at": coverage_row["signal_date"],
        "source_run_id": source_row["run_id"] if source_exists else None,
    }

    metric_rows: list[dict[str, object]] = []
    if not source_exists:
        return snapshot_row, metric_rows

    if window_code == "daily":
        metric_specs = (
            "return_5d",
            "return_10d",
            "return_20d",
            "return_60d",
            "distance_to_ema10_pct",
            "distance_to_ema20_pct",
            "latest_structure_age_trading_days",
            "latest_bos_age_trading_days",
            "latest_reset_age_trading_days",
        )
    else:
        metric_specs = (
            "breakout_days",
            "pullback_days",
            "exit_risk_days",
            "high_exit_risk_days",
            "medium_exit_risk_days",
            "valid_signal_dates",
            "distance_to_ema20_pct",
        )
    for metric_name in metric_specs:
        _append_numeric_metric(metric_rows, base_row=coverage_row, metric_name=metric_name, metric_value=source_row[metric_name])
    for row in metric_rows:
        row["source_run_id"] = source_row["run_id"]
    return snapshot_row, metric_rows


def _build_group_rows(
    coverage_row: sqlite3.Row,
    *,
    group_context: dict[tuple[str, str, str], sqlite3.Row],
) -> tuple[dict[str, object], list[dict[str, object]]]:
    group_type = GROUP_TYPE_BY_ENTITY_TYPE[str(coverage_row["entity_type"])]
    source_row = group_context.get((group_type, str(coverage_row["entity_name"]), str(coverage_row["window_code"])))
    source_exists = source_row is not None
    freshness_value = None
    if source_exists:
        freshness_value = _normalize_freshness(source_row["synthetic_latest_bos_freshness"])
        if freshness_value is None:
            freshness_value = _normalize_freshness(source_row["synthetic_latest_reset_freshness"])
    snapshot_row = {
        "run_id": coverage_row["run_id"],
        "ecosystem_id": coverage_row["ecosystem_id"],
        "signal_date": coverage_row["signal_date"],
        "taxonomy_version_id": coverage_row["taxonomy_version_id"],
        "window_code": coverage_row["window_code"],
        "entity_id": coverage_row["entity_id"],
        "snapshot_status": "OK" if source_exists else "MISSING",
        "timing_state": source_row["timing_state"] if source_exists else None,
        "trend_state": source_row["synthetic_trend_classification"] if source_exists else None,
        "summary_state": (
            source_row["group_window_status"]
            if source_exists and source_row["group_window_status"] is not None
            else source_row["group_current_status"] if source_exists else None
        ),
        "classification_state": None,
        "freshness_status": freshness_value,
        "quality_status": "OK" if source_exists else "MISSING",
        "asof_observed_at": source_row["window_end_date"] if source_exists else coverage_row["signal_date"],
        "source_run_id": source_row["run_id"] if source_exists else None,
    }

    metric_rows: list[dict[str, object]] = []
    if not source_exists:
        return snapshot_row, metric_rows

    for metric_name in (
        "return_2d",
        "return_5d",
        "return_30d",
        "synthetic_close",
        "pct_above_ema20",
        "trend_breadth",
        "weakness_breadth",
        "strength_breadth",
        "valid_signal_dates",
    ):
        _append_numeric_metric(metric_rows, base_row=coverage_row, metric_name=metric_name, metric_value=source_row[metric_name])
    for row in metric_rows:
        row["source_run_id"] = source_row["run_id"]
    return snapshot_row, metric_rows


def _build_snapshot_and_metric_rows(
    conn: sqlite3.Connection,
    *,
    run_row: sqlite3.Row,
    coverage_rows: list[sqlite3.Row],
    quality_rows: dict[tuple[str, str], sqlite3.Row],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[str]]:
    daily_context = _load_daily_ticker_context(
        conn,
        signal_date=str(run_row["signal_date"]),
        taxonomy_version_code=str(run_row["version_code"]),
    )
    window_context = _load_window_ticker_context(
        conn,
        signal_date=str(run_row["signal_date"]),
        taxonomy_version_code=str(run_row["version_code"]),
    )
    group_context = _load_group_context(
        conn,
        signal_date=str(run_row["signal_date"]),
        taxonomy_version_code=str(run_row["version_code"]),
    )
    classifications = _load_classifications(
        conn,
        signal_date=str(run_row["signal_date"]),
        taxonomy_version_code=str(run_row["version_code"]),
    )

    coverage_by_window: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in coverage_rows:
        coverage_by_window[str(row["window_code"])].append(row)

    snapshot_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    warnings: Counter[str] = Counter()

    for coverage_row in coverage_rows:
        entity_type = str(coverage_row["entity_type"])
        if entity_type == "ECOSYSTEM":
            snapshot_row, entity_metric_rows = _build_ecosystem_rows(
                coverage_row,
                window_rows=coverage_by_window[str(coverage_row["window_code"])],
                quality_row=quality_rows.get((str(coverage_row["window_code"]), "WINDOW")),
            )
        elif entity_type == "TICKER":
            snapshot_row, entity_metric_rows = _build_ticker_rows(
                coverage_row,
                daily_context=daily_context,
                window_context=window_context,
                classifications=classifications,
            )
        else:
            snapshot_row, entity_metric_rows = _build_group_rows(
                coverage_row,
                group_context=group_context,
            )

        snapshot_rows.append(snapshot_row)
        metric_rows.extend(entity_metric_rows)

        if snapshot_row["snapshot_status"] == "WARN":
            warnings["warn_snapshot_rows"] += 1
        elif snapshot_row["snapshot_status"] == "MISSING":
            warnings["missing_snapshot_rows"] += 1

    warning_messages = [f"{key}={warnings[key]}" for key in sorted(warnings)]
    return snapshot_rows, metric_rows, warning_messages


def _insert_snapshot_rows(conn: sqlite3.Connection, snapshot_rows: list[dict[str, object]]) -> None:
    conn.executemany(
        """
        INSERT INTO eco_entity_window_snapshot (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code,
            entity_id, snapshot_status, timing_state, trend_state, summary_state,
            classification_state, freshness_status, quality_status, asof_observed_at,
            source_run_id
        ) VALUES (
            :run_id, :ecosystem_id, :signal_date, :taxonomy_version_id, :window_code,
            :entity_id, :snapshot_status, :timing_state, :trend_state, :summary_state,
            :classification_state, :freshness_status, :quality_status, :asof_observed_at,
            :source_run_id
        )
        """,
        snapshot_rows,
    )


def _insert_metric_rows(conn: sqlite3.Connection, metric_rows: list[dict[str, object]]) -> None:
    conn.executemany(
        """
        INSERT INTO eco_entity_metric_value (
            run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code,
            entity_id, metric_name, metric_value_num, metric_value_text, metric_unit,
            value_status, source_run_id
        ) VALUES (
            :run_id, :ecosystem_id, :signal_date, :taxonomy_version_id, :window_code,
            :entity_id, :metric_name, :metric_value_num, :metric_value_text, :metric_unit,
            :value_status, :source_run_id
        )
        """,
        metric_rows,
    )


def build_canonical_v3_snapshot_metrics(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_coverage_rows(conn, run_id)
        quality_rows = _load_quality_rows(conn, run_id)

        existing_snapshot_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM eco_entity_window_snapshot WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
        )
        existing_metric_count = int(
            conn.execute(
                "SELECT COUNT(*) FROM eco_entity_metric_value WHERE run_id = ?",
                (run_id,),
            ).fetchone()[0]
        )
        if not replace_existing and (existing_snapshot_count > 0 or existing_metric_count > 0):
            raise ValueError(f"Snapshot or metric rows already exist for run_id '{run_id}'")

        snapshot_rows, metric_rows, warnings = _build_snapshot_and_metric_rows(
            conn,
            run_row=run_row,
            coverage_rows=coverage_rows,
            quality_rows=quality_rows,
        )

        conn.execute("BEGIN")
        if replace_existing:
            conn.execute("DELETE FROM eco_entity_metric_value WHERE run_id = ?", (run_id,))
            conn.execute("DELETE FROM eco_entity_window_snapshot WHERE run_id = ?", (run_id,))
        _insert_snapshot_rows(conn, snapshot_rows)
        _insert_metric_rows(conn, metric_rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    snapshot_status_counts = Counter(str(row["snapshot_status"]) for row in snapshot_rows)
    metric_name_counts = Counter(str(row["metric_name"]) for row in metric_rows)
    selected_entity_count = len({int(row["entity_id"]) for row in coverage_rows})
    window_count = len({str(row["window_code"]) for row in coverage_rows})
    warning_count = sum(1 for row in snapshot_rows if str(row["snapshot_status"]) != "OK")
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_code": str(run_row["ecosystem_code"]),
        "taxonomy_version_code": str(run_row["version_code"]),
        "signal_date": str(run_row["signal_date"]),
        "selected_entity_count": selected_entity_count,
        "window_count": window_count,
        "snapshot_rows_inserted": len(snapshot_rows),
        "metric_rows_inserted": len(metric_rows),
        "snapshot_status_counts": dict(sorted(snapshot_status_counts.items())),
        "metric_name_counts": dict(sorted(metric_name_counts.items())),
        "warning_count": warning_count,
        "warnings": warnings,
    }
