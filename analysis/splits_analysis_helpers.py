from __future__ import annotations

import sqlite3
from typing import Tuple


def delete_analysis_rows_for_ticker(conn: sqlite3.Connection, ticker: str) -> Tuple[int, int, int]:
    """
    Poista annetun tickerin rivit analysis_findingsista, divergence_datasta ja results_datasta.
    Palauttaa tuple (findings_deleted, divergence_deleted, results_deleted).
    """
    findings = conn.execute(
        "DELETE FROM analysis_findings WHERE ticker = ?", (ticker,)
    ).rowcount
    divergence = conn.execute(
        "DELETE FROM divergence_data WHERE ticker = ?", (ticker,)
    ).rowcount
    results = conn.execute(
        "DELETE FROM results_data WHERE ticker = ?", (ticker,)
    ).rowcount
    conn.commit()
    return findings, divergence, results

