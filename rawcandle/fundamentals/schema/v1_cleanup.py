"""Copy-only cleanup of retired Fundamentals V1 analysis structures."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.operating_income_v2 import activation, phase10b


PRODUCTION_ANALYSIS_DB = (
    Path(__file__).resolve().parents[3] / "data/fundamentals_analysis.db"
)
LEGACY_TABLES = (
    "lifecycle_result",
    "valuation_result",
    "operating_income_v2_package_manifest_history",
)
LEGACY_INDEXES = (
    "idx_lifecycle_result_company_quarter",
    "idx_valuation_result_company_quarter",
)
REQUIRED_CURRENT_TABLES = (
    "analysis_model_run",
    "score_result",
    "score_component",
    "lifecycle_revised_result",
    "valuation_revised_result",
    "fundamental_delta_package",
    "diagnostic_flag_package",
    "relative_position_snapshot",
    "relative_position_active_snapshot",
    "relative_valuation_active_snapshot",
    "operating_income_v2_package_manifest",
    "fundamentals_active_model_family",
)


def _objects(conn: sqlite3.Connection, object_type: str) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_schema WHERE type=?", (object_type,)
        )
    }


def _validate_current_v2(conn: sqlite3.Connection) -> None:
    tables = _objects(conn, "table")
    missing = sorted(set(REQUIRED_CURRENT_TABLES) - tables)
    if missing:
        raise RuntimeError(f"V1_CLEANUP_REQUIRED_CURRENT_SCHEMA_MISSING:{','.join(missing)}")

    active = activation.assert_v2_active(conn)
    if active.persistence_fingerprint != phase10b.PACKAGE_FINGERPRINT:
        raise RuntimeError("V1_CLEANUP_CURRENT_PACKAGE_REQUIRED")

    expected = {
        "score_result": phase10b.MODEL_MAP["score"][1],
        "lifecycle_revised_result": phase10b.MODEL_MAP["lifecycle"][1],
        "valuation_revised_result": phase10b.MODEL_MAP["valuation"][1],
        "fundamental_delta_package": phase10b.MODEL_MAP["delta"][1],
        "diagnostic_flag_package": phase10b.MODEL_MAP["diagnostic_flags"][1],
        "relative_position_snapshot": phase10b.MODEL_MAP["relative_position"][1],
        "relative_position_active_snapshot": phase10b.MODEL_MAP["relative_position"][1],
    }
    for table, fingerprint in expected.items():
        if conn.execute(
            f"SELECT 1 FROM {table} WHERE model_fingerprint<>? LIMIT 1",
            (fingerprint,),
        ).fetchone():
            raise RuntimeError(f"V1_CLEANUP_NON_CURRENT_MODEL_STATE:{table}")

    run_fingerprint = phase10b.MODEL_MAP["score"][1]
    if conn.execute(
        "SELECT 1 FROM analysis_model_run "
        "WHERE model_type<>'SCORE' OR model_fingerprint<>? LIMIT 1",
        (run_fingerprint,),
    ).fetchone():
        raise RuntimeError("V1_CLEANUP_NON_CURRENT_MODEL_STATE:analysis_model_run")


def cleanup_legacy_v1_schema(target_analysis_db: Path) -> dict[str, Any]:
    """Remove proven V1-only structures from a non-production analysis DB copy."""
    target = Path(target_analysis_db)
    resolved = target.resolve()
    production = PRODUCTION_ANALYSIS_DB.resolve()
    aliases_production = (
        production.exists() and resolved.exists() and resolved.samefile(production)
    )
    if (
        not target.is_absolute()
        or target.is_symlink()
        or resolved == production
        or aliases_production
    ):
        raise PermissionError("V1_CLEANUP_PRODUCTION_OR_ALIAS_BLOCKED")
    if not resolved.is_file():
        raise FileNotFoundError(resolved)

    with sqlite3.connect(resolved) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("BEGIN IMMEDIATE")
        try:
            _validate_current_v2(conn)
            tables_before = _objects(conn, "table")
            indexes_before = _objects(conn, "index")
            present_legacy_tables = sorted(set(LEGACY_TABLES) & tables_before)
            present_legacy_indexes = sorted(set(LEGACY_INDEXES) & indexes_before)

            for table in ("lifecycle_result", "valuation_result"):
                if table in tables_before and conn.execute(
                    f"SELECT 1 FROM {table} LIMIT 1"
                ).fetchone():
                    raise RuntimeError(f"V1_CLEANUP_LEGACY_ROWS_PRESENT:{table}")

            for index in present_legacy_indexes:
                conn.execute(f"DROP INDEX {index}")
            for table in present_legacy_tables:
                conn.execute(f"DROP TABLE {table}")

            remaining = sorted(set(LEGACY_TABLES) & _objects(conn, "table"))
            if remaining:
                raise RuntimeError(f"V1_CLEANUP_SCHEMA_REMAINS:{','.join(remaining)}")
            if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise RuntimeError("V1_CLEANUP_FOREIGN_KEY_CHECK_FAILED")
            if conn.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                raise RuntimeError("V1_CLEANUP_QUICK_CHECK_FAILED")
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    removed = present_legacy_tables + present_legacy_indexes
    return {
        "outcome": "APPLIED" if removed else "NO_CHANGE",
        "target": str(resolved),
        "removed": removed,
        "vacuum_performed": False,
    }
