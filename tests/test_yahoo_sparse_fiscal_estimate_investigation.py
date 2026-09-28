from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.forecasts.contracts import (
    EARNINGS_TREND_CONTRACT_VERSION,
    EARNINGS_TREND_MIXED_CONTRACT_VERSION,
    FAMILY_FISCAL_ESTIMATE,
    ROW_EMPTY_PLACEHOLDER,
    ROW_USABLE_TARGETED,
    STATE_EXPLICIT_NULL,
    STATE_FIELD_ABSENT,
    STATUS_MALFORMED,
    STATUS_SUCCESS_CHANGED,
    STATUS_SUCCESS_UNCHANGED,
    STATUS_SUCCESS_WITH_DATA,
    STATUS_VALID_NO_DATA,
    ForecastContractError,
    _is_empty_earnings_trend_row,
    canonicalize_earnings_trend,
    parse_payload,
)
from rawcandle.forecasts.fiscal_linker import UNRESOLVED
from rawcandle.forecasts.linking import ForecastLinkService
from rawcandle.forecasts.repository import ForecastRepository
from rawcandle.forecasts.schema import connect_forecasts_db, migrate_forecasts_db
from rawcandle.forecasts.transport import YahooRawResult


FIXTURES = Path(__file__).parent / "fixtures" / "forecasts" / "yahoo"
SPARSE_SHAPES = (
    (
        "mixed_empty_missing_enddate_0q_atlx.real_compact.json",
        ["0q"], ["0y"],
    ),
    (
        "mixed_empty_missing_enddate_0q_1q_bhp.real_compact.json",
        ["0q", "+1q"], ["0y", "+1y"],
    ),
    (
        "mixed_empty_missing_enddate_1q_bivi.real_compact.json",
        ["+1q"], ["0y", "+1y"],
    ),
    (
        "mixed_empty_missing_enddate_0q_1q_1y_btct.real_compact.json",
        ["0q", "+1q", "+1y"], ["0y"],
    ),
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _trend(payload: dict) -> list[dict]:
    return payload["quoteSummary"]["result"][0]["earningsTrend"]["trend"]


@pytest.mark.parametrize(
    ("name", "missing_horizons", "usable_horizons"), SPARSE_SHAPES
)
def test_observed_mixed_shapes_keep_incomplete_rows_empty_and_usable_rows_targeted(
    name: str, missing_horizons: list[str], usable_horizons: list[str]
) -> None:
    payload = _load(name)
    rows = _trend(payload)

    assert [row["period"] for row in rows] == ["0q", "+1q", "0y", "+1y"]
    assert [row["period"] for row in rows if row["endDate"] is None] == (
        missing_horizons
    )
    assert all(
        _is_empty_earnings_trend_row(row)
        for row in rows if row["endDate"] is None
    )
    assert [
        row["period"] for row in rows if not _is_empty_earnings_trend_row(row)
    ] == usable_horizons
    assert all(
        isinstance(row["endDate"], str)
        for row in rows if not _is_empty_earnings_trend_row(row)
    )
    assert payload["_fixtureMetadata"]["stableLiveRounds"] == 2
    assert payload["_fixtureMetadata"]["periodMissingObserved"] is False


@pytest.mark.parametrize("name,missing_horizons,usable_horizons", SPARSE_SHAPES)
def test_mixed_usable_and_incomplete_empty_payload_uses_v2(
    name: str, missing_horizons: list[str], usable_horizons: list[str]
) -> None:
    payload = _load(name)
    parsed = parse_payload(FAMILY_FISCAL_ESTIMATE, payload)

    assert parsed.status == STATUS_SUCCESS_WITH_DATA
    assert parsed.forecast is not None
    assert parsed.forecast.contract_version == EARNINGS_TREND_MIXED_CONTRACT_VERSION
    rows = parsed.forecast.payload["rows"]
    assert [row["providerHorizon"] for row in rows] == ["0q", "+1q", "0y", "+1y"]
    assert [row["occurrenceIndex"] for row in rows] == [0, 1, 2, 3]
    assert [
        row["providerHorizon"] for row in rows
        if row["rowClassification"] == ROW_EMPTY_PLACEHOLDER
    ] == [
        row["period"] for row in _trend(payload)
        if _is_empty_earnings_trend_row(row)
    ]
    assert [
        row["providerHorizon"] for row in rows
        if row["rowClassification"] == ROW_USABLE_TARGETED
    ] == usable_horizons
    for row in rows:
        if row["providerHorizon"] in missing_horizons:
            assert row["providerEndDate"]["state"] == STATE_EXPLICIT_NULL
    with pytest.raises(ForecastContractError, match="period and endDate"):
        canonicalize_earnings_trend(payload)


def test_v2_missing_end_date_state_and_hash_are_deterministic() -> None:
    payload = _load(SPARSE_SHAPES[0][0])
    missing = copy.deepcopy(payload)
    del _trend(missing)[0]["endDate"]
    formatting_only = copy.deepcopy(missing)
    _trend(formatting_only)[2]["growth"]["fmt"] = "format only"

    first = parse_payload(FAMILY_FISCAL_ESTIMATE, missing).forecast
    second = parse_payload(FAMILY_FISCAL_ESTIMATE, formatting_only).forecast

    assert first is not None and second is not None
    assert first.payload["rows"][0]["providerEndDate"]["state"] == STATE_FIELD_ABSENT
    assert first.content_hash == second.content_hash


def test_unknown_field_on_incomplete_row_remains_raw_visible_and_malformed() -> None:
    payload = copy.deepcopy(_load(SPARSE_SHAPES[0][0]))
    row = _trend(payload)[0]
    row["futureProviderField"] = {"raw": 7}

    parsed = parse_payload(FAMILY_FISCAL_ESTIMATE, payload)

    assert row["futureProviderField"] == {"raw": 7}
    assert parsed.status == STATUS_MALFORMED


def test_near_empty_row_does_not_become_usable_from_placeholder_zeroes() -> None:
    payload = copy.deepcopy(_load(SPARSE_SHAPES[0][0]))
    targeted_empty = _trend(payload)[1]
    targeted_empty["revenueEstimate"]["avg"]["fmt"] = "0"

    parsed = parse_payload(FAMILY_FISCAL_ESTIMATE, payload)

    assert parsed.status == STATUS_MALFORMED
    assert parsed.forecast is None


def test_normal_v1_and_exact_empty_template_contracts_are_unchanged() -> None:
    normal = _load("success_with_data_aapl.real_compact.json")
    empty = _load("empty_trend_all_end_dates_null_aei.real_compact.json")

    canonical = canonicalize_earnings_trend(normal)

    assert canonical.contract_version == EARNINGS_TREND_CONTRACT_VERSION
    assert parse_payload(FAMILY_FISCAL_ESTIMATE, normal).status == (
        STATUS_SUCCESS_WITH_DATA
    )
    assert parse_payload(FAMILY_FISCAL_ESTIMATE, empty).status == (
        STATUS_VALID_NO_DATA
    )


def test_usable_row_with_missing_target_remains_malformed() -> None:
    payload = copy.deepcopy(_load(SPARSE_SHAPES[0][0]))
    _trend(payload)[2]["endDate"] = None

    parsed = parse_payload(FAMILY_FISCAL_ESTIMATE, payload)

    assert parsed.status == STATUS_MALFORMED
    assert parsed.forecast is None


def _raw(
    payload: dict | None,
    fetched_at: str,
    *,
    status: str = STATUS_SUCCESS_WITH_DATA,
) -> YahooRawResult:
    return YahooRawResult(
        requested_at_utc=fetched_at,
        fetched_at_utc=fetched_at,
        provider_symbol="ATLX",
        forecast_family=FAMILY_FISCAL_ESTIMATE,
        http_status=200 if payload is not None else None,
        status=status,
        success=status == STATUS_SUCCESS_WITH_DATA,
        error_class=None if status == STATUS_SUCCESS_WITH_DATA else status,
        error_code=None,
        error_message=None,
        raw_payload=payload,
        raw_body=json.dumps(payload, separators=(",", ":")) if payload else None,
        raw_hash=f"raw-{fetched_at}",
        attempt_count=1,
    )


@pytest.mark.parametrize("name,missing_horizons,usable_horizons", SPARSE_SHAPES)
def test_each_v2_shape_normalizes_only_usable_rows(
    tmp_path: Path,
    name: str,
    missing_horizons: list[str],
    usable_horizons: list[str],
) -> None:
    db_path = tmp_path / "forecasts.db"
    migrate_forecasts_db(db_path, applied_at_utc="2026-09-28T08:00:00Z")
    repo = ForecastRepository(db_path, adapter_version="test")
    run_id = repo.start_run(run_id="mixed-shape")

    persisted = repo.record_fetch(
        run_id,
        _raw(_load(name), "2026-09-28T10:00:00Z"),
        company_id=1,
        security_id=10,
    )

    assert persisted.status == STATUS_SUCCESS_CHANGED
    with connect_forecasts_db(db_path) as connection:
        observations = connection.execute(
            "SELECT DISTINCT occurrence_index,provider_horizon "
            "FROM forecast_estimate WHERE snapshot_id=? ORDER BY occurrence_index",
            (persisted.snapshot_id,),
        ).fetchall()
        record_count = connection.execute(
            "SELECT COUNT(*) FROM forecast_estimate WHERE snapshot_id=?",
            (persisted.snapshot_id,),
        ).fetchone()[0]
    assert [row["provider_horizon"] for row in observations] == usable_horizons
    assert not ({row["provider_horizon"] for row in observations} & set(missing_horizons))
    assert record_count == len(usable_horizons) * 23


def _fundamentals(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE company(company_id INTEGER PRIMARY KEY,company_key TEXT);
            CREATE TABLE security(security_id INTEGER PRIMARY KEY,company_id INTEGER,
                current_ticker TEXT,active INTEGER,valid_from TEXT,valid_to TEXT);
            CREATE TABLE ticker_alias(alias_id INTEGER PRIMARY KEY,security_id INTEGER,
                ticker TEXT,provider TEXT,valid_from TEXT,valid_to TEXT,source TEXT);
            CREATE TABLE provider_security_identity(provider TEXT,provider_security_id TEXT,
                security_id INTEGER,provider_ticker TEXT,source TEXT,created_at_utc TEXT);
            CREATE TABLE company_fiscal_calendar_profile(company_id INTEGER PRIMARY KEY,
                typical_fiscal_year_start TEXT,chain_status TEXT,break_reason TEXT,source TEXT,
                source_type TEXT,source_name TEXT,source_field TEXT,source_value TEXT,
                bootstrap_status TEXT,created_at_utc TEXT,updated_at_utc TEXT);
            CREATE TABLE company_fiscal_year_anchor(company_id INTEGER,fiscal_year INTEGER,
                fiscal_year_start TEXT,source TEXT,source_type TEXT,source_name TEXT,
                source_field TEXT,source_value TEXT,confidence TEXT,observed_verified INTEGER,
                created_at_utc TEXT);
            CREATE TABLE v4_quarter(quarter_id INTEGER PRIMARY KEY,company_id INTEGER,
                fiscal_year INTEGER,fiscal_quarter TEXT,period_end TEXT,
                source_fiscalperiod TEXT,source_reportperiod TEXT,identity_provider TEXT,
                identity_status TEXT,source_availability_date TEXT,first_public_result_date TEXT,
                created_at_utc TEXT,updated_at_utc TEXT);
            INSERT INTO company VALUES(1,'atlx');
            INSERT INTO security VALUES(10,1,'ATLX',1,NULL,NULL);
            INSERT INTO v4_quarter VALUES(1,1,2026,'Q3','2026-09-30','2026-Q3',
                '2026-09-30','TEST','ACCEPTED','2026-10-01','2026-10-01',
                '2026-01-01T00:00:00Z','2026-01-01T00:00:00Z');
            """
        )


def test_v2_persistence_linking_pit_and_historical_malformed_are_isolated(
    tmp_path: Path,
) -> None:
    forecast_db = tmp_path / "forecasts.db"
    fundamentals_db = tmp_path / "fundamentals.db"
    migrate_forecasts_db(forecast_db, applied_at_utc="2026-09-28T08:00:00Z")
    _fundamentals(fundamentals_db)
    repo = ForecastRepository(forecast_db, adapter_version="test")
    run_id = repo.start_run(run_id="mixed-v2")
    old = repo.record_fetch(
        run_id,
        _raw(None, "2026-09-28T09:00:00Z", status=STATUS_MALFORMED),
        company_id=1,
        security_id=10,
    )
    payload = _load(SPARSE_SHAPES[0][0])
    changed = repo.record_fetch(
        run_id, _raw(payload, "2026-09-28T10:00:00Z"), company_id=1, security_id=10
    )
    unchanged = repo.record_fetch(
        run_id, _raw(payload, "2026-09-28T11:00:00Z"), company_id=1, security_id=10
    )

    assert old.status == STATUS_MALFORMED
    assert changed.status == STATUS_SUCCESS_CHANGED
    assert unchanged.status == STATUS_SUCCESS_UNCHANGED
    assert changed.snapshot_id == unchanged.snapshot_id
    with connect_forecasts_db(forecast_db) as connection:
        snapshot = connection.execute(
            "SELECT contract_version FROM forecast_snapshot WHERE snapshot_id=?",
            (changed.snapshot_id,),
        ).fetchone()
        estimates = connection.execute(
            "SELECT DISTINCT occurrence_index,provider_horizon FROM forecast_estimate "
            "WHERE snapshot_id=? ORDER BY occurrence_index",
            (changed.snapshot_id,),
        ).fetchall()
        assert snapshot["contract_version"] == EARNINGS_TREND_MIXED_CONTRACT_VERSION
        assert [(row[0], row[1]) for row in estimates] == [(2, "0y")]
        assert connection.execute(
            "SELECT COUNT(*) FROM forecast_estimate WHERE snapshot_id=?",
            (changed.snapshot_id,),
        ).fetchone()[0] == 23
        assert connection.execute(
            "SELECT status FROM forecast_fetch WHERE fetch_id=?", (old.fetch_id,)
        ).fetchone()[0] == STATUS_MALFORMED

    links = ForecastLinkService(forecast_db, fundamentals_db).link_fetch(
        changed.fetch_id, linked_at_utc="2026-09-28T10:01:00Z"
    )
    assert len(links) == 1
    assert links[0]["occurrence_index"] == 2
    assert links[0]["link_status"] == UNRESOLVED
    known = repo.as_known_at(
        forecast_family=FAMILY_FISCAL_ESTIMATE,
        timestamp_utc="2026-09-28T10:30:00Z",
        provider_symbol="ATLX",
        company_id=1,
        security_id=10,
    )
    assert known is not None
    assert known["snapshot"]["contract_version"] == EARNINGS_TREND_MIXED_CONTRACT_VERSION
    assert {row["occurrence_index"] for row in known["records"]} == {2}
