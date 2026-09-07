from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.operating_income_v2.activation import active_family, assert_v2_active
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
from rawcandle.fundamentals.snapshot.renderer import render_snapshot
from rawcandle.fundamentals.snapshot.v2_assembler import assemble_company_snapshot_v2
from rawcandle.fundamentals.snapshot.writer import publish_report


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
    snapshot = assemble_company_snapshot_v2(paths, ticker=ticker, report_date=report_date)
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
