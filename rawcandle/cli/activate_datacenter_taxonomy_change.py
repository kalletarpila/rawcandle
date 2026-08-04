from __future__ import annotations

from rawcandle.datacenter_taxonomy_replacement import (
    apply_datacenter_taxonomy_activation,
    build_apply_activation_parser,
    print_json,
)
from rawcandle.datacenter_taxonomy_operation_log import (
    complete_taxonomy_change_operation,
    create_taxonomy_change_operation,
    write_taxonomy_operation_artifact,
)


def main(argv: list[str] | None = None) -> int:
    args = build_apply_activation_parser().parse_args(argv)
    summary = apply_datacenter_taxonomy_activation(
        analysis_db=args.analysis_db,
        ecosystem_code=args.ecosystem,
        deployment_id=args.deployment_id,
        current_taxonomy_version=args.current_taxonomy_version,
        current_taxonomy_csv=args.current_taxonomy_csv,
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
    operation = create_taxonomy_change_operation(
        deployment_id=args.deployment_id,
        operation_type="ACTIVATE",
    )
    write_taxonomy_operation_artifact(operation, relative_name="activation_result.json", payload=summary)
    complete_taxonomy_change_operation(
        operation,
        status="OK" if summary["activation_apply_status"] in {"ACTIVE", "NO_CHANGE"} else "FAILED",
        failed_phase=None if summary["activation_apply_status"] in {"ACTIVE", "NO_CHANGE"} else "ACTIVATION",
    )
    print_json(summary)
    return 0 if summary["activation_apply_status"] in {"ACTIVE", "NO_CHANGE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
