from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from rawcandle.fundamentals.providers.sharadar import resolve_api_key
from rawcandle.fundamentals.schema.production_bootstrap import production_paths, run_production_bootstrap
from rawcandle.fundamentals.schema.sharadar_history_policy import MINIMUM_HISTORY_YEARS


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"Bootstrap production Fundamentals V4 from Sharadar fundamentals (minimum {MINIMUM_HISTORY_YEARS} years)"
    )
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--bootstrap-csv", type=Path)
    parser.add_argument(
        "--history-years", type=int, default=None,
        help=f"Requested fundamentals history; minimum and default is {MINIMUM_HISTORY_YEARS}",
    )
    return parser.parse_args(argv)


def git_status_short(repo_root: Path) -> str:
    result = subprocess.run(["git", "status", "--short"], cwd=repo_root, check=True, text=True, capture_output=True)
    return result.stdout


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_root = Path.cwd()
    paths = production_paths(repo_root, bootstrap_csv=args.bootstrap_csv)
    if args.artifact_root:
        paths = paths.__class__(
            repo_root=paths.repo_root,
            artifact_root=args.artifact_root,
            provider_db=paths.provider_db,
            canonical_db=paths.canonical_db,
            analysis_db=paths.analysis_db,
            bootstrap_csv=paths.bootstrap_csv,
            bulk_zip_path=args.artifact_root / "sharadar_fundamentals.zip",
            extracted_csv_path=args.artifact_root / "sharadar_fundamentals.csv",
        )
    try:
        api_key = resolve_api_key()
    except RuntimeError:
        api_key = None
    summary = run_production_bootstrap(
        paths, history_years=args.history_years, api_key=api_key,
        git_status=git_status_short(repo_root),
    )
    print(f"classification={summary['classification']}")
    print(f"artifact_root={summary['artifact_root']}")
    if "production_paths" in summary:
        print(f"provider_db={summary['production_paths']['provider_db']}")
        print(f"canonical_db={summary['production_paths']['canonical_db']}")
        print(f"analysis_db={summary['production_paths']['analysis_db']}")
    print(f"next_action={summary['next_action']}")
    return 0 if summary["classification"] != "V4_PRODUCTION_BOOTSTRAP_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
