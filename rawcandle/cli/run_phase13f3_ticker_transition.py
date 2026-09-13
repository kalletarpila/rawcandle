from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13f3_ticker_transition import run_phase13f3


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 13F.3 ticker-transition copy-only reconciliation.")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_phase13f3(args.output)
    print(json.dumps({
        "outcome": result["outcome"],
        "artifact_dir": str(Path(result["report"]["path"]).parent),
        "blockers": result["blockers"],
        "determinism": result["determinism"]["match"],
        "production_immutable": result["production_immutability"]["identical"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
