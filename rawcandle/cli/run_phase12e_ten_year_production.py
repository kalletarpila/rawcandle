from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase12e import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy the rehearsed ten-year Fundamentals V4 history")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run(args.output, apply=args.apply, confirm_production=args.confirm_production)
    except Exception as exc:
        print(json.dumps({"outcome": "FAILED", "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
