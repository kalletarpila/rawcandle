from __future__ import annotations

from rawcandle.datacenter_taxonomy_replacement import (
    build_activation_plan_parser,
    plan_datacenter_taxonomy_activation,
    print_json,
)


def main(argv: list[str] | None = None) -> int:
    args = build_activation_plan_parser().parse_args(argv)
    summary = plan_datacenter_taxonomy_activation(
        analysis_db=args.analysis_db,
        ecosystem_code=args.ecosystem,
        deployment_id=args.deployment_id,
        current_taxonomy_version=args.current_taxonomy_version,
        current_taxonomy_csv=args.current_taxonomy_csv,
        proposed_taxonomy_version=args.proposed_taxonomy_version,
        proposed_taxonomy_csv=args.proposed_taxonomy_csv,
        required_signal_date=args.required_signal_date,
        scheduler_config_path=args.scheduler_config,
        expected_scheduler_taxonomy_version=args.expected_scheduler_taxonomy_version,
        expected_scheduler_taxonomy_csv=args.expected_scheduler_taxonomy_csv,
    )
    print_json(summary)
    return 0 if summary["activation_plan_status"] != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
