from __future__ import annotations

import sqlite3

import pytest

from rawcandle.research.fundamental_profile_baseline.contract import CONTRACT_FINGERPRINT
from rawcandle.research.fundamental_profile_baseline.engine import (
    AliasInterval,
    PriceBar,
    construct_forward_label,
    delta_band,
    diagnostic_count_band,
    fundamental_band,
    monthly_ic,
    partition_decision,
    resolve_ticker,
    stress_excess,
    trajectory_band,
    valid_bar,
    valuation_band,
)
from rawcandle.research.fundamental_profile_baseline.models import (
    LIFECYCLE_CATEGORIES,
    MODEL_FEATURES,
    calibration_rows,
    fit_baseline,
    predict,
)
from rawcandle.research.fundamental_profile_baseline.runner import (
    _bootstrap_interval,
    attrition_waterfall,
    eligibility_reason,
)
from rawcandle.research.fundamental_profile_baseline.source import readonly


def _bars(days: list[str], *, missing: set[int] | None = None) -> dict[str, PriceBar]:
    missing = missing or set()
    return {
        day: PriceBar(day, 100.0 + index, 102.0 + index, 99.0 + index, 101.0 + index)
        for index, day in enumerate(days)
        if index not in missing
    }


def test_strict_next_session_session_zero_and_synchronized_return() -> None:
    days = [f"2024-01-{day:02d}" for day in range(2, 31)]
    benchmark = _bars(days)
    company = _bars(days)
    label = construct_forward_label(
        signal_date="2024-01-02", horizon=21, benchmark_sessions=days,
        benchmark_bars=benchmark, company_bars=company,
    )
    assert label.entry_date == "2024-01-03"
    assert label.exit_date == "2024-01-24"
    assert label.status == "LABEL_READY"
    assert label.excess_return == pytest.approx(0.0)


@pytest.mark.parametrize("horizon", [21, 42, 63])
def test_exact_locked_horizon_offsets(horizon: int) -> None:
    days = [f"2024-{1 + index // 28:02d}-{1 + index % 28:02d}" for index in range(90)]
    label = construct_forward_label(
        signal_date=days[0], horizon=horizon, benchmark_sessions=days,
        benchmark_bars=_bars(days), company_bars=_bars(days),
    )
    assert label.entry_date == days[1]
    assert label.exit_date == days[1 + horizon]


def test_exact_exit_coverage_boundary_and_missing_states() -> None:
    days = [f"2024-02-{day:02d}" for day in range(1, 30)]
    benchmark = _bars(days)
    exact = construct_forward_label(
        signal_date="2024-02-01", horizon=21, benchmark_sessions=days,
        benchmark_bars=benchmark, company_bars=_bars(days, missing={3, 4}),
    )
    assert exact.status == "LABEL_READY"
    assert exact.session_coverage >= 0.90
    low = construct_forward_label(
        signal_date="2024-02-01", horizon=21, benchmark_sessions=days,
        benchmark_bars=benchmark, company_bars=_bars(days, missing={3, 4, 5}),
    )
    assert low.status == "INSUFFICIENT_SESSION_COVERAGE"
    missing_exit = construct_forward_label(
        signal_date="2024-02-01", horizon=21, benchmark_sessions=days,
        benchmark_bars=benchmark, company_bars=_bars(days, missing={22}),
    )
    assert missing_exit.status == "MISSING_EXACT_EXIT_PRICE"
    immature = construct_forward_label(
        signal_date="2024-02-20", horizon=21, benchmark_sessions=days,
        benchmark_bars=benchmark, company_bars=_bars(days),
    )
    assert immature.status == "HORIZON_NOT_MATURED"


def test_exact_ninety_percent_coverage_is_inclusive() -> None:
    days = [f"2024-04-{day:02d}" for day in range(1, 16)]
    label = construct_forward_label(
        signal_date=days[0], horizon=9, benchmark_sessions=days,
        benchmark_bars=_bars(days), company_bars=_bars(days, missing={5}),
    )
    assert label.status == "LABEL_READY"
    assert label.session_coverage == pytest.approx(0.9)


def test_invalid_and_nonfinite_ohlc_are_rejected_without_readjustment() -> None:
    assert valid_bar((100.0, 102.0, 99.0, 101.0))
    assert not valid_bar((100.0, 99.0, 98.0, 101.0))
    assert not valid_bar((100.0, float("nan"), 99.0, 101.0))
    assert not valid_bar((100.0, 102.0, 0.0, 101.0))


def test_identity_alias_interval_and_unresolved_identity() -> None:
    aliases = [AliasInterval("OLD", "2020-01-01", "2024-01-01", False, "NEW")]
    assert resolve_ticker("2023-06-01", aliases) == ("OLD", "DATED_ALIAS")
    assert resolve_ticker("2025-01-01", aliases) == (None, "UNRESOLVED_IDENTITY")
    ambiguous = aliases + [AliasInterval("OTHER", "2023-01-01", None, True, "OTHER")]
    assert resolve_ticker("2023-06-01", ambiguous) == (None, "UNRESOLVED_IDENTITY")


@pytest.mark.parametrize(
    ("value", "expected"),
    [(-11, "<-10"), (-10, "-10-<0"), (-0.1, "-10-<0"), (0, "0"), (0.1, ">0-10"), (10, ">0-10"), (10.1, ">10")],
)
def test_locked_delta_bands(value: float, expected: str) -> None:
    assert delta_band(value) == expected


def test_other_locked_band_boundaries() -> None:
    assert [fundamental_band(x) for x in (39.9, 40, 60, 80, 100)] == ["<40", "40-<60", "60-<80", "80-100", "80-100"]
    assert [valuation_band(x) for x in (19.9, 20, 40, 60, 80)] == ["<20", "20-<40", "40-<60", "60-<80", "80-100"]
    assert [trajectory_band(x) for x in (3.9, 4, 6, 8)] == ["<4", "4-<6", "6-<8", "8-10"]
    assert [diagnostic_count_band(x) for x in (0, 1, 2, 8)] == ["0", "1", "2+", "2+"]


def test_partition_purge_and_embargo() -> None:
    sessions = [f"2024-{month:02d}-{day:02d}" for month in range(1, 7) for day in range(1, 29)]
    period, status = partition_decision(entry_date="2024-01-05", exit_date_63="2024-04-10", benchmark_sessions=sessions)
    assert period == "TEMPORAL_VALIDATION"
    assert status == "EMBARGO_FIRST_63_SESSIONS"
    _, status = partition_decision(entry_date="2024-10-01", exit_date_63="2025-01-02", benchmark_sessions=sessions)
    assert status == "PURGED_LABEL_CROSSES_PERIOD_END"


def test_stress_bounds_do_not_make_rows_model_eligible() -> None:
    days = [f"2024-03-{day:02d}" for day in range(1, 30)]
    label = construct_forward_label(
        signal_date="2024-03-01", horizon=21, benchmark_sessions=days,
        benchmark_bars=_bars(days), company_bars=_bars(days, missing={22}),
    )
    assert stress_excess(label, "NEUTRAL_ZERO_EXCESS_BOUND") == 0.0
    row = {
        "identity_status": "DATED_ALIAS", "score_status": "SCORE_FULL",
        "valuation_status": "VALUATION_FULL", "two_quarter_status": "DELTA_READY",
        "lifecycle_status": "LIFECYCLE_READY", "lifecycle": "MATURE",
        "diagnostic_complete": True, "fundamental_score": 80.0,
        "valuation_score": 60.0, "two_quarter_delta": 1.0,
        "component_fundamental_trajectory": 7.0, "diagnostic_flag_count": 0,
        "h63_status": label.status,
    }
    assert eligibility_reason(row) == "MISSING_EXACT_EXIT_PRICE"


def _model_rows(count: int, *, shift: float = 0.0) -> list[dict[str, object]]:
    states = ("MATURE",) + LIFECYCLE_CATEGORIES
    output = []
    for index in range(count):
        signal = float(index % 17) + shift
        output.append({
            "company_id": index + 1, "quarter_id": index + 100,
            "fundamental_score": 40.0 + signal,
            "valuation_score": 20.0 + signal,
            "two_quarter_delta": signal - 8.0,
            "component_fundamental_trajectory": signal % 10,
            "diagnostic_flag_count": index % 3,
            "lifecycle": states[index % len(states)],
            "h63_excess_return": (signal - 8.0) / 20.0,
            "h63_positive_excess": int(signal > 8.0),
        })
    return output


def test_fixed_models_and_development_only_scaling() -> None:
    development = _model_rows(80)
    model = fit_baseline(development, "B4")
    assert tuple(MODEL_FEATURES["B4"]) == (
        "fundamental_score", "valuation_score", "two_quarter_delta",
        "component_fundamental_trajectory", "diagnostic_flag_count",
    )
    assert "lifecycle_MATURE" not in model.feature_names
    scaler_mean = model.scaler.mean_.copy()
    predictions, probabilities = predict(model, _model_rows(20, shift=100.0))
    assert (model.scaler.mean_ == scaler_mean).all()
    assert len(predictions) == len(probabilities) == 20


def test_calibration_and_monthly_ic_are_deterministic() -> None:
    rows = _model_rows(40)
    for index, row in enumerate(rows):
        row["entry_date"] = f"2024-{1 + index // 20:02d}-15"
    first = calibration_rows("DEVELOPMENT", "B0", rows, [0.5] * len(rows))
    second = calibration_rows("DEVELOPMENT", "B0", rows, [0.5] * len(rows))
    assert first == second
    assert monthly_ic(rows, "fundamental_score", "h63_excess_return") == monthly_ic(rows, "fundamental_score", "h63_excess_return")


def test_calendar_block_bootstrap_is_deterministic() -> None:
    sessions = [f"2024-{1 + index // 28:02d}-{1 + index % 28:02d}" for index in range(90)]
    rows = []
    for index, day in enumerate(sessions):
        rows.append({"entry_date": day, "h63_excess_return": (index % 11 - 5) / 100.0})
    statistic = lambda sample: sum(float(row["h63_excess_return"]) for row in sample) / len(sample)
    assert _bootstrap_interval(rows, sessions, statistic) == _bootstrap_interval(rows, sessions, statistic)


def test_readonly_connection_rejects_writes(tmp_path) -> None:
    path = tmp_path / "source.db"
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE evidence(value INTEGER)")
    connection.commit()
    connection.close()
    source = readonly(path)
    with pytest.raises(sqlite3.OperationalError):
        source.execute("INSERT INTO evidence VALUES (1)")
    source.close()


def test_contract_fingerprint_is_required_by_cli_contract() -> None:
    assert len(CONTRACT_FINGERPRINT) == 64


def test_development_attrition_waterfall_is_sequential() -> None:
    base = {
        "source_availability_date": "2023-06-01", "entry_date": "2023-06-02",
        "company_id": 1, "h63_status": "LABEL_READY", "score_status": "SCORE_FULL",
        "valuation_status": "VALUATION_FULL", "two_quarter_status": "DELTA_READY",
        "lifecycle_status": "LIFECYCLE_READY", "lifecycle": "MATURE",
        "diagnostic_complete": True, "identity_status": "DATED_ALIAS",
        "period": "DEVELOPMENT", "partition_status": "RETAINED",
    }
    missing_score = dict(base, company_id=2, score_status="SCORE_LIMITED")
    purged = dict(base, company_id=3, partition_status="PURGED_LABEL_CROSSES_PERIOD_END")
    rows = attrition_waterfall(
        [base, missing_score, purged],
        availability_start="2021-01-01", availability_end="2023-12-31",
        final_period="DEVELOPMENT",
    )
    counts = {row["stage"]: row["remaining"] for row in rows}
    assert counts["ALL_ENDPOINTS"] == 3
    assert counts["SCORE_FULL"] == 2
    assert counts["PURGE_AND_EMBARGO"] == 1
