from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.score.calibration import run_score_calibration, score_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Fundamentals V4-3A continuous score scaling phase")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--no-durable-docs", action="store_true")
    args = parser.parse_args()
    paths = score_paths(args.repo_root)
    if args.artifact_root:
        paths = paths.__class__(
            repo_root=paths.repo_root,
            artifact_root=args.artifact_root,
            canonical_db=paths.canonical_db,
            analysis_db=paths.analysis_db,
            provider_db=paths.provider_db,
            known_gaps_doc=paths.known_gaps_doc,
        )
    summary = run_score_calibration(paths, write_durable_docs=not args.no_durable_docs)
    print(f"classification={summary['classification']}")
    print(f"artifact_root={summary['artifact_root']}")
    print(f"score_semantic={summary['philosophy']['score_semantic']}")
    print(f"delta_score_semantic={summary['philosophy']['delta_score_semantic']}")
    print(f"model_fingerprint={summary['model_lock']['model_fingerprint']}")
    print(json.dumps(summary["production_safety"], sort_keys=True))
    print(f"next_action={summary['next_action']}")
    return 0 if summary["classification"] != "V4_SCORE_V1_CONTINUOUS_SCALING_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
