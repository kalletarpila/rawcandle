from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.relative_valuation.production import (
    BACKUP_DIR,
    PRODUCTION_PATHS,
    run_production,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deploy or refresh the full Relative Valuation production snapshot"
    )
    for name in PRODUCTION_PATHS:
        parser.add_argument(f"--{name}-db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, default=BACKUP_DIR)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--model-fingerprint", required=True)
    parser.add_argument("--persistence-version", required=True)
    parser.add_argument("--layout-fingerprint", required=True)
    parser.add_argument("--expected-active-package", required=True)
    parser.add_argument("--expected-source-fingerprint", required=True)
    parser.add_argument("--expected-result-fingerprint", required=True)
    parser.add_argument("--expected-physical-fingerprint", required=True)
    parser.add_argument("--expected-snapshot-id", required=True)
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        result = run_production(build_parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"outcome": "FAILED", "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, allow_nan=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
