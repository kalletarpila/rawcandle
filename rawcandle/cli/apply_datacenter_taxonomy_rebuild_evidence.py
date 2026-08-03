from __future__ import annotations

import argparse

from rawcandle.datacenter_taxonomy_replacement import (
    DATACENTER_ECOSYSTEM_CODE,
    apply_datacenter_taxonomy_dc_rebuild_acceptance,
    apply_datacenter_taxonomy_rebuild_evidence,
    print_json,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify Datacenter taxonomy rebuild evidence"
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
    parser.add_argument(
        "--accept-dc-only",
        action="store_true",
        help="Accept completed DC rebuild evidence without marking EC rebuild complete",
    )
    parser.add_argument("--required-start-date", default="2025-08-01")
    parser.add_argument("--evidence-dir")
    parser.add_argument("--scheduler-config", default="scheduler_config.json")
    parser.add_argument("--expected-scheduler-taxonomy-version", default="DC_TAXONOMY_FULL_V1")
    parser.add_argument("--expected-ticker-rows", type=int, default=257)
    parser.add_argument("--expected-group-rows", type=int, default=54)
    parser.add_argument("--expected-synthetic-rows", type=int, default=53)
    parser.add_argument("--expected-index-rows", type=int, default=54)
    parser.add_argument("--windows-copy-status", default="FAILED_OPTIONAL")
    parser.add_argument("--windows-copy-required", action="store_true")
    parser.add_argument("--format", choices=("json",), default="json")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.accept_dc_only:
        if not args.evidence_dir:
            raise SystemExit("ERROR --evidence-dir is required with --accept-dc-only")
        summary = apply_datacenter_taxonomy_dc_rebuild_acceptance(
            analysis_db=args.analysis_db,
            ecosystem_code=args.ecosystem,
            proposed_taxonomy_version=args.proposed_taxonomy_version,
            proposed_taxonomy_csv=args.proposed_taxonomy_csv,
            deployment_id=args.deployment_id,
            required_start_date=args.required_start_date,
            required_signal_date=args.required_signal_date,
            evidence_dir=args.evidence_dir,
            scheduler_config=args.scheduler_config,
            expected_scheduler_taxonomy_version=args.expected_scheduler_taxonomy_version,
            expected_ticker_rows=args.expected_ticker_rows,
            expected_group_rows=args.expected_group_rows,
            expected_synthetic_rows=args.expected_synthetic_rows,
            expected_index_rows=args.expected_index_rows,
            windows_copy_status=args.windows_copy_status,
            windows_copy_required=args.windows_copy_required,
        )
        print_json(summary)
        return 0 if summary.get("status_update") == "VALIDATION_REQUIRED" else 1
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
