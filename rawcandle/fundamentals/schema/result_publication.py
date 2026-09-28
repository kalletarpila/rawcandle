from __future__ import annotations

import sqlite3


RESULT_PUBLICATION_RULE_VERSION = "result_publication_v1"

RESULT_PUBLICATION_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS v4_result_publication_evidence (
    evidence_id TEXT PRIMARY KEY,
    quarter_id INTEGER NOT NULL,
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter TEXT NOT NULL CHECK (fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    source_type TEXT NOT NULL CHECK (source_type IN (
        'ISSUER_EARNINGS_RELEASE','SEC_8K_ITEM_2_02','SEC_FILING_FALLBACK','MANUAL_REVIEW',
        'YAHOO_EARNINGS_CALENDAR'
    )),
    source_timestamp_utc TEXT NOT NULL,
    source_timestamp_original TEXT,
    source_timezone TEXT,
    observed_at_utc TEXT,
    fetched_at_utc TEXT,
    provider_symbol TEXT,
    security_id INTEGER,
    accession_number TEXT,
    document_id TEXT,
    filing_form TEXT,
    item_2_02_status TEXT,
    source_reference TEXT NOT NULL,
    matching_method TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    reviewed_manual INTEGER NOT NULL DEFAULT 0 CHECK (reviewed_manual IN (0,1)),
    evidence_hash TEXT NOT NULL UNIQUE,
    disposition TEXT NOT NULL CHECK (disposition IN ('ACCEPTED','CONFLICT','REJECTED')),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS v4_result_publication_authority (
    company_id INTEGER NOT NULL REFERENCES company(company_id),
    fiscal_year INTEGER NOT NULL,
    fiscal_quarter TEXT NOT NULL CHECK (fiscal_quarter IN ('Q1','Q2','Q3','Q4')),
    quarter_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('VERIFIED','UNRESOLVED','AMBIGUOUS','NOT_FOUND')),
    result_publication_timestamp_utc TEXT,
    result_publication_source TEXT CHECK (result_publication_source IS NULL OR result_publication_source IN (
        'ISSUER_EARNINGS_RELEASE','SEC_8K_ITEM_2_02','SEC_FILING_FALLBACK','MANUAL_REVIEW'
    )),
    result_publication_confidence TEXT CHECK (result_publication_confidence IS NULL OR result_publication_confidence IN ('HIGH','MEDIUM','LOW')),
    result_publication_evidence_reference TEXT,
    selected_evidence_id TEXT REFERENCES v4_result_publication_evidence(evidence_id),
    verified_at_utc TEXT,
    rule_version TEXT NOT NULL,
    status_reason TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    PRIMARY KEY(company_id,fiscal_year,fiscal_quarter),
    CHECK (
        (status='VERIFIED' AND result_publication_timestamp_utc IS NOT NULL AND
         result_publication_source IS NOT NULL AND result_publication_confidence IS NOT NULL AND
         selected_evidence_id IS NOT NULL AND verified_at_utc IS NOT NULL)
        OR status<>'VERIFIED'
    )
);

CREATE INDEX IF NOT EXISTS idx_v4_result_publication_evidence_quarter
ON v4_result_publication_evidence(company_id,fiscal_year,fiscal_quarter);
CREATE INDEX IF NOT EXISTS idx_v4_result_publication_authority_status
ON v4_result_publication_authority(status,result_publication_source);
"""


def ensure_result_publication_schema(connection: sqlite3.Connection) -> dict[str, int]:
    before = {
        str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    connection.executescript(RESULT_PUBLICATION_SCHEMA_SQL)
    after = {
        str(row[0]) for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    return {"tables_added": len(after - before)}
