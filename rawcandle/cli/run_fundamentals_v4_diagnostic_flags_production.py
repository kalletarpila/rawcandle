from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT as DELTA_FINGERPRINT
from rawcandle.fundamentals.delta.persistence import (
    LAYOUT_FINGERPRINT as DELTA_LAYOUT_FINGERPRINT,
    PERSISTENCE_VERSION as DELTA_PERSISTENCE_VERSION,
)
from rawcandle.fundamentals.diagnostic_flags.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.diagnostic_flags.persistence import (
    LAYOUT_FINGERPRINT,
    PERSISTENCE_VERSION,
)
from rawcandle.fundamentals.diagnostic_flags.production import (
    calculate_production_package,
    deep_authoritative_replay,
    migrate_diagnostic_schema,
    reader_verification,
    refresh_diagnostic_flags,
    validate_production_request,
)
from rawcandle.fundamentals.relative_position.engine import MODEL_FINGERPRINT as RELATIVE_FINGERPRINT
from rawcandle.fundamentals.schema.migrations import migrate_valuation_foundation
from rawcandle.fundamentals.schema.operating_working_capital import (
    migrate_and_backfill_operating_working_capital,
)
from rawcandle.fundamentals.score.engine import ScorePaths, refresh_post_valuation_stages


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deploy Diagnostic Flags V1 with exact Phase 6D production gates"
    )
    for name in ("analysis", "canonical", "provider", "market", "taxonomy"):
        parser.add_argument(f"--{name}-db", type=Path, required=True)
    parser.add_argument("--model-fingerprint", required=True)
    parser.add_argument("--persistence-version", required=True)
    parser.add_argument("--layout-fingerprint", required=True)
    parser.add_argument("--expected-source-fingerprint", required=True)
    parser.add_argument("--expected-economic-result-fingerprint", required=True)
    parser.add_argument("--expected-package-fingerprint", required=True)
    parser.add_argument("--expected-content-fingerprint", required=True)
    parser.add_argument("--full-universe", action="store_true")
    parser.add_argument("--as-of-date")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--confirm-production", action="store_true")
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--provider-compatibility", action="store_true")
    operations.add_argument("--working-capital", action="store_true")
    operations.add_argument("--diagnostic-schema", action="store_true")
    operations.add_argument("--deep-replay", action="store_true")
    operations.add_argument("--pipeline-smoke", action="store_true")
    return parser


def _database_check(path: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        return {
            "quick_check": connection.execute("PRAGMA quick_check").fetchone()[0],
            "foreign_key_violations": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "page_count": connection.execute("PRAGMA page_count").fetchone()[0],
            "freelist_count": connection.execute("PRAGMA freelist_count").fetchone()[0],
        }


def _validate_expected(calculation: Any, args: argparse.Namespace) -> None:
    expected = {
        "SOURCE": (args.expected_source_fingerprint, calculation.package.source_fingerprint),
        "ECONOMIC_RESULT": (
            args.expected_economic_result_fingerprint,
            calculation.package.economic_result_fingerprint,
        ),
        "PACKAGE": (args.expected_package_fingerprint, calculation.package.package_fingerprint),
    }
    for name, (supplied, actual) in expected.items():
        if supplied != actual:
            raise RuntimeError(f"DIAGNOSTIC_{name}_FINGERPRINT_CHANGED:{actual}")
    if args.expected_content_fingerprint != calculation.physical_content_fingerprint:
        raise RuntimeError(
            "DIAGNOSTIC_CONTENT_FINGERPRINT_CHANGED:"
            f"{calculation.physical_content_fingerprint}"
        )


def run(args: argparse.Namespace) -> dict[str, Any]:
    if any(
        (args.provider_compatibility, args.working_capital, args.diagnostic_schema)
    ) and not args.apply:
        raise ValueError("DIAGNOSTIC_MIGRATION_OPERATION_REQUIRES_APPLY")
    if args.pipeline_smoke and not args.apply:
        raise ValueError("DIAGNOSTIC_PIPELINE_SMOKE_REQUIRES_APPLY")
    if args.pipeline_smoke and not args.as_of_date:
        raise ValueError("DIAGNOSTIC_PIPELINE_SMOKE_REQUIRES_AS_OF_DATE")
    resolved = validate_production_request(
        analysis_db=args.analysis_db,
        canonical_db=args.canonical_db,
        provider_db=args.provider_db,
        market_db=args.market_db,
        taxonomy_db=args.taxonomy_db,
        model_fingerprint=args.model_fingerprint,
        persistence_version=args.persistence_version,
        layout_fingerprint=args.layout_fingerprint,
        full_universe=args.full_universe,
        apply=args.apply,
        confirm_production=args.confirm_production,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    generated = utc_now()
    report: dict[str, Any] = {
        "mode": "APPLY" if args.apply else "DRY_RUN",
        "generated_at_utc": generated,
        "resolved_paths": resolved,
        "model_fingerprint": MODEL_FINGERPRINT,
        "persistence_version": PERSISTENCE_VERSION,
        "layout_fingerprint": LAYOUT_FINGERPRINT,
        "provider_update_triggered": False,
    }
    if args.provider_compatibility:
        report["provider_compatibility"] = migrate_valuation_foundation(
            args.provider_db,
            args.canonical_db,
            generated,
            allow_production=True,
        )
        report["provider_check"] = _database_check(args.provider_db)
        report["canonical_check"] = _database_check(args.canonical_db)
    elif args.working_capital:
        report["working_capital"] = migrate_and_backfill_operating_working_capital(
            args.provider_db,
            args.canonical_db,
            generated,
            allow_production=True,
        )
        report["provider_check"] = _database_check(args.provider_db)
        report["canonical_check"] = _database_check(args.canonical_db)
    elif args.diagnostic_schema:
        report["diagnostic_schema"] = migrate_diagnostic_schema(
            analysis_db=args.analysis_db
        )
    else:
        calculation = calculate_production_package(
            analysis_db=args.analysis_db, canonical_db=args.canonical_db
        )
        _validate_expected(calculation, args)
        report.update(
            source_fingerprint=calculation.package.source_fingerprint,
            economic_result_fingerprint=calculation.package.economic_result_fingerprint,
            package_fingerprint=calculation.package.package_fingerprint,
            physical_content_fingerprint=calculation.physical_content_fingerprint,
            endpoint_count=len(calculation.package.endpoints),
            evaluation_count=len(calculation.package.evaluations),
            calculation_seconds=calculation.duration_seconds,
        )
        if args.apply:
            report["diagnostic_refresh"] = refresh_diagnostic_flags(
                analysis_db=args.analysis_db,
                canonical_db=args.canonical_db,
                applied_at_utc=generated,
                calculation=calculation,
            )
            content = report["diagnostic_refresh"]["physical_content_fingerprint"]
            if content != args.expected_content_fingerprint:
                raise RuntimeError(
                    f"DIAGNOSTIC_CONTENT_FINGERPRINT_CHANGED:{content}"
                )
        if args.deep_replay:
            report["deep_replay"] = deep_authoritative_replay(
                analysis_db=args.analysis_db, calculation=calculation
            )
            if not report["deep_replay"]["check"]["ok"]:
                raise RuntimeError("DIAGNOSTIC_DEEP_REPLAY_FAILED")
        if args.apply or args.deep_replay:
            report["readers"] = reader_verification(
                analysis_db=args.analysis_db, calculation=calculation
            )
        if args.pipeline_smoke:
            paths = ScorePaths(
                args.analysis_db.parent.parent,
                args.output_dir / "unused_score_artifacts",
                args.canonical_db,
                args.analysis_db,
                args.market_db,
            )
            report["pipeline_smoke"] = refresh_post_valuation_stages(
                paths,
                diagnostic_model_fingerprint=MODEL_FINGERPRINT,
                diagnostic_persistence_version=PERSISTENCE_VERSION,
                diagnostic_layout_fingerprint=LAYOUT_FINGERPRINT,
                delta_model_fingerprint=DELTA_FINGERPRINT,
                delta_persistence_version=DELTA_PERSISTENCE_VERSION,
                delta_layout_fingerprint=DELTA_LAYOUT_FINGERPRINT,
                relative_position_model_fingerprint=RELATIVE_FINGERPRINT,
                relative_position_snapshot_date=args.as_of_date,
            )
    (args.output_dir / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return report


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = run(args)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
