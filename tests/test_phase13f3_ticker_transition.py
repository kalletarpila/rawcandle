from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.phase12d import PRODUCTION
from rawcandle.fundamentals.phase13f3_ticker_transition import (
    TRANSITIONS,
    _apply_transition_identities,
    accepted_normalization,
    enhanced_listing_population,
    run_phase13f3,
    transition_evidence,
)
from rawcandle.fundamentals.phase13f1_reconciliation import AuditPaths


def _minimal_canonical(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(
            """
            CREATE TABLE company(
                company_id INTEGER PRIMARY KEY,
                company_key TEXT NOT NULL UNIQUE,
                company_name TEXT,
                status TEXT NOT NULL,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE TABLE security(
                security_id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                current_ticker TEXT NOT NULL UNIQUE,
                exchange TEXT,
                active INTEGER NOT NULL,
                valid_from TEXT,
                valid_to TEXT,
                created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            CREATE TABLE ticker_alias(
                alias_id INTEGER PRIMARY KEY,
                security_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,
                provider TEXT,
                valid_from TEXT,
                valid_to TEXT,
                source TEXT NOT NULL,
                UNIQUE(security_id,ticker,provider,valid_from)
            );
            """
        )
        for index, ticker in enumerate(("EQR", "ISSC", "AIHS", "BBBY", "LIXT"), start=1):
            conn.execute(
                "INSERT INTO company VALUES (?,?,?,?,?,?)",
                (index, f"SEC_CIK:{index:010d}", ticker, "ACTIVE", "now", "now"),
            )
            conn.execute(
                "INSERT INTO security VALUES (?,?,?,?,?,?,?,?,?)",
                (index, index, ticker, "NASDAQ", 1, None, None, "now", "now"),
            )
            conn.execute(
                "INSERT INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES (?,?,?,?,?,?)",
                (index, ticker, "TEST", None, None, "fixture"),
            )
        conn.commit()
    finally:
        conn.close()


def test_transition_contract_has_expected_semantic_distinctions() -> None:
    by_current = {row["current_ticker"]: row for row in TRANSITIONS}

    assert by_current["IA"]["structural_break"] == "NO_ECONOMIC_STRUCTURAL_BREAK_FROM_TICKER_CHANGE"
    assert by_current["VMRK"]["structural_break"] == "MAJOR_BUSINESS_COMBINATION"
    assert by_current["NMAD"]["structural_break"] == "REVERSE_MERGER_MAJOR_BUSINESS_CHANGE"
    assert by_current["NXH"]["structural_break"] == "TICKER_REUSE_SEPARATION"


def test_normalized_only_is_accepted_without_collapsing_semantic_mismatch() -> None:
    assert accepted_normalization({
        "exact_match_status": "NOT_EXACT_MATCH",
        "normalized_match_status": "NORMALIZED_MATCH",
        "ticker_meta_sector_raw": "Real Estate",
        "ticker_meta_industry_raw": "REIT - Residential",
    }) == "ACCEPTED_HARMLESS_NORMALIZATION"
    assert accepted_normalization({
        "exact_match_status": "NOT_EXACT_MATCH",
        "normalized_match_status": "NOT_NORMALIZED_MATCH",
        "ticker_meta_sector_raw": "Real Estate",
        "ticker_meta_industry_raw": "REIT - Residential",
    }) == "SEMANTIC_MISMATCH"


def test_copy_identity_apply_moves_old_tickers_to_successors(tmp_path: Path) -> None:
    db = tmp_path / "canonical.db"
    _minimal_canonical(db)

    result = _apply_transition_identities(db)

    assert result["outcome"] == "APPLIED"
    conn = sqlite3.connect(db)
    try:
        current = {row[0] for row in conn.execute("SELECT current_ticker FROM security")}
        aliases = {(row[0], row[1]) for row in conn.execute("SELECT ticker,valid_to FROM ticker_alias")}
    finally:
        conn.close()
    assert {"VMRK", "IA", "VAI", "NXH", "NMAD"} <= current
    assert ("BBBY", "2026-08-17") in aliases
    assert ("NXH", None) in aliases


def test_protected_production_output_refusal() -> None:
    with pytest.raises(PermissionError):
        run_phase13f3(PRODUCTION["analysis"])


def test_real_transition_evidence_separates_nxh_from_bankrupt_bbby() -> None:
    rows = transition_evidence(AuditPaths())
    nxh = next(row for row in rows if row["current_ticker"] == "NXH")

    assert str(nxh["provider_permaticker"]) == "195902"
    assert "SEPARATE_FROM_BANKRUPT_BBBY" in nxh["bbby_reuse_result"]


def test_enhanced_listing_population_resolves_former_transition_tickers() -> None:
    listing = enhanced_listing_population(AuditPaths())
    resolved = {
        row["historical_ticker"]: row
        for row in listing["rows"]
        if row.get("transition_resolution_code") == "RESOLVED_BY_DATED_SUCCESSOR_IDENTITY"
    }

    assert set(resolved) == {"AIHS", "BBBY", "EQR", "ISSC", "LIXT"}
    assert {row["current_ticker"] for row in resolved.values()} == {"VAI", "NXH", "VMRK", "IA", "NMAD"}
