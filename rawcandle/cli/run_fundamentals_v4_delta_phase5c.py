from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rawcandle.fundamentals.delta.phase5c import run_phase5c


def build_parser() -> argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description="Run protected Fundamentals V4 Delta Phase 5C rehearsal")
    for name in ("analysis-db","canonical-db","provider-db","market-db","taxonomy-db","destination"):
        parser.add_argument(f"--{name}",type=Path,required=True)
    parser.add_argument("--as-of-date",required=True)
    parser.add_argument("--score-model-fingerprint",required=True); parser.add_argument("--lifecycle-model-fingerprint",required=True); parser.add_argument("--valuation-model-fingerprint",required=True); parser.add_argument("--delta-model-fingerprint",required=True)
    scope=parser.add_mutually_exclusive_group(required=True); scope.add_argument("--full-universe",action="store_true"); scope.add_argument("--company-id",type=int,action="append",default=[])
    parser.add_argument("--apply",action="store_true"); parser.add_argument("--create-online-copy",action="store_true"); parser.add_argument("--verify-idempotency",action="store_true"); parser.add_argument("--exercise-company-rebuilds",action="store_true"); parser.add_argument("--exercise-failures",action="store_true"); parser.add_argument("--output-dir",type=Path)
    return parser


def main(argv:list[str]|None=None)->int:
    args=build_parser().parse_args(argv)
    try: report=run_phase5c(analysis_db=args.analysis_db,canonical_db=args.canonical_db,provider_db=args.provider_db,market_db=args.market_db,taxonomy_db=args.taxonomy_db,destination=args.destination,as_of_date=args.as_of_date,score_model_fingerprint=args.score_model_fingerprint,lifecycle_model_fingerprint=args.lifecycle_model_fingerprint,valuation_model_fingerprint=args.valuation_model_fingerprint,delta_model_fingerprint=args.delta_model_fingerprint,full_universe=args.full_universe,company_ids=args.company_id,apply=args.apply,create_online_copy=args.create_online_copy,verify_idempotency=args.verify_idempotency,exercise_company_rebuilds=args.exercise_company_rebuilds,exercise_failures=args.exercise_failures,output_dir=args.output_dir)
    except Exception as exc: print(json.dumps({"ok":False,"error":str(exc)},sort_keys=True),file=sys.stderr); return 2
    print(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)); return 0


if __name__=="__main__": raise SystemExit(main())
