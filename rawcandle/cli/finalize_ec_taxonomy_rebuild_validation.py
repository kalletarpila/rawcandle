from __future__ import annotations

import argparse

from rawcandle.datacenter_taxonomy_replacement import (
    finalize_ec_taxonomy_rebuild_validation,
    print_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate existing EC taxonomy rebuild facts without rerunning loaders")
    parser.add_argument("--db", required=True)
    parser.add_argument("--ecosystem", required=True)
    parser.add_argument("--target-taxonomy-version", required=True)
    parser.add_argument("--taxonomy-csv", required=True)
    parser.add_argument("--deployment-id", required=True, type=int)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--coverage-status", default="OK")
    parser.add_argument("--parity-status", default="OK")
    parser.add_argument("--total-mismatch-count", type=int, default=0)
    parser.add_argument("--finalize-watermarks", action="store_true")
    parser.add_argument("--update-deployment-evidence", action="store_true")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = finalize_ec_taxonomy_rebuild_validation(
        db=args.db,
        ecosystem=args.ecosystem,
        target_taxonomy_version=args.target_taxonomy_version,
        taxonomy_csv=args.taxonomy_csv,
        deployment_id=args.deployment_id,
        date_from=args.date_from,
        date_to=args.date_to,
        coverage_status=args.coverage_status,
        parity_status=args.parity_status,
        total_mismatch_count=args.total_mismatch_count,
        finalize_watermarks=args.finalize_watermarks,
        update_deployment_evidence=args.update_deployment_evidence,
    )
    print_json(summary)
    return 0 if summary["finalization_status"] == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
