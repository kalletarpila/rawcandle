from __future__ import annotations

from rawcandle.datacenter_taxonomy_replacement import (
    build_plan_change_parser,
    plan_datacenter_taxonomy_change,
    print_json,
)


def main(argv: list[str] | None = None) -> int:
    args = build_plan_change_parser().parse_args(argv)
    summary = plan_datacenter_taxonomy_change(
        analysis_db=args.analysis_db,
        current_taxonomy_version=args.current_taxonomy_version,
        current_taxonomy_csv=args.current_taxonomy_csv,
        proposed_taxonomy_version=args.proposed_taxonomy_version,
        proposed_taxonomy_csv=args.proposed_taxonomy_csv,
        ecosystem_code=args.ecosystem,
        rebuild_start_date=args.rebuild_start_date,
    )
    print_json(summary)
    return 0 if summary["taxonomy_plan_status"] != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
