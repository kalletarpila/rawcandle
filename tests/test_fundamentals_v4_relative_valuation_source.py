from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.relative_valuation.candidate_snapshot import (
    CANDIDATE_REPORT_CONTRACT,
)
from rawcandle.fundamentals.relative_valuation.source import (
    ReadOnlySourcePaths,
    _active_universe_members,
    _bars,
    _listing_eligibility,
    _strip_filing_valuation_run_metadata,
    _strip_upstream_snapshot_identity,
    _validate_paths,
)


AS_OF_DATE = "2026-09-08"


def test_candidate_module_can_be_imported_directly() -> None:
    assert CANDIDATE_REPORT_CONTRACT.endswith("RELATIVE_VALUATION_CANDIDATE")


def test_source_paths_must_be_distinct_regular_files(tmp_path: Path) -> None:
    files = []
    for name in ("a.db", "b.db", "c.db", "d.db"):
        path = tmp_path / name
        sqlite3.connect(path).close()
        files.append(path)
    _validate_paths(ReadOnlySourcePaths(*files))
    with pytest.raises(ValueError, match="MUST_BE_DISTINCT"):
        _validate_paths(ReadOnlySourcePaths(files[0], files[0], files[2], files[3]))
    alias = tmp_path / "alias.db"
    alias.symlink_to(files[0])
    with pytest.raises(FileNotFoundError):
        _validate_paths(ReadOnlySourcePaths(alias, files[1], files[2], files[3]))


def test_source_paths_accept_optional_provider_db(tmp_path: Path) -> None:
    files = []
    for name in ("analysis.db", "canonical.db", "market.db", "taxonomy.db", "provider.db"):
        path = tmp_path / name
        sqlite3.connect(path).close()
        files.append(path)

    _validate_paths(ReadOnlySourcePaths(*files))


def test_listing_eligibility_uses_provider_delisting_date(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis.db"
    canonical = tmp_path / "canonical.db"
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    provider = tmp_path / "provider.db"
    for path in (analysis, market, taxonomy):
        sqlite3.connect(path).close()
    with sqlite3.connect(canonical) as conn:
        conn.execute(
            "CREATE TABLE security(security_id INTEGER,company_id INTEGER,current_ticker TEXT,exchange TEXT,active INTEGER,valid_from TEXT,valid_to TEXT)"
        )
        conn.execute("INSERT INTO security VALUES(192,192,'AREB','NASDAQ',0,NULL,NULL)")
    with sqlite3.connect(provider) as conn:
        conn.execute(
            "CREATE TABLE sharadar_ticker_metadata(table_name TEXT,ticker TEXT,permaticker TEXT,isdelisted TEXT,firstpricedate TEXT,lastpricedate TEXT,lastupdated TEXT)"
        )
        conn.execute(
            "INSERT INTO sharadar_ticker_metadata VALUES('fundamentals','AREB','637535','Y','2022-02-07','2026-05-12','2026-08-12')"
        )

    eligibility, metadata = _listing_eligibility(
        ReadOnlySourcePaths(analysis, canonical, market, taxonomy, provider),
        "2026-09-12",
    )

    assert eligibility[192] == (False, "POST_DELISTING")
    assert metadata["reason_counts"]["POST_DELISTING"] == 1


def test_active_universe_filter_does_not_treat_backfill_effective_start_as_listing_date(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.db"
    with sqlite3.connect(canonical) as conn:
        conn.executescript(
            """
            CREATE TABLE fundamentals_operational_universe_active_version(singleton INTEGER PRIMARY KEY, universe_version_id TEXT, activated_at_utc TEXT);
            CREATE TABLE fundamentals_operational_universe_member(
                universe_version_id TEXT,
                company_id INTEGER,
                security_id INTEGER,
                current_ticker TEXT,
                market TEXT,
                membership_status TEXT,
                identity_resolution_status TEXT,
                active_security_count INTEGER,
                all_security_count INTEGER,
                effective_start_date TEXT,
                effective_end_date TEXT,
                source TEXT,
                reason TEXT,
                created_at_utc TEXT,
                updated_at_utc TEXT
            );
            INSERT INTO fundamentals_operational_universe_active_version VALUES(1,'u1','2026-09-13T00:00:00Z');
            INSERT INTO fundamentals_operational_universe_member VALUES('u1',1,1,'ONE','usa','ACTIVE_SINGLE_SECURITY','OK',1,1,'2026-09-13',NULL,'backfill','current universe','n','n');
            INSERT INTO fundamentals_operational_universe_member VALUES('u1',192,192,'AREB','usa','HISTORICAL_RETAINED_NO_ACTIVE_SECURITY','OLD',0,1,'2026-09-13',NULL,'backfill','historical','n','n');
            """
        )

    members, metadata = _active_universe_members(canonical, "2026-09-12")

    assert members == {1}
    assert metadata["eligible_companies"] == 1


def test_market_bar_adapter_prefers_exact_ticker_and_never_reads_future(tmp_path: Path) -> None:
    path = tmp_path / "market.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            "CREATE TABLE osakedata(osake TEXT,pvm TEXT,open REAL,high REAL,low REAL,close REAL)"
        )
        connection.executemany(
            "INSERT INTO osakedata VALUES(?,?,?,?,?,?)",
            (
                ("Abc", "2026-09-07", 1.0, 1.0, 1.0, 1.0),
                ("ABC", "2026-09-08", 2.0, 2.0, 2.0, 2.0),
                ("ABC", "2026-09-09", 3.0, 3.0, 3.0, 3.0),
            ),
        )
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    try:
        bars = _bars(connection, "ABC", AS_OF_DATE)
    finally:
        connection.close()
    assert [(bar.price_date, bar.close) for bar in bars] == [("2026-09-08", 2.0)]


def test_relative_position_storage_ids_are_not_relative_valuation_source_input() -> None:
    row = {
        "snapshot_id": "lane-specific-relative-position-snapshot",
        "relative_position_result_id": 17,
        "company_id": 1,
        "peer_scope": "UNIVERSE",
        "percentile": 50.0,
    }

    cleaned = _strip_upstream_snapshot_identity(row)

    assert "snapshot_id" not in cleaned
    assert "relative_position_result_id" not in cleaned
    assert cleaned["company_id"] == 1
    assert row["snapshot_id"] == "lane-specific-relative-position-snapshot"


def test_filing_valuation_storage_identity_is_not_source_input() -> None:
    row = {
        "valuation_revised_result_id": 7,
        "company_id": 1,
        "total_valuation_score": 4.5,
        "calculated_at_utc": "2026-09-12T10:23:15Z",
    }

    cleaned = _strip_filing_valuation_run_metadata(row)

    assert "calculated_at_utc" not in cleaned
    assert "valuation_revised_result_id" not in cleaned
    assert cleaned["total_valuation_score"] == 4.5
