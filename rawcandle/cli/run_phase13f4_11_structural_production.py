from __future__ import annotations

import argparse
import json
from pathlib import Path

from rawcandle.fundamentals.phase12d import ROOT
from rawcandle.fundamentals.phase13f4_2_production import run_phase13f4_2


PHASE = "PHASE13F4_11_FINAL_STRUCTURAL_REGIME_PRODUCTION_ACTIVATION"
ARTIFACT_ROOT = ROOT / "temp/fundamentals_v4_phase13f4_11_structural_production"
BACKUP_ROOT = ROOT / "backups/fundamentals_v4_phase13f4_11_structural_production"
DEFAULT_RUN_ID = "20260914T_PHASE13F4_11_PRODUCTION_ACTIVATION"

OUTCOME_A = "OUTCOME A — STRUCTURAL-REGIME PACKAGE AND RELATIVE VALUATION ACTIVE AND STABLE IN PRODUCTION"
OUTCOME_B = "OUTCOME B — PRE-WRITE BLOCKER; PRODUCTION REMAINS UNCHANGED"
OUTCOME_C = "OUTCOME C — MATERIAL DEPLOYMENT FAILURE; COMPLETE BACKUP SET RESTORED"
OUTCOME_D = "OUTCOME D — DEPLOYMENT STATE OR ROLLBACK COULD NOT BE PROVEN"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run Phase 13F.4.11 structural production activation")
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
        result_filename="phase13f4_11_result.json",
        outcome_a=OUTCOME_A,
        outcome_b=OUTCOME_B,
        outcome_c=OUTCOME_C,
        outcome_d=OUTCOME_D,
    )
    print(json.dumps(result, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
