from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .activation import TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT, assert_v2_active
from . import phase10b
from .persistence import apply_package
from .rehearsal import calculate


def refresh_active_package(paths: Mapping[str, Path]) -> dict[str, Any]:
    """Rebuild the coherent V2 package without fetching or changing source data."""
    with sqlite3.connect(f"file:{paths['analysis'].resolve()}?mode=ro", uri=True) as reader:
        active = assert_v2_active(reader)
    candidate_active = active.persistence_fingerprint in {
        phase10b.PACKAGE_FINGERPRINT,
        TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT,
    }
    calculated = (
        phase10b.calculate(
            paths,
            verify_v1_overlap=active.persistence_fingerprint != TEN_YEAR_OPERATIONAL_PACKAGE_FINGERPRINT,
        )
        if candidate_active else calculate(paths)
    )
    applied_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(paths["analysis"]) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        report = (
            phase10b.apply_candidate_package(
                conn,
                calculated,
                applied_at=applied_at,
                persistence_fingerprint=active.persistence_fingerprint,
            )
            if candidate_active else apply_package(conn, calculated, applied_at=applied_at)
        )
        assert_v2_active(conn)
    return {
        "family": "OPERATING_INCOME_MODEL_FAMILY_V2",
        "provider_update": False,
        "outcome": report.outcome,
        "logical_changes": report.logical_changes,
        "rows": report.rows,
        "economic_result_fingerprint": report.economic_result_fingerprint,
        "physical_content_fingerprint": report.physical_content_fingerprint,
    }
