from __future__ import annotations

from rawcandle.datacenter_taxonomy_change_orchestrator import (
    build_run_parser,
    execute_taxonomy_rebuild,
    print_json,
)


def main(argv: list[str] | None = None) -> int:
    args = build_run_parser().parse_args(argv)
    summary = execute_taxonomy_rebuild(
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
    )
    print_json(summary)
    return 0 if summary.get("run_status") in {"READY_TO_ACTIVATE", "NO_CHANGE_READY_TO_ACTIVATE", "ALREADY_ACTIVE"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
