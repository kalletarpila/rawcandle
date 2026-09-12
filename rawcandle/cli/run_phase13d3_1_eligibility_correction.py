from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13d3_1_eligibility_correction import ARTIFACT_ROOT, DEFAULT_RUN_ID, run_correction


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 13D.3.1 read-only eligibility correction audit")
    parser.add_argument("--output", type=Path, default=ARTIFACT_ROOT / DEFAULT_RUN_ID)
    args = parser.parse_args(argv)
    try:
        result = run_correction(args.output)
        print(json.dumps({"ok": True, **result}, sort_keys=True, default=str))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
