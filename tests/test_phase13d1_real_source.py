from __future__ import annotations

import sqlite3
from pathlib import Path

from rawcandle.fundamentals.phase13d1_real_source import (
    SNDK_PERMATICKER,
    archive_rows_for_ticker,
    connect_sndk_taxonomy_identity,
    select_local_provider_candidate,
    sndk_identity_evidence,
)


def _provider(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE sharadar_fundamental_observation(ticker TEXT, reportperiod TEXT);
            INSERT INTO sharadar_fundamental_observation VALUES
              ('AREB','2025-12-31'),('AREB','2024-12-31'),('AVB','2026-06-30');
            CREATE TABLE sharadar_ticker_metadata(
              table_name TEXT,ticker TEXT,permaticker TEXT,name TEXT,exchange TEXT,isdelisted TEXT,
              category TEXT,relatedtickers TEXT,secfilings TEXT,firstpricedate TEXT,lastpricedate TEXT,
              firstquarter TEXT,lastquarter TEXT,lastupdated TEXT
            );
            INSERT INTO sharadar_ticker_metadata VALUES
              ('fundamentals','SNDK','643888','SANDISK CORP','NASDAQ','N','Domestic Common Stock','SNDKV','https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0002023554','2025-02-24','2026-08-28','2023-06-30','2026-06-30','2026-08-18'),
              ('fundamentals','SNDK1','197210','SANDISK CORP','NASDAQ','Y','Domestic Common Stock','SNDK','https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0000315213','1995-11-08','2016-05-11','1995-12-31','2016-03-31','2025-02-03');
            """
        )


def _market(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE osakedata(osake TEXT, market TEXT, pvm TEXT);
            INSERT INTO osakedata VALUES
              ('AREB','usa','2026-09-11'),('AREB','usa','2026-09-10'),
              ('AVB','usa','2026-09-11'),('SNDK','usa','2026-09-11');
            """
        )


def _canonical(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE company(company_id INTEGER PRIMARY KEY,company_key TEXT,company_name TEXT,status TEXT,created_at_utc TEXT,updated_at_utc TEXT);
            CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT,exchange TEXT,active INTEGER,valid_from TEXT,valid_to TEXT,created_at_utc TEXT,updated_at_utc TEXT);
            CREATE TABLE ticker_alias(alias_id INTEGER PRIMARY KEY,security_id INTEGER,ticker TEXT,provider TEXT,valid_from TEXT,valid_to TEXT,source TEXT);
            CREATE TABLE provider_company_identity(provider TEXT,provider_identifier_type TEXT,provider_identifier_value TEXT,company_id INTEGER,provider_ticker TEXT,source TEXT,source_type TEXT,source_value TEXT,created_at_utc TEXT);
            INSERT INTO company VALUES (1,'T:AREB','AREB','ACTIVE','n','n'),(2,'T:AVB','AVB','ACTIVE','n','n');
            INSERT INTO security VALUES (1,1,'AREB','NASDAQ',0,NULL,NULL,'n','n'),(2,2,'AVB','NYSE',0,NULL,NULL,'n','n');
            """
        )


def _taxonomy(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.executescript(
            """
            CREATE TABLE ec_taxonomy_version(taxonomy_version_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,taxonomy_version_code TEXT,taxonomy_name TEXT,source_type TEXT,source_reference TEXT,source_hash TEXT,status TEXT,is_active INTEGER,active_from TEXT,active_to TEXT,created_at_utc TEXT);
            CREATE TABLE ec_entity(entity_id INTEGER PRIMARY KEY,ecosystem_id INTEGER NOT NULL,entity_type TEXT NOT NULL,entity_code TEXT NOT NULL,entity_name TEXT,ticker TEXT,status TEXT NOT NULL,active_from TEXT,active_to TEXT,created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at_utc TEXT,entity_level INTEGER,entity_role_code TEXT);
            CREATE TABLE ec_membership(membership_id INTEGER PRIMARY KEY,ecosystem_id INTEGER NOT NULL,taxonomy_version_id INTEGER NOT NULL,parent_entity_id INTEGER NOT NULL,child_entity_id INTEGER NOT NULL,membership_type TEXT NOT NULL,membership_role TEXT,is_primary INTEGER NOT NULL DEFAULT 0,role_weight REAL,status TEXT NOT NULL,active_from TEXT,active_to TEXT,source_note TEXT,created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE ec_entity_alias(entity_alias_id INTEGER PRIMARY KEY,ecosystem_id INTEGER NOT NULL,entity_id INTEGER NOT NULL,alias_type TEXT NOT NULL CHECK (alias_type IN ('DC_GROUP_NAME','TICKER','DISPLAY_NAME','LEGACY_CODE')),alias_value TEXT NOT NULL,source_system TEXT NOT NULL DEFAULT 'UNKNOWN',status TEXT NOT NULL CHECK (status IN ('ACTIVE','INACTIVE','DEPRECATED')),active_from TEXT,active_to TEXT,created_at_utc TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,UNIQUE(ecosystem_id,alias_type,alias_value,source_system));
            INSERT INTO ec_taxonomy_version VALUES (1,1,'TAX','Tax','fixture','fixture','hash','ACTIVE',1,'2026-01-01',NULL,'n');
            INSERT INTO ec_entity(entity_id,ecosystem_id,entity_type,entity_code,entity_name,ticker,status) VALUES
              (10,1,'GROUP_L2','MEMORY','Memory',NULL,'ACTIVE'),
              (258,1,'TICKER','SNDK','SNDK','SNDK','ACTIVE');
            INSERT INTO ec_membership(membership_id,ecosystem_id,taxonomy_version_id,parent_entity_id,child_entity_id,membership_type,membership_role,is_primary,role_weight,status) VALUES
              (1,1,1,10,258,'CONTAINS','EXTENDED',1,1.0,'ACTIVE'),
              (2,1,1,10,258,'CONTAINS','EXTENDED',1,1.0,'ACTIVE');
            """
        )


def test_local_provider_selection_is_evidence_based(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    market = tmp_path / "market.db"
    canonical = tmp_path / "canonical.db"
    taxonomy = tmp_path / "taxonomy.db"
    _provider(provider)
    _market(market)
    _canonical(canonical)
    _taxonomy(taxonomy)

    selection = select_local_provider_candidate(
        provider_db=provider,
        market_db=market,
        canonical_db=canonical,
        taxonomy_db=taxonomy,
    )
    assert selection["selected_ticker"] == "AREB"
    selected = selection["selected"]
    assert selected["provider_rows"] > 0
    assert selected["market_rows"] > 0
    assert selected["canonical_active_security"] == 0
    assert selected["taxonomy_present"] is False


def test_sndk_archive_rows_are_available_without_api() -> None:
    rows = archive_rows_for_ticker("SNDK", limit=10)
    assert rows
    assert {row["ticker"] for row in rows} == {"SNDK"}
    assert {row["dimension"] for row in rows} & {"ARQ", "MRQ", "MRT"}


def test_sndk_identity_evidence_detects_current_identity_and_predecessor(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    market = tmp_path / "market.db"
    canonical = tmp_path / "canonical.db"
    taxonomy = tmp_path / "taxonomy.db"
    _provider(provider)
    _market(market)
    _canonical(canonical)
    _taxonomy(taxonomy)
    evidence = sndk_identity_evidence(provider_db=provider, canonical_db=canonical, market_db=market, taxonomy_db=taxonomy)
    assert evidence["identity_status"] == "RESOLVED_WITH_PREDECESSOR_RISK"
    assert evidence["permanent_provider_identity"]["permaticker"] == SNDK_PERMATICKER
    assert evidence["taxonomy_memberships"]
    assert evidence["taxonomy_duplicate_membership_count"] > 0
    assert any(row["permaticker"] == "197210" for row in evidence["predecessor_or_reuse_metadata"])


def test_sndk_taxonomy_connection_adds_aliases_without_duplicate_membership(tmp_path: Path) -> None:
    taxonomy_copy = tmp_path / "analysis.db"
    _taxonomy(taxonomy_copy)

    with sqlite3.connect(taxonomy_copy) as conn:
        before_memberships = conn.execute(
            "SELECT COUNT(*) FROM ec_membership WHERE child_entity_id=(SELECT entity_id FROM ec_entity WHERE ticker='SNDK' LIMIT 1)"
        ).fetchone()[0]

    result = connect_sndk_taxonomy_identity(
        taxonomy_copy,
        company_id=999001,
        security_id=999002,
        now="2026-09-12T00:00:00Z",
    )

    assert result["outcome"] == "CONNECTED_EXISTING_MEMBERSHIP"
    assert result["created_duplicate_memberships"] == 0
    assert result["economic_fingerprint_changed"] is False
    with sqlite3.connect(taxonomy_copy) as conn:
        after_memberships = conn.execute(
            "SELECT COUNT(*) FROM ec_membership WHERE child_entity_id=(SELECT entity_id FROM ec_entity WHERE ticker='SNDK' LIMIT 1)"
        ).fetchone()[0]
        aliases = conn.execute(
            "SELECT alias_type,alias_value FROM ec_entity_alias WHERE entity_id=?",
            (result["entity_id"],),
        ).fetchall()
    assert after_memberships == before_memberships
    assert ("LEGACY_CODE", f"SHARADAR_PERMATICKER:{SNDK_PERMATICKER}") in aliases
    assert ("LEGACY_CODE", "CANONICAL_COMPANY_ID:999001") in aliases
