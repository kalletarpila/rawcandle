from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13e_production_onboarding import (
    ARTIFACT_ROOT,
    DEFAULT_RUN_ID,
    run_phase13e,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run protected Phase 13E SNDK production onboarding")
    parser.add_argument("--output", type=Path, default=ARTIFACT_ROOT / DEFAULT_RUN_ID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    result = run_phase13e(args.output, apply=args.apply)
    print(json.dumps(result, sort_keys=True, allow_nan=False, default=str))
    return 0 if result.get("outcome", "").startswith("OUTCOME A") or result.get("mode") == "DRY_RUN" else 2


if __name__ == "__main__":
    raise SystemExit(main())

