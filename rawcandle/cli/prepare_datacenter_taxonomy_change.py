from __future__ import annotations

from rawcandle.datacenter_taxonomy_change_orchestrator import (
    build_prepare_parser,
    prepare_taxonomy_change,
    print_json,
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
    print_json(summary)
    return 0 if summary.get("prepare_status") in {"READY_TO_REBUILD", "PLAN_READY"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
