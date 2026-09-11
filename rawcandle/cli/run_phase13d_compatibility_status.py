from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase13d_backend import Phase13DPaths, compatibility_status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect Phase 13D Relative Valuation dependency compatibility")
    parser.add_argument("--provider-db", required=True, type=Path)
    parser.add_argument("--canonical-db", required=True, type=Path)
    parser.add_argument("--analysis-db", required=True, type=Path)
    parser.add_argument("--market-db", required=True, type=Path)
    parser.add_argument("--taxonomy-db", required=True, type=Path)
    parser.add_argument("--report-date", required=True)
    args = parser.parse_args(argv)
    try:
        paths = Phase13DPaths(args.provider_db, args.canonical_db, args.analysis_db, args.market_db, args.taxonomy_db)
        print(json.dumps({"ok": True, "compatibility": compatibility_status(paths, report_date=args.report_date)}, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": type(exc).__name__, "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
