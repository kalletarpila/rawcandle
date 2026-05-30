from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from analysis.datacenter_indices.report_canonical_v2_daily_formatter_loader import (
    build_markdown_daily_canonical_v2_report,
    load_daily_canonical_formatter_data_v2,
)
from analysis.datacenter_indices.report_canonical_v2_orchestrator import (
    ALLOWED_HORIZONS,
    run_report_canonical_v2,
)
from analysis.datacenter_indices.report_canonical_v2_parity_audit import (
    audit_report_canonical_v2_parity,
)
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run temp-copy canonical daily Markdown smoke workflow."
    )
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--temp-db", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--market")
    parser.add_argument(
        "--horizons",
        default="daily,rolling2,rolling5,rolling30",
        help="Comma-separated list of horizons.",
    )
    parser.add_argument("--created-at-utc")
    parser.add_argument("--overwrite-temp", action="store_true")
    parser.add_argument("--overwrite-output", action="store_true")
    return parser


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"analysis_db not found: {db_path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _parse_horizons(parser: argparse.ArgumentParser, value: str) -> tuple[str, ...]:
    horizons = tuple(part.strip() for part in value.split(",") if part.strip())
    if not horizons:
        parser.error("--horizons must contain at least one allowed horizon")
    invalid = [horizon for horizon in horizons if horizon not in ALLOWED_HORIZONS]
    if invalid:
        parser.error(f"unsupported horizons: {', '.join(invalid)}")
    return tuple(dict.fromkeys(horizons))


def _validated_args(parser: argparse.ArgumentParser, argv: list[str] | None) -> argparse.Namespace:
    args = parser.parse_args(argv)
    if not str(args.signal_date).strip():
        parser.error("--signal-date must be non-empty")
    if not str(args.taxonomy_version).strip():
        parser.error("--taxonomy-version must be non-empty")
    if not str(args.run_id).strip():
        parser.error("--run-id must be non-empty")
    args.horizons = _parse_horizons(parser, str(args.horizons))
    if args.created_at_utc is None:
        args.created_at_utc = f"{args.signal_date}T00:00:00Z"
    return args


def _summary(key: str, value: object) -> None:
    print(f"SUMMARY {key}={value}")


def _text_cell(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _source_count(
    conn: sqlite3.Connection,
    *,
    table: str,
    date_column: str,
    signal_date: str,
    taxonomy_version: str,
    market: str | None,
) -> int:
    where_clauses = [f"{date_column} = ?", "taxonomy_version = ?"]
    params: list[object] = [signal_date, taxonomy_version]
    if market is not None:
        where_clauses.append("market = ?")
        params.append(market)
    row = conn.execute(
        f"SELECT COUNT(*) AS row_count FROM {table} WHERE {' AND '.join(where_clauses)}",
        tuple(params),
    ).fetchone()
    return int(row["row_count"])


def _prepare_temp_path(path: Path, *, overwrite: bool, label: str) -> None:
    if path.exists():
        if not overwrite:
            raise FileExistsError(f"{label} already exists: {path}")
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)


def _backup_source_to_temp(*, source_db: Path, temp_db: Path) -> None:
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as src:
        with sqlite3.connect(str(temp_db)) as dst:
            src.backup(dst)
            dst.commit()


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS row_count FROM {table}").fetchone()
    return int(row["row_count"])


def _write_markdown(path: Path, markdown: str) -> tuple[int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding="utf-8")
    line_count = markdown.count("\n")
    if markdown and not markdown.endswith("\n"):
        line_count += 1
    byte_count = len(markdown.encode("utf-8"))
    return line_count, byte_count


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = _validated_args(parser, argv)
    except SystemExit as exc:
        return int(exc.code)

    source_db = Path(str(args.source_db))
    temp_db = Path(str(args.temp_db))
    output_path = Path(str(args.output))

    try:
        with _connect_read_only(str(source_db)) as source_conn:
            source_ticker_rows = _source_count(
                source_conn,
                table="dc_ticker_swing_signal_daily",
                date_column="signal_date",
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
            )
            source_group_rows = _source_count(
                source_conn,
                table="dc_group_swing_signal_daily",
                date_column="signal_date",
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
            )
            source_synthetic_rows = _source_count(
                source_conn,
                table="dc_group_synthetic_ohlc_daily",
                date_column="ohlc_date",
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
            )
        _summary("source_ticker_rows", source_ticker_rows)
        _summary("source_group_rows", source_group_rows)
        _summary("source_synthetic_rows", source_synthetic_rows)
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if min(source_ticker_rows, source_group_rows, source_synthetic_rows) <= 0:
        print("required source data missing for signal-date/taxonomy-version", file=sys.stderr)
        return 1

    try:
        _prepare_temp_path(temp_db, overwrite=bool(args.overwrite_temp), label="temp_db")
        _prepare_temp_path(output_path, overwrite=bool(args.overwrite_output), label="output")
        _backup_source_to_temp(source_db=source_db, temp_db=temp_db)
        _summary("temp_db", temp_db)
        _summary("backup_status", "OK")

        with sqlite3.connect(str(temp_db)) as conn:
            apply_report_canonical_v2_migration(conn)
            conn.commit()
        _summary("migration_status", "OK")

        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            run_report_canonical_v2(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                run_id=str(args.run_id),
                market=args.market,
                horizons=args.horizons,
                created_at_utc=str(args.created_at_utc),
                notes="Temp-copy canonical V2 daily Markdown smoke run",
            )
            conn.commit()
            v2_run_rows = _table_count(conn, "dc_report_run_v2")
            v2_group_context_rows = _table_count(conn, "dc_report_context_group_v2")
            v2_daily_context_rows = _table_count(conn, "dc_report_context_daily_v2")
            v2_window_context_rows = _table_count(conn, "dc_report_context_window_v2")
            v2_classification_rows = _table_count(conn, "dc_report_classification_v2")
        _summary("v2_run_rows", v2_run_rows)
        _summary("v2_group_context_rows", v2_group_context_rows)
        _summary("v2_daily_context_rows", v2_daily_context_rows)
        _summary("v2_window_context_rows", v2_window_context_rows)
        _summary("v2_classification_rows", v2_classification_rows)

        if min(v2_run_rows, v2_group_context_rows, v2_daily_context_rows, v2_window_context_rows, v2_classification_rows) <= 0:
            print("required canonical V2 output tables are empty", file=sys.stderr)
            return 1

        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            parity_result = audit_report_canonical_v2_parity(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                horizons=args.horizons,
            )
        _summary("parity_status", _text_cell(parity_result["status"]))
        _summary("parity_mismatch_count", parity_result["mismatch_count"])
        _summary("parity_missing_current_count", parity_result["missing_current_count"])
        _summary("parity_missing_v2_count", parity_result["missing_v2_count"])
        _summary("parity_matched_count", parity_result["matched_count"])
        if str(parity_result["status"]) != "OK":
            for mismatch in list(parity_result["mismatches"])[:10]:
                print(
                    "MISMATCH "
                    f"horizon={_text_cell(mismatch['horizon'])} "
                    f"classification_type={_text_cell(mismatch['classification_type'])} "
                    f"ticker={_text_cell(mismatch['ticker'])} "
                    f"field={_text_cell(mismatch['field'])} "
                    f"current={_text_cell(mismatch['current_value'])} "
                    f"v2={_text_cell(mismatch['v2_value'])} "
                    f"reason={_text_cell(mismatch['reason'])}"
                )
            return 1

        with _connect_read_only(str(temp_db)) as conn:
            formatter_data = load_daily_canonical_formatter_data_v2(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                run_id=str(args.run_id),
            )
        markdown = build_markdown_daily_canonical_v2_report(formatter_data)
        line_count, byte_count = _write_markdown(output_path, markdown)
        if byte_count <= 0:
            print("markdown output is empty", file=sys.stderr)
            return 1
        _summary("output", output_path)
        _summary("markdown_status", "OK")
        _summary("markdown_line_count", line_count)
        _summary("markdown_byte_count", byte_count)
    except FileExistsError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
