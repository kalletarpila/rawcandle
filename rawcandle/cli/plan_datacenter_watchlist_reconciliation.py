from __future__ import annotations

import argparse
import json
import sys

from rawcandle.ec_datacenter_watchlist_loader import plan_datacenter_watchlist_reconciliation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan Datacenter watchlist TXT -> EC membership reconciliation without writes")
    parser.add_argument("--db", required=True)
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--ecosystem", default="DATACENTER")
    parser.add_argument("--taxonomy-version", default="DC_TAXONOMY_FULL_V1")
    parser.add_argument("--watchlist-code", default="DATACENTER_WATCHLIST")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def render_text(summary: dict[str, object]) -> str:
    lines = ["Datacenter Watchlist Reconciliation Plan"]
    for key in (
        "watchlist_reconciliation_status",
        "watchlist_plan_apply_safe",
        "watchlist_source_reference",
        "watchlist_source_sha256",
        "watchlist_source_member_count",
        "watchlist_previous_member_count",
        "watchlist_current_member_count",
        "watchlist_added_count",
        "watchlist_removed_count",
        "watchlist_added_tickers",
        "watchlist_removed_tickers",
        "watchlist_reconciliation_error",
    ):
        lines.append(f"{key}={summary.get(key)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = plan_datacenter_watchlist_reconciliation(
        db_path=args.db,
        watchlist_path=args.watchlist,
        ecosystem_code=args.ecosystem,
        taxonomy_version_code=args.taxonomy_version,
        watchlist_code=args.watchlist_code,
    )
    if args.format == "json":
        sys.stdout.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_text(summary) + "\n")
    return 0 if summary.get("watchlist_reconciliation_status") != "FAILED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
