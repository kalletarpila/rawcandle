from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase12d import ROOT
from rawcandle.fundamentals.phase13b_foundation import run_rehearsal


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 13B foundation rehearsal on production-shaped copies")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = run_rehearsal(args.output)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps({
        "ok": True,
        "outcome": result["outcome"],
        "output": str(args.output.relative_to(ROOT) if args.output.is_absolute() and ROOT in args.output.parents else args.output),
        "result_fingerprint": result["result_fingerprint"],
        "second_no_change": result["second_no_change"],
        "production_unchanged": result["production_preflight_postflight"]["identical"],
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
