from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.schema.migrations import migrate_canonical_valuation_copy
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT
from rawcandle.fundamentals.valuation.persistence import (
    PERSISTENCE_SCHEMA_VERSION,
    ValuationRepository,
    build_persisted_results,
    ensure_schema,
    load_canonical_source,
    logical_fingerprint,
    quick_check,
    replace_results,
)


PRODUCTION_PATHS = {
    "canonical": Path("/home/kalle/projects/rawcandle/data/fundamentals_v4.db"),
    "provider": Path("/home/kalle/projects/rawcandle/data/fundamentals_provider.db"),
    "analysis": Path("/home/kalle/projects/rawcandle/data/fundamentals_analysis.db"),
    "market": Path("/home/kalle/projects/rawcandle/data/osakedata.db"),
}
FULL_UNIVERSE_SCOPE = "FULL_UNIVERSE"


@dataclass(frozen=True)
class ValuationRefreshReport:
    source_fingerprint: str
    result_fingerprint: str
    rows: int
    rows_before: int
    rows_after: int
    rows_deleted: int
    rows_inserted: int
    rows_unchanged: int
    quick_check: dict[str, Any]


def validate_production_request(
    *,
    canonical_db: Path,
    provider_db: Path,
    analysis_db: Path,
    market_db: Path,
    model_fingerprint: str,
    full_universe: bool,
    apply: bool,
    confirm_production: bool,
) -> dict[str, str]:
    supplied = {
        "canonical": canonical_db,
        "provider": provider_db,
        "analysis": analysis_db,
        "market": market_db,
    }
    resolved: dict[str, str] = {}
    for name, path in supplied.items():
        expected = PRODUCTION_PATHS[name]
        if not path.is_absolute() or path != expected or path.is_symlink() or path.resolve() != expected:
            raise PermissionError(f"EXACT_PRODUCTION_PATH_REQUIRED:{name}:{expected}")
        resolved[name] = str(path.resolve())
    if len(set(resolved.values())) != len(resolved):
        raise ValueError("PRODUCTION_DATABASE_PATHS_MUST_BE_DISTINCT")
    if model_fingerprint != MODEL_FINGERPRINT:
        raise ValueError("VALUATION_MODEL_FINGERPRINT_MISMATCH")
    if not full_universe:
        raise ValueError("INITIAL_PRODUCTION_REQUIRES_FULL_UNIVERSE")
    if confirm_production and not apply:
        raise ValueError("CONFIRM_PRODUCTION_REQUIRES_APPLY")
    if apply and not confirm_production:
        raise PermissionError("PRODUCTION_APPLY_REQUIRES_CONFIRM_PRODUCTION")
    return resolved


def _set_analysis_schema_version(conn: sqlite3.Connection, applied_at_utc: str) -> None:
    current = conn.execute(
        "SELECT version FROM schema_version WHERE db_name='fundamentals_analysis'"
    ).fetchone()
    if current is not None and current[0] == PERSISTENCE_SCHEMA_VERSION:
        return
    conn.execute(
        "INSERT OR REPLACE INTO schema_version(db_name,version,applied_at_utc) VALUES ('fundamentals_analysis',?,?)",
        (PERSISTENCE_SCHEMA_VERSION, applied_at_utc),
    )


def calculate_valuation_rows(
    canonical_db: Path,
    market_db: Path,
    *,
    calculated_at: str,
) -> tuple[str, list[dict[str, Any]]]:
    source = load_canonical_source(canonical_db, market_db)
    rows = build_persisted_results(source, calculated_at=calculated_at)
    return source.source_fingerprint, rows


def refresh_valuation(
    canonical_db: Path,
    analysis_db: Path,
    market_db: Path,
    *,
    calculated_at: str,
) -> ValuationRefreshReport:
    source_fingerprint, rows = calculate_valuation_rows(
        canonical_db, market_db, calculated_at=calculated_at
    )
    conn = sqlite3.connect(analysis_db)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        conn.execute("BEGIN IMMEDIATE")
        ensure_schema(conn)
        _set_analysis_schema_version(conn, calculated_at)
        write = replace_results(conn, rows)
        check = quick_check(conn, expected_rows=rows)
        if not check["ok"]:
            raise RuntimeError(f"VALUATION_PRODUCTION_QUICK_CHECK_FAILED:{check['details']}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    write_values = asdict(write)
    write_values.pop("result_fingerprint")
    return ValuationRefreshReport(
        source_fingerprint=source_fingerprint,
        result_fingerprint=logical_fingerprint(rows),
        rows=len(rows),
        **write_values,
        quick_check=check,
    )


def apply_canonical_production(
    canonical_db: Path,
    provider_db: Path,
    *,
    applied_at_utc: str,
) -> dict[str, object]:
    if canonical_db != PRODUCTION_PATHS["canonical"] or provider_db != PRODUCTION_PATHS["provider"]:
        raise PermissionError("CANONICAL_PRODUCTION_PATH_NOT_AUTHORIZED")
    return migrate_canonical_valuation_copy(
        canonical_db,
        provider_db,
        applied_at_utc,
        allow_production=True,
    )


def reader_smoke(analysis_db: Path, *, as_of_date: str) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{analysis_db.resolve()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        repository = ValuationRepository(conn)
        current = repository.current_universe(
            model_fingerprint=MODEL_FINGERPRINT,
            as_of_date=as_of_date,
        )
        by_ticker = {row["ticker"]: row for row in current if row.get("ticker")}
        return {
            "current_rows": len(current),
            "nvda_status": by_ticker.get("NVDA", {}).get("valuation_status"),
            "reit_o_status": by_ticker.get("O", {}).get("valuation_status"),
            "wrong_fingerprint_rows": len(repository.current_universe(
                model_fingerprint="WRONG", as_of_date=as_of_date
            )),
        }
    finally:
        conn.close()
