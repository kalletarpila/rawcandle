from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from analysis.datacenter_indices.report_canonical_v2_daily_formatter_loader import (
    build_csv_daily_canonical_v2_report,
    load_daily_canonical_formatter_data_v2,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render canonical daily CSV report from existing canonical V2 tables."
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--market")
    parser.add_argument("--run-id")
    parser.add_argument("--output")
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
    return args


def _write_output(path_str: str, csv_text: str) -> None:
    path = Path(path_str)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(csv_text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = _validated_args(parser, argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        with _connect_read_only(str(args.db)) as conn:
            formatter_data = load_daily_canonical_formatter_data_v2(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                run_id=args.run_id,
            )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    csv_text = build_csv_daily_canonical_v2_report(formatter_data)
    if args.output:
        _write_output(str(args.output), csv_text)
    else:
        print(csv_text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
