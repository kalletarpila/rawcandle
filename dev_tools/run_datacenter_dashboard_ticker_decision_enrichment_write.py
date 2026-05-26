from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from dev_tools.datacenter_dashboard_enrichment_decision_adapter import (
    _is_valid_ticker,
    build_decisions_from_ticker_enrichment_rows,
)


TABLE_NAME = "dc_dashboard_ticker_enrichment_daily"
DECISION_FIELDS = (
    "action",
    "severity",
    "primary_reason",
    "pullback_validity",
    "entry_readiness",
    "candidate_priority",
    "candidate_priority_label",
    "horizons_present",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write Datacenter ticker decision enrichment fields into analysis.db."
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--mode", required=True, choices=("upsert", "replace-date"))
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    return parser


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


def _load_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
) -> list[dict[str, object]]:
    rows = conn.execute(
        f"""
        SELECT *
        FROM {TABLE_NAME}
        WHERE signal_date = ? AND taxonomy_version = ?
        ORDER BY ticker ASC
        """,
        (signal_date, taxonomy_version),
    ).fetchall()
    return [dict(row) for row in rows]


def _valid_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if _is_valid_ticker(row.get("ticker"))]


def _decision_payloads(decisions) -> list[tuple[str, tuple[object, ...]]]:
    payloads: list[tuple[str, tuple[object, ...]]] = []
    for decision in decisions.decisions:
        payloads.append(
            (
                decision.ticker,
                (
                    decision.action,
                    decision.severity,
                    decision.primary_reason,
                    decision.pullback_validity,
                    decision.entry_readiness,
                    decision.candidate_priority,
                    decision.candidate_priority_label,
                    ",".join(decision.horizons_present),
                    decision.ticker,
                ),
            )
        )
    return payloads


def _count_rows_with_existing_decision_fields(
    rows: list[dict[str, object]],
) -> int:
    count = 0
    for row in rows:
        if any(str(row.get(field) or "").strip() for field in DECISION_FIELDS):
            count += 1
    return count


def _emit_summary(name: str, value: object) -> None:
    print(f"SUMMARY datacenter_dashboard_ticker_decision_enrichment_write.{name}={value}")


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        signal_date = _normalize_signal_date(args.signal_date)
        taxonomy_version = _normalize_taxonomy_version(args.taxonomy_version)
        if args.limit is not None and args.limit <= 0:
            raise ValueError("--limit must be greater than 0 when provided")

        connector = _connect_read_only if args.dry_run else _connect_read_write
        with connector(args.analysis_db) as conn:
            if not _table_exists(conn, TABLE_NAME):
                raise ValueError(f"missing required source table: {TABLE_NAME}")

            source_rows = _load_rows(
                conn,
                signal_date=signal_date,
                taxonomy_version=taxonomy_version,
            )
            valid_rows_all = _valid_rows(source_rows)
            valid_rows = (
                valid_rows_all[: args.limit] if args.limit is not None else valid_rows_all
            )

            updated_rows = 0
            cleared_rows = 0
            warning: str | None = None

            if not source_rows:
                warning = "NO_TICKER_ENRICHMENT_ROWS_FOR_SELECTION"
                decisions_count = 0
                payloads: list[tuple[str, tuple[object, ...]]] = []
            else:
                decision_result = build_decisions_from_ticker_enrichment_rows(valid_rows)
                decisions_count = len(decision_result.decisions)
                payloads = _decision_payloads(decision_result)
                if decisions_count == 0:
                    warning = "NO_DECISIONS_PRODUCED"

            if args.mode == "replace-date":
                rows_to_clear = valid_rows if args.limit is None else valid_rows
                cleared_rows = _count_rows_with_existing_decision_fields(rows_to_clear)
                if not args.dry_run and rows_to_clear:
                    conn.execute(
                        f"""
                        UPDATE {TABLE_NAME}
                        SET action = NULL,
                            severity = NULL,
                            primary_reason = NULL,
                            pullback_validity = NULL,
                            entry_readiness = NULL,
                            candidate_priority = NULL,
                            candidate_priority_label = NULL,
                            horizons_present = NULL
                        WHERE signal_date = ? AND taxonomy_version = ?
                          AND ticker IN ({",".join("?" for _ in rows_to_clear)})
                        """,
                        (
                            signal_date,
                            taxonomy_version,
                            *[str(row["ticker"]).strip() for row in rows_to_clear],
                        ),
                    )

            updated_rows = decisions_count
            if not args.dry_run and payloads:
                conn.executemany(
                    f"""
                    UPDATE {TABLE_NAME}
                    SET action = ?,
                        severity = ?,
                        primary_reason = ?,
                        pullback_validity = ?,
                        entry_readiness = ?,
                        candidate_priority = ?,
                        candidate_priority_label = ?,
                        horizons_present = ?
                    WHERE signal_date = ? AND taxonomy_version = ?
                      AND ticker = ?
                    """,
                    [
                        (
                            action,
                            severity,
                            primary_reason,
                            pullback_validity,
                            entry_readiness,
                            candidate_priority,
                            candidate_priority_label,
                            horizons_present,
                            signal_date,
                            taxonomy_version,
                            ticker,
                        )
                        for ticker, (
                            action,
                            severity,
                            primary_reason,
                            pullback_validity,
                            entry_readiness,
                            candidate_priority,
                            candidate_priority_label,
                            horizons_present,
                            _,
                        ) in payloads
                    ],
                )

            if not args.dry_run:
                conn.commit()
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    except sqlite3.Error as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    _emit_summary("status", "OK")
    _emit_summary("analysis_db", args.analysis_db)
    _emit_summary("signal_date", signal_date)
    _emit_summary("taxonomy_version", taxonomy_version)
    _emit_summary("mode", args.mode)
    _emit_summary("dry_run", 1 if args.dry_run else 0)
    _emit_summary("source_rows", len(source_rows))
    _emit_summary("valid_ticker_rows", len(valid_rows))
    _emit_summary("decisions", decisions_count)
    _emit_summary("updated_rows", updated_rows)
    _emit_summary("cleared_rows", cleared_rows)
    _emit_summary("run_id", args.run_id or "")
    if warning:
        _emit_summary("warning", warning)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
