from __future__ import annotations

import argparse
from pathlib import Path

from rawcandle.fundamentals.score.engine import ScorePaths, run_score, score_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Fundamentals V4 Simple Fundamental Score V1")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--no-production-write", action="store_true")
    args = parser.parse_args()
    paths = score_paths(args.repo_root)
    if args.artifact_root:
        paths = ScorePaths(
            repo_root=paths.repo_root,
            artifact_root=args.artifact_root,
            canonical_db=paths.canonical_db,
            analysis_db=paths.analysis_db,
            market_db=paths.market_db,
        )
    summary = run_score(paths, write_production=not args.no_production_write)
    print(f"classification={summary['classification']}")
    print(f"artifact_root={summary['artifact_root']}")
    print(f"model_version={summary['model_version']}")
    print(f"model_fingerprint={summary['model_fingerprint']}")
    print(f"score_rows={summary['production']['rows_after']}")
    print(f"status_counts={summary['status_counts']}")
    return 0 if summary["classification"] != "V4_SCORE_V1_IMPLEMENTATION_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
