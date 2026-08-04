from __future__ import annotations

import argparse

from rawcandle.datacenter_taxonomy_replacement import (
    plan_ec_taxonomy_replacement_cleanup,
    print_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plan guarded EC old-taxonomy replacement cleanup")
    parser.add_argument("--db", required=True)
    parser.add_argument("--ecosystem", required=True)
    parser.add_argument("--target-taxonomy-version", required=True)
    parser.add_argument("--deployment-id", required=True, type=int)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--scheduler-config")
    parser.add_argument("--expected-scheduler-taxonomy-version")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = plan_ec_taxonomy_replacement_cleanup(
        db=args.db,
        ecosystem=args.ecosystem,
        target_taxonomy_version=args.target_taxonomy_version,
        deployment_id=args.deployment_id,
        date_from=args.date_from,
        date_to=args.date_to,
        scheduler_config=args.scheduler_config,
        expected_scheduler_taxonomy_version=args.expected_scheduler_taxonomy_version,
    )
    print_json(summary)
    return 0 if summary["cleanup_plan_status"] != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
