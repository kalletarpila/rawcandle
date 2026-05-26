from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


SOURCE_TABLE = "dc_dashboard_ticker_enrichment_daily"
DESTINATION_TABLE = "dc_dashboard_decision_trace_daily"
CALC_VERSION = "DATACENTER_DASHBOARD_DECISION_TRACE_ENRICHMENT_V1"
TRACE_FIELDS: tuple[tuple[str, str | None], ...] = (
    ("action", None),
    ("severity", None),
    ("primary_reason", None),
    ("current_status", None),
    ("pullback_validity", None),
    ("entry_readiness", None),
    ("candidate_priority", None),
    ("candidate_priority_label", None),
    ("daily_status", "daily"),
    ("rolling_2d_status", "rolling_2d"),
    ("rolling_5d_status", "rolling_5d"),
    ("rolling_30d_status", "rolling_30d"),
    ("horizons_present", None),
    ("trend_state", None),
    ("latest_structure_label", None),
    ("latest_bos_event_type", None),
    ("latest_reset_reason", None),
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write Datacenter decision trace rows into analysis.db."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument(
        "--mode",
        required=True,
        choices=("insert-missing", "upsert", "replace-date"),
    )
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_run_id(signal_date: str, explicit_run_id: str | None) -> str:
    if explicit_run_id:
        return explicit_run_id
    return f"DC_DASH_DECISION_TRACE_{signal_date}_{_utc_now_text()}"


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    normalized = db_path.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    if not Path(normalized).exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    conn = sqlite3.connect(f"file:{normalized}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _connect_read_write(db_path: str) -> sqlite3.Connection:
    normalized = db_path.strip()
    if not normalized:
        raise FileNotFoundError("analysis_db path is required")
    if not Path(normalized).exists():
        raise FileNotFoundError(f"analysis_db not found: {normalized}")
    conn = sqlite3.connect(normalized)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = ?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _normalize_signal_date(value: str) -> str:
    normalized = value.strip()
    parts = normalized.split("-")
    if len(parts) != 3 or any(not part.isdigit() for part in parts):
        raise ValueError(f"invalid signal_date format: {normalized}")
    if len(parts[0]) != 4 or len(parts[1]) != 2 or len(parts[2]) != 2:
        raise ValueError(f"invalid signal_date format: {normalized}")
    return normalized


def _normalize_taxonomy_version(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("taxonomy_version must be non-empty")
    return normalized


def _load_source_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            f"""
            SELECT
                signal_date,
                taxonomy_version,
                ticker,
                action,
                severity,
                primary_reason,
                current_status,
                pullback_validity,
                entry_readiness,
                candidate_priority,
                candidate_priority_label,
                daily_status,
                rolling_2d_status,
                rolling_5d_status,
                rolling_30d_status,
                horizons_present,
                trend_state,
                latest_structure_label,
                latest_bos_event_type,
                latest_reset_reason
            FROM {SOURCE_TABLE}
            WHERE signal_date = ? AND taxonomy_version = ?
            ORDER BY ticker ASC
            """,
            (signal_date, taxonomy_version),
        ).fetchall()
    )


def _normalized_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _eligible_rows(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
    return [row for row in rows if _normalized_text(row["action"]) is not None]


def _expand_trace_rows(
    rows: list[sqlite3.Row],
    *,
    run_id: str,
    created_at_utc: str,
) -> list[tuple[tuple[str, str, str, int], tuple[object, ...]]]:
    expanded: list[tuple[tuple[str, str, str, int], tuple[object, ...]]] = []
    for row in rows:
        ticker = str(row["ticker"]).strip()
        action = _normalized_text(row["action"])
        assert action is not None
        trace_index = 1
        for field_name, horizon in TRACE_FIELDS:
            field_value = _normalized_text(row[field_name])
            if field_value is None:
                continue
            key = (
                str(row["signal_date"]),
                str(row["taxonomy_version"]),
                ticker,
                trace_index,
            )
            values = (
                row["signal_date"],
                row["taxonomy_version"],
                ticker,
                trace_index,
                action,
                "ENRICHMENT_FIELD_PRESENT",
                field_name,
                field_value,
                horizon,
                field_name,
                CALC_VERSION,
                run_id,
                created_at_utc,
            )
            expanded.append((key, values))
            trace_index += 1
    return expanded


def _existing_keys(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
) -> set[tuple[str, str, str, int]]:
    rows = conn.execute(
        f"""
        SELECT signal_date, taxonomy_version, ticker, trace_index
        FROM {DESTINATION_TABLE}
        WHERE signal_date = ? AND taxonomy_version = ?
        """,
        (signal_date, taxonomy_version),
    ).fetchall()
    return {
        (
            str(row["signal_date"]),
            str(row["taxonomy_version"]),
            str(row["ticker"]),
            int(row["trace_index"]),
        )
        for row in rows
    }


def _emit_summary(name: str, value: object) -> None:
    print(f"SUMMARY datacenter_dashboard_decision_trace_write.{name}={value}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        signal_date = _normalize_signal_date(args.signal_date)
        taxonomy_version = _normalize_taxonomy_version(args.taxonomy_version)
        if args.limit is not None and args.limit <= 0:
            raise ValueError("--limit must be greater than 0 when provided")

        connector = _connect_read_only if args.dry_run else _connect_read_write
        with connector(args.analysis_db) as conn:
            if not _table_exists(conn, SOURCE_TABLE):
                raise ValueError(f"missing required source table: {SOURCE_TABLE}")
            if not _table_exists(conn, DESTINATION_TABLE):
                raise ValueError(f"missing required destination table: {DESTINATION_TABLE}")

            source_rows = _load_source_rows(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
            eligible_rows_all = _eligible_rows(source_rows)
            eligible_rows = (
                eligible_rows_all[: args.limit] if args.limit is not None else eligible_rows_all
            )

            run_id = _resolve_run_id(signal_date, args.run_id)
            created_at_utc = _utc_now_text()
            row_specs = _expand_trace_rows(
                eligible_rows,
                run_id=run_id,
                created_at_utc=created_at_utc,
            )
            existing_keys = _existing_keys(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
            selected_keys = {item[0] for item in row_specs}

            inserted_rows = 0
            updated_rows = 0
            deleted_existing_rows = 0
            skipped_existing_rows = 0

            if args.mode == "insert-missing":
                inserted_rows = sum(1 for key in selected_keys if key not in existing_keys)
                skipped_existing_rows = sum(1 for key in selected_keys if key in existing_keys)
                rows_to_write = [values for key, values in row_specs if key not in existing_keys]
                if not args.dry_run and rows_to_write:
                    conn.executemany(
                        f"""
                        INSERT INTO {DESTINATION_TABLE} (
                            signal_date,
                            taxonomy_version,
                            ticker,
                            trace_index,
                            action,
                            matched_rule,
                            matched_token,
                            matched_value,
                            horizon,
                            field,
                            calc_version,
                            run_id,
                            created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rows_to_write,
                    )
            elif args.mode == "upsert":
                inserted_rows = sum(1 for key in selected_keys if key not in existing_keys)
                updated_rows = sum(1 for key in selected_keys if key in existing_keys)
                if not args.dry_run and row_specs:
                    conn.executemany(
                        f"""
                        INSERT INTO {DESTINATION_TABLE} (
                            signal_date,
                            taxonomy_version,
                            ticker,
                            trace_index,
                            action,
                            matched_rule,
                            matched_token,
                            matched_value,
                            horizon,
                            field,
                            calc_version,
                            run_id,
                            created_at_utc
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(signal_date, taxonomy_version, ticker, trace_index) DO UPDATE SET
                            action=excluded.action,
                            matched_rule=excluded.matched_rule,
                            matched_token=excluded.matched_token,
                            matched_value=excluded.matched_value,
                            horizon=excluded.horizon,
                            field=excluded.field,
                            calc_version=excluded.calc_version,
                            run_id=excluded.run_id,
                            created_at_utc=excluded.created_at_utc
                        """,
                        [values for _, values in row_specs],
                    )
            else:
                deleted_existing_rows = len(existing_keys)
                inserted_rows = len(row_specs)
                if not args.dry_run:
                    conn.execute(
                        f"""
                        DELETE FROM {DESTINATION_TABLE}
                        WHERE signal_date = ? AND taxonomy_version = ?
                        """,
                        (signal_date, taxonomy_version),
                    )
                    if row_specs:
                        conn.executemany(
                            f"""
                            INSERT INTO {DESTINATION_TABLE} (
                                signal_date,
                                taxonomy_version,
                                ticker,
                                trace_index,
                                action,
                                matched_rule,
                                matched_token,
                                matched_value,
                                horizon,
                                field,
                                calc_version,
                                run_id,
                                created_at_utc
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            [values for _, values in row_specs],
                        )

            if not args.dry_run:
                conn.commit()

            _emit_summary("status", "OK")
            _emit_summary("analysis_db", args.analysis_db)
            _emit_summary("signal_date", signal_date)
            _emit_summary("taxonomy_version", taxonomy_version)
            _emit_summary("mode", args.mode)
            _emit_summary("dry_run", 1 if args.dry_run else 0)
            _emit_summary("source_rows", len(source_rows))
            _emit_summary("eligible_ticker_rows", len(eligible_rows))
            _emit_summary("trace_rows", len(row_specs))
            _emit_summary("inserted_rows", inserted_rows)
            _emit_summary("updated_rows", updated_rows)
            _emit_summary("deleted_existing_rows", deleted_existing_rows)
            _emit_summary("skipped_existing_rows", skipped_existing_rows)
            _emit_summary("run_id", run_id)
            if not source_rows:
                _emit_summary("warning", "NO_TICKER_ENRICHMENT_ROWS_FOR_SELECTION")
            elif not eligible_rows_all:
                _emit_summary("warning", "NO_ACTION_VALUES_FOR_SELECTION")
            return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
