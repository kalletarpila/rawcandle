from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13d1_real_source import ARTIFACT_ROOT, run_rehearsal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 13D.1 real-source copy-only onboarding rehearsal")
    parser.add_argument("--output", type=Path, default=ARTIFACT_ROOT / "20260912T_PHASE13D1_REAL_SOURCE")
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(args.output)
        print(json.dumps({"ok": True, **result}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
