from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.schema.operating_working_capital import migrate_and_backfill_operating_working_capital


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Apply Phase 6A.2 only to explicit database copies")
    parser.add_argument("--provider-destination", type=Path, required=True)
    parser.add_argument("--canonical-destination", type=Path, required=True)
    parser.add_argument("--applied-at-utc", required=True)
    parser.add_argument("--company-id", type=int, action="append")
    parser.add_argument("--apply", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    plan: dict[str, object] = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "provider_destination": str(args.provider_destination.resolve()),
        "canonical_destination": str(args.canonical_destination.resolve()),
        "company_ids": args.company_id,
    }
    if not args.apply:
        return plan
    return migrate_and_backfill_operating_working_capital(
        args.provider_destination,
        args.canonical_destination,
        args.applied_at_utc,
        company_ids=args.company_id,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        result = run(build_parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
