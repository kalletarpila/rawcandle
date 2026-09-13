from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13f4_2_production import run_phase13f4_2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 13F.4.2 structural production deployment")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.apply and not args.confirm_production:
        raise SystemExit("--apply requires --confirm-production")
    result = run_phase13f4_2(args.output, apply=args.apply)
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
