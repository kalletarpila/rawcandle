from __future__ import annotations

import argparse
import json
from dataclasses import asdict

from rawcandle.fundamentals.admin.history import AdminRunHistory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect durable Fundamentals administration run history.")
    parser.add_argument("action", choices=("list", "show", "artifact"))
    parser.add_argument("--run-id")
    parser.add_argument("--artifact")
    parser.add_argument("--operation-type")
    parser.add_argument("--outcome")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    history = AdminRunHistory()
    if args.action == "list":
        rows = [asdict(row) for row in history.list_runs(operation_type=args.operation_type, outcome=args.outcome)]
        print(json.dumps(rows, indent=2, sort_keys=True))
        return 0
    if not args.run_id:
        raise SystemExit("--run-id is required")
    if args.action == "show":
        print(json.dumps(asdict(history.summarize(args.run_id)), indent=2, sort_keys=True))
        return 0
    if not args.artifact:
        raise SystemExit("--artifact is required")
    print(str(history.artifact_path(args.run_id, args.artifact)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
