from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping

import pytest

from rawcandle.fundamentals.admin import refresh_copy_runtime, refresh_production
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.full_v2_downstream import run_full_v2_downstream
from rawcandle.fundamentals.admin.publication_journal import (
    PUBLICATION_ROLES,
    PublicationRecoveredRetryRequired,
    guard_production_writes,
    sha256_file,
)
from rawcandle.fundamentals.admin.refresh_copy_runtime import (
    fresh_rebuild_canonical,
    replace_provider_histories,
)
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    FINANCIAL_FIELDS,
    REFRESH_REQUEST_FIELDS,
    run_preview,
    validate_complete_history,
)
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.providers.sharadar import AUTH_OK, STATUS_SUCCESS, SharadarResult
from rawcandle.fundamentals.schema.migrations import (
    CANONICAL_SCHEMA_SQL,
    PROVIDER_SCHEMA_SQL,
    bootstrap_database,
)


AS_OF = "2026-09-22"
NOW = "2026-09-22T12:00:00Z"


def _source_row(
    ticker: str, dimension: str, fiscal_year: int, quarter: int, *,
    lastupdated: str = "2026-08-15", revenue_delta: float = 0,
) -> dict[str, object]:
    month_day = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}[quarter]
    reportperiod = f"{fiscal_year}-{month_day}"
    filing = (date.fromisoformat(reportperiod) + timedelta(days=35)).isoformat()
    base = float((fiscal_year - 2020) * 100 + quarter * 10 + (1 if ticker == "AAA" else 20))
    row: dict[str, object] = {
        "ticker": ticker,
        "dimension": dimension,
        "date": filing,
        "reportperiod": reportperiod,
        "calendardate": reportperiod,
        "fiscalperiod": f"{fiscal_year}-Q{quarter}",
        "lastupdated": lastupdated,
    }
    row.update({field: None for field in FINANCIAL_FIELDS})
    row.update({
        "revenue": base + revenue_delta,
        "gp": base * 0.5,
        "opinc": base * 0.2,
        "ebit": base * 0.21,
        "ebitda": base * 0.25,
        "netinc": base * 0.14,
        "netinccmn": base * 0.13,
        "ncfo": base * 0.22,
        "capex": -base * 0.05,
        "fcf": base * 0.17,
        "cashneq": base * 0.4,
        "debt": base * 0.2,
        "debtc": base * 0.04,
        "debtnc": base * 0.16,
        "sharesbas": 100,
        "shareswa": 100,
        "shareswadil": 102,
        "receivables": base * 0.1,
        "inventory": base * 0.08,
        "payables": base * 0.07,
        "deferredrev": base * 0.03,
        "assets": base * 2,
    })
    return row


def _histories(*, revised: bool) -> dict[str, dict[str, list[dict[str, object]]]]:
    output: dict[str, dict[str, list[dict[str, object]]]] = {}
    for ticker in ("AAA", "BBB"):
        output[ticker] = {}
        for dimension in ("ARQ", "MRQ"):
            rows = [
                _source_row(ticker, dimension, 2025, quarter)
                for quarter in range(1, 5)
            ]
            if revised and ticker == "AAA":
                rows[-1] = _source_row(
                    ticker,
                    dimension,
                    2025,
                    4,
                    lastupdated="2026-09-20",
                    revenue_delta=7,
                )
            output[ticker][dimension] = rows
    return output


class FakeSharadarClient:
    def __init__(self, histories: Mapping[str, Mapping[str, list[dict[str, object]]]]) -> None:
        self.histories = histories
        self.request_count = 0

    @staticmethod
    def _result(records: list[dict[str, object]], *, payload: object | None = None) -> SharadarResult:
        return SharadarResult(
            status=STATUS_SUCCESS,
            auth_status=AUTH_OK,
            http_status=200,
            endpoint="fixture",
            url="fixture://sharadar",
            request_count=1,
            records=records,
            payload=records if payload is None else payload,
        )

    def schema(self, _table: str = "fundamentals") -> SharadarResult:
        self.request_count += 1
        return self._result([], payload={"fields": list(REFRESH_REQUEST_FIELDS)})

    def fundamentals(
        self,
        *,
        ticker: str | None = None,
        dimension: str | None = None,
        fields: object | None = None,
        filters: Mapping[str, str] | None = None,
        **_kwargs: object,
    ) -> SharadarResult:
        self.request_count += 1
        wanted_dimension = str(dimension or "").upper()
        if ticker:
            records = [dict(row) for row in self.histories[ticker.upper()][wanted_dimension]]
        else:
            threshold = str((filters or {}).get("lastupdated.gte") or (filters or {}).get("lastupdated") or "")
            records = [
                {
                    "ticker": name,
                    "dimension": wanted_dimension,
                    "lastupdated": str(row["lastupdated"]),
                }
                for name, dimensions in self.histories.items()
                for row in dimensions[wanted_dimension]
                if (not threshold or str(row["lastupdated"]) >= threshold)
            ]
        if fields:
            selected = set(fields)
            records = [{key: value for key, value in row.items() if key in selected} for row in records]
        return self._result(records)


def _insert_identities(canonical: Path) -> None:
    with sqlite3.connect(canonical) as connection:
        for company_id, ticker in ((1, "AAA"), (2, "BBB")):
            security_id = company_id * 10
            provider_id = str(company_id * 100)
            connection.execute(
                "INSERT INTO company VALUES(?,?,?,?,?,?)",
                (company_id, ticker, f"{ticker} Corp", "ACTIVE", NOW, NOW),
            )
            connection.execute(
                "INSERT INTO security VALUES(?,?,?,?,1,NULL,NULL,?,?)",
                (security_id, company_id, ticker, "NASDAQ", NOW, NOW),
            )
            connection.execute(
                "INSERT INTO ticker_alias VALUES(?,?,?,'SHARADAR',NULL,NULL,'fixture')",
                (company_id, security_id, ticker),
            )
            connection.execute(
                "INSERT INTO provider_security_identity VALUES('SHARADAR',?,?,?,'fixture',?)",
                (provider_id, security_id, ticker, NOW),
            )
            connection.execute(
                "INSERT INTO provider_company_identity VALUES('SHARADAR','PERMATICKER',?,?,?,'fixture','fixture',?,?)",
                (provider_id, company_id, ticker, provider_id, NOW),
            )


def _create_market(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE ticker_meta(ticker TEXT,market TEXT,sector TEXT,industry TEXT);
            CREATE TABLE osakedata(
                id INTEGER PRIMARY KEY,osake TEXT NOT NULL,pvm TEXT NOT NULL,
                open REAL,high REAL,low REAL,close REAL
            );
            CREATE INDEX idx_osake_pvm ON osakedata(osake,pvm DESC);
            CREATE TABLE splits_data(
                osake TEXT,split_date TEXT,split_ratio REAL,is_price_data_corrected INTEGER
            );
            INSERT INTO ticker_meta VALUES('AAA','usa','Technology','Semiconductors');
            INSERT INTO ticker_meta VALUES('BBB','usa','Industrials','Machinery');
            INSERT INTO splits_data VALUES('AAA','2025-07-01',2,1);
            """
        )
        start = date(2025, 1, 1)
        rows = []
        for index in range(630):
            current = start + timedelta(days=index)
            value = 20 + index / 100
            rows.append((index + 1, "AAA", current.isoformat(), value, value + 1, value - 1, value + 0.5))
        connection.executemany("INSERT INTO osakedata VALUES(?,?,?,?,?,?,?)", rows)


def _create_taxonomy(path: Path, *, version: str = "DC_FIXTURE_V1") -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            f"""
            CREATE TABLE ec_ecosystem(
                ecosystem_id INTEGER PRIMARY KEY,ecosystem_code TEXT,ecosystem_name TEXT,status TEXT
            );
            CREATE TABLE ec_taxonomy_version(
                taxonomy_version_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,
                taxonomy_version_code TEXT,taxonomy_name TEXT,source_reference TEXT,
                source_hash TEXT,status TEXT,is_active INTEGER,active_from TEXT,active_to TEXT
            );
            CREATE TABLE ec_entity(
                entity_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,entity_type TEXT,
                entity_code TEXT,entity_name TEXT,ticker TEXT,status TEXT,entity_level INTEGER
            );
            CREATE TABLE ec_membership(
                membership_id INTEGER PRIMARY KEY,ecosystem_id INTEGER,taxonomy_version_id INTEGER,
                parent_entity_id INTEGER,child_entity_id INTEGER,membership_type TEXT,
                membership_role TEXT,is_primary INTEGER,role_weight REAL,status TEXT,source_note TEXT
            );
            INSERT INTO ec_ecosystem VALUES(1,'DATACENTER','Data Center','ACTIVE');
            INSERT INTO ec_taxonomy_version VALUES(
                10,1,'{version}','Fixture','fixture','{version}-hash','ACTIVE',1,'2026-01-01',NULL
            );
            INSERT INTO ec_entity VALUES(100,1,'GROUP_L1','COMPUTE','Compute',NULL,'ACTIVE',1);
            INSERT INTO ec_entity VALUES(110,1,'GROUP_L2','CHIPS','Chips',NULL,'ACTIVE',2);
            INSERT INTO ec_entity VALUES(120,1,'TICKER','AAA','AAA','AAA','ACTIVE',3);
            INSERT INTO ec_entity VALUES(130,1,'TICKER','BBB','BBB','BBB','ACTIVE',3);
            INSERT INTO ec_membership VALUES(1000,1,10,100,110,'CONTAINS',NULL,1,1,'ACTIVE',NULL);
            INSERT INTO ec_membership VALUES(1001,1,10,110,120,'CONTAINS','CORE',1,1,'ACTIVE','fixture');
            INSERT INTO ec_membership VALUES(1002,1,10,110,130,'CONTAINS','ADJACENT',1,1,'ACTIVE','fixture');
            """
        )


@dataclass
class WorkflowFixture:
    root: Path
    paths: BatchAddTickerPaths
    run_root: Path
    temp_root: Path
    backup_root: Path
    journal_path: Path
    client: FakeSharadarClient
    initial_hashes: dict[str, str]
    initial_semantic_hashes: dict[str, str]
    copied_sources: list[Path]


def _semantic_fingerprint(path: Path) -> str:
    with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
        dump = "\n".join(connection.iterdump()).encode("utf-8")
    return hashlib.sha256(dump).hexdigest()


def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> WorkflowFixture:
    db_root = tmp_path / "databases"
    db_root.mkdir()
    paths = BatchAddTickerPaths(*(db_root / f"{role}.db" for role in ("provider", "canonical", "analysis", "market", "taxonomy")))
    bootstrap_database(paths.provider_db, "fundamentals_provider", PROVIDER_SCHEMA_SQL, NOW)
    bootstrap_database(paths.canonical_db, "fundamentals_v4", CANONICAL_SCHEMA_SQL, NOW)
    _insert_identities(paths.canonical_db)
    baseline = _histories(revised=False)
    trusted = {
        ticker: {
            dimension: validate_complete_history(rows, ticker=ticker, dimension=dimension)
            for dimension, rows in dimensions.items()
        }
        for ticker, dimensions in baseline.items()
    }
    identities = {
        "AAA": {"company_id": 1, "security_id": 10, "provider_security_id": "100"},
        "BBB": {"company_id": 2, "security_id": 20, "provider_security_id": "200"},
    }
    replace_provider_histories(paths.provider_db, trusted, identities, applied_at=NOW)
    with sqlite3.connect(paths.provider_db) as connection:
        for ticker, provider_id in (("AAA", "100"), ("BBB", "200")):
            connection.execute(
                "INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,payload_json,fetched_at_utc) "
                "VALUES('fundamentals',?,?, '{}',?)",
                (ticker, provider_id, NOW),
            )
    monkeypatch.setattr(refresh_copy_runtime, "_events", lambda: ())
    fresh_rebuild_canonical(
        paths.provider_db,
        paths.canonical_db,
        applied_at=NOW,
        affected_company_ids=(1, 2),
    )
    _create_market(paths.market_db)
    _create_taxonomy(paths.taxonomy_db)
    initial = run_full_v2_downstream(
        paths.as_dict(),
        output=tmp_path / "initial-analysis-build",
        as_of_date=AS_OF,
    )
    shutil.copy2(Path(initial["candidate_analysis_db"]), paths.analysis_db)
    client = FakeSharadarClient(_histories(revised=True))
    copied_sources: list[Path] = []
    copy_runtime_backup = refresh_copy_runtime.online_backup
    production_backup = refresh_production.online_backup

    def record_copy_runtime(source: Path, destination: Path):
        copied_sources.append(source)
        return copy_runtime_backup(source, destination)

    def record_production(source: Path, destination: Path):
        copied_sources.append(source)
        return production_backup(source, destination)

    monkeypatch.setattr(refresh_copy_runtime, "online_backup", record_copy_runtime)
    monkeypatch.setattr(refresh_production, "online_backup", record_production)
    return WorkflowFixture(
        root=tmp_path,
        paths=paths,
        run_root=tmp_path / "runs",
        temp_root=tmp_path / "temp",
        backup_root=tmp_path / "backups",
        journal_path=tmp_path / "publication-journal.json",
        client=client,
        initial_hashes={role: sha256_file(paths.as_dict()[role]) for role in PUBLICATION_ROLES},
        initial_semantic_hashes={
            role: _semantic_fingerprint(paths.as_dict()[role]) for role in PUBLICATION_ROLES
        },
        copied_sources=copied_sources,
    )


def _service(
    fixture: WorkflowFixture,
    *,
    before_production: Any | None = None,
    inject_failure_at: str | None = None,
    inject_crash_at: str | None = None,
) -> FundamentalsAdminUIService:
    def preview_backend(**kwargs: object) -> dict[str, Any]:
        return run_preview(
            source_paths=fixture.paths,
            run_root=Path(kwargs["run_root"]),
            client=fixture.client,
            progress_callback=kwargs.get("progress_callback"),
        )

    def test_backend(**kwargs: object) -> dict[str, Any]:
        return refresh_copy_runtime.run_apply(
            preview_payload_path=Path(kwargs["preview_payload_path"]),
            preview_fingerprint=str(kwargs["preview_fingerprint"]),
            source_paths=fixture.paths,
            run_root=Path(kwargs["run_root"]),
            temp_root=fixture.temp_root,
            client=fixture.client,
            confirm_apply=bool(kwargs["confirm_apply"]),
            progress_callback=kwargs.get("progress_callback"),
            as_of_date=AS_OF,
        )

    def production_backend(**kwargs: object) -> dict[str, Any]:
        if before_production:
            before_production()
        return refresh_production.run_production_apply(
            preview_payload_path=Path(kwargs["preview_payload_path"]),
            preview_fingerprint=str(kwargs["preview_fingerprint"]),
            test_run_id=str(kwargs["test_run_id"]),
            source_paths=fixture.paths,
            run_root=Path(kwargs["run_root"]),
            temp_root=fixture.temp_root,
            backup_root=fixture.backup_root,
            journal_path=fixture.journal_path,
            client=fixture.client,
            confirm_production=bool(kwargs["confirm_production"]),
            production_intent=False,
            rehearsal=True,
            lock_path=fixture.root / "production.lock",
            scheduler_log_dir=str(fixture.root / "scheduler"),
            progress_callback=kwargs.get("progress_callback"),
            as_of_date=AS_OF,
            inject_failure_at=inject_failure_at,
            inject_crash_at=inject_crash_at,
        )

    return FundamentalsAdminUIService(
        run_root=fixture.run_root,
        refresh_preview=preview_backend,
        refresh_apply=test_backend,
        refresh_production_apply=production_backend,
        operation_lock_path=fixture.root / "ui.lock",
        recover_publication_on_startup=False,
    )


def _stage_payload(workflow_result: Mapping[str, Any], stage: str) -> dict[str, Any]:
    run_id = next(item["run_id"] for item in workflow_result["stages"] if item["stage"] == stage)
    return json.loads((Path(workflow_result["artifact_dir"]).parent / run_id / "result.json").read_text(encoding="utf-8"))


def _assert_terminal_lane_cleanup(fixture: WorkflowFixture) -> None:
    if fixture.temp_root.exists():
        assert not list(fixture.temp_root.rglob("market_source_bundle"))
        assert not list(fixture.temp_root.rglob("taxonomy.db"))
        assert not list(fixture.temp_root.rglob("*_candidate.db"))


def _workflow_payload(result: Any) -> dict[str, Any]:
    return json.loads((Path(result.artifact_dir) / "workflow_result.json").read_text(encoding="utf-8"))


def test_refresh_full_workflow_real_production_parity_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    started = time.monotonic()
    result = _service(fixture).full_workflow(operation_type="REFRESH_FUNDAMENTALS", raw_inputs="")
    runtime = time.monotonic() - started

    assert result.outcome == "COMPLETED"
    workflow = _workflow_payload(result)
    test = _stage_payload(workflow, "Test on copies")
    production = _stage_payload(workflow, "Production update")
    tested = test["downstream"]["read_only_source_binding"]
    published = production["production_source_binding"]
    comparison = production["test_source_binding_comparison"]
    test_contract = comparison["test"]
    production_contract = comparison["production"]

    assert tested["market"]["mode"] == published["market"]["mode"] == "STABLE_SOURCE_BUNDLE"
    assert tested["taxonomy"]["mode"] == published["taxonomy"]["mode"] == "FULL_SQLITE_BACKUP"
    assert comparison["status"] == "MATCH"
    assert comparison["test"] == comparison["production"]
    assert comparison["differing_contract_sections"] == []
    assert test_contract["market"]["source_contract_version"] == "FUNDAMENTALS_READ_ONLY_SOURCE_V1"
    assert test_contract["market"]["as_of_date"] == production_contract["market"]["as_of_date"] == AS_OF
    assert (
        test_contract["market"]["canonical_binding"]["semantic_fingerprint"]
        == production_contract["market"]["canonical_binding"]["semantic_fingerprint"]
    )
    assert test_contract["market"]["semantic_fingerprint"] == production_contract["market"]["semantic_fingerprint"]
    assert test_contract["market"]["valuation_coverage"] == production_contract["market"]["valuation_coverage"]
    assert test_contract["taxonomy"]["version"] == production_contract["taxonomy"]["version"] == "DC_FIXTURE_V1"
    assert test_contract["taxonomy"]["semantic_fingerprint"] == production_contract["taxonomy"]["semantic_fingerprint"]
    assert tested["market"]["bundle_path"] != published["market"]["bundle_path"]
    assert Path(test["artifacts"]["read_only_source_binding"]).is_file()
    assert production["test_source_binding_reference"]["test_run_id"] == test["run_id"]
    assert production["test_source_binding_reference"]["evidence_path"] == test["artifacts"]["read_only_source_binding"]
    assert production["test_source_binding_reference"]["semantic_contract"] == comparison["test"]
    assert production["journal"]["state"] == "COMPLETED"
    assert set(production["journal"]["roles"]) == set(PUBLICATION_ROLES)
    assert set(production["backups"]) == set(PUBLICATION_ROLES)
    assert production["postflight"]["cross_role_lineage"]["analysis_matches_validated_candidate"] is True
    assert production["journal"]["postflight_state"] == "PASSED"
    assert production["cleanup"]["remaining_phase_owned_files"] == 0
    assert production["production_source_binding"]["market"]["compact_bundle_bytes"] > 0
    assert production["production_source_binding"]["market"]["old_full_copy_bytes_avoided"] == fixture.paths.market_db.stat().st_size
    assert not any(item.get("source") == str(fixture.paths.market_db) for item in production.get("backups", {}).values())
    assert fixture.client.request_count > 0
    assert fixture.paths.market_db not in fixture.copied_sources
    assert runtime < 30
    _assert_terminal_lane_cleanup(fixture)


@pytest.mark.parametrize("drift", ["market", "taxonomy"])
def test_refresh_full_workflow_stales_test_on_relevant_source_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, drift: str,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)

    def mutate_source() -> None:
        if drift == "market":
            with sqlite3.connect(fixture.paths.market_db) as connection:
                connection.execute(
                    "UPDATE osakedata SET close=close+10 WHERE id=(SELECT MAX(id) FROM osakedata WHERE osake='AAA')"
                )
        else:
            with sqlite3.connect(fixture.paths.taxonomy_db) as connection:
                connection.execute(
                    "UPDATE ec_taxonomy_version SET taxonomy_version_code='DC_FIXTURE_V2',source_hash='changed' "
                    "WHERE is_active=1"
                )

    result = _service(fixture, before_production=mutate_source).full_workflow(
        operation_type="REFRESH_FUNDAMENTALS", raw_inputs="",
    )
    workflow = _workflow_payload(result)
    production = _stage_payload(workflow, "Production update")

    assert result.outcome == "STOPPED"
    assert production["outcome"] == "FAILED"
    assert "REFRESH_TEST_SOURCE_BINDING_STALE" in production["error"]
    assert production["test_source_binding_comparison"]["status"] == "STALE"
    assert production["test_source_binding_comparison"]["differing_contract_sections"] == [drift]
    assert "analysis_candidate" not in production
    assert "backups" not in production
    assert not fixture.journal_path.exists()
    assert {
        role: sha256_file(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
    } == fixture.initial_hashes
    assert production["cleanup"]["remaining_phase_owned_files"] == 0
    _assert_terminal_lane_cleanup(fixture)


def test_refresh_full_workflow_publication_failure_rolls_back_only_three_db_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    result = _service(fixture, inject_failure_at="AFTER_PROVIDER_REPLACEMENT").full_workflow(
        operation_type="REFRESH_FUNDAMENTALS", raw_inputs="",
    )
    workflow = _workflow_payload(result)
    production = _stage_payload(workflow, "Production update")

    assert result.outcome == "STOPPED"
    assert production["outcome"] == "FAILED_ROLLED_BACK"
    assert production["journal"]["state"] == "ROLLED_BACK"
    assert production["publication_activity"]["live_replacements"] == ["provider"]
    assert production["publication_activity"]["rollback_restorations"] == list(PUBLICATION_ROLES)
    assert set(production["journal"]["roles"]) == set(PUBLICATION_ROLES)
    assert "market" not in production["journal"]["roles"]
    assert "taxonomy" not in production["journal"]["roles"]
    assert {
        role: _semantic_fingerprint(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
    } == fixture.initial_semantic_hashes
    assert all(
        sha256_file(fixture.paths.as_dict()[role])
        == production["journal"]["roles"][role]["verified_backup_fingerprint"]
        for role in PUBLICATION_ROLES
    )
    assert all(
        item["replacement_state"] == "OLD_GENERATION_RESTORED"
        and item["rollback_restoration_verified"] is True
        for item in production["journal"]["roles"].values()
    )
    assert production["cleanup"]["remaining_phase_owned_files"] == 0
    _assert_terminal_lane_cleanup(fixture)


def test_refresh_full_workflow_crash_recovery_restores_old_and_requires_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path, monkeypatch)
    with pytest.raises(refresh_production.SimulatedPublicationCrash):
        _service(fixture, inject_crash_at="AFTER_PROVIDER_REPLACEMENT").full_workflow(
            operation_type="REFRESH_FUNDAMENTALS", raw_inputs="",
        )

    active = json.loads(fixture.journal_path.read_text(encoding="utf-8"))
    assert active["state"] != "COMPLETED"
    assert set(active["roles"]) == set(PUBLICATION_ROLES)
    assert any(fixture.temp_root.rglob("market_source_bundle"))

    with pytest.raises(PublicationRecoveredRetryRequired) as recovered:
        guard_production_writes(fixture.journal_path)

    assert recovered.value.recovery["status"] == "RECOVERED"
    terminal = json.loads(fixture.journal_path.read_text(encoding="utf-8"))
    assert terminal["state"] == "RECOVERED"
    assert {
        role: _semantic_fingerprint(fixture.paths.as_dict()[role]) for role in PUBLICATION_ROLES
    } == fixture.initial_semantic_hashes
    assert all(
        sha256_file(fixture.paths.as_dict()[role])
        == terminal["roles"][role]["verified_backup_fingerprint"]
        for role in PUBLICATION_ROLES
    )
    assert terminal["candidate_cleanup"]["status"] == "COMPLETED"
    _assert_terminal_lane_cleanup(fixture)
