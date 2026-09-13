from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13f3_2_successor_recovery import run_phase13f3_2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 13F.3.2 copy-only successor fundamentals recovery")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_phase13f3_2(build_parser().parse_args(argv).output)
        print(json.dumps({
            "outcome": result["outcome"],
            "blockers": result["blockers"],
            "report": result["report"],
            "production_immutable": result["production_immutability"]["identical"],
        }, sort_keys=True, allow_nan=False))
        return 0 if not result["blockers"] else 1
    except Exception as exc:
        print(json.dumps({"outcome": "FAILED", "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
