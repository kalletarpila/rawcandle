from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from rawcandle.fundamentals.admin import refresh_copy_runtime, source_bundle
from rawcandle.fundamentals.admin.refresh_copy_runtime import (
    StaleRefreshPreview,
    build_publication_date_preservation_map,
    fresh_rebuild_canonical,
    prepare_full_v2_read_only_copies,
    prepare_refresh_test_read_only_sources,
    replace_provider_histories,
    revalidate_bound_source,
    run_apply,
    run_refresh_test_full_v2_downstream,
    validate_provider_candidate,
)
from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
from rawcandle.fundamentals.admin.first_public_result_date_bootstrap import _apply_bootstrap
from rawcandle.fundamentals.admin.refresh_fundamentals import CONTRACT_VERSION
from rawcandle.fundamentals.admin.refresh_fundamentals import (
    FINANCIAL_FIELDS,
    REFRESH_REQUEST_FIELDS,
    RETAINED_OUTSIDE_SOURCE_WINDOW,
    build_source_history_merge,
    compare_ticker_histories,
    history_fingerprints,
    load_current_history,
    normalize_source_row,
    source_key,
    validate_complete_history,
)
from rawcandle.fundamentals.admin.source_bundle import TaxonomySourceBinding
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


def test_retention_merge_persists_provenance_rebuilds_canonical_and_stabilizes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    create_provider(provider)
    create_canonical(canonical)
    old = source_row(
        date="2016-08-15", reportperiod="2016-06-30", fiscalperiod="2016-Q2",
        lastupdated="2026-05-20", revenue=100,
    )
    latest = source_row(
        date="2026-08-15", reportperiod="2026-06-30", fiscalperiod="2026-Q2",
        lastupdated="2026-09-20", revenue=200,
    )
    with sqlite3.connect(provider) as connection:
        for observation_id, value in (
            ("old-arq", old), ("new-arq", latest),
            ("old-mrq", dict(old, dimension="MRQ", date="2016-06-30")),
            ("new-mrq", dict(latest, dimension="MRQ", date="2026-06-30")),
        ):
            _insert_legacy_version(connection, value, observation_id)
    with sqlite3.connect(canonical) as connection:
        connection.execute(
            "UPDATE v4_quarter SET fiscal_year=2016,fiscal_quarter='Q2',period_end='2016-06-30',"
            "source_fiscalperiod='2016-Q2',source_reportperiod='2016-06-30',"
            "source_availability_date='2016-08-15',first_public_result_date='2016-08-15'"
        )

    current = {dimension: load_current_history(provider, "TEST", dimension) for dimension in ("ARQ", "MRQ")}
    histories = {
        "TEST": {
            "ARQ": validate_complete_history([latest], ticker="TEST", dimension="ARQ"),
            "MRQ": validate_complete_history(
                [dict(latest, dimension="MRQ", date="2026-06-30")], ticker="TEST", dimension="MRQ",
            ),
        }
    }
    plan = build_source_history_merge("TEST", current, histories["TEST"])
    identity = {"TEST": {"company_id": 1, "security_id": 1, "provider_security_id": "100"}}
    replacement = replace_provider_histories(
        provider, histories, identity, applied_at=NOW, merge_plans={"TEST": plan},
    )
    assert replacement["verification"]["histories"][0]["retained_only_key_count"] == 1
    validation = replacement["verification"]["retention_validation"]
    assert validation["expected_retained_total"] == 2
    assert validation["actual_retained_total"] == 2
    assert validation["retained_arq"] == 1
    assert validation["retained_mrq"] == 1
    assert validation["retained_provenance_valid"] == 2
    assert validation["retained_payload_mismatch_count"] == 0
    assert validation["retained_duplicate_count"] == 0
    assert validation["current_source_marked_retained_count"] == 0
    retained = load_current_history(provider, "TEST", "ARQ")["rows"][0]
    assert retained["_history_retention_status"] == RETAINED_OUTSIDE_SOURCE_WINDOW
    assert retained["revenue"] == 100

    monkeypatch.setattr(refresh_copy_runtime, "_events", lambda: ())
    rebuilt = fresh_rebuild_canonical(provider, canonical, applied_at=NOW, affected_company_ids=[1])
    assert rebuilt["identity_contract"]["company_security_identity_mapping_unchanged"] is True
    with sqlite3.connect(canonical) as connection:
        rows = connection.execute(
            "SELECT q.fiscal_year,q.first_public_result_date,f.revenue FROM v4_quarter q "
            "JOIN v4_quarter_financials f USING(quarter_id) ORDER BY q.fiscal_year"
        ).fetchall()
    assert rows == [(2016, "2016-08-15", 100), (2026, "2026-08-15", 200)]

    second_current = {
        dimension: load_current_history(provider, "TEST", dimension) for dimension in ("ARQ", "MRQ")
    }
    assert compare_ticker_histories("TEST", second_current, histories["TEST"])["classification"] == "NO_EFFECTIVE_CHANGE"

    newer_key = dict(old, date="2016-09-01", revenue=777, lastupdated="2026-09-21")
    newer_histories = {
        "TEST": {
            "ARQ": validate_complete_history([newer_key, latest], ticker="TEST", dimension="ARQ"),
            "MRQ": histories["TEST"]["MRQ"],
        }
    }
    newer_plan = build_source_history_merge("TEST", second_current, newer_histories["TEST"])
    replace_provider_histories(
        provider, newer_histories, identity, applied_at="2026-09-21T11:00:00Z",
        merge_plans={"TEST": newer_plan},
    )
    fresh_rebuild_canonical(
        provider, canonical, applied_at="2026-09-21T11:00:00Z", affected_company_ids=[1],
    )
    with sqlite3.connect(canonical) as connection:
        assert connection.execute(
            "SELECT q.first_public_result_date,f.revenue FROM v4_quarter q "
            "JOIN v4_quarter_financials f USING(quarter_id) WHERE q.fiscal_year=2016"
        ).fetchone() == ("2016-08-15", 777)

    second_current = {
        dimension: load_current_history(provider, "TEST", dimension) for dimension in ("ARQ", "MRQ")
    }
    reappeared = dict(old, revenue=999, lastupdated="2026-09-21")
    reappeared_histories = {
        "TEST": {
            "ARQ": validate_complete_history(
                [reappeared, newer_key, latest], ticker="TEST", dimension="ARQ",
            ),
            "MRQ": validate_complete_history(
                [dict(reappeared, dimension="MRQ", date="2016-06-30"), dict(latest, dimension="MRQ", date="2026-06-30")],
                ticker="TEST", dimension="MRQ",
            ),
        }
    }
    reappeared_plan = build_source_history_merge("TEST", second_current, reappeared_histories["TEST"])
    replace_provider_histories(
        provider, reappeared_histories, identity, applied_at="2026-09-21T12:00:00Z",
        merge_plans={"TEST": reappeared_plan},
    )
    current_arq = {source_key(row): row for row in load_current_history(provider, "TEST", "ARQ")["rows"]}
    assert current_arq[source_key(old)]["revenue"] == 999
    assert current_arq[source_key(old)].get("_history_retention_status") is None
    fresh_rebuild_canonical(
        provider, canonical, applied_at="2026-09-21T12:00:00Z", affected_company_ids=[1],
    )
    with sqlite3.connect(canonical) as connection:
        assert connection.execute(
            "SELECT q.first_public_result_date,f.revenue FROM v4_quarter q "
            "JOIN v4_quarter_financials f USING(quarter_id) WHERE q.fiscal_year=2016"
        ).fetchone() == ("2016-08-15", 777)


def test_true_interior_removal_deletes_key_but_preserves_alternate_canonical_quarter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    create_provider(provider)
    create_canonical(canonical)
    oldest = source_row(date="2020-11-20", reportperiod="2020-10-07", fiscalperiod="2020-Q3")
    alternate = source_row(date="2022-10-13", reportperiod="2022-06-30", fiscalperiod="2022-Q2", revenue=150)
    obsolete = source_row(date="2022-11-28", reportperiod="2022-06-30", fiscalperiod="2022-Q2", revenue=151)
    latest = source_row(date="2026-08-05", reportperiod="2026-06-30", fiscalperiod="2026-Q2", revenue=200)
    mrq = [
        dict(oldest, dimension="MRQ", date="2020-10-07"),
        dict(alternate, dimension="MRQ", date="2022-06-30"),
        dict(latest, dimension="MRQ", date="2026-06-30"),
    ]
    with sqlite3.connect(provider) as connection:
        for index, value in enumerate([oldest, alternate, obsolete, latest, *mrq]):
            _insert_legacy_version(connection, value, f"obs-{index}")
    with sqlite3.connect(canonical) as connection:
        connection.execute(
            "UPDATE v4_quarter SET fiscal_year=2022,fiscal_quarter='Q2',period_end='2022-06-30',"
            "source_fiscalperiod='2022-Q2',source_reportperiod='2022-06-30',"
            "source_availability_date='2022-10-13',first_public_result_date='2022-10-13'"
        )
        connection.execute("UPDATE v4_quarter_financials SET revenue=150")

    current = {dimension: load_current_history(provider, "TEST", dimension) for dimension in ("ARQ", "MRQ")}
    histories = {
        "TEST": {
            "ARQ": validate_complete_history([oldest, alternate, latest], ticker="TEST", dimension="ARQ"),
            "MRQ": validate_complete_history(mrq, ticker="TEST", dimension="MRQ"),
        }
    }
    comparison = compare_ticker_histories("TEST", current, histories["TEST"])
    assert comparison["classification"] == "SOURCE_REMOVAL"
    plan = build_source_history_merge("TEST", current, histories["TEST"])
    replace_provider_histories(
        provider, histories,
        {"TEST": {"company_id": 1, "security_id": 1, "provider_security_id": "100"}},
        applied_at=NOW, merge_plans={"TEST": plan},
    )
    arq_keys = {source_key(row) for row in load_current_history(provider, "TEST", "ARQ")["rows"]}
    assert source_key(obsolete) not in arq_keys
    assert source_key(alternate) in arq_keys

    monkeypatch.setattr(refresh_copy_runtime, "_events", lambda: ())
    fresh_rebuild_canonical(provider, canonical, applied_at=NOW, affected_company_ids=[1])
    with sqlite3.connect(canonical) as connection:
        assert connection.execute(
            "SELECT q.first_public_result_date,f.revenue FROM v4_quarter q "
            "JOIN v4_quarter_financials f USING(quarter_id) WHERE q.fiscal_year=2022 AND q.fiscal_quarter='Q2'"
        ).fetchone() == ("2022-10-13", 150)


def test_retained_provider_provenance_is_a_fail_closed_candidate_gate(tmp_path: Path) -> None:
    provider = tmp_path / "provider.db"
    create_provider(provider)
    old = source_row(
        date="2016-08-15", reportperiod="2016-06-30", fiscalperiod="2016-Q2",
        lastupdated="2026-05-20", revenue=100,
    )
    latest = source_row(
        date="2026-08-15", reportperiod="2026-06-30", fiscalperiod="2026-Q2",
        lastupdated="2026-09-20", revenue=200,
    )
    with sqlite3.connect(provider) as connection:
        for observation_id, value in (
            ("old-arq", old), ("new-arq", latest),
            ("old-mrq", dict(old, dimension="MRQ", date="2016-06-30")),
            ("new-mrq", dict(latest, dimension="MRQ", date="2026-06-30")),
        ):
            _insert_legacy_version(connection, value, observation_id)
    current = {dimension: load_current_history(provider, "TEST", dimension) for dimension in ("ARQ", "MRQ")}
    histories = {
        "TEST": {
            "ARQ": validate_complete_history([latest], ticker="TEST", dimension="ARQ"),
            "MRQ": validate_complete_history(
                [dict(latest, dimension="MRQ", date="2026-06-30")], ticker="TEST", dimension="MRQ",
            ),
        }
    }
    plan = build_source_history_merge("TEST", current, histories["TEST"])
    replace_provider_histories(
        provider, histories,
        {"TEST": {"company_id": 1, "security_id": 1, "provider_security_id": "100"}},
        applied_at=NOW, merge_plans={"TEST": plan},
    )
    with sqlite3.connect(provider) as connection:
        connection.execute(
            "UPDATE provider_observation SET provenance_json=? "
            "WHERE observation_id IN (SELECT observation_id FROM sharadar_fundamental_observation "
            "WHERE ticker='TEST' AND reportperiod='2016-06-30')",
            (json.dumps({"history_retention_status": RETAINED_OUTSIDE_SOURCE_WINDOW}),),
        )
    with pytest.raises(RuntimeError, match="REFRESH_RETAINED_PROVENANCE_INVALID"):
        validate_provider_candidate(provider, histories, merge_plans={"TEST": plan})


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


def test_second_generation_preserves_established_date_and_initializes_new_quarter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    create_provider(provider)
    create_canonical(canonical)
    monkeypatch.setattr(refresh_copy_runtime, "_events", lambda: ())
    identity = {"TEST": {"company_id": 1, "security_id": 1, "provider_security_id": "100"}}

    first_q2 = source_row(date="2026-08-26", lastupdated="2026-08-26", revenue=100)
    first_histories = {
        "TEST": {
            "ARQ": validate_complete_history([first_q2], ticker="TEST", dimension="ARQ"),
            "MRQ": validate_complete_history([dict(first_q2, dimension="MRQ")], ticker="TEST", dimension="MRQ"),
        }
    }
    replace_provider_histories(provider, first_histories, identity, applied_at=NOW)
    first = fresh_rebuild_canonical(provider, canonical, applied_at=NOW, affected_company_ids=[1])
    assert first["publication_date_bootstrap"]["bootstrap_eligible"] == 1
    with sqlite3.connect(canonical) as connection:
        assert connection.execute(
            "SELECT source_availability_date,first_public_result_date FROM v4_quarter"
        ).fetchone() == ("2026-08-26", "2026-08-26")

    revised_q2 = source_row(date="2026-09-15", lastupdated="2026-09-15", revenue=120)
    new_q3 = source_row(
        date="2026-11-20", reportperiod="2026-10-31", fiscalperiod="2026-Q3",
        lastupdated="2026-11-20", revenue=130,
    )
    second_histories = {
        "TEST": {
            "ARQ": validate_complete_history([revised_q2, new_q3], ticker="TEST", dimension="ARQ"),
            "MRQ": validate_complete_history(
                [dict(revised_q2, dimension="MRQ"), dict(new_q3, dimension="MRQ")],
                ticker="TEST", dimension="MRQ",
            ),
        }
    }
    second_applied_at = "2026-11-21T12:00:00Z"
    replace_provider_histories(provider, second_histories, identity, applied_at=second_applied_at)
    second = fresh_rebuild_canonical(
        provider, canonical, applied_at=second_applied_at, affected_company_ids=[1],
    )
    assert second["publication_date_bootstrap"].get("bootstrap_eligible", 0) == 0
    assert second["publication_date_bootstrap"]["preservation_map_applied"] == 1
    assert second["publication_date_bootstrap"]["preservation_map_applicable_existing_quarters"] == 1
    assert second["impact"]["source_availability_date_changes"] == 1
    assert second["impact"]["new_first_public_result_date_established"] == 1
    with sqlite3.connect(canonical) as connection:
        rows = connection.execute(
            "SELECT fiscal_quarter,source_availability_date,first_public_result_date "
            "FROM v4_quarter ORDER BY fiscal_quarter"
        ).fetchall()
    assert rows == [
        ("Q2", "2026-09-15", "2026-08-26"),
        ("Q3", "2026-11-20", "2026-11-20"),
    ]


def test_standalone_bootstrap_then_normal_refresh_has_zero_historical_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = tmp_path / "provider.db"
    canonical = tmp_path / "canonical.db"
    create_provider(provider)
    create_canonical(canonical)
    with sqlite3.connect(canonical) as connection:
        assert _apply_bootstrap(connection) == 1
    monkeypatch.setattr(refresh_copy_runtime, "_events", lambda: ())
    identity = {"TEST": {"company_id": 1, "security_id": 1, "provider_security_id": "100"}}
    revised_q2 = source_row(date="2026-09-15", lastupdated="2026-09-15", revenue=120)
    new_q3 = source_row(
        date="2026-11-20", reportperiod="2026-10-31", fiscalperiod="2026-Q3",
        lastupdated="2026-11-20", revenue=130,
    )
    histories = {
        "TEST": {
            "ARQ": validate_complete_history([revised_q2, new_q3], ticker="TEST", dimension="ARQ"),
            "MRQ": validate_complete_history(
                [dict(revised_q2, dimension="MRQ"), dict(new_q3, dimension="MRQ")],
                ticker="TEST", dimension="MRQ",
            ),
        }
    }
    replace_provider_histories(provider, histories, identity, applied_at=NOW)
    result = fresh_rebuild_canonical(
        provider, canonical, applied_at=NOW, affected_company_ids=[1],
    )
    assert result["publication_date_bootstrap"].get("bootstrap_eligible", 0) == 0
    assert result["publication_date_bootstrap"]["preservation_map_applied"] == 1
    assert result["impact"]["source_availability_date_changes"] == 1
    assert result["impact"]["new_first_public_result_date_established"] == 1
    with sqlite3.connect(canonical) as connection:
        rows = connection.execute(
            "SELECT fiscal_quarter,source_availability_date,first_public_result_date "
            "FROM v4_quarter ORDER BY fiscal_quarter"
        ).fetchall()
    assert rows == [
        ("Q2", "2026-09-15", "2026-08-26"),
        ("Q3", "2026-11-20", "2026-11-20"),
    ]


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


def test_full_v2_read_only_copy_helper_prepares_market_and_taxonomy(tmp_path: Path) -> None:
    sources = []
    for role in ("provider", "canonical", "analysis", "market", "taxonomy"):
        path = tmp_path / "source" / f"{role}.db"
        path.parent.mkdir(exist_ok=True)
        with sqlite3.connect(path) as connection:
            connection.execute("CREATE TABLE state(value TEXT)")
            connection.execute("INSERT INTO state VALUES(?)", (role,))
        sources.append(path)
    lane = tmp_path / "lane"
    copies, evidence = prepare_full_v2_read_only_copies(
        BatchAddTickerPaths(*sources), lane_dir=lane,
    )
    assert set(copies) == {"market", "taxonomy"}
    assert set(evidence) == {"market", "taxonomy"}
    for role, path in copies.items():
        assert path != sources[("provider", "canonical", "analysis", "market", "taxonomy").index(role)]
        with sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True) as connection:
            assert connection.execute("SELECT value FROM state").fetchone()[0] == role
        assert evidence[role]["immutable_after_creation"] is True
        assert evidence[role]["cleanup_required"] is True


def test_refresh_test_uses_compact_market_bundle_and_direct_locked_taxonomy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    roles = ("provider", "canonical", "analysis", "market", "taxonomy")
    sources = []
    for role in roles:
        path = tmp_path / "source" / f"{role}.db"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(role.encode())
        sources.append(path)
    canonical_candidate = tmp_path / "lane" / "canonical_candidate.db"
    canonical_candidate.parent.mkdir()
    canonical_candidate.write_bytes(b"canonical-candidate")
    copied_sources: list[Path] = []

    def fake_backup(source: Path, destination: Path) -> dict[str, object]:
        copied_sources.append(source)
        destination.write_bytes(source.read_bytes())
        return {
            "source": str(source), "destination": str(destination),
            "quick_check": "ok", "size": destination.stat().st_size,
        }

    taxonomy_binding = TaxonomySourceBinding(
        mode="DIRECT_LOCKED_READ", source_path=str(sources[4].resolve()), domain="dc_ecosystem",
        version="DC_V1", semantic_fingerprint="taxonomy-fingerprint", membership_rows=1,
        lock_path=str(tmp_path / "taxonomy.lock"), lock_contract_status="AUTHORITATIVE_TAXONOMY_LOCK_HELD",
        runtime_authorized=True, packaged=False,
    )
    manifest = {
        "source_contract_version": "FUNDAMENTALS_READ_ONLY_SOURCE_V1",
        "mode": "STABLE_SOURCE_BUNDLE",
        "as_of_date": "2026-09-22",
        "canonical_binding": {"semantic_fingerprint": "canonical-fingerprint"},
        "market": {
            "semantic_fingerprint": "market-fingerprint", "physical_sha256": "market-sha",
            "row_counts": {"ticker_meta": 2, "osakedata": 3, "splits_data": 1},
            "valuation_coverage": {"status_counts": {
                "PRICE_FOUND": 1, "NO_MATCHING_VALID_PRICE": 1,
                "NO_CUTOFF": 1, "NO_TICKER": 0,
            }},
        },
    }

    def fake_build(**kwargs: object) -> SimpleNamespace:
        assert kwargs["market_db"] == sources[3]
        assert kwargs["canonical_db"] == canonical_candidate
        assert kwargs["as_of_date"] == "2026-09-22"
        bundle_dir = Path(kwargs["bundle_dir"])
        bundle_dir.mkdir()
        market_db = bundle_dir / "market.db"
        market_db.write_bytes(b"compact")
        manifest_path = bundle_dir / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return SimpleNamespace(
            market_db=market_db, manifest_path=manifest_path,
            manifest=manifest, extraction_seconds=0.25,
        )

    validated: list[object] = []
    monkeypatch.setattr(refresh_copy_runtime, "online_backup", fake_backup)
    monkeypatch.setattr(source_bundle, "build_stable_read_only_source_bundle", fake_build)
    monkeypatch.setattr(source_bundle, "validate_stable_read_only_source_bundle", validated.append)

    paths, evidence = prepare_refresh_test_read_only_sources(
        BatchAddTickerPaths(*sources), lane_dir=canonical_candidate.parent,
        canonical_candidate=canonical_candidate, as_of_date="2026-09-22",
        taxonomy_binding=taxonomy_binding,
    )

    assert copied_sources == []
    assert paths["market"].name == "market.db"
    assert paths["taxonomy"] == sources[4].resolve()
    assert evidence["market"]["mode"] == "STABLE_SOURCE_BUNDLE"
    assert evidence["market"]["bundle_manifest"] is manifest
    assert evidence["market"]["bundle_manifest"]["market"]["valuation_coverage"]["status_counts"] == {
        "PRICE_FOUND": 1, "NO_MATCHING_VALID_PRICE": 1, "NO_CUTOFF": 1, "NO_TICKER": 0,
    }
    assert evidence["taxonomy"]["mode"] == "DIRECT_LOCKED_READ"
    assert evidence["taxonomy"]["binding"]["version"] == "DC_V1"
    assert evidence["taxonomy"]["old_full_copy_bytes_avoided"] == len(b"taxonomy")
    assert evidence["taxonomy"]["cleanup_required"] is False
    assert evidence["market"]["old_full_copy_bytes_avoided"] == len(b"market")
    assert validated


@pytest.mark.parametrize("failure_point", ["taxonomy", "bundle", "validation"])
def test_refresh_test_source_preparation_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_point: str,
) -> None:
    sources = []
    for role in ("provider", "canonical", "analysis", "market", "taxonomy"):
        path = tmp_path / f"{role}.db"
        path.write_bytes(role.encode())
        sources.append(path)
    lane = tmp_path / "lane"
    lane.mkdir()
    canonical_candidate = lane / "canonical_candidate.db"
    canonical_candidate.write_bytes(b"canonical")

    def fake_backup(source: Path, destination: Path) -> dict[str, object]:
        destination.write_bytes(source.read_bytes())
        return {"source": str(source), "destination": str(destination), "quick_check": "ok", "size": 1}

    def fake_build(**kwargs: object) -> SimpleNamespace:
        if failure_point == "bundle":
            raise RuntimeError("READ_ONLY_SOURCE_DRIFT")
        bundle_dir = Path(kwargs["bundle_dir"])
        bundle_dir.mkdir()
        market_db = bundle_dir / "market.db"
        market_db.write_bytes(b"compact")
        manifest_path = bundle_dir / "manifest.json"
        manifest_path.write_text("{}", encoding="utf-8")
        return SimpleNamespace(
            market_db=market_db, manifest_path=manifest_path,
            manifest={"market": {}}, extraction_seconds=0.1,
        )

    monkeypatch.setattr(refresh_copy_runtime, "online_backup", fake_backup)
    taxonomy_binding = TaxonomySourceBinding(
        mode="FULL_SQLITE_BACKUP" if failure_point == "taxonomy" else "DIRECT_LOCKED_READ",
        source_path=str(sources[4].resolve()), domain="dc_ecosystem",
        version="DC_V1", semantic_fingerprint="fp", membership_rows=1,
        lock_path=str(tmp_path / "taxonomy.lock"),
        lock_contract_status=(
            "FULL_SQLITE_BACKUP_RUNTIME_AUTHORITY"
            if failure_point == "taxonomy" else "AUTHORITATIVE_TAXONOMY_LOCK_HELD"
        ),
        runtime_authorized=True, packaged=False,
    )
    monkeypatch.setattr(source_bundle, "build_stable_read_only_source_bundle", fake_build)
    monkeypatch.setattr(
        source_bundle, "validate_stable_read_only_source_bundle",
        lambda _bundle: (_ for _ in ()).throw(RuntimeError("SOURCE_BUNDLE_INVALID"))
        if failure_point == "validation" else None,
    )

    expected = {
        "taxonomy": "REFRESH_DIRECT_TAXONOMY_BINDING_REQUIRED",
        "bundle": "READ_ONLY_SOURCE_DRIFT",
        "validation": "SOURCE_BUNDLE_INVALID",
    }[failure_point]
    with pytest.raises(RuntimeError, match=expected):
        prepare_refresh_test_read_only_sources(
            BatchAddTickerPaths(*sources), lane_dir=lane,
            canonical_candidate=canonical_candidate, as_of_date="2026-09-22",
            taxonomy_binding=taxonomy_binding,
        )


def test_refresh_production_uses_same_compact_source_policy_as_test() -> None:
    from rawcandle.fundamentals.admin import refresh_production

    assert (
        refresh_production.prepare_compact_read_only_sources
        is refresh_copy_runtime.prepare_compact_read_only_sources
    )


def test_refresh_test_downstream_receives_compact_market_and_live_taxonomy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = tmp_path / "provider_candidate.db"
    canonical = tmp_path / "canonical_candidate.db"
    compact_market = tmp_path / "market_source_bundle" / "market.db"
    live_taxonomy = tmp_path / "analysis.db"
    captured: dict[str, object] = {}

    def fake_downstream(paths: dict[str, Path], **kwargs: object) -> dict[str, object]:
        captured.update({"paths": paths, **kwargs})
        return {"status": "READY"}

    monkeypatch.setattr(refresh_copy_runtime, "run_full_v2_downstream", fake_downstream)
    result = run_refresh_test_full_v2_downstream(
        provider_candidate=provider,
        canonical_candidate=canonical,
        read_only_sources={"market": compact_market, "taxonomy": live_taxonomy},
        lane_dir=tmp_path,
        as_of_date="2026-09-22",
    )

    assert result == {"status": "READY"}
    assert captured["paths"]["market"] == compact_market
    assert captured["paths"]["taxonomy"] == live_taxonomy
    assert captured["paths"]["market"] != tmp_path / "osakedata.db"
    assert captured["as_of_date"] == "2026-09-22"


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
            "read_only_source_binding": {
                "market": {
                    "mode": "STABLE_SOURCE_BUNDLE",
                    "bundle_manifest": {
                        "source_contract_version": "FUNDAMENTALS_READ_ONLY_SOURCE_V1",
                        "as_of_date": "2026-09-22",
                        "canonical_binding": {"semantic_fingerprint": "canonical-fp"},
                        "market": {
                            "semantic_fingerprint": "market-fp", "physical_sha256": "market-sha",
                            "row_counts": {"osakedata": 10},
                            "valuation_coverage": {"status_counts": {
                                "PRICE_FOUND": 7, "NO_MATCHING_VALID_PRICE": 1,
                                "NO_CUTOFF": 2, "NO_TICKER": 0,
                            }},
                        },
                    },
                },
                "taxonomy": {
                    "mode": "DIRECT_LOCKED_READ",
                    "binding": {"version": "DC_V1", "semantic_fingerprint": "taxonomy-fp"},
                },
            },
        },
    })
    assert "company/security identity mapping before candidate rebuild == after candidate rebuild`: true" in report
    assert "first_public_result_date preservation map applied: 10/10 existing quarters" in report
    assert "Market mode: `STABLE_SOURCE_BUNDLE`" in report
    assert "Coverage: PRICE_FOUND=7, NO_MATCHING_VALID_PRICE=1, NO_CUTOFF=2, NO_TICKER=0" in report
    assert "Taxonomy mode: `DIRECT_LOCKED_READ`" in report


def test_report_uses_exact_canonical_deltas_and_renders_retention_validation() -> None:
    changes = []
    company_impact = {}
    expected = {
        "BNC": (1, 2, 1), "NAMS": (0, 1, 0), "BNED": (0, 0, 0),
        "AI": (1, 0, 0), "GOSS": (0, 32, 0), "LOVE": (1, 2, 0),
    }
    for company_id, (ticker, canonical) in enumerate(expected.items(), start=1):
        changes.append({
            "ticker": ticker, "classification": "HISTORICAL_REVISION",
            "identity": {"company_id": company_id},
            "current_counts": {"ARQ": 10}, "source_counts": {"ARQ": 11},
            "added_count": 9, "changed_count": 8, "removed_count": 7,
        })
        company_impact[company_id] = {
            "quarters_added": canonical[0], "quarters_changed": canonical[1],
            "quarters_removed": canonical[2],
        }
    report = refresh_copy_runtime._render_report({
        "run_id": "test", "bound_preview_run_id": "preview", "preview_fingerprint": "fingerprint",
        "summary_counts": {"effective_changed_known": len(changes)},
        "downstream": {
            "provider": {"ticker_count": len(changes), "tickers": []},
            "canonical": {
                "company_impact": company_impact,
                "identity_contract": {"company_security_identity_mapping_unchanged": True},
                "publication_date_bootstrap": {
                    "preservation_map_applied": 88_834,
                    "preservation_map_applicable_existing_quarters": 88_834,
                },
            },
            "analysis": {"status": "READY"}, "ticker_changes": changes,
            "test_evidence": {"summary": {
                "expected_retained_total": 98, "actual_retained_total": 98,
                "retained_arq": 48, "retained_mrq": 50,
                "retained_provenance_valid": 98, "true_removal_expected": 5,
                "true_removal_absent": 5, "ambiguous_removal_count": 0,
            }},
        },
    })
    for ticker, canonical in expected.items():
        assert f"| {ticker} |" in report
        assert f"+{canonical[0]} / {canonical[1]} / -{canonical[2]}" in report
    assert "+9 / ~8 / -7" not in report
    assert "## Source-Window Retention Validation" in report
    assert "Correct retained provenance: 98/98" in report
    assert "True source removals absent from candidate: 5/5" in report
