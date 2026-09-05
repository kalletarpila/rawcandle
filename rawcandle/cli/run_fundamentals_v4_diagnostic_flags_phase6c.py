from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.diagnostic_flags.phase6c import run_phase6c


def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description="Run protected Diagnostic Flags Phase 6C persistence rehearsal")
    parser.add_argument("--canonical-db",type=Path,required=True); parser.add_argument("--analysis-db",type=Path,required=True)
    parser.add_argument("--destination",type=Path,required=True); parser.add_argument("--model-fingerprint",required=True)
    scope=parser.add_mutually_exclusive_group(required=True); scope.add_argument("--full-universe",action="store_true"); scope.add_argument("--company-id",type=int,action="append",default=[])
    parser.add_argument("--apply",action="store_true"); parser.add_argument("--applied-at-utc",default="")
    return parser


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try: report=run_phase6c(canonical_db=args.canonical_db,analysis_db=args.analysis_db,destination=args.destination,model_fingerprint=args.model_fingerprint,full_universe=args.full_universe,company_ids=args.company_id,apply=args.apply,applied_at_utc=args.applied_at_utc)
    except Exception as exc: print(json.dumps({"ok":False,"error":str(exc)},sort_keys=True),file=sys.stderr); return 2
    print(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)); return 0


if __name__=="__main__": raise SystemExit(main())
