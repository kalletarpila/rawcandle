from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.remove_tickers import _canonical_plan, _shared_sources, run_preview
from rawcandle.fundamentals.admin.operation_report import build_operation_summary
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paths(tmp_path: Path) -> BatchAddTickerPaths:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    analysis = tmp_path / "analysis.db"
    market = tmp_path / "market.db"
    taxonomy = tmp_path / "taxonomy.db"
    with sqlite3.connect(provider) as connection:
        connection.executescript(
            """
            CREATE TABLE sharadar_fundamental_observation(ticker TEXT,dimension TEXT,value REAL);
            CREATE TABLE sharadar_ticker_metadata(ticker TEXT,name TEXT);
            CREATE TABLE provider_observation(company_id INTEGER,security_id INTEGER,value REAL);
            CREATE TABLE provider_company_identity(company_id INTEGER,provider_ticker TEXT);
            CREATE TABLE provider_security_identity(security_id INTEGER,provider_ticker TEXT);
            """
        )
    with sqlite3.connect(canonical) as connection:
        connection.executescript(
            """
            CREATE TABLE company(company_id INTEGER PRIMARY KEY,company_key TEXT,company_name TEXT,status TEXT);
            CREATE TABLE security(
              security_id INTEGER PRIMARY KEY,company_id INTEGER,current_ticker TEXT,active INTEGER,
              valid_from TEXT,valid_to TEXT
            );
            CREATE TABLE ticker_alias(alias_id INTEGER PRIMARY KEY,security_id INTEGER,ticker TEXT);
            CREATE TABLE fundamentals_operational_universe_active_version(
              singleton INTEGER PRIMARY KEY,universe_version_id TEXT
            );
            CREATE TABLE fundamentals_operational_universe_member(
              universe_version_id TEXT,company_id INTEGER,security_id INTEGER,current_ticker TEXT
            );
            INSERT INTO company VALUES(1,'C1','Alpha','ACTIVE'),(2,'C2','Beta','ACTIVE'),(3,'C3','Gamma','ACTIVE');
            INSERT INTO security VALUES
              (11,1,'AAA',1,NULL,NULL),(21,2,'BBB',1,NULL,NULL),(22,2,'BBB.B',1,NULL,NULL),
              (31,3,'NEW',1,NULL,NULL),(32,3,'GONE',0,NULL,'2025-01-01');
            INSERT INTO ticker_alias VALUES(1,11,'AAA'),(2,31,'OLD'),(3,32,'GONE');
            INSERT INTO fundamentals_operational_universe_active_version VALUES(1,'u1');
            INSERT INTO fundamentals_operational_universe_member VALUES
              ('u1',1,11,'AAA'),('u1',2,NULL,NULL),('u1',3,31,'NEW');
            """
        )
    sqlite3.connect(analysis).close()
    sqlite3.connect(market).close()
    sqlite3.connect(taxonomy).close()
    return BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)


def _source_evidence() -> dict:
    return {
        "market": {
            "mode": "STABLE_SOURCE_BUNDLE",
            "bundle_manifest": {
                "source_contract_version": "FUNDAMENTALS_READ_ONLY_SOURCE_V1",
                "as_of_date": "2026-09-23",
                "market": {
                    "semantic_fingerprint": "market-fp", "schema_fingerprint": "schema-fp",
                    "row_counts": {}, "valuation_coverage": {
                        "requirements": 0, "status_counts": {}, "status_identity_fingerprints": {},
                    },
                },
                "canonical_binding": {
                    "semantic_fingerprint": "canonical-fp", "valuation_requirement_count": 0,
                    "recent_ticker_count": 0, "validation_sample_ticker": "AAA",
                },
            },
        },
        "taxonomy": {
            "mode": "DIRECT_LOCKED_READ",
            "binding": {
                "domain": "dc_ecosystem", "version": "v1",
                "semantic_fingerprint": "taxonomy-fp", "membership_rows": 0,
            },
        },
    }


@contextmanager
def _fake_source_context(*_args, **_kwargs):
    yield _source_evidence()


@pytest.fixture(autouse=True)
def _taxonomy_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.remove_tickers._taxonomy_presence",
        lambda _paths, company_id: {
            "present": company_id == 1, "membership_count": int(company_id == 1),
            "memberships": [], "dependency": {"version": "v1", "semantic_fingerprint": "taxonomy-fp"},
            "planned_action": "READ_ONLY_REEVALUATION_DURING_FUTURE_REBUILD",
        },
    )


def test_classifies_removable_shared_absent_and_historical_alias(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    ordinary = _canonical_plan(paths.canonical_db, "AAA")
    shared = _canonical_plan(paths.canonical_db, "BBB")
    absent = _canonical_plan(paths.canonical_db, "GONE")
    alias = _canonical_plan(paths.canonical_db, "OLD")

    assert ordinary["classification"] == "REMOVABLE_ACTIVE_SECURITY"
    assert ordinary["permanent_identity_action"] == "PRESERVE_COMPANY_SECURITY_AND_TICKER_ALIAS_HISTORY"
    assert shared["classification"] == "SHARED_COMPANY_PRESERVE_COMPANY"
    assert {row["current_ticker"] for row in shared["related_securities_preserved"]} == {"BBB.B"}
    assert absent["classification"] == "ALREADY_ABSENT"
    assert alias["classification"] == "AMBIGUOUS_IDENTITY_REVIEW_REQUIRED"
    assert alias["expected_mutation_set"] == []


def test_operational_universe_and_security_active_disagreement_blocks(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("DELETE FROM fundamentals_operational_universe_member WHERE company_id=1")
    plan = _canonical_plan(paths.canonical_db, "AAA")
    assert plan["classification"] == "REMOVAL_BLOCKED"
    assert plan["reasons"] == ["SECURITY_ACTIVE_BUT_NOT_IN_ACTIVE_OPERATIONAL_UNIVERSE"]


def test_duplicate_current_identity_is_blocked(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("INSERT INTO security VALUES(12,1,'AAA',1,NULL,NULL)")
    plan = _canonical_plan(paths.canonical_db, "AAA")
    assert plan["classification"] == "REMOVAL_BLOCKED"
    assert plan["reasons"] == ["CURRENT_TICKER_IDENTITY_CONFLICT"]


def test_preview_is_read_only_deterministic_bound_and_creates_no_full_copies(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    journal = tmp_path / "journal.json"
    before = {role: _hash(path) for role, path in paths.as_dict().items()}
    kwargs = {
        "source_paths": paths, "temp_root": tmp_path / "temp", "journal_path": journal,
        "source_context": _fake_source_context,
    }
    first = run_preview("AAA BBB", run_root=tmp_path / "runs1", **kwargs)
    second = run_preview("AAA BBB", run_root=tmp_path / "runs2", **kwargs)

    assert first["preview_fingerprint"] == second["preview_fingerprint"]
    assert first["plan_binding"] == second["plan_binding"]
    assert first["read_only_source_binding"]["market"]["mode"] == "STABLE_SOURCE_BUNDLE"
    assert first["read_only_source_binding"]["taxonomy"]["mode"] == "DIRECT_LOCKED_READ"
    assert first["full_source_copies_created"] == 0
    assert not (tmp_path / "temp").exists()
    assert before == {role: _hash(path) for role, path in paths.as_dict().items()}


def test_shared_source_wiring_uses_bundle_and_direct_locked_taxonomy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    calls: dict = {}

    @contextmanager
    def lock_context(**kwargs):
        calls["lock"] = kwargs
        yield object()

    def bind(taxonomy_db, canonical_db, *, mode, operation_lock):
        calls["bind"] = (taxonomy_db, canonical_db, mode, operation_lock)
        return "direct-binding"

    def prepare(**kwargs):
        calls["prepare"] = kwargs
        return {"market": tmp_path / "compact.db", "taxonomy": paths.taxonomy_db}, _source_evidence()

    monkeypatch.setattr("rawcandle.fundamentals.admin.remove_tickers.taxonomy_operation_lock_context", lock_context)
    monkeypatch.setattr("rawcandle.fundamentals.admin.remove_tickers.bind_taxonomy_source", bind)
    monkeypatch.setattr("rawcandle.fundamentals.admin.remove_tickers.prepare_protected_read_only_sources", prepare)

    with _shared_sources(
        paths, bundle_dir=tmp_path / "bundle", as_of_date="2026-09-23",
        tickers=("AAA",), operation_id="remove-preview",
    ) as evidence:
        assert evidence["market"]["mode"] == "STABLE_SOURCE_BUNDLE"
    assert calls["bind"][2].value == "DIRECT_LOCKED_READ"
    assert calls["prepare"]["market_db"] == paths.market_db
    assert calls["prepare"]["taxonomy_db"] == paths.taxonomy_db
    assert calls["prepare"]["additional_full_history_tickers"] == ("AAA",)


def test_relevant_state_change_changes_binding(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    common = {
        "source_paths": paths, "temp_root": tmp_path / "temp", "journal_path": tmp_path / "journal.json",
        "source_context": _fake_source_context,
    }
    first = run_preview("AAA", run_root=tmp_path / "runs1", **common)
    with sqlite3.connect(paths.provider_db) as connection:
        connection.execute("INSERT INTO sharadar_ticker_metadata VALUES('AAA','Alpha')")
    second = run_preview("AAA", run_root=tmp_path / "runs2", **common)
    assert first["preview_fingerprint"] != second["preview_fingerprint"]


def test_nonterminal_publication_journal_blocks_before_source_preparation(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    journal = tmp_path / "journal.json"
    journal.write_text(json.dumps({"state": "PREPARED"}), encoding="utf-8")
    called = False

    @contextmanager
    def source(*_args, **_kwargs):
        nonlocal called
        called = True
        yield _source_evidence()

    with pytest.raises(RuntimeError, match="PUBLICATION_RECOVERY_REQUIRED"):
        run_preview(
            "AAA", source_paths=paths, run_root=tmp_path / "runs", temp_root=tmp_path / "temp",
            journal_path=journal, source_context=source,
        )
    assert called is False


def test_ui_dispatch_and_capability_are_preview_only(tmp_path: Path) -> None:
    captured: dict = {}

    def preview(raw_inputs: str, **_kwargs) -> dict:
        captured["raw_inputs"] = raw_inputs
        return {
            "operation_type": "REMOVE_TICKERS", "mode": "PREVIEW", "outcome": "COMPLETED",
            "removal_plan": [{
                "requested_ticker": "AAA", "classification": "REMOVABLE_ACTIVE_SECURITY",
                "removal_eligible": True, "company_id": 1, "security_id": 11,
            }],
        }

    service = FundamentalsAdminUIService(
        run_root=tmp_path / "runs", remove_preview=preview, recover_publication_on_startup=False,
    )
    capability = next(item for item in service.capabilities() if item.operation_type == "REMOVE_TICKERS")
    result = service.preview("REMOVE_TICKERS", raw_inputs="AAA")
    assert (capability.preview_enabled, capability.copy_apply_enabled, capability.production_apply_enabled) == (True, False, False)
    assert captured["raw_inputs"] == "AAA"
    assert build_operation_summary({
        "operation_type": "REMOVE_TICKERS", "mode": "PREVIEW", "outcome": "COMPLETED",
        "removal_plan": [{
            "requested_ticker": "AAA", "classification": "REMOVABLE_ACTIVE_SECURITY",
            "removal_eligible": True, "company_id": 1, "security_id": 11,
        }],
    }) == (
        "Preview completed.",
        "AAA: REMOVABLE_ACTIVE_SECURITY; eligible=True; company/security=1/11.",
    )


def test_ui_summary_exposes_eligible_review_and_blocked_states() -> None:
    rows = build_operation_summary({
        "operation_type": "REMOVE_TICKERS", "mode": "PREVIEW", "outcome": "REVIEW_REQUIRED",
        "removal_plan": [
            {"requested_ticker": "AAA", "classification": "REMOVABLE_ACTIVE_SECURITY", "removal_eligible": True, "company_id": 1, "security_id": 11},
            {"requested_ticker": "OLD", "classification": "AMBIGUOUS_IDENTITY_REVIEW_REQUIRED", "removal_eligible": False, "company_id": None, "security_id": None},
            {"requested_ticker": "BAD", "classification": "REMOVAL_BLOCKED", "removal_eligible": False, "company_id": 2, "security_id": 22},
        ],
    })
    assert any("REMOVABLE_ACTIVE_SECURITY; eligible=True" in row for row in rows)
    assert any("AMBIGUOUS_IDENTITY_REVIEW_REQUIRED; eligible=False" in row for row in rows)
    assert any("REMOVAL_BLOCKED; eligible=False" in row for row in rows)


def test_already_absent_is_informational_not_failure(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    result = run_preview(
        "GONE", source_paths=paths, run_root=tmp_path / "runs", temp_root=tmp_path / "temp",
        journal_path=tmp_path / "journal.json", source_context=_fake_source_context,
    )
    assert result["outcome"] == "COMPLETED"
    assert result["removal_plan"][0]["classification"] == "ALREADY_ABSENT"


def test_preview_artifact_is_visible_in_admin_history(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    run_root = tmp_path / "runs"
    result = run_preview(
        "AAA", source_paths=paths, run_root=run_root, temp_root=tmp_path / "temp",
        journal_path=tmp_path / "journal.json", source_context=_fake_source_context,
    )
    service = FundamentalsAdminUIService(
        run_root=run_root, recover_publication_on_startup=False,
    )
    entries = service.history_entries(limit=10)
    entry = next(item for item in entries if item.run_id == result["run_id"])
    assert entry.operation_type == "REMOVE_TICKERS"
    assert entry.mode == "PREVIEW"
    assert entry.report_available is True
