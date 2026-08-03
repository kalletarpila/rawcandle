from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rawcandle.cli.plan_ec_source_layer_build import (
    REQUIRED_SOURCE_TABLES,
    _collect_source_readiness,
    _distinct_values,
    _glob_table_names,
    _read_taxonomy_csv,
    _read_watchlist,
    _resolve_selected_signal_date,
    _scalar,
    _table_exists,
    open_readonly_sqlite,
)
from rawcandle.cli.ec_source_layer_watchlist_policy import build_watchlist_membership_summary
from rawcandle.ec_datacenter_taxonomy_loader import _compute_source_hash


EXPECTED_TAXONOMY_ROW_COUNT = 329
EXPECTED_TAXONOMY_TICKER_COUNT = 236
EXPECTED_TAXONOMY_LAYER_COUNT = 16
EXPECTED_TAXONOMY_SUBINDUSTRY_COUNT = 37

REQUIRED_REFRESH_EC_TABLES = (
    "ec_ecosystem",
    "ec_taxonomy_version",
    "ec_entity",
    "ec_membership",
    "ec_watchlist",
    "ec_watchlist_member",
    "ec_signal_run",
    "ec_ticker_signal_daily",
    "ec_group_signal_daily",
    "ec_group_synthetic_ohlc_daily",
    "ec_group_index_daily",
    "ec_pipeline_watermark",
)

EC_FACT_TABLES = (
    ("ec_ticker_signal_daily", "signal_date"),
    ("ec_group_signal_daily", "signal_date"),
    ("ec_group_synthetic_ohlc_daily", "signal_date"),
    ("ec_group_index_daily", "signal_date"),
)

READY_STATUSES = {
    "READY_REFRESH_NEW_DATE",
    "READY_REFRESH_REPLACE_DATE",
    "SKIP_UP_TO_DATE",
}

PLANNED_REFRESH_SEQUENCE = (
    "1. Backup production analysis.db",
    "2. Verify ec_ schema installed",
    "3. Re-verify source date alignment",
    "4. Verify taxonomy/watchlist source compatibility",
    "5. Refresh selected date ticker facts with replace_existing=True",
    "6. Refresh selected date group signal facts with replace_existing=True",
    "7. Refresh selected date synthetic OHLC facts with replace_existing=True",
    "8. Refresh selected date group index facts with replace_existing=True",
    "9. Refresh pipeline watermark with replace_existing=True",
    "10. Run coverage audit",
    "11. Run fact parity audit",
    "12. Print summary",
)

SCHEDULER_INTEGRATION_NOTES = (
    "legacy dc_ Datacenter reporting remains primary",
    "future scheduler refresh must run additively after legacy Datacenter success",
    "refresh planner is read-only and does not perform replacement itself",
    "taxonomy/watchlist recurring update policy is not implemented in this planner",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan a no-write ec_ source-layer refresh against an installed production-style SQLite DB")
    parser.add_argument("--db", required=True, help="Path to the SQLite database to inspect read-only")
    parser.add_argument("--ecosystem", required=True, help="Target ecosystem code, for example DATACENTER")
    parser.add_argument("--taxonomy-version", required=True, help="Expected taxonomy version code, for example DC_TAXONOMY_FULL_V1")
    parser.add_argument("--taxonomy-csv", required=True, help="Path to the source taxonomy CSV")
    parser.add_argument("--watchlist", required=True, help="Path to the source watchlist TXT")
    parser.add_argument("--signal-date", help="Optional explicit signal date in YYYY-MM-DD format")
    parser.add_argument("--allow-replace-date", action="store_true", help="Allow planner to mark an already loaded or partially loaded date as refresh-replace ready")
    parser.add_argument("--format", choices=("text",), default="text")
    return parser


def _collect_refresh_schema_state(conn) -> dict[str, object]:
    true_ec_tables = _glob_table_names(conn, "ec_*")
    eco_tables = _glob_table_names(conn, "eco_*")
    required_ec_missing = [table_name for table_name in REQUIRED_REFRESH_EC_TABLES if table_name not in true_ec_tables]
    source_tables = {
        table_name: {
            "present": _table_exists(conn, table_name),
            "date_column": date_column,
        }
        for table_name, date_column in REQUIRED_SOURCE_TABLES
    }
    return {
        "true_ec_tables": true_ec_tables,
        "eco_tables": eco_tables,
        "required_ec_missing": required_ec_missing,
        "source_tables": source_tables,
    }


def _with_selected_date_row_counts(conn, source_readiness: dict[str, object], selected_signal_date: str) -> dict[str, object]:
    tables = source_readiness.get("tables", {})
    assert isinstance(tables, dict)
    for table_name, date_column in REQUIRED_SOURCE_TABLES:
        table_info = tables.get(table_name)
        if not isinstance(table_info, dict) or not table_info.get("present") or not date_column:
            continue
        row_count = int(
            _scalar(
                conn,
                f"SELECT COUNT(*) FROM {table_name} WHERE {date_column} = ?",
                (selected_signal_date,),
            )
            or 0
        )
        table_info["selected_date_row_count"] = row_count
    return source_readiness


def _collect_loaded_ec_state(conn, selected_signal_date: str) -> dict[str, object]:
    tables: dict[str, object] = {}
    latest_loaded_dates: dict[str, str | None] = {}
    fully_loaded = True
    any_selected_rows = False
    any_selected_missing = False
    for table_name, date_column in EC_FACT_TABLES:
        latest_loaded_date = _scalar(conn, f"SELECT MAX({date_column}) FROM {table_name}")
        distinct_loaded_dates = _distinct_values(conn, table_name, date_column)
        selected_date_row_count = int(
            _scalar(
                conn,
                f"SELECT COUNT(*) FROM {table_name} WHERE {date_column} = ?",
                (selected_signal_date,),
            )
            or 0
        )
        selected_date_present = selected_date_row_count > 0
        tables[table_name] = {
            "latest_loaded_date": latest_loaded_date,
            "distinct_loaded_dates": distinct_loaded_dates,
            "selected_date_present": selected_date_present,
            "selected_date_row_count": selected_date_row_count,
        }
        latest_loaded_dates[table_name] = str(latest_loaded_date) if latest_loaded_date is not None else None
        any_selected_rows = any_selected_rows or selected_date_present
        fully_loaded = fully_loaded and selected_date_present
        any_selected_missing = any_selected_missing or not selected_date_present

    loaded_latest_dates = [date for date in latest_loaded_dates.values() if date]
    latest_loaded_fact_date = max(loaded_latest_dates) if loaded_latest_dates else None
    selected_date_exists_partially = any_selected_rows and any_selected_missing
    return {
        "tables": tables,
        "latest_loaded_dates": latest_loaded_dates,
        "latest_loaded_fact_date": latest_loaded_fact_date,
        "selected_date_exists_in_all_facts": fully_loaded,
        "selected_date_exists_partially": selected_date_exists_partially,
        "selected_date_exists_in_any_fact": any_selected_rows,
    }


def _fetch_loaded_taxonomy_state(conn, ecosystem_code: str, taxonomy_version_code: str) -> dict[str, object]:
    row = conn.execute(
        """
        SELECT
            e.ecosystem_id,
            e.ecosystem_code,
            tv.taxonomy_version_id,
            tv.taxonomy_version_code,
            tv.source_reference,
            tv.source_hash,
            tv.status,
            tv.is_active
        FROM ec_ecosystem e
        JOIN ec_taxonomy_version tv
          ON tv.ecosystem_id = e.ecosystem_id
        WHERE e.ecosystem_code = ?
          AND tv.taxonomy_version_code = ?
        ORDER BY tv.taxonomy_version_id DESC
        LIMIT 1
        """,
        (ecosystem_code, taxonomy_version_code),
    ).fetchone()
    if row is None:
        return {"present": False}
    return {
        "present": True,
        "ecosystem_id": int(row["ecosystem_id"]),
        "ecosystem_code": str(row["ecosystem_code"]),
        "taxonomy_version_id": int(row["taxonomy_version_id"]),
        "taxonomy_version_code": str(row["taxonomy_version_code"]),
        "source_reference": row["source_reference"],
        "source_hash": row["source_hash"],
        "status": row["status"],
        "is_active": int(row["is_active"]),
    }


def _table_columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _collect_loaded_watchlist_tickers(conn, ecosystem_code: str) -> list[str]:
    watchlist_columns = _table_columns(conn, "ec_watchlist")
    watchlist_member_columns = _table_columns(conn, "ec_watchlist_member")
    entity_columns = _table_columns(conn, "ec_entity")
    watchlist_status_sql = "AND w.status = 'ACTIVE'" if "status" in watchlist_columns else ""
    member_status_sql = "AND wm.status = 'ACTIVE'" if "status" in watchlist_member_columns else ""
    entity_status_sql = "AND e.status = 'ACTIVE'" if "status" in entity_columns else ""
    rows = conn.execute(
        f"""
        SELECT DISTINCT UPPER(e.entity_code) AS ticker
        FROM ec_watchlist w
        JOIN ec_ecosystem eco ON eco.ecosystem_id = w.ecosystem_id
        JOIN ec_watchlist_member wm ON wm.watchlist_id = w.watchlist_id
        JOIN ec_entity e ON e.entity_id = wm.entity_id
        WHERE eco.ecosystem_code = ?
          AND e.entity_type = 'TICKER'
          {watchlist_status_sql}
          {member_status_sql}
          {entity_status_sql}
        ORDER BY ticker
        """,
        (ecosystem_code,),
    ).fetchall()
    return [str(row["ticker"]) for row in rows]


def _check_taxonomy_watchlist_compatibility(
    conn,
    *,
    ecosystem_code: str,
    taxonomy_version_code: str,
    taxonomy_summary: dict[str, object],
    watchlist_summary: dict[str, object],
) -> dict[str, object]:
    loaded_taxonomy = _fetch_loaded_taxonomy_state(conn, ecosystem_code, taxonomy_version_code)
    if not loaded_taxonomy.get("present"):
        return {
            "status": "BLOCKED_TAXONOMY_SOURCE",
            "loaded_taxonomy": loaded_taxonomy,
            "error": f"loaded ec_taxonomy_version missing for ecosystem {ecosystem_code!r} and taxonomy_version {taxonomy_version_code!r}",
        }

    count_errors: list[str] = []
    if int(taxonomy_summary.get("row_count", 0)) != EXPECTED_TAXONOMY_ROW_COUNT:
        count_errors.append(f"taxonomy row_count expected {EXPECTED_TAXONOMY_ROW_COUNT} but got {taxonomy_summary.get('row_count')}")
    if int(taxonomy_summary.get("distinct_ticker_count", 0)) != EXPECTED_TAXONOMY_TICKER_COUNT:
        count_errors.append(
            f"taxonomy distinct_ticker_count expected {EXPECTED_TAXONOMY_TICKER_COUNT} but got {taxonomy_summary.get('distinct_ticker_count')}"
        )
    if int(taxonomy_summary.get("distinct_layer_count", 0)) != EXPECTED_TAXONOMY_LAYER_COUNT:
        count_errors.append(
            f"taxonomy distinct_layer_count expected {EXPECTED_TAXONOMY_LAYER_COUNT} but got {taxonomy_summary.get('distinct_layer_count')}"
        )
    if int(taxonomy_summary.get("distinct_subindustry_count", 0)) != EXPECTED_TAXONOMY_SUBINDUSTRY_COUNT:
        count_errors.append(
            "taxonomy distinct_subindustry_count expected "
            f"{EXPECTED_TAXONOMY_SUBINDUSTRY_COUNT} but got {taxonomy_summary.get('distinct_subindustry_count')}"
        )
    if count_errors:
        return {
            "status": "BLOCKED_TAXONOMY_SOURCE",
            "loaded_taxonomy": loaded_taxonomy,
            "error": "; ".join(count_errors),
        }

    source_hash = _compute_source_hash(Path(str(taxonomy_summary["path"])))
    loaded_source_hash = loaded_taxonomy.get("source_hash")
    if loaded_source_hash and str(loaded_source_hash) != source_hash:
        return {
            "status": "BLOCKED_TAXONOMY_SOURCE",
            "loaded_taxonomy": loaded_taxonomy,
            "source_hash_match": False,
            "loaded_source_hash": loaded_source_hash,
            "source_hash": source_hash,
            "error": "source taxonomy hash differs from loaded ec_taxonomy_version.source_hash",
        }

    source_watchlist_tickers = list(watchlist_summary.get("tickers", []))
    loaded_watchlist_tickers = _collect_loaded_watchlist_tickers(conn, ecosystem_code)
    watchlist_membership_summary = build_watchlist_membership_summary(
        source_watchlist_tickers=source_watchlist_tickers,
        loaded_watchlist_tickers=loaded_watchlist_tickers,
    )

    return {
        "status": "OK",
        "loaded_taxonomy": loaded_taxonomy,
        "source_hash_match": True,
        "loaded_source_hash": loaded_source_hash,
        "source_hash": source_hash,
        **watchlist_membership_summary,
    }


def _compare_universe_and_groups(conn, selected_signal_date: str, taxonomy_version_id: int) -> dict[str, object]:
    source_tickers = set(
        _distinct_values(
            conn,
            "dc_ticker_swing_signal_daily",
            "ticker",
            "signal_date = ?",
            (selected_signal_date,),
        )
    )
    ec_ticker_entities = set(
        _distinct_values(
            conn,
            "ec_entity",
            "entity_code",
            "entity_type = 'TICKER'",
        )
    )
    taxonomy_tickers = set(
        _distinct_values(
            conn,
            "ec_entity e JOIN ec_membership m ON m.child_entity_id = e.entity_id",
            "e.entity_code",
            "e.entity_type = 'TICKER' AND m.taxonomy_version_id = ? AND m.is_primary = 1",
            (taxonomy_version_id,),
        )
    )

    missing_in_ec_entities = sorted(source_tickers - ec_ticker_entities)
    missing_primary_membership = sorted(source_tickers - taxonomy_tickers)

    group_l1_names = set(
        _distinct_values(
            conn,
            "ec_entity",
            "entity_name",
            "entity_type = 'GROUP_L1'",
        )
    )
    group_l2_names = set(
        _distinct_values(
            conn,
            "ec_entity",
            "entity_name",
            "entity_type = 'GROUP_L2'",
        )
    )
    ecosystem_aliases = set(
        _distinct_values(
            conn,
            "ec_entity_alias",
            "alias_value",
            "alias_type = 'DC_GROUP_NAME' AND source_system = 'dc_group_facts'",
        )
    )

    group_signal_layers = set(
        _distinct_values(
            conn,
            "dc_group_swing_signal_daily",
            "group_name",
            "signal_date = ? AND group_type = 'layer'",
            (selected_signal_date,),
        )
    )
    group_signal_subindustries = set(
        _distinct_values(
            conn,
            "dc_group_swing_signal_daily",
            "group_name",
            "signal_date = ? AND group_type = 'subindustry'",
            (selected_signal_date,),
        )
    )
    group_signal_ecosystem = set(
        _distinct_values(
            conn,
            "dc_group_swing_signal_daily",
            "group_name",
            "signal_date = ? AND group_type = 'ecosystem'",
            (selected_signal_date,),
        )
    )
    synth_layers = set(
        _distinct_values(
            conn,
            "dc_group_synthetic_ohlc_daily",
            "group_name",
            "ohlc_date = ? AND group_type = 'layer'",
            (selected_signal_date,),
        )
    )
    synth_subindustries = set(
        _distinct_values(
            conn,
            "dc_group_synthetic_ohlc_daily",
            "group_name",
            "ohlc_date = ? AND group_type = 'subindustry'",
            (selected_signal_date,),
        )
    )
    index_layers = set(
        _distinct_values(
            conn,
            "dc_group_index_daily",
            "group_name",
            "index_date = ? AND group_type = 'layer'",
            (selected_signal_date,),
        )
    )
    index_subindustries = set(
        _distinct_values(
            conn,
            "dc_group_index_daily",
            "group_name",
            "index_date = ? AND group_type = 'subindustry'",
            (selected_signal_date,),
        )
    )
    index_ecosystem = set(
        _distinct_values(
            conn,
            "dc_group_index_daily",
            "group_name",
            "index_date = ? AND group_type = 'ecosystem'",
            (selected_signal_date,),
        )
    )

    missing_group_l1 = sorted((group_signal_layers | synth_layers | index_layers) - group_l1_names)
    missing_group_l2 = sorted((group_signal_subindustries | synth_subindustries | index_subindustries) - group_l2_names)
    expected_ecosystem_aliases = sorted((group_signal_ecosystem | index_ecosystem) - ecosystem_aliases)

    return {
        "dc_ticker_count": len(source_tickers),
        "ec_ticker_entity_count": len(ec_ticker_entities),
        "taxonomy_ticker_count": len(taxonomy_tickers),
        "dc_ticker_missing_in_ec_entity": missing_in_ec_entities,
        "dc_ticker_missing_primary_taxonomy_membership": missing_primary_membership,
        "missing_group_l1_entities": missing_group_l1,
        "missing_group_l2_entities": missing_group_l2,
        "missing_ecosystem_aliases": expected_ecosystem_aliases,
        "mapping_clear": not any(
            [
                missing_in_ec_entities,
                missing_primary_membership,
                missing_group_l1,
                missing_group_l2,
                expected_ecosystem_aliases,
            ]
        ),
    }


def _decide_refresh_status(
    *,
    selected_signal_date: str,
    allow_replace_date: bool,
    loaded_state: dict[str, object],
) -> tuple[str, str | None]:
    latest_loaded_fact_date = loaded_state.get("latest_loaded_fact_date")
    if isinstance(latest_loaded_fact_date, str) and selected_signal_date < latest_loaded_fact_date:
        return (
            "BLOCKED_OLDER_THAN_LOADED_DATE",
            "selected signal date is older than the latest loaded ec_ fact date; backfill refresh planning is not implemented",
        )

    selected_in_all = bool(loaded_state.get("selected_date_exists_in_all_facts"))
    selected_partial = bool(loaded_state.get("selected_date_exists_partially"))
    selected_any = bool(loaded_state.get("selected_date_exists_in_any_fact"))

    if not selected_any:
        return ("READY_REFRESH_NEW_DATE", None)
    if selected_in_all and allow_replace_date:
        return ("READY_REFRESH_REPLACE_DATE", None)
    if selected_in_all:
        return ("SKIP_UP_TO_DATE", None)
    if selected_partial and allow_replace_date:
        return ("READY_REFRESH_REPLACE_DATE", None)
    if selected_partial:
        return (
            "BLOCKED_EXISTING_DATE_WITHOUT_REPLACE",
            "selected signal date exists partially in ec_ facts and --allow-replace-date was not supplied",
        )
    return ("SKIP_UP_TO_DATE", None)


def plan_ec_source_layer_refresh(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    signal_date: str | None = None,
    allow_replace_date: bool = False,
) -> dict[str, object]:
    taxonomy_summary = _read_taxonomy_csv(taxonomy_csv_path, taxonomy_version_code)
    if taxonomy_summary["status"] != "OK":
        return {
            "status": "BLOCKED_TAXONOMY_SOURCE",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "taxonomy_summary": taxonomy_summary,
        }

    watchlist_summary = _read_watchlist(watchlist_path)
    if watchlist_summary["status"] != "OK":
        return {
            "status": "BLOCKED_WATCHLIST_SOURCE",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "taxonomy_summary": taxonomy_summary,
            "watchlist_summary": watchlist_summary,
        }

    with open_readonly_sqlite(db_path) as conn:
        schema_state = _collect_refresh_schema_state(conn)
        if schema_state["required_ec_missing"]:
            return {
                "status": "BLOCKED_EC_SCHEMA_MISSING",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "schema_state": schema_state,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
            }

        source_readiness = _collect_source_readiness(conn)
        missing_tables = source_readiness["missing_tables"]
        assert isinstance(missing_tables, list)
        if missing_tables:
            return {
                "status": "BLOCKED_MISSING_SOURCE",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "schema_state": schema_state,
                "source_readiness": source_readiness,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
            }

        selected_date_info = _resolve_selected_signal_date(source_readiness, signal_date)
        if selected_date_info["status"] != "OK":
            return {
                "status": "BLOCKED_DATE_MISMATCH",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "schema_state": schema_state,
                "source_readiness": source_readiness,
                "selected_date_info": selected_date_info,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
            }

        selected_signal_date = selected_date_info["selected_signal_date"]
        assert isinstance(selected_signal_date, str)
        source_readiness = _with_selected_date_row_counts(conn, source_readiness, selected_signal_date)
        selected_date_missing_rows = [
            table_name
            for table_name, date_column in REQUIRED_SOURCE_TABLES
            if date_column
            and int(
                (
                    source_readiness.get("tables", {})
                    .get(table_name, {})
                    .get("selected_date_row_count", 0)
                )
            )
            == 0
        ]
        if selected_date_missing_rows:
            selected_date_info = {
                **selected_date_info,
                "status": "BLOCKED_DATE_MISMATCH",
                "error": (
                    f"selected signal_date {selected_signal_date} has no source rows for: "
                    f"{', '.join(selected_date_missing_rows)}"
                ),
            }
            return {
                "status": "BLOCKED_DATE_MISMATCH",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "schema_state": schema_state,
                "source_readiness": source_readiness,
                "selected_date_info": selected_date_info,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
            }
        loaded_state = _collect_loaded_ec_state(conn, selected_signal_date)
        compatibility_summary = _check_taxonomy_watchlist_compatibility(
            conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            taxonomy_summary=taxonomy_summary,
            watchlist_summary=watchlist_summary,
        )
        if compatibility_summary["status"] != "OK":
            return {
                "status": compatibility_summary["status"],
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "schema_state": schema_state,
                "source_readiness": source_readiness,
                "selected_date_info": selected_date_info,
                "loaded_state": loaded_state,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
                "compatibility_summary": compatibility_summary,
            }

        loaded_taxonomy = compatibility_summary["loaded_taxonomy"]
        assert isinstance(loaded_taxonomy, dict)
        taxonomy_version_id = int(loaded_taxonomy["taxonomy_version_id"])
        mapping_summary = _compare_universe_and_groups(conn, selected_signal_date, taxonomy_version_id)
        if not mapping_summary["mapping_clear"]:
            return {
                "status": "BLOCKED_UNCLEAR_MAPPING",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "schema_state": schema_state,
                "source_readiness": source_readiness,
                "selected_date_info": selected_date_info,
                "loaded_state": loaded_state,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
                "compatibility_summary": compatibility_summary,
                "mapping_summary": mapping_summary,
            }

    status, decision_error = _decide_refresh_status(
        selected_signal_date=selected_signal_date,
        allow_replace_date=allow_replace_date,
        loaded_state=loaded_state,
    )
    summary = {
        "status": status,
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_code": taxonomy_version_code,
        "allow_replace_date": allow_replace_date,
        "schema_state": schema_state,
        "source_readiness": source_readiness,
        "selected_date_info": selected_date_info,
        "loaded_state": loaded_state,
        "taxonomy_summary": taxonomy_summary,
        "watchlist_summary": watchlist_summary,
        "compatibility_summary": compatibility_summary,
        "mapping_summary": mapping_summary,
        "planned_refresh_sequence": list(PLANNED_REFRESH_SEQUENCE),
        "scheduler_integration_notes": list(SCHEDULER_INTEGRATION_NOTES),
    }
    if decision_error:
        summary["decision_error"] = decision_error
    return summary


def _render_source_table_lines(source_readiness: dict[str, object]) -> list[str]:
    tables = source_readiness.get("tables", {})
    assert isinstance(tables, dict)
    lines: list[str] = []
    for table_name, _ in REQUIRED_SOURCE_TABLES:
        table_info = tables.get(table_name, {})
        assert isinstance(table_info, dict)
        if not table_info.get("present"):
            lines.append(f"- {table_name}: MISSING")
            continue
        row_count = table_info.get("row_count", 0)
        latest_date = table_info.get("latest_date")
        selected_row_count = table_info.get("selected_date_row_count")
        if latest_date is None:
            lines.append(f"- {table_name}: present, row_count={row_count}")
        elif selected_row_count is None:
            lines.append(f"- {table_name}: present, row_count={row_count}, latest_date={latest_date}")
        else:
            lines.append(
                f"- {table_name}: present, row_count={row_count}, latest_date={latest_date}, "
                f"selected_date_row_count={selected_row_count}"
            )
    return lines


def render_plan_text(summary: dict[str, object]) -> str:
    lines = [
        "EC Source Layer Refresh Plan",
        f"ecosystem_code={summary.get('ecosystem_code', '')}",
        f"taxonomy_version_code={summary.get('taxonomy_version_code', '')}",
        "mode=NO_WRITE_REFRESH_PLAN",
        "",
        "Schema State",
    ]

    schema_state = summary.get("schema_state", {})
    if isinstance(schema_state, dict):
        lines.extend(
            [
                f"- true_ec_tables={schema_state.get('true_ec_tables', [])}",
                f"- required_ec_missing={schema_state.get('required_ec_missing', [])}",
                f"- eco_tables={schema_state.get('eco_tables', [])}",
            ]
        )

    lines.extend(["", "Source Readiness"])
    source_readiness = summary.get("source_readiness")
    if isinstance(source_readiness, dict):
        lines.extend(_render_source_table_lines(source_readiness))

    selected_date_info = summary.get("selected_date_info")
    if isinstance(selected_date_info, dict):
        lines.extend(
            [
                f"- selected_signal_date={selected_date_info.get('selected_signal_date')}",
                f"- latest_source_dates={selected_date_info.get('latest_dates', {})}",
            ]
        )
        if selected_date_info.get("error"):
            lines.append(f"- error={selected_date_info.get('error')}")

    lines.extend(["", "Loaded EC State"])
    loaded_state = summary.get("loaded_state")
    if isinstance(loaded_state, dict):
        lines.extend(
            [
                f"- latest_loaded_fact_date={loaded_state.get('latest_loaded_fact_date')}",
                f"- latest_loaded_dates={loaded_state.get('latest_loaded_dates', {})}",
                f"- selected_date_exists_in_all_facts={loaded_state.get('selected_date_exists_in_all_facts')}",
                f"- selected_date_exists_partially={loaded_state.get('selected_date_exists_partially')}",
            ]
        )
        tables = loaded_state.get("tables", {})
        if isinstance(tables, dict):
            for table_name, _ in EC_FACT_TABLES:
                table_info = tables.get(table_name, {})
                if not isinstance(table_info, dict):
                    continue
                lines.append(
                    f"- {table_name}: latest_loaded_date={table_info.get('latest_loaded_date')}, "
                    f"selected_date_present={table_info.get('selected_date_present')}, "
                    f"selected_date_row_count={table_info.get('selected_date_row_count')}, "
                    f"distinct_loaded_dates={table_info.get('distinct_loaded_dates')}"
                )

    lines.extend(["", "Taxonomy / Watchlist Compatibility"])
    taxonomy_summary = summary.get("taxonomy_summary")
    watchlist_summary = summary.get("watchlist_summary")
    compatibility_summary = summary.get("compatibility_summary")
    if isinstance(taxonomy_summary, dict):
        lines.extend(
            [
                f"- taxonomy_path={taxonomy_summary.get('path')}",
                f"- taxonomy_row_count={taxonomy_summary.get('row_count')}",
                f"- taxonomy_distinct_ticker_count={taxonomy_summary.get('distinct_ticker_count')}",
                f"- taxonomy_distinct_layer_count={taxonomy_summary.get('distinct_layer_count')}",
                f"- taxonomy_distinct_subindustry_count={taxonomy_summary.get('distinct_subindustry_count')}",
            ]
        )
    if isinstance(watchlist_summary, dict):
        lines.extend(
            [
                f"- watchlist_path={watchlist_summary.get('path')}",
                f"- watchlist_ticker_count={watchlist_summary.get('ticker_count')}",
                f"- watchlist_contains_crgy={watchlist_summary.get('contains_crgy')}",
            ]
        )
    if isinstance(compatibility_summary, dict):
        lines.extend(
            [
                f"- compatibility_status={compatibility_summary.get('status')}",
                f"- source_hash_match={compatibility_summary.get('source_hash_match')}",
                f"- watchlist_membership_status={compatibility_summary.get('watchlist_membership_status')}",
                f"- watchlist_sync_required={str(bool(compatibility_summary.get('watchlist_sync_required'))).lower()}",
                f"- watchlist_source_member_count={compatibility_summary.get('watchlist_source_member_count')}",
                f"- watchlist_loaded_member_count={compatibility_summary.get('watchlist_loaded_member_count')}",
                f"- watchlist_missing_in_loaded_count={compatibility_summary.get('watchlist_missing_in_loaded_count')}",
                f"- watchlist_loaded_only_count={compatibility_summary.get('watchlist_loaded_only_count')}",
            ]
        )
        if compatibility_summary.get("watchlist_missing_in_loaded") is not None:
            lines.append(f"- watchlist_missing_in_loaded={compatibility_summary.get('watchlist_missing_in_loaded')}")
        if compatibility_summary.get("watchlist_loaded_only") is not None:
            lines.append(f"- watchlist_loaded_only={compatibility_summary.get('watchlist_loaded_only')}")
        if compatibility_summary.get("error"):
            lines.append(f"- error={compatibility_summary.get('error')}")

    lines.extend(["", "Universe and Group Consistency"])
    mapping_summary = summary.get("mapping_summary")
    if isinstance(mapping_summary, dict):
        lines.extend(
            [
                f"- dc_ticker_count={mapping_summary.get('dc_ticker_count')}",
                f"- ec_ticker_entity_count={mapping_summary.get('ec_ticker_entity_count')}",
                f"- taxonomy_ticker_count={mapping_summary.get('taxonomy_ticker_count')}",
                f"- dc_ticker_missing_in_ec_entity={mapping_summary.get('dc_ticker_missing_in_ec_entity')}",
                f"- dc_ticker_missing_primary_taxonomy_membership={mapping_summary.get('dc_ticker_missing_primary_taxonomy_membership')}",
                f"- missing_group_l1_entities={mapping_summary.get('missing_group_l1_entities')}",
                f"- missing_group_l2_entities={mapping_summary.get('missing_group_l2_entities')}",
                f"- missing_ecosystem_aliases={mapping_summary.get('missing_ecosystem_aliases')}",
            ]
        )

    lines.extend(["", "Planned Refresh Sequence"])
    if summary.get("status") in READY_STATUSES:
        lines.extend(f"- {step}" for step in PLANNED_REFRESH_SEQUENCE)
    else:
        lines.append("- blocked before write-capable refresh planning can proceed")

    lines.extend(["", "Scheduler Integration Notes"])
    lines.extend(f"- {note}" for note in SCHEDULER_INTEGRATION_NOTES)

    lines.extend(
        [
            "",
            "Plan Status",
            f"- status={summary.get('status')}",
        ]
    )
    if summary.get("decision_error"):
        lines.append(f"- decision_error={summary.get('decision_error')}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = plan_ec_source_layer_refresh(
        db_path=args.db,
        ecosystem_code=args.ecosystem,
        taxonomy_version_code=args.taxonomy_version,
        taxonomy_csv_path=args.taxonomy_csv,
        watchlist_path=args.watchlist,
        signal_date=args.signal_date,
        allow_replace_date=args.allow_replace_date,
    )
    sys.stdout.write(render_plan_text(summary) + "\n")
    return 0 if summary["status"] in READY_STATUSES else 2


if __name__ == "__main__":
    raise SystemExit(main())
