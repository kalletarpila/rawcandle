from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from rawcandle.cli.plan_ec_source_layer_build import (
    REQUIRED_SOURCE_TABLES,
    _distinct_values,
    _glob_table_names,
    _read_taxonomy_csv,
    _read_watchlist,
    _scalar,
    _table_exists,
    open_readonly_sqlite,
)
from rawcandle.cli.plan_ec_source_layer_refresh import (
    EC_FACT_TABLES,
    EXPECTED_TAXONOMY_LAYER_COUNT,
    EXPECTED_TAXONOMY_ROW_COUNT,
    EXPECTED_TAXONOMY_SUBINDUSTRY_COUNT,
    EXPECTED_TAXONOMY_TICKER_COUNT,
    REQUIRED_REFRESH_EC_TABLES,
)
from rawcandle.cli.ec_source_layer_watchlist_policy import build_watchlist_membership_summary
from rawcandle.ec_datacenter_taxonomy_loader import _compute_source_hash


MAX_RANGE_DAYS = 60
SOURCE_FACT_TABLES = tuple((table_name, date_column) for table_name, date_column in REQUIRED_SOURCE_TABLES if date_column)
SUCCESS_EXIT_STATUSES = {"READY_BACKFILL_PLAN", "SKIP_ALL_DATES_ALREADY_LOADED"}

PLANNED_BACKFILL_SEQUENCE = (
    "1. Backup production analysis.db",
    "2. Re-check ec_ schema installed",
    "3. Re-check taxonomy/watchlist compatibility",
    "4. Resolve aligned source dates in requested range",
    "5. For each eligible selected date:",
    "   a. load ticker facts",
    "   b. load group signal facts",
    "   c. load synthetic OHLC facts",
    "   d. load group index facts",
    "   e. run coverage audit",
    "   f. run fact parity audit",
    "6. Optionally refresh pipeline watermark once at end",
    "7. Print summary",
)

WATERMARK_POLICY_NOTES = (
    "do not refresh ec_pipeline_watermark for every old date",
    "preferred first-write policy is to skip watermark during per-date historical loads",
    "acceptable alternative is one watermark refresh after the full backfill completes",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan a no-write ec_ historical source-layer backfill against an installed production-style SQLite DB")
    parser.add_argument("--db", required=True, help="Path to the SQLite database to inspect read-only")
    parser.add_argument("--ecosystem", required=True, help="Target ecosystem code, for example DATACENTER")
    parser.add_argument("--taxonomy-version", required=True, help="Expected taxonomy version code, for example DC_TAXONOMY_FULL_V1")
    parser.add_argument("--date-from", required=True, help="Inclusive start date in YYYY-MM-DD format")
    parser.add_argument("--date-to", required=True, help="Inclusive end date in YYYY-MM-DD format")
    parser.add_argument("--taxonomy-csv", required=True, help="Path to the source taxonomy CSV")
    parser.add_argument("--watchlist", required=True, help="Path to the source watchlist TXT")
    parser.add_argument("--allow-replace-existing", action="store_true", help="Allow planner to mark already loaded or partially loaded dates as replace-ready")
    parser.add_argument("--format", choices=("text",), default="text")
    return parser


def _parse_date_range(date_from_text: str, date_to_text: str) -> dict[str, object]:
    try:
        start_date = date.fromisoformat(date_from_text)
        end_date = date.fromisoformat(date_to_text)
    except ValueError:
        return {
            "status": "BLOCKED_INVALID_DATE_RANGE",
            "error": "date_from and date_to must parse as YYYY-MM-DD",
        }
    if start_date > end_date:
        return {
            "status": "BLOCKED_INVALID_DATE_RANGE",
            "error": "date_from must be less than or equal to date_to",
        }
    day_count = (end_date - start_date).days + 1
    if day_count > MAX_RANGE_DAYS:
        return {
            "status": "BLOCKED_INVALID_DATE_RANGE",
            "error": f"requested range exceeds max supported length of {MAX_RANGE_DAYS} calendar days",
        }
    return {
        "status": "OK",
        "date_from": start_date.isoformat(),
        "date_to": end_date.isoformat(),
        "day_count": day_count,
        "dates": [(start_date + timedelta(days=offset)).isoformat() for offset in range(day_count)],
    }


def _collect_schema_state(conn) -> dict[str, object]:
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
        "required_ec_missing": required_ec_missing,
        "eco_tables": eco_tables,
        "source_tables": source_tables,
        "ec_entity_alias_present": _table_exists(conn, "ec_entity_alias"),
    }


def _grouped_counts_by_date(conn, table_name: str, date_column: str, date_from: str, date_to: str) -> dict[str, int]:
    rows = conn.execute(
        f"""
        SELECT {date_column} AS fact_date, COUNT(*) AS row_count
        FROM {table_name}
        WHERE {date_column} >= ? AND {date_column} <= ?
        GROUP BY {date_column}
        ORDER BY {date_column}
        """,
        (date_from, date_to),
    ).fetchall()
    return {str(row["fact_date"]): int(row["row_count"]) for row in rows}


def _collect_source_date_availability(conn, date_range: dict[str, object]) -> dict[str, object]:
    dates = list(date_range["dates"])
    date_from = str(date_range["date_from"])
    date_to = str(date_range["date_to"])
    per_table_counts = {
        table_name: _grouped_counts_by_date(conn, table_name, date_column, date_from, date_to)
        for table_name, date_column in SOURCE_FACT_TABLES
    }
    watermark_present = _table_exists(conn, "dc_pipeline_watermark")
    watermark_row_count = int(_scalar(conn, "SELECT COUNT(*) FROM dc_pipeline_watermark") or 0) if watermark_present else 0

    per_date: list[dict[str, object]] = []
    aligned_dates: list[str] = []
    missing_source_dates: list[str] = []
    for fact_date in dates:
        ticker_count = per_table_counts["dc_ticker_swing_signal_daily"].get(fact_date, 0)
        group_signal_count = per_table_counts["dc_group_swing_signal_daily"].get(fact_date, 0)
        synthetic_ohlc_count = per_table_counts["dc_group_synthetic_ohlc_daily"].get(fact_date, 0)
        group_index_count = per_table_counts["dc_group_index_daily"].get(fact_date, 0)
        missing_tables = [
            table_name
            for table_name, row_count in (
                ("dc_ticker_swing_signal_daily", ticker_count),
                ("dc_group_swing_signal_daily", group_signal_count),
                ("dc_group_synthetic_ohlc_daily", synthetic_ohlc_count),
                ("dc_group_index_daily", group_index_count),
            )
            if row_count == 0
        ]
        aligned = not missing_tables
        if aligned:
            aligned_dates.append(fact_date)
        else:
            missing_source_dates.append(fact_date)
        per_date.append(
            {
                "date": fact_date,
                "ticker_source_row_count": ticker_count,
                "group_signal_source_row_count": group_signal_count,
                "synthetic_ohlc_source_row_count": synthetic_ohlc_count,
                "group_index_source_row_count": group_index_count,
                "aligned": aligned,
                "missing_source_tables": missing_tables,
            }
        )

    return {
        "watermark_present": watermark_present,
        "watermark_row_count": watermark_row_count,
        "per_date": per_date,
        "aligned_dates": aligned_dates,
        "missing_source_dates": missing_source_dates,
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


def _collect_loaded_watchlist_tickers(conn, ecosystem_code: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT DISTINCT UPPER(e.entity_code) AS ticker
        FROM ec_watchlist w
        JOIN ec_ecosystem eco ON eco.ecosystem_id = w.ecosystem_id
        JOIN ec_watchlist_member wm ON wm.watchlist_id = w.watchlist_id
        JOIN ec_entity e ON e.entity_id = wm.entity_id
        WHERE eco.ecosystem_code = ?
          AND e.entity_type = 'TICKER'
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


def _compare_universe_and_groups(conn, fact_date: str, taxonomy_version_id: int) -> dict[str, object]:
    source_tickers = set(
        _distinct_values(
            conn,
            "dc_ticker_swing_signal_daily",
            "ticker",
            "signal_date = ?",
            (fact_date,),
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
    ecosystem_aliases: set[str] = set()
    if _table_exists(conn, "ec_entity_alias"):
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
            (fact_date,),
        )
    )
    group_signal_subindustries = set(
        _distinct_values(
            conn,
            "dc_group_swing_signal_daily",
            "group_name",
            "signal_date = ? AND group_type = 'subindustry'",
            (fact_date,),
        )
    )
    group_signal_ecosystem = set(
        _distinct_values(
            conn,
            "dc_group_swing_signal_daily",
            "group_name",
            "signal_date = ? AND group_type = 'ecosystem'",
            (fact_date,),
        )
    )
    synth_layers = set(
        _distinct_values(
            conn,
            "dc_group_synthetic_ohlc_daily",
            "group_name",
            "ohlc_date = ? AND group_type = 'layer'",
            (fact_date,),
        )
    )
    synth_subindustries = set(
        _distinct_values(
            conn,
            "dc_group_synthetic_ohlc_daily",
            "group_name",
            "ohlc_date = ? AND group_type = 'subindustry'",
            (fact_date,),
        )
    )
    index_layers = set(
        _distinct_values(
            conn,
            "dc_group_index_daily",
            "group_name",
            "index_date = ? AND group_type = 'layer'",
            (fact_date,),
        )
    )
    index_subindustries = set(
        _distinct_values(
            conn,
            "dc_group_index_daily",
            "group_name",
            "index_date = ? AND group_type = 'subindustry'",
            (fact_date,),
        )
    )
    index_ecosystem = set(
        _distinct_values(
            conn,
            "dc_group_index_daily",
            "group_name",
            "index_date = ? AND group_type = 'ecosystem'",
            (fact_date,),
        )
    )

    missing_group_l1 = sorted((group_signal_layers | synth_layers | index_layers) - group_l1_names)
    missing_group_l2 = sorted((group_signal_subindustries | synth_subindustries | index_subindustries) - group_l2_names)
    missing_ecosystem_aliases = sorted((group_signal_ecosystem | index_ecosystem) - ecosystem_aliases)

    return {
        "date": fact_date,
        "dc_ticker_count": len(source_tickers),
        "ec_ticker_entity_count": len(ec_ticker_entities),
        "taxonomy_ticker_count": len(taxonomy_tickers),
        "dc_ticker_missing_in_ec_entity": missing_in_ec_entities,
        "dc_ticker_missing_primary_taxonomy_membership": missing_primary_membership,
        "missing_group_l1_entities": missing_group_l1,
        "missing_group_l2_entities": missing_group_l2,
        "missing_ecosystem_aliases": missing_ecosystem_aliases,
        "mapping_clear": not any(
            [
                missing_in_ec_entities,
                missing_primary_membership,
                missing_group_l1,
                missing_group_l2,
                missing_ecosystem_aliases,
            ]
        ),
    }


def _collect_loaded_ec_state(conn, aligned_dates: list[str], source_date_availability: dict[str, object], allow_replace_existing: bool) -> dict[str, object]:
    if not aligned_dates:
        return {
            "latest_loaded_fact_date": None,
            "latest_loaded_dates": {},
            "per_date": [],
            "missing_dates": [],
            "fully_loaded_dates": [],
            "partial_dates": [],
            "candidate_dates": [],
            "already_loaded_dates": [],
        }

    earliest_aligned_date = min(aligned_dates)
    latest_aligned_date = max(aligned_dates)
    ec_counts_by_table = {
        table_name: _grouped_counts_by_date(conn, table_name, date_column, earliest_aligned_date, latest_aligned_date)
        for table_name, date_column in EC_FACT_TABLES
    }
    latest_loaded_dates = {
        table_name: _scalar(conn, f"SELECT MAX({date_column}) FROM {table_name}")
        for table_name, date_column in EC_FACT_TABLES
    }
    latest_loaded_fact_date = max(
        [str(value) for value in latest_loaded_dates.values() if value is not None],
        default=None,
    )

    source_lookup = {
        str(entry["date"]): entry
        for entry in source_date_availability.get("per_date", [])
        if isinstance(entry, dict)
    }

    per_date: list[dict[str, object]] = []
    missing_dates: list[str] = []
    fully_loaded_dates: list[str] = []
    partial_dates: list[str] = []
    candidate_dates: list[dict[str, object]] = []
    already_loaded_dates: list[str] = []

    for fact_date in aligned_dates:
        source_entry = source_lookup[fact_date]
        source_counts = {
            "ec_ticker_signal_daily": int(source_entry["ticker_source_row_count"]),
            "ec_group_signal_daily": int(source_entry["group_signal_source_row_count"]),
            "ec_group_synthetic_ohlc_daily": int(source_entry["synthetic_ohlc_source_row_count"]),
            "ec_group_index_daily": int(source_entry["group_index_source_row_count"]),
        }
        ec_counts = {
            table_name: int(ec_counts_by_table[table_name].get(fact_date, 0))
            for table_name, _ in EC_FACT_TABLES
        }
        zero_ec_tables = [table_name for table_name, row_count in ec_counts.items() if row_count == 0]
        mismatched_tables = [
            table_name
            for table_name, row_count in ec_counts.items()
            if row_count != source_counts[table_name]
        ]

        if len(zero_ec_tables) == len(EC_FACT_TABLES):
            classification = "MISSING_IN_EC"
            missing_dates.append(fact_date)
            candidate_dates.append({"date": fact_date, "action": "BACKFILL_MISSING"})
        elif not mismatched_tables:
            classification = "FULLY_LOADED_IN_EC"
            fully_loaded_dates.append(fact_date)
            if allow_replace_existing:
                candidate_dates.append({"date": fact_date, "action": "REPLACE_EXISTING"})
            else:
                already_loaded_dates.append(fact_date)
        else:
            classification = "PARTIALLY_LOADED_IN_EC"
            partial_dates.append(fact_date)
            if allow_replace_existing:
                candidate_dates.append({"date": fact_date, "action": "REPLACE_PARTIAL"})

        per_date.append(
            {
                "date": fact_date,
                "classification": classification,
                "source_counts": source_counts,
                "ec_counts": ec_counts,
                "zero_ec_tables": zero_ec_tables,
                "count_mismatch_tables": mismatched_tables,
            }
        )

    return {
        "latest_loaded_fact_date": latest_loaded_fact_date,
        "latest_loaded_dates": {table_name: (str(value) if value is not None else None) for table_name, value in latest_loaded_dates.items()},
        "per_date": per_date,
        "missing_dates": missing_dates,
        "fully_loaded_dates": fully_loaded_dates,
        "partial_dates": partial_dates,
        "candidate_dates": candidate_dates,
        "already_loaded_dates": already_loaded_dates,
    }


def _aggregate_mapping_results(mapping_results: list[dict[str, object]]) -> dict[str, object]:
    failures = [result for result in mapping_results if not result["mapping_clear"]]
    return {
        "per_date": mapping_results,
        "blocking_dates": [str(result["date"]) for result in failures],
        "dc_ticker_missing_in_ec_entity": sorted(
            {ticker for result in failures for ticker in result["dc_ticker_missing_in_ec_entity"]}
        ),
        "dc_ticker_missing_primary_taxonomy_membership": sorted(
            {ticker for result in failures for ticker in result["dc_ticker_missing_primary_taxonomy_membership"]}
        ),
        "missing_group_l1_entities": sorted(
            {group_name for result in failures for group_name in result["missing_group_l1_entities"]}
        ),
        "missing_group_l2_entities": sorted(
            {group_name for result in failures for group_name in result["missing_group_l2_entities"]}
        ),
        "missing_ecosystem_aliases": sorted(
            {alias for result in failures for alias in result["missing_ecosystem_aliases"]}
        ),
        "mapping_clear": not failures,
    }


def _decide_plan_status(
    *,
    aligned_dates: list[str],
    loaded_state: dict[str, object],
    allow_replace_existing: bool,
) -> tuple[str, str | None]:
    if not aligned_dates:
        return (
            "BLOCKED_MISSING_SOURCE",
            "no dates in the requested range are aligned across all active dc_ source fact tables",
        )

    partial_dates = list(loaded_state.get("partial_dates", []))
    missing_dates = list(loaded_state.get("missing_dates", []))
    candidate_dates = list(loaded_state.get("candidate_dates", []))

    if partial_dates and not allow_replace_existing:
        return (
            "BLOCKED_PARTIAL_EXISTING_DATES_WITHOUT_REPLACE",
            "one or more aligned dates exist partially in ec_ facts and --allow-replace-existing was not supplied",
        )
    if missing_dates:
        return ("READY_BACKFILL_PLAN", None)
    if candidate_dates:
        return ("READY_BACKFILL_PLAN", None)
    return ("SKIP_ALL_DATES_ALREADY_LOADED", None)


def _build_future_command(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    date_from: str,
    date_to: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    allow_replace_existing: bool,
) -> str:
    command_parts = [
        "PYTHONPATH=. python3 -m rawcandle.cli.run_ec_source_layer_backfill",
        f"--db {db_path}",
        f"--ecosystem {ecosystem_code}",
        f"--taxonomy-version {taxonomy_version_code}",
        f"--date-from {date_from}",
        f"--date-to {date_to}",
        f"--taxonomy-csv {taxonomy_csv_path}",
        f"--watchlist {watchlist_path}",
        "--format text",
    ]
    if allow_replace_existing:
        command_parts.append("--allow-replace-existing")
    return " \\\n  ".join(command_parts)


def plan_ec_source_layer_backfill(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    date_from: str,
    date_to: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    allow_replace_existing: bool = False,
) -> dict[str, object]:
    date_range = _parse_date_range(date_from, date_to)
    if date_range["status"] != "OK":
        return {
            "status": "BLOCKED_INVALID_DATE_RANGE",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "date_range": date_range,
        }

    taxonomy_summary = _read_taxonomy_csv(taxonomy_csv_path, taxonomy_version_code)
    if taxonomy_summary["status"] != "OK":
        return {
            "status": "BLOCKED_TAXONOMY_SOURCE",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "date_range": date_range,
            "taxonomy_summary": taxonomy_summary,
        }

    watchlist_summary = _read_watchlist(watchlist_path)
    if watchlist_summary["status"] != "OK":
        return {
            "status": "BLOCKED_WATCHLIST_SOURCE",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "date_range": date_range,
            "taxonomy_summary": taxonomy_summary,
            "watchlist_summary": watchlist_summary,
        }

    with open_readonly_sqlite(db_path) as conn:
        schema_state = _collect_schema_state(conn)
        if schema_state["required_ec_missing"]:
            return {
                "status": "BLOCKED_EC_SCHEMA_MISSING",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "date_range": date_range,
                "schema_state": schema_state,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
            }

        source_readiness = {
            "tables": {
                table_name: {
                    "present": _table_exists(conn, table_name),
                    "date_column": date_column,
                    "row_count": int(_scalar(conn, f"SELECT COUNT(*) FROM {table_name}") or 0) if _table_exists(conn, table_name) else 0,
                }
                for table_name, date_column in REQUIRED_SOURCE_TABLES
            },
            "missing_tables": [table_name for table_name, _ in REQUIRED_SOURCE_TABLES if not _table_exists(conn, table_name)],
        }
        missing_tables = list(source_readiness["missing_tables"])
        if missing_tables:
            return {
                "status": "BLOCKED_MISSING_SOURCE",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "date_range": date_range,
                "schema_state": schema_state,
                "source_readiness": source_readiness,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
            }

        source_date_availability = _collect_source_date_availability(conn, date_range)
        compatibility_summary = _check_taxonomy_watchlist_compatibility(
            conn,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            taxonomy_summary=taxonomy_summary,
            watchlist_summary=watchlist_summary,
        )
        loaded_state = _collect_loaded_ec_state(
            conn,
            list(source_date_availability["aligned_dates"]),
            source_date_availability,
            allow_replace_existing,
        )
        if compatibility_summary["status"] != "OK":
            return {
                "status": compatibility_summary["status"],
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "date_range": date_range,
                "schema_state": schema_state,
                "source_readiness": source_readiness,
                "source_date_availability": source_date_availability,
                "loaded_state": loaded_state,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
                "compatibility_summary": compatibility_summary,
            }

        loaded_taxonomy = compatibility_summary["loaded_taxonomy"]
        assert isinstance(loaded_taxonomy, dict)
        taxonomy_version_id = int(loaded_taxonomy["taxonomy_version_id"])
        mapping_summary = _aggregate_mapping_results(
            [_compare_universe_and_groups(conn, fact_date, taxonomy_version_id) for fact_date in source_date_availability["aligned_dates"]]
        )
        if not mapping_summary["mapping_clear"]:
            return {
                "status": "BLOCKED_UNCLEAR_MAPPING",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "date_range": date_range,
                "schema_state": schema_state,
                "source_readiness": source_readiness,
                "source_date_availability": source_date_availability,
                "loaded_state": loaded_state,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
                "compatibility_summary": compatibility_summary,
                "mapping_summary": mapping_summary,
            }

    status, decision_error = _decide_plan_status(
        aligned_dates=list(source_date_availability["aligned_dates"]),
        loaded_state=loaded_state,
        allow_replace_existing=allow_replace_existing,
    )
    return {
        "status": status,
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_code": taxonomy_version_code,
        "allow_replace_existing": allow_replace_existing,
        "date_range": date_range,
        "schema_state": schema_state,
        "source_readiness": source_readiness,
        "source_date_availability": source_date_availability,
        "loaded_state": loaded_state,
        "taxonomy_summary": taxonomy_summary,
        "watchlist_summary": watchlist_summary,
        "compatibility_summary": compatibility_summary,
        "mapping_summary": mapping_summary,
        "planned_backfill_sequence": list(PLANNED_BACKFILL_SEQUENCE),
        "watermark_policy_notes": list(WATERMARK_POLICY_NOTES),
        "future_command": _build_future_command(
            db_path=db_path,
            ecosystem_code=ecosystem_code,
            taxonomy_version_code=taxonomy_version_code,
            date_from=str(date_range["date_from"]),
            date_to=str(date_range["date_to"]),
            taxonomy_csv_path=taxonomy_csv_path,
            watchlist_path=watchlist_path,
            allow_replace_existing=allow_replace_existing,
        ),
    } | ({"decision_error": decision_error} if decision_error else {})


def render_plan_text(summary: dict[str, object]) -> str:
    lines = [
        "EC Source Layer Backfill Plan",
        f"ecosystem_code={summary.get('ecosystem_code', '')}",
        f"taxonomy_version_code={summary.get('taxonomy_version_code', '')}",
        "mode=NO_WRITE_BACKFILL_PLAN",
    ]

    schema_state = summary.get("schema_state", {})
    if isinstance(schema_state, dict):
        lines.extend(
            [
                "",
                "Schema State",
                f"- true_ec_tables={schema_state.get('true_ec_tables', [])}",
                f"- required_ec_missing={schema_state.get('required_ec_missing', [])}",
                f"- eco_tables={schema_state.get('eco_tables', [])}",
                f"- ec_entity_alias_present={schema_state.get('ec_entity_alias_present')}",
            ]
        )

    date_range = summary.get("date_range", {})
    if isinstance(date_range, dict):
        lines.extend(
            [
                "",
                "Date Range",
                f"- date_from={date_range.get('date_from')}",
                f"- date_to={date_range.get('date_to')}",
                f"- day_count={date_range.get('day_count')}",
            ]
        )
        if date_range.get("error"):
            lines.append(f"- error={date_range.get('error')}")

    source_date_availability = summary.get("source_date_availability")
    if isinstance(source_date_availability, dict):
        lines.extend(
            [
                "",
                "Source Date Availability",
                f"- dc_pipeline_watermark_present={source_date_availability.get('watermark_present')}",
                f"- dc_pipeline_watermark_row_count={source_date_availability.get('watermark_row_count')}",
                f"- aligned_dates={source_date_availability.get('aligned_dates', [])}",
                f"- missing_source_dates={source_date_availability.get('missing_source_dates', [])}",
            ]
        )
        for entry in source_date_availability.get("per_date", []):
            if not isinstance(entry, dict):
                continue
            lines.append(
                "- "
                f"{entry.get('date')}: "
                f"ticker={entry.get('ticker_source_row_count')}, "
                f"group_signal={entry.get('group_signal_source_row_count')}, "
                f"synthetic_ohlc={entry.get('synthetic_ohlc_source_row_count')}, "
                f"group_index={entry.get('group_index_source_row_count')}, "
                f"aligned={entry.get('aligned')}, "
                f"missing_source_tables={entry.get('missing_source_tables')}"
            )

    loaded_state = summary.get("loaded_state")
    if isinstance(loaded_state, dict):
        lines.extend(
            [
                "",
                "Loaded EC State",
                f"- latest_loaded_fact_date={loaded_state.get('latest_loaded_fact_date')}",
                f"- latest_loaded_dates={loaded_state.get('latest_loaded_dates', {})}",
            ]
        )
        for entry in loaded_state.get("per_date", []):
            if not isinstance(entry, dict):
                continue
            lines.append(
                "- "
                f"{entry.get('date')}: "
                f"classification={entry.get('classification')}, "
                f"source_counts={entry.get('source_counts')}, "
                f"ec_counts={entry.get('ec_counts')}, "
                f"count_mismatch_tables={entry.get('count_mismatch_tables')}"
            )

    taxonomy_summary = summary.get("taxonomy_summary")
    watchlist_summary = summary.get("watchlist_summary")
    compatibility_summary = summary.get("compatibility_summary")
    lines.extend(["", "Taxonomy / Watchlist Compatibility"])
    if isinstance(taxonomy_summary, dict):
        if taxonomy_summary.get("status") == "OK":
            lines.extend(
                [
                    f"- taxonomy_path={taxonomy_summary.get('path')}",
                    f"- taxonomy_row_count={taxonomy_summary.get('row_count')}",
                    f"- taxonomy_distinct_ticker_count={taxonomy_summary.get('distinct_ticker_count')}",
                    f"- taxonomy_distinct_layer_count={taxonomy_summary.get('distinct_layer_count')}",
                    f"- taxonomy_distinct_subindustry_count={taxonomy_summary.get('distinct_subindustry_count')}",
                ]
            )
        else:
            lines.append(f"- taxonomy_error={taxonomy_summary.get('error')}")
    if isinstance(watchlist_summary, dict):
        if watchlist_summary.get("status") == "OK":
            lines.extend(
                [
                    f"- watchlist_path={watchlist_summary.get('path')}",
                    f"- watchlist_ticker_count={watchlist_summary.get('ticker_count')}",
                    f"- watchlist_contains_crgy={watchlist_summary.get('contains_crgy')}",
                ]
            )
        else:
            lines.append(f"- watchlist_error={watchlist_summary.get('error')}")
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
                f"- watchlist_missing_in_loaded={compatibility_summary.get('watchlist_missing_in_loaded')}",
                f"- watchlist_loaded_only={compatibility_summary.get('watchlist_loaded_only')}",
            ]
        )
        if compatibility_summary.get("error"):
            lines.append(f"- error={compatibility_summary.get('error')}")

    mapping_summary = summary.get("mapping_summary")
    if isinstance(mapping_summary, dict):
        lines.extend(
            [
                "",
                "Universe and Group Consistency",
                f"- blocking_dates={mapping_summary.get('blocking_dates', [])}",
                f"- dc_ticker_missing_in_ec_entity={mapping_summary.get('dc_ticker_missing_in_ec_entity', [])}",
                "- "
                f"dc_ticker_missing_primary_taxonomy_membership="
                f"{mapping_summary.get('dc_ticker_missing_primary_taxonomy_membership', [])}",
                f"- missing_group_l1_entities={mapping_summary.get('missing_group_l1_entities', [])}",
                f"- missing_group_l2_entities={mapping_summary.get('missing_group_l2_entities', [])}",
                f"- missing_ecosystem_aliases={mapping_summary.get('missing_ecosystem_aliases', [])}",
            ]
        )

    lines.extend(
        [
            "",
            "Backfill Candidate Dates",
            f"- candidate_dates={loaded_state.get('candidate_dates', []) if isinstance(loaded_state, dict) else []}",
            "",
            "Already Loaded Dates",
            f"- already_loaded_dates={loaded_state.get('already_loaded_dates', []) if isinstance(loaded_state, dict) else []}",
            "",
            "Partial Dates",
            f"- partial_dates={loaded_state.get('partial_dates', []) if isinstance(loaded_state, dict) else []}",
            "",
            "Planned Backfill Sequence",
        ]
    )
    if summary.get("status") in {"READY_BACKFILL_PLAN", "SKIP_ALL_DATES_ALREADY_LOADED"}:
        lines.extend(f"- {step}" for step in summary.get("planned_backfill_sequence", []))
        lines.extend(["", "Recommended Future Command", "```bash", str(summary.get("future_command", "")), "```"])
        lines.extend(["", "Watermark Policy Recommendation"])
        lines.extend(f"- {note}" for note in summary.get("watermark_policy_notes", []))
    else:
        lines.append("- blocked before historical write-capable backfill planning can proceed")

    lines.extend(["", "Plan Status", f"- status={summary.get('status')}"])
    if summary.get("decision_error"):
        lines.append(f"- decision_error={summary.get('decision_error')}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = plan_ec_source_layer_backfill(
        db_path=args.db,
        ecosystem_code=args.ecosystem,
        taxonomy_version_code=args.taxonomy_version,
        date_from=args.date_from,
        date_to=args.date_to,
        taxonomy_csv_path=args.taxonomy_csv,
        watchlist_path=args.watchlist,
        allow_replace_existing=args.allow_replace_existing,
    )
    sys.stdout.write(render_plan_text(summary) + "\n")
    return 0 if summary["status"] in SUCCESS_EXIT_STATUSES else 2


if __name__ == "__main__":
    raise SystemExit(main())
