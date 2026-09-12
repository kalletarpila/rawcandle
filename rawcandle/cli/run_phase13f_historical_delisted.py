from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13f_historical_delisted import run_copy_only_pilot


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 13F AREB historical/delisted copy-only pilot.")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument(
        "--skip-heavy-rebuild",
        action="store_true",
        help="Skip Phase12D candidate package rebuild; intended only for very small smoke tests.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_copy_only_pilot(args.output, run_heavy=not args.skip_heavy_rebuild)
    print(json.dumps({
        "outcome": result["outcome"],
        "artifact_dir": result["artifact_dir"],
        "determinism_fingerprint": result["determinism_fingerprint"],
        "production_immutable": result["production_immutability"]["identical"],
    }, sort_keys=True))
    return 0 if result["outcome"].startswith(("OUTCOME A", "OUTCOME B")) else 2


if __name__ == "__main__":
    raise SystemExit(main())

