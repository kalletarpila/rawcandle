from __future__ import annotations

from rawcandle.datacenter_taxonomy_replacement import (
    apply_datacenter_taxonomy_version,
    build_apply_version_parser,
    print_json,
)


def main(argv: list[str] | None = None) -> int:
    args = build_apply_version_parser().parse_args(argv)
    summary = apply_datacenter_taxonomy_version(
        analysis_db=args.analysis_db,
        current_taxonomy_version=args.current_taxonomy_version,
        current_taxonomy_csv=args.current_taxonomy_csv,
        proposed_taxonomy_version=args.proposed_taxonomy_version,
        proposed_taxonomy_csv=args.proposed_taxonomy_csv,
        confirm_proposed_taxonomy_version=args.confirm_proposed_taxonomy_version,
        ecosystem_code=args.ecosystem,
        invocation_source=args.invocation_source,
        rebuild_start_date=args.rebuild_start_date,
    )
    print_json(summary)
    return 0 if summary["taxonomy_apply_status"] != "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
