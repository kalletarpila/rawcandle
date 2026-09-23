from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping

import pytest

import rawcandle.datacenter_taxonomy_operation_log as taxonomy_locking
from rawcandle.datacenter_taxonomy_operation_log import taxonomy_operation_lock_context
from rawcandle.fundamentals.admin import batch_add_tickers, remove_tickers
from rawcandle.fundamentals.admin.full_v2_downstream import run_full_v2_downstream
from rawcandle.fundamentals.admin.publication_journal import PUBLICATION_ROLES, sha256_file
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.phase13b_foundation import CANONICAL_SCHEMA_SQL as UNIVERSE_SCHEMA_SQL
from tests.test_fundamentals_admin_refresh_full_workflow_production_parity import (
    WorkflowFixture,
    _fixture as build_refresh_fixture,
    _semantic_fingerprint,
)


@dataclass
class RemoveWorkflowFixture:
    base: WorkflowFixture
    fixture_db_sizes: dict[str, int]
    source_bundle_sizes: list[int]
    stage_results: dict[str, dict[str, Any]]
    production_calls: list[str]

    @property
    def paths(self):
        return self.base.paths

    @property
    def run_root(self) -> Path:
        return self.base.run_root

    @property
    def temp_root(self) -> Path:
        return self.base.temp_root

    @property
    def journal_path(self) -> Path:
        return self.base.journal_path


def _add_operational_universe_and_shared_security(fixture: WorkflowFixture) -> None:
    now = "2026-09-23T00:00:00Z"
    with sqlite3.connect(fixture.paths.canonical_db) as connection:
        connection.executescript(UNIVERSE_SCHEMA_SQL)
        connection.execute(
            "INSERT INTO security VALUES(21,2,'BBB.B','NASDAQ',1,NULL,NULL,?,?)",
            (now, now),
        )
        connection.execute(
            "INSERT INTO ticker_alias(alias_id,security_id,ticker,provider,valid_from,valid_to,source) "
            "VALUES(3,21,'BBB.B','SHARADAR',NULL,NULL,'fixture')"
        )
        connection.execute(
            "INSERT INTO provider_security_identity VALUES('SHARADAR','201',21,'BBB.B','fixture',?)",
            (now,),
        )
        connection.execute(
            "INSERT INTO fundamentals_operational_universe_version VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "remove-fixture-v1", "PHASE13B_OPERATIONAL_UNIVERSE_CONTRACT_V1",
                "CURRENT_OPERATIONAL_UNIVERSE", "2026-09-23", "source-fixture",
                "economic-fixture", "physical-fixture", "COMPLETE", 2, 2, 3, 0, 1,
                now, now,
            ),
        )
        connection.execute(
            "INSERT INTO fundamentals_operational_universe_active_version VALUES(1,'remove-fixture-v1',?)",
            (now,),
        )
        rows = (
            (
                "remove-fixture-v1", 1, 10, "AAA", "usa", "ACTIVE_SINGLE_SECURITY",
                "EXACT_ONE_ACTIVE_SECURITY", 1, 1, "2020-01-01", None, "FIXTURE",
                "fixture", now, now,
            ),
            (
                "remove-fixture-v1", 2, None, "BBB,BBB.B", "usa", "ACTIVE_MULTI_SECURITY",
                "MULTIPLE_ACTIVE_SECURITIES_REQUIRES_SECURITY_SELECTION", 2, 2,
                "2020-01-01", None, "FIXTURE", "fixture", now, now,
            ),
        )
        connection.executemany(
            "INSERT INTO fundamentals_operational_universe_member VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )

    with sqlite3.connect(fixture.paths.market_db) as connection:
        connection.execute(
            "INSERT INTO ticker_meta VALUES('BBB.B','usa','Industrials','Machinery')"
        )
        next_id = int(connection.execute("SELECT COALESCE(MAX(id),0)+1 FROM osakedata").fetchone()[0])
        start = date(2025, 1, 1)
        rows = []
        for ticker_offset, ticker in enumerate(("BBB", "BBB.B")):
            for index in range(630):
                current = start + timedelta(days=index)
                value = 30 + ticker_offset * 5 + index / 100
                rows.append(
                    (
                        next_id + ticker_offset * 630 + index, ticker, "usa",
                        current.isoformat(), value, value + 1, value - 1, value + 0.5,
                    )
                )
        connection.executemany("INSERT INTO osakedata VALUES(?,?,?,?,?,?,?,?)", rows)

    with sqlite3.connect(fixture.paths.taxonomy_db) as connection:
        connection.execute(
            "INSERT INTO ec_entity VALUES(140,1,'TICKER','BBB.B','BBB.B','BBB.B','ACTIVE',3)"
        )
        connection.execute(
            "INSERT INTO ec_membership VALUES(1003,1,10,110,140,'CONTAINS','ADJACENT',1,1,'ACTIVE','fixture')"
        )


def _build_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RemoveWorkflowFixture:
    fixture = build_refresh_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(remove_tickers, "_events", lambda: ())
    _add_operational_universe_and_shared_security(fixture)
    initial = run_full_v2_downstream(
        fixture.paths.as_dict(),
        output=tmp_path / "remove-initial-analysis-build",
        as_of_date="2026-09-23",
    )
    Path(initial["candidate_analysis_db"]).replace(fixture.paths.analysis_db)
    fixture.initial_hashes = {
        role: sha256_file(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
    }
    fixture.initial_semantic_hashes = {
        role: _semantic_fingerprint(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
    }
    original_backup = batch_add_tickers.online_backup

    def observed_backup(source: Path, destination: Path) -> None:
        fixture.copied_sources.append(Path(source).resolve())
        original_backup(source, destination)

    monkeypatch.setattr(batch_add_tickers, "online_backup", observed_backup)
    return RemoveWorkflowFixture(
        base=fixture,
        fixture_db_sizes={role: path.stat().st_size for role, path in fixture.paths.as_dict().items()},
        source_bundle_sizes=[],
        stage_results={},
        production_calls=[],
    )


def _source_context(fixture: RemoveWorkflowFixture):
    @contextmanager
    def observed(*args: Any, **kwargs: Any) -> Iterator[dict[str, Any]]:
        with remove_tickers._shared_sources(*args, **kwargs) as evidence:
            size = int((evidence.get("market") or {}).get("compact_bundle_bytes") or 0)
            if size:
                fixture.source_bundle_sizes.append(size)
            yield evidence

    return observed


def _service(
    fixture: RemoveWorkflowFixture,
    *,
    before_test: Callable[[], None] | None = None,
    before_production: Callable[[], None] | None = None,
    inject_failure_at: str | None = None,
    inject_crash_at: str | None = None,
    downstream_runner: Callable[..., dict[str, Any]] = run_full_v2_downstream,
) -> FundamentalsAdminUIService:
    source_context = _source_context(fixture)

    def preview_backend(raw_inputs: str, **kwargs: Any) -> dict[str, Any]:
        result = remove_tickers.run_preview(
            raw_inputs,
            source_paths=fixture.paths,
            run_root=Path(kwargs["run_root"]),
            temp_root=fixture.temp_root,
            journal_path=fixture.journal_path,
            source_context=source_context,
            progress_callback=kwargs.get("progress_callback"),
        )
        fixture.stage_results["preview"] = result
        return result

    def test_backend(**kwargs: Any) -> dict[str, Any]:
        if before_test:
            before_test()
        result = remove_tickers.run_test(
            preview_payload_path=Path(kwargs["preview_payload_path"]),
            preview_fingerprint=str(kwargs["preview_fingerprint"]),
            source_paths=fixture.paths,
            run_root=Path(kwargs["run_root"]),
            temp_root=fixture.temp_root,
            journal_path=fixture.journal_path,
            lock_path=fixture.base.root / "remove-test.lock",
            source_context=source_context,
            downstream_runner=downstream_runner,
            as_of_date="2026-09-23",
            progress_callback=kwargs.get("progress_callback"),
        )
        fixture.stage_results["test"] = result
        return result

    def production_backend(**kwargs: Any) -> dict[str, Any]:
        fixture.production_calls.append("CALLED")
        if before_production:
            before_production()
        result = remove_tickers.run_production_apply(
            preview_payload_path=Path(kwargs["preview_payload_path"]),
            preview_fingerprint=str(kwargs["preview_fingerprint"]),
            test_run_id=str(kwargs["test_run_id"]),
            source_paths=fixture.paths,
            run_root=Path(kwargs["run_root"]),
            temp_root=fixture.temp_root,
            backup_root=fixture.base.backup_root,
            journal_path=fixture.journal_path,
            lock_path=fixture.base.root / "production.lock",
            scheduler_log_dir=str(fixture.base.root / "scheduler"),
            confirm_production=bool(kwargs["confirm_production"]),
            production_intent=False,
            rehearsal=True,
            source_context=source_context,
            downstream_runner=downstream_runner,
            progress_callback=kwargs.get("progress_callback"),
            inject_failure_at=inject_failure_at,
            inject_crash_at=inject_crash_at,
        )
        fixture.stage_results["production"] = result
        return result

    return FundamentalsAdminUIService(
        run_root=fixture.run_root,
        remove_preview=preview_backend,
        remove_apply=test_backend,
        remove_production_apply=production_backend,
        operation_lock_path=fixture.base.root / "ui.lock",
        recover_publication_on_startup=False,
    )


def _workflow_payload(result: Any) -> dict[str, Any]:
    return json.loads(Path(result.artifact_dir, "workflow_result.json").read_text(encoding="utf-8"))


def _terminal_cleanup(fixture: RemoveWorkflowFixture) -> None:
    if fixture.temp_root.exists():
        assert not list(fixture.temp_root.rglob("*.db"))
        assert not list(fixture.temp_root.rglob("*.sqlite"))
        assert not list(fixture.temp_root.rglob("*.sqlite3"))
    assert not taxonomy_locking.authoritative_taxonomy_lock_path().exists()


def _identity_rows(path: Path) -> dict[str, list[tuple[Any, ...]]]:
    with sqlite3.connect(path) as connection:
        return {
            table: connection.execute(f"SELECT * FROM {table} ORDER BY 1,2").fetchall()
            for table in ("company", "security", "ticker_alias", "provider_security_identity")
        }


@pytest.mark.parametrize(
    ("ticker", "expected_company_in_universe", "expected_ttm_security"),
    (("AAA", False, None), ("BBB", True, 21)),
)
def test_remove_tickers_real_full_workflow_success_and_source_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ticker: str,
    expected_company_in_universe: bool,
    expected_ttm_security: int | None,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    identity_before = _identity_rows(fixture.paths.canonical_db)
    taxonomy_before = sha256_file(fixture.paths.taxonomy_db)
    contention: list[str] = []
    original_postflight = remove_tickers._production_postflight

    def protected_downstream(*args: Any, **kwargs: Any) -> dict[str, Any]:
        with pytest.raises(RuntimeError, match="taxonomy operation lock is active"):
            with taxonomy_operation_lock_context(
                deployment_id="fixture-writer", operation_type="ACTIVATE",
                operation_id=f"remove-downstream-{len(contention)}",
            ):
                raise AssertionError("taxonomy writer entered protected downstream")
        contention.append("DOWNSTREAM")
        return run_full_v2_downstream(*args, **kwargs)

    def protected_postflight(**kwargs: Any) -> dict[str, Any]:
        with pytest.raises(RuntimeError, match="taxonomy operation lock is active"):
            with taxonomy_operation_lock_context(
                deployment_id="fixture-writer", operation_type="ACTIVATE",
                operation_id="remove-postflight",
            ):
                raise AssertionError("taxonomy writer entered protected postflight")
        contention.append("POSTFLIGHT")
        return original_postflight(**kwargs)

    monkeypatch.setattr(remove_tickers, "_production_postflight", protected_postflight)
    started = time.monotonic()
    result = _service(fixture, downstream_runner=protected_downstream).full_workflow(
        operation_type="REMOVE_TICKERS", raw_inputs=ticker,
    )
    runtime = time.monotonic() - started

    assert result.outcome == "COMPLETED", result.message
    workflow = _workflow_payload(result)
    assert [item["stage"] for item in workflow["stages"]] == [
        "Preview", "Test on copies", "Production update",
    ]
    preview = fixture.stage_results["preview"]
    tested = fixture.stage_results["test"]
    production = fixture.stage_results["production"]
    bindings = (
        preview["read_only_source_binding"], tested["market_taxonomy_binding"],
        production["candidate"]["source_binding"],
    )
    assert all(binding["market"]["mode"] == "STABLE_SOURCE_BUNDLE" for binding in bindings)
    assert all(binding["taxonomy"]["mode"] == "DIRECT_LOCKED_READ" for binding in bindings)
    assert preview["full_source_copies_created"] == 0
    assert tested["full_market_copy_created"] is False
    assert tested["full_taxonomy_copy_created"] is False
    assert production["full_market_copy_created"] is False
    assert production["full_taxonomy_copy_created"] is False
    assert production["test_to_production_binding"]["status"] == "MATCH"
    assert production["publication_boundary_revalidation"] == "PASSED"
    assert set(production["journal"]["roles"]) == set(PUBLICATION_ROLES)
    assert production["postflight"]["passed"] is True
    assert all(production["candidate"]["identity_invariants"].values())
    assert production["postflight"]["reviewed_identity_registry_preserved"] is True
    assert all(
        item["removed_current_participation"]
        for item in production["postflight"]["removed_current_state"]
    )
    assert production["cleanup"]["remaining_phase_owned_files"] == 0
    assert contention == ["DOWNSTREAM", "DOWNSTREAM", "POSTFLIGHT"]
    assert sha256_file(fixture.paths.taxonomy_db) == taxonomy_before
    assert fixture.paths.market_db.resolve() not in fixture.base.copied_sources
    assert fixture.paths.taxonomy_db.resolve() not in fixture.base.copied_sources
    assert fixture.source_bundle_sizes
    assert max(fixture.source_bundle_sizes) < fixture.fixture_db_sizes["market"]
    assert all(item["report"] for item in workflow["stages"])
    assert runtime < 45

    with sqlite3.connect(fixture.paths.canonical_db) as connection:
        company_id, security_id = connection.execute(
            "SELECT company_id,security_id FROM security WHERE current_ticker=?", (ticker,),
        ).fetchone()
        assert connection.execute(
            "SELECT active FROM security WHERE security_id=?", (security_id,),
        ).fetchone() == (0,)
        if expected_ttm_security is not None:
            assert connection.execute(
                "SELECT active FROM security WHERE security_id=?", (expected_ttm_security,),
            ).fetchone() == (1,)
        active_version = connection.execute(
            "SELECT universe_version_id FROM fundamentals_operational_universe_active_version WHERE singleton=1"
        ).fetchone()[0]
        company_present = connection.execute(
            "SELECT COUNT(*) FROM fundamentals_operational_universe_member "
            "WHERE universe_version_id=? AND company_id=?",
            (active_version, company_id),
        ).fetchone()[0] == 1
        assert company_present is expected_company_in_universe
        ttm_ids = [row[0] for row in connection.execute(
            "SELECT DISTINCT security_id FROM v4_ttm_values WHERE company_id=?", (company_id,),
        )]
        assert ttm_ids == ([] if expected_ttm_security is None else [expected_ttm_security])
    identity_after = _identity_rows(fixture.paths.canonical_db)
    assert identity_after["company"] == identity_before["company"]
    assert len(identity_after["security"]) == len(identity_before["security"])
    assert identity_after["ticker_alias"] == identity_before["ticker_alias"]
    assert identity_after["provider_security_identity"] == identity_before["provider_security_identity"]
    _terminal_cleanup(fixture)


def test_remove_tickers_full_workflow_stale_preview_blocks_before_production(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)

    def drift_provider() -> None:
        with sqlite3.connect(fixture.paths.provider_db) as connection:
            connection.execute(
                "INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,payload_json,fetched_at_utc) "
                "VALUES('fundamentals','AAA','999','{}','2026-09-23T00:00:00Z')"
            )

    result = _service(fixture, before_test=drift_provider).full_workflow(
        operation_type="REMOVE_TICKERS", raw_inputs="AAA",
    )

    assert result.outcome == "STOPPED"
    assert fixture.stage_results["test"]["outcome"] == "STALE_PREVIEW"
    assert fixture.production_calls == []
    assert not fixture.journal_path.exists()
    _terminal_cleanup(fixture)


@pytest.mark.parametrize("drift", ("canonical", "market", "taxonomy"))
def test_remove_tickers_full_workflow_stale_test_or_source_blocks_publication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)

    def mutate() -> None:
        if drift == "canonical":
            with sqlite3.connect(fixture.paths.canonical_db) as connection:
                connection.execute(
                    "UPDATE fundamentals_operational_universe_member SET reason='drift' WHERE company_id=1"
                )
        elif drift == "market":
            with sqlite3.connect(fixture.paths.market_db) as connection:
                connection.execute(
                    "UPDATE osakedata SET close=close+7 WHERE id=(SELECT MAX(id) FROM osakedata WHERE osake='AAA')"
                )
        else:
            with sqlite3.connect(fixture.paths.taxonomy_db) as connection:
                connection.execute(
                    "UPDATE ec_taxonomy_version SET taxonomy_version_code='DC_FIXTURE_V2',source_hash='changed' "
                    "WHERE is_active=1"
                )
    old_generation = {
        role: _semantic_fingerprint(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
    }
    result = _service(fixture, before_production=mutate).full_workflow(
        operation_type="REMOVE_TICKERS", raw_inputs="AAA",
    )
    production = fixture.stage_results["production"]

    assert result.outcome == "STOPPED"
    assert production["outcome"] == "STALE_PREVIEW_OR_TEST"
    assert "backups" not in production
    assert not fixture.journal_path.exists()
    if drift != "canonical":
        assert {
            role: _semantic_fingerprint(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
        } == old_generation
    _terminal_cleanup(fixture)


def test_remove_tickers_full_workflow_preboundary_failure_cleans_everything(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    old_generation = dict(fixture.base.initial_semantic_hashes)
    result = _service(fixture, inject_failure_at="BEFORE_FIRST_REPLACEMENT").full_workflow(
        operation_type="REMOVE_TICKERS", raw_inputs="AAA",
    )
    production = fixture.stage_results["production"]

    assert result.outcome == "STOPPED"
    assert production["outcome"] == "FAILED"
    assert production["pre_publication_cleanup"] == {
        "journal_removed": True, "backup_directory_removed": True,
    }
    assert {
        role: _semantic_fingerprint(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
    } == old_generation
    assert production["cleanup"]["remaining_phase_owned_files"] == 0
    _terminal_cleanup(fixture)


def test_remove_tickers_full_workflow_publication_failure_rolls_back_complete_old_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    old_generation = dict(fixture.base.initial_semantic_hashes)
    result = _service(fixture, inject_failure_at="AFTER_CANONICAL_REPLACEMENT").full_workflow(
        operation_type="REMOVE_TICKERS", raw_inputs="AAA",
    )
    production = fixture.stage_results["production"]

    assert result.outcome == "STOPPED"
    assert production["outcome"] == "FAILED_ROLLED_BACK"
    assert production["journal"]["state"] == "ROLLED_BACK"
    assert set(production["rollback"]["roles"]) == set(PUBLICATION_ROLES)
    assert set(production["journal"]["roles"]) == set(PUBLICATION_ROLES)
    assert "market" not in production["journal"]["roles"]
    assert "taxonomy" not in production["journal"]["roles"]
    assert {
        role: _semantic_fingerprint(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
    } == old_generation
    _terminal_cleanup(fixture)


def test_remove_tickers_full_workflow_partial_crash_recovers_through_real_entrypoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _build_fixture(tmp_path, monkeypatch)
    old_generation = dict(fixture.base.initial_semantic_hashes)
    service = _service(fixture, inject_crash_at="AFTER_PROVIDER_REPLACEMENT")

    with pytest.raises(remove_tickers.SimulatedRemoveTickersPublicationCrash):
        service.full_workflow(operation_type="REMOVE_TICKERS", raw_inputs="AAA")
    assert json.loads(fixture.journal_path.read_text(encoding="utf-8"))["state"] == "PUBLISHING"
    preview = fixture.stage_results["preview"]
    tested = fixture.stage_results["test"]
    recovered = _service(fixture).production_apply(
        "REMOVE_TICKERS",
        preview_payload_path=preview["preview_payload_path"],
        preview_fingerprint=preview["preview_fingerprint"],
        confirmation="CONFIRM_PRODUCTION_REMOVE_TICKERS",
        test_run_id=tested["run_id"],
    )

    assert recovered.outcome == "RETRY_REQUIRED"
    terminal = json.loads(fixture.journal_path.read_text(encoding="utf-8"))
    assert terminal["state"] == "RECOVERED"
    assert {
        role: _semantic_fingerprint(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
    } == old_generation
    assert set(terminal["roles"]) == set(PUBLICATION_ROLES)
    _terminal_cleanup(fixture)
