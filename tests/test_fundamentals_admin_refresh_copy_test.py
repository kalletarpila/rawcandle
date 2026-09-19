from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from rawcandle.fundamentals.admin import refresh_copy_runtime
from rawcandle.fundamentals.admin.refresh_copy_runtime import (
    StaleRefreshPreview,
    build_publication_date_preservation_map,
    fresh_rebuild_canonical,
    replace_provider_histories,
    revalidate_bound_source,
    run_apply,
)
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.refresh_fundamentals import CONTRACT_VERSION
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    FINANCIAL_FIELDS,
    REFRESH_REQUEST_FIELDS,
    compare_ticker_histories,
    history_fingerprints,
    load_current_history,
    normalize_source_row,
    validate_complete_history,
)
from rawcandle.fundamentals.schema.migrations import (
    CANONICAL_SCHEMA_SQL,
    PROVIDER_SCHEMA_SQL,
    bootstrap_database,
)


NOW = "2026-09-19T12:00:00Z"


def source_row(
    *, ticker: str = "TEST", dimension: str = "ARQ", date: str = "2026-09-15",
    reportperiod: str = "2026-07-31", fiscalperiod: str = "2026-Q2",
    lastupdated: str = "2026-09-16", revenue: int = 120,
) -> dict[str, object]:
    row: dict[str, object] = {
        "ticker": ticker, "dimension": dimension, "date": date,
        "reportperiod": reportperiod, "calendardate": reportperiod,
        "fiscalperiod": fiscalperiod, "lastupdated": lastupdated,
    }
    row.update({field: None for field in FINANCIAL_FIELDS})
    row.update({"revenue": revenue, "netinc": 10, "sharesbas": 5})
    return row


def create_provider(path: Path) -> None:
    bootstrap_database(path, "fundamentals_provider", PROVIDER_SCHEMA_SQL, NOW)


def create_canonical(path: Path) -> None:
    bootstrap_database(path, "fundamentals_v4", CANONICAL_SCHEMA_SQL, NOW)
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO company VALUES(1,'TEST','Test Corp','ACTIVE',?,?)", (NOW, NOW))
        connection.execute("INSERT INTO security VALUES(1,1,'TEST','NASDAQ',1,NULL,NULL,?,?)", (NOW, NOW))
        connection.execute("INSERT INTO ticker_alias VALUES(1,1,'TEST','SHARADAR',NULL,NULL,'fixture')")
        connection.execute("INSERT INTO provider_security_identity VALUES('SHARADAR','100',1,'TEST','fixture',?)", (NOW,))
        connection.execute(
            "INSERT INTO provider_company_identity VALUES('SHARADAR','PERMATICKER','100',1,'TEST','fixture','fixture','100',?)",
            (NOW,),
        )
        connection.execute(
            "INSERT INTO v4_quarter VALUES(1,1,2026,'Q2','2026-07-31','2026-Q2','2026-07-31',"
            "'SHARADAR_ARQ','ACCEPTED','2026-08-26',NULL,?,?)",
            (NOW, NOW),
        )
        connection.execute(
            "INSERT INTO v4_quarter_financials(quarter_id,revenue,net_income,shares_outstanding,canonical_source_policy,created_at_utc,updated_at_utc) "
            "VALUES(1,100,10,5,'SHARADAR_ARQ_PRIMARY',?,?)",
            (NOW, NOW),
        )


def _insert_legacy_version(connection: sqlite3.Connection, row: dict[str, object], observation_id: str) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO provider_run VALUES('legacy','SHARADAR',?,?,'COMPLETED','fixture',NULL,NULL,'{}')",
        (NOW, NOW),
    )
    connection.execute(
        "INSERT INTO provider_observation(observation_id,run_id,provider,provider_record_key,company_id,security_id,provider_ticker,"
        "provider_security_id,native_table,dimension,calendardate,reportperiod,fiscalperiod,source_availability_date,fetched_at_utc,"
        "content_hash,provider_status,payload_json,provenance_json) VALUES(?,'legacy','SHARADAR',?,1,1,'TEST','100','fundamentals',?,?,?,?,?,?,?,'SUCCESS','{}','{}')",
        (observation_id, observation_id, row["dimension"], row["calendardate"], row["reportperiod"], row["fiscalperiod"], row["date"], NOW, observation_id),
    )
    columns = ("observation_id", *REFRESH_REQUEST_FIELDS)
    connection.execute(
        f"INSERT INTO sharadar_fundamental_observation({','.join(columns)}) VALUES({','.join('?' for _ in columns)})",
        (observation_id, *[row[field] for field in REFRESH_REQUEST_FIELDS]),
    )


def test_legacy_same_max_conflicting_versions_are_ambiguous_and_order_invariant(tmp_path: Path) -> None:
    outcomes = []
    versions = [source_row(revenue=100), source_row(revenue=200)]
    for index, ordered in enumerate((versions, list(reversed(versions)))):
        provider = tmp_path / f"provider-{index}.db"
        create_provider(provider)
        with sqlite3.connect(provider) as connection:
            for number, row in enumerate(ordered):
                _insert_legacy_version(connection, row, f"obs-{number}")
        current = load_current_history(provider, "TEST", "ARQ")
        outcomes.append(current["legacy_source_version_ambiguities"])
        assert current["current_row_count"] == 0
    assert outcomes[0][0]["reason"] == "LEGACY_SOURCE_VERSION_AMBIGUITY"
    assert outcomes[1][0]["reason"] == "LEGACY_SOURCE_VERSION_AMBIGUITY"


def test_legacy_unique_max_and_same_max_identical_collapse_safely(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    create_provider(provider)
    with sqlite3.connect(provider) as connection:
        _insert_legacy_version(connection, source_row(lastupdated="2026-09-15", revenue=100), "old")
        _insert_legacy_version(connection, source_row(lastupdated="2026-09-16", revenue=120), "new")
    current = load_current_history(provider, "TEST", "ARQ")
    assert current["rows"][0]["revenue"] == 120
    assert current["legacy_source_version_ambiguities"] == []

    identical = tmp_path / "identical.db"
    create_provider(identical)
    with sqlite3.connect(identical) as connection:
        _insert_legacy_version(connection, source_row(), "a")
        _insert_legacy_version(connection, source_row(), "b")
    current = load_current_history(identical, "TEST", "ARQ")
    assert current["current_row_count"] == 1
    assert current["legacy_source_version_ambiguities"] == []


def test_complete_provider_replacement_uses_true_keys_and_preserves_unrelated_native_state(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    create_provider(provider)
    with sqlite3.connect(provider) as connection:
        connection.execute(
            "INSERT INTO sharadar_ticker_metadata(table_name,ticker,permaticker,payload_json,fetched_at_utc) VALUES('fundamentals','TEST','100','{}',?)",
            (NOW,),
        )
    histories = {
        "TEST": {
            "ARQ": validate_complete_history([source_row()], ticker="TEST", dimension="ARQ"),
            "MRQ": validate_complete_history([source_row(dimension="MRQ", revenue=999)], ticker="TEST", dimension="MRQ"),
        }
    }
    result = replace_provider_histories(
        provider, histories,
        {"TEST": {"company_id": 1, "security_id": 1, "provider_security_id": "100"}},
        applied_at=NOW,
    )
    assert result["unrelated_state_unchanged"] is True
    assert result["verification"]["orphan_children"] == 0
    with sqlite3.connect(provider) as connection:
        keys = [row[0] for row in connection.execute("SELECT provider_record_key FROM provider_observation WHERE run_id=? ORDER BY provider_record_key", (result["run_id"],))]
        assert keys == ["TEST|ARQ|2026-09-15|2026-07-31", "TEST|MRQ|2026-09-15|2026-07-31"]
        assert connection.execute("SELECT COUNT(*) FROM sharadar_ticker_metadata").fetchone()[0] == 1


def test_source_availability_may_change_but_established_first_public_must_not(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    create_provider(provider)
    create_canonical(canonical)
    with sqlite3.connect(canonical) as connection:
        connection.execute("UPDATE v4_quarter SET first_public_result_date='2026-08-26'")
    histories = {
        "TEST": {
            "ARQ": validate_complete_history([source_row()], ticker="TEST", dimension="ARQ"),
            "MRQ": validate_complete_history([source_row(dimension="MRQ", revenue=999)], ticker="TEST", dimension="MRQ"),
        }
    }
    replace_provider_histories(
        provider, histories,
        {"TEST": {"company_id": 1, "security_id": 1, "provider_security_id": "100"}},
        applied_at=NOW,
    )
    monkeypatch.setattr(refresh_copy_runtime, "_events", lambda: ())
    result = fresh_rebuild_canonical(provider, canonical, applied_at=NOW)
    assert result["identity_contract"]["company_security_identity_mapping_unchanged"] is True
    assert result["publication_date_bootstrap"]["preservation_map_applied"] == 1
    assert result["publication_date_bootstrap"]["preservation_map_applicable_existing_quarters"] == 1
    with sqlite3.connect(canonical) as connection:
        quarter = connection.execute("SELECT source_availability_date,first_public_result_date FROM v4_quarter").fetchone()
        assert quarter == ("2026-09-15", "2026-08-26")
        assert connection.execute("SELECT revenue FROM v4_quarter_financials").fetchone()[0] == 120
        assert connection.execute("SELECT company_id,current_ticker FROM security").fetchone() == (1, "TEST")
    assert load_current_history(provider, "TEST", "MRQ")["rows"][0]["revenue"] == 999


def test_comparison_fails_closed_for_legacy_source_ambiguity() -> None:
    normalized = normalize_source_row(source_row())
    current = {
        dimension: {
            "rows": (normalized,), "current_row_count": 1, "legacy_versions_collapsed": 1,
            "legacy_source_version_ambiguities": ([{"reason": "LEGACY_SOURCE_VERSION_AMBIGUITY"}] if dimension == "ARQ" else []),
            "invalid_rows": [], **history_fingerprints([normalized]),
        }
        for dimension in ("ARQ", "MRQ")
    }
    source = {
        "ARQ": validate_complete_history([source_row()], ticker="TEST", dimension="ARQ"),
        "MRQ": validate_complete_history([source_row(dimension="MRQ")], ticker="TEST", dimension="MRQ"),
    }
    result = compare_ticker_histories("TEST", current, source)
    assert result["classification"] == "REVIEW_REQUIRED"
    assert result["review_reason"] == "LEGACY_SOURCE_VERSION_AMBIGUITY"


def test_publish_date_map_scales_deterministically_to_production_shape() -> None:
    rows = {
        (index // 40 + 1, 2000 + (index % 40) // 4, f"Q{index % 4 + 1}"): {
            "source_availability_date": "2026-08-26", "first_public_result_date": None,
        }
        for index in range(88_835)
    }
    first, summary = build_publication_date_preservation_map(rows)
    second, second_summary = build_publication_date_preservation_map(dict(reversed(list(rows.items()))))
    assert len(first) == 88_835
    assert summary["bootstrap_eligible"] == 88_835
    assert summary["repair_required"] == 0
    assert first == second
    assert summary == second_summary


def test_stale_preview_stops_before_candidate_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_root = tmp_path / "runs"
    preview_dir = run_root / "20260919T120000Z_refresh_fundamentals_fixture"
    preview_dir.mkdir(parents=True)
    preview = {
        "contract_version": CONTRACT_VERSION,
        "refresh_set_fingerprint": "a" * 64,
        "future_test_authorized": True,
        "discovery": {"status": "COMPLETE"},
        "schema": {"schema_fingerprint": "schema"},
        "ticker_changes": [{"ticker": "TEST", "classification": "HISTORICAL_REVISION"}],
    }
    preview_path = preview_dir / "refresh_preview.json"
    preview_path.write_text(json.dumps(preview), encoding="utf-8")
    dbs = []
    for name in ("provider", "canonical", "analysis", "market", "taxonomy"):
        path = tmp_path / f"{name}.db"
        sqlite3.connect(path).close()
        dbs.append(path)
    copied = []
    monkeypatch.setattr(refresh_copy_runtime, "revalidate_bound_source", lambda *_args, **_kwargs: (_ for _ in ()).throw(StaleRefreshPreview("STALE_REFRESH_PREVIEW")))
    monkeypatch.setattr(refresh_copy_runtime, "online_backup", lambda *_args, **_kwargs: copied.append(True))
    monkeypatch.setattr(refresh_copy_runtime, "SharadarClient", lambda: object())
    temp_root = tmp_path / "temp"
    result = run_apply(
        preview_payload_path=preview_path, preview_fingerprint="a" * 64,
        source_paths=BatchAddTickerPaths(*dbs), run_root=run_root, temp_root=temp_root,
        confirm_apply=True,
    )
    assert result["outcome"] == "FAILED"
    assert result["failed_stage"] == "SOURCE_REVALIDATION"
    assert result["production_writes"] == 0
    assert copied == []
    assert not temp_root.exists()
    assert list(tmp_path.rglob("provider_candidate.db")) == []
    assert list(tmp_path.rglob("canonical_candidate.db")) == []
    assert list(tmp_path.rglob("analysis_candidate.db")) == []
    assert "Run Preview again" in result["recommended_next_action"]
def test_revalidation_rejects_source_fingerprint_b_after_preview_a(monkeypatch: pytest.MonkeyPatch) -> None:
    class State(SimpleNamespace):
        def as_dict(self):
            return dict(self.__dict__)

    state = State(mode="BOOTSTRAP_BASELINE", published_watermark=None, derived_watermark="2026-09-16", query_start_date="2026-09-13")
    schema = {"schema_fingerprint": "schema"}
    discovery = {
        "changed_tickers": ["TEST"], "observed_source_max_lastupdated": "2026-09-16",
        "status": "COMPLETE",
    }
    common = {
        "ticker": "TEST", "classification": "HISTORICAL_REVISION",
        "current_effective_fingerprint": "current", "source_raw_fingerprints": {"ARQ": "raw", "MRQ": "raw"},
        "added_count": 0, "changed_count": 1, "removed_count": 0, "metadata_only_count": 0,
        "identity": {"status": "KNOWN", "ticker": "TEST", "company_id": 1, "security_id": 1},
    }
    preview_change = dict(common, source_effective_fingerprint="A")
    preview = {
        "state": state.as_dict(), "schema": schema,
        "refresh_set_fingerprint": refresh_copy_runtime.fingerprint(
            refresh_copy_runtime._binding(state=state, schema=schema, discovery=discovery, changes=[preview_change])
        ),
    }
    monkeypatch.setattr(refresh_copy_runtime, "resolve_refresh_state", lambda _path: state)
    monkeypatch.setattr(refresh_copy_runtime, "source_schema", lambda _client: schema)
    monkeypatch.setattr(refresh_copy_runtime, "discover_changed_tickers", lambda *_args, **_kwargs: discovery)
    monkeypatch.setattr(refresh_copy_runtime, "resolve_identity", lambda *_args: common["identity"])
    trust = validate_complete_history([source_row()], ticker="TEST", dimension="ARQ")
    monkeypatch.setattr(refresh_copy_runtime, "fetch_complete_history", lambda *_args: trust)
    monkeypatch.setattr(refresh_copy_runtime, "load_current_history", lambda *_args: {})
    monkeypatch.setattr(refresh_copy_runtime, "compare_ticker_histories", lambda *_args: dict(common, source_effective_fingerprint="B"))
    paths = BatchAddTickerPaths(*(Path(f"/{name}") for name in ("p", "c", "a", "m", "t")))
    with pytest.raises(StaleRefreshPreview, match="STALE_REFRESH_PREVIEW"):
        revalidate_bound_source(preview, paths, object())


def test_removed_quarter_is_evidence_only_and_new_quarter_gets_initial_date(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    create_provider(provider)
    create_canonical(canonical)
    q3 = source_row(date="2026-11-20", reportperiod="2026-10-31", fiscalperiod="2026-Q3", lastupdated="2026-11-20")
    histories = {
        "TEST": {
            "ARQ": validate_complete_history([q3], ticker="TEST", dimension="ARQ"),
            "MRQ": validate_complete_history([dict(q3, dimension="MRQ")], ticker="TEST", dimension="MRQ"),
        }
    }
    replace_provider_histories(
        provider, histories,
        {"TEST": {"company_id": 1, "security_id": 1, "provider_security_id": "100"}},
        applied_at=NOW,
    )
    monkeypatch.setattr(refresh_copy_runtime, "_events", lambda: ())
    result = fresh_rebuild_canonical(provider, canonical, applied_at=NOW, affected_company_ids=[1])
    assert result["impact"]["removed_quarters"] == 1
    assert result["impact"]["added_quarters"] == 1
    assert result["removed_quarter_publication_evidence"][0]["prior_first_public_result_date"] == "2026-08-26"
    with sqlite3.connect(canonical) as connection:
        assert connection.execute("SELECT fiscal_quarter,first_public_result_date FROM v4_quarter").fetchall() == [("Q3", "2026-11-20")]


def test_report_contains_explicit_identity_and_publish_date_invariants() -> None:
    report = refresh_copy_runtime._render_report({
        "run_id": "test", "bound_preview_run_id": "preview", "preview_fingerprint": "fingerprint",
        "summary_counts": {"effective_changed_known": 1},
        "downstream": {
            "provider": {"ticker_count": 1, "tickers": []},
            "canonical": {
                "identity_contract": {"company_security_identity_mapping_unchanged": True},
                "publication_date_bootstrap": {
                    "preservation_map_applied": 10,
                    "preservation_map_applicable_existing_quarters": 10,
                },
            },
            "analysis": {"status": "READY"}, "ticker_changes": [],
        },
    })
    assert "company/security identity mapping before candidate rebuild == after candidate rebuild`: true" in report
    assert "first_public_result_date preservation map applied: 10/10 existing quarters" in report
