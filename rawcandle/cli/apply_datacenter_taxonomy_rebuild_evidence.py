from __future__ import annotations

import argparse

from rawcandle.datacenter_taxonomy_replacement import (
    DATACENTER_ECOSYSTEM_CODE,
    apply_datacenter_taxonomy_rebuild_evidence,
    print_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify Datacenter taxonomy rebuild evidence and mark deployment READY_TO_ACTIVATE"
    )
    parser.add_argument("--analysis-db", required=True)
    parser.add_argument("--ecosystem", default=DATACENTER_ECOSYSTEM_CODE)
    parser.add_argument("--proposed-taxonomy-version", required=True)
    parser.add_argument("--proposed-taxonomy-csv", required=True)
    parser.add_argument("--deployment-id", type=int, required=True)
    parser.add_argument("--required-signal-date", required=True)
    parser.add_argument("--coverage-status", default="OK")
    parser.add_argument("--parity-status", default="OK")
    parser.add_argument("--total-mismatch-count", type=int, default=0)
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = apply_datacenter_taxonomy_rebuild_evidence(
        analysis_db=args.analysis_db,
        ecosystem_code=args.ecosystem,
        proposed_taxonomy_version=args.proposed_taxonomy_version,
        proposed_taxonomy_csv=args.proposed_taxonomy_csv,
        deployment_id=args.deployment_id,
        required_signal_date=args.required_signal_date,
        coverage_status=args.coverage_status,
        parity_status=args.parity_status,
        total_mismatch_count=args.total_mismatch_count,
    )
    print_json(summary)
    return 0 if summary.get("status_update") == "READY_TO_ACTIVATE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
