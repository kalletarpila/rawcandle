from __future__ import annotations

import hashlib
import json
import sqlite3
import fcntl
from contextlib import contextmanager
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.remove_tickers import (
    _canonical_plan,
    _shared_sources,
    run_preview,
    run_test,
)
from rawcandle.fundamentals.admin.operation_report import build_operation_summary
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.phase13b_foundation import CANONICAL_SCHEMA_SQL as UNIVERSE_SCHEMA_SQL
from rawcandle.fundamentals.schema.migrations import (
    CANONICAL_SCHEMA_SQL,
    bootstrap_database,
)
from rawcandle.fundamentals.ttm.engine import TTM_SCHEMA_SQL, load_canonical_rows


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _paths(tmp_path: Path) -> BatchAddTickerPaths:
    tmp_path.mkdir(parents=True, exist_ok=True)
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
    now = "2026-09-23T00:00:00Z"
    bootstrap_database(canonical, "fundamentals_v4", CANONICAL_SCHEMA_SQL, now)
    with sqlite3.connect(canonical) as connection:
        connection.executemany(
            "INSERT INTO company VALUES(?,?,?,?,?,?)",
            ((1,'C1','Alpha','ACTIVE',now,now),(2,'C2','Beta','ACTIVE',now,now),(3,'C3','Gamma','ACTIVE',now,now)),
        )
        connection.executemany(
            "INSERT INTO security VALUES(?,?,?,?,?,?,?,?,?)",
            (
                (11,1,'AAA','NASDAQ',1,None,None,now,now),
                (21,2,'BBB','NASDAQ',1,None,None,now,now),
                (22,2,'BBB.B','NASDAQ',1,None,None,now,now),
                (31,3,'NEW','NASDAQ',1,None,None,now,now),
                (32,3,'GONE','NASDAQ',0,None,'2025-01-01',now,now),
            ),
        )
        connection.executemany(
            "INSERT INTO ticker_alias VALUES(?,?,?,?,?,?,?)",
            (
                (1,11,'AAA','SHARADAR',None,None,'fixture'),
                (2,31,'OLD','SHARADAR',None,'2025-01-01','fixture'),
                (3,32,'GONE','SHARADAR',None,'2025-01-01','fixture'),
            ),
        )
        quarter_id = 0
        for company_id in (1, 2, 3):
            for quarter, period_end in enumerate(('2025-03-31','2025-06-30','2025-09-30','2025-12-31'), start=1):
                quarter_id += 1
                connection.execute(
                    "INSERT INTO v4_quarter VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (quarter_id,company_id,2025,f'Q{quarter}',period_end,f'Q{quarter}',period_end,
                     'SHARADAR','CANONICAL',period_end,period_end,now,now),
                )
                connection.execute(
                    "INSERT INTO v4_quarter_financials(quarter_id,revenue,gross_profit,operating_income,ebit,ebitda,net_income,operating_cashflow,capex,free_cashflow,cash,total_debt,shares_outstanding,canonical_source_policy,created_at_utc,updated_at_utc,net_income_common) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (quarter_id,100,50,20,20,25,10,15,-5,10,30,5,10,'fixture',now,now,10),
                )
        connection.executescript(UNIVERSE_SCHEMA_SQL)
        connection.execute(
            "INSERT INTO fundamentals_operational_universe_version VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ('u1','PHASE13B_OPERATIONAL_UNIVERSE_CONTRACT_V1','CURRENT_OPERATIONAL_UNIVERSE',
             '2026-09-23','source','economic','physical','COMPLETE',3,3,4,0,1,
             '2026-09-23T00:00:00Z','2026-09-23T00:00:00Z'),
        )
        connection.execute(
            "INSERT INTO fundamentals_operational_universe_active_version VALUES(1,'u1','2026-09-23T00:00:00Z')"
        )
        for row in (
            ('u1',1,11,'AAA','usa','ACTIVE_SINGLE_SECURITY','EXACT_ONE_ACTIVE_SECURITY',1,1),
            ('u1',2,None,'BBB,BBB.B','usa','ACTIVE_MULTI_SECURITY','MULTIPLE_ACTIVE_SECURITIES_REQUIRES_SECURITY_SELECTION',2,2),
            ('u1',3,31,'NEW','usa','ACTIVE_SINGLE_SECURITY','EXACT_ONE_ACTIVE_SECURITY',1,2),
        ):
            connection.execute(
                "INSERT INTO fundamentals_operational_universe_member VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*row,'2020-01-01',None,'FIXTURE','fixture','2026-09-23T00:00:00Z','2026-09-23T00:00:00Z'),
            )
        connection.executescript(TTM_SCHEMA_SQL)
    from rawcandle.fundamentals.phase12d import rebuild_ttm
    rebuild_ttm(canonical, applied_at=now)
    sqlite3.connect(analysis).close()
    sqlite3.connect(market).close()
    sqlite3.connect(taxonomy).close()
    return BatchAddTickerPaths(provider, canonical, analysis, market, taxonomy)


def _source_evidence() -> dict:
    return {
        "market": {
            "mode": "STABLE_SOURCE_BUNDLE",
            "bundle_path": "/tmp/remove-tickers-fixture-market.db",
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


def _fake_downstream(paths, *, output: Path, as_of_date: str) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    analysis = output / "analysis_candidate.db"
    with sqlite3.connect(analysis) as connection:
        connection.execute("CREATE TABLE score_result(company_id INTEGER,security_id INTEGER,ticker TEXT)")
        with sqlite3.connect(paths["canonical"]) as canonical:
            rows = canonical.execute(
                "SELECT DISTINCT company_id,security_id FROM v4_ttm_values ORDER BY company_id"
            ).fetchall()
            for company_id, security_id in rows:
                ticker = canonical.execute(
                    "SELECT current_ticker FROM security WHERE security_id=?", (security_id,),
                ).fetchone()[0]
                connection.execute("INSERT INTO score_result VALUES(?,?,?)", (company_id, security_id, ticker))
    return {
        "status": "READY",
        "candidate_analysis_db": str(analysis),
        "invocation_counts": {
            "full_v2_rebuild": 1, "package": 1,
            "relative_position": 1, "relative_valuation": 1,
        },
    }


def _preview_and_test(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    raw_inputs: str,
    *,
    paths: BatchAddTickerPaths | None = None,
) -> tuple[dict, dict, BatchAddTickerPaths]:
    paths = paths or _paths(tmp_path)
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.remove_tickers.structural_break.apply_contract",
        lambda *_args, **_kwargs: {"outcome": "READY"},
    )
    preview = run_preview(
        raw_inputs, source_paths=paths, run_root=tmp_path / "preview_runs",
        temp_root=tmp_path / "temp", journal_path=tmp_path / "journal.json",
        source_context=_fake_source_context,
    )
    result = run_test(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"],
        source_paths=paths, run_root=tmp_path / "test_runs", temp_root=tmp_path / "temp",
        journal_path=tmp_path / "journal.json", lock_path=tmp_path / "remove.lock",
        source_context=_fake_source_context, downstream_runner=_fake_downstream,
        as_of_date="2026-09-23",
    )
    return preview, result, paths


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


def test_canonical_schema_rejects_duplicate_current_identity(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    with pytest.raises(sqlite3.IntegrityError), sqlite3.connect(paths.canonical_db) as connection:
        connection.execute(
            "INSERT INTO security VALUES(12,1,'AAA','NASDAQ',1,NULL,NULL,?,?)",
            ('2026-09-23T00:00:00Z', '2026-09-23T00:00:00Z'),
        )


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


def test_ui_dispatch_enables_test_but_keeps_production_unavailable(tmp_path: Path) -> None:
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

    def apply(**kwargs) -> dict:
        captured["apply"] = kwargs
        return {
            "operation_type": "REMOVE_TICKERS", "mode": "COPY_ONLY_APPLY",
            "outcome": "COMPLETED",
        }

    service = FundamentalsAdminUIService(
        run_root=tmp_path / "runs", remove_preview=preview, remove_apply=apply,
        recover_publication_on_startup=False,
    )
    capability = next(item for item in service.capabilities() if item.operation_type == "REMOVE_TICKERS")
    result = service.preview("REMOVE_TICKERS", raw_inputs="AAA")
    tested = service.copy_apply(
        "REMOVE_TICKERS", preview_payload_path="preview.json", preview_fingerprint="fingerprint",
    )
    assert (capability.preview_enabled, capability.copy_apply_enabled, capability.production_apply_enabled) == (True, True, False)
    assert captured["raw_inputs"] == "AAA"
    assert captured["apply"]["preview_fingerprint"] == "fingerprint"
    assert tested.outcome == "COMPLETED"
    assert result.copy_actionable is True
    with pytest.raises(ValueError, match="UNSUPPORTED_ADMIN_OPERATION"):
        service.production_apply(
            "REMOVE_TICKERS", preview_payload_path="preview.json",
            preview_fingerprint="fingerprint", confirmation="anything", test_run_id="test-run",
        )
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


def test_active_security_ttm_selection_is_generic_and_deterministic(tmp_path: Path) -> None:
    paths = _paths(tmp_path)

    def selected(company_id: int) -> set[int]:
        return {
            int(row["security_id"])
            for row in load_canonical_rows(paths.canonical_db)
            if int(row["company_id"]) == company_id
        }

    assert selected(1) == {11}
    assert selected(2) == {21}
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("UPDATE security SET active=0 WHERE security_id=21")
    assert selected(2) == {22}
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("UPDATE security SET active=0 WHERE security_id=22")
    assert selected(2) == set()
    assert selected(3) == {31}


def test_remove_test_single_security_preserves_identity_and_removes_current_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    before = {role: _hash(path) for role, path in paths.as_dict().items()}
    _, result, _ = _preview_and_test(tmp_path, monkeypatch, "AAA", paths=paths)

    assert result["outcome"] == "COMPLETED"
    assert result["removed_current_state_participation_verified"] is True
    assert result["active_universe_invariants"]["passed"] is True
    assert result["ttm_active_security_invariants"]["results"][0]["ttm_security_ids"] == []
    assert all(result["identity_invariants"].values())
    assert result["downstream"]["invocation_counts"]["full_v2_rebuild"] == 1
    assert result["full_market_copy_created"] is False
    assert result["full_taxonomy_copy_created"] is False
    assert result["cleanup"]["run_temp_exists"] is False
    assert before == {role: _hash(path) for role, path in paths.as_dict().items()}


def test_remove_test_shared_company_rebinds_ttm_to_active_sibling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, result, _ = _preview_and_test(tmp_path, monkeypatch, "BBB")

    assert result["outcome"] == "COMPLETED"
    target = result["active_universe_invariants"]["target_results"][0]
    assert target["active_sibling_security_ids"] == [22]
    assert target["company_participation_preserved"] is True
    assert result["ttm_active_security_invariants"]["results"][0]["ttm_security_ids"] == [22]
    assert result["ticker_results"][0]["company_rows_by_table"]["score_result"] == 1


def test_remove_test_batch_removing_all_company_securities_omits_company(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    preview, result, _ = _preview_and_test(tmp_path, monkeypatch, "BBB BBB.B")

    assert {item["classification"] for item in preview["removal_plan"]} == {
        "REMOVABLE_ACTIVE_SECURITY"
    }
    assert result["outcome"] == "COMPLETED"
    assert all(
        item["company_participation_matches"] and not item["company_participation_preserved"]
        for item in result["active_universe_invariants"]["target_results"]
    )
    assert all(
        item["ttm_security_ids"] == []
        for item in result["ttm_active_security_invariants"]["results"]
    )


@pytest.mark.parametrize(
    ("ticker", "expected"),
    (("GONE", "NO_CHANGE"), ("OLD", "REVIEW_REQUIRED")),
)
def test_remove_test_noop_and_review_stop_before_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, ticker: str, expected: str,
) -> None:
    _, result, _ = _preview_and_test(tmp_path, monkeypatch, ticker)
    assert result["outcome"] == expected
    assert result["cleanup"]["removed_count"] == 0
    assert not (tmp_path / "temp").exists()


def test_remove_test_blocked_and_stale_stop_before_candidate_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    with sqlite3.connect(paths.canonical_db) as connection:
        connection.execute("DELETE FROM fundamentals_operational_universe_member WHERE company_id=1")
    _, blocked, _ = _preview_and_test(tmp_path, monkeypatch, "AAA", paths=paths)
    assert blocked["outcome"] == "BLOCKED"
    assert blocked["cleanup"]["removed_count"] == 0

    paths = _paths(tmp_path / "stale")
    monkeypatch.setattr(
        "rawcandle.fundamentals.admin.remove_tickers.structural_break.apply_contract",
        lambda *_args, **_kwargs: {"outcome": "READY"},
    )
    preview = run_preview(
        "AAA", source_paths=paths, run_root=tmp_path / "stale_preview",
        temp_root=tmp_path / "stale_temp", journal_path=tmp_path / "stale_journal.json",
        source_context=_fake_source_context,
    )
    with sqlite3.connect(paths.provider_db) as connection:
        connection.execute("INSERT INTO sharadar_ticker_metadata VALUES('AAA','changed')")
    stale = run_test(
        preview_payload_path=Path(preview["preview_payload_path"]),
        preview_fingerprint=preview["preview_fingerprint"], source_paths=paths,
        run_root=tmp_path / "stale_test", temp_root=tmp_path / "stale_temp",
        journal_path=tmp_path / "stale_journal.json", lock_path=tmp_path / "stale.lock",
        source_context=_fake_source_context, downstream_runner=_fake_downstream,
    )
    assert stale["outcome"] == "STALE_PREVIEW"
    assert stale["cleanup"]["removed_count"] == 0
    assert not (tmp_path / "stale_temp").exists()


def test_remove_test_writer_contention_fails_without_candidates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _paths(tmp_path)
    preview = run_preview(
        "AAA", source_paths=paths, run_root=tmp_path / "preview",
        temp_root=tmp_path / "temp", journal_path=tmp_path / "journal.json",
        source_context=_fake_source_context,
    )
    lock_path = tmp_path / "remove.lock"
    with lock_path.open("a+") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = run_test(
            preview_payload_path=Path(preview["preview_payload_path"]),
            preview_fingerprint=preview["preview_fingerprint"], source_paths=paths,
            run_root=tmp_path / "test", temp_root=tmp_path / "temp",
            journal_path=tmp_path / "journal.json", lock_path=lock_path,
            source_context=_fake_source_context, downstream_runner=_fake_downstream,
        )
    assert result["outcome"] == "FAILED"
    assert result["errors"][0]["message"] == "REMOVE_TICKERS_TEST_ALREADY_RUNNING"
    assert not (tmp_path / "temp").exists()
