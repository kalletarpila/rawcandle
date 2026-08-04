from __future__ import annotations

from rawcandle.datacenter_taxonomy_change_orchestrator import (
    build_inspect_parser,
    inspect_taxonomy_change,
    print_json,
)


def main(argv: list[str] | None = None) -> int:
    args = build_inspect_parser().parse_args(argv)
    summary = inspect_taxonomy_change(
        analysis_db=args.analysis_db,
        deployment_id=args.deployment_id,
        scheduler_config_path=args.scheduler_config,
    )
    print_json(summary)
    return 0 if summary.get("inspect_status") == "OK" else 1


if __name__ == "__main__":
    raise SystemExit(main())
