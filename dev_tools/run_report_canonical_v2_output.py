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


ALLOWED_HORIZONS = ("daily", "rolling2", "rolling5", "rolling30")
ALLOWED_FORMATS = ("markdown", "csv")

LOADER_FORMATTER_MAP = {
    ("daily", "markdown"): (
        load_daily_canonical_formatter_data_v2,
        build_markdown_daily_canonical_v2_report,
    ),
    ("daily", "csv"): (
        load_daily_canonical_formatter_data_v2,
        build_csv_daily_canonical_v2_report,
    ),
    ("rolling2", "markdown"): (
        load_rolling2_canonical_formatter_data_v2,
        build_markdown_rolling2_canonical_v2_report,
    ),
    ("rolling2", "csv"): (
        load_rolling2_canonical_formatter_data_v2,
        build_csv_rolling2_canonical_v2_report,
    ),
    ("rolling5", "markdown"): (
        load_rolling5_canonical_formatter_data_v2,
        build_markdown_rolling5_canonical_v2_report,
    ),
    ("rolling5", "csv"): (
        load_rolling5_canonical_formatter_data_v2,
        build_csv_rolling5_canonical_v2_report,
    ),
    ("rolling30", "markdown"): (
        load_rolling30_canonical_formatter_data_v2,
        build_markdown_rolling30_canonical_v2_report,
    ),
    ("rolling30", "csv"): (
        load_rolling30_canonical_formatter_data_v2,
        build_csv_rolling30_canonical_v2_report,
    ),
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render one canonical V2 output from existing canonical V2 tables."
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--horizon", required=True, choices=ALLOWED_HORIZONS)
    parser.add_argument("--format", required=True, choices=ALLOWED_FORMATS)
    parser.add_argument("--market")
    parser.add_argument("--run-id")
    parser.add_argument("--output")
    parser.add_argument("--require-parity-ok", action="store_true")
    parser.add_argument("--parity-horizons")
    parser.add_argument("--summary-output")
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
        parser.error("--parity-horizons must contain at least one allowed horizon")
    invalid = [horizon for horizon in horizons if horizon not in ALLOWED_HORIZONS]
    if invalid:
        parser.error(f"unsupported parity horizons: {', '.join(invalid)}")
    return tuple(dict.fromkeys(horizons))


def _validated_args(parser: argparse.ArgumentParser, argv: list[str] | None) -> argparse.Namespace:
    args = parser.parse_args(argv)
    if not str(args.signal_date).strip():
        parser.error("--signal-date must be non-empty")
    if not str(args.taxonomy_version).strip():
        parser.error("--taxonomy-version must be non-empty")
    if args.parity_horizons:
        args.parity_horizons = _parse_horizons(parser, str(args.parity_horizons))
    elif args.require_parity_ok:
        args.parity_horizons = (str(args.horizon),)
    else:
        args.parity_horizons = ()
    return args


def _text_cell(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _line_count(text: str) -> int:
    count = text.count("\n")
    if text and not text.endswith("\n"):
        count += 1
    return count


def _write_output(path_str: str, text: str) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _summary_lines(
    *,
    db: str,
    signal_date: str,
    taxonomy_version: str,
    horizon: str,
    output_format: str,
    market: str | None,
    run_id: str | None,
    output_path: str | None,
    text: str,
    parity_status: str | None = None,
    parity_mismatch_count: int | None = None,
) -> list[str]:
    lines = [
        "SUMMARY status=OK",
        f"SUMMARY db={_text_cell(db)}",
        f"SUMMARY signal_date={_text_cell(signal_date)}",
        f"SUMMARY taxonomy_version={_text_cell(taxonomy_version)}",
        f"SUMMARY horizon={_text_cell(horizon)}",
        f"SUMMARY format={_text_cell(output_format)}",
        f"SUMMARY market={_text_cell(market)}",
        f"SUMMARY run_id={_text_cell(run_id)}",
        f"SUMMARY output_path={_text_cell(output_path)}",
        f"SUMMARY line_count={_line_count(text)}",
        f"SUMMARY byte_count={len(text.encode('utf-8'))}",
    ]
    if parity_status is not None:
        lines.append(f"SUMMARY parity_status={_text_cell(parity_status)}")
        lines.append(f"SUMMARY parity_mismatch_count={parity_mismatch_count or 0}")
    return lines


def _write_summary_output(path_str: str, lines: list[str]) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = _validated_args(parser, argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        conn = _connect_read_only(str(args.db))
    except (FileNotFoundError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        with conn:
            parity_lines: list[str] = []
            if args.require_parity_ok:
                parity_result = audit_report_canonical_v2_parity(
                    conn,
                    signal_date=str(args.signal_date),
                    taxonomy_version=str(args.taxonomy_version),
                    market=args.market,
                    horizons=tuple(args.parity_horizons),
                )
                parity_status = str(parity_result.get("status") or "")
                parity_mismatch_count = int(parity_result.get("mismatch_count") or 0)
                parity_lines = [
                    f"SUMMARY parity_status={_text_cell(parity_status)}",
                    f"SUMMARY parity_mismatch_count={parity_mismatch_count}",
                ]
                if parity_status != "OK":
                    for mismatch in list(parity_result.get("mismatches") or [])[:10]:
                        parity_lines.append(
                            "MISMATCH "
                            f"horizon={_text_cell(mismatch.get('horizon'))} "
                            f"classification_type={_text_cell(mismatch.get('classification_type'))} "
                            f"ticker={_text_cell(mismatch.get('ticker'))} "
                            f"field={_text_cell(mismatch.get('field'))} "
                            f"current={_text_cell(mismatch.get('current_value'))} "
                            f"v2={_text_cell(mismatch.get('v2_value'))} "
                            f"reason={_text_cell(mismatch.get('reason'))}"
                        )
                    if args.summary_output:
                        _write_summary_output(str(args.summary_output), parity_lines)
                    else:
                        for line in parity_lines:
                            print(line)
                    return 1

            loader, formatter = LOADER_FORMATTER_MAP[(str(args.horizon), str(args.format))]
            formatter_data = loader(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                run_id=args.run_id,
            )
    except (sqlite3.Error, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    try:
        output_text = formatter(formatter_data)
        if args.output:
            _write_output(str(args.output), output_text)
        else:
            print(output_text, end="")
        if args.summary_output:
            parity_status = None
            parity_mismatch_count = None
            if args.require_parity_ok:
                parity_status = "OK"
                parity_mismatch_count = 0
            _write_summary_output(
                str(args.summary_output),
                _summary_lines(
                    db=str(args.db),
                    signal_date=str(args.signal_date),
                    taxonomy_version=str(args.taxonomy_version),
                    horizon=str(args.horizon),
                    output_format=str(args.format),
                    market=args.market,
                    run_id=args.run_id,
                    output_path=None if args.output is None else str(args.output),
                    text=output_text,
                    parity_status=parity_status,
                    parity_mismatch_count=parity_mismatch_count,
                ),
            )
    except OSError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
