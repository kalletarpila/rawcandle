from __future__ import annotations

import math
from dataclasses import replace
from datetime import date

import pytest

from rawcandle.fundamentals.operating_income_v2 import valuation
from rawcandle.fundamentals.relative_position.engine import EcosystemMembership
from rawcandle.fundamentals.relative_valuation.engine import (
    MODEL_FINGERPRINT,
    ComponentHistoryStatus,
    HistoricalEndpoint,
    OwnHistoryStatus,
    RelativeValuationInput,
    calculate_current_price_valuation,
    calculate_own_history,
    calculate_relative_valuation,
    historical_percentile,
    select_history,
    subtract_calendar_years,
)


def endpoint(sequence: int, value: float | None = 0.1, *, available: str | None = None) -> HistoricalEndpoint:
    return HistoricalEndpoint(
        fiscal_sequence=sequence,
        fiscal_year=2020 + sequence // 4,
        fiscal_quarter=f"Q{sequence % 4 + 1}",
        available_date=available or f"202{2 + sequence // 4}-{sequence % 4 * 3 + 1:02d}-15",
        valuation_status="VALUATION_FULL",
        market_cap=100.0,
        enterprise_value=100.0,
        ttm_operating_income=None if value is None else value * 100,
        ttm_free_cashflow=None if value is None else value * 100,
        ttm_reported_common_earnings=None if value is None else value * 100,
    )


def current(status: str = "VALUATION_FULL", value: object = 0.1) -> dict[str, object]:
    return {
        "valuation_status": status,
        "operating_income_yield": value,
        "fcf_yield": value,
        "earnings_yield": value,
    }


def observation(company_id: int = 1, *, yield_value: float = 0.05) -> valuation.ValuationObservation:
    return valuation.ValuationObservation(
        company_id=company_id,
        security_id=company_id,
        ticker=f"T{company_id}",
        fiscal_year=2026,
        fiscal_quarter="Q2",
        quarter_id=company_id,
        period_end="2026-06-30",
        fundamental_available_date="2026-08-01",
        ttm_readiness_status="TTM_READY",
        ttm_blocker_codes=(),
        ttm_operating_income=yield_value * 100,
        ttm_free_cashflow=yield_value * 100,
        ttm_net_income_common=yield_value * 100,
        net_income_common_4q_ready=True,
        shares_outstanding=100.0,
        cash=0.0,
        total_debt=0.0,
        sector="Technology",
        industry="Software - Application",
    )


def price(day: str, close: float = 1.0, *, complete: bool = True) -> valuation.PriceBar:
    return valuation.PriceBar(day, close if complete else None, close, close, close)


def model_input(company_id: int, *, memberships=(), sector="Technology", industry="Software - Application") -> RelativeValuationInput:
    history = tuple(endpoint(index, 0.01 * index, available=f"202{2 + (index - 1) // 4}-{((index - 1) % 4) * 3 + 1:02d}-15") for index in range(1, 13))
    return RelativeValuationInput(
        company_id=company_id,
        security_id=company_id,
        ticker=f"T{company_id}",
        sector=sector,
        industry=industry,
        ecosystem_memberships=memberships,
        endpoint_available_date="2026-08-01",
        current_fresh=True,
        valuation_observation=observation(company_id, yield_value=0.05 + company_id / 10000),
        price_bars=(price("2026-09-01"),),
        filing_valuation={"quarter_id": company_id, "total_valuation_score": 10.0},
        filing_peer_results=(),
        history=history,
    )


def test_model_identity_is_stable_and_separate() -> None:
    assert len(MODEL_FINGERPRINT) == 64
    assert MODEL_FINGERPRINT != valuation.MODEL_FINGERPRINT


def test_current_price_boundaries_and_bad_bars() -> None:
    source = observation()
    assert calculate_current_price_valuation(source, (price("2026-09-08"),), as_of_date="2026-09-08")["valuation_status"] == "VALUATION_FULL"
    assert calculate_current_price_valuation(source, (price("2026-09-01"),), as_of_date="2026-09-08")["valuation_status"] == "VALUATION_FULL"
    assert calculate_current_price_valuation(source, (price("2026-08-31"),), as_of_date="2026-09-08")["reason_code"] == "CURRENT_PRICE_FALLBACK_TOO_OLD"
    assert calculate_current_price_valuation(source, (price("2026-09-09"),), as_of_date="2026-09-08")["reason_code"] == "PRICE_MISSING"
    assert calculate_current_price_valuation(source, (price("2026-09-08", complete=False),), as_of_date="2026-09-08")["reason_code"] == "PRICE_MISSING"
    assert calculate_current_price_valuation(source, (), as_of_date="2026-09-08")["reason_code"] == "PRICE_MISSING"
    assert calculate_current_price_valuation(source, (price("2026-09-08", 0.0),), as_of_date="2026-09-08")["reason_code"] == "PRICE_MISSING"


def test_history_window_boundary_cap_gaps_and_leap_day() -> None:
    assert subtract_calendar_years(date(2024, 2, 29), 5).isoformat() == "2019-02-28"
    rows = [endpoint(index, available=f"2021-09-{7 + index:02d}") for index in range(1, 23)]
    selected, start, gaps = select_history(rows, as_of_date="2026-09-08")
    assert start == "2021-09-08"
    assert len(selected) == 20
    assert selected[0].fiscal_sequence == 3
    assert gaps == 0
    gapped = (endpoint(1, available="2026-01-01"), endpoint(3, available="2026-07-01"))
    assert select_history(gapped, as_of_date="2026-09-08")[2] == 1


def test_historical_percentile_ties_and_extremes() -> None:
    assert historical_percentile([2.0, 3.0], 1.0) == 0.0
    assert historical_percentile([1.0, 2.0], 3.0) == 100.0
    assert historical_percentile([1.0, 2.0, 3.0], 2.0) == 50.0
    assert historical_percentile([2.0] * 12, 2.0) == 50.0


def test_history_records_component_observation_bounds_and_even_median() -> None:
    rows = tuple(
        endpoint(index, value, available=available)
        for index, value, available in (
            (1, 0.01, "2022-01-15"),
            (2, 0.03, "2022-04-15"),
            (3, 0.05, "2022-07-15"),
            (4, 0.07, "2022-10-15"),
            (5, 0.09, "2023-01-15"),
            (6, 0.11, "2023-04-15"),
            (7, 0.13, "2023-07-15"),
            (8, 0.15, "2023-10-15"),
        )
    )
    result = calculate_own_history(
        current(value=0.08), rows, as_of_date="2026-09-08", current_fresh=True
    )
    component = result.components[0]
    assert component.component_observation_count == 8
    assert component.component_first_observation_date == "2022-01-15"
    assert component.component_last_observation_date == "2023-10-15"
    assert component.historical_median_positive_yield == pytest.approx(0.08)


@pytest.mark.parametrize(
    ("count", "status", "emitted"),
    [
        (7, OwnHistoryStatus.INSUFFICIENT, False),
        (8, OwnHistoryStatus.LIMITED, True),
        (11, OwnHistoryStatus.LIMITED, True),
        (12, OwnHistoryStatus.READY, True),
    ],
)
def test_history_readiness_boundaries(count, status, emitted) -> None:
    result = calculate_own_history(current(), tuple(endpoint(index) for index in range(count)), as_of_date="2026-09-08", current_fresh=True)
    assert result.status == status.value
    assert (result.percentile is not None) is emitted


@pytest.mark.parametrize(
    ("value", "component_status", "aggregate"),
    [
        (0.0, ComponentHistoryStatus.CURRENT_YIELD_NONPOSITIVE, OwnHistoryStatus.CURRENT_YIELD_NOT_COMPARABLE),
        (-0.1, ComponentHistoryStatus.CURRENT_YIELD_NONPOSITIVE, OwnHistoryStatus.CURRENT_YIELD_NOT_COMPARABLE),
        (None, ComponentHistoryStatus.CURRENT_COMPONENT_MISSING, OwnHistoryStatus.CURRENT_YIELD_NOT_COMPARABLE),
        (math.nan, ComponentHistoryStatus.CURRENT_COMPONENT_NONFINITE, OwnHistoryStatus.CURRENT_YIELD_NOT_COMPARABLE),
    ],
)
def test_current_component_invalid_states_are_not_reweighted(value, component_status, aggregate) -> None:
    payload = current()
    payload["fcf_yield"] = value
    result = calculate_own_history(payload, tuple(endpoint(index) for index in range(12)), as_of_date="2026-09-08", current_fresh=True)
    fcf = next(row for row in result.components if row.component == "FCF_YIELD")
    assert fcf.component_history_status == component_status.value
    assert result.status == aggregate.value
    assert result.percentile is None


def test_history_exclusions_independent_sets_median_and_reconciliation() -> None:
    rows = []
    for index in range(12):
        row = endpoint(index, 0.01 * (index + 1), available=f"202{3 + index // 4}-{index % 4 * 3 + 1:02d}-15")
        if index == 0:
            row = replace(row, ttm_free_cashflow=0.0)
        if index == 1:
            row = replace(row, ttm_reported_common_earnings=None)
        rows.append(row)
    result = calculate_own_history(current(value=0.2), rows, as_of_date="2026-09-08", current_fresh=True)
    counts = {row.component: row.positive_history_count for row in result.components}
    assert counts == {"OPERATING_YIELD": 12, "FCF_YIELD": 11, "REPORTED_EARNINGS_YIELD": 11}
    assert result.status == OwnHistoryStatus.LIMITED.value
    assert result.percentile == pytest.approx(sum({"OPERATING_YIELD": 0.4, "FCF_YIELD": 0.4, "REPORTED_EARNINGS_YIELD": 0.2}[row.component] * row.historical_percentile for row in result.components))
    assert next(row for row in result.components if row.component == "FCF_YIELD").nonpositive_history_count == 1
    assert next(row for row in result.components if row.component == "REPORTED_EARNINGS_YIELD").missing_or_invalid_history_count == 1


def test_not_ready_not_applicable_and_stale_precedence() -> None:
    history = tuple(endpoint(index) for index in range(12))
    assert calculate_own_history(current("VALUATION_NOT_APPLICABLE"), history, as_of_date="2026-09-08", current_fresh=True).status == "NOT_APPLICABLE"
    assert calculate_own_history(current("VALUATION_NOT_READY"), history, as_of_date="2026-09-08", current_fresh=True).status == "CURRENT_VALUATION_NOT_READY"
    assert calculate_own_history(current(), history, as_of_date="2026-09-08", current_fresh=False).status == "CURRENT_VALUATION_NOT_READY"


@pytest.mark.parametrize(("count", "scope", "expected"), [(1, "UNIVERSE", "PEER_GROUP_TOO_SMALL"), (2, "UNIVERSE", "RELATIVE_POSITION_READY"), (19, "SECTOR", "PEER_GROUP_TOO_SMALL"), (20, "SECTOR", "RELATIVE_POSITION_READY"), (9, "INDUSTRY", "PEER_GROUP_TOO_SMALL"), (10, "INDUSTRY", "RELATIVE_POSITION_READY")])
def test_peer_minimums(count, scope, expected) -> None:
    result = calculate_relative_valuation([model_input(index) for index in range(1, count + 1)], as_of_date="2026-09-08", classification_fingerprint="c", taxonomy_fingerprint="t")
    rows = [row for company in result.companies for row in company.current_peer_results if row["peer_scope"] == scope]
    assert len(rows) == count
    assert {row["status"] for row in rows} == {expected}


@pytest.mark.parametrize(("count", "expected"), [(19, "PEER_GROUP_TOO_SMALL"), (20, "RELATIVE_POSITION_READY")])
def test_ecosystem_minimum_and_duplicate_membership(count, expected) -> None:
    membership = (EcosystemMembership("ECO", "CORE", "1"), EcosystemMembership("ECO", "EXTENDED", "2"))
    result = calculate_relative_valuation([model_input(index, memberships=membership) for index in range(1, count + 1)], as_of_date="2026-09-08", classification_fingerprint="c", taxonomy_fingerprint="t")
    rows = [row for company in result.companies for row in company.current_peer_results if row["peer_scope"] == "ECOSYSTEM"]
    assert len(rows) == count
    assert {row["peer_count"] for row in rows} == {count}
    assert {row["status"] for row in rows} == {expected}


def test_missing_classification_nonmember_ties_and_dual_replay() -> None:
    inputs = [model_input(1, sector=None, industry=None), model_input(2)]
    first = calculate_relative_valuation(inputs, as_of_date="2026-09-08", classification_fingerprint="c", taxonomy_fingerprint="t")
    second = calculate_relative_valuation(list(reversed(inputs)), as_of_date="2026-09-08", classification_fingerprint="c", taxonomy_fingerprint="t")
    assert first.to_json() == second.to_json()
    company = first.companies[0]
    assert all(isinstance(row["peer_scope"], str) for row in company.current_peer_results)
    assert all(row["model_fingerprint"] == MODEL_FINGERPRINT for row in company.current_peer_results)
    statuses = {row["peer_scope"]: row["status"] for row in company.current_peer_coverage}
    assert statuses["SECTOR"] == "PEER_CLASSIFICATION_MISSING"
    assert statuses["INDUSTRY"] == "PEER_CLASSIFICATION_MISSING"
    assert statuses["ECOSYSTEM"] == "NOT_ECOSYSTEM_MEMBER"


@pytest.mark.parametrize(("yield_value", "expected_score"), [(0.0, 0.0), (1.0, 100.0)])
def test_peer_exact_score_extremes_and_all_equal_midrank(yield_value, expected_score) -> None:
    inputs = []
    for company_id in (1, 2):
        item = model_input(company_id)
        item = replace(
            item,
            valuation_observation=observation(company_id, yield_value=yield_value),
        )
        inputs.append(item)
    result = calculate_relative_valuation(
        inputs,
        as_of_date="2026-09-08",
        classification_fingerprint="c",
        taxonomy_fingerprint="t",
    )
    universe = [
        row
        for company in result.companies
        for row in company.current_peer_results
        if row["peer_scope"] == "UNIVERSE"
    ]
    assert {row["score"] for row in universe} == {expected_score}
    assert {row["percentile"] for row in universe} == {50.0}
    assert {row["tie_count"] for row in universe} == {2}


def test_small_peer_group_does_not_fall_back_and_unresolved_identity_is_explicit() -> None:
    small = calculate_relative_valuation(
        [model_input(index) for index in range(1, 20)],
        as_of_date="2026-09-08",
        classification_fingerprint="c",
        taxonomy_fingerprint="t",
    )
    first = small.companies[0]
    assert next(row for row in first.current_peer_results if row["peer_scope"] == "UNIVERSE")["status"] == "RELATIVE_POSITION_READY"
    sector = next(row for row in first.current_peer_results if row["peer_scope"] == "SECTOR")
    assert sector["status"] == "PEER_GROUP_TOO_SMALL"
    assert sector["percentile"] is None
    assert sector["peer_count"] == 19

    unresolved = model_input(1)
    unresolved = replace(
        unresolved,
        company_id=None,
        security_id=None,
        ticker=None,
        valuation_observation=replace(
            unresolved.valuation_observation,
            company_id=None,
            security_id=None,
            ticker=None,
        ),
    )
    result = calculate_relative_valuation(
        [unresolved],
        as_of_date="2026-09-08",
        classification_fingerprint="c",
        taxonomy_fingerprint="t",
    )
    assert result.companies[0].current_valuation["valuation_status"] == "VALUATION_NOT_READY"
    assert {
        row["status"] for row in result.companies[0].current_peer_coverage
    } == {"IDENTITY_MAPPING_UNRESOLVED"}
