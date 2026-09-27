from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tests.yahoo_forecast_contract import (
    canonical_state,
    canonicalize,
    classify_result,
    semantic_hash,
)


FIXTURES = Path(__file__).parent / "fixtures" / "forecasts" / "yahoo"


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_real_success_fixture_preserves_distinct_growth_and_field_states() -> None:
    payload = load_fixture("success_with_data_aapl.real_compact.json")

    canonical = canonicalize(payload)
    first = canonical["rows"][0]

    assert canonical["defaultMethodology"] == {
        "state": "TEXT_VALUE",
        "value": "gaap",
    }
    assert first["topLevelGrowth"]["value"] == "0.0709"
    assert first["earningsEstimate"]["growth"]["value"] == "0.0689"
    assert first["revenueEstimate"]["growth"]["value"] == "0.1089"
    assert first["epsRevisions"]["downLast90days"] == {
        "state": "EMPTY_OBJECT"
    }
    assert first["epsRevisions"]["downLast7Days"] == {
        "state": "NUMERIC_ZERO",
        "value": "0",
    }


def test_success_fixture_classifies_as_success_with_data() -> None:
    payload = load_fixture("success_with_data_aapl.real_compact.json")

    assert classify_result({"transport": {"http_status": 200}, "payload": payload}) == (
        "SUCCESS_WITH_DATA"
    )


def test_formatting_and_json_key_order_do_not_change_semantic_hash() -> None:
    payload = load_fixture("success_with_data_aapl.real_compact.json")
    changed = copy.deepcopy(payload)
    module = changed["quoteSummary"]["result"][0]["earningsTrend"]
    module["maxAge"] = 999
    first = module["trend"][0]
    first["maxAge"] = 999
    first["growth"]["fmt"] = "FORMATTING-ONLY"
    first["revenueEstimate"]["avg"]["longFmt"] = "FORMATTING-ONLY"

    assert semantic_hash(changed) == semantic_hash(payload)


def test_semantic_raw_change_changes_hash() -> None:
    payload = load_fixture("success_with_data_aapl.real_compact.json")
    changed = copy.deepcopy(payload)
    changed["quoteSummary"]["result"][0]["earningsTrend"]["trend"][0][
        "earningsEstimate"
    ]["avg"]["raw"] = 1.98

    assert semantic_hash(changed) != semantic_hash(payload)


def test_adbe_fixture_preserves_order_and_duplicate_quarter_end_date() -> None:
    payload = load_fixture("ambiguous_target_adbe.real_compact.json")
    rows = canonicalize(payload)["rows"]

    assert [row["providerHorizon"] for row in rows] == ["0q", "+1q", "0y", "+1y"]
    assert rows[0]["providerEndDate"] == rows[1]["providerEndDate"]
    assert rows[0]["occurrenceIndex"] == 0
    assert rows[1]["occurrenceIndex"] == 1


def test_sparse_fixture_keeps_eps_and_revenue_analyst_counts_separate() -> None:
    payload = load_fixture("success_sparse_bb.real_compact.json")
    row = canonicalize(payload)["rows"][0]

    assert row["earningsEstimate"]["numberOfAnalysts"]["value"] == "6"
    assert row["revenueEstimate"]["numberOfAnalysts"]["value"] == "4"


def test_strict_field_state_contract() -> None:
    fixture = load_fixture("field_states.synthetic.json")

    assert canonical_state()["state"] == "FIELD_ABSENT"
    assert canonical_state(fixture["EMPTY_OBJECT"]["field"])["state"] == "EMPTY_OBJECT"
    assert canonical_state(fixture["EXPLICIT_NULL"]["field"])["state"] == "EXPLICIT_NULL"
    assert canonical_state(fixture["NUMERIC_ZERO"]["field"])["state"] == "NUMERIC_ZERO"
    assert canonical_state(fixture["NUMERIC_VALUE"]["field"])["state"] == "NUMERIC_VALUE"


@pytest.mark.parametrize(
    "case_name",
    [
        "VALID_NO_DATA",
        "PROVIDER_SYMBOL_UNAVAILABLE",
        "RATE_LIMITED",
        "TRANSIENT_5XX",
        "MALFORMED_OR_SCHEMA_MISMATCH",
    ],
)
def test_result_classification_contract(case_name: str) -> None:
    fixture = load_fixture("result_cases.synthetic.json")
    case = next(item for item in fixture["cases"] if item["name"] == case_name)

    assert classify_result(case) == case_name


def test_malformed_date_is_schema_mismatch_at_canonicalization_boundary() -> None:
    payload = load_fixture("success_with_data_aapl.real_compact.json")
    payload["quoteSummary"]["result"][0]["earningsTrend"]["trend"][0][
        "endDate"
    ] = "09/30/2026"

    with pytest.raises(ValueError):
        canonicalize(payload)
