from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from analysis.datacenter_indices.report_canonical_v2_daily_formatter_loader import (
    build_csv_daily_canonical_v2_report,
    build_markdown_daily_canonical_v2_report,
    load_daily_canonical_formatter_data_v2,
)
from analysis.datacenter_indices.report_canonical_v2_orchestrator import run_report_canonical_v2
from analysis.datacenter_indices.report_canonical_v2_parity_audit import (
    audit_report_canonical_v2_parity,
)
from analysis.datacenter_indices.report_canonical_v2_rolling2_formatter_loader import (
    build_csv_rolling2_canonical_v2_report,
    build_markdown_rolling2_canonical_v2_report,
    load_rolling2_canonical_formatter_data_v2,
)
from analysis.datacenter_indices.report_canonical_v2_rolling30_formatter_loader import (
    build_csv_rolling30_canonical_v2_report,
    build_markdown_rolling30_canonical_v2_report,
    load_rolling30_canonical_formatter_data_v2,
)
from analysis.datacenter_indices.report_canonical_v2_rolling5_formatter_loader import (
    build_csv_rolling5_canonical_v2_report,
    build_markdown_rolling5_canonical_v2_report,
    load_rolling5_canonical_formatter_data_v2,
)
from rawcandle.report_canonical_v2_migration import apply_report_canonical_v2_migration


HORIZONS = ("daily", "rolling2", "rolling5", "rolling30")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run explicit temp-copy canonical V2 smoke and emit all canonical outputs."
    )
    parser.add_argument("--source-db", required=True)
    parser.add_argument("--temp-db", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--market")
    parser.add_argument("--created-at-utc")
    parser.add_argument("--overwrite-temp", action="store_true")
    parser.add_argument("--overwrite-output", action="store_true")
    parser.add_argument("--summary-output")
    return parser


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"analysis_db not found: {db_path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _validated_args(parser: argparse.ArgumentParser, argv: list[str] | None) -> argparse.Namespace:
    args = parser.parse_args(argv)
    if not str(args.signal_date).strip():
        parser.error("--signal-date must be non-empty")
    if not str(args.taxonomy_version).strip():
        parser.error("--taxonomy-version must be non-empty")
    if not str(args.run_id).strip():
        parser.error("--run-id must be non-empty")
    if args.created_at_utc is None:
        args.created_at_utc = f"{args.signal_date}T00:00:00Z"
    return args


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


def _prepare_temp_path(path: Path, *, overwrite: bool) -> None:
    if path.exists():
        if not overwrite:
            raise FileExistsError(f"temp_db already exists: {path}")
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)


def _prepare_output_paths(paths: list[Path], *, overwrite: bool) -> None:
    for path in paths:
        if path.exists() and not overwrite:
            raise FileExistsError(f"output already exists: {path}")
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)


def _backup_source_to_temp(*, source_db: Path, temp_db: Path) -> None:
    with sqlite3.connect(f"file:{source_db}?mode=ro", uri=True) as src:
        with sqlite3.connect(str(temp_db)) as dst:
            src.backup(dst)
            dst.commit()


def _table_count(conn: sqlite3.Connection, table: str) -> int:
    row = conn.execute(f"SELECT COUNT(*) AS row_count FROM {table}").fetchone()
    return int(row["row_count"])


def _line_count(text: str) -> int:
    count = text.count("\n")
    if text and not text.endswith("\n"):
        count += 1
    return count


def _write_text(path: Path, text: str) -> tuple[int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return _line_count(text), len(text.encode("utf-8"))


def _emit_summary(lines: list[str], *, key: str, value: object) -> None:
    lines.append(f"SUMMARY {key}={_text_cell(value)}")


def _output_paths(output_dir: Path, signal_date: str) -> dict[str, Path]:
    return {
        "daily_markdown": output_dir / f"datacenter_daily_canonical_v2_{signal_date}.md",
        "daily_csv": output_dir / f"datacenter_daily_canonical_v2_{signal_date}.csv",
        "rolling2_markdown": output_dir / f"datacenter_rolling2_canonical_v2_{signal_date}.md",
        "rolling2_csv": output_dir / f"datacenter_rolling2_canonical_v2_{signal_date}.csv",
        "rolling5_markdown": output_dir / f"datacenter_rolling5_canonical_v2_{signal_date}.md",
        "rolling5_csv": output_dir / f"datacenter_rolling5_canonical_v2_{signal_date}.csv",
        "rolling30_markdown": output_dir / f"datacenter_rolling30_canonical_v2_{signal_date}.md",
        "rolling30_csv": output_dir / f"datacenter_rolling30_canonical_v2_{signal_date}.csv",
    }


def _write_summary_output(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = _validated_args(parser, argv)
    except SystemExit as exc:
        return int(exc.code)

    source_db = Path(str(args.source_db))
    temp_db = Path(str(args.temp_db))
    output_dir = Path(str(args.output_dir))
    summary_output = None if args.summary_output is None else Path(str(args.summary_output))
    output_paths = _output_paths(output_dir, str(args.signal_date))
    summary_lines: list[str] = []

    _emit_summary(summary_lines, key="source_db", value=source_db)
    _emit_summary(summary_lines, key="temp_db", value=temp_db)
    _emit_summary(summary_lines, key="output_dir", value=output_dir)
    _emit_summary(summary_lines, key="signal_date", value=args.signal_date)
    _emit_summary(summary_lines, key="taxonomy_version", value=args.taxonomy_version)
    _emit_summary(summary_lines, key="run_id", value=args.run_id)
    _emit_summary(summary_lines, key="market", value=args.market or "")

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
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    _emit_summary(summary_lines, key="source_ticker_rows", value=source_ticker_rows)
    _emit_summary(summary_lines, key="source_group_rows", value=source_group_rows)
    _emit_summary(summary_lines, key="source_synthetic_rows", value=source_synthetic_rows)

    if min(source_ticker_rows, source_group_rows, source_synthetic_rows) <= 0:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(summary_output, summary_lines)
        print("required source data missing for signal-date/taxonomy-version", file=sys.stderr)
        return 1

    try:
        _prepare_temp_path(temp_db, overwrite=bool(args.overwrite_temp))
        protected_outputs = list(output_paths.values())
        if summary_output is not None:
            protected_outputs.append(summary_output)
        _prepare_output_paths(protected_outputs, overwrite=bool(args.overwrite_output))
        _backup_source_to_temp(source_db=source_db, temp_db=temp_db)
    except FileExistsError as exc:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(summary_output, summary_lines)
        print(str(exc), file=sys.stderr)
        return 1
    except sqlite3.Error as exc:
        print(str(exc), file=sys.stderr)
        return 2

    _emit_summary(summary_lines, key="backup_status", value="OK")

    try:
        with sqlite3.connect(str(temp_db)) as conn:
            apply_report_canonical_v2_migration(conn)
            conn.commit()
    except sqlite3.Error as exc:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(summary_output, summary_lines)
        print(str(exc), file=sys.stderr)
        return 1

    _emit_summary(summary_lines, key="migration_status", value="OK")

    try:
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            orchestration = run_report_canonical_v2(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                run_id=str(args.run_id),
                market=args.market,
                horizons=HORIZONS,
                created_at_utc=str(args.created_at_utc),
                notes="Temp-copy canonical V2 all-output smoke run",
            )
            conn.commit()
            v2_run_rows = _table_count(conn, "dc_report_run_v2")
            v2_group_context_rows = _table_count(conn, "dc_report_context_group_v2")
            v2_daily_context_rows = _table_count(conn, "dc_report_context_daily_v2")
            v2_window_context_rows = _table_count(conn, "dc_report_context_window_v2")
            v2_classification_rows = _table_count(conn, "dc_report_classification_v2")
    except (sqlite3.Error, ValueError) as exc:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(summary_output, summary_lines)
        print(str(exc), file=sys.stderr)
        return 1

    _emit_summary(summary_lines, key="orchestrator_status", value=orchestration.get("status", ""))
    _emit_summary(summary_lines, key="v2_run_rows", value=v2_run_rows)
    _emit_summary(summary_lines, key="v2_group_context_rows", value=v2_group_context_rows)
    _emit_summary(summary_lines, key="v2_daily_context_rows", value=v2_daily_context_rows)
    _emit_summary(summary_lines, key="v2_window_context_rows", value=v2_window_context_rows)
    _emit_summary(summary_lines, key="v2_classification_rows", value=v2_classification_rows)

    try:
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            parity = audit_report_canonical_v2_parity(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                horizons=HORIZONS,
            )
    except (sqlite3.Error, ValueError) as exc:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(summary_output, summary_lines)
        print(str(exc), file=sys.stderr)
        return 1

    _emit_summary(summary_lines, key="parity_status", value=parity.get("status", ""))
    _emit_summary(summary_lines, key="parity_mismatch_count", value=parity.get("mismatch_count", ""))
    for mismatch in list(parity.get("mismatches") or [])[:10]:
        summary_lines.append(
            "MISMATCH "
            f"horizon={_text_cell(mismatch.get('horizon'))} "
            f"classification_type={_text_cell(mismatch.get('classification_type'))} "
            f"ticker={_text_cell(mismatch.get('ticker'))} "
            f"field={_text_cell(mismatch.get('field'))} "
            f"current={_text_cell(mismatch.get('current_value'))} "
            f"v2={_text_cell(mismatch.get('v2_value'))} "
            f"reason={_text_cell(mismatch.get('reason'))}"
        )

    if str(parity.get("status")) != "OK":
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(summary_output, summary_lines)
        return 1

    try:
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row

            daily_data = load_daily_canonical_formatter_data_v2(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                run_id=args.run_id,
            )
            rolling2_data = load_rolling2_canonical_formatter_data_v2(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                run_id=args.run_id,
            )
            rolling5_data = load_rolling5_canonical_formatter_data_v2(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                run_id=args.run_id,
            )
            rolling30_data = load_rolling30_canonical_formatter_data_v2(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                run_id=args.run_id,
            )
    except (sqlite3.Error, ValueError) as exc:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(summary_output, summary_lines)
        print(str(exc), file=sys.stderr)
        return 1

    rendered_outputs = {
        "daily_markdown": build_markdown_daily_canonical_v2_report(daily_data),
        "daily_csv": build_csv_daily_canonical_v2_report(daily_data),
        "rolling2_markdown": build_markdown_rolling2_canonical_v2_report(rolling2_data),
        "rolling2_csv": build_csv_rolling2_canonical_v2_report(rolling2_data),
        "rolling5_markdown": build_markdown_rolling5_canonical_v2_report(rolling5_data),
        "rolling5_csv": build_csv_rolling5_canonical_v2_report(rolling5_data),
        "rolling30_markdown": build_markdown_rolling30_canonical_v2_report(rolling30_data),
        "rolling30_csv": build_csv_rolling30_canonical_v2_report(rolling30_data),
    }

    try:
        for key, text in rendered_outputs.items():
            line_count, byte_count = _write_text(output_paths[key], text)
            if not output_paths[key].exists() or line_count <= 0 or byte_count <= 0:
                raise ValueError(f"output verification failed for {key}")
            _emit_summary(summary_lines, key=f"output.{key}.path", value=output_paths[key])
            _emit_summary(summary_lines, key=f"output.{key}.line_count", value=line_count)
            _emit_summary(summary_lines, key=f"output.{key}.byte_count", value=byte_count)
    except (OSError, ValueError) as exc:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(summary_output, summary_lines)
        print(str(exc), file=sys.stderr)
        return 1

    _emit_summary(summary_lines, key="status", value="OK")

    for line in summary_lines:
        print(line)
    if summary_output is not None:
        _write_summary_output(summary_output, summary_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
