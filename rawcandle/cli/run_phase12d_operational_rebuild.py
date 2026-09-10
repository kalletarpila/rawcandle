from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase12d import ROOT, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the isolated Phase 12D ten-year operational rebuild rehearsal"
    )
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        result = run(args.output)
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0
    except Exception as exc:
        print(json.dumps({
            "outcome": "OUTCOME C - REBUILD OR RECONCILIATION FAILED; PRODUCTION DEPLOYMENT BLOCKED",
            "error": type(exc).__name__, "reason": str(exc), "repo": str(ROOT),
        }, sort_keys=True, separators=(",", ":")))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
