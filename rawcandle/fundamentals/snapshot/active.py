from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from rawcandle.fundamentals.operating_income_v2.activation import active_family, assert_v2_active
from rawcandle.fundamentals.operating_income_v2.reporting import build_company_report
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths
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
        row = conn.execute(
            "SELECT company_id FROM lifecycle_revised_result "
            "WHERE model_fingerprint=(SELECT json_extract(model_manifest_json,'$.lifecycle[1]') "
            "FROM fundamentals_active_model_family WHERE singleton=1) AND ticker=? "
            "ORDER BY fiscal_sequence DESC LIMIT 1",
            (ticker.strip().upper(),),
        ).fetchone()
        if row is None:
            raise LookupError(f"OPERATING_INCOME_V2_REPORT_TICKER_NOT_FOUND:{ticker}")
        canonical_ticker, markdown, metadata = build_company_report(
            conn, company_id=int(row[0]), market_db=paths.market_db
        )
    markdown = markdown.replace("\n\n", f"\n\nReport date: `{report_date}`\n\n", 1)
    published = publish_report(
        output_dir=output_dir,
        ticker=canonical_ticker,
        report_date=report_date,
        markdown=markdown,
        overwrite=overwrite,
    )
    fingerprint = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
    snapshot = {
        **metadata,
        "report_date": report_date,
        "source_state": {"analysis": str(paths.analysis_db.resolve())},
        "source_state_fingerprint": fingerprint,
    }
    return {
        "status": published.status,
        "output_path": str(published.path),
        "report_content_fingerprint": fingerprint,
        "snapshot": snapshot,
    }
