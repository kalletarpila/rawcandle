from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.research.historical_universe.runner import run_dual


ROOT = Path(__file__).resolve().parents[2]


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description="Run read-only Phase 12C.3 historical-universe audit")
    value.add_argument("--output", type=Path, required=True)
    value.add_argument("--preflight", type=Path, required=True)
    value.add_argument(
        "--source-zip", type=Path,
        default=ROOT / "temp/fundamentals_v4_phase12c/20260910T_STAGE_10Y_C/sharadar_fundamentals_10y.zip",
    )
    value.add_argument(
        "--archive-zip", type=Path,
        default=ROOT / "data/source_archives/sharadar/fundamentals/phase12c_20260910/sharadar_fundamentals_10y.zip",
    )
    return value


def main() -> int:
    args = parser().parse_args()
    paths = {
        "repo_root": ROOT,
        "source_zip": args.source_zip.resolve(), "archive_zip": args.archive_zip.resolve(),
        "provider_db": (ROOT / "data/fundamentals_provider.db").resolve(),
        "canonical_db": (ROOT / "data/fundamentals_v4.db").resolve(),
        "analysis_db": (ROOT / "data/fundamentals_analysis.db").resolve(),
        "market_db": (ROOT / "data/osakedata.db").resolve(),
        "taxonomy_db": (ROOT / "data/analysis.db").resolve(),
    }
    result = run_dual(paths, args.output.resolve(), args.preflight.resolve())
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
