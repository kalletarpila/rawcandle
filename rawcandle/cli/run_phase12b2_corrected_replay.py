from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from rawcandle.fundamentals.phase12d import PRODUCTION, ROOT
from rawcandle.research.fundamental_profile_baseline.source import ResearchPaths
from rawcandle.research.fundamental_profile_baseline_v2.contract import CONTRACT_FINGERPRINT
from rawcandle.research.fundamental_profile_baseline_v2.runner import run


PHASE12D = ROOT / "temp/fundamentals_v4_phase12d/20260910T_PHASE12D_REHEARSAL_V7"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the frozen Phase 12B.2 corrected retrospective replay")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    candidate = PHASE12D / "candidate_a"
    result = run(
        ResearchPaths(candidate / "fundamentals_v4.db", candidate / "fundamentals_analysis.db", candidate / "fundamentals_provider.db", PRODUCTION["market"], PRODUCTION["taxonomy"]),
        args.output,
        contract_fingerprint=CONTRACT_FINGERPRINT,
        original_dir=candidate / "phase12b_replay",
    )
    print(json.dumps(asdict(result), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
