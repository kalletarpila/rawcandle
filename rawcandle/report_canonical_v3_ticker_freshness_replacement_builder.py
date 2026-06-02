from __future__ import annotations

import sqlite3
from collections import Counter


SOURCE_TABLE = "dc_ticker_swing_signal_daily"
SOURCE_CLASSIFICATIONS = {
    SOURCE_TABLE: "DERIVED_FROM_RAW_SOURCE",
}
TARGET_ENTITY_TYPE = "TICKER"
TARGET_WINDOWS = ("daily", "rolling2", "rolling5", "rolling30")
SIGNAL_FAMILY = "FRESHNESS"
DAILY_AGE_METRICS = (
    ("latest_structure_age_trading_days", "freshness_latest_structure_age_trading_days"),
    ("latest_bos_age_trading_days", "freshness_latest_bos_age_trading_days"),
    ("latest_reset_age_trading_days", "freshness_latest_reset_age_trading_days"),
)
CLASS_METRICS = (
    ("latest_structure_freshness", "freshness_latest_structure_class"),
    ("latest_bos_freshness", "freshness_latest_bos_class"),
    ("latest_reset_freshness", "freshness_latest_reset_class"),
)
SIGNAL_SPECS = (
    ("latest_structure_freshness", "STRUCTURE_FRESHNESS"),
    ("latest_bos_freshness", "BOS_FRESHNESS"),
    ("latest_reset_freshness", "RESET_FRESHNESS"),
)
REPLACEMENT_METRIC_NAMES = tuple(metric_name for _, metric_name in DAILY_AGE_METRICS + CLASS_METRICS)
REPLACEMENT_SIGNAL_NAMES = tuple(signal_name for _, signal_name in SIGNAL_SPECS)


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


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


def _normalize_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


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
            e.entity_code,
            e.entity_name
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND c.signal_date = ?
          AND c.taxonomy_version_id = ?
          AND c.ecosystem_id = ?
          AND c.window_code IN ('daily', 'rolling2', 'rolling5', 'rolling30')
          AND e.entity_type = ?
        ORDER BY e.entity_code, c.window_code
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
            TARGET_ENTITY_TYPE,
        ),
    ).fetchall()
    if not rows:
        raise ValueError(
            f"Missing eligible {TARGET_ENTITY_TYPE} coverage rows for run_id '{run_row['run_id']}'"
        )
    return rows


def _load_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    eligible_tickers: set[str],
) -> list[sqlite3.Row]:
    if not _table_exists(conn, SOURCE_TABLE):
        raise ValueError(f"Missing source table '{SOURCE_TABLE}'")
    columns = _column_names(conn, SOURCE_TABLE)
    required = {
        "ticker",
        "signal_date",
        "latest_structure_age_trading_days",
        "latest_structure_freshness",
        "latest_bos_age_trading_days",
        "latest_bos_freshness",
        "latest_reset_age_trading_days",
        "latest_reset_freshness",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE}' missing required columns: {', '.join(missing)}")
    taxonomy_filter = "AND taxonomy_version = ?" if "taxonomy_version" in columns else ""
    ticker_clause = ", ".join("?" for _ in sorted(eligible_tickers))
    query = f"""
        SELECT
            ticker,
            signal_date,
            latest_structure_age_trading_days,
            latest_structure_freshness,
            latest_bos_age_trading_days,
            latest_bos_freshness,
            latest_reset_age_trading_days,
            latest_reset_freshness,
            {_select_expr(columns, ('run_id', 'signal_version'), 'source_run_id')},
            {_select_expr(columns, ('latest_structure_label',), 'latest_structure_label')},
            {_select_expr(columns, ('latest_bos_event_type',), 'latest_bos_event_type')},
            {_select_expr(columns, ('latest_reset_reason',), 'latest_reset_reason')},
            {_select_expr(columns, ('price_data_status',), 'price_data_status')}
        FROM {SOURCE_TABLE}
        WHERE signal_date = ?
          {taxonomy_filter}
          AND ticker IN ({ticker_clause})
        ORDER BY ticker
    """
    params: list[object] = [signal_date]
    if "taxonomy_version" in columns:
        params.append(taxonomy_version_code)
    params.extend(sorted(eligible_tickers))
    return conn.execute(query, tuple(params)).fetchall()


def _build_metric_row(
    *,
    run_row: sqlite3.Row,
    window_code: str,
    entity_id: int,
    metric_name: str,
    metric_value_num: float | None,
    metric_value_text: str | None,
    metric_unit: str | None,
    source_run_id: str | None,
) -> dict[str, object]:
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": window_code,
        "entity_id": entity_id,
        "metric_name": metric_name,
        "metric_value_num": metric_value_num,
        "metric_value_text": metric_value_text,
        "metric_unit": metric_unit,
        "value_status": "OK",
        "source_run_id": source_run_id,
    }


def _build_signal_row(
    *,
    run_row: sqlite3.Row,
    ticker: str,
    window_code: str,
    entity_id: int,
    signal_name: str,
    signal_value: str,
    source_run_id: str | None,
) -> dict[str, object]:
    observed_date = str(run_row["signal_date"])
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": window_code,
        "entity_id": entity_id,
        "signal_name": signal_name,
        "signal_family": SIGNAL_FAMILY,
        "signal_direction": "UNKNOWN",
        "signal_value": signal_value,
        "observed_date": observed_date,
        "source_table": SOURCE_TABLE,
        "source_run_id": source_run_id,
        "source_event_id": f"ticker_freshness:{ticker}:{observed_date}:{window_code}:{signal_name}",
        "signal_status": "ACTIVE",
    }


def _build_rows(
    *,
    run_row: sqlite3.Row,
    coverage_by_ticker: dict[str, list[sqlite3.Row]],
    source_rows: list[sqlite3.Row],
    warnings: list[str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], int, int, list[str]]:
    metric_rows: list[dict[str, object]] = []
    signal_rows: list[dict[str, object]] = []
    mapped_count = 0
    skipped_count = 0
    missing_source_tickers = sorted(set(coverage_by_ticker) - {str(row["ticker"]) for row in source_rows})

    for source_row in source_rows:
        ticker = str(source_row["ticker"])
        coverage_rows = coverage_by_ticker.get(ticker)
        if not coverage_rows:
            warnings.append(f"Skipped source ticker without eligible ticker freshness coverage: {ticker}")
            skipped_count += 1
            continue

        mapped_count += 1
        source_run_id = _normalize_text(source_row["source_run_id"])

        for coverage_row in coverage_rows:
            window_code = str(coverage_row["window_code"])
            entity_id = int(coverage_row["entity_id"])

            if window_code == "daily":
                for source_column, metric_name in DAILY_AGE_METRICS:
                    value_num = _normalize_float(source_row[source_column])
                    if value_num is None:
                        continue
                    metric_rows.append(
                        _build_metric_row(
                            run_row=run_row,
                            window_code=window_code,
                            entity_id=entity_id,
                            metric_name=metric_name,
                            metric_value_num=value_num,
                            metric_value_text=None,
                            metric_unit="trading_days",
                            source_run_id=source_run_id,
                        )
                    )

            for source_column, metric_name in CLASS_METRICS:
                value_text = _normalize_text(source_row[source_column])
                if value_text is None:
                    continue
                metric_rows.append(
                    _build_metric_row(
                        run_row=run_row,
                        window_code=window_code,
                        entity_id=entity_id,
                        metric_name=metric_name,
                        metric_value_num=None,
                        metric_value_text=value_text,
                        metric_unit=None,
                        source_run_id=source_run_id,
                    )
                )

            for source_column, signal_name in SIGNAL_SPECS:
                value_text = _normalize_text(source_row[source_column])
                if value_text is None:
                    continue
                signal_rows.append(
                    _build_signal_row(
                        run_row=run_row,
                        ticker=ticker,
                        window_code=window_code,
                        entity_id=entity_id,
                        signal_name=signal_name,
                        signal_value=value_text,
                        source_run_id=source_run_id,
                    )
                )

    return metric_rows, signal_rows, mapped_count, skipped_count, missing_source_tickers


def _existing_replacement_counts(conn: sqlite3.Connection, *, run_id: str) -> tuple[int, int]:
    metric_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM eco_entity_metric_value m
        JOIN eco_entity e ON e.entity_id = m.entity_id
        WHERE m.run_id = ?
          AND e.entity_type = ?
          AND m.metric_name IN ({", ".join("?" for _ in REPLACEMENT_METRIC_NAMES)})
        """,
        (run_id, TARGET_ENTITY_TYPE, *REPLACEMENT_METRIC_NAMES),
    ).fetchone()[0]
    signal_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM eco_signal_observation o
        JOIN eco_entity e ON e.entity_id = o.entity_id
        WHERE o.run_id = ?
          AND e.entity_type = ?
          AND o.signal_family = ?
          AND o.signal_name IN ({", ".join("?" for _ in REPLACEMENT_SIGNAL_NAMES)})
        """,
        (run_id, TARGET_ENTITY_TYPE, SIGNAL_FAMILY, *REPLACEMENT_SIGNAL_NAMES),
    ).fetchone()[0]
    return int(metric_count), int(signal_count)


def _ensure_replace_allowed(conn: sqlite3.Connection, *, run_id: str, replace_existing: bool) -> int:
    existing_metric_count, existing_signal_count = _existing_replacement_counts(conn, run_id=run_id)
    if (existing_metric_count or existing_signal_count) and not replace_existing:
        raise ValueError(f"Ticker freshness replacement rows already exist for run_id '{run_id}'")
    if not replace_existing or not (existing_metric_count or existing_signal_count):
        return 0

    relevance_count = conn.execute(
        f"""
        SELECT COUNT(*)
        FROM eco_signal_relevance r
        JOIN eco_signal_observation o ON o.signal_observation_id = r.signal_observation_id
        JOIN eco_entity e ON e.entity_id = o.entity_id
        WHERE o.run_id = ?
          AND e.entity_type = ?
          AND o.signal_family = ?
          AND o.signal_name IN ({", ".join("?" for _ in REPLACEMENT_SIGNAL_NAMES)})
        """,
        (run_id, TARGET_ENTITY_TYPE, SIGNAL_FAMILY, *REPLACEMENT_SIGNAL_NAMES),
    ).fetchone()[0]
    if relevance_count:
        raise ValueError(
            "Cannot replace ticker freshness observations because relevance rows point to replacement-scope "
            "TICKER FRESHNESS observations"
        )

    conn.execute(
        f"""
        DELETE FROM eco_entity_metric_value
        WHERE rowid IN (
            SELECT m.rowid
            FROM eco_entity_metric_value m
            JOIN eco_entity e ON e.entity_id = m.entity_id
            WHERE m.run_id = ?
              AND e.entity_type = ?
              AND m.metric_name IN ({", ".join("?" for _ in REPLACEMENT_METRIC_NAMES)})
        )
        """,
        (run_id, TARGET_ENTITY_TYPE, *REPLACEMENT_METRIC_NAMES),
    )
    conn.execute(
        f"""
        DELETE FROM eco_signal_observation
        WHERE signal_observation_id IN (
            SELECT o.signal_observation_id
            FROM eco_signal_observation o
            JOIN eco_entity e ON e.entity_id = o.entity_id
            WHERE o.run_id = ?
              AND e.entity_type = ?
              AND o.signal_family = ?
              AND o.signal_name IN ({", ".join("?" for _ in REPLACEMENT_SIGNAL_NAMES)})
        )
        """,
        (run_id, TARGET_ENTITY_TYPE, SIGNAL_FAMILY, *REPLACEMENT_SIGNAL_NAMES),
    )
    return existing_metric_count + existing_signal_count


def build_canonical_v3_ticker_freshness_from_signal_daily(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        selected_ticker_entity_count = len({int(row["entity_id"]) for row in coverage_rows})
        selected_windows = sorted({str(row["window_code"]) for row in coverage_rows})
        coverage_by_ticker: dict[str, list[sqlite3.Row]] = {}
        for row in coverage_rows:
            coverage_by_ticker.setdefault(str(row["entity_code"]), []).append(row)

        source_rows = _load_source_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
            eligible_tickers=set(coverage_by_ticker),
        )
        warnings: list[str] = []
        limitations = [
            "replaces ticker freshness only",
            "group freshness rows are preserved",
            "source is dc_ticker_swing_signal_daily, not dc_report_context_*_v2",
            "metric source_table lineage is unavailable because eco_entity_metric_value has no source_table column",
            "no relevance rows are created",
            "no event rows are created",
            "no OVERALL_FRESHNESS rows are created",
        ]

        metric_rows, signal_rows, mapped_count, skipped_count, missing_source_tickers = _build_rows(
            run_row=run_row,
            coverage_by_ticker=coverage_by_ticker,
            source_rows=source_rows,
            warnings=warnings,
        )
        metric_name_counts = dict(sorted(Counter(row["metric_name"] for row in metric_rows).items()))
        signal_name_counts = dict(sorted(Counter(row["signal_name"] for row in signal_rows).items()))
        freshness_class_counts = dict(sorted(Counter(row["signal_value"] for row in signal_rows).items()))

        conn.execute("BEGIN")
        rows_deleted_on_replace = _ensure_replace_allowed(
            conn,
            run_id=str(run_row["run_id"]),
            replace_existing=replace_existing,
        )
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
            "selected_ticker_entity_count": selected_ticker_entity_count,
            "window_count": len(selected_windows),
            "source_rows_read": len(source_rows),
            "source_rows_mapped": mapped_count,
            "source_rows_skipped": skipped_count,
            "missing_source_tickers": missing_source_tickers,
            "metric_rows_inserted": len(metric_rows),
            "signal_observations_inserted": len(signal_rows),
            "metric_name_counts": metric_name_counts,
            "signal_name_counts": signal_name_counts,
            "freshness_class_counts": freshness_class_counts,
            "rows_deleted_on_replace": rows_deleted_on_replace,
            "warning_count": len(warnings),
            "warnings": warnings,
            "limitations": limitations,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
