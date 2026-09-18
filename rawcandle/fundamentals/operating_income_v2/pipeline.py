from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .activation import assert_v2_active
from . import phase10b


def refresh_active_package(paths: Mapping[str, Path], *, as_of_date: str | None = None) -> dict[str, Any]:
    """Rebuild the coherent V2 package without fetching or changing source data."""
    with sqlite3.connect(f"file:{paths['analysis'].resolve()}?mode=ro", uri=True) as reader:
        active = assert_v2_active(reader)
    if active.persistence_fingerprint != phase10b.PACKAGE_FINGERPRINT:
        raise RuntimeError("CURRENT_V2_PACKAGE_REQUIRED")
    calculated = phase10b.calculate(paths, as_of_date=as_of_date)
    applied_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with sqlite3.connect(paths["analysis"]) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        report = phase10b.apply_candidate_package(
            conn, calculated, applied_at=applied_at,
            persistence_fingerprint=active.persistence_fingerprint,
        )
        assert_v2_active(conn)
    return {
        "family": "OPERATING_INCOME_MODEL_FAMILY_V2",
        "as_of_date": calculated["as_of_date"],
        "taxonomy_dependency": calculated["taxonomy_dependency"],
        "provider_update": False,
        "outcome": report.outcome,
        "logical_changes": report.logical_changes,
        "rows": report.rows,
        "economic_result_fingerprint": report.economic_result_fingerprint,
        "physical_content_fingerprint": report.physical_content_fingerprint,
    }
