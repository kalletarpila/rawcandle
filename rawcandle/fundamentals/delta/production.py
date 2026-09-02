from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT, MODEL_VERSION, fingerprint
from rawcandle.fundamentals.delta.persistence import (
    LAYOUT_FINGERPRINT,
    PERSISTENCE_VERSION,
    apply_package,
    build_persistence_package,
    ensure_schema,
    quick_check,
)
from rawcandle.fundamentals.delta.source import ReadOnlyDeltaPaths, load_delta_source
from rawcandle.fundamentals.delta.storage_v2 import normalized_rows
from rawcandle.fundamentals.delta.readers import (
    FundamentalDeltaRepository,
    LifecycleChangeRepository,
    ValuationChangeRepository,
)
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_MODEL_FINGERPRINT
from rawcandle.fundamentals.score.engine import MODEL_FINGERPRINT as SCORE_MODEL_FINGERPRINT
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_MODEL_FINGERPRINT


PRODUCTION_PATHS = {
    "analysis": Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db"),
    "canonical": Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db"),
    "provider": Path("/home/kalle/projects/rawcandle/data/fundamentals_provider.db"),
    "market": Path("/home/kalle/projects/rawcandle/data/osakedata.db"),
    "taxonomy": Path("/home/kalle/projects/rawcandle/data/analysis.db"),
}


@dataclass(frozen=True)
class DeltaCalculation:
    package: Any
    source: Any
    duration_seconds: float
    physical_content_fingerprint: str


@dataclass(frozen=True)
class DeltaRefreshReport:
    model_version: str
    model_fingerprint: str
    persistence_version: str
    layout_fingerprint: str
    economic_package_fingerprint: str
    physical_content_fingerprint: str
    source_fingerprints: dict[str, str]
    result_fingerprints: dict[str, str]
    total_rows: int
    component_rows: int
    calculation_seconds: float
    apply_seconds: float
    apply: dict[str, Any]
    routine_quick_check_seconds: float
    quick_check: dict[str, Any]


def validate_production_request(
    *,
    analysis_db: Path,
    canonical_db: Path,
    provider_db: Path,
    market_db: Path,
    taxonomy_db: Path,
    score_model_fingerprint: str,
    lifecycle_model_fingerprint: str,
    valuation_model_fingerprint: str,
    delta_model_fingerprint: str,
    persistence_version: str,
    layout_fingerprint: str,
    full_universe: bool,
    apply: bool,
    confirm_production: bool,
) -> dict[str, str]:
    supplied = {
        "analysis": analysis_db,
        "canonical": canonical_db,
        "provider": provider_db,
        "market": market_db,
        "taxonomy": taxonomy_db,
    }
    resolved: dict[str, str] = {}
    for name, path in supplied.items():
        expected = PRODUCTION_PATHS[name]
        if (
            not path.is_absolute()
            or path != expected
            or path.is_symlink()
            or path.resolve() != expected
            or not path.is_file()
        ):
            raise PermissionError(f"EXACT_DELTA_PRODUCTION_PATH_REQUIRED:{name}:{expected}")
        resolved[name] = str(path.resolve())
    if len(set(resolved.values())) != len(resolved):
        raise ValueError("DELTA_PRODUCTION_PATHS_MUST_BE_DISTINCT")
    locked = {
        "SCORE": (score_model_fingerprint, SCORE_MODEL_FINGERPRINT),
        "LIFECYCLE": (lifecycle_model_fingerprint, LIFECYCLE_MODEL_FINGERPRINT),
        "VALUATION": (valuation_model_fingerprint, VALUATION_MODEL_FINGERPRINT),
        "DELTA": (delta_model_fingerprint, MODEL_FINGERPRINT),
    }
    for label, (value, expected) in locked.items():
        if value != expected:
            raise ValueError(f"{label}_MODEL_FINGERPRINT_MISMATCH")
    if persistence_version != PERSISTENCE_VERSION:
        raise ValueError("DELTA_PERSISTENCE_VERSION_MISMATCH")
    if layout_fingerprint != LAYOUT_FINGERPRINT:
        raise ValueError("DELTA_LAYOUT_FINGERPRINT_MISMATCH")
    if not full_universe:
        raise ValueError("DELTA_PRODUCTION_REQUIRES_FULL_HISTORY")
    if confirm_production and not apply:
        raise ValueError("DELTA_CONFIRM_PRODUCTION_REQUIRES_APPLY")
    if apply and not confirm_production:
        raise PermissionError("DELTA_APPLY_REQUIRES_CONFIRM_PRODUCTION")
    return resolved


def calculate_production_package(
    *,
    analysis_db: Path,
    canonical_db: Path,
    score_model_fingerprint: str,
    lifecycle_model_fingerprint: str,
    valuation_model_fingerprint: str,
) -> DeltaCalculation:
    started = time.monotonic()
    source = load_delta_source(
        ReadOnlyDeltaPaths(analysis_db=analysis_db, canonical_db=canonical_db),
        score_model_fingerprint=score_model_fingerprint,
        lifecycle_model_fingerprint=lifecycle_model_fingerprint,
        valuation_model_fingerprint=valuation_model_fingerprint,
    )
    package = build_persistence_package(source)
    totals, components, _, _, _ = normalized_rows(package)
    physical = fingerprint([
        [row["result_fingerprint"] for row in totals],
        [row["result_fingerprint"] for row in components],
    ])
    return DeltaCalculation(package, source, time.monotonic() - started, physical)


def validate_expected_source_fingerprints(
    calculation: DeltaCalculation,
    *,
    fundamental_source_fingerprint: str | None = None,
    lifecycle_source_fingerprint: str | None = None,
    valuation_source_fingerprint: str | None = None,
) -> None:
    expected = {
        "FUNDAMENTAL": (fundamental_source_fingerprint, calculation.package.fundamental_source_fingerprint),
        "LIFECYCLE": (lifecycle_source_fingerprint, calculation.package.lifecycle_source_fingerprint),
        "VALUATION": (valuation_source_fingerprint, calculation.package.valuation_source_fingerprint),
    }
    for label, (supplied, actual) in expected.items():
        if supplied is not None and supplied != actual:
            raise RuntimeError(f"DELTA_{label}_SOURCE_FINGERPRINT_CHANGED")


def refresh_delta(
    *,
    analysis_db: Path,
    canonical_db: Path,
    applied_at_utc: str,
    score_model_fingerprint: str = SCORE_MODEL_FINGERPRINT,
    lifecycle_model_fingerprint: str = LIFECYCLE_MODEL_FINGERPRINT,
    valuation_model_fingerprint: str = VALUATION_MODEL_FINGERPRINT,
    calculation: DeltaCalculation | None = None,
) -> DeltaRefreshReport:
    value = calculation or calculate_production_package(
        analysis_db=analysis_db,
        canonical_db=canonical_db,
        score_model_fingerprint=score_model_fingerprint,
        lifecycle_model_fingerprint=lifecycle_model_fingerprint,
        valuation_model_fingerprint=valuation_model_fingerprint,
    )
    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn, applied_at_utc=applied_at_utc)
        conn.commit()
        started = time.monotonic()
        write = apply_package(conn, value.package, applied_at_utc=applied_at_utc)
        apply_seconds = time.monotonic() - started
        started = time.monotonic()
        check = quick_check(conn, model_fingerprint=MODEL_FINGERPRINT)
        quick_seconds = time.monotonic() - started
        if not check["ok"]:
            raise RuntimeError(f"DELTA_PRODUCTION_QUICK_CHECK_FAILED:{check['details']}")
    finally:
        conn.close()
    return DeltaRefreshReport(
        model_version=MODEL_VERSION,
        model_fingerprint=MODEL_FINGERPRINT,
        persistence_version=PERSISTENCE_VERSION,
        layout_fingerprint=LAYOUT_FINGERPRINT,
        economic_package_fingerprint=value.package.package_fingerprint,
        physical_content_fingerprint=write.persisted_content_fingerprint,
        source_fingerprints={
            "fundamental": value.package.fundamental_source_fingerprint,
            "lifecycle": value.package.lifecycle_source_fingerprint,
            "valuation": value.package.valuation_source_fingerprint,
        },
        result_fingerprints={
            "fundamental": value.package.fundamental_result_fingerprint,
            "lifecycle": value.package.lifecycle_result_fingerprint,
            "valuation": value.package.valuation_result_fingerprint,
        },
        total_rows=len(value.package.total_rows),
        component_rows=len(value.package.component_rows),
        calculation_seconds=value.duration_seconds,
        apply_seconds=apply_seconds,
        apply=asdict(write),
        routine_quick_check_seconds=quick_seconds,
        quick_check=check,
    )


def migrate_delta_schema(*, analysis_db: Path, applied_at_utc: str) -> dict[str, Any]:
    conn = sqlite3.connect(analysis_db)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        before = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE sql IS NOT NULL"
            )
        }
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn, applied_at_utc=applied_at_utc)
        conn.commit()
        after = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE sql IS NOT NULL"
            )
        }
        return {
            "objects_added": sorted(after - before),
            "objects_removed": sorted(before - after),
            "sqlite_quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
            "foreign_key_violations": len(conn.execute("PRAGMA foreign_key_check").fetchall()),
        }
    finally:
        conn.close()


def deep_authoritative_replay(
    *, analysis_db: Path, calculation: DeltaCalculation
) -> dict[str, Any]:
    started = time.monotonic()
    conn = sqlite3.connect(f"file:{analysis_db.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        check = quick_check(
            conn,
            model_fingerprint=MODEL_FINGERPRINT,
            authoritative_package=calculation.package,
        )
    finally:
        conn.close()
    return {
        "duration_seconds": time.monotonic() - started,
        "compared_endpoints": len(calculation.package.total_rows),
        "compared_components": len(calculation.package.component_rows),
        "mismatch_count": len(check["details"]),
        "check": check,
    }


def reader_verification(
    *, analysis_db: Path, calculation: DeltaCalculation
) -> dict[str, Any]:
    tickers = {
        ticker: company_id
        for company_id, ticker in calculation.source.company_tickers.items()
        if ticker
    }
    conn = sqlite3.connect(f"file:{analysis_db.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    try:
        fundamental = FundamentalDeltaRepository(conn)
        lifecycle = LifecycleChangeRepository(conn)
        valuation = ValuationChangeRepository(conn)
        representatives: dict[str, Any] = {}
        for ticker in ("CRMD", "APD"):
            company_id = tickers.get(ticker)
            if company_id is None:
                representatives[ticker] = {"status": "TICKER_NOT_FOUND"}
                continue
            current = fundamental.current_company(company_id, model_fingerprint=MODEL_FINGERPRINT)
            if current is None:
                representatives[ticker] = {"status": "DELTA_NOT_FOUND"}
                continue
            combined = fundamental.with_components(
                company_id, current["fiscal_year"], current["fiscal_quarter"],
                model_fingerprint=MODEL_FINGERPRINT,
            )
            representatives[ticker] = {
                "company_id": company_id,
                "current": current,
                "history_rows": len(fundamental.history(company_id, model_fingerprint=MODEL_FINGERPRINT)),
                "component_rows": len(combined["components"]),
                "lifecycle": lifecycle.current_company(company_id, model_fingerprint=LIFECYCLE_MODEL_FINGERPRINT),
                "valuation": valuation.current_company(company_id, model_fingerprint=VALUATION_MODEL_FINGERPRINT),
            }
        universe = fundamental.current_universe(model_fingerprint=MODEL_FINGERPRINT)
        latest = universe[0] if universe else None
        cross_rows = 0
        endpoint_matches = False
        if latest is not None:
            endpoint = fundamental.endpoint(
                latest["company_id"], latest["fiscal_year"], latest["fiscal_quarter"],
                model_fingerprint=MODEL_FINGERPRINT,
            )
            endpoint_matches = endpoint == latest
            cross_rows = len(fundamental.cross_section(
                latest["fiscal_year"], latest["fiscal_quarter"],
                model_fingerprint=MODEL_FINGERPRINT,
            ))
        wrong_delta_rejected = False
        wrong_lifecycle_rejected = False
        wrong_valuation_rejected = False
        try:
            fundamental.current_company(1, model_fingerprint="WRONG")
        except ValueError:
            wrong_delta_rejected = True
        try:
            lifecycle.current_company(1, model_fingerprint="WRONG")
        except ValueError:
            wrong_lifecycle_rejected = True
        try:
            valuation.current_company(1, model_fingerprint="WRONG")
        except ValueError:
            wrong_valuation_rejected = True
        return {
            "current_universe_rows": len(universe),
            "deterministic_company_order": [row["company_id"] for row in universe] == sorted(row["company_id"] for row in universe),
            "endpoint_matches_current": endpoint_matches,
            "representative_cross_section_rows": cross_rows,
            "wrong_fingerprint_rejected": {
                "delta": wrong_delta_rejected,
                "lifecycle": wrong_lifecycle_rejected,
                "valuation": wrong_valuation_rejected,
            },
            "representatives": representatives,
        }
    finally:
        conn.close()
