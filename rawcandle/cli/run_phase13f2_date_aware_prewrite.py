from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13f2_date_aware_policy import run_prewrite_audit


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 13F.2 date-aware listing eligibility pre-write audit.")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_prewrite_audit(args.output)
    print(json.dumps({
        "outcome": result["outcome"],
        "artifact_dir": str(args.output) if args.output else str(Path(result["report"]["path"]).parent),
        "determinism_fingerprint": result["determinism_fingerprint"],
        "production_immutable": result["production_immutability"]["identical"],
        "prewrite_blockers": result["prewrite_blockers"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
