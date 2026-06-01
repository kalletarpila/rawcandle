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


HORIZONS = ("daily", "rolling2", "rolling5", "rolling30")
REQUIRED_CLASSIFICATION_TYPES = (
    "daily_trigger",
    "rolling2_sell_pressure",
    "rolling5_pullback",
    "rolling30_buy",
    "rolling30_exit",
)
OUTPUT_SPECS = {
    "daily_markdown": (
        load_daily_canonical_formatter_data_v2,
        build_markdown_daily_canonical_v2_report,
        "datacenter_daily_canonical_v2_{signal_date}.md",
    ),
    "daily_csv": (
        load_daily_canonical_formatter_data_v2,
        build_csv_daily_canonical_v2_report,
        "datacenter_daily_canonical_v2_{signal_date}.csv",
    ),
    "rolling2_markdown": (
        load_rolling2_canonical_formatter_data_v2,
        build_markdown_rolling2_canonical_v2_report,
        "datacenter_rolling2_canonical_v2_{signal_date}.md",
    ),
    "rolling2_csv": (
        load_rolling2_canonical_formatter_data_v2,
        build_csv_rolling2_canonical_v2_report,
        "datacenter_rolling2_canonical_v2_{signal_date}.csv",
    ),
    "rolling5_markdown": (
        load_rolling5_canonical_formatter_data_v2,
        build_markdown_rolling5_canonical_v2_report,
        "datacenter_rolling5_canonical_v2_{signal_date}.md",
    ),
    "rolling5_csv": (
        load_rolling5_canonical_formatter_data_v2,
        build_csv_rolling5_canonical_v2_report,
        "datacenter_rolling5_canonical_v2_{signal_date}.csv",
    ),
    "rolling30_markdown": (
        load_rolling30_canonical_formatter_data_v2,
        build_markdown_rolling30_canonical_v2_report,
        "datacenter_rolling30_canonical_v2_{signal_date}.md",
    ),
    "rolling30_csv": (
        load_rolling30_canonical_formatter_data_v2,
        build_csv_rolling30_canonical_v2_report,
        "datacenter_rolling30_canonical_v2_{signal_date}.csv",
    ),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Publish all canonical V2 outputs from an existing production canonical slice."
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--market")
    parser.add_argument("--summary-output")
    parser.add_argument("--overwrite-output", action="store_true")
    return parser


def _validated_args(parser: argparse.ArgumentParser, argv: list[str] | None) -> argparse.Namespace:
    args = parser.parse_args(argv)
    if not str(args.signal_date).strip():
        parser.error("--signal-date must be non-empty")
    if not str(args.taxonomy_version).strip():
        parser.error("--taxonomy-version must be non-empty")
    if not str(args.run_id).strip():
        parser.error("--run-id must be non-empty")
    return args


def _connect_read_only(db_path: str) -> sqlite3.Connection:
    path = Path(db_path)
    if not path.exists():
        raise FileNotFoundError(f"analysis_db not found: {db_path}")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _text_cell(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _line_count(text: str) -> int:
    count = text.count("\n")
    if text and not text.endswith("\n"):
        count += 1
    return count


def _emit_summary(lines: list[str], *, key: str, value: object) -> None:
    lines.append(f"SUMMARY {key}={_text_cell(value)}")


def _write_summary_output(path_str: str, lines: list[str]) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _slice_where_clause(*, include_run_id: bool, market: str | None) -> tuple[str, tuple[object, ...]]:
    where = ["signal_date = ?", "taxonomy_version = ?"]
    params: list[object] = []
    if include_run_id:
        where.append("run_id = ?")
    if market is not None:
        where.append("market = ?")
    return " AND ".join(where), tuple(params)


def _count_rows(
    conn: sqlite3.Connection,
    *,
    table: str,
    signal_date: str,
    taxonomy_version: str,
    run_id: str | None = None,
    market: str | None = None,
) -> int:
    where = ["signal_date = ?", "taxonomy_version = ?"]
    params: list[object] = [signal_date, taxonomy_version]
    if run_id is not None:
        where.append("run_id = ?")
        params.append(run_id)
    if market is not None:
        where.append("market = ?")
        params.append(market)
    row = conn.execute(
        f"SELECT COUNT(*) AS row_count FROM {table} WHERE {' AND '.join(where)}",
        tuple(params),
    ).fetchone()
    return int(row["row_count"])


def _count_run_rows(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    run_id: str,
    market: str | None,
) -> int:
    return _count_rows(
        conn,
        table="dc_report_run_v2",
        signal_date=signal_date,
        taxonomy_version=taxonomy_version,
        run_id=run_id,
        market=market,
    )


def _classification_types(
    conn: sqlite3.Connection,
    *,
    signal_date: str,
    taxonomy_version: str,
    run_id: str,
    market: str | None,
) -> set[str]:
    where = ["signal_date = ?", "taxonomy_version = ?", "run_id = ?"]
    params: list[object] = [signal_date, taxonomy_version, run_id]
    if market is not None:
        where.append("market = ?")
        params.append(market)
    rows = conn.execute(
        f"""
        SELECT DISTINCT classification_type
        FROM dc_report_classification_v2
        WHERE {' AND '.join(where)}
        """,
        tuple(params),
    ).fetchall()
    return {str(row["classification_type"]) for row in rows}


def _output_paths(output_dir: Path, signal_date: str) -> dict[str, Path]:
    return {
        key: output_dir / filename_pattern.format(signal_date=signal_date)
        for key, (_, _, filename_pattern) in OUTPUT_SPECS.items()
    }


def _prepare_output_paths(paths: list[Path], *, overwrite: bool) -> None:
    for path in paths:
        if path.exists() and not overwrite:
            raise FileExistsError(f"output already exists: {path}")
    for path in paths:
        path.parent.mkdir(parents=True, exist_ok=True)


def _write_output(path: Path, text: str) -> tuple[int, int]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    if not path.exists():
        raise OSError(f"output not written: {path}")
    line_count = _line_count(text)
    byte_count = len(text.encode("utf-8"))
    if line_count <= 0 or byte_count <= 0:
        raise OSError(f"output was empty: {path}")
    return line_count, byte_count


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = _validated_args(parser, argv)
    except SystemExit as exc:
        return int(exc.code)

    summary_lines: list[str] = []
    output_dir = Path(str(args.output_dir))
    summary_output = None if args.summary_output is None else Path(str(args.summary_output))
    output_paths = _output_paths(output_dir, str(args.signal_date))

    _emit_summary(summary_lines, key="db", value=args.db)
    _emit_summary(summary_lines, key="output_dir", value=args.output_dir)
    _emit_summary(summary_lines, key="signal_date", value=args.signal_date)
    _emit_summary(summary_lines, key="taxonomy_version", value=args.taxonomy_version)
    _emit_summary(summary_lines, key="run_id", value=args.run_id)
    _emit_summary(summary_lines, key="market", value=args.market or "")

    try:
        conn = _connect_read_only(str(args.db))
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        with conn:
            v2_run_rows = _count_run_rows(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                run_id=str(args.run_id),
                market=args.market,
            )
            v2_group_context_rows = _count_rows(
                conn,
                table="dc_report_context_group_v2",
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                run_id=str(args.run_id),
                market=args.market,
            )
            v2_daily_context_rows = _count_rows(
                conn,
                table="dc_report_context_daily_v2",
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                run_id=str(args.run_id),
                market=args.market,
            )
            v2_window_context_rows = _count_rows(
                conn,
                table="dc_report_context_window_v2",
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                run_id=str(args.run_id),
                market=args.market,
            )
            v2_classification_rows = _count_rows(
                conn,
                table="dc_report_classification_v2",
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                run_id=str(args.run_id),
                market=args.market,
            )
            classification_types = _classification_types(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                run_id=str(args.run_id),
                market=args.market,
            )
    except sqlite3.Error as exc:
        print(str(exc), file=sys.stderr)
        return 1

    _emit_summary(summary_lines, key="v2_run_rows", value=v2_run_rows)
    _emit_summary(summary_lines, key="v2_group_context_rows", value=v2_group_context_rows)
    _emit_summary(summary_lines, key="v2_daily_context_rows", value=v2_daily_context_rows)
    _emit_summary(summary_lines, key="v2_window_context_rows", value=v2_window_context_rows)
    _emit_summary(summary_lines, key="v2_classification_rows", value=v2_classification_rows)

    if v2_run_rows != 1:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(str(summary_output), summary_lines)
        print("expected exactly one canonical V2 run row for requested slice", file=sys.stderr)
        return 1

    if min(
        v2_group_context_rows,
        v2_daily_context_rows,
        v2_window_context_rows,
        v2_classification_rows,
    ) <= 0:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(str(summary_output), summary_lines)
        print("requested canonical V2 slice has missing row coverage", file=sys.stderr)
        return 1

    missing_types = sorted(set(REQUIRED_CLASSIFICATION_TYPES) - classification_types)
    if missing_types:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(str(summary_output), summary_lines)
        print(
            "missing required classification types: " + ", ".join(missing_types),
            file=sys.stderr,
        )
        return 1

    try:
        with conn:
            parity = audit_report_canonical_v2_parity(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                horizons=HORIZONS,
            )
    except sqlite3.Error as exc:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(str(summary_output), summary_lines)
        print(str(exc), file=sys.stderr)
        return 1

    _emit_summary(summary_lines, key="parity_status", value=parity.get("status", ""))
    _emit_summary(summary_lines, key="parity_mismatch_count", value=parity.get("mismatch_count", 0))

    if str(parity.get("status") or "") != "OK":
        mismatches = list(parity.get("mismatches") or [])[:10]
        for mismatch in mismatches:
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
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(str(summary_output), summary_lines)
        return 1

    protected_outputs = list(output_paths.values())
    if summary_output is not None:
        protected_outputs.append(summary_output)
    try:
        _prepare_output_paths(protected_outputs, overwrite=bool(args.overwrite_output))
    except FileExistsError as exc:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(str(summary_output), summary_lines)
        print(str(exc), file=sys.stderr)
        return 1

    rendered_outputs: dict[str, tuple[Path, int, int]] = {}
    try:
        with _connect_read_only(str(args.db)) as render_conn:
            for key, (loader, formatter, _) in OUTPUT_SPECS.items():
                formatter_data = loader(
                    render_conn,
                    signal_date=str(args.signal_date),
                    taxonomy_version=str(args.taxonomy_version),
                    market=args.market,
                    run_id=str(args.run_id),
                )
                output_text = formatter(formatter_data)
                line_count, byte_count = _write_output(output_paths[key], output_text)
                rendered_outputs[key] = (output_paths[key], line_count, byte_count)
    except (sqlite3.Error, ValueError, OSError) as exc:
        for line in summary_lines:
            print(line)
        if summary_output is not None:
            _write_summary_output(str(summary_output), summary_lines)
        print(str(exc), file=sys.stderr)
        return 1

    for key, (path, line_count, byte_count) in rendered_outputs.items():
        _emit_summary(summary_lines, key=f"output.{key}.path", value=path)
        _emit_summary(summary_lines, key=f"output.{key}.line_count", value=line_count)
        _emit_summary(summary_lines, key=f"output.{key}.byte_count", value=byte_count)

    summary_lines.insert(0, "SUMMARY status=OK")
    for line in summary_lines:
        print(line)
    if summary_output is not None:
        _write_summary_output(str(summary_output), summary_lines)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
