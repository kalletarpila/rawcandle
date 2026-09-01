from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.relative_position.phase4c import database_evidence
from rawcandle.fundamentals.relative_position.production import (
    calculate_current_snapshot,
    reader_smoke,
    refresh_relative_position,
    snapshot_summary,
    validate_production_request,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deploy or smoke-test Relative Position V1 with exact production gates"
    )
    parser.add_argument("--canonical-db", type=Path, required=True)
    parser.add_argument("--provider-db", type=Path, required=True)
    parser.add_argument("--analysis-db", type=Path, required=True)
    parser.add_argument("--market-db", type=Path, required=True)
    parser.add_argument("--taxonomy-db", type=Path, required=True)
    parser.add_argument("--snapshot-date", required=True)
    parser.add_argument("--model-fingerprint", required=True)
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    parser.add_argument("--pipeline-smoke", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.pipeline_smoke and not args.apply:
        raise ValueError("RELATIVE_POSITION_PIPELINE_SMOKE_REQUIRES_APPLY")
    resolved = validate_production_request(
        canonical_db=args.canonical_db,
        provider_db=args.provider_db,
        analysis_db=args.analysis_db,
        market_db=args.market_db,
        taxonomy_db=args.taxonomy_db,
        model_fingerprint=args.model_fingerprint,
        full_universe=args.full_universe,
        apply=args.apply,
        confirm_production=args.confirm_production,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated = utc_now()
    preflight = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "pipeline_smoke": args.pipeline_smoke,
        "resolved_paths": resolved,
        "model_fingerprint": MODEL_FINGERPRINT,
        "scope": "FULL_UNIVERSE",
        "snapshot_date": args.snapshot_date,
    }
    preflight_path = args.output_dir / "relative_position_production_preflight.json"
    preflight_path.write_text(
        json.dumps(preflight, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    before = {
        name: database_evidence(path) for name, path in {
            "canonical": args.canonical_db,
            "analysis": args.analysis_db,
            "market": args.market_db,
            "taxonomy": args.taxonomy_db,
        }.items()
    }
    snapshot = calculate_current_snapshot(
        canonical_db=args.canonical_db,
        analysis_db=args.analysis_db,
        market_db=args.market_db,
        taxonomy_db=args.taxonomy_db,
        snapshot_date=args.snapshot_date,
    )
    report: dict[str, object] = {
        "preflight": preflight,
        "generated_at_utc": generated,
        "before": before,
        "source_fingerprint": snapshot.source_fingerprint,
        "result_fingerprint": snapshot.result_fingerprint,
        "calculation": snapshot_summary(snapshot),
        "planned_schema_migration": True,
        "planned_full_snapshot_apply": True,
    }
    if args.apply:
        refresh = refresh_relative_position(
            canonical_db=args.canonical_db,
            analysis_db=args.analysis_db,
            market_db=args.market_db,
            taxonomy_db=args.taxonomy_db,
            snapshot_date=args.snapshot_date,
            model_fingerprint=args.model_fingerprint,
            applied_at_utc=generated,
            expected_source_fingerprint=snapshot.source_fingerprint,
            expected_result_fingerprint=snapshot.result_fingerprint,
        )
        report["apply"] = asdict(refresh)
        report["readers"] = reader_smoke(args.analysis_db)
        if args.pipeline_smoke:
            report["pipeline_hook"] = {
                "stage": "AFTER_ABSOLUTE_VALUATION",
                "provider_update_triggered": False,
                "status": "COMPLETE",
                "outcome": refresh.apply["outcome"],
            }
    report["after"] = {
        name: database_evidence(path) for name, path in {
            "canonical": args.canonical_db,
            "analysis": args.analysis_db,
            "market": args.market_db,
            "taxonomy": args.taxonomy_db,
        }.items()
    }
    output = args.output_dir / (
        "relative_position_pipeline_smoke.json"
        if args.pipeline_smoke else
        f"relative_position_{'apply' if args.apply else 'dry_run'}.json"
    )
    output.write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    report["report_path"] = str(output.resolve())
    return report


def main(argv: list[str] | None = None) -> int:
    try:
        report = run(build_parser().parse_args(argv))
    except Exception as exc:
        print(json.dumps({"error": str(exc), "ok": False}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
