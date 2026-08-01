from __future__ import annotations

import argparse
import json
import sys

from rawcandle.ec_datacenter_watchlist_loader import apply_datacenter_watchlist_reconciliation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply Datacenter watchlist TXT -> EC membership reconciliation")
    parser.add_argument("--db", required=True)
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--ecosystem", default="DATACENTER")
    parser.add_argument("--taxonomy-version", default="DC_TAXONOMY_FULL_V1")
    parser.add_argument("--watchlist-code", default="DATACENTER_WATCHLIST")
    parser.add_argument("--confirm-db", required=True)
    parser.add_argument("--confirm-ecosystem", required=True)
    parser.add_argument("--confirm-watchlist", required=True)
    parser.add_argument("--invocation-source", default="MANUAL_APPLY")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    return parser


def render_text(summary: dict[str, object]) -> str:
    lines = ["Datacenter Watchlist Reconciliation Apply"]
    for key in (
        "watchlist_reconciliation_status",
        "watchlist_source_reference",
        "watchlist_source_sha256",
        "watchlist_source_member_count",
        "watchlist_previous_member_count",
        "watchlist_current_member_count",
        "watchlist_added_count",
        "watchlist_removed_count",
        "watchlist_added_tickers",
        "watchlist_removed_tickers",
        "watchlist_created_watchlist_only_ticker_count",
        "watchlist_created_watchlist_only_tickers",
        "watchlist_reconciliation_error",
    ):
        lines.append(f"{key}={summary.get(key)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.confirm_db != args.db:
        summary = {
            "watchlist_reconciliation_status": "FAILED",
            "watchlist_reconciliation_error": "--confirm-db must exactly match --db",
        }
    elif args.confirm_ecosystem != args.ecosystem:
        summary = {
            "watchlist_reconciliation_status": "FAILED",
            "watchlist_reconciliation_error": "--confirm-ecosystem must exactly match --ecosystem",
        }
    elif args.confirm_watchlist != args.watchlist:
        summary = {
            "watchlist_reconciliation_status": "FAILED",
            "watchlist_reconciliation_error": "--confirm-watchlist must exactly match --watchlist",
        }
    else:
        summary = apply_datacenter_watchlist_reconciliation(
            db_path=args.db,
            watchlist_path=args.watchlist,
            ecosystem_code=args.ecosystem,
            taxonomy_version_code=args.taxonomy_version,
            watchlist_code=args.watchlist_code,
            invocation_source=args.invocation_source,
        )
    if args.format == "json":
        sys.stdout.write(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    else:
        sys.stdout.write(render_text(summary) + "\n")
    return 0 if summary.get("watchlist_reconciliation_status") in {"APPLIED", "NO_CHANGE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
