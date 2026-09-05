from __future__ import annotations

import json
from pathlib import Path

import pytest

from rawcandle.cli.run_fundamentals_v4_working_capital_rehearsal import build_parser, run
from rawcandle.fundamentals.schema.migrations import CANONICAL_SCHEMA_SQL, PROVIDER_SCHEMA_SQL, bootstrap_database, connect
from rawcandle.fundamentals.schema.operating_working_capital import migrate_and_backfill_operating_working_capital
from rawcandle.fundamentals.schema.provenance import read_provenance
from rawcandle.fundamentals.ttm.engine import ensure_ttm_schema


FIELDS = {
    "accounts_receivable": "receivables",
    "inventory": "inventory",
    "accounts_payable": "payables",
    "deferred_revenue": "deferredrev",
    "total_assets": "assets",
}


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    provider, canonical = tmp_path / "provider.db", tmp_path / "canonical.db"
    bootstrap_database(provider, "fundamentals_provider", PROVIDER_SCHEMA_SQL, "old")
    bootstrap_database(canonical, "fundamentals_v4", CANONICAL_SCHEMA_SQL, "old")
    with connect(provider) as conn:
        for field in FIELDS.values():
            conn.execute(f"ALTER TABLE sharadar_fundamental_observation DROP COLUMN {field}")
        conn.execute("UPDATE schema_version SET version='old'")
        conn.execute("INSERT INTO provider_run(run_id,provider,started_at_utc,status,request_scope) VALUES ('R','SHARADAR','n','OK','TEST')")
        observations = [
            ("OLD", "2025-03-31", "2025-Q1", "2025-04-01", {"receivables": 1, "inventory": 0, "payables": 3, "deferredrev": "", "assets": 100}),
            ("NEW", "2025-03-31", "2025-Q1", "2025-04-02", {"receivables": 11, "inventory": 0, "payables": 13, "deferredrev": None, "assets": 110}),
            ("Q2", "2025-06-30", "2025-Q2", "2025-07-01", {"receivables": "bad", "inventory": 20, "payables": 30, "deferredrev": 40, "assets": "inf"}),
        ]
        for oid, reportperiod, fiscalperiod, updated, payload in observations:
            conn.execute(
                """INSERT INTO provider_observation(observation_id,run_id,provider,provider_record_key,company_id,
                   provider_ticker,native_table,dimension,reportperiod,fiscalperiod,source_availability_date,
                   fetched_at_utc,content_hash,provider_status,payload_json)
                   VALUES (?,'R','SHARADAR',?,1,'X','fundamentals','ARQ',?,?,?,'n',?,'SUCCESS',?)""",
                (oid, oid, reportperiod, fiscalperiod, updated, oid, json.dumps(payload)),
            )
            conn.execute(
                """INSERT INTO sharadar_fundamental_observation(observation_id,ticker,dimension,reportperiod,
                   fiscalperiod,date,lastupdated) VALUES (?,'X','ARQ',?,?,?,?)""",
                (oid, reportperiod, fiscalperiod, updated, updated),
            )
    with connect(canonical) as conn:
        ensure_ttm_schema(conn)
        conn.execute("DROP TABLE v4_operating_working_capital_provenance")
        for field in FIELDS:
            conn.execute(f"ALTER TABLE v4_quarter_financials DROP COLUMN {field}")
        conn.execute("UPDATE schema_version SET version='old'")
        conn.execute("INSERT INTO company(company_id,company_key,created_at_utc,updated_at_utc) VALUES (1,'X','n','n')")
        for qid, fq, period in ((1, "Q1", "2025-03-31"), (2, "Q2", "2025-06-30")):
            conn.execute(
                """INSERT INTO v4_quarter(quarter_id,company_id,fiscal_year,fiscal_quarter,period_end,
                   source_fiscalperiod,source_reportperiod,identity_provider,identity_status,source_availability_date,
                   created_at_utc,updated_at_utc) VALUES (?,1,2025,?,?,?,?,'SHARADAR_ARQ','ACCEPTED','x','n','n')""",
                (qid, fq, period, f"2025-{fq}", period),
            )
            conn.execute("INSERT INTO v4_quarter_financials(quarter_id,revenue,canonical_source_policy,created_at_utc,updated_at_utc) VALUES (?,99,'V1','n','n')", (qid,))
    return provider, canonical


def test_backfill_winner_null_zero_invalid_provenance_and_idempotency(tmp_path: Path) -> None:
    provider, canonical = _fixture(tmp_path)
    first = migrate_and_backfill_operating_working_capital(provider, canonical, "new")
    assert first["provider_columns_added"] == first["canonical_columns_added"] == 5
    assert first["invalid_values"] == 2
    with connect(canonical) as conn:
        q1 = conn.execute("SELECT * FROM v4_quarter_financials WHERE quarter_id=1").fetchone()
        assert (q1["accounts_receivable"], q1["inventory"], q1["accounts_payable"], q1["deferred_revenue"], q1["total_assets"]) == (11, 0, 13, None, 110)
        assert q1["revenue"] == 99
        assert len(read_provenance(conn, quarter_id=1)) == 4
        assert len(read_provenance(conn, canonical_field="inventory")) == 2
        assert not any(row[1] in FIELDS for row in conn.execute("PRAGMA table_info(v4_ttm_values)"))
    second = migrate_and_backfill_operating_working_capital(provider, canonical, "later")
    assert all(second[key] == 0 for key in ("provider_columns_added", "canonical_columns_added", "provider_rows_changed", "canonical_values_changed", "provenance_rows_added", "provenance_rows_removed"))


def test_provenance_read_does_not_migrate_old_database(tmp_path: Path) -> None:
    _, canonical = _fixture(tmp_path)
    with connect(canonical) as conn:
        assert read_provenance(conn, canonical_field="total_assets") == []
        assert conn.execute("SELECT 1 FROM sqlite_schema WHERE name='v4_operating_working_capital_provenance'").fetchone() is None


@pytest.mark.parametrize("stage", ["schema", "provider_backfill", "canonical_backfill"])
def test_failure_rolls_back_all_attached_changes(tmp_path: Path, stage: str) -> None:
    provider, canonical = _fixture(tmp_path)
    with pytest.raises(RuntimeError, match="INJECTED"):
        migrate_and_backfill_operating_working_capital(provider, canonical, "new", inject_failure_at=stage)
    with connect(provider) as conn:
        assert "assets" not in {row[1] for row in conn.execute("PRAGMA table_info(sharadar_fundamental_observation)")}
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    with connect(canonical) as conn:
        assert "total_assets" not in {row[1] for row in conn.execute("PRAGMA table_info(v4_quarter_financials)")}
        assert conn.execute("SELECT 1 FROM sqlite_schema WHERE name='v4_operating_working_capital_provenance'").fetchone() is None
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_company_scoped_changed_rebuild_and_provenance_api(tmp_path: Path) -> None:
    provider, canonical = _fixture(tmp_path)
    migrate_and_backfill_operating_working_capital(provider, canonical, "new")
    with connect(provider) as conn:
        payload = json.loads(conn.execute("SELECT payload_json FROM provider_observation WHERE observation_id='NEW'").fetchone()[0])
        payload["assets"] = 777
        conn.execute("UPDATE provider_observation SET payload_json=? WHERE observation_id='NEW'", (json.dumps(payload),))
    changed = migrate_and_backfill_operating_working_capital(provider, canonical, "changed", company_ids=[1])
    assert changed["provider_rows_changed"] == 1
    assert changed["canonical_values_changed"] == 1
    with connect(canonical) as conn:
        assert conn.execute("SELECT total_assets FROM v4_quarter_financials WHERE quarter_id=1").fetchone()[0] == 777
        assert read_provenance(conn, quarter_id=1, canonical_field="total_assets")[0]["provider_observation_id"] == "NEW"


def test_cli_defaults_dry_and_rejects_production(tmp_path: Path) -> None:
    args = build_parser().parse_args(["--provider-destination", str(tmp_path / "p.db"), "--canonical-destination", str(tmp_path / "c.db"), "--applied-at-utc", "n"])
    assert run(args)["mode"] == "DRY_RUN"
    args = build_parser().parse_args(["--provider-destination", "/home/kalle/projects/rawcandle/data/fundamentals_provider.db", "--canonical-destination", str(tmp_path / "c.db"), "--applied-at-utc", "n", "--apply"])
    with pytest.raises(PermissionError, match="PRODUCTION_OR_ALIAS"):
        run(args)


def test_fresh_and_upgraded_columns_match(tmp_path: Path) -> None:
    provider, upgraded = _fixture(tmp_path / "old")
    migrate_and_backfill_operating_working_capital(provider, upgraded, "new")
    fresh_provider, fresh_canonical = tmp_path / "fresh-p.db", tmp_path / "fresh-c.db"
    bootstrap_database(fresh_provider, "fundamentals_provider", PROVIDER_SCHEMA_SQL, "new")
    bootstrap_database(fresh_canonical, "fundamentals_v4", CANONICAL_SCHEMA_SQL, "new")
    with connect(fresh_provider) as fresh, connect(provider) as old:
        assert [tuple(row)[1:6] for row in fresh.execute("PRAGMA table_info(sharadar_fundamental_observation)")] == [tuple(row)[1:6] for row in old.execute("PRAGMA table_info(sharadar_fundamental_observation)")]
    with connect(fresh_canonical) as fresh, connect(upgraded) as old:
        assert [tuple(row)[1:6] for row in fresh.execute("PRAGMA table_info(v4_quarter_financials)")] == [tuple(row)[1:6] for row in old.execute("PRAGMA table_info(v4_quarter_financials)")]
