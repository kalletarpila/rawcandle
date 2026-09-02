from __future__ import annotations

from dataclasses import replace

from rawcandle.fundamentals.delta.context import (
    LifecycleObservation,
    ValuationObservation,
    calculate_lifecycle_context,
    calculate_valuation_diagnostic,
)
from rawcandle.fundamentals.delta.engine import DeltaStatus, FiscalObservation, Horizon
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_FP
from rawcandle.fundamentals.valuation.engine import MODEL_FINGERPRINT as VALUATION_FP


def fiscal(sequence: int) -> FiscalObservation:
    year, pos = divmod(sequence - 1, 4)
    return FiscalObservation(f"obs:{sequence}", 1, year, f"Q{pos+1}", sequence, f"{year}-{(pos+1)*3:02d}-28", f"{year}-{(pos+1)*3:02d}-29")


def lifecycle(sequence: int, state: str, *, status: str = "LIFECYCLE_READY", candidate=None):
    return LifecycleObservation(fiscal(sequence), sequence, LIFECYCLE_FP, status, state, state if status == "LIFECYCLE_READY" else None, state, candidate, int(candidate is not None))


def valuation(sequence: int, score: float, *, status="VALUATION_FULL"):
    return ValuationObservation(
        fiscal(sequence), sequence, VALUATION_FP, status, score,
        score * .4, score * .4, score * .2,
        fiscal(sequence).available_date, 10 + sequence, .1, .1, .1, 100, 90, f"fp:{sequence}",
    )


def by_horizon(result, horizon):
    return next(item for item in result.horizons if item.horizon == horizon)


def test_lifecycle_categorical_changes_streak_and_multiple_internal_changes():
    states = ["MATURE", "GROWTH", "MATURE", "MATURE", "MATURE"]
    history = [lifecycle(sequence, state) for sequence, state in zip(range(8096, 8101), states)]
    result = calculate_lifecycle_context(history[-1], history, source_fingerprint="source")
    assert by_horizon(result, Horizon.QOQ).state_changed is False
    assert by_horizon(result, Horizon.TWO_QUARTER).state_changed is False
    assert by_horizon(result, Horizon.YOY).state_changed is False
    assert result.latest_confirmed_transition_observation_id == "obs:8098"
    assert result.consecutive_classified_observations == 3
    assert not hasattr(result, "state_delta")


def test_lifecycle_not_ready_is_not_replaced_by_last_confirmed_state():
    history = [lifecycle(8100, "MATURE"), lifecycle(8101, "UNCLASSIFIED", status="LIFECYCLE_NOT_READY", candidate=None)]
    result = calculate_lifecycle_context(history[-1], history, source_fingerprint="source")
    assert result.current_final_state is None
    assert by_horizon(result, Horizon.QOQ).status == DeltaStatus.SOURCE_NOT_READY
    assert result.candidate_state is None


def test_lifecycle_horizon_change_flags_are_independent():
    states = ["DISTRESSED", "MATURE", "MATURE", "GROWTH", "MATURE"]
    history = [lifecycle(sequence, state) for sequence, state in zip(range(8096, 8101), states)]
    result = calculate_lifecycle_context(history[-1], history, source_fingerprint="source")
    assert by_horizon(result, Horizon.QOQ).state_changed is True
    assert by_horizon(result, Horizon.TWO_QUARTER).state_changed is False
    assert by_horizon(result, Horizon.YOY).state_changed is True


def test_valuation_three_horizons_reconcile_and_preserve_sources():
    history = [valuation(sequence, value) for sequence, value in zip(range(8096, 8101), [20, 25, 30, 35, 50])]
    result = calculate_valuation_diagnostic(history[-1], history, source_fingerprint="source")
    assert [item.score_change for item in result.horizons] == [15.0, 20.0, 30.0]
    assert all(item.status == DeltaStatus.READY and item.reconciliation_error == 0 for item in result.horizons)
    assert by_horizon(result, Horizon.QOQ).prior_result_id == 8099
    assert not hasattr(result, "fundamental_delta")


def test_valuation_requirements_model_status_price_and_reconciliation():
    prior, current = valuation(8100, 20), valuation(8101, 30)
    assert by_horizon(calculate_valuation_diagnostic(replace(current, valuation_status="VALUATION_NOT_READY"), [prior, replace(current, valuation_status="VALUATION_NOT_READY")], source_fingerprint="s"), Horizon.QOQ).status == DeltaStatus.ENDPOINT_NOT_COMPARABLE
    assert by_horizon(calculate_valuation_diagnostic(replace(current, model_fingerprint="wrong"), [prior, replace(current, model_fingerprint="wrong")], source_fingerprint="s"), Horizon.QOQ).status == DeltaStatus.MODEL_MISMATCH
    future_price = replace(current, price_date="2099-01-01")
    assert by_horizon(calculate_valuation_diagnostic(future_price, [prior, future_price], source_fingerprint="s"), Horizon.QOQ).status == DeltaStatus.AVAILABILITY_CHRONOLOGY_INVALID
    broken = replace(current, ebit_points=99)
    assert by_horizon(calculate_valuation_diagnostic(broken, [prior, broken], source_fingerprint="s"), Horizon.QOQ).reason_code == "VALUATION_RECONCILIATION_FAILED"


def test_valuation_floor_and_ceiling_changes_are_plain_signed_points():
    prior, current = valuation(8100, 0), valuation(8101, 100)
    item = by_horizon(calculate_valuation_diagnostic(current, [prior, current], source_fingerprint="s"), Horizon.QOQ)
    assert item.score_change == 100
    reverse = by_horizon(calculate_valuation_diagnostic(prior, [valuation(8099, 100), prior], source_fingerprint="s"), Horizon.QOQ)
    assert reverse.score_change == -100
