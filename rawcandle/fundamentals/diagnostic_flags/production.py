from __future__ import annotations

import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.diagnostic_flags.engine import (
    FLAG_NAMES,
    MODEL_FINGERPRINT,
    MODEL_VERSION,
)
from rawcandle.fundamentals.diagnostic_flags.persistence import (
    LAYOUT_FINGERPRINT,
    PERSISTENCE_VERSION,
    apply_package,
    build_persistence_package,
    ensure_schema,
    package_content_fingerprint,
    quick_check,
)
from rawcandle.fundamentals.diagnostic_flags.readers import DiagnosticFlagRepository
from rawcandle.fundamentals.diagnostic_flags.source import (
    ReadOnlyDiagnosticPaths,
    load_diagnostic_source,
)


PRODUCTION_PATHS = {
    "analysis": Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db"),
    "canonical": Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db"),
    "provider": Path("/home/kalle/projects/rawcandle/data/fundamentals_provider.db"),
    "market": Path("/home/kalle/projects/rawcandle/data/osakedata.db"),
    "taxonomy": Path("/home/kalle/projects/rawcandle/data/analysis.db"),
}


@dataclass(frozen=True)
class DiagnosticCalculation:
    package: Any
    source: Any
    duration_seconds: float
    physical_content_fingerprint: str


def validate_production_request(
    *,
    analysis_db: Path,
    canonical_db: Path,
    provider_db: Path,
    market_db: Path,
    taxonomy_db: Path,
    model_fingerprint: str,
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
            raise PermissionError(
                f"EXACT_DIAGNOSTIC_PRODUCTION_PATH_REQUIRED:{name}:{expected}"
            )
        resolved[name] = str(path.resolve())
    if len(set(resolved.values())) != len(resolved):
        raise ValueError("DIAGNOSTIC_PRODUCTION_PATHS_MUST_BE_DISTINCT")
    if model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("DIAGNOSTIC_MODEL_FINGERPRINT_MISMATCH")
    if persistence_version != PERSISTENCE_VERSION:
        raise ValueError("DIAGNOSTIC_PERSISTENCE_VERSION_MISMATCH")
    if layout_fingerprint != LAYOUT_FINGERPRINT:
        raise ValueError("DIAGNOSTIC_LAYOUT_FINGERPRINT_MISMATCH")
    if not full_universe:
        raise ValueError("DIAGNOSTIC_PRODUCTION_REQUIRES_FULL_HISTORY")
    if confirm_production and not apply:
        raise ValueError("DIAGNOSTIC_CONFIRM_PRODUCTION_REQUIRES_APPLY")
    if apply and not confirm_production:
        raise PermissionError("DIAGNOSTIC_APPLY_REQUIRES_CONFIRM_PRODUCTION")
    return resolved


def calculate_production_package(
    *, analysis_db: Path, canonical_db: Path
) -> DiagnosticCalculation:
    started = time.monotonic()
    source = load_diagnostic_source(
        ReadOnlyDiagnosticPaths(canonical_db=canonical_db, analysis_db=analysis_db)
    )
    package = build_persistence_package(source)
    return DiagnosticCalculation(
        package,
        source,
        time.monotonic() - started,
        package_content_fingerprint(package),
    )


def migrate_diagnostic_schema(*, analysis_db: Path) -> dict[str, Any]:
    with sqlite3.connect(analysis_db) as connection:
        before = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE sql IS NOT NULL"
            )
        }
        ensure_schema(connection)
        after = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_schema WHERE sql IS NOT NULL"
            )
        }
        return {
            "objects_added": sorted(after - before),
            "objects_removed": sorted(before - after),
            "quick_check": connection.execute("PRAGMA quick_check").fetchone()[0],
            "foreign_key_violations": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
        }


def refresh_diagnostic_flags(
    *,
    analysis_db: Path,
    canonical_db: Path,
    applied_at_utc: str,
    calculation: DiagnosticCalculation | None = None,
) -> dict[str, Any]:
    value = calculation or calculate_production_package(
        analysis_db=analysis_db, canonical_db=canonical_db
    )
    with sqlite3.connect(analysis_db) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        ensure_schema(connection)
        started = time.monotonic()
        write = apply_package(
            connection, value.package, applied_at_utc=applied_at_utc
        )
        apply_seconds = time.monotonic() - started
        check = quick_check(connection)
        if not check["ok"]:
            raise RuntimeError(
                f"DIAGNOSTIC_PRODUCTION_QUICK_CHECK_FAILED:{check['details']}"
            )
    return {
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "persistence_version": PERSISTENCE_VERSION,
        "layout_fingerprint": LAYOUT_FINGERPRINT,
        "source_fingerprint": value.package.source_fingerprint,
        "economic_result_fingerprint": value.package.economic_result_fingerprint,
        "package_fingerprint": value.package.package_fingerprint,
        "physical_content_fingerprint": write.persisted_content_fingerprint,
        "endpoint_count": len(value.package.endpoints),
        "evaluation_count": len(value.package.evaluations),
        "calculation_seconds": value.duration_seconds,
        "apply_seconds": apply_seconds,
        "apply": asdict(write),
        "quick_check": check,
    }


def deep_authoritative_replay(
    *, analysis_db: Path, calculation: DiagnosticCalculation
) -> dict[str, Any]:
    started = time.monotonic()
    with sqlite3.connect(
        f"file:{analysis_db.resolve()}?mode=ro", uri=True
    ) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        check = quick_check(
            connection, authoritative_package=calculation.package
        )
    return {
        "duration_seconds": time.monotonic() - started,
        "compared_endpoints": len(calculation.package.endpoints),
        "compared_evaluations": len(calculation.package.evaluations),
        "mismatch_count": len(check["details"]),
        "check": check,
    }


def reader_verification(
    *, analysis_db: Path, calculation: DiagnosticCalculation
) -> dict[str, Any]:
    tickers = {
        row.ticker: row.diagnostic_input.current.company_id
        for row in calculation.source.rows
    }
    with sqlite3.connect(
        f"file:{analysis_db.resolve()}?mode=ro", uri=True
    ) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        repository = DiagnosticFlagRepository(connection)
        representatives: dict[str, Any] = {}
        for ticker in ("CRMD", "APD"):
            company_id = tickers.get(ticker)
            current = (
                repository.current_company(
                    company_id, model_fingerprint=MODEL_FINGERPRINT
                )
                if company_id is not None
                else None
            )
            representatives[ticker] = {
                "company_id": company_id,
                "current": current,
                "history_rows": len(
                    repository.history(
                        company_id, model_fingerprint=MODEL_FINGERPRINT
                    )
                )
                if company_id is not None
                else 0,
            }
        flagged = repository.current_flagged_universe(
            model_fingerprint=MODEL_FINGERPRINT
        )
        latest = max(
            calculation.source.rows,
            key=lambda row: row.diagnostic_input.current.fiscal_sequence,
        ).diagnostic_input.current
        cross_section = repository.cross_section(
            latest.fiscal_year,
            latest.fiscal_quarter,
            model_fingerprint=MODEL_FINGERPRINT,
        )
        wrong_fingerprint_rejected = False
        try:
            repository.current_company(1, model_fingerprint="WRONG")
        except ValueError:
            wrong_fingerprint_rejected = True
        return {
            "flagged_universe_rows": len(flagged),
            "deterministic_flag_order": all(
                tuple(sorted(row["flags"], key=FLAG_NAMES.index)) == row["flags"]
                for row in flagged
            ),
            "cross_section_rows": len(cross_section),
            "wrong_fingerprint_rejected": wrong_fingerprint_rejected,
            "representatives": representatives,
        }
