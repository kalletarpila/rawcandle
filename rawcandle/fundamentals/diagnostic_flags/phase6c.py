from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Sequence

from rawcandle.fundamentals.diagnostic_flags.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.diagnostic_flags.persistence import apply_package, build_persistence_package, ensure_schema, quick_check
from rawcandle.fundamentals.diagnostic_flags.source import ReadOnlyDiagnosticPaths, load_diagnostic_source


PRODUCTION_DATABASES = {
    (Path(__file__).resolve().parents[3] / "data" / name).resolve()
    for name in ("fundamentals_provider.db", "fundamentals_v4.db", "fundamentals_analysis.db", "osakedata.db", "analysis.db")
}

PIPELINE_PLACEMENT = {
    "prerequisites": ("CANONICAL_TTM", "SCORE_TRAJECTORY", "LIFECYCLE_APPLICABILITY", "ABSOLUTE_VALUATION", "WORKING_CAPITAL_FIELDS"),
    "after": "VALUATION_REFRESH_COMMITTED",
    "before": ("DELTA_REFRESH", "RELATIVE_POSITION_REFRESH"),
    "delta_is_prerequisite": False,
    "relative_position_is_prerequisite": False,
    "failure_isolation": "REPORT_DIAGNOSTIC_STAGE_FAILED_WITHOUT_ROLLING_BACK_COMMITTED_UPSTREAM_STAGES",
    "changed_company_policy": "FULL_HISTORY_FALLBACK_UNTIL_RELIABLE_COMPLETE_CHANGED_COMPANY_SET_EXISTS",
    "phase6c_activation": False,
}


def validate_request(*, canonical_db: Path, analysis_db: Path, destination: Path,
                     model_fingerprint: str, company_ids: Sequence[int], full_universe: bool) -> None:
    if model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("DIAGNOSTIC_MODEL_FINGERPRINT_REJECTED")
    if bool(company_ids) == bool(full_universe):
        raise ValueError("DIAGNOSTIC_EXACTLY_ONE_SCOPE_REQUIRED")
    supplied = (canonical_db, analysis_db, destination)
    if any(not path.is_absolute() for path in supplied):
        raise ValueError("DIAGNOSTIC_ABSOLUTE_DATABASE_PATHS_REQUIRED")
    if any(path.is_symlink() for path in supplied):
        raise PermissionError("DIAGNOSTIC_SYMLINK_PATH_BLOCKED")
    if canonical_db.resolve() == analysis_db.resolve():
        raise ValueError("DIAGNOSTIC_SOURCE_DATABASES_MUST_BE_DISTINCT")
    resolved_destination = destination.resolve()
    if resolved_destination in PRODUCTION_DATABASES:
        raise PermissionError("DIAGNOSTIC_PRODUCTION_DESTINATION_BLOCKED")
    if resolved_destination == canonical_db.resolve():
        raise PermissionError("DIAGNOSTIC_DESTINATION_IS_CANONICAL_SOURCE")
    if resolved_destination.parent == (Path(__file__).resolve().parents[3] / "data").resolve():
        raise PermissionError("DIAGNOSTIC_DATA_DIRECTORY_DESTINATION_BLOCKED")
    if destination.exists():
        with sqlite3.connect(f"file:{destination}?mode=ro", uri=True) as connection:
            tables = {row[0] for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE type='table'"
            )}
        wrong_destination_markers = {
            "provider_observation", "v4_quarter", "osakedata", "daily", "prices",
            "ec_taxonomy_version", "dc_ecosystem_membership",
        }
        if tables & wrong_destination_markers:
            raise PermissionError("DIAGNOSTIC_INCORRECT_DESTINATION_DATABASE")


def run_phase6c(*, canonical_db: Path, analysis_db: Path, destination: Path,
                model_fingerprint: str, full_universe: bool, company_ids: Sequence[int] = (),
                apply: bool = False, applied_at_utc: str = "") -> dict[str, Any]:
    validate_request(canonical_db=canonical_db,analysis_db=analysis_db,destination=destination,
                     model_fingerprint=model_fingerprint,company_ids=company_ids,full_universe=full_universe)
    started=time.perf_counter(); source=load_diagnostic_source(ReadOnlyDiagnosticPaths(canonical_db,analysis_db)); package=build_persistence_package(source)
    report: dict[str,Any]={"ok":True,"mode":"APPLY" if apply else "DRY_RUN","scope":"FULL" if full_universe else "COMPANY",
      "company_ids":sorted(set(company_ids)),"model_fingerprint":MODEL_FINGERPRINT,"source_fingerprint":package.source_fingerprint,
      "economic_result_fingerprint":package.economic_result_fingerprint,"package_fingerprint":package.package_fingerprint,
      "endpoint_count":len(package.endpoints),"evaluation_count":len(package.evaluations),"build_seconds":time.perf_counter()-started}
    if not apply: return report
    destination.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(destination); conn.row_factory=sqlite3.Row; conn.execute("PRAGMA foreign_keys=ON")
    try:
        ensure_schema(conn)
        result=apply_package(conn,package,applied_at_utc=applied_at_utc,company_ids=company_ids)
        report["apply_report"]=asdict(result); report["quick_check"]=quick_check(conn,authoritative_package=package if full_universe else None)
    finally: conn.close()
    return report
