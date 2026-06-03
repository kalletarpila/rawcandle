from __future__ import annotations

import sqlite3
from collections import Counter

from analysis.datacenter_indices.daily_trigger_classifier import (
    classify_daily_trigger_row,
    classify_daily_watchlist_status,
)


SOURCE_TABLE_TICKER = "dc_ticker_swing_signal_daily"
SOURCE_TABLE_GROUP = "dc_group_swing_signal_daily"
CLASSIFICATION_TYPE = "daily_trigger"
WINDOW_CODE = "daily"
TARGET_ENTITY_TYPE = "TICKER"
DEFAULT_SIGNAL_VERSION = "DC_SWING_SIGNAL_V1"
CLASSIFICATION_VERSION = "V3_DAILY_TRIGGER_CLASSIFIER_V1"
SOURCE_CLASSIFIER = "daily_trigger_classifier"
MISSING_PRICE_STATUS = "MISSING_AS_OF_DATE"


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
          AND c.window_code = 'daily'
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
        raise ValueError(f"Missing eligible TICKER daily coverage rows for run_id '{run_row['run_id']}'")
    return rows


def _load_ticker_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    eligible_tickers: list[str],
) -> tuple[dict[str, sqlite3.Row], set[str]]:
    if not _table_exists(conn, SOURCE_TABLE_TICKER):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_TICKER}'")
    columns = _column_names(conn, SOURCE_TABLE_TICKER)
    required = {
        "signal_date",
        "taxonomy_version",
        "ticker",
        "primary_layer",
        "primary_subindustry",
        "price_data_status",
        "close",
        "exit_risk_severity",
        "exit_reason",
        "latest_structure_label",
        "latest_bos_event_type",
        "latest_bos_freshness",
        "latest_reset_reason",
        "latest_reset_freshness",
        "pullback_signal",
        "breakout_signal",
        "exit_risk_signal",
        "bullish_candle_signal",
        "bullish_divergence_signal",
        "hidden_bullish_divergence_signal",
        "bearish_candle_signal",
        "bearish_divergence_signal",
        "hidden_bearish_divergence_signal",
        "distance_to_ema10_pct",
        "distance_to_ema20_pct",
    }
    missing = sorted(required - columns)
    if missing:
        raise ValueError(f"Source table '{SOURCE_TABLE_TICKER}' missing required columns: {', '.join(missing)}")
    if "trend_state" not in columns and "ticker_trend_state" not in columns:
        raise ValueError(f"Source table '{SOURCE_TABLE_TICKER}' missing both trend_state and ticker_trend_state")

    if not eligible_tickers:
        return {}, columns
    ticker_placeholders = ", ".join("?" for _ in eligible_tickers)
    where_clauses = [
        "signal_date = ?",
        "taxonomy_version = ?",
        f"ticker IN ({ticker_placeholders})",
    ]
    params: list[object] = [signal_date, taxonomy_version_code, *eligible_tickers]
    if "signal_version" in columns:
        where_clauses.append("signal_version = ?")
        params.append(DEFAULT_SIGNAL_VERSION)
    rows = conn.execute(
        f"""
        SELECT *
        FROM {SOURCE_TABLE_TICKER}
        WHERE {' AND '.join(where_clauses)}
        ORDER BY ticker
        """,
        tuple(params),
    ).fetchall()
    return {str(row["ticker"]): row for row in rows}, columns


def _build_pair_clause(pairs: list[tuple[str, str]]) -> tuple[str, list[object]]:
    clause = " OR ".join("(group_type = ? AND group_name = ?)" for _ in pairs)
    params: list[object] = []
    for group_type, group_name in pairs:
        params.extend((group_type, group_name))
    return clause, params


def _load_group_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version_code: str,
    needed_groups: set[tuple[str, str]],
) -> tuple[dict[tuple[str, str], sqlite3.Row], int]:
    if not needed_groups:
        return {}, 0
    if not _table_exists(conn, SOURCE_TABLE_GROUP):
        raise ValueError(f"Missing source table '{SOURCE_TABLE_GROUP}'")
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


def _missing_source_classifier_row(*, ticker: str) -> dict[str, object]:
    output_row = {
        "ticker": ticker,
        "in_datacenter_ecosystem": 1,
        "price_data_status": MISSING_PRICE_STATUS,
        "close": None,
        "trend_state": None,
        "exit_risk_severity": None,
        "latest_structure_label": None,
        "latest_exit_reason": None,
        "latest_bos_event_type": None,
        "latest_bos_freshness": None,
        "latest_reset_reason": None,
        "latest_reset_freshness": None,
        "pullback_signal": 0,
        "breakout_signal": 0,
        "exit_risk_signal": 0,
        "latest_bullish_relevance_class": None,
        "latest_bearish_relevance_class": None,
        "bullish_candle_signal": 0,
        "bullish_divergence_signal": 0,
        "hidden_bullish_divergence_signal": 0,
        "bearish_candle_signal": 0,
        "bearish_divergence_signal": 0,
        "hidden_bearish_divergence_signal": 0,
        "distance_to_ema10_pct": None,
        "distance_to_ema20_pct": None,
        "distance_to_ema50_pct": None,
        "layer_timing_state": None,
        "layer_overheat_risk_level": None,
        "subindustry_timing_state": None,
        "subindustry_overheat_risk_level": None,
    }
    output_row["current_watchlist_status"] = classify_daily_watchlist_status(output_row)
    return output_row


def _context_row_for_classifier(
    *,
    ticker: str,
    ticker_row: sqlite3.Row,
    ticker_columns: set[str],
    layer_row: sqlite3.Row | None,
    subindustry_row: sqlite3.Row | None,
) -> dict[str, object]:
    output_row = {
        "ticker": ticker,
        "in_datacenter_ecosystem": 1,
        "price_data_status": ticker_row["price_data_status"],
        "close": ticker_row["close"],
        "trend_state": ticker_row["trend_state"] if "trend_state" in ticker_columns else ticker_row["ticker_trend_state"],
        "exit_risk_severity": ticker_row["exit_risk_severity"],
        "latest_structure_label": ticker_row["latest_structure_label"],
        "latest_exit_reason": ticker_row["exit_reason"],
        "latest_bos_event_type": ticker_row["latest_bos_event_type"],
        "latest_bos_freshness": ticker_row["latest_bos_freshness"],
        "latest_reset_reason": ticker_row["latest_reset_reason"],
        "latest_reset_freshness": ticker_row["latest_reset_freshness"],
        "pullback_signal": int(ticker_row["pullback_signal"] or 0),
        "breakout_signal": int(ticker_row["breakout_signal"] or 0),
        "exit_risk_signal": int(ticker_row["exit_risk_signal"] or 0),
        "latest_bullish_relevance_class": None,
        "latest_bearish_relevance_class": None,
        "bullish_candle_signal": int(ticker_row["bullish_candle_signal"] or 0),
        "bullish_divergence_signal": int(ticker_row["bullish_divergence_signal"] or 0),
        "hidden_bullish_divergence_signal": int(ticker_row["hidden_bullish_divergence_signal"] or 0),
        "bearish_candle_signal": int(ticker_row["bearish_candle_signal"] or 0),
        "bearish_divergence_signal": int(ticker_row["bearish_divergence_signal"] or 0),
        "hidden_bearish_divergence_signal": int(ticker_row["hidden_bearish_divergence_signal"] or 0),
        "distance_to_ema10_pct": ticker_row["distance_to_ema10_pct"],
        "distance_to_ema20_pct": ticker_row["distance_to_ema20_pct"],
        "distance_to_ema50_pct": None,
        "layer_timing_state": None if layer_row is None else layer_row["timing_state"],
        "layer_overheat_risk_level": None if layer_row is None else layer_row["overheat_risk_level"],
        "subindustry_timing_state": None if subindustry_row is None else subindustry_row["timing_state"],
        "subindustry_overheat_risk_level": None
        if subindustry_row is None
        else subindustry_row["overheat_risk_level"],
    }
    output_row["current_watchlist_status"] = classify_daily_watchlist_status(output_row)
    return output_row


def _classification_row(
    *,
    run_row: sqlite3.Row,
    coverage_row: sqlite3.Row,
    classifier_row: dict[str, object],
    source_run_id: str,
) -> dict[str, object]:
    classification_state, primary_reason, blocking_reason, next_action = classify_daily_trigger_row(classifier_row)
    decision_status = "OK" if _normalize_text(classification_state) else "MISSING"
    return {
        "run_id": str(run_row["run_id"]),
        "ecosystem_id": int(run_row["ecosystem_id"]),
        "signal_date": str(run_row["signal_date"]),
        "taxonomy_version_id": int(run_row["taxonomy_version_id"]),
        "window_code": WINDOW_CODE,
        "entity_id": int(coverage_row["entity_id"]),
        "classification_type": CLASSIFICATION_TYPE,
        "classification_state": _normalize_text(classification_state),
        "primary_reason": _normalize_text(primary_reason),
        "blocking_reason": _normalize_text(blocking_reason),
        "risk_reason": None,
        "next_action": _normalize_text(next_action),
        "priority_score": None,
        "priority_label": None,
        "sort_rank": None,
        "source_classifier": SOURCE_CLASSIFIER,
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


def build_canonical_v3_daily_trigger_classifications(
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

        eligible_tickers = [str(row["entity_code"]) for row in coverage_rows]
        ticker_rows_by_ticker, ticker_columns = _load_ticker_rows(
            conn,
            signal_date=str(run_row["signal_date"]),
            taxonomy_version_code=str(run_row["version_code"]),
            eligible_tickers=eligible_tickers,
        )

        needed_groups: set[tuple[str, str]] = set()
        for ticker_row in ticker_rows_by_ticker.values():
            layer_name = _normalize_text(ticker_row["primary_layer"])
            subindustry_name = _normalize_text(ticker_row["primary_subindustry"])
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
        drift_counters = Counter(
            {
                "bearish_divergence_signal_truthy": 0,
                "bullish_divergence_signal_truthy": 0,
                "hidden_bullish_divergence_signal_truthy": 0,
                "hidden_bearish_divergence_signal_truthy": 0,
                "relevance_fields_forced_null": 0,
                "distance_to_ema50_pct_forced_null": 0,
                "rows_without_lower_level_source": 0,
            }
        )
        context_rows_built = 0

        explicit_source_run_id = (
            f"V3_DAILY_TRIGGER_CLASSIFICATION_FROM_LOWER_LEVEL_{str(run_row['signal_date']).replace('-', '_')}"
        )

        for coverage_row in coverage_rows:
            ticker = str(coverage_row["entity_code"])
            ticker_row = ticker_rows_by_ticker.get(ticker)
            if ticker_row is None:
                warnings.append(f"Missing lower-level ticker row for daily ticker '{ticker}', classifying as INSUFFICIENT_DATA")
                classifier_row = _missing_source_classifier_row(ticker=ticker)
                drift_counters["rows_without_lower_level_source"] += 1
            else:
                layer_name = _normalize_text(ticker_row["primary_layer"])
                subindustry_name = _normalize_text(ticker_row["primary_subindustry"])
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
                    ticker_row=ticker_row,
                    ticker_columns=ticker_columns,
                    layer_row=layer_row,
                    subindustry_row=subindustry_row,
                )
                if classifier_row["bearish_divergence_signal"]:
                    drift_counters["bearish_divergence_signal_truthy"] += 1
                if classifier_row["bullish_divergence_signal"]:
                    drift_counters["bullish_divergence_signal_truthy"] += 1
                if classifier_row["hidden_bullish_divergence_signal"]:
                    drift_counters["hidden_bullish_divergence_signal_truthy"] += 1
                if classifier_row["hidden_bearish_divergence_signal"]:
                    drift_counters["hidden_bearish_divergence_signal_truthy"] += 1

            drift_counters["relevance_fields_forced_null"] += 1
            drift_counters["distance_to_ema50_pct_forced_null"] += 1
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
            SOURCE_TABLE_TICKER: len(ticker_rows_by_ticker),
            SOURCE_TABLE_GROUP: group_rows_read,
            "eco_entity_coverage": len(coverage_rows),
        }
        source_dependency_summary = {
            SOURCE_TABLE_TICKER: "DERIVED_FROM_RAW_SOURCE",
            SOURCE_TABLE_GROUP: "DERIVED_FROM_RAW_SOURCE",
            "eco_entity_coverage": "V3_TARGET_UNIVERSE",
            "runtime_excludes": ["dc_report_classification_v2", "dc_report_context_daily_v2"],
        }
        known_source_drift_checks = dict(drift_counters)
        limitations = [
            "replaces only daily_trigger",
            "does not use dc_report_classification_v2 as runtime source",
            "does not use dc_report_context_daily_v2 as runtime source",
            "priority/rank fields remain NULL",
            "rolling2/rolling5/rolling30 classifications remain as-is",
            "relevance-class fields are intentionally kept NULL to preserve current production behavior",
            "source drift may cause parity deltas versus frozen V2 payload",
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
            "known_source_drift_checks": known_source_drift_checks,
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
