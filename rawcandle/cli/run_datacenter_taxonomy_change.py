from __future__ import annotations

from rawcandle.datacenter_taxonomy_change_orchestrator import (
    build_production_taxonomy_change_services,
    build_run_parser,
    execute_taxonomy_rebuild,
    print_json,
    resume_taxonomy_rebuild,
)
from rawcandle.datacenter_taxonomy_operation_log import (
    complete_taxonomy_change_operation,
    create_taxonomy_change_operation,
    taxonomy_operation_lock_context,
    write_taxonomy_operation_artifact,
)


def main(argv: list[str] | None = None) -> int:
    args = build_run_parser().parse_args(argv)
    operation_type = "RESUME" if args.resume else "REBUILD"
    operation = create_taxonomy_change_operation(
        deployment_id=args.deployment_id,
        operation_type=operation_type,
        evidence_root=args.evidence_root,
    )
    services = (
        build_production_taxonomy_change_services(
            scheduler_config_path=args.scheduler_config,
            evidence_root=args.evidence_root,
            resume=args.resume,
        )
        if args.scheduler_config
        else None
    )
    with taxonomy_operation_lock_context(
        deployment_id=args.deployment_id,
        operation_type=operation_type,
        operation_id=operation.operation_id,
        evidence_root=args.evidence_root,
    ):
        runner = resume_taxonomy_rebuild if args.resume else execute_taxonomy_rebuild
        summary = runner(
            analysis_db=args.analysis_db,
            deployment_id=args.deployment_id,
            proposed_taxonomy_csv=args.proposed_taxonomy_csv,
            date_to=args.date_to,
            scheduler_config_path=args.scheduler_config,
            watchlist_path=args.watchlist,
            evidence_root=args.evidence_root,
            confirm_deployment_id=args.confirm_deployment_id,
            confirm_proposed_taxonomy_version=args.confirm_proposed_taxonomy_version,
            confirm_proposed_source_hash=args.confirm_proposed_source_hash,
            confirm_date_from=args.confirm_date_from,
            confirm_date_to=args.confirm_date_to,
            confirm_rebuild_mode=args.confirm_rebuild_mode,
            confirm_plan_hash=args.confirm_plan_hash,
            confirm_repair_amendment_hash=args.confirm_repair_amendment_hash,
            confirm_dc_repair_scope=args.confirm_dc_repair_scope,
            confirm_repair_candidate_hash=args.confirm_repair_candidate_hash,
            confirm_existing_backup_path=args.confirm_existing_backup_path,
            confirm_existing_backup_sha256=args.confirm_existing_backup_sha256,
            services=services,
        )
    write_taxonomy_operation_artifact(operation, relative_name="run_summary.json", payload=summary)
    complete_taxonomy_change_operation(
        operation,
        status="OK" if summary.get("run_status") in {"READY_TO_ACTIVATE", "NO_CHANGE_READY_TO_ACTIVATE", "ALREADY_ACTIVE"} else "FAILED",
        failed_phase=summary.get("failed_phase"),
        resume_from_phase=summary.get("resume_from_phase"),
    )
    print_json(summary)
    return 0 if summary.get("run_status") in {"READY_TO_ACTIVATE", "NO_CHANGE_READY_TO_ACTIVATE", "ALREADY_ACTIVE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
