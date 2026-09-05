from __future__ import annotations

import hashlib
import json
import sqlite3
import re
from pathlib import Path

import pytest

from rawcandle.fundamentals.schema.contract import SCHEMA_VERSION
from rawcandle.fundamentals.schema.migrations import (
    CANONICAL_SCHEMA_SQL,
    PROVIDER_SCHEMA_SQL,
    bootstrap_database,
    connect,
    migrate_canonical_valuation_copy,
)
from rawcandle.fundamentals.schema.provenance import read_provenance, write_provenance
from rawcandle.fundamentals.schema.operating_working_capital import migrate_and_backfill_operating_working_capital
from rawcandle.fundamentals.ttm.engine import ensure_ttm_schema


def _hash_legacy_provenance(conn: sqlite3.Connection) -> str:
    payload = [tuple(row) for row in conn.execute("SELECT * FROM v4_field_provenance ORDER BY provenance_id")]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def _storage(conn: sqlite3.Connection, path: Path) -> tuple[int, int, int]:
    return (
        path.stat().st_size,
        int(conn.execute("PRAGMA page_count").fetchone()[0]),
        int(conn.execute("PRAGMA freelist_count").fetchone()[0]),
    )


def _fixture(tmp_path: Path, *, filler_rows: int = 0) -> tuple[Path, Path]:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    bootstrap_database(provider, "fundamentals_provider", PROVIDER_SCHEMA_SQL, "old")
    bootstrap_database(canonical, "fundamentals_v4", CANONICAL_SCHEMA_SQL, "old")
    with connect(canonical) as conn:
        ensure_ttm_schema(conn)
        conn.execute("DROP TABLE v4_operating_working_capital_provenance")
        conn.execute("DROP TABLE v4_common_earnings_provenance")
        for field in ("accounts_receivable", "inventory", "accounts_payable", "deferred_revenue", "total_assets"):
            conn.execute(f"ALTER TABLE v4_quarter_financials DROP COLUMN {field}")
        conn.execute("ALTER TABLE v4_quarter_financials DROP COLUMN net_income_common")
        conn.execute("ALTER TABLE v4_ttm_values DROP COLUMN ttm_net_income_common")
        conn.execute("ALTER TABLE v4_ttm_values DROP COLUMN net_income_common_4q_ready")
        conn.execute("UPDATE schema_version SET version='v4_2_lifecycle'")
        conn.execute("INSERT INTO company(company_id,company_key,created_at_utc,updated_at_utc) VALUES (1,'X','n','n')")
        conn.execute("INSERT INTO security(security_id,company_id,current_ticker,created_at_utc,updated_at_utc) VALUES (1,1,'X','n','n')")
        for qid in range(1, 5):
            conn.execute(
                """INSERT INTO v4_quarter(
                       quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,source_fiscalperiod,
                       source_reportperiod,identity_provider,identity_status,source_availability_date,
                       created_at_utc,updated_at_utc
                   ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (qid, 1, 2025, f"Q{qid}", f"2025-{qid * 3:02d}-28", f"Q{qid}", "r", "SHARADAR", "ACCEPTED", "2026-01-01", "n", "n"),
            )
            conn.execute(
                "INSERT INTO v4_quarter_financials(quarter_id,net_income,canonical_source_policy,created_at_utc,updated_at_utc) VALUES (?,?,'V1','n','n')",
                (qid, qid),
            )
            conn.execute(
                """INSERT INTO v4_field_provenance(
                       quarter_id,canonical_field,provider,provider_observation_id,source_native_field,
                       transformation,accepted_at_utc,rule_version,confidence
                   ) VALUES (?,'net_income','SHARADAR',?,'netinc','DIRECT','n','V1','HIGH')""",
                (qid, f"O{qid}"),
            )
        for index in range(filler_rows):
            conn.execute(
                """INSERT INTO v4_field_provenance(
                       quarter_id,canonical_field,provider,provider_observation_id,source_native_field,
                       transformation,accepted_at_utc,rule_version,confidence
                   ) VALUES (1,'revenue','SHARADAR',?,'revenue','DIRECT','n','V1','HIGH')""",
                (f"F{index}",),
            )
    with connect(provider) as conn:
        for field in ("receivables", "inventory", "payables", "deferredrev", "assets"):
            conn.execute(f"ALTER TABLE sharadar_fundamental_observation DROP COLUMN {field}")
        conn.execute("INSERT INTO provider_run(run_id,provider,started_at_utc,status,request_scope) VALUES ('R','SHARADAR','n','OK','TEST')")
        for qid in range(1, 5):
            conn.execute(
                """INSERT INTO provider_observation(
                       observation_id,run_id,provider,provider_record_key,native_table,fetched_at_utc,
                       content_hash,provider_status,payload_json
                   ) VALUES (?,'R','SHARADAR',?,'SF1','n',?,'ACCEPTED',?)""",
                (f"O{qid}", f"K{qid}", f"H{qid}", json.dumps({"netinccmn": qid + 10})),
            )
    return provider, canonical


def _schema_signature(conn: sqlite3.Connection) -> dict[str, object]:
    tables = ("v4_field_provenance", "v4_common_earnings_provenance", "v4_operating_working_capital_provenance", "v4_quarter_financials", "v4_ttm_values")
    return {
        table: {
            "normalized_sql": re.sub(
                r"\s+", " ", str(conn.execute("SELECT sql FROM sqlite_schema WHERE name=?", (table,)).fetchone()[0])
            ).strip().lower().replace(" )", ")"),
            "columns": [tuple(row) for row in conn.execute(f"PRAGMA table_info({table})")],
            "foreign_keys": [tuple(row) for row in conn.execute(f"PRAGMA foreign_key_list({table})")],
            "indexes": sorted(row[1] for row in conn.execute(f"PRAGMA index_list({table})")),
        }
        for table in tables
    }


def test_unified_provenance_api_routes_and_returns_one_shape(tmp_path: Path) -> None:
    canonical = tmp_path / "fresh.db"
    bootstrap_database(canonical, "fundamentals_v4", CANONICAL_SCHEMA_SQL, "n")
    with connect(canonical) as conn:
        conn.execute("INSERT INTO company(company_id,company_key,created_at_utc,updated_at_utc) VALUES (1,'X','n','n')")
        conn.execute("INSERT INTO v4_quarter(quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,source_fiscalperiod,source_reportperiod,identity_provider,identity_status,created_at_utc,updated_at_utc) VALUES (1,1,2025,'Q1','2025-03-31','Q1','r','S','A','n','n')")
        base = {
            "quarter_id": 1, "provider": "SHARADAR", "provider_observation_id": "O1",
            "transformation": "DIRECT", "accepted_at_utc": "n", "rule_version": "V1", "confidence": "HIGH",
        }
        assert write_provenance(conn, {**base, "canonical_field": "revenue", "source_native_field": "revenue"}) == 1
        assert write_provenance(conn, {**base, "canonical_field": "net_income_common", "source_native_field": "netinccmn"}) == 1
        rows = read_provenance(conn, quarter_id=1)
        assert len(rows) == 2
        assert rows[0].keys() == rows[1].keys()
        assert conn.execute("SELECT COUNT(*) FROM v4_field_provenance").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM v4_common_earnings_provenance").fetchone()[0] == 1
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO v4_field_provenance(
                       quarter_id,canonical_field,provider,provider_observation_id,source_native_field,
                       transformation,accepted_at_utc,rule_version,confidence
                   ) VALUES (1,'net_income_common','SHARADAR','OTHER','netinccmn','DIRECT','n','V1','HIGH')"""
            )
        assert read_provenance(conn, quarter_id=999) == []
        with pytest.raises(ValueError, match="UNKNOWN_CANONICAL"):
            read_provenance(conn, canonical_field="unknown")
        with pytest.raises(ValueError, match="INVALID_COMMON"):
            write_provenance(conn, {**base, "canonical_field": "net_income_common", "source_native_field": "netinc"})
        with pytest.raises(sqlite3.IntegrityError):
            write_provenance(conn, {**base, "canonical_field": "net_income_common", "source_native_field": "netinccmn"})


def test_additive_upgrade_preserves_legacy_table_and_is_idempotent(tmp_path: Path) -> None:
    provider, canonical = _fixture(tmp_path, filler_rows=3000)
    with connect(canonical) as conn:
        rootpage = conn.execute("SELECT rootpage FROM sqlite_schema WHERE name='v4_field_provenance'").fetchone()[0]
        sql = conn.execute("SELECT sql FROM sqlite_schema WHERE name='v4_field_provenance'").fetchone()[0]
        legacy_hash = _hash_legacy_provenance(conn)
        initial_size, _, initial_free = _storage(conn, canonical)
    first = migrate_canonical_valuation_copy(canonical, provider, "new")
    with connect(canonical) as conn:
        first_size, _, first_free = _storage(conn, canonical)
        assert conn.execute("SELECT rootpage FROM sqlite_schema WHERE name='v4_field_provenance'").fetchone()[0] == rootpage
        assert conn.execute("SELECT sql FROM sqlite_schema WHERE name='v4_field_provenance'").fetchone()[0] == sql
        assert _hash_legacy_provenance(conn) == legacy_hash
        assert conn.execute("SELECT COUNT(*) FROM v4_common_earnings_provenance").fetchone()[0] == 4
        assert conn.execute("SELECT version FROM schema_version WHERE db_name='fundamentals_v4'").fetchone()[0] == SCHEMA_VERSION
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
    second = migrate_canonical_valuation_copy(canonical, provider, "newer")
    with connect(canonical) as conn:
        second_size, _, second_free = _storage(conn, canonical)
        assert conn.execute("SELECT applied_at_utc FROM schema_version WHERE db_name='fundamentals_v4'").fetchone()[0] == "new"
    assert first["canonical_rows_backfilled"] == first["provenance_rows_added"] == 4
    assert second["canonical_rows_backfilled"] == second["provenance_rows_added"] == second["ttm_rows_changed"] == 0
    assert initial_free == first_free == second_free == 0
    # The prior defect copied the whole provenance table. Eight MiB is generous for three columns,
    # one small restricted table, indexes, and SQLite page-boundary variation in this fixture.
    assert first_size - initial_size < 8 * 1024 * 1024
    assert second_size - first_size < 64 * 1024


@pytest.mark.parametrize("failure_at", ["schema", "backfill", "ttm"])
def test_additive_upgrade_rolls_back_injected_failure(tmp_path: Path, failure_at: str) -> None:
    provider, canonical = _fixture(tmp_path)
    with connect(canonical) as conn:
        legacy_hash = _hash_legacy_provenance(conn)
    with pytest.raises(RuntimeError, match="INJECTED"):
        migrate_canonical_valuation_copy(canonical, provider, "new", inject_failure_at=failure_at)
    with connect(canonical) as conn:
        assert "net_income_common" not in {row[1] for row in conn.execute("PRAGMA table_info(v4_quarter_financials)")}
        assert conn.execute("SELECT 1 FROM sqlite_schema WHERE name='v4_common_earnings_provenance'").fetchone() is None
        assert conn.execute("SELECT version FROM schema_version").fetchone()[0] == "v4_2_lifecycle"
        assert _hash_legacy_provenance(conn) == legacy_hash
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_fresh_and_upgraded_schema_have_matching_active_contract(tmp_path: Path) -> None:
    provider, upgraded = _fixture(tmp_path / "upgrade")
    migrate_canonical_valuation_copy(upgraded, provider, "new")
    migrate_and_backfill_operating_working_capital(provider, upgraded, "new")
    fresh = tmp_path / "fresh.db"
    bootstrap_database(fresh, "fundamentals_v4", CANONICAL_SCHEMA_SQL, "new")
    with connect(fresh) as conn:
        ensure_ttm_schema(conn)
        fresh_signature = _schema_signature(conn)
    with connect(upgraded) as conn:
        upgraded_signature = _schema_signature(conn)
    assert fresh_signature == upgraded_signature
