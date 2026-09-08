from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.operating_income_v2.activation import active_family, assert_v2_active
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.renderer import render_snapshot
from rawcandle.fundamentals.snapshot.v2_assembler import assemble_company_snapshot_v2
from rawcandle.fundamentals.snapshot.writer import publish_report


def _relative_valuation_schema_exists(connection: sqlite3.Connection) -> bool:
    required = {
        "relative_valuation_snapshot",
        "relative_valuation_active_snapshot",
        "relative_valuation_company_result",
    }
    present = {
        str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_schema WHERE type='table' AND name LIKE 'relative_valuation_%'"
        )
    }
    return required <= present


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def generate_active_company_snapshot(
    paths: SnapshotPaths,
    *,
    ticker: str,
    report_date: str,
    output_dir: Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    relative_schema = False
    with _readonly(paths.analysis_db) as conn:
        if active_family(conn) is None:
            from rawcandle.fundamentals.snapshot.assembler import generate_company_snapshot

            return generate_company_snapshot(
                paths,
                ticker=ticker,
                report_date=report_date,
                output_dir=output_dir,
                overwrite=overwrite,
            )
        assert_v2_active(conn)
        relative_schema = _relative_valuation_schema_exists(conn)
    snapshot = assemble_company_snapshot_v2(paths, ticker=ticker, report_date=report_date)
    if relative_schema:
        from rawcandle.fundamentals.relative_valuation.candidate_snapshot import (
            attach_relative_valuation_unavailable,
            promote_persisted_relative_valuation_snapshot,
        )
        from rawcandle.fundamentals.relative_valuation.engine import MODEL_FINGERPRINT
        from rawcandle.fundamentals.relative_valuation.persistence import (
            RelativeValuationRepository,
        )

        with _readonly(paths.analysis_db) as conn:
            repository = RelativeValuationRepository(conn)
            active_id = repository.active_snapshot_id(model_fingerprint=MODEL_FINGERPRINT)
            try:
                metadata = repository.report_snapshot_metadata(
                    report_date, model_fingerprint=MODEL_FINGERPRINT
                )
            except ValueError:
                snapshot = attach_relative_valuation_unavailable(
                    snapshot, reason_code="RELATIVE_VALUATION_SNAPSHOT_INVALID"
                )
            else:
                if metadata is None:
                    reason = (
                        "RELATIVE_VALUATION_SNAPSHOT_NOT_ACTIVE"
                        if active_id is None
                        else "RELATIVE_VALUATION_NO_ELIGIBLE_NON_FUTURE_SNAPSHOT"
                    )
                    snapshot = attach_relative_valuation_unavailable(
                        snapshot, reason_code=reason
                    )
                else:
                    try:
                        snapshot = promote_persisted_relative_valuation_snapshot(
                            snapshot, repository, snapshot_metadata=metadata
                        )
                    except LookupError:
                        snapshot = attach_relative_valuation_unavailable(
                            snapshot,
                            reason_code="RELATIVE_VALUATION_COMPANY_NOT_IN_SNAPSHOT",
                            metadata=metadata,
                        )
    rendered = render_snapshot(snapshot)
    canonical_ticker = snapshot["identity"]["ticker"]
    markdown = rendered.markdown
    published = publish_report(
        output_dir=output_dir,
        ticker=canonical_ticker,
        report_date=report_date,
        markdown=markdown,
        overwrite=overwrite,
    )
    return {
        "status": published.status,
        "output_path": str(published.path),
        "report_content_fingerprint": rendered.content_fingerprint,
        "snapshot": snapshot,
    }
