from __future__ import annotations

from rawcandle.datacenter_taxonomy_change_orchestrator import (
    build_prepare_parser,
    prepare_taxonomy_change,
    print_json,
)
from rawcandle.datacenter_taxonomy_operation_log import (
    complete_taxonomy_change_operation,
    create_taxonomy_change_operation,
    write_taxonomy_operation_artifact,
)


def main(argv: list[str] | None = None) -> int:
    args = build_prepare_parser().parse_args(argv)
    summary = prepare_taxonomy_change(
        analysis_db=args.analysis_db,
        ecosystem_code=args.ecosystem,
        proposed_taxonomy_csv=args.proposed_taxonomy_csv,
        date_from=args.date_from,
        date_to=args.date_to,
        scheduler_config_path=args.scheduler_config,
        watchlist_path=args.watchlist,
        evidence_root=args.evidence_root,
        rebuild_mode=args.rebuild_mode,
        create_deployment=not args.plan_only,
    )
    deployment_id = summary.get("deployment_id") or "plan_only"
    operation = create_taxonomy_change_operation(
        deployment_id=deployment_id,
        operation_type="PREPARE",
        evidence_root=args.evidence_root,
    )
    write_taxonomy_operation_artifact(operation, relative_name="prepare.json", payload=summary)
    if isinstance(summary.get("plan"), dict):
        write_taxonomy_operation_artifact(operation, relative_name="plan.json", payload=summary["plan"])
        write_taxonomy_operation_artifact(
            operation,
            relative_name="taxonomy_diff.json",
            payload=summary["plan"].get("taxonomy_diff", {}),
        )
        write_taxonomy_operation_artifact(
            operation,
            relative_name="work_estimate.json",
            payload=summary["plan"].get("estimated_delta_work", {}),
        )
    complete_taxonomy_change_operation(
        operation,
        status="OK" if summary.get("prepare_status") in {"READY_TO_REBUILD", "PLAN_READY"} else "FAILED",
        failed_phase=None if summary.get("prepare_status") in {"READY_TO_REBUILD", "PLAN_READY"} else "PREPARE",
    )
    print_json(summary)
    return 0 if summary.get("prepare_status") in {"READY_TO_REBUILD", "PLAN_READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
