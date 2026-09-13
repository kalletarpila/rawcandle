from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase12d import ROOT
from rawcandle.fundamentals.phase13f4_2_production import run_phase13f4_2


PHASE = "PHASE13F4_3_STRUCTURAL_PRODUCTION_RETRY"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13f4_3_structural_production"
BACKUP_ROOT = ROOT / "backups/fundamentals_v4_phase13f4_3_structural_production"
DEFAULT_RUN_ID = "20260913T_PHASE13F4_3_PRODUCTION_RETRY"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 13F.4.3 structural production deployment retry")
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.apply and not args.confirm_production:
        raise SystemExit("--apply requires --confirm-production")
    result = run_phase13f4_2(
        args.output,
        apply=args.apply,
        phase=PHASE,
        artifact_root=ARTIFACT_ROOT,
        backup_root=BACKUP_ROOT,
        default_run_id=DEFAULT_RUN_ID,
        result_filename="phase13f4_3_result.json",
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
