from __future__ import annotations

import dataclasses
import inspect
from datetime import date, timedelta
from decimal import Decimal

import pytest

from rawcandle.fundamentals.lifecycle import engine


AUTO = object()


def observation(
    *,
    g: float = 0.0,
    m: float = 0.10,
    dm: float = 0.0,
    f: float | None = 0.10,
    current_revenue: float | None | object = AUTO,
    current_ebit: float | None | object = AUTO,
    lag_revenue: float | None | object = AUTO,
    lag_ebit: float | None | object = AUTO,
    chain_valid: bool = True,
    core_ready: bool = True,
    quarterly_revenues: tuple[float | None, ...] = (25.0, 25.0, 25.0, 25.0),
    available_date: str | None = "2026-05-01",
    quarter_id: int = 1,
) -> engine.LifecycleObservation:
    if current_revenue is AUTO:
        lag_revenue = 100.0 if lag_revenue is AUTO else lag_revenue
        current_revenue = (
            float(Decimal(str(lag_revenue)) * (Decimal(1) + Decimal(str(g))))
            if isinstance(lag_revenue, (int, float))
            else 100.0
        )
    if current_ebit is AUTO and current_revenue is not None:
        current_ebit = float(Decimal(str(current_revenue)) * Decimal(str(m)))
    if lag_revenue is AUTO and current_revenue is not None and current_revenue > 0 and g > -1:
        lag_revenue = current_revenue / (1.0 + g)
    if lag_ebit is AUTO and isinstance(lag_revenue, (int, float)):
        lag_ebit = float(Decimal(str(lag_revenue)) * (Decimal(str(m)) - Decimal(str(dm))))
    current_fcf = (
        None
        if f is None or current_revenue is None
        else float(Decimal(str(current_revenue)) * Decimal(str(f)))
    )
    return engine.LifecycleObservation(
        company_id=1,
        security_id=1,
        endpoint_quarter_id=quarter_id,
        endpoint_fiscal_year=2026,
        endpoint_fiscal_quarter="Q1",
        period_end="2026-03-31",
        source_available_date=available_date,
        source_data_version=f"SOURCE_{quarter_id}",
        core_ttm_ready=core_ready,
        ttm_revenue=current_revenue,
        ttm_ebit=current_ebit if isinstance(current_ebit, (int, float)) else None,
        ttm_free_cashflow=current_fcf,
        lag4_ttm_revenue=lag_revenue if isinstance(lag_revenue, (int, float)) else None,
        lag4_ttm_ebit=lag_ebit if isinstance(lag_ebit, (int, float)) else None,
        lag4_chain_valid=chain_valid,
        input_quarter_revenues=quarterly_revenues,
    )


def classify(**kwargs: object) -> engine.RawLifecycleResult:
    return engine.classify_raw_state(observation(**kwargs))


def assert_state(expected: engine.LifecycleState, **kwargs: object) -> engine.RawLifecycleResult:
    result = classify(**kwargs)
    assert result.raw_state is expected
    assert result.lifecycle_status is engine.LifecycleStatus.READY
    return result


def test_pre_revenue_startup_requires_four_exact_zero_quarters_and_negative_ebit_and_fcf() -> None:
    row = observation(
        current_revenue=0.0,
        current_ebit=-10.0,
        f=None,
        quarterly_revenues=(0.0, 0.0, 0.0, 0.0),
    )
    # FCF is set explicitly because a zero revenue cannot derive it from a margin.
    result = engine.classify_raw_state(dataclasses.replace(row, ttm_free_cashflow=-8.0))
    assert result.raw_state is engine.LifecycleState.STARTUP
    assert result.startup_profile is engine.StartupProfile.PRE_REVENUE
    assert result.metrics == engine.LifecycleMetrics(None, None, None, None)


@pytest.mark.parametrize(
    ("revenues", "ebit", "fcf", "reason"),
    [
        ((0.0, 0.0, 0.0, 1.0), -1.0, -1.0, engine.LifecycleReason.ZERO_REVENUE_PRE_REVENUE_CONDITIONS_NOT_MET),
        ((0.0, 0.0, 0.0, -1.0), -1.0, -1.0, engine.LifecycleReason.ZERO_REVENUE_PRE_REVENUE_CONDITIONS_NOT_MET),
        ((0.0, 0.0, 0.0, None), -1.0, -1.0, engine.LifecycleReason.PRE_REVENUE_QUARTER_REVENUE_MISSING),
        ((0.0, 0.0, 0.0), -1.0, -1.0, engine.LifecycleReason.PRE_REVENUE_QUARTER_COUNT_INVALID),
        ((0.0, 0.0, 0.0, 0.0), 0.0, -1.0, engine.LifecycleReason.ZERO_REVENUE_PRE_REVENUE_CONDITIONS_NOT_MET),
        ((0.0, 0.0, 0.0, 0.0), -1.0, 0.0, engine.LifecycleReason.ZERO_REVENUE_PRE_REVENUE_CONDITIONS_NOT_MET),
    ],
)
def test_zero_revenue_pre_revenue_failures_are_unclassified(
    revenues: tuple[float | None, ...], ebit: float, fcf: float, reason: engine.LifecycleReason
) -> None:
    row = observation(current_revenue=0.0, current_ebit=ebit, f=None, quarterly_revenues=revenues)
    result = engine.classify_raw_state(dataclasses.replace(row, ttm_free_cashflow=fcf))
    assert result.raw_state is engine.LifecycleState.UNCLASSIFIED
    assert result.lifecycle_status is engine.LifecycleStatus.NOT_READY
    assert result.reason_code is reason


@pytest.mark.parametrize(
    ("m", "f", "expected"),
    [
        (-0.201, -0.201, engine.LifecycleState.DISTRESSED),
        (-0.20, -0.201, engine.LifecycleState.STRUGGLING),
        (-0.201, -0.20, engine.LifecycleState.STRUGGLING),
        (-0.201, 0.01, engine.LifecycleState.STRUGGLING),
        (0.01, -0.201, engine.LifecycleState.STRUGGLING),
    ],
)
def test_distressed_strict_boundaries(m: float, f: float, expected: engine.LifecycleState) -> None:
    assert_state(expected, m=m, f=f)


def test_distressed_needs_no_lag4_and_wins_startup_overlap() -> None:
    no_history = assert_state(
        engine.LifecycleState.DISTRESSED,
        m=-0.25,
        f=-0.30,
        chain_valid=False,
        lag_revenue=None,
        lag_ebit=None,
    )
    assert no_history.metrics.revenue_growth_yoy_ttm is None
    assert_state(engine.LifecycleState.DISTRESSED, g=0.40, m=-0.25, dm=0.0, f=-0.30)


@pytest.mark.parametrize(
    ("g", "m", "f", "expected"),
    [
        (0.30, -0.10, -0.05, engine.LifecycleState.GROWTH),
        (0.301, -0.10, -0.05, engine.LifecycleState.STARTUP),
        (0.40, -0.05, -0.05, engine.LifecycleState.GROWTH),
        (0.40, -0.10, 0.0, engine.LifecycleState.GROWTH),
    ],
)
def test_revenue_generating_startup_boundaries(g: float, m: float, f: float, expected: engine.LifecycleState) -> None:
    result = assert_state(expected, g=g, m=m, dm=0.0, f=f)
    if expected is engine.LifecycleState.STARTUP:
        assert result.startup_profile is engine.StartupProfile.REVENUE_GENERATING


def test_startup_wins_growth_overlap_and_missing_fcf_can_still_be_growth() -> None:
    assert_state(engine.LifecycleState.STARTUP, g=0.40, m=-0.10, dm=0.0, f=-0.05)
    result = assert_state(engine.LifecycleState.GROWTH, g=0.40, m=-0.10, dm=0.0, f=None)
    assert result.metrics.fcf_margin_ttm is None


def test_scaling_has_priority_over_growth() -> None:
    assert_state(engine.LifecycleState.SCALING, g=0.25, m=0.05, dm=0.02, f=0.05)


@pytest.mark.parametrize(
    ("g", "m", "dm", "expected"),
    [
        (0.10, 0.05, 0.01, engine.LifecycleState.TRANSITION),
        (0.11, 0.0, 0.01, engine.LifecycleState.SCALING),
        (0.11, 0.05, 0.0, engine.LifecycleState.TRANSITION),
        (0.20, -0.01, 0.0, engine.LifecycleState.STRUGGLING),
        (0.21, 0.10, 0.0, engine.LifecycleState.TRANSITION),
        (0.21, 0.05, -0.05, engine.LifecycleState.GROWTH),
    ],
)
def test_scaling_and_growth_exact_boundaries(
    g: float, m: float, dm: float, expected: engine.LifecycleState
) -> None:
    assert_state(expected, g=g, m=m, dm=dm, f=0.10)


def test_scaling_and_growth_do_not_require_fcf_but_do_require_valid_lag4() -> None:
    assert_state(engine.LifecycleState.SCALING, g=0.15, m=0.05, dm=0.01, f=None)
    assert_state(engine.LifecycleState.GROWTH, g=0.25, m=-0.01, dm=0.0, f=None)
    result = classify(g=0.25, m=-0.01, dm=0.0, f=0.10, chain_valid=False)
    assert result.raw_state is engine.LifecycleState.UNCLASSIFIED
    assert result.reason_code is engine.LifecycleReason.FISCAL_CHAIN_INVALID


def test_mature_inclusive_boundaries_and_scaling_priority() -> None:
    assert_state(engine.LifecycleState.MATURE, g=-0.05, m=0.15, dm=-0.05, f=0.05)
    assert_state(engine.LifecycleState.SCALING, g=0.20, m=0.20, dm=0.01, f=0.10)


@pytest.mark.parametrize(
    ("g", "m", "dm", "f"),
    [
        (-0.050001, 0.15, -0.05, 0.05),
        (-0.05, 0.149999, -0.05, 0.05),
        (-0.05, 0.15, -0.050001, 0.05),
        (-0.05, 0.15, -0.05, 0.049999),
    ],
)
def test_mature_condition_below_boundary_does_not_classify_mature(g: float, m: float, dm: float, f: float) -> None:
    assert classify(g=g, m=m, dm=dm, f=f).raw_state is not engine.LifecycleState.MATURE


def test_mature_missing_growth_or_margin_direction_is_unclassified() -> None:
    missing_g = classify(m=0.20, f=0.10, lag_revenue=None, lag_ebit=None, chain_valid=False)
    assert missing_g.raw_state is engine.LifecycleState.UNCLASSIFIED
    missing_dm = classify(g=0.0, m=0.20, f=0.10, lag_ebit=float("nan"))
    assert missing_dm.raw_state is engine.LifecycleState.UNCLASSIFIED
    assert missing_dm.reason_code is engine.LifecycleReason.LAG4_EBIT_INVALID


@pytest.mark.parametrize(
    ("g", "dm"),
    [(-0.050001, 0.0), (0.0, -0.050001)],
)
def test_declining_strict_boundaries(g: float, dm: float) -> None:
    assert_state(engine.LifecycleState.DECLINING, g=g, m=0.10, dm=dm, f=0.10)


def test_exact_decline_boundaries_are_not_declining_and_declining_wins_struggling() -> None:
    assert_state(engine.LifecycleState.TRANSITION, g=-0.05, m=0.10, dm=-0.05, f=0.10)
    assert_state(engine.LifecycleState.DECLINING, g=0.0, m=-0.10, dm=-0.051, f=-0.05)


def test_declining_missing_required_margin_direction_is_unclassified() -> None:
    result = classify(g=-0.10, m=0.10, f=0.10, lag_ebit=None)
    assert result.raw_state is engine.LifecycleState.UNCLASSIFIED
    assert result.reason_code is engine.LifecycleReason.LAG4_EBIT_MISSING


@pytest.mark.parametrize(
    ("m", "f"),
    [(-0.01, 0.01), (0.01, -0.01), (-0.01, -0.01)],
)
def test_struggling_negative_level_combinations(m: float, f: float) -> None:
    assert_state(engine.LifecycleState.STRUGGLING, g=0.0, m=m, dm=0.0, f=f)


def test_struggling_exact_boundaries_and_missing_history() -> None:
    assert_state(engine.LifecycleState.TRANSITION, g=0.0, m=0.0, dm=0.0, f=0.0)
    assert_state(engine.LifecycleState.STRUGGLING, g=-0.05, m=-0.01, dm=-0.05, f=0.01)
    result = classify(m=-0.01, f=0.01, chain_valid=False)
    assert result.raw_state is engine.LifecycleState.UNCLASSIFIED


def test_transition_requires_all_four_metrics() -> None:
    assert_state(engine.LifecycleState.TRANSITION, g=0.05, m=0.10, dm=0.0, f=0.04)
    result = classify(g=0.05, m=0.10, dm=0.0, f=None)
    assert result.raw_state is engine.LifecycleState.UNCLASSIFIED
    assert result.reason_code is engine.LifecycleReason.CURRENT_FCF_MISSING


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"core_ready": False}, engine.LifecycleReason.TTM_NOT_READY),
        ({"available_date": None}, engine.LifecycleReason.SOURCE_AVAILABILITY_DATE_MISSING),
        ({"available_date": "bad-date"}, engine.LifecycleReason.SOURCE_AVAILABILITY_DATE_INVALID),
        ({"current_revenue": None, "current_ebit": None}, engine.LifecycleReason.CURRENT_REVENUE_MISSING),
        ({"current_revenue": float("inf")}, engine.LifecycleReason.CURRENT_REVENUE_INVALID),
        ({"current_revenue": -1.0}, engine.LifecycleReason.CURRENT_REVENUE_NEGATIVE),
        ({"current_ebit": float("nan")}, engine.LifecycleReason.CURRENT_EBIT_INVALID),
        ({"current_revenue": 100.0, "lag_revenue": 0.0}, engine.LifecycleReason.LAG4_REVENUE_NONPOSITIVE),
        ({"current_revenue": 100.0, "lag_revenue": float("nan")}, engine.LifecycleReason.LAG4_REVENUE_INVALID),
        ({"chain_valid": False}, engine.LifecycleReason.FISCAL_CHAIN_INVALID),
    ],
)
def test_invalid_inputs_are_unclassified(kwargs: dict[str, object], reason: engine.LifecycleReason) -> None:
    result = classify(**kwargs)
    assert result.raw_state is engine.LifecycleState.UNCLASSIFIED
    assert result.lifecycle_status is engine.LifecycleStatus.NOT_READY
    assert result.reason_code is reason


def test_wrong_ttm_model_version_is_unclassified() -> None:
    row = dataclasses.replace(observation(), ttm_model_version="OTHER_TTM_MODEL")
    result = engine.classify_raw_state(row)
    assert result.raw_state is engine.LifecycleState.UNCLASSIFIED
    assert result.reason_code is engine.LifecycleReason.TTM_MODEL_VERSION_UNSUPPORTED


CLASS_REASON = {
    engine.LifecycleState.STARTUP: engine.LifecycleReason.CLASSIFIED_REVENUE_GENERATING_STARTUP,
    engine.LifecycleState.DISTRESSED: engine.LifecycleReason.CLASSIFIED_DISTRESSED,
    engine.LifecycleState.SCALING: engine.LifecycleReason.CLASSIFIED_SCALING,
    engine.LifecycleState.GROWTH: engine.LifecycleReason.CLASSIFIED_GROWTH,
    engine.LifecycleState.MATURE: engine.LifecycleReason.CLASSIFIED_MATURE,
    engine.LifecycleState.DECLINING: engine.LifecycleReason.CLASSIFIED_DECLINING,
    engine.LifecycleState.STRUGGLING: engine.LifecycleReason.CLASSIFIED_STRUGGLING,
    engine.LifecycleState.TRANSITION: engine.LifecycleReason.CLASSIFIED_TRANSITION,
}


def raw(state: engine.LifecycleState, index: int) -> engine.RawLifecycleResult:
    available = date(2025, 1, 1) + timedelta(days=index)
    row = observation(available_date=available.isoformat(), quarter_id=index)
    if state is engine.LifecycleState.UNCLASSIFIED:
        return engine.RawLifecycleResult(
            observation=row,
            raw_state=state,
            lifecycle_status=engine.LifecycleStatus.NOT_READY,
            reason_code=engine.LifecycleReason.REQUIRED_METRICS_MISSING,
            metrics=engine.LifecycleMetrics(None, None, None, None),
            missing_inputs=("test_input",),
        )
    return engine.RawLifecycleResult(
        observation=row,
        raw_state=state,
        lifecycle_status=engine.LifecycleStatus.READY,
        reason_code=CLASS_REASON[state],
        metrics=engine.LifecycleMetrics(0.0, 0.0, 0.0, 0.0),
        startup_profile=engine.StartupProfile.REVENUE_GENERATING if state is engine.LifecycleState.STARTUP else None,
    )


def replay(*states: engine.LifecycleState) -> tuple[engine.StateMachineResult, ...]:
    return engine.replay_state_machine(tuple(raw(state, index) for index, state in enumerate(states, 1)))


def test_first_classified_observation_and_leading_unclassified() -> None:
    results = replay(engine.LifecycleState.UNCLASSIFIED, engine.LifecycleState.MATURE)
    assert results[0].final_state is None
    assert results[0].last_confirmed_state is None
    assert results[1].final_state is engine.LifecycleState.MATURE
    assert results[1].transition_reason is engine.StateMachineReason.INITIAL_STATE_CONFIRMED


def test_ordinary_candidate_confirmation_and_return_to_confirmed_state() -> None:
    candidate = replay(engine.LifecycleState.MATURE, engine.LifecycleState.GROWTH)
    assert candidate[-1].final_state is engine.LifecycleState.MATURE
    assert candidate[-1].candidate_state is engine.LifecycleState.GROWTH
    assert candidate[-1].candidate_count == 1

    confirmed = replay(engine.LifecycleState.MATURE, engine.LifecycleState.GROWTH, engine.LifecycleState.GROWTH)
    assert confirmed[-1].final_state is engine.LifecycleState.GROWTH
    assert confirmed[-1].candidate_state is None

    returned = replay(engine.LifecycleState.MATURE, engine.LifecycleState.GROWTH, engine.LifecycleState.MATURE)
    assert returned[-1].final_state is engine.LifecycleState.MATURE
    assert returned[-1].candidate_state is None


def test_candidate_replacement_restarts_count() -> None:
    results = replay(engine.LifecycleState.MATURE, engine.LifecycleState.GROWTH, engine.LifecycleState.SCALING)
    assert results[-1].final_state is engine.LifecycleState.MATURE
    assert results[-1].candidate_state is engine.LifecycleState.SCALING
    assert results[-1].candidate_count == 1
    assert results[-1].transition_reason is engine.StateMachineReason.CANDIDATE_REPLACED


def test_distressed_entry_is_immediate_and_exit_needs_two_identical_states() -> None:
    entered = replay(engine.LifecycleState.MATURE, engine.LifecycleState.GROWTH, engine.LifecycleState.DISTRESSED)
    assert entered[-1].final_state is engine.LifecycleState.DISTRESSED
    assert entered[-1].candidate_state is None

    recovered = replay(engine.LifecycleState.DISTRESSED, engine.LifecycleState.STRUGGLING, engine.LifecycleState.STRUGGLING)
    assert recovered[-1].final_state is engine.LifecycleState.STRUGGLING

    failed = replay(engine.LifecycleState.DISTRESSED, engine.LifecycleState.STRUGGLING, engine.LifecycleState.DECLINING)
    assert failed[-1].final_state is engine.LifecycleState.DISTRESSED
    assert failed[-1].candidate_state is engine.LifecycleState.DECLINING
    assert failed[-1].candidate_count == 1


def test_unclassified_clears_candidate_and_never_publishes_last_confirmed_as_current() -> None:
    results = replay(
        engine.LifecycleState.MATURE,
        engine.LifecycleState.GROWTH,
        engine.LifecycleState.UNCLASSIFIED,
        engine.LifecycleState.GROWTH,
    )
    gap = results[2]
    assert gap.raw_result.raw_state is engine.LifecycleState.UNCLASSIFIED
    assert gap.lifecycle_status is engine.LifecycleStatus.NOT_READY
    assert gap.final_state is None
    assert gap.last_confirmed_state is engine.LifecycleState.MATURE
    assert gap.candidate_state is None
    assert results[-1].final_state is engine.LifecycleState.MATURE
    assert results[-1].candidate_state is engine.LifecycleState.GROWTH
    assert results[-1].candidate_count == 1


def test_unclassified_while_distressed_preserves_only_internal_last_confirmed_state() -> None:
    result = replay(engine.LifecycleState.DISTRESSED, engine.LifecycleState.UNCLASSIFIED)[-1]
    assert result.final_state is None
    assert result.last_confirmed_state is engine.LifecycleState.DISTRESSED
    assert result.lifecycle_status is engine.LifecycleStatus.NOT_READY


def test_direct_non_adjacent_transition_and_repeated_stable_state() -> None:
    direct = replay(engine.LifecycleState.GROWTH, engine.LifecycleState.MATURE, engine.LifecycleState.MATURE)
    assert direct[-1].final_state is engine.LifecycleState.MATURE
    stable = replay(engine.LifecycleState.SCALING, engine.LifecycleState.SCALING, engine.LifecycleState.SCALING)
    assert all(result.final_state is engine.LifecycleState.SCALING for result in stable)
    assert stable[-1].candidate_count == 0


def test_replay_is_deterministic_does_not_mutate_inputs_and_rejects_bad_order() -> None:
    inputs = tuple(raw(state, index) for index, state in enumerate((engine.LifecycleState.MATURE, engine.LifecycleState.GROWTH), 1))
    before = repr(inputs)
    first = engine.replay_state_machine(inputs)
    second = engine.replay_state_machine(inputs)
    assert first == second
    assert repr(inputs) == before
    assert dataclasses.is_dataclass(first[0])
    with pytest.raises(dataclasses.FrozenInstanceError):
        first[0].final_state = engine.LifecycleState.GROWTH  # type: ignore[misc]

    reversed_inputs = tuple(reversed(inputs))
    with pytest.raises(ValueError, match="NOT_CHRONOLOGICAL"):
        engine.replay_state_machine(reversed_inputs)


def test_lifecycle_contract_is_fingerprinted_and_has_no_score_or_legacy_runtime_dependency() -> None:
    assert engine.MODEL_VERSION == "V4_FUNDAMENTAL_LIFECYCLE_V1"
    assert engine.MODEL_FINGERPRINT == "db72e072fc2f0d9e3ceb13db1ee4cc92045383a5f44bfb65d21858b80190832f"
    source = inspect.getsource(engine).lower()
    assert "import swingmaster" not in source
    assert "from swingmaster" not in source
    assert "fundamentals.score" not in source
    assert "score_result" not in source
    assert "lifecycle_result" not in source
    assert "sqlite3" not in source
