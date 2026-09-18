from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Mapping

from rawcandle.fundamentals import structural_break
from rawcandle.fundamentals.phase12d import stable_hash


def _events() -> tuple[dict[str, Any], ...]:
    transitions = []
    for historical, current, effective, event, structural, semantics, permaticker in (
        ("EQR", "VMRK", "2026-08-18", "2026-08-17", "MAJOR_BUSINESS_COMBINATION", "LEGAL_CONTINUITY_WITH_MAJOR_MERGER_TRANSITION", "197624"),
        ("ISSC", "IA", "2026-08-18", "2026-08-18", "NO_ECONOMIC_STRUCTURAL_BREAK_FROM_TICKER_CHANGE", "SAME_SECURITY_TICKER_CONTINUATION", "198182"),
        ("AIHS", "VAI", "2026-08-26", "2026-08-26", "BUSINESS_COMPARABILITY_REVIEW_REQUIRED", "SAME_COMMON_STOCK_CONTINUATION_WITH_BUSINESS_REVIEW", "120343"),
        ("BBBY", "NXH", "2026-08-17", "2026-08-17", "TICKER_REUSE_SEPARATION", "CURRENT_OSTK_BYON_BBBY_NXH_LINEAGE_NOT_BANKRUPT_BBBY", "195902"),
        ("LIXT", "NMAD", "2026-07-06", "2026-07-02", "REVERSE_MERGER_MAJOR_BUSINESS_CHANGE", "REVERSE_MERGER_CONTINUATION_WITH_MAJOR_ECONOMIC_BREAK", "108994"),
    ):
        transitions.append({
            "historical_ticker": historical, "current_ticker": current,
            "effective_date": effective, "event_date": event,
            "structural_break": structural, "semantics": semantics,
            "permaticker": permaticker,
        })
    return structural_break.default_events(transitions)


def _structural_package_fingerprint(structural: Mapping[str, Any]) -> str:
    return stable_hash({
        "base_package": "OPERATING_INCOME_V2_PARALLEL_PERSISTENCE_V2",
        "structural_contract_version": structural_break.CONTRACT_VERSION,
        "structural_regime_fingerprint": structural["regime_fingerprint"],
    })


def _structural_evidence(canonical_db: Path) -> dict[str, Any]:
    with sqlite3.connect(f"file:{canonical_db.resolve()}?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(
            f"""WITH quarter_counts AS (
                    SELECT event_id,
                           COUNT(*) quarter_rows,
                           SUM(CASE WHEN economic_regime='PRE_EVENT' THEN 1 ELSE 0 END) pre_event_quarters,
                           SUM(CASE WHEN economic_regime='UNRESOLVED' THEN 1 ELSE 0 END) unresolved_quarters
                      FROM {structural_break.QUARTER_TABLE}
                     GROUP BY event_id
                 ),
                 ttm_counts AS (
                    SELECT event_id,
                           SUM(CASE WHEN ttm_regime_status='PRE_EVENT_COHERENT' THEN 1 ELSE 0 END) pre_event_ttm,
                           SUM(CASE WHEN ttm_regime_status='POST_EVENT_COHERENT' THEN 1 ELSE 0 END) post_event_clean_ttm,
                           SUM(CASE WHEN ttm_regime_status='STRUCTURAL_NOT_READY' THEN 1 ELSE 0 END) structural_not_ready_ttm
                      FROM {structural_break.TTM_TABLE}
                     GROUP BY event_id
                 )
                SELECT e.successor_ticker,e.predecessor_ticker,e.event_type,e.event_date,
                       e.comparability_status,e.review_status,
                       COALESCE(q.quarter_rows,0) quarter_rows,
                       COALESCE(q.pre_event_quarters,0) pre_event_quarters,
                       COALESCE(q.unresolved_quarters,0) unresolved_quarters,
                       COALESCE(t.pre_event_ttm,0) pre_event_ttm,
                       COALESCE(t.post_event_clean_ttm,0) post_event_clean_ttm,
                       COALESCE(t.structural_not_ready_ttm,0) structural_not_ready_ttm
                  FROM {structural_break.EVENT_TABLE} e
                  LEFT JOIN quarter_counts q USING(event_id)
                  LEFT JOIN ttm_counts t USING(event_id)
                 ORDER BY e.successor_ticker"""
        )]
        eligibility, metadata = structural_break.latest_ttm_eligibility(conn, as_of_date="2026-09-12")
    by_company = {
        str(row.company_id): {
            "eligible": row.eligible,
            "reason_code": row.reason_code,
            "ticker_event_type": row.event_type,
            "ttm_regime_status": row.ttm_regime_status,
        }
        for row in eligibility.values()
    }
    return {"rows": rows, "current_eligibility": by_company, "metadata": metadata}
