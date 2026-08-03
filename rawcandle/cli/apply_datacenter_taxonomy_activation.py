from __future__ import annotations

from rawcandle.datacenter_taxonomy_replacement import (
    apply_datacenter_taxonomy_activation,
    build_apply_activation_parser,
    print_json,
)


def main(argv: list[str] | None = None) -> int:
    args = build_apply_activation_parser().parse_args(argv)
    if args.confirm_activate_taxonomy_version != args.proposed_taxonomy_version:
        summary = {
            "activation_apply_status": "BLOCKED",
            "blocking_errors": [
                "confirm_activate_taxonomy_version must match proposed_taxonomy_version"
            ],
        }
        print_json(summary)
        return 1
    summary = apply_datacenter_taxonomy_activation(
        analysis_db=args.analysis_db,
        ecosystem_code=args.ecosystem,
        proposed_taxonomy_version=args.proposed_taxonomy_version,
        proposed_taxonomy_csv=args.proposed_taxonomy_csv,
        required_signal_date=args.required_signal_date,
        confirm_activate_taxonomy_version=args.confirm_activate_taxonomy_version,
        expected_scheduler_taxonomy_version=args.expected_scheduler_taxonomy_version,
        expected_scheduler_taxonomy_csv=args.expected_scheduler_taxonomy_csv,
        scheduler_config_path=args.scheduler_config,
        expected_current_scheduler_taxonomy_version=args.expected_current_scheduler_taxonomy_version,
        expected_current_scheduler_taxonomy_csv=args.expected_current_scheduler_taxonomy_csv,
        target_scheduler_taxonomy_csv=args.target_scheduler_taxonomy_csv,
        config_backup_dir=args.config_backup_dir,
    )
    print_json(summary)
    return 0 if summary["activation_apply_status"] == "ACTIVE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
