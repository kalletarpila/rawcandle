from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.research.phase12b1_signal_month_audit import run


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit Phase 12B signal-month attrition without rerunning research")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.output), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

