from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.refresh_fundamentals import resolve_identity
from rawcandle.fundamentals.admin.publication_journal import prepare_journal, sqlite_verification, update_journal
from rawcandle.fundamentals.admin.refresh_production import _replace_role
from rawcandle.fundamentals.admin.universe_removal import (
    _analysis_effects,
    _company_model_fingerprints,
    _identity,
    assert_production_authorization,
    production_file_state,
    run_test,
)


def _analysis(path: Path, *, score: int, quarter_id: int) -> None:
    with sqlite3.connect(path) as connection:
        for table, value in (
            ("score_result", score),
            ("lifecycle_revised_result", 2),
            ("valuation_revised_result", 3),
            ("relative_position_result", 4),
            ("relative_valuation_company_result", 5),
        ):
            connection.execute(
                f"CREATE TABLE {table}(result_id INTEGER,company_id INTEGER,security_id INTEGER,"
                "quarter_id INTEGER,metric INTEGER,created_at_utc TEXT)"
            )
            connection.execute(
                f"INSERT INTO {table} VALUES(?,?,?,?,?,?)",
                (quarter_id, 1, 1, quarter_id, value, "different-run-time"),
            )


def test_analysis_effects_ignore_surrogate_ids_but_detect_economic_change(tmp_path: Path) -> None:
    before, same, changed = (tmp_path / name for name in ("before.db", "same.db", "changed.db"))
    _analysis(before, score=10, quarter_id=10)
    _analysis(same, score=10, quarter_id=999)
    _analysis(changed, score=11, quarter_id=1000)
    assert all(item["affected_company_count"] == 0 for item in _analysis_effects(before, same, 346).values())
    assert _analysis_effects(before, changed, 346)["score"]["affected_company_count"] == 1


def test_score_comparison_ignores_only_global_structural_lineage(tmp_path: Path) -> None:
    paths = [tmp_path / name for name in ("old.db", "lineage.db", "economic.db")]
    reasons = (
        '{"observed_points":10,"structural_contract_fingerprint":"old","structural_readiness_status":"STRUCTURAL_READY"}',
        '{"observed_points":10,"structural_contract_fingerprint":"new","structural_readiness_status":"STRUCTURAL_READY"}',
        '{"observed_points":11,"structural_contract_fingerprint":"new","structural_readiness_status":"STRUCTURAL_READY"}',
    )
    for path, reason in zip(paths, reasons, strict=True):
        with sqlite3.connect(path) as connection:
            connection.execute(
                "CREATE TABLE score_result(score_result_id INTEGER,company_id INTEGER,quarter_id INTEGER,"
                "total_score REAL,readiness_status TEXT,missing_input_reason TEXT,generated_at_utc TEXT)"
            )
            connection.execute("INSERT INTO score_result VALUES(1,1,10,10,'SCORE_FULL',?,'now')", (reason,))
    baseline = _company_model_fingerprints(paths[0], "score_result", exclude_company_id=346)
    assert baseline == _company_model_fingerprints(paths[1], "score_result", exclude_company_id=346)
    assert baseline != _company_model_fingerprints(paths[2], "score_result", exclude_company_id=346)


def test_production_authorization_requires_confirmation_bound_test_and_stable_generation() -> None:
    state = {"provider": "old"}
    preview = {
        "run_id": "preview", "ticker": "BNC", "preview_fingerprint": "fp",
        "production_file_state": state,
    }
    test = {
        "mode": "COPY_ONLY_APPLY", "outcome": "COMPLETED", "ticker": "BNC",
        "preview_run_id": "preview", "preview_fingerprint": "fp",
        "production_unchanged": True, "production_file_state_after": state,
    }
    with pytest.raises(PermissionError, match="CONFIRM_PRODUCTION_REQUIRED"):
        assert_production_authorization(
            preview=preview, test=test, preview_fingerprint="fp",
            current_state=state, confirm_production=False,
        )
    assert_production_authorization(
        preview=preview, test=test, preview_fingerprint="fp",
        current_state=state, confirm_production=True,
    )
    with pytest.raises(ValueError, match="GENERATION_CHANGED"):
        assert_production_authorization(
            preview=preview, test=test, preview_fingerprint="fp",
            current_state={"provider": "new"}, confirm_production=True,
        )

    stale_test = {**test, "preview_run_id": "other-preview"}
    with pytest.raises(ValueError, match="PREVIEW_RUN_INVALID"):
        assert_production_authorization(
            preview=preview, test=stale_test, preview_fingerprint="fp",
            current_state=state, confirm_production=True,
        )


def test_refresh_identity_uses_active_operational_universe(tmp_path: Path) -> None:
    provider, canonical = tmp_path / "provider.db", tmp_path / "canonical.db"
    with sqlite3.connect(provider) as connection:
        connection.execute("CREATE TABLE sharadar_ticker_metadata(table_name TEXT,ticker TEXT,permaticker TEXT,isdelisted TEXT,relatedtickers TEXT,lastupdated TEXT)")
    with sqlite3.connect(canonical) as connection:
        connection.executescript(
            """
            CREATE TABLE company(company_id INTEGER PRIMARY KEY);
            CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT);
            CREATE TABLE ticker_alias(security_id INTEGER,ticker TEXT);
            CREATE TABLE provider_security_identity(provider TEXT,provider_security_id TEXT,security_id INTEGER,provider_ticker TEXT);
            CREATE TABLE fundamentals_operational_universe_active_version(singleton INTEGER,universe_version_id TEXT);
            CREATE TABLE fundamentals_operational_universe_member(universe_version_id TEXT,company_id INTEGER,security_id INTEGER);
            INSERT INTO company VALUES(346);
            INSERT INTO security VALUES(346,346,'BNC');
            INSERT INTO ticker_alias VALUES(346,'BNC');
            INSERT INTO provider_security_identity VALUES('SHARADAR','193045',346,'BNC');
            INSERT INTO fundamentals_operational_universe_active_version VALUES(1,'without-bnc');
            """
        )
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    paths = BatchAddTickerPaths(provider, canonical, empty, empty, empty)
    assert resolve_identity(paths, "BNC")["status"] == "NOT_IN_CANONICAL_UNIVERSE"


def test_removal_identity_requires_exclusive_company_and_active_membership(tmp_path: Path) -> None:
    canonical = tmp_path / "canonical.db"
    with sqlite3.connect(canonical) as connection:
        connection.executescript(
            """
            CREATE TABLE company(
                company_id INTEGER PRIMARY KEY, company_key TEXT, company_name TEXT, status TEXT
            );
            CREATE TABLE security(
                security_id INTEGER PRIMARY KEY, company_id INTEGER, current_ticker TEXT,
                active INTEGER, valid_from TEXT, valid_to TEXT
            );
            CREATE TABLE ticker_alias(alias_id INTEGER,security_id INTEGER,ticker TEXT);
            CREATE TABLE fundamentals_operational_universe_active_version(
                singleton_id INTEGER, universe_version_id TEXT
            );
            CREATE TABLE fundamentals_operational_universe_member(
                universe_version_id TEXT, company_id INTEGER, security_id INTEGER
            );
            INSERT INTO company VALUES(346,'SEC_CIK:1','BNC','ACTIVE');
            INSERT INTO security VALUES(346,346,'BNC',1,NULL,NULL);
            INSERT INTO ticker_alias VALUES(346,346,'BNC');
            INSERT INTO fundamentals_operational_universe_active_version VALUES(1,'active');
            INSERT INTO fundamentals_operational_universe_member VALUES('active',346,346);
            """
        )
    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    paths = BatchAddTickerPaths(empty, canonical, empty, empty, empty)
    assert _identity(paths, "BNC")["company_security_exclusive"] is True
    with sqlite3.connect(canonical) as connection:
        connection.execute("INSERT INTO security VALUES(347,346,'BNC.A',1,NULL,NULL)")
    with pytest.raises(ValueError, match="IDENTITY_OWNERSHIP_AMBIGUOUS"):
        _identity(paths, "BNC")


def test_stale_removal_preview_rejects_before_candidate_creation(tmp_path: Path) -> None:
    databases = [tmp_path / f"{role}.db" for role in ("provider", "canonical", "analysis", "market", "taxonomy")]
    for path in databases:
        sqlite3.connect(path).close()
    paths = BatchAddTickerPaths(*databases)
    preview = {
        "run_id": "preview", "ticker": "BNC", "preview_fingerprint": "fp",
        "production_file_state": production_file_state(paths),
    }
    preview_path = tmp_path / "preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    with sqlite3.connect(databases[0]) as connection:
        connection.execute("CREATE TABLE changed(value INTEGER)")
    temp_root = tmp_path / "temp"
    with pytest.raises(ValueError, match="STALE_PREVIEW"):
        run_test(
            preview_payload_path=preview_path, preview_fingerprint="fp", source_paths=paths,
            run_root=tmp_path / "runs", temp_root=temp_root,
        )
    assert not temp_root.exists()


def test_removal_reuses_durable_three_role_publication_protocol_on_fixtures(tmp_path: Path) -> None:
    roles = {}
    for role in ("provider", "canonical", "analysis"):
        production = tmp_path / f"{role}.db"
        backup = tmp_path / f"{role}.backup.db"
        candidate_dir = tmp_path / "run" / "candidates"
        candidate_dir.mkdir(parents=True, exist_ok=True)
        candidate = candidate_dir / f"{role}.db"
        for path, generation in ((production, "OLD"), (backup, "OLD"), (candidate, "NEW")):
            with sqlite3.connect(path) as connection:
                connection.execute("CREATE TABLE generation(value TEXT)")
                connection.execute("INSERT INTO generation VALUES(?)", (generation,))
        roles[role] = {
            "production_path": str(production),
            "old_production_fingerprint": sqlite_verification(production)["sha256"],
            "backup_path": str(backup),
            "verified_backup_fingerprint": sqlite_verification(backup)["sha256"],
            "candidate_path": str(candidate),
            "candidate_fingerprint": sqlite_verification(candidate)["sha256"],
            "replacement_state": "NOT_STARTED",
        }
    journal_path = tmp_path / "journal.json"
    journal = prepare_journal(
        path=journal_path, operation_type="REMOVE_FUNDAMENTALS_TICKERS", run_id="run",
        preview_run_id="preview", test_run_id="test", refresh_set_fingerprint="removal-fp",
        old_source_watermark=None, new_source_watermark="UNCHANGED",
        source_schema_fingerprint="UNCHANGED", roles=roles,
    )
    for role in ("provider", "canonical", "analysis"):
        journal = _replace_role(role, journal, journal_path=journal_path)
    journal = update_journal(journal_path, journal, state="COMPLETED", current_publication_step="COMPLETED")
    assert journal["state"] == "COMPLETED"
    for role in roles:
        with sqlite3.connect(roles[role]["production_path"]) as connection:
            assert connection.execute("SELECT value FROM generation").fetchone()[0] == "NEW"
