from __future__ import annotations

import argparse

from rawcandle.datacenter_taxonomy_replacement import (
    DATACENTER_ECOSYSTEM_CODE,
    prepare_datacenter_taxonomy_rebuild,
    print_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a loaded Datacenter taxonomy for a controlled full rebuild without running the pipeline"
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--ecosystem", default=DATACENTER_ECOSYSTEM_CODE)
    parser.add_argument("--proposed-taxonomy-version", required=True)
    parser.add_argument("--proposed-taxonomy-csv", required=True)
    parser.add_argument("--deployment-id", type=int, required=True)
    parser.add_argument("--expected-active-taxonomy-version", required=True)
    parser.add_argument("--confirm-proposed-taxonomy-version", required=True)
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = prepare_datacenter_taxonomy_rebuild(
        analysis_db=args.analysis_db,
        ecosystem_code=args.ecosystem,
        proposed_taxonomy_version=args.proposed_taxonomy_version,
        proposed_taxonomy_csv=args.proposed_taxonomy_csv,
        deployment_id=args.deployment_id,
        expected_active_taxonomy_version=args.expected_active_taxonomy_version,
        confirm_proposed_taxonomy_version=args.confirm_proposed_taxonomy_version,
    )
    print_json(summary)
    return 0 if summary.get("prepare_status") == "REBUILD_IN_PROGRESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
