from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

from analysis.datacenter_indices.report_canonical_v2_parity_audit import (
    audit_report_canonical_v2_parity,
)


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
ALLOWED_HORIZONS = ("daily", "rolling2", "rolling5", "rolling30")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run read-only canonical V2 parity audit for one signal date."
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--signal-date", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--market")
    parser.add_argument(
        "--horizons",
        default="daily,rolling2,rolling5,rolling30",
        help="Comma-separated list of horizons.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
    )
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
    if not DATE_RE.match(str(args.signal_date)):
        parser.error("--signal-date must match YYYY-MM-DD")
    if not str(args.taxonomy_version).strip():
        parser.error("--taxonomy-version must be non-empty")
    args.horizons = _parse_horizons(parser, str(args.horizons))
    return args


def _text_cell(value: object | None) -> str:
    if value is None:
        return ""
    return str(value).replace("\n", " ").strip()


def _emit_text(result: dict[str, object]) -> None:
    horizons = ",".join(str(horizon) for horizon in result["horizons"])
    print(f"SUMMARY status={_text_cell(result['status'])}")
    print(f"SUMMARY signal_date={_text_cell(result['signal_date'])}")
    print(f"SUMMARY taxonomy_version={_text_cell(result['taxonomy_version'])}")
    print(f"SUMMARY market={_text_cell(result['market'])}")
    print(f"SUMMARY horizons={horizons}")
    print(f"SUMMARY mismatch_count={_text_cell(result['mismatch_count'])}")
    print(f"SUMMARY missing_current_count={_text_cell(result['missing_current_count'])}")
    print(f"SUMMARY missing_v2_count={_text_cell(result['missing_v2_count'])}")
    print(f"SUMMARY matched_count={_text_cell(result['matched_count'])}")

    horizon_summaries = result["horizon_summaries"]
    for horizon in result["horizons"]:
        summary = horizon_summaries[horizon]
        print(f"SUMMARY horizon.{horizon}.mismatch_count={_text_cell(summary['mismatch_count'])}")
        print(
            "SUMMARY "
            f"horizon.{horizon}.missing_current_count={_text_cell(summary['missing_current_count'])}"
        )
        print(
            "SUMMARY "
            f"horizon.{horizon}.missing_v2_count={_text_cell(summary['missing_v2_count'])}"
        )
        print(f"SUMMARY horizon.{horizon}.matched_count={_text_cell(summary['matched_count'])}")

    for mismatch in result["mismatches"]:
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


def _exit_code_for_status(status: str) -> int:
    if status == "OK":
        return 0
    if status in {"MISMATCH", "NO_CURRENT_DATA", "NO_V2_DATA"}:
        return 1
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    try:
        args = _validated_args(parser, argv)
    except SystemExit as exc:
        return int(exc.code)

    try:
        with _connect_read_only(str(args.db)) as conn:
            result = audit_report_canonical_v2_parity(
                conn,
                signal_date=str(args.signal_date),
                taxonomy_version=str(args.taxonomy_version),
                market=args.market,
                horizons=args.horizons,
            )
    except (FileNotFoundError, sqlite3.Error, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        print(json.dumps(result, sort_keys=True, indent=2))
    else:
        _emit_text(result)
    return _exit_code_for_status(str(result["status"]))


if __name__ == "__main__":
    raise SystemExit(main())
