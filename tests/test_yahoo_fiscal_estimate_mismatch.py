from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from rawcandle.forecasts.contracts import (
    FAMILY_FISCAL_ESTIMATE,
    STATUS_MALFORMED,
    STATUS_VALID_NO_DATA,
    STATUS_SUCCESS_WITH_DATA,
    ForecastContractError,
    canonicalize_earnings_trend,
    parse_payload,
)
from rawcandle.forecasts.repository import ForecastRepository
from rawcandle.forecasts.schema import connect_forecasts_db, migrate_forecasts_db
from rawcandle.forecasts.transport import YahooRawResult


FIXTURES = Path(__file__).parent / "fixtures" / "forecasts" / "yahoo"
EMPTY_FIXTURES = (
    "empty_trend_all_end_dates_null_aei.real_compact.json",
    "empty_trend_partial_end_dates_abvc.real_compact.json",
    "empty_trend_annual_end_date_aiv.real_compact.json",
)


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", EMPTY_FIXTURES)
def test_observed_empty_template_is_valid_no_data(name: str) -> None:
    parsed = parse_payload(FAMILY_FISCAL_ESTIMATE, _load(name))

    assert parsed.status == STATUS_VALID_NO_DATA
    assert parsed.forecast is None


def test_fixture_shapes_preserve_observed_end_date_classes() -> None:
    all_null, partial, annual = (
        _load(name)["quoteSummary"]["result"][0]["earningsTrend"]["trend"]
        for name in EMPTY_FIXTURES
    )

    assert [row["endDate"] for row in all_null] == [None, None, None, None]
    assert [row["endDate"] for row in partial] == [
        "2023-06-30", None, "2023-12-31", None,
    ]
    assert [row["endDate"] for row in annual] == [None, None, "2026-12-31", None]
    assert all(len(rows) == 4 for rows in (all_null, partial, annual))


def test_missing_period_on_otherwise_exact_empty_template_is_no_data() -> None:
    payload = _load(EMPTY_FIXTURES[0])
    del payload["quoteSummary"]["result"][0]["earningsTrend"]["trend"][0]["period"]

    assert parse_payload(FAMILY_FISCAL_ESTIMATE, payload).status == STATUS_VALID_NO_DATA


def test_canonicalizer_remains_strict_for_missing_target_metadata() -> None:
    payload = _load(EMPTY_FIXTURES[0])

    with pytest.raises(ForecastContractError, match="period and endDate"):
        canonicalize_earnings_trend(payload)


def test_usable_estimate_with_missing_target_metadata_remains_malformed() -> None:
    payload = _load(EMPTY_FIXTURES[0])
    first = payload["quoteSummary"]["result"][0]["earningsTrend"]["trend"][0]
    first["earningsEstimate"]["avg"] = {"raw": 1.25, "fmt": "1.25"}
    first["earningsEstimate"]["numberOfAnalysts"] = {"raw": 2, "fmt": "2"}

    parsed = parse_payload(FAMILY_FISCAL_ESTIMATE, payload)

    assert parsed.status == STATUS_MALFORMED
    assert parsed.error_code == "ForecastContractError"


def test_unknown_field_does_not_get_hidden_by_empty_template_classification() -> None:
    payload = _load(EMPTY_FIXTURES[1])
    payload["quoteSummary"]["result"][0]["earningsTrend"]["trend"][1][
        "newProviderField"
    ] = {"raw": 1}

    assert parse_payload(FAMILY_FISCAL_ESTIMATE, payload).status == STATUS_MALFORMED


def test_boolean_false_is_not_accepted_as_numeric_zero_placeholder() -> None:
    payload = _load(EMPTY_FIXTURES[0])
    row = payload["quoteSummary"]["result"][0]["earningsTrend"]["trend"][0]
    row["revenueEstimate"]["avg"]["raw"] = False

    assert parse_payload(FAMILY_FISCAL_ESTIMATE, payload).status == STATUS_MALFORMED


def test_empty_template_classification_is_stable_for_repeated_observation() -> None:
    payload = _load(EMPTY_FIXTURES[2])
    repeated = copy.deepcopy(payload)

    first = parse_payload(FAMILY_FISCAL_ESTIMATE, payload)
    second = parse_payload(FAMILY_FISCAL_ESTIMATE, repeated)

    assert first == second
    assert first.status == STATUS_VALID_NO_DATA


def test_empty_template_persists_fetch_and_raw_but_no_semantic_snapshot(
    tmp_path: Path,
) -> None:
    database = tmp_path / "forecasts.db"
    migrate_forecasts_db(database)
    repository = ForecastRepository(database, adapter_version="test")
    run_id = repository.start_run(run_id="empty-template")
    payload = _load(EMPTY_FIXTURES[0])
    result = YahooRawResult(
        requested_at_utc="2026-09-27T20:00:00Z",
        fetched_at_utc="2026-09-27T20:00:00Z",
        provider_symbol="AEI",
        forecast_family=FAMILY_FISCAL_ESTIMATE,
        http_status=200,
        status=STATUS_SUCCESS_WITH_DATA,
        success=True,
        error_class=None,
        error_code=None,
        error_message=None,
        raw_payload=payload,
        raw_body=json.dumps(payload, separators=(",", ":")),
        raw_hash="empty-template-raw",
        attempt_count=1,
    )

    persisted = repository.record_fetch(run_id, result)
    repository.complete_run(run_id)

    assert persisted.status == STATUS_VALID_NO_DATA
    assert persisted.snapshot_id is None
    with connect_forecasts_db(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forecast_fetch").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM forecast_raw_evidence").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM forecast_snapshot").fetchone()[0] == 0
        assert connection.execute(
            "SELECT status FROM forecast_run WHERE run_id=?", (run_id,)
        ).fetchone()[0] == "SUCCESS"
