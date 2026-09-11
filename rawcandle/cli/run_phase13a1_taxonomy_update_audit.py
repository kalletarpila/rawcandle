from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase12d import ROOT
from rawcandle.research.phase13a1_taxonomy_update import AuditPaths, run, utc_stamp


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 13A.1 taxonomy-update readiness audit")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Artifact directory. Defaults under temp/fundamentals_v4_phase13a1_taxonomy_update/<timestamp>.",
    )
    args = parser.parse_args(argv)
    output = args.output or ROOT / "temp" / "fundamentals_v4_phase13a1_taxonomy_update" / utc_stamp()
    try:
        result = run(AuditPaths(output=output))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
