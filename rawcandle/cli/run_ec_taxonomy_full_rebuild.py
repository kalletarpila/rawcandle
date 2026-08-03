from __future__ import annotations

import argparse
import sys

from rawcandle.ec_taxonomy_full_rebuild_orchestrator import (
    render_run_text,
    run_ec_taxonomy_full_rebuild,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a guarded DATACENTER EC taxonomy full rebuild in bounded chunks")
    parser.add_argument("--db", required=True)
    parser.add_argument("--ecosystem", required=True)
    parser.add_argument("--taxonomy-version", required=True)
    parser.add_argument("--taxonomy-csv", required=True)
    parser.add_argument("--watchlist", required=True)
    parser.add_argument("--deployment-id", required=True, type=int)
    parser.add_argument("--date-from", required=True)
    parser.add_argument("--date-to", required=True)
    parser.add_argument("--backup-dir", required=True)
    parser.add_argument("--evidence-output-root", required=True)
    parser.add_argument("--confirm-db", required=True)
    parser.add_argument("--confirm-ecosystem", required=True)
    parser.add_argument("--confirm-taxonomy-version", required=True)
    parser.add_argument("--confirm-deployment-id", required=True, type=int)
    parser.add_argument("--confirm-date-from", required=True)
    parser.add_argument("--confirm-date-to", required=True)
    parser.add_argument("--expected-active-taxonomy-version")
    parser.add_argument("--scheduler-config")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--format", choices=("text",), default="text")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    summary = run_ec_taxonomy_full_rebuild(
        db_path=args.db,
        ecosystem_code=args.ecosystem,
        taxonomy_version_code=args.taxonomy_version,
        taxonomy_csv_path=args.taxonomy_csv,
        watchlist_path=args.watchlist,
        deployment_id=args.deployment_id,
        date_from=args.date_from,
        date_to=args.date_to,
        backup_dir=args.backup_dir,
        evidence_output_root=args.evidence_output_root,
        confirm_db=args.confirm_db,
        confirm_ecosystem=args.confirm_ecosystem,
        confirm_taxonomy_version=args.confirm_taxonomy_version,
        confirm_deployment_id=args.confirm_deployment_id,
        confirm_date_from=args.confirm_date_from,
        confirm_date_to=args.confirm_date_to,
        expected_active_taxonomy_version=args.expected_active_taxonomy_version,
        scheduler_config_path=args.scheduler_config,
        resume=args.resume,
        repo_root=args.repo_root,
    )
    sys.stdout.write(render_run_text(summary) + "\n")
    return 0 if summary.get("overall_status") == "REBUILD_COMPLETED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
