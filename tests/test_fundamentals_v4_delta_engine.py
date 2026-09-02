from __future__ import annotations

import math
import random
from dataclasses import replace

import pytest

from rawcandle.fundamentals.delta.engine import (
    COMPONENT_MAXIMA,
    MODEL_FINGERPRINT,
    ChainReason,
    DeltaStatus,
    FiscalObservation,
    Horizon,
    ScoreComponentObservation,
    ScoreObservation,
    build_fiscal_index,
    calculate_fundamental_delta,
    fiscal_sequence,
    resolve_horizon,
)
from rawcandle.fundamentals.score.engine import COMPONENTS, MODEL_FINGERPRINT as SCORE_FP, MODEL_VERSION as SCORE_VERSION


def fiscal(sequence: int, *, company_id: int = 1, available_shift: int = 0) -> FiscalObservation:
    year, position = divmod(sequence - 1, 4)
    quarter = f"Q{position + 1}"
    month = (position + 1) * 3
    return FiscalObservation(
        observation_id=f"obs:{company_id}:{sequence}", company_id=company_id,
        fiscal_year=year, fiscal_quarter=quarter, fiscal_sequence=sequence,
        period_end=f"{year:04d}-{month:02d}-28",
        available_date=f"{year:04d}-{month:02d}-{29 + available_shift:02d}",
    )


def score(sequence: int, total: float, *, status: str = "SCORE_FULL", company_id: int = 1) -> ScoreObservation:
    weights = [COMPONENT_MAXIMA[name] / 100.0 for name in COMPONENTS]
    components = tuple(
        ScoreComponentObservation(name, total * weight, COMPONENT_MAXIMA[name], "OBSERVED")
        for name, weight in zip(COMPONENTS, weights)
    )
    return ScoreObservation(
        fiscal(sequence, company_id=company_id), sequence, SCORE_VERSION, SCORE_FP,
        total, status, "TTM_READY", components,
    )


def result(history: list[ScoreObservation]):
    return calculate_fundamental_delta(history[-1], history, source_fingerprint="source")


def horizon(output, name: Horizon):
    return next(item for item in output.horizons if item.horizon == name)


def test_resolver_supports_year_end_noncalendar_and_53_week_periods():
    rows = [
        FiscalObservation("a", 1, 2024, "Q4", fiscal_sequence(2024, "Q4"), "2025-01-04", "2025-02-01"),
        FiscalObservation("b", 1, 2025, "Q1", fiscal_sequence(2025, "Q1"), "2025-04-05", "2025-05-01"),
    ]
    index = build_fiscal_index(rows)[1]
    resolved = resolve_horizon(rows[1], index, Horizon.QOQ)
    assert resolved.status == DeltaStatus.READY
    assert resolved.chain_observation_ids == ("a", "b")


@pytest.mark.parametrize(
    ("horizon_name", "sequences", "status", "reason"),
    [
        (Horizon.QOQ, [8100], DeltaStatus.LAG_ENDPOINT_MISSING, ChainReason.PREVIOUS_QUARTER_MISSING.value),
        (Horizon.TWO_QUARTER, [8099, 8100], DeltaStatus.LAG_ENDPOINT_MISSING, ChainReason.LAG2_MISSING.value),
        (Horizon.YOY, [8096, 8100], DeltaStatus.INVALID_FISCAL_CHAIN, ChainReason.INTERMEDIATE_FISCAL_OBSERVATION_MISSING.value),
        (Horizon.YOY, [8098, 8099, 8100], DeltaStatus.LAG_ENDPOINT_MISSING, ChainReason.LAG4_MISSING.value),
    ],
)
def test_resolver_missing_endpoint_and_chain(horizon_name, sequences, status, reason):
    rows = [fiscal(sequence) for sequence in sequences]
    resolved = resolve_horizon(rows[-1], build_fiscal_index(rows)[1], horizon_name)
    assert (resolved.status, resolved.reason_code) == (status, reason)


def test_duplicate_identity_rejected_and_input_order_independent():
    rows = [fiscal(sequence) for sequence in range(8096, 8101)]
    shuffled = rows[:]
    random.Random(7).shuffle(shuffled)
    assert build_fiscal_index(rows) == build_fiscal_index(shuffled)
    with pytest.raises(ValueError, match="DUPLICATE_FISCAL_IDENTITY"):
        build_fiscal_index(rows + [replace(rows[-1], observation_id="duplicate")])


def test_company_identity_not_ticker_controls_chain():
    first = fiscal(8100, company_id=1)
    other = fiscal(8101, company_id=2)
    index = build_fiscal_index([first, other])
    assert resolve_horizon(other, index[2], Horizon.QOQ).status == DeltaStatus.LAG_ENDPOINT_MISSING


def test_source_chronology_reversal_is_explicitly_not_ready():
    prior = replace(fiscal(8100), available_date="2026-07-01")
    current = replace(fiscal(8101), available_date="2026-06-01")
    resolved = resolve_horizon(current, build_fiscal_index([prior, current])[1], Horizon.QOQ)
    assert resolved.status == DeltaStatus.AVAILABILITY_CHRONOLOGY_INVALID


@pytest.mark.parametrize("values", [[10, 20, 30, 40, 50], [50, 40, 30, 20, 10], [25, 25, 25, 25, 25]])
def test_positive_negative_and_zero_all_horizons(values):
    output = result([score(8096 + index, value) for index, value in enumerate(values)])
    assert [item.status for item in output.horizons] == [DeltaStatus.READY] * 3
    assert horizon(output, Horizon.QOQ).delta_points == values[-1] - values[-2]
    assert horizon(output, Horizon.TWO_QUARTER).delta_points == values[-1] - values[-3]
    assert horizon(output, Horizon.YOY).delta_points == values[-1] - values[-5]
    for item in output.horizons:
        assert math.isclose(sum(component.delta_points for component in item.components), item.delta_points, abs_tol=1e-9)
        assert item.reconciliation_error == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (lambda row: replace(row, readiness_status="SCORE_LIMITED"), DeltaStatus.SOURCE_NOT_READY),
        (lambda row: replace(row, ttm_readiness_status="TTM_NOT_READY"), DeltaStatus.SOURCE_NOT_READY),
        (lambda row: replace(row, model_fingerprint="wrong"), DeltaStatus.MODEL_MISMATCH),
        (lambda row: replace(row, reweighted=True), DeltaStatus.ENDPOINT_NOT_COMPARABLE),
        (lambda row: replace(row, total_score=float("nan")), DeltaStatus.INVALID_VALUE),
        (lambda row: replace(row, total_score=True), DeltaStatus.INVALID_VALUE),
        (lambda row: replace(row, components=row.components[:-1]), DeltaStatus.ENDPOINT_NOT_COMPARABLE),
    ],
)
def test_strict_total_endpoint_requirements(mutation, expected):
    history = [score(8100, 40), mutation(score(8101, 50))]
    assert horizon(result(history), Horizon.QOQ).status == expected


def test_prior_limited_blocks_total_but_observed_component_delta_remains_ready():
    prior = score(8100, 40, status="SCORE_LIMITED")
    current = score(8101, 50)
    item = horizon(result([prior, current]), Horizon.QOQ)
    assert item.status == DeltaStatus.ENDPOINT_NOT_COMPARABLE
    assert all(component.status == DeltaStatus.READY for component in item.components)


def test_component_missing_is_not_zero_and_maximum_mismatch_is_rejected():
    prior, current = score(8100, 40), score(8101, 40)
    altered = list(current.components)
    altered[0] = replace(altered[0], value_status="MISSING", points=None)
    item = horizon(result([prior, replace(current, readiness_status="SCORE_LIMITED", components=tuple(altered))]), Horizon.QOQ)
    assert item.components[0].delta_points is None
    assert item.components[0].status == DeltaStatus.COMPONENT_NOT_COMPARABLE
    assert item.components[1].delta_points == 0.0
    wrong_max = list(current.components)
    wrong_max[0] = replace(wrong_max[0], maximum_points=999)
    item = horizon(result([prior, replace(current, components=tuple(wrong_max))]), Horizon.QOQ)
    assert item.components[0].reason_code == "COMPONENT_MAXIMUM_MISMATCH"


def test_component_identifier_change_is_not_comparable():
    prior, current = score(8100, 40), score(8101, 50)
    changed = list(current.components)
    changed[0] = replace(changed[0], component_name="RENAMED_COMPONENT")
    item = horizon(result([prior, replace(current, readiness_status="SCORE_LIMITED", components=tuple(changed))]), Horizon.QOQ)
    assert item.components[0].status == DeltaStatus.COMPONENT_NOT_COMPARABLE
    assert item.components[0].delta_points is None


def test_component_boolean_is_invalid_and_reconciliation_tolerance_is_absolute_1e_9():
    prior, current = score(8100, 40), score(8101, 50)
    boolean_components = list(current.components)
    boolean_components[0] = replace(boolean_components[0], points=True)
    item = horizon(result([prior, replace(current, components=tuple(boolean_components))]), Horizon.QOQ)
    assert item.components[0].status == DeltaStatus.INVALID_VALUE
    within = list(current.components)
    within[-1] = replace(within[-1], points=float(within[-1].points) + 5e-10)
    assert horizon(result([prior, replace(current, components=tuple(within))]), Horizon.QOQ).status == DeltaStatus.READY
    outside = list(current.components)
    outside[-1] = replace(outside[-1], points=float(outside[-1].points) + 2e-9)
    assert horizon(result([prior, replace(current, components=tuple(outside))]), Horizon.QOQ).status == DeltaStatus.ENDPOINT_NOT_COMPARABLE


def test_trajectory_delta_is_only_component_point_change_and_replay_is_deterministic():
    history = [score(sequence, value) for sequence, value in zip(range(8096, 8101), [20, 30, 40, 45, 60])]
    first = result(history)
    second = calculate_fundamental_delta(history[-1], list(reversed(history)), source_fingerprint="source")
    assert first.to_json() == second.to_json()
    trajectory = next(component for component in horizon(first, Horizon.TWO_QUARTER).components if component.component_name == "FUNDAMENTAL_TRAJECTORY")
    assert trajectory.delta_points == 2.0
    assert first.model_fingerprint == MODEL_FINGERPRINT
