from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from pathlib import Path


REQUIRED_TAXONOMY_COLUMNS = (
    "taxonomy_version",
    "ticker",
    "layer",
    "subindustry",
    "report_group_status",
    "is_primary",
    "role_weight",
    "notes",
)

REQUIRED_SOURCE_TABLES = (
    ("dc_ticker_swing_signal_daily", "signal_date"),
    ("dc_group_swing_signal_daily", "signal_date"),
    ("dc_group_synthetic_ohlc_daily", "ohlc_date"),
    ("dc_group_index_daily", "index_date"),
    ("dc_pipeline_watermark", None),
)

PLANNED_BUILD_SEQUENCE = (
    "1. Backup analysis.db",
    "2. Apply ec_ migrations",
    "3. Load taxonomy into ec_ sidecar tables",
    "4. Load watchlist into ec_ sidecar tables",
    "5. Load ec_ticker_signal_daily",
    "6. Load ec_group_signal_daily",
    "7. Load ec_group_synthetic_ohlc_daily",
    "8. Load ec_group_index_daily",
    "9. Load ec_pipeline_watermark",
    "10. Run ec coverage audit",
    "11. Run dc vs ec fact parity audit",
)

FUTURE_WRITE_GUARDRAILS = (
    "mandatory pre-write backup under temp/",
    "explicit --confirm-db path match",
    "explicit --confirm-ecosystem match",
    "explicit --confirm-taxonomy-version match",
    "planner must pass before any write mode",
    "stop on first loader failure",
    "do not alter dc_ or eco_ tables",
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan a no-write ec_ source-layer build against a production-style SQLite DB")
    parser.add_argument("--db", required=True, help="Path to the SQLite database to inspect read-only")
    parser.add_argument("--ecosystem", required=True, help="Target ecosystem code, for example DATACENTER")
    parser.add_argument("--taxonomy-version", required=True, help="Expected taxonomy version code, for example DC_TAXONOMY_FULL_V1")
    parser.add_argument("--taxonomy-csv", required=True, help="Path to the source taxonomy CSV")
    parser.add_argument("--watchlist", required=True, help="Path to the source watchlist TXT")
    parser.add_argument("--signal-date", help="Optional explicit signal date in YYYY-MM-DD format")
    parser.add_argument("--format", choices=("text",), default="text")
    return parser


def open_readonly_sqlite(db_path: str) -> sqlite3.Connection:
    resolved = Path(db_path).resolve()
    conn = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _glob_table_names(conn: sqlite3.Connection, pattern: str) -> list[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name GLOB ?
        ORDER BY name
        """,
        (pattern,),
    ).fetchall()
    return [str(row["name"]) for row in rows]


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _scalar(conn: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> object | None:
    row = conn.execute(query, params).fetchone()
    if row is None:
        return None
    return row[0]


def _distinct_values(
    conn: sqlite3.Connection,
    table_name: str,
    column_name: str,
    where_clause: str = "",
    params: tuple[object, ...] = (),
) -> list[str]:
    sql = f"SELECT DISTINCT {column_name} AS value FROM {table_name}"
    if where_clause:
        sql += f" WHERE {where_clause}"
    sql += " ORDER BY value"
    rows = conn.execute(sql, params).fetchall()
    return [str(row["value"]) for row in rows if row["value"] is not None]


def _read_taxonomy_csv(path: str, taxonomy_version_code: str) -> dict[str, object]:
    csv_path = Path(path)
    if not csv_path.exists():
        return {"status": "BLOCKED_TAXONOMY_SOURCE", "error": f"taxonomy file does not exist: {csv_path}"}
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [column for column in REQUIRED_TAXONOMY_COLUMNS if column not in fieldnames]
        if missing_columns:
            return {
                "status": "BLOCKED_TAXONOMY_SOURCE",
                "error": f"taxonomy file missing required columns: {', '.join(missing_columns)}",
            }

        rows = list(reader)
    if not rows:
        return {"status": "BLOCKED_TAXONOMY_SOURCE", "error": "taxonomy file has no data rows"}

    versions = sorted({str(row["taxonomy_version"]).strip() for row in rows if str(row["taxonomy_version"]).strip()})
    if versions != [taxonomy_version_code]:
        return {
            "status": "BLOCKED_TAXONOMY_SOURCE",
            "error": f"taxonomy_version values {versions!r} do not match requested {taxonomy_version_code!r}",
        }

    tickers = [str(row["ticker"]).strip().upper() for row in rows if str(row["ticker"]).strip()]
    layers = [str(row["layer"]).strip() for row in rows if str(row["layer"]).strip()]
    subindustries = [str(row["subindustry"]).strip() for row in rows if str(row["subindustry"]).strip()]
    primary_count = sum(1 for row in rows if str(row["is_primary"]).strip() in {"1", "true", "TRUE", "True"})

    return {
        "status": "OK",
        "path": str(csv_path.resolve()),
        "row_count": len(rows),
        "distinct_ticker_count": len(set(tickers)),
        "distinct_layer_count": len(set(layers)),
        "distinct_subindustry_count": len(set(subindustries)),
        "primary_membership_count": primary_count,
        "versions": versions,
        "columns_present": list(fieldnames),
        "tickers": sorted(set(tickers)),
        "layers": sorted(set(layers)),
        "subindustries": sorted(set(subindustries)),
    }


def _read_watchlist(path: str) -> dict[str, object]:
    watchlist_path = Path(path)
    if not watchlist_path.exists():
        return {"status": "BLOCKED_WATCHLIST_SOURCE", "error": f"watchlist file does not exist: {watchlist_path}"}

    tickers: list[str] = []
    seen: set[str] = set()
    for raw_line in watchlist_path.read_text(encoding="utf-8").splitlines():
        value = raw_line.strip()
        if not value or value.startswith("#"):
            continue
        ticker = value.upper()
        if ticker in seen:
            continue
        seen.add(ticker)
        tickers.append(ticker)

    if not tickers:
        return {"status": "BLOCKED_WATCHLIST_SOURCE", "error": "watchlist file has no valid tickers"}

    return {
        "status": "OK",
        "path": str(watchlist_path.resolve()),
        "ticker_count": len(tickers),
        "tickers": tickers,
        "contains_crgy": "CRGY" in seen,
    }


def _collect_schema_state(conn: sqlite3.Connection) -> dict[str, object]:
    true_ec_tables = _glob_table_names(conn, "ec_*")
    eco_tables = _glob_table_names(conn, "eco_*")
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
        "source_tables": source_tables,
    }


def _collect_source_readiness(conn: sqlite3.Connection) -> dict[str, object]:
    summary: dict[str, object] = {"tables": {}, "missing_tables": []}
    for table_name, date_column in REQUIRED_SOURCE_TABLES:
        entry: dict[str, object] = {"present": _table_exists(conn, table_name), "date_column": date_column}
        if not entry["present"]:
            cast_list = summary["missing_tables"]
            assert isinstance(cast_list, list)
            cast_list.append(table_name)
            summary["tables"][table_name] = entry
            continue
        row_count = int(_scalar(conn, f"SELECT COUNT(*) FROM {table_name}") or 0)
        entry["row_count"] = row_count
        if date_column:
            entry["latest_date"] = _scalar(conn, f"SELECT MAX({date_column}) FROM {table_name}")
        summary["tables"][table_name] = entry
    return summary


def _resolve_selected_signal_date(
    source_readiness: dict[str, object],
    requested_signal_date: str | None,
) -> dict[str, object]:
    tables = source_readiness["tables"]
    assert isinstance(tables, dict)

    dated_tables = {
        table_name: table_info
        for table_name, table_info in tables.items()
        if isinstance(table_info, dict) and table_info.get("date_column")
    }

    latest_dates = {
        table_name: str(table_info["latest_date"])
        for table_name, table_info in dated_tables.items()
        if table_info.get("latest_date")
    }

    if requested_signal_date:
        missing_at_requested = [
            table_name
            for table_name, table_info in dated_tables.items()
            if str(table_info.get("latest_date", "")) < requested_signal_date
        ]
        if missing_at_requested:
            return {
                "status": "BLOCKED_DATE_MISMATCH",
                "selected_signal_date": requested_signal_date,
                "latest_dates": latest_dates,
                "error": f"requested signal_date {requested_signal_date} is newer than source coverage for: {', '.join(missing_at_requested)}",
            }
        return {
            "status": "OK",
            "selected_signal_date": requested_signal_date,
            "latest_dates": latest_dates,
        }

    unique_latest_dates = sorted(set(latest_dates.values()))
    if len(unique_latest_dates) != 1:
        return {
            "status": "BLOCKED_DATE_MISMATCH",
            "selected_signal_date": None,
            "latest_dates": latest_dates,
            "error": f"latest source dates are not aligned: {latest_dates}",
        }
    return {
        "status": "OK",
        "selected_signal_date": unique_latest_dates[0] if unique_latest_dates else None,
        "latest_dates": latest_dates,
    }


def _compare_universe_and_groups(
    conn: sqlite3.Connection,
    selected_signal_date: str,
    taxonomy_summary: dict[str, object],
) -> dict[str, object]:
    source_tickers = set(
        _distinct_values(
            conn,
            "dc_ticker_swing_signal_daily",
            "ticker",
            "signal_date = ?",
            (selected_signal_date,),
        )
    )
    taxonomy_tickers = set(taxonomy_summary["tickers"])
    taxonomy_layers = set(taxonomy_summary["layers"])
    taxonomy_subindustries = set(taxonomy_summary["subindustries"])

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

    ticker_missing_in_taxonomy = sorted(source_tickers - taxonomy_tickers)
    taxonomy_only_tickers = sorted(taxonomy_tickers - source_tickers)
    layer_mismatches = sorted((group_signal_layers | synth_layers | index_layers) ^ taxonomy_layers)
    subindustry_mismatches = sorted((group_signal_subindustries | synth_subindustries | index_subindustries) ^ taxonomy_subindustries)

    return {
        "source_ticker_count": len(source_tickers),
        "taxonomy_ticker_count": len(taxonomy_tickers),
        "ticker_missing_in_taxonomy": ticker_missing_in_taxonomy,
        "taxonomy_only_tickers": taxonomy_only_tickers,
        "group_signal_layer_count": len(group_signal_layers),
        "group_signal_subindustry_count": len(group_signal_subindustries),
        "synthetic_layer_count": len(synth_layers),
        "synthetic_subindustry_count": len(synth_subindustries),
        "index_layer_count": len(index_layers),
        "index_subindustry_count": len(index_subindustries),
        "layer_mismatches": layer_mismatches,
        "subindustry_mismatches": subindustry_mismatches,
        "mapping_clear": not any(
            [
                ticker_missing_in_taxonomy,
                taxonomy_only_tickers,
                layer_mismatches,
                subindustry_mismatches,
            ]
        ),
    }


def plan_ec_source_layer_build(
    *,
    db_path: str,
    ecosystem_code: str,
    taxonomy_version_code: str,
    taxonomy_csv_path: str,
    watchlist_path: str,
    signal_date: str | None = None,
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
        schema_state = _collect_schema_state(conn)
        source_readiness = _collect_source_readiness(conn)

        if schema_state["true_ec_tables"]:
            return {
                "status": "BLOCKED_EXISTING_EC_SCHEMA",
                "ecosystem_code": ecosystem_code,
                "taxonomy_version_code": taxonomy_version_code,
                "schema_state": schema_state,
                "source_readiness": source_readiness,
                "taxonomy_summary": taxonomy_summary,
                "watchlist_summary": watchlist_summary,
            }

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
        mapping_summary = _compare_universe_and_groups(conn, selected_signal_date, taxonomy_summary)

    if not mapping_summary["mapping_clear"]:
        return {
            "status": "BLOCKED_UNCLEAR_MAPPING",
            "ecosystem_code": ecosystem_code,
            "taxonomy_version_code": taxonomy_version_code,
            "schema_state": schema_state,
            "source_readiness": source_readiness,
            "selected_date_info": selected_date_info,
            "taxonomy_summary": taxonomy_summary,
            "watchlist_summary": watchlist_summary,
            "mapping_summary": mapping_summary,
        }

    return {
        "status": "READY_NO_WRITE_PLAN",
        "ecosystem_code": ecosystem_code,
        "taxonomy_version_code": taxonomy_version_code,
        "schema_state": schema_state,
        "source_readiness": source_readiness,
        "selected_date_info": selected_date_info,
        "taxonomy_summary": taxonomy_summary,
        "watchlist_summary": watchlist_summary,
        "mapping_summary": mapping_summary,
        "planned_build_sequence": list(PLANNED_BUILD_SEQUENCE),
        "future_write_guardrails": list(FUTURE_WRITE_GUARDRAILS),
    }


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
        if latest_date is None:
            lines.append(f"- {table_name}: present, row_count={row_count}")
        else:
            lines.append(f"- {table_name}: present, row_count={row_count}, latest_date={latest_date}")
    return lines


def render_plan_text(summary: dict[str, object]) -> str:
    lines = [
        f"plan_status={summary['status']}",
        f"ecosystem_code={summary.get('ecosystem_code', '')}",
        f"taxonomy_version_code={summary.get('taxonomy_version_code', '')}",
        "mode=NO_WRITE",
    ]

    schema_state = summary.get("schema_state")
    if isinstance(schema_state, dict):
        lines.extend(
            [
                "",
                "Schema state:",
                f"- true_ec_tables={schema_state.get('true_ec_tables', [])}",
                f"- eco_tables={schema_state.get('eco_tables', [])}",
            ]
        )

    source_readiness = summary.get("source_readiness")
    if isinstance(source_readiness, dict):
        lines.extend(["", "Source readiness:"])
        lines.extend(_render_source_table_lines(source_readiness))

    selected_date_info = summary.get("selected_date_info")
    if isinstance(selected_date_info, dict):
        lines.extend(
            [
                "",
                "Date alignment:",
                f"- selected_signal_date={selected_date_info.get('selected_signal_date')}",
                f"- latest_dates={selected_date_info.get('latest_dates', {})}",
            ]
        )
        error = selected_date_info.get("error")
        if error:
            lines.append(f"- error={error}")

    taxonomy_summary = summary.get("taxonomy_summary")
    if isinstance(taxonomy_summary, dict):
        lines.extend(["", "Taxonomy readiness:"])
        if taxonomy_summary.get("status") == "OK":
            lines.extend(
                [
                    f"- path={taxonomy_summary.get('path')}",
                    f"- row_count={taxonomy_summary.get('row_count')}",
                    f"- distinct_ticker_count={taxonomy_summary.get('distinct_ticker_count')}",
                    f"- distinct_layer_count={taxonomy_summary.get('distinct_layer_count')}",
                    f"- distinct_subindustry_count={taxonomy_summary.get('distinct_subindustry_count')}",
                ]
            )
        else:
            lines.append(f"- error={taxonomy_summary.get('error')}")

    watchlist_summary = summary.get("watchlist_summary")
    if isinstance(watchlist_summary, dict):
        lines.extend(["", "Watchlist readiness:"])
        if watchlist_summary.get("status") == "OK":
            lines.extend(
                [
                    f"- path={watchlist_summary.get('path')}",
                    f"- ticker_count={watchlist_summary.get('ticker_count')}",
                    f"- contains_crgy={watchlist_summary.get('contains_crgy')}",
                ]
            )
        else:
            lines.append(f"- error={watchlist_summary.get('error')}")

    mapping_summary = summary.get("mapping_summary")
    if isinstance(mapping_summary, dict):
        lines.extend(
            [
                "",
                "Universe and group consistency:",
                f"- source_ticker_count={mapping_summary.get('source_ticker_count')}",
                f"- taxonomy_ticker_count={mapping_summary.get('taxonomy_ticker_count')}",
                f"- ticker_missing_in_taxonomy={mapping_summary.get('ticker_missing_in_taxonomy')}",
                f"- taxonomy_only_tickers={mapping_summary.get('taxonomy_only_tickers')}",
                f"- layer_mismatches={mapping_summary.get('layer_mismatches')}",
                f"- subindustry_mismatches={mapping_summary.get('subindustry_mismatches')}",
            ]
        )

    if summary["status"] == "READY_NO_WRITE_PLAN":
        lines.extend(["", "Planned build sequence:"])
        lines.extend(f"- {step}" for step in PLANNED_BUILD_SEQUENCE)
        lines.extend(["", "Future write guardrails:"])
        lines.extend(f"- {guardrail}" for guardrail in FUTURE_WRITE_GUARDRAILS)
    else:
        lines.extend(
            [
                "",
                "Planned build sequence:",
                "- blocked before write-capable build planning can proceed",
            ]
        )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = plan_ec_source_layer_build(
        db_path=args.db,
        ecosystem_code=args.ecosystem,
        taxonomy_version_code=args.taxonomy_version,
        taxonomy_csv_path=args.taxonomy_csv,
        watchlist_path=args.watchlist,
        signal_date=args.signal_date,
    )
    sys.stdout.write(render_plan_text(summary) + "\n")
    return 0 if summary["status"] == "READY_NO_WRITE_PLAN" else 2


if __name__ == "__main__":
    raise SystemExit(main())
