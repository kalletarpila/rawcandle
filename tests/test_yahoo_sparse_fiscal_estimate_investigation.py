from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from rawcandle.forecasts.contracts import (
    EARNINGS_TREND_CONTRACT_VERSION,
    FAMILY_FISCAL_ESTIMATE,
    STATUS_MALFORMED,
    STATUS_SUCCESS_WITH_DATA,
    STATUS_VALID_NO_DATA,
    ForecastContractError,
    _is_empty_earnings_trend_row,
    canonicalize_earnings_trend,
    parse_payload,
)


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
def test_mixed_usable_and_incomplete_empty_payload_is_not_no_data_or_v1_success(
    name: str, missing_horizons: list[str], usable_horizons: list[str]
) -> None:
    payload = _load(name)
    parsed = parse_payload(FAMILY_FISCAL_ESTIMATE, payload)

    assert parsed.status == STATUS_MALFORMED
    assert parsed.status not in {STATUS_VALID_NO_DATA, STATUS_SUCCESS_WITH_DATA}
    assert parsed.forecast is None
    with pytest.raises(ForecastContractError, match="period and endDate"):
        canonicalize_earnings_trend(payload)


def test_unknown_field_on_incomplete_row_remains_raw_visible_and_malformed() -> None:
    payload = copy.deepcopy(_load(SPARSE_SHAPES[0][0]))
    row = _trend(payload)[0]
    row["futureProviderField"] = {"raw": 7}

    parsed = parse_payload(FAMILY_FISCAL_ESTIMATE, payload)

    assert row["futureProviderField"] == {"raw": 7}
    assert parsed.status == STATUS_MALFORMED


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
