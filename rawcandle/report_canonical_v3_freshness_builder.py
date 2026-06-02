from __future__ import annotations

import sqlite3
from collections import Counter


DAILY_SOURCE_TABLE = "dc_report_context_daily_v2"
WINDOW_SOURCE_TABLE = "dc_report_context_window_v2"
GROUP_SOURCE_TABLE = "dc_group_synthetic_ohlc_daily"
FRESHNESS_SIGNAL_FAMILY = "FRESHNESS"
FRESHNESS_METRIC_PREFIX = "freshness_"
REQUIRED_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
REQUIRED_ENTITY_TYPES = ("TICKER", "LAYER", "SUBINDUSTRY")
SOURCE_CLASSIFICATIONS = {
    DAILY_SOURCE_TABLE: "TRANSITIONAL_V2_SOURCE",
    WINDOW_SOURCE_TABLE: "TRANSITIONAL_V2_SOURCE",
    GROUP_SOURCE_TABLE: "DERIVED_FROM_RAW_SOURCE",
}
METRIC_COLUMN_SPECS = (
    ("latest_structure_age_trading_days", "freshness_latest_structure_age_trading_days", "numeric"),
    ("latest_bos_age_trading_days", "freshness_latest_bos_age_trading_days", "numeric"),
    ("latest_reset_age_trading_days", "freshness_latest_reset_age_trading_days", "numeric"),
    ("latest_structure_freshness", "freshness_latest_structure_class", "text"),
    ("latest_bos_freshness", "freshness_latest_bos_class", "text"),
    ("latest_reset_freshness", "freshness_latest_reset_class", "text"),
    ("freshness_status", "freshness_overall_status", "text"),
)
SIGNAL_COLUMN_SPECS = (
    ("latest_structure_freshness", "STRUCTURE_FRESHNESS"),
    ("latest_bos_freshness", "BOS_FRESHNESS"),
    ("latest_reset_freshness", "RESET_FRESHNESS"),
    ("freshness_status", "OVERALL_FRESHNESS"),
)
GROUP_ENTITY_TYPE_MAP = {
    "layer": "LAYER",
    "subindustry": "SUBINDUSTRY",
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


def _column_names(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {str(row["name"]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _select_expr(column_names: set[str], preferred_names: tuple[str, ...], alias: str) -> str:
    for name in preferred_names:
        if name in column_names:
            return f"{name} AS {alias}"
    return f"NULL AS {alias}"


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


def _load_target_coverage(conn: sqlite3.Connection, run_row: sqlite3.Row) -> list[sqlite3.Row]:
    rows = conn.execute(
        """
        SELECT
            c.run_id,
            c.ecosystem_id,
            c.signal_date,
            c.taxonomy_version_id,
            c.window_code,
            c.entity_id,
            e.entity_type,
            e.entity_code,
            e.entity_name
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND c.signal_date = ?
          AND c.taxonomy_version_id = ?
          AND c.ecosystem_id = ?
          AND e.entity_type IN ('TICKER', 'LAYER', 'SUBINDUSTRY', 'ECOSYSTEM')
        ORDER BY e.entity_type, e.entity_id, c.window_code
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
        ),
    ).fetchall()
    if not rows:
        raise ValueError(f"Missing eco_entity_coverage rows for run_id '{run_row['run_id']}'")
    return rows


def _load_daily_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, DAILY_SOURCE_TABLE):
        return []
    columns = _column_names(conn, DAILY_SOURCE_TABLE)
    required = {"signal_date", "taxonomy_version", "ticker"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(
            f"Source table '{DAILY_SOURCE_TABLE}' missing required columns: {', '.join(missing)}"
        )
    query = f"""
        SELECT
            ticker,
            {_select_expr(columns, ('latest_structure_age_trading_days',), 'latest_structure_age_trading_days')},
            {_select_expr(columns, ('latest_bos_age_trading_days',), 'latest_bos_age_trading_days')},
            {_select_expr(columns, ('latest_reset_age_trading_days',), 'latest_reset_age_trading_days')},
            {_select_expr(columns, ('latest_structure_freshness',), 'latest_structure_freshness')},
            {_select_expr(columns, ('latest_bos_freshness',), 'latest_bos_freshness')},
            {_select_expr(columns, ('latest_reset_freshness',), 'latest_reset_freshness')},
            {_select_expr(columns, ('freshness_status',), 'freshness_status')},
            {_select_expr(columns, ('run_id', 'calc_version'), 'source_run_id')}
        FROM {DAILY_SOURCE_TABLE}
        WHERE signal_date = ?
          AND taxonomy_version = ?
        ORDER BY ticker
    """
    return conn.execute(query, (signal_date, taxonomy_version_code)).fetchall()


def _load_window_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, WINDOW_SOURCE_TABLE):
        return []
    columns = _column_names(conn, WINDOW_SOURCE_TABLE)
    required = {"signal_date", "taxonomy_version", "ticker", "horizon"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(
            f"Source table '{WINDOW_SOURCE_TABLE}' missing required columns: {', '.join(missing)}"
        )
    query = f"""
        SELECT
            ticker,
            horizon,
            {_select_expr(columns, ('latest_structure_age_trading_days',), 'latest_structure_age_trading_days')},
            {_select_expr(columns, ('latest_bos_age_trading_days',), 'latest_bos_age_trading_days')},
            {_select_expr(columns, ('latest_reset_age_trading_days',), 'latest_reset_age_trading_days')},
            {_select_expr(columns, ('latest_structure_freshness',), 'latest_structure_freshness')},
            {_select_expr(columns, ('latest_bos_freshness',), 'latest_bos_freshness')},
            {_select_expr(columns, ('latest_reset_freshness',), 'latest_reset_freshness')},
            {_select_expr(columns, ('freshness_status',), 'freshness_status')},
            {_select_expr(columns, ('run_id', 'calc_version'), 'source_run_id')}
        FROM {WINDOW_SOURCE_TABLE}
        WHERE signal_date = ?
          AND taxonomy_version = ?
          AND horizon IN ('rolling2', 'rolling5', 'rolling30')
        ORDER BY horizon, ticker
    """
    return conn.execute(query, (signal_date, taxonomy_version_code)).fetchall()


def _load_group_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> list[sqlite3.Row]:
    if not _table_exists(conn, GROUP_SOURCE_TABLE):
        return []
    columns = _column_names(conn, GROUP_SOURCE_TABLE)
    required = {"ohlc_date", "taxonomy_version", "group_type", "group_name"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(
            f"Source table '{GROUP_SOURCE_TABLE}' missing required columns: {', '.join(missing)}"
        )
    query = f"""
        SELECT
            group_type,
            group_name,
            {_select_expr(columns, ('latest_structure_age_trading_days',), 'latest_structure_age_trading_days')},
            {_select_expr(columns, ('latest_bos_age_trading_days',), 'latest_bos_age_trading_days')},
            {_select_expr(columns, ('latest_reset_age_trading_days',), 'latest_reset_age_trading_days')},
            {_select_expr(columns, ('latest_structure_freshness',), 'latest_structure_freshness')},
            {_select_expr(columns, ('latest_bos_freshness',), 'latest_bos_freshness')},
            {_select_expr(columns, ('latest_reset_freshness',), 'latest_reset_freshness')},
            {_select_expr(columns, ('run_id', 'calc_version'), 'source_run_id')}
        FROM {GROUP_SOURCE_TABLE}
        WHERE ohlc_date = ?
          AND taxonomy_version = ?
          AND group_type IN ('layer', 'subindustry')
        ORDER BY group_type, group_name
    """
    return conn.execute(query, (signal_date, taxonomy_version_code)).fetchall()


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    window_code: str,
    entity_id: int,
    metric_name: str,
    metric_kind: str,
    source_value: object,
    source_run_id: object,
) -> dict[str, object] | None:
    if metric_kind == "numeric":
        value_num = _normalize_float(source_value)
        if value_num is None:
            return None
        return {
            "run_id": str(run_row["run_id"]),
            "ecosystem_id": int(run_row["ecosystem_id"]),
            "signal_date": str(run_row["signal_date"]),
            "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
            "window_code": window_code,
            "entity_id": entity_id,
            "metric_name": metric_name,
            "metric_value_num": value_num,
            "metric_value_text": None,
            "metric_unit": "trading_days",
            "value_status": "OK",
            "source_run_id": _normalize_text(source_run_id),
        }
    value_text = _normalize_text(source_value)
    if value_text is None:
        return None
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": window_code,
        "entity_id": entity_id,
        "metric_name": metric_name,
        "metric_value_num": None,
        "metric_value_text": value_text,
        "metric_unit": None,
        "value_status": "OK",
        "source_run_id": _normalize_text(source_run_id),
    }


def _build_signal_row(
    *,
    run_row: sqlite3.Row,
    window_code: str,
    entity_id: int,
    signal_name: str,
    signal_value: object,
    source_table: str,
    source_run_id: object,
) -> dict[str, object] | None:
    value_text = _normalize_text(signal_value)
    if value_text is None:
        return None
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": window_code,
        "entity_id": entity_id,
        "signal_name": signal_name,
        "signal_family": FRESHNESS_SIGNAL_FAMILY,
        "signal_direction": "UNKNOWN",
        "signal_value": value_text,
        "observed_date": str(run_row["signal_date"]),
        "source_table": source_table,
        "source_run_id": _normalize_text(source_run_id),
        "source_event_id": f"{entity_id}|{window_code}|{signal_name}|{run_row['signal_date']}",
        "signal_status": "ACTIVE",
    }


def _build_rows_for_source(
    *,
    run_row: sqlite3.Row,
    source_rows: list[sqlite3.Row],
    source_table: str,
    coverage_map: dict[tuple[str, str, str], sqlite3.Row],
    source_kind: str,
    warnings: list[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], int, int]:
    metric_rows: list[dict[str, object]] = []
    signal_rows: list[dict[str, object]] = []
    mapped_count = 0
    skipped_count = 0

    for source_row in source_rows:
        if source_kind == "ticker_daily":
            ticker = str(source_row["ticker"])
            targets = [coverage_map.get(("daily", "TICKER", ticker))]
        elif source_kind == "ticker_window":
            ticker = str(source_row["ticker"])
            window_code = str(source_row["horizon"])
            targets = [coverage_map.get((window_code, "TICKER", ticker))]
        else:
            group_type = _normalize_text(source_row["group_type"])
            group_name = _normalize_text(source_row["group_name"])
            entity_type = GROUP_ENTITY_TYPE_MAP.get(group_type.lower() if group_type else "")
            if entity_type is None or group_name is None:
                warnings.append(
                    f"Skipped {source_table} row with unsupported group_type/group_name: {group_type}/{group_name}"
                )
                skipped_count += 1
                continue
            targets = [
                coverage_map.get((window_code, entity_type, group_name))
                for window_code in REQUIRED_WINDOWS
            ]

        matched_targets = [target for target in targets if target is not None]
        if not matched_targets:
            skipped_count += 1
            if source_kind == "ticker_daily":
                warnings.append(f"Skipped {source_table} ticker without eligible daily coverage: {source_row['ticker']}")
            elif source_kind == "ticker_window":
                warnings.append(
                    "Skipped "
                    f"{source_table} ticker/window without eligible coverage: {source_row['ticker']}/{source_row['horizon']}"
                )
            else:
                warnings.append(
                    "Skipped "
                    f"{source_table} group without eligible coverage: {source_row['group_type']}/{source_row['group_name']}"
                )
            continue

        mapped_count += 1
        for target in matched_targets:
            window_code = str(target["window_code"])
            entity_id = int(target["entity_id"])
            source_run_id = source_row["source_run_id"]

            for source_column, metric_name, metric_kind in METRIC_COLUMN_SPECS:
                if source_column == "freshness_status" and source_kind == "group":
                    continue
                metric_row = _build_metric_row(
                    run_row=run_row,
                    window_code=window_code,
                    entity_id=entity_id,
                    metric_name=metric_name,
                    metric_kind=metric_kind,
                    source_value=source_row[source_column],
                    source_run_id=source_run_id,
                )
                if metric_row is not None:
                    metric_rows.append(metric_row)

            for source_column, signal_name in SIGNAL_COLUMN_SPECS:
                if source_column == "freshness_status" and source_kind == "group":
                    continue
                signal_row = _build_signal_row(
                    run_row=run_row,
                    window_code=window_code,
                    entity_id=entity_id,
                    signal_name=signal_name,
                    signal_value=source_row[source_column],
                    source_table=source_table,
                    source_run_id=source_run_id,
                )
                if signal_row is not None:
                    signal_rows.append(signal_row)

    return metric_rows, signal_rows, mapped_count, skipped_count


def _ensure_replace_allowed(conn: sqlite3.Connection, *, run_id: str, replace_existing: bool) -> None:
    existing_metric_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_entity_metric_value
        WHERE run_id = ?
          AND metric_name LIKE 'freshness_%'
        """,
        (run_id,),
    ).fetchone()[0]
    existing_signal_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_signal_observation
        WHERE run_id = ?
          AND signal_family = ?
        """,
        (run_id, FRESHNESS_SIGNAL_FAMILY),
    ).fetchone()[0]
    if (existing_metric_count or existing_signal_count) and not replace_existing:
        raise ValueError(
            f"Freshness builder-owned rows already exist for run_id '{run_id}'"
        )
    if not replace_existing:
        return

    relevance_count = conn.execute(
        """
        SELECT COUNT(*)
        FROM eco_signal_relevance sr
        JOIN eco_signal_observation so
          ON so.signal_observation_id = sr.signal_observation_id
        WHERE so.run_id = ?
          AND so.signal_family = ?
        """,
        (run_id, FRESHNESS_SIGNAL_FAMILY),
    ).fetchone()[0]
    if relevance_count:
        raise ValueError(
            "Cannot replace freshness signal observations because eco_signal_relevance rows "
            f"exist for run_id '{run_id}' and signal_family '{FRESHNESS_SIGNAL_FAMILY}'"
        )

    conn.execute(
        """
        DELETE FROM eco_signal_observation
        WHERE run_id = ?
          AND signal_family = ?
        """,
        (run_id, FRESHNESS_SIGNAL_FAMILY),
    )
    conn.execute(
        """
        DELETE FROM eco_entity_metric_value
        WHERE run_id = ?
          AND metric_name LIKE 'freshness_%'
        """,
        (run_id,),
    )


def build_canonical_v3_freshness(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        coverage_map: dict[tuple[str, str, str], sqlite3.Row] = {}
        selected_entity_ids: set[int] = set()
        selected_windows: set[str] = set()
        ecosystem_present = False
        for row in coverage_rows:
            entity_type = str(row["entity_type"])
            window_code = str(row["window_code"])
            if entity_type in REQUIRED_ENTITY_TYPES:
                lookup_key = str(row["entity_code"]) if entity_type == "TICKER" else str(row["entity_name"])
                coverage_map[(window_code, entity_type, lookup_key)] = row
                selected_entity_ids.add(int(row["entity_id"]))
                selected_windows.add(window_code)
            elif entity_type == "ECOSYSTEM":
                ecosystem_present = True

        warnings: list[str] = []
        limitations = [
            "dc_report_context_daily_v2 and dc_report_context_window_v2 are TRANSITIONAL_V2_SOURCE",
            "no freshness events are created",
            "no signal relevance rows are created",
        ]
        if ecosystem_present:
            limitations.append("ecosystem freshness skipped if no direct source was used")
        else:
            limitations.append("ecosystem freshness skipped if no direct source was used")

        daily_rows = _load_daily_source_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
        )
        window_rows = _load_window_source_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
        )
        group_rows = _load_group_source_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
        )

        metric_rows: list[dict[str, object]] = []
        signal_rows: list[dict[str, object]] = []
        source_rows_mapped_by_table: dict[str, int] = {}
        source_rows_skipped = 0

        for source_table, source_kind, source_rows in (
            (DAILY_SOURCE_TABLE, "ticker_daily", daily_rows),
            (WINDOW_SOURCE_TABLE, "ticker_window", window_rows),
            (GROUP_SOURCE_TABLE, "group", group_rows),
        ):
            table_metric_rows, table_signal_rows, mapped_count, skipped_count = _build_rows_for_source(
                run_row=run_row,
                source_rows=source_rows,
                source_table=source_table,
                coverage_map=coverage_map,
                source_kind=source_kind,
                warnings=warnings,
            )
            metric_rows.extend(table_metric_rows)
            signal_rows.extend(table_signal_rows)
            source_rows_mapped_by_table[source_table] = mapped_count
            source_rows_skipped += skipped_count

        metric_name_counts = dict(sorted(Counter(row["metric_name"] for row in metric_rows).items()))
        signal_name_counts = dict(sorted(Counter(row["signal_name"] for row in signal_rows).items()))

        conn.execute("BEGIN")
        _ensure_replace_allowed(conn, run_id=str(run_row["run_id"]), replace_existing=replace_existing)
        conn.executemany(
            """
            INSERT INTO eco_entity_metric_value (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                metric_name, metric_value_num, metric_value_text, metric_unit, value_status, source_run_id
            ) VALUES (
                :run_id, :ecosystem_id, :signal_date, :taxonomy_version_id, :window_code, :entity_id,
                :metric_name, :metric_value_num, :metric_value_text, :metric_unit, :value_status, :source_run_id
            )
            """,
            metric_rows,
        )
        conn.executemany(
            """
            INSERT INTO eco_signal_observation (
                run_id, ecosystem_id, signal_date, taxonomy_version_id, window_code, entity_id,
                signal_name, signal_family, signal_direction, signal_value, observed_date,
                source_table, source_run_id, source_event_id, signal_status
            ) VALUES (
                :run_id, :ecosystem_id, :signal_date, :taxonomy_version_id, :window_code, :entity_id,
                :signal_name, :signal_family, :signal_direction, :signal_value, :observed_date,
                :source_table, :source_run_id, :source_event_id, :signal_status
            )
            """,
            signal_rows,
        )
        conn.commit()

        return {
            "run_id": str(run_row["run_id"]),
            "ecosystem_code": str(run_row["ecosystem_code"]),
            "taxonomy_version_code": str(run_row["version_code"]),
            "signal_date": str(run_row["signal_date"]),
            "source_classifications": dict(SOURCE_CLASSIFICATIONS),
            "selected_entity_count": len(selected_entity_ids),
            "window_count": len(selected_windows),
            "metric_rows_inserted": len(metric_rows),
            "signal_observations_inserted": len(signal_rows),
            "metric_name_counts": metric_name_counts,
            "signal_name_counts": signal_name_counts,
            "source_rows_read_by_table": {
                DAILY_SOURCE_TABLE: len(daily_rows),
                WINDOW_SOURCE_TABLE: len(window_rows),
                GROUP_SOURCE_TABLE: len(group_rows),
            },
            "source_rows_mapped_by_table": source_rows_mapped_by_table,
            "source_rows_skipped": source_rows_skipped,
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": limitations,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
