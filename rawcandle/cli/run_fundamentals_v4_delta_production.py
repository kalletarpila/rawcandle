from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.delta.persistence import LAYOUT_FINGERPRINT, PERSISTENCE_VERSION
from rawcandle.fundamentals.delta.phase5c import _readiness_reconciliation, database_evidence
from rawcandle.fundamentals.delta.production import (
    calculate_production_package,
    deep_authoritative_replay,
    migrate_delta_schema,
    reader_verification,
    refresh_delta,
    validate_expected_source_fingerprints,
    validate_production_request,
)
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_MODEL_FINGERPRINT
from rawcandle.fundamentals.score.engine import MODEL_FINGERPRINT as SCORE_MODEL_FINGERPRINT
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_MODEL_FINGERPRINT


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Deploy Fundamental Delta V1 V2 persistence with exact production gates")
    for name in ("analysis", "canonical", "provider", "market", "taxonomy"):
        parser.add_argument(f"--{name}-db", type=Path, required=True)
    parser.add_argument("--as-of-date", required=True)
    parser.add_argument("--score-model-fingerprint", required=True)
    parser.add_argument("--lifecycle-model-fingerprint", required=True)
    parser.add_argument("--valuation-model-fingerprint", required=True)
    parser.add_argument("--delta-model-fingerprint", required=True)
    parser.add_argument("--persistence-version", required=True)
    parser.add_argument("--layout-fingerprint", required=True)
    parser.add_argument("--fundamental-source-fingerprint", required=True)
    parser.add_argument("--lifecycle-source-fingerprint", required=True)
    parser.add_argument("--valuation-source-fingerprint", required=True)
    parser.add_argument("--economic-package-fingerprint", required=True)
    parser.add_argument("--relative-position-model-fingerprint")
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    parser.add_argument("--deep-replay", action="store_true")
    parser.add_argument("--migrate-only", action="store_true")
    parser.add_argument("--pipeline-smoke", action="store_true")
    return parser


def run(args: argparse.Namespace) -> dict[str, object]:
    if args.migrate_only and not args.apply:
        raise ValueError("DELTA_MIGRATE_ONLY_REQUIRES_APPLY")
    if args.migrate_only and (args.deep_replay or args.pipeline_smoke):
        raise ValueError("DELTA_MIGRATE_ONLY_CANNOT_RUN_REPLAY_OR_SMOKE")
    if args.pipeline_smoke and args.deep_replay:
        raise ValueError("DELTA_PIPELINE_SMOKE_DOES_NOT_RUN_DEEP_REPLAY")
    if args.pipeline_smoke and (not args.apply or not args.relative_position_model_fingerprint):
        raise ValueError("DELTA_PIPELINE_SMOKE_REQUIRES_APPLY_AND_RELATIVE_FINGERPRINT")
    resolved = validate_production_request(
        analysis_db=args.analysis_db, canonical_db=args.canonical_db,
        provider_db=args.provider_db, market_db=args.market_db,
        taxonomy_db=args.taxonomy_db,
        score_model_fingerprint=args.score_model_fingerprint,
        lifecycle_model_fingerprint=args.lifecycle_model_fingerprint,
        valuation_model_fingerprint=args.valuation_model_fingerprint,
        delta_model_fingerprint=args.delta_model_fingerprint,
        persistence_version=args.persistence_version,
        layout_fingerprint=args.layout_fingerprint,
        full_universe=args.full_universe, apply=args.apply,
        confirm_production=args.confirm_production,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated = utc_now()
    before = database_evidence(args.analysis_db)
    source_before = None
    if not args.apply:
        source_before = {
            name: database_evidence(path)
            for name, path in {
                "canonical": args.canonical_db,
                "provider": args.provider_db,
                "market": args.market_db,
                "taxonomy": args.taxonomy_db,
            }.items()
        }
    calculation = calculate_production_package(
        analysis_db=args.analysis_db, canonical_db=args.canonical_db,
        score_model_fingerprint=args.score_model_fingerprint,
        lifecycle_model_fingerprint=args.lifecycle_model_fingerprint,
        valuation_model_fingerprint=args.valuation_model_fingerprint,
    )
    validate_expected_source_fingerprints(
        calculation,
        fundamental_source_fingerprint=args.fundamental_source_fingerprint,
        lifecycle_source_fingerprint=args.lifecycle_source_fingerprint,
        valuation_source_fingerprint=args.valuation_source_fingerprint,
    )
    package = calculation.package
    if package.package_fingerprint != args.economic_package_fingerprint:
        raise RuntimeError("DELTA_ECONOMIC_PACKAGE_FINGERPRINT_CHANGED")
    report: dict[str, object] = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "generated_at_utc": generated,
        "resolved_paths": resolved,
        "full_history": True,
        "model_fingerprint": MODEL_FINGERPRINT,
        "persistence_version": PERSISTENCE_VERSION,
        "layout_fingerprint": LAYOUT_FINGERPRINT,
        "economic_package_fingerprint": package.package_fingerprint,
        "physical_content_fingerprint": calculation.physical_content_fingerprint,
        "source_fingerprints": {
            "fundamental": package.fundamental_source_fingerprint,
            "lifecycle": package.lifecycle_source_fingerprint,
            "valuation": package.valuation_source_fingerprint,
        },
        "result_fingerprints": {
            "fundamental": package.fundamental_result_fingerprint,
            "lifecycle": package.lifecycle_result_fingerprint,
            "valuation": package.valuation_result_fingerprint,
        },
        "rows": {"total": len(package.total_rows), "component": len(package.component_rows), "lifecycle": 0, "valuation": 0},
        "readiness": _readiness_reconciliation(package, as_of_date=args.as_of_date, source=calculation.source),
        "calculation_seconds": calculation.duration_seconds,
        "planned_operations": ["ADDITIVE_V2_SCHEMA", "FULL_HISTORY_APPLY", "ROUTINE_QUICK_CHECK"],
        "deep_replay_requested": args.deep_replay,
        "before": before,
        "production_sources_before": source_before,
    }
    if args.migrate_only:
        report["migration"] = migrate_delta_schema(
            analysis_db=args.analysis_db, applied_at_utc=generated,
        )
    elif args.apply:
        refresh = refresh_delta(
            analysis_db=args.analysis_db, canonical_db=args.canonical_db,
            applied_at_utc=generated,
            score_model_fingerprint=args.score_model_fingerprint,
            lifecycle_model_fingerprint=args.lifecycle_model_fingerprint,
            valuation_model_fingerprint=args.valuation_model_fingerprint,
            calculation=calculation,
        )
        report["apply"] = asdict(refresh)
        report["readers"] = reader_verification(
            analysis_db=args.analysis_db, calculation=calculation,
        )
        if args.deep_replay:
            deep = deep_authoritative_replay(analysis_db=args.analysis_db, calculation=calculation)
            report["deep_replay"] = deep
            if not deep["check"]["ok"]:
                raise RuntimeError(f"DELTA_DEEP_REPLAY_FAILED:{deep['check']['details']}")
        if args.pipeline_smoke:
            from rawcandle.fundamentals.relative_position.production import (
                refresh_relative_position,
                validate_production_request as validate_relative_request,
            )

            validate_relative_request(
                canonical_db=args.canonical_db, provider_db=args.provider_db,
                analysis_db=args.analysis_db, market_db=args.market_db,
                taxonomy_db=args.taxonomy_db,
                model_fingerprint=args.relative_position_model_fingerprint,
                full_universe=True, apply=True, confirm_production=True,
            )
            relative = refresh_relative_position(
                canonical_db=args.canonical_db, analysis_db=args.analysis_db,
                market_db=args.market_db, taxonomy_db=args.taxonomy_db,
                snapshot_date=args.as_of_date,
                model_fingerprint=args.relative_position_model_fingerprint,
                applied_at_utc=generated,
            )
            report["pipeline_smoke"] = {
                "stages": [
                    {"stage": "ABSOLUTE_VALUATION", "status": "SOURCE_READY", "writes": 0},
                    {"stage": "FUNDAMENTAL_DELTA", "status": "COMPLETE", "apply": report["apply"]["apply"]},
                    {"stage": "RELATIVE_POSITION", "status": "COMPLETE", "apply": asdict(relative)["apply"]},
                ],
                "provider_update_triggered": False,
                "deep_replay_triggered": False,
            }
    elif args.deep_replay:
        deep = deep_authoritative_replay(
            analysis_db=args.analysis_db, calculation=calculation,
        )
        report["deep_replay"] = deep
        report["readers"] = reader_verification(
            analysis_db=args.analysis_db, calculation=calculation,
        )
        if not deep["check"]["ok"]:
            raise RuntimeError(f"DELTA_DEEP_REPLAY_FAILED:{deep['check']['details']}")
    after = database_evidence(args.analysis_db)
    report["after"] = after
    if not args.apply:
        source_after = {
            name: database_evidence(path)
            for name, path in {
                "canonical": args.canonical_db,
                "provider": args.provider_db,
                "market": args.market_db,
                "taxonomy": args.taxonomy_db,
            }.items()
        }
        report["production_sources_after"] = source_after
        report["sources_unchanged"] = {
            "analysis": before == after,
            **{name: source_before[name] == value for name, value in source_after.items()},
        }
    report["dry_run_unchanged"] = before == after if not args.apply else None
    operation = "pipeline_smoke" if args.pipeline_smoke else "migration" if args.migrate_only else "apply" if args.apply else "deep_replay" if args.deep_replay else "dry_run"
    output = args.output_dir / f"fundamental_delta_{operation}.json"
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
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
