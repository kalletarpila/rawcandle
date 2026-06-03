from __future__ import annotations

import sqlite3
from collections import Counter

from analysis.datacenter_indices.rolling2_sell_pressure_classifier import (
    classify_rolling_2_sell_pressure_row,
)


SOURCE_TABLE_TICKER = "dc_ticker_swing_signal_daily"
SOURCE_TABLE_GROUP = "dc_group_swing_signal_daily"
CLASSIFICATION_TYPE = "rolling2_sell_pressure"
WINDOW_CODE = "rolling2"
TARGET_ENTITY_TYPE = "TICKER"
DEFAULT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
WATCHLIST_MISSING_PRICE_STATUSES = {"MISSING_AS_OF_DATE", "MISSING_CLOSE_AS_OF_DATE"}
GROUP_RISK_TIMING_STATES = {"EXIT_ZONE", "TRIM_WATCH"}
GROUP_RISK_OVERHEAT_LEVELS = {"HIGH", "EXTREME"}
CLASSIFICATION_VERSION = "V3_ROLLING2_SELL_PRESSURE_CLASSIFIER_V1"


def _connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _fetch_one(conn: sqlite3.Connection, query: str, params: tuple[object, ...]) -> sqlite3.Row | None:
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


def _normalize_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None


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
            e.entity_code
        FROM eco_entity_coverage c
        JOIN eco_entity e ON e.entity_id = c.entity_id
        WHERE c.run_id = ?
          AND c.signal_date = ?
          AND c.taxonomy_version_id = ?
          AND c.ecosystem_id = ?
          AND c.window_code = 'rolling2'
          AND e.entity_type = 'TICKER'
        ORDER BY e.entity_code
        """,
        (
            str(run_row["run_id"]),
            str(run_row["signal_date"]),
            int(run_row["taxonomy_version_id"]),
            int(run_row["ecosystem_id"]),
        ),
    ).fetchall()
    if not rows:
        raise ValueError(f"Missing eligible TICKER rolling2 coverage rows for run_id '{run_row['run_id']}'")
    return rows


def _load_valid_signal_dates(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
) -> list[str]:
    if not _table_exists(conn, SOURCE_TABLE_GROUP):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_GROUP}'")
    columns = _column_names(conn, SOURCE_TABLE_GROUP)
    if "signal_date" not in columns or "taxonomy_version" not in columns:
        raise ValueError(f"Source table '{SOURCE_TABLE_GROUP}' missing required date columns")
    where_clauses = ["signal_date <= ?", "taxonomy_version = ?"]
    params: list[object] = [signal_date, taxonomy_version_code]
    if "signal_version" in columns:
        where_clauses.append("signal_version = ?")
        params.append(DEFAULT_SIGNAL_VERSION)
    rows = conn.execute(
        f"""
        SELECT DISTINCT signal_date
        FROM {SOURCE_TABLE_GROUP}
        WHERE {' AND '.join(where_clauses)}
        ORDER BY signal_date DESC
        LIMIT 2
        """,
        tuple(params),
    ).fetchall()
    return sorted(str(row[0]) for row in rows)


def _build_pair_clause(pairs: list[tuple[str, str]]) -> tuple[str, list[object]]:
    clause = " OR ".join("(group_type = ? AND group_name = ?)" for _ in pairs)
    params: list[object] = []
    for group_type, group_name in pairs:
        params.extend((group_type, group_name))
    return clause, params


def _load_ticker_history_rows(
    conn: sqlite3.Connection,
    *,
    selected_dates: list[str],
    taxonomy_version_code: str,
    eligible_tickers: list[str],
) -> tuple[list[sqlite3.Row], set[str]]:
    if not _table_exists(conn, SOURCE_TABLE_TICKER):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_TICKER}'")
    columns = _column_names(conn, SOURCE_TABLE_TICKER)
    required = {
        "signal_date",
        "taxonomy_version",
        "ticker",
        "primary_layer",
        "primary_subindustry",
        "breakout_signal",
        "pullback_signal",
        "fast_ema10_pullback_signal",
        "conservative_ema20_pullback_signal",
        "exit_risk_signal",
        "exit_risk_severity",
        "exit_reason",
        "latest_bos_event_type",
        "latest_bos_freshness",
        "latest_reset_reason",
        "latest_reset_freshness",
        "latest_structure_label",
        "distance_to_ema20_pct",
        "price_data_status",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_TICKER}' missing required columns: {', '.join(missing)}")
    if "trend_state" not in columns and "ticker_trend_state" not in columns:
        raise ValueError(f"Source table '{SOURCE_TABLE_TICKER}' missing both trend_state and ticker_trend_state")

    if not selected_dates or not eligible_tickers:
        return [], columns
    date_placeholders = ", ".join("?" for _ in selected_dates)
    ticker_placeholders = ", ".join("?" for _ in eligible_tickers)
    where_clauses = [
        f"signal_date IN ({date_placeholders})",
        "taxonomy_version = ?",
        f"ticker IN ({ticker_placeholders})",
    ]
    params: list[object] = [*selected_dates, taxonomy_version_code, *eligible_tickers]
    if "signal_version" in columns:
        where_clauses.append("signal_version = ?")
        params.append(DEFAULT_SIGNAL_VERSION)
    rows = conn.execute(
        f"""
        SELECT *
        FROM {SOURCE_TABLE_TICKER}
        WHERE {' AND '.join(where_clauses)}
        ORDER BY ticker ASC, signal_date ASC
        """,
        tuple(params),
    ).fetchall()
    return rows, columns


def _load_group_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    needed_groups: set[tuple[str, str]],
) -> tuple[dict[tuple[str, str], sqlite3.Row], int]:
    if not needed_groups:
        return {}, 0
    columns = _column_names(conn, SOURCE_TABLE_GROUP)
    required = {"signal_date", "taxonomy_version", "group_type", "group_name", "timing_state", "overheat_risk_level"}
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_GROUP}' missing required columns: {', '.join(missing)}")
    pairs = sorted(needed_groups)
    pair_clause, pair_params = _build_pair_clause(pairs)
    where_clauses = [
        "signal_date = ?",
        "taxonomy_version = ?",
        f"({pair_clause})",
    ]
    params: list[object] = [signal_date, taxonomy_version_code, *pair_params]
    if "signal_version" in columns:
        where_clauses.append("signal_version = ?")
        params.append(DEFAULT_SIGNAL_VERSION)
    rows = conn.execute(
        f"""
        SELECT group_type, group_name, timing_state, overheat_risk_level
        FROM {SOURCE_TABLE_GROUP}
        WHERE {' AND '.join(where_clauses)}
        ORDER BY group_type, group_name
        """,
        tuple(params),
    ).fetchall()
    row_map = {
        (str(row["group_type"]).lower(), str(row["group_name"])): row
        for row in rows
    }
    return row_map, len(rows)


def _group_risk_state(
    *,
    subindustry_timing_state: object | None,
    subindustry_overheat_risk_level: object | None,
    layer_timing_state: object | None,
    layer_overheat_risk_level: object | None,
) -> bool:
    return (
        subindustry_timing_state in GROUP_RISK_TIMING_STATES
        or layer_timing_state in GROUP_RISK_TIMING_STATES
        or subindustry_overheat_risk_level in GROUP_RISK_OVERHEAT_LEVELS
        or layer_overheat_risk_level in GROUP_RISK_OVERHEAT_LEVELS
    )


def _classify_rolling_current_watchlist_status(row: dict[str, object]) -> str:
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES:
        return "MISSING_PRICE"
    if row.get("last_exit_risk_severity") == "HIGH":
        return "HIGH_EXIT_RISK"
    if row.get("last_exit_risk_severity") == "MEDIUM":
        return "MEDIUM_EXIT_RISK"
    if row.get("last_breakout_signal") == 1:
        return "BREAKOUT_CANDIDATE"
    if row.get("last_pullback_signal") == 1:
        return "PULLBACK_CANDIDATE"
    if _group_risk_state(
        subindustry_timing_state=row.get("last_subindustry_timing_state"),
        subindustry_overheat_risk_level=row.get("last_subindustry_overheat_risk_level"),
        layer_timing_state=row.get("last_layer_timing_state"),
        layer_overheat_risk_level=row.get("last_layer_overheat_risk_level"),
    ):
        return "GROUP_RISK"
    return "NEUTRAL_MONITOR"


def _classify_rolling_window_watchlist_status(row: dict[str, object]) -> str:
    if row.get("last_price_data_status") in WATCHLIST_MISSING_PRICE_STATUSES or bool(row.get("all_price_rows_missing")):
        return "MISSING_PRICE"
    if int(row.get("high_exit_risk_days") or 0) > 0:
        return "HIGH_EXIT_RISK"
    if int(row.get("medium_exit_risk_days") or 0) > 0:
        return "MEDIUM_EXIT_RISK"
    if int(row.get("breakout_days") or 0) > 0:
        return "BREAKOUT_CANDIDATE"
    if int(row.get("pullback_days") or 0) > 0:
        return "PULLBACK_CANDIDATE"
    if _group_risk_state(
        subindustry_timing_state=row.get("last_subindustry_timing_state"),
        subindustry_overheat_risk_level=row.get("last_subindustry_overheat_risk_level"),
        layer_timing_state=row.get("last_layer_timing_state"),
        layer_overheat_risk_level=row.get("last_layer_overheat_risk_level"),
    ):
        return "GROUP_RISK"
    return "NEUTRAL_MONITOR"


def _context_row_for_classifier(
    *,
    ticker: str,
    current_rows: list[sqlite3.Row],
    ticker_columns: set[str],
    layer_row: sqlite3.Row | None,
    subindustry_row: sqlite3.Row | None,
) -> dict[str, object]:
    last_row = current_rows[-1]
    output_row = {
        "ticker": ticker,
        "breakout_days": sum(1 for row in current_rows if int(row["breakout_signal"] or 0) == 1),
        "pullback_days": sum(1 for row in current_rows if int(row["pullback_signal"] or 0) == 1),
        "exit_risk_days": sum(1 for row in current_rows if int(row["exit_risk_signal"] or 0) == 1),
        "high_exit_risk_days": sum(1 for row in current_rows if row["exit_risk_severity"] == "HIGH"),
        "medium_exit_risk_days": sum(1 for row in current_rows if row["exit_risk_severity"] == "MEDIUM"),
        "last_exit_reason": last_row["exit_reason"],
        "last_latest_bos_event_type": last_row["latest_bos_event_type"],
        "last_latest_bos_freshness": last_row["latest_bos_freshness"],
        "last_latest_reset_reason": last_row["latest_reset_reason"],
        "last_latest_reset_freshness": last_row["latest_reset_freshness"],
        "last_latest_structure_label": last_row["latest_structure_label"],
        "last_distance_to_ema20_pct": last_row["distance_to_ema20_pct"],
        "last_price_data_status": last_row["price_data_status"],
        "last_exit_risk_severity": last_row["exit_risk_severity"],
        "last_breakout_signal": int(last_row["breakout_signal"] or 0),
        "last_pullback_signal": int(last_row["pullback_signal"] or 0),
        "last_ticker_trend_state": last_row["trend_state"] if "trend_state" in ticker_columns else last_row["ticker_trend_state"],
        "latest_bearish_relevance_class": last_row["latest_bearish_relevance_class"] if "latest_bearish_relevance_class" in ticker_columns else None,
        "last_subindustry_timing_state": None if subindustry_row is None else subindustry_row["timing_state"],
        "last_subindustry_overheat_risk_level": None if subindustry_row is None else subindustry_row["overheat_risk_level"],
        "last_layer_timing_state": None if layer_row is None else layer_row["timing_state"],
        "last_layer_overheat_risk_level": None if layer_row is None else layer_row["overheat_risk_level"],
        "all_price_rows_missing": all(row["price_data_status"] in WATCHLIST_MISSING_PRICE_STATUSES for row in current_rows),
    }
    output_row["current_watchlist_status"] = _classify_rolling_current_watchlist_status(output_row)
    output_row["window_watchlist_status"] = _classify_rolling_window_watchlist_status(output_row)
    return output_row


def _classification_row(
    *,
    run_row: sqlite3.Row,
    coverage_row: sqlite3.Row,
    classifier_row: dict[str, object],
    source_run_id: str,
) -> dict[str, object]:
    result = classify_rolling_2_sell_pressure_row(classifier_row)
    blocking_reason = None
    risk_reason = _normalize_text(result.risk_reason)
    next_action = _normalize_text(result.next_action)
    classification_state = _normalize_text(result.rolling_2_sell_pressure_state)
    decision_status = "OK" if classification_state else "MISSING"
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": WINDOW_CODE,
        "entity_id": int(coverage_row["entity_id"]),
        "classification_type": CLASSIFICATION_TYPE,
        "classification_state": classification_state,
        "primary_reason": _normalize_text(result.primary_reason),
        "blocking_reason": blocking_reason,
        "risk_reason": risk_reason,
        "next_action": next_action,
        "priority_score": None,
        "priority_label": None,
        "sort_rank": None,
        "source_classifier": "rolling2_sell_pressure_classifier",
        "classification_version": CLASSIFICATION_VERSION,
        "source_run_id": source_run_id,
        "decision_status": decision_status,
    }


def _existing_count(conn: sqlite3.Connection, *, run_id: str) -> int:
    return int(
        conn.execute(
            """
            SELECT COUNT(*)
            FROM eco_classification_decision
            WHERE run_id = ?
              AND classification_type = ?
            """,
            (run_id, CLASSIFICATION_TYPE),
        ).fetchone()[0]
    )


def _delete_existing(conn: sqlite3.Connection, *, run_id: str) -> int:
    count = _existing_count(conn, run_id=run_id)
    if count:
        conn.execute(
            """
            DELETE FROM eco_classification_decision
            WHERE run_id = ?
              AND classification_type = ?
            """,
            (run_id, CLASSIFICATION_TYPE),
        )
    return count


def build_canonical_v3_rolling2_sell_pressure_classifications(
    db_path: str,
    run_id: str,
    replace_existing: bool = False,
) -> dict[str, object]:
    conn = _connect(db_path)
    try:
        run_row = _resolve_run(conn, run_id)
        coverage_rows = _load_target_coverage(conn, run_row)
        existing_count = _existing_count(conn, run_id=str(run_row["run_id"]))
        if existing_count and not replace_existing:
            raise ValueError(
                "eco_classification_decision rows already exist for "
                f"run_id '{run_row['run_id']}' and classification_type '{CLASSIFICATION_TYPE}'"
            )

        selected_dates = _load_valid_signal_dates(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
        )
        eligible_tickers = [str(row["entity_code"]) for row in coverage_rows]
        ticker_history_rows, ticker_columns = _load_ticker_history_rows(
            conn,
            selected_dates=selected_dates,
            taxonomy_version_code=str(run_row["version_code"]),
            eligible_tickers=eligible_tickers,
        )

        ticker_rows_by_ticker: dict[str, list[sqlite3.Row]] = {}
        for row in ticker_history_rows:
            ticker_rows_by_ticker.setdefault(str(row["ticker"]), []).append(row)

        needed_groups: set[tuple[str, str]] = set()
        for current_rows in ticker_rows_by_ticker.values():
            current_rows.sort(key=lambda row: str(row["signal_date"]))
            last_row = current_rows[-1]
            layer_name = _normalize_text(last_row["primary_layer"])
            subindustry_name = _normalize_text(last_row["primary_subindustry"])
            if layer_name is not None:
                needed_groups.add(("layer", layer_name))
            if subindustry_name is not None:
                needed_groups.add(("subindustry", subindustry_name))

        group_rows_by_key, group_rows_read = _load_group_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
            needed_groups=needed_groups,
        )

        warnings: list[str] = []
        decision_rows: list[dict[str, object]] = []
        state_counts: Counter[str] = Counter()
        decision_status_counts: Counter[str] = Counter()
        field_coverage_counts = Counter(
            {
                "primary_reason": 0,
                "blocking_reason": 0,
                "risk_reason": 0,
                "next_action": 0,
                "priority_score": 0,
                "priority_label": 0,
                "sort_rank": 0,
            }
        )
        context_rows_built = 0

        explicit_source_run_id = f"V3_ROLLING2_CLASSIFICATION_FROM_LOWER_LEVEL_{str(run_row['signal_date']).replace('-', '_')}"

        for coverage_row in coverage_rows:
            ticker = str(coverage_row["entity_code"])
            current_rows = ticker_rows_by_ticker.get(ticker)
            if not current_rows:
                warnings.append(f"Missing lower-level ticker history for rolling2 ticker '{ticker}'")
                continue

            last_row = current_rows[-1]
            layer_name = _normalize_text(last_row["primary_layer"])
            subindustry_name = _normalize_text(last_row["primary_subindustry"])
            layer_row = None if layer_name is None else group_rows_by_key.get(("layer", layer_name))
            subindustry_row = (
                None if subindustry_name is None else group_rows_by_key.get(("subindustry", subindustry_name))
            )
            if layer_name is not None and layer_row is None:
                warnings.append(f"Missing layer context for ticker '{ticker}' layer '{layer_name}'")
            if subindustry_name is not None and subindustry_row is None:
                warnings.append(f"Missing subindustry context for ticker '{ticker}' subindustry '{subindustry_name}'")

            classifier_row = _context_row_for_classifier(
                ticker=ticker,
                current_rows=current_rows,
                ticker_columns=ticker_columns,
                layer_row=layer_row,
                subindustry_row=subindustry_row,
            )
            context_rows_built += 1
            decision_row = _classification_row(
                run_row=run_row,
                coverage_row=coverage_row,
                classifier_row=classifier_row,
                source_run_id=explicit_source_run_id,
            )
            decision_rows.append(decision_row)
            state_counts[str(decision_row["classification_state"])] += 1
            decision_status_counts[str(decision_row["decision_status"])] += 1
            for field_name in field_coverage_counts:
                if decision_row[field_name] is not None:
                    field_coverage_counts[field_name] += 1

        source_rows_read_by_table = {
            SOURCE_TABLE_TICKER: len(ticker_history_rows),
            SOURCE_TABLE_GROUP: group_rows_read,
            "eco_entity_coverage": len(coverage_rows),
        }
        source_dependency_summary = {
            SOURCE_TABLE_TICKER: "DERIVED_FROM_RAW_SOURCE",
            SOURCE_TABLE_GROUP: "DERIVED_FROM_RAW_SOURCE",
            "eco_entity_coverage": "V3_TARGET_UNIVERSE",
            "runtime_excludes": ["dc_report_classification_v2", "dc_report_context_window_v2"],
            "selected_window_dates": selected_dates,
        }
        limitations = [
            "replaces only rolling2_sell_pressure",
            "does not use dc_report_classification_v2 as runtime source",
            "priority/rank fields remain NULL",
            "other classification types remain transitional",
            "no metrics/signals/events are created",
        ]

        conn.execute("BEGIN")
        rows_deleted_on_replace = 0
        if replace_existing:
            rows_deleted_on_replace = _delete_existing(conn, run_id=str(run_row["run_id"]))
        conn.executemany(
            """
            INSERT INTO eco_classification_decision (
                run_id,
                ecosystem_id,
                signal_date,
                taxonomy_version_id,
                window_code,
                entity_id,
                classification_type,
                classification_state,
                primary_reason,
                blocking_reason,
                risk_reason,
                next_action,
                priority_score,
                priority_label,
                sort_rank,
                source_classifier,
                classification_version,
                source_run_id,
                decision_status
            ) VALUES (
                :run_id,
                :ecosystem_id,
                :signal_date,
                :taxonomy_version_id,
                :window_code,
                :entity_id,
                :classification_type,
                :classification_state,
                :primary_reason,
                :blocking_reason,
                :risk_reason,
                :next_action,
                :priority_score,
                :priority_label,
                :sort_rank,
                :source_classifier,
                :classification_version,
                :source_run_id,
                :decision_status
            )
            """,
            decision_rows,
        )
        conn.commit()

        return {
            "run_id": str(run_row["run_id"]),
            "ecosystem_code": str(run_row["ecosystem_code"]),
            "taxonomy_version_code": str(run_row["version_code"]),
            "signal_date": str(run_row["signal_date"]),
            "classification_type": CLASSIFICATION_TYPE,
            "window_code": WINDOW_CODE,
            "selected_ticker_entity_count": len(coverage_rows),
            "source_rows_read_by_table": source_rows_read_by_table,
            "context_rows_built": context_rows_built,
            "classification_rows_inserted": len(decision_rows),
            "classification_state_counts": dict(state_counts),
            "decision_status_counts": dict(decision_status_counts),
            "field_coverage_counts": dict(field_coverage_counts),
            "source_dependency_summary": source_dependency_summary,
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
