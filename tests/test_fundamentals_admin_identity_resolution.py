from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin import batch_add_tickers as batch
from rawcandle.fundamentals.admin.batch_add_tickers import _apply_identities, build_generic_batch_plan, parse_batch_tickers
from rawcandle.fundamentals.admin.identity_resolution import (
    AuthorityClass,
    ResolutionClass,
    resolve_ticker_identity,
    run_preview,
)
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from tests.test_fundamentals_admin_batch_add_tickers import _archive, _archive_row, _generic_paths


def _metadata(paths, ticker: str, permaticker: str, cik: str | None = "0000101") -> None:
    secfilings = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}" if cik else None
    with sqlite3.connect(paths.provider_db) as conn:
        conn.execute(
            "INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,name,exchange,isdelisted,category,relatedtickers,secfilings,firstpricedate,lastpricedate,firstquarter,lastquarter,lastupdated,payload_json,fetched_at_utc) "
            "VALUES('fundamentals',?,?,?,'NASDAQ','N','Domestic Common Stock','',?,'2026-09-01','2026-09-20','2026-06-30','2026-06-30','2026-09-20','{}','2026-09-20T00:00:00Z')",
            (ticker, permaticker, f"{ticker} Corp", secfilings),
        )
    with sqlite3.connect(paths.market_db) as conn:
        conn.execute("INSERT INTO ticker_meta VALUES(?,'usa','Technology','Software - Application')", (ticker,))
        conn.execute("INSERT INTO osakedata VALUES(?,'usa','2026-09-20',10.0)", (ticker,))


def _registry(path: Path, record: dict) -> Path:
    path.write_text(json.dumps({"schema_version": "1.0", "records": [record]}), encoding="utf-8")
    return path


def _review(ticker: str, status: str = "PROPOSED", **overrides) -> dict:
    record = {
        "subject_ticker": ticker,
        "effective_date": "2026-09-01",
        "resolution_class": "REORGANIZATION_SUCCESSOR",
        "company_continuity": "SUCCESSOR_COMPANY",
        "security_continuity": "NEW_SECURITY",
        "ticker_relationship": "PREDECESSOR_TO_SUCCESSOR",
        "provider_continuity": "PROVIDER_METADATA_ABSENT",
        "predecessor_ticker": "OLD",
        "canonical_company_id": None,
        "canonical_security_id": None,
        "cik": "0000000101",
        "provider_permaticker": None,
        "exchange": "NASDAQ",
        "security_category": "Domestic Common Stock",
        "review_status": status,
        "reason": "Fixture reviewed identity decision.",
        "evidence": [{"source_type": "SEC_8_K", "source_authority": "SEC", "reference": "fixture", "research_date": "2026-09-21", "fact": "Fixture fact."}],
    }
    record.update(overrides)
    return record


def test_exact_existing_security_is_deterministic(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    plan = build_generic_batch_plan(paths, parse_batch_tickers("NEWC"), archive_path=_archive(tmp_path / "source.zip"))
    _apply_identities(paths, [plan.safe_dict(include_rows=True)["items"][0]], applied_at="2026-09-20T00:00:00Z")

    resolution = resolve_ticker_identity(paths, "NEWC")

    assert resolution.resolution_class == ResolutionClass.EXISTING_SECURITY.value
    assert resolution.authority_class == AuthorityClass.LOCAL_DETERMINISTIC.value
    assert resolution.automatic_mutation_permitted is False


def test_same_permaticker_transition_preserves_company_security_and_alias_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    paths = _generic_paths(tmp_path / "source")
    first = build_generic_batch_plan(paths, parse_batch_tickers("NEWC"), archive_path=_archive(tmp_path / "source.zip"))
    _apply_identities(paths, [first.safe_dict(include_rows=True)["items"][0]], applied_at="2026-09-20T00:00:00Z")
    with sqlite3.connect(paths.canonical_db) as conn:
        before = conn.execute("SELECT company_id,security_id FROM security WHERE current_ticker='NEWC'").fetchone()
    _metadata(paths, "RENAMED", "1001")
    archive = _archive(tmp_path / "renamed.zip", ("RENAMED",))

    plan = build_generic_batch_plan(paths, parse_batch_tickers("RENAMED"), archive_path=archive)
    item = plan.safe_dict(include_rows=True)["items"][0]
    assert item["identity_resolution"]["resolution_class"] == "TICKER_TRANSITION_SAME_SECURITY"
    assert item["status"] == "ELIGIBLE"
    downstream_calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(
        batch,
        "_run_authoritative_downstream",
        lambda _paths, _output, *, accepted_tickers, **_kwargs: downstream_calls.append(tuple(accepted_tickers)) or {
            "invocation_counts": {"package": 1, "relative_position": 1, "relative_valuation": 1}
        },
    )
    applied = batch._apply_generic_plan(paths, plan.safe_dict(include_rows=True), output=tmp_path / "output")

    with sqlite3.connect(paths.canonical_db) as conn:
        after = conn.execute("SELECT company_id,security_id FROM security WHERE current_ticker='RENAMED'").fetchone()
        aliases = conn.execute("SELECT ticker,valid_to FROM ticker_alias WHERE security_id=? ORDER BY ticker", (after[1],)).fetchall()
        assert conn.execute("SELECT COUNT(*) FROM security WHERE company_id=?", (after[0],)).fetchone()[0] == 1
    assert after == before
    assert {row[0] for row in aliases} == {"NEWC", "RENAMED"}
    assert next(row[1] for row in aliases if row[0] == "NEWC") is not None
    assert applied["identities"]["rows"][0]["status"] == "TICKER_TRANSITION"
    assert downstream_calls == [("RENAMED",)]


def test_same_cik_different_permaticker_creates_security_not_company(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    first = build_generic_batch_plan(paths, parse_batch_tickers("NEWC"), archive_path=_archive(tmp_path / "source.zip"))
    _apply_identities(paths, [first.safe_dict(include_rows=True)["items"][0]], applied_at="2026-09-20T00:00:00Z")
    _metadata(paths, "CLASSB", "1002")
    plan = build_generic_batch_plan(paths, parse_batch_tickers("CLASSB"), archive_path=_archive(tmp_path / "classb.zip", ("CLASSB",)))
    item = plan.safe_dict(include_rows=True)["items"][0]
    assert item["identity_resolution"]["mutation"]["action"] == "CREATE_SECURITY"
    before_company_count = None
    with sqlite3.connect(paths.canonical_db) as conn:
        before_company_count = conn.execute("SELECT COUNT(*) FROM company").fetchone()[0]
        existing_company = conn.execute("SELECT company_id FROM security WHERE current_ticker='NEWC'").fetchone()[0]
    _apply_identities(paths, [item], applied_at="2026-09-21T00:00:00Z")
    with sqlite3.connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM company").fetchone()[0] == before_company_count
        assert conn.execute("SELECT company_id FROM security WHERE current_ticker='CLASSB'").fetchone()[0] == existing_company
        assert conn.execute("SELECT COUNT(*) FROM security WHERE company_id=?", (existing_company,)).fetchone()[0] == 2


def test_ticker_reuse_does_not_join_historical_alias(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    with sqlite3.connect(paths.canonical_db) as conn:
        security_id = conn.execute("SELECT MIN(security_id) FROM security").fetchone()[0]
        conn.execute("INSERT INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES(?,?,?,?,?,?)", (security_id, "REUSE", "SHARADAR", "2000-01-01", "2005-01-01", "fixture"))
    _metadata(paths, "REUSE", "9999", "0000999")

    resolution = resolve_ticker_identity(paths, "REUSE")

    assert resolution.resolution_class == ResolutionClass.IDENTITY_REVIEW_REQUIRED.value
    assert "TICKER_REUSE_RISK" in resolution.reason_codes


def test_same_permaticker_cannot_override_alias_owned_by_other_security(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    first = build_generic_batch_plan(paths, parse_batch_tickers("NEWC"), archive_path=_archive(tmp_path / "source.zip"))
    _apply_identities(paths, [first.safe_dict(include_rows=True)["items"][0]], applied_at="2026-09-20T00:00:00Z")
    with sqlite3.connect(paths.canonical_db) as conn:
        other_security = conn.execute("SELECT MIN(security_id) FROM security WHERE current_ticker<>'NEWC'").fetchone()[0]
        conn.execute("INSERT INTO ticker_alias(security_id,ticker,provider,valid_from,valid_to,source) VALUES(?,?,?,?,?,?)", (other_security, "COLLIDE", "SHARADAR", "2000-01-01", "2005-01-01", "fixture"))
    _metadata(paths, "COLLIDE", "1001")

    resolution = resolve_ticker_identity(paths, "COLLIDE")

    assert resolution.resolution_class == ResolutionClass.IDENTITY_REVIEW_REQUIRED.value
    assert "TICKER_REUSE_PROVIDER_CONFLICT" in resolution.reason_codes


def test_proposed_review_never_authorizes_and_approved_review_does(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    proposed = _registry(tmp_path / "proposed.json", _review("MISSING"))
    approved = _registry(tmp_path / "approved.json", _review("MISSING", "APPROVED"))

    blocked = resolve_ticker_identity(paths, "MISSING", registry_path=proposed)
    allowed = resolve_ticker_identity(paths, "MISSING", registry_path=approved)

    assert blocked.authority_class == AuthorityClass.PROPOSED_REVIEW.value
    assert blocked.automatic_mutation_permitted is False
    assert allowed.authority_class == AuthorityClass.APPROVED_REVIEW.value
    assert allowed.automatic_mutation_permitted is True


def test_approved_review_conflicting_with_provider_fails_closed(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    registry = _registry(tmp_path / "approved.json", _review("NEWC", "APPROVED", cik="0000000999", provider_permaticker="9999"))

    resolution = resolve_ticker_identity(paths, "NEWC", registry_path=registry)

    assert resolution.resolution_class == ResolutionClass.IDENTITY_REVIEW_REQUIRED.value
    assert resolution.automatic_mutation_permitted is False
    assert "APPROVED_REVIEW_PROVIDER_CONFLICT" in resolution.reason_codes


def test_approved_same_security_review_requires_canonical_target(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    registry = _registry(tmp_path / "approved.json", _review(
        "RENAMED",
        "APPROVED",
        resolution_class="TICKER_TRANSITION_SAME_SECURITY",
        company_continuity="SAME_COMPANY",
        security_continuity="SAME_SECURITY",
    ))

    resolution = resolve_ticker_identity(paths, "RENAMED", registry_path=registry)

    assert resolution.resolution_class == ResolutionClass.IDENTITY_REVIEW_REQUIRED.value
    assert resolution.automatic_mutation_permitted is False
    assert "APPROVED_REVIEW_MISSING_CANONICAL_TARGET" in resolution.reason_codes


def test_identity_mutation_rejects_legacy_item_without_resolver_contract(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    legacy_item = {
        "ticker": "LEGACY",
        "provider_metadata": {"identity": {"name": "Legacy Co", "exchange": "NASDAQ", "permaticker": "88"}},
        "market": {"first_date": "2026-01-01"},
    }

    with pytest.raises(RuntimeError, match="IDENTITY_RESOLUTION_REQUIRED:LEGACY"):
        _apply_identities(paths, [legacy_item], applied_at="2026-09-21T00:00:00Z")

    with sqlite3.connect(paths.canonical_db) as conn:
        assert conn.execute("SELECT COUNT(*) FROM security WHERE current_ticker='LEGACY'").fetchone()[0] == 0


def test_identity_and_quarterly_history_are_independent_and_exchange_unknown_is_not_unsupported(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    registry = _registry(tmp_path / "proposed.json", _review("GHOST"))
    with sqlite3.connect(paths.provider_db) as conn:
        row = _archive_row("GHOST")
        row["dimension"] = "MRQ"
        columns = ["observation_id", "ticker", "dimension", "reportperiod"]
        conn.execute("INSERT INTO provider_run VALUES('r','SHARADAR','2026-01-01',NULL,'SUCCESS','fixture',NULL,NULL,'{}')")
        conn.execute("INSERT INTO provider_observation(observation_id,run_id,provider,provider_record_key,native_table,fetched_at_utc,content_hash,provider_status,payload_json) VALUES('o','r','SHARADAR','g','fundamentals','2026-01-01','h','OK','{}')")
        conn.execute("INSERT INTO sharadar_fundamental_observation(observation_id,ticker,dimension,reportperiod) VALUES('o','GHOST','MRQ','2026-06-30')")
    with sqlite3.connect(paths.market_db) as conn:
        conn.execute("INSERT INTO ticker_meta VALUES('GHOST','usa','Technology','Software - Application')")
        conn.execute("INSERT INTO osakedata VALUES('GHOST','usa','2026-09-20',10.0)")

    resolution = resolve_ticker_identity(paths, "GHOST", registry_path=registry)
    assert resolution.exchange_status == "EXCHANGE_UNKNOWN"
    plan = build_generic_batch_plan(paths, parse_batch_tickers("GHOST"), archive_path=tmp_path / "none.zip")
    assert "EXCHANGE_UNKNOWN" in plan.items[0].reason
    assert "INCOMPATIBLE_EXCHANGE" not in plan.items[0].reason
    assert "NO_USABLE_QUARTERLY_HISTORY" in plan.items[0].reason


def test_read_only_preview_is_self_contained_and_does_not_change_databases(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    before = {role: path.stat().st_mtime_ns for role, path in paths.as_dict().items()}

    result = run_preview("DRK KRSA PSQL QVCG", source_paths=paths, run_root=tmp_path / "runs")

    after = {role: path.stat().st_mtime_ns for role, path in paths.as_dict().items()}
    report = Path(result["artifact_dir"], "operation_report.md").read_text(encoding="utf-8")
    assert before == after
    assert all(ticker in report for ticker in ("DRK", "KRSA", "PSQL", "QVCG"))
    assert report.count("PROPOSED_REVIEW_NOT_AUTHORITY") == 4


def test_admin_service_exposes_identity_preview_without_apply_capability(tmp_path: Path) -> None:
    paths = _generic_paths(tmp_path / "source")
    service = FundamentalsAdminUIService(
        run_root=tmp_path / "runs",
        identity_paths=paths,
        recover_publication_on_startup=False,
    )

    result = service.preview("RESOLVE_TICKER_IDENTITY", raw_inputs="DRK")
    capability = next(item for item in service.capabilities() if item.operation_type == "RESOLVE_TICKER_IDENTITY")

    assert result.status == "COMPLETED"
    assert result.mode == "PREVIEW"
    assert result.preview_payload_path and result.preview_payload_path.endswith("identity_preview.json")
    assert capability.preview_enabled is True
    assert capability.copy_apply_enabled is False
    assert capability.production_apply_enabled is False
