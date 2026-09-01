from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.valuation.persistence import logical_fingerprint
from rawcandle.fundamentals.valuation.phase3c import (
    database_evidence,
    distribution_summary,
    utc_now,
    zero_score_audit,
)
from rawcandle.fundamentals.valuation.production import (
    apply_canonical_production,
    calculate_valuation_rows,
    refresh_valuation,
    validate_production_request,
)


LOCKED_SOURCE_FINGERPRINT = "e552cf0b01a1e649d6269a968c4ea7e96b903acccce9c8b73d21d7c6cd230e47"
LOCKED_RESULT_FINGERPRINT = "46bdde9bd6711180b9bc1b75462c42c39e2ff5498ee93ad0c711cbbf88e69a18"
CURRENT_AS_OF_DATE = "2026-09-01"
CURRENT_FRESHNESS_DAYS = 180


def _current_universe(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    as_of = date.fromisoformat(CURRENT_AS_OF_DATE)
    latest: dict[int, dict[str, object]] = {}
    for row in rows:
        available = row.get("fundamental_available_date")
        if not available or str(available) > CURRENT_AS_OF_DATE:
            continue
        company_id = int(row["company_id"])
        if company_id not in latest or int(row["fiscal_sequence"]) > int(latest[company_id]["fiscal_sequence"]):
            latest[company_id] = row
    return [
        row for row in latest.values()
        if (as_of - date.fromisoformat(str(row["fundamental_available_date"]))).days <= CURRENT_FRESHNESS_DAYS
    ]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy Fundamentals V4 Valuation V1 in explicit production stages")
    parser.add_argument("--stage", choices=("canonical", "valuation"), required=True)
    parser.add_argument("--canonical-db", type=Path, required=True)
    parser.add_argument("--provider-db", type=Path, required=True)
    parser.add_argument("--analysis-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--model-fingerprint", required=True)
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    resolved = validate_production_request(
        canonical_db=args.canonical_db,
        provider_db=args.provider_db,
        analysis_db=args.analysis_db,
        market_db=args.market_db,
        model_fingerprint=args.model_fingerprint,
        full_universe=args.full_universe,
        apply=args.apply,
        confirm_production=args.confirm_production,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    preflight = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "resolved_paths": resolved,
        "model_fingerprint": MODEL_FINGERPRINT,
        "scope": "FULL_UNIVERSE",
        "stage": args.stage,
    }
    preflight_path = args.output_dir / f"{args.stage}_production_preflight.json"
    preflight_path.write_text(
        json.dumps(preflight, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"production_preflight": preflight}, sort_keys=True), flush=True)
    generated = utc_now()
    report: dict[str, object] = {
        "stage": args.stage,
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "resolved_paths": resolved,
        "model_fingerprint": MODEL_FINGERPRINT,
        "scope": "FULL_UNIVERSE",
        "generated_at_utc": generated,
        "preflight_path": str(preflight_path.resolve()),
        "before": {
            "canonical": database_evidence(args.canonical_db),
            "analysis": database_evidence(args.analysis_db),
            "market": database_evidence(args.market_db),
        },
    }
    if args.stage == "canonical":
        report["canonical_migration"] = (
            apply_canonical_production(args.canonical_db, args.provider_db, applied_at_utc=generated)
            if args.apply else {"planned": True, "writes": "canonical_only"}
        )
    else:
        source_fingerprint, rows = calculate_valuation_rows(
            args.canonical_db, args.market_db, calculated_at=generated
        )
        result_fingerprint = logical_fingerprint(rows)
        audit = zero_score_audit(rows)
        current = _current_universe(rows)
        report.update({
            "source_fingerprint": source_fingerprint,
            "result_fingerprint": result_fingerprint,
            "historical_distribution": distribution_summary(rows),
            "current_universe": {
                "as_of_date": CURRENT_AS_OF_DATE,
                "freshness_days": CURRENT_FRESHNESS_DAYS,
                **distribution_summary(current),
            },
            "zero_score_audit": audit,
            "planned_rows": len(rows),
            "planned_schema": "valuation_revised_result",
            "planned_write_count": len(rows),
        })
        if source_fingerprint != LOCKED_SOURCE_FINGERPRINT or result_fingerprint != LOCKED_RESULT_FINGERPRINT:
            raise RuntimeError("LOCKED_VALUATION_FINGERPRINT_GATE_FAILED")
        if args.apply:
            report["valuation_apply"] = asdict(refresh_valuation(
                args.canonical_db,
                args.analysis_db,
                args.market_db,
                calculated_at=generated,
            ))
    report["after"] = {
        "canonical": database_evidence(args.canonical_db),
        "analysis": database_evidence(args.analysis_db),
        "market": database_evidence(args.market_db),
    }
    output = args.output_dir / f"{args.stage}_{report['mode'].lower()}.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    report["report_path"] = str(output.resolve())
    return report


def main(argv: list[str] | None = None) -> int:
    try:
        report = run(build_parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
