from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.ttm.engine import run_v4_ttm, ttm_paths


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Fundamentals V4 EBIT-first TTM migration")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--no-production-write", action="store_true")
    args = parser.parse_args()
    paths = ttm_paths(args.repo_root)
    if args.artifact_root:
        paths = paths.__class__(
            repo_root=paths.repo_root,
            artifact_root=args.artifact_root,
            provider_db=paths.provider_db,
            canonical_db=paths.canonical_db,
            analysis_db=paths.analysis_db,
            v3_db=paths.v3_db,
            v4_1b1_artifact_root=paths.v4_1b1_artifact_root,
        )
    summary = run_v4_ttm(paths, write_production=not args.no_production_write)
    print(f"classification={summary['classification']}")
    print(f"artifact_root={summary['artifact_root']}")
    print(f"ttm_ready={summary['ttm_readiness']['TTM_READY']}")
    print(f"ttm_not_ready={summary['ttm_readiness']['TTM_NOT_READY']}")
    print(f"ttm_rows={summary['production']['ttm_rows_written']}")
    print(f"next_action={summary['next_action']}")
    print(json.dumps({"math_mismatches": summary["math_validation"]["mathematical_logic_mismatches"], "engine_logic_differences": summary["v3_v4_parity"].get("ENGINE_LOGIC_DIFFERENCE", 0)}, sort_keys=True))
    return 0 if summary["classification"] != "V4_TTM_MIGRATION_BLOCKED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
