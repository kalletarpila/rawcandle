from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.result_publication import (
    SecClient,
    apply_resolution,
    enrich_database,
    match_quarter_context,
    normalize_utc_timestamp,
    pit_result_side,
    resolve_sec_filings,
    store_secondary_evidence,
    yahoo_evidence_payload,
)
from rawcandle.fundamentals.schema.migrations import bootstrap_all
from rawcandle.fundamentals.schema.result_publication import ensure_result_publication_schema


NOW = "2026-09-28T12:00:00Z"
SAMPLES = {
    "AAPL": (1, "0000320193", 2026, "Q3", "2026-06-27", "2026-07-30T20:30:28Z", "0000320193-26-000018"),
    "NVDA": (2, "0001045810", 2026, "Q4", "2026-01-25", "2026-02-25T21:31:25Z", "0001045810-26-000019"),
    "AMZN": (3, "0001018724", 2026, "Q2", "2026-06-30", "2026-07-30T20:06:23Z", "0001018724-26-000024"),
    "ADBE": (4, "0000796343", 2026, "Q3", "2026-08-28", "2026-09-10T20:06:14Z", "0000796343-26-000147"),
}


def _database(tmp_path: Path) -> Path:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    bootstrap_all(provider, canonical, analysis, NOW)
    with sqlite3.connect(canonical) as connection:
        for ticker, (company_id, cik, year, quarter, period_end, _, _) in SAMPLES.items():
            connection.execute(
                "INSERT INTO company VALUES(?,?,?,?,?,?)",
                (company_id, f"SEC_CIK:{cik}", ticker, "ACTIVE", NOW, NOW),
            )
            connection.execute(
                "INSERT INTO security VALUES(?,?,?,?,?,?,?,?,?)",
                (company_id, company_id, ticker, "NASDAQ", 1, None, None, NOW, NOW),
            )
            connection.execute(
                """INSERT INTO company_cik(
                    company_id,cik_normalized,cik_display,source,source_table,source_row_id,status,created_at_utc,
                    source_type,source_name,source_field,source_value,derivation,confidence
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (company_id, cik, cik, "TEST", None, None, "ACTIVE", NOW, "TEST", "SEC", "CIK", cik, "DIRECT", "HIGH"),
            )
            connection.execute(
                """INSERT INTO v4_quarter(
                    quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,source_fiscalperiod,
                    source_reportperiod,identity_provider,identity_status,source_availability_date,
                    first_public_result_date,created_at_utc,updated_at_utc
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (company_id, company_id, year, quarter, period_end, quarter, period_end, "SHARADAR", "RESOLVED",
                 "2026-09-22", "2026-09-22", NOW, NOW),
            )
    return canonical


def _sec_payload(cik: str, timestamp: str, accession: str, ticker: str) -> dict[str, object]:
    return {"filings": {"recent": {
        "form": ["8-K"], "items": ["2.02,9.01"], "accessionNumber": [accession],
        "acceptanceDateTime": [timestamp], "primaryDocument": [f"{ticker.lower()}.htm"],
    }}}


def _client() -> SecClient:
    payloads = {
        cik: _sec_payload(cik, timestamp, accession, ticker)
        for ticker, (_, cik, _, _, _, timestamp, accession) in SAMPLES.items()
    }
    texts = {
        "aapl.htm": "Item 2.02 Results of Operations and Financial Condition. results for its third fiscal quarter ended June 27, 2026.",
        "nvda.htm": "Item 2.02 Results of Operations and Financial Condition. results for the quarter ended January 25, 2026.",
        "amzn.htm": "Item 2.02 Results of Operations and Financial Condition. announced its second quarter 2026 financial results.",
        "adbe.htm": "Item 2.02 Results of Operations and Financial Condition. financial results for its third quarter fiscal year 2026 ended August 28, 2026.",
    }
    return SecClient(
        fetch_json=lambda url: payloads[url.split("CIK", 1)[1].split(".", 1)[0]],
        fetch_text=lambda url: texts[url.rsplit("/", 1)[1]],
        minimum_interval_seconds=0,
    )


def _manual_evidence(quarter: dict[str, object], source: str, timestamp: str, token: str) -> dict[str, object]:
    digest = hashlib.sha256(token.encode()).hexdigest()
    return {
        "evidence_id": f"rpe_{digest[:24]}", "quarter_id": quarter["quarter_id"],
        "company_id": quarter["company_id"], "fiscal_year": quarter["fiscal_year"],
        "fiscal_quarter": quarter["fiscal_quarter"], "source_type": source,
        "source_timestamp_utc": timestamp, "source_reference": f"https://example.test/{token}",
        "matching_method": "TEST_REVIEW", "rule_version": "result_publication_v1",
        "reviewed_manual": 1, "evidence_hash": digest,
    }


def test_schema_is_additive_idempotent_and_preserves_existing_dates(tmp_path: Path) -> None:
    canonical = _database(tmp_path)
    with sqlite3.connect(canonical) as connection:
        before = connection.execute(
            "SELECT first_public_result_date,source_availability_date FROM v4_quarter ORDER BY quarter_id"
        ).fetchall()
        connection.execute("DROP TABLE v4_result_publication_authority")
        connection.execute("DROP TABLE v4_result_publication_evidence")
        assert ensure_result_publication_schema(connection) == {"tables_added": 2}
        assert ensure_result_publication_schema(connection) == {"tables_added": 0}
        after = connection.execute(
            "SELECT first_public_result_date,source_availability_date FROM v4_quarter ORDER BY quarter_id"
        ).fetchall()
    assert before == after


def test_utc_contract_and_future_pit_boundary() -> None:
    assert normalize_utc_timestamp("2026-07-30T16:30:28-04:00") == "2026-07-30T20:30:28Z"
    with pytest.raises(ValueError, match="TIMEZONE_AWARE"):
        normalize_utc_timestamp("2026-07-30T20:30:28")
    authority = {"status": "VERIFIED", "result_publication_timestamp_utc": "2026-07-30T20:30:28Z"}
    assert pit_result_side("2026-07-30T20:30:27Z", authority) == "PRE_RESULT"
    assert pit_result_side("2026-07-30T20:30:28Z", authority) == "POST_RESULT"
    assert pit_result_side("2026-07-30T20:30:28Z", {"status": "NOT_FOUND"}) is None


def test_known_official_sec_item_202_samples_resolve_without_sharadar_fallback(tmp_path: Path) -> None:
    canonical = _database(tmp_path)
    result = enrich_database(canonical, from_fiscal_year=2025, tickers=list(SAMPLES), client=_client(), apply=True)
    assert result["status_counts"] == {"VERIFIED": 4, "UNRESOLVED": 0, "AMBIGUOUS": 0, "NOT_FOUND": 0}
    with sqlite3.connect(canonical) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            "SELECT * FROM v4_result_publication_authority ORDER BY company_id"
        ).fetchall()
        evidence = connection.execute(
            "SELECT * FROM v4_result_publication_evidence ORDER BY company_id"
        ).fetchall()
        old_dates = connection.execute(
            "SELECT DISTINCT first_public_result_date,source_availability_date FROM v4_quarter"
        ).fetchall()
    assert [row["result_publication_timestamp_utc"] for row in rows] == [value[5] for value in SAMPLES.values()]
    assert all(row["result_publication_source"] == "SEC_8K_ITEM_2_02" for row in rows)
    assert all(row["result_publication_confidence"] == "HIGH" for row in rows)
    assert all(row["item_2_02_status"] == "PRESENT_AND_DOCUMENT_CONFIRMED" for row in evidence)
    assert all(row["accession_number"] for row in evidence)
    assert [tuple(row) for row in old_dates] == [("2026-09-22", "2026-09-22")]
    resumed = enrich_database(canonical, from_fiscal_year=2025, tickers=list(SAMPLES), client=_client(), apply=True)
    assert resumed["scope_quarters"] == 0


def test_matching_requires_cik_scope_and_period_context() -> None:
    quarter = {"quarter_id": 1, "company_id": 1, "fiscal_year": 2026, "fiscal_quarter": "Q2", "period_end": "2026-06-30"}
    assert match_quarter_context("second quarter 2026 financial results", quarter) == "CIK_ITEM_2_02_EXPLICIT_FISCAL_QUARTER"
    assert match_quarter_context("earnings announced July 30, 2026", quarter) is None
    filings = _client().item_2_02_filings("0001018724")
    matches, unresolved = resolve_sec_filings([quarter], filings)
    assert (1, 2026, "Q2") in matches
    assert not unresolved


def test_statuses_precedence_conflict_and_verified_restart_preservation(tmp_path: Path) -> None:
    canonical = _database(tmp_path)
    quarter = {"quarter_id": 1, "company_id": 1, "fiscal_year": 2026, "fiscal_quarter": "Q3"}
    with sqlite3.connect(canonical) as connection:
        connection.row_factory = sqlite3.Row
        ensure_result_publication_schema(connection)
        sec = _manual_evidence(quarter, "SEC_8K_ITEM_2_02", "2026-07-30T20:30:28Z", "sec")
        issuer = _manual_evidence(quarter, "ISSUER_EARNINGS_RELEASE", "2026-07-30T20:25:00Z", "issuer")
        assert apply_resolution(connection, quarter, [sec], now=NOW) == "VERIFIED"
        assert apply_resolution(connection, quarter, [issuer], now=NOW) == "VERIFIED"
        assert apply_resolution(connection, quarter, [], now=NOW) == "VERIFIED"
        row = connection.execute("SELECT * FROM v4_result_publication_authority WHERE company_id=1").fetchone()
        assert row["result_publication_source"] == "ISSUER_EARNINGS_RELEASE"
        conflict = _manual_evidence(quarter, "ISSUER_EARNINGS_RELEASE", "2026-07-30T20:24:00Z", "issuer-conflict")
        assert apply_resolution(connection, quarter, [conflict], now=NOW) == "AMBIGUOUS"
        assert connection.execute("SELECT COUNT(*) FROM v4_result_publication_evidence").fetchone()[0] == 3
        conflicted = connection.execute("SELECT * FROM v4_result_publication_authority WHERE company_id=1").fetchone()
        assert conflicted["result_publication_timestamp_utc"] == "2026-07-30T20:25:00Z"
        assert pit_result_side(NOW, dict(conflicted)) is None

        quarter2 = {"quarter_id": 2, "company_id": 2, "fiscal_year": 2026, "fiscal_quarter": "Q4"}
        assert apply_resolution(connection, quarter2, [], unresolved=True, now=NOW) == "UNRESOLVED"
        quarter3 = {"quarter_id": 3, "company_id": 3, "fiscal_year": 2026, "fiscal_quarter": "Q2"}
        assert apply_resolution(connection, quarter3, [], now=NOW) == "NOT_FOUND"


def test_yahoo_history_is_stored_as_secondary_evidence_and_never_selected(tmp_path: Path) -> None:
    canonical = _database(tmp_path)
    quarter = {"quarter_id": 1, "company_id": 1, "fiscal_year": 2026, "fiscal_quarter": "Q3"}
    yahoo = yahoo_evidence_payload(
        quarter,
        provider_symbol="AAPL",
        event_timestamp="2026-07-30T16:00:00-04:00",
        source_timezone="America/New_York",
        fetched_at_utc=NOW,
        security_id=1,
    )
    with sqlite3.connect(canonical) as connection:
        connection.row_factory = sqlite3.Row
        store_secondary_evidence(connection, yahoo, now=NOW)
        assert apply_resolution(connection, quarter, [yahoo], now=NOW) == "NOT_FOUND"
        evidence = connection.execute("SELECT * FROM v4_result_publication_evidence").fetchone()
        authority = connection.execute("SELECT * FROM v4_result_publication_authority").fetchone()
    assert evidence["source_type"] == "YAHOO_EARNINGS_CALENDAR"
    assert evidence["source_timestamp_original"] == "2026-07-30T16:00:00-04:00"
    assert evidence["source_timestamp_utc"] == "2026-07-30T20:00:00Z"
    assert evidence["source_timezone"] == "America/New_York"
    assert evidence["disposition"] == "REJECTED"
    assert authority["result_publication_timestamp_utc"] is None
