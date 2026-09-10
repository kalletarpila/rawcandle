from __future__ import annotations

import bisect
import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any, Callable, Iterable, Mapping, Sequence

import numpy as np
from scipy import stats

from .contract import CONTRACT


@dataclass(frozen=True)
class AliasInterval:
    ticker: str
    valid_from: str | None
    valid_to: str | None
    security_active: bool
    current_ticker: str


@dataclass(frozen=True)
class PriceBar:
    session_date: str
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class ForwardLabel:
    horizon: int
    status: str
    entry_date: str | None = None
    exit_date: str | None = None
    entry_open: float | None = None
    exit_close: float | None = None
    benchmark_entry_open: float | None = None
    benchmark_exit_close: float | None = None
    price_return: float | None = None
    benchmark_return: float | None = None
    excess_return: float | None = None
    positive_return: int | None = None
    positive_excess: int | None = None
    mfe: float | None = None
    mae: float | None = None
    session_coverage: float | None = None
    last_market_date: str | None = None
    last_market_close: float | None = None
    trading_later_resumes: bool | None = None


def stable_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def valid_bar(values: Sequence[float | int | None]) -> bool:
    if len(values) != 4:
        return False
    if not all(value is not None and math.isfinite(float(value)) and float(value) > 0 for value in values):
        return False
    open_, high, low, close = (float(value) for value in values)
    return high >= max(open_, close) and low <= min(open_, close)


def resolve_ticker(signal_date: str, aliases: Sequence[AliasInterval]) -> tuple[str | None, str]:
    valid = [
        alias
        for alias in aliases
        if (alias.valid_from is None or alias.valid_from <= signal_date)
        and (alias.valid_to is None or signal_date < alias.valid_to)
    ]
    if len(valid) == 1:
        return valid[0].ticker.upper(), "DATED_ALIAS"
    current = sorted({alias.current_ticker.upper() for alias in aliases if alias.security_active})
    if not valid and len(current) == 1:
        return current[0], "CURRENT_TICKER_FALLBACK"
    return None, "UNRESOLVED_IDENTITY"


def construct_forward_label(
    *,
    signal_date: str | None,
    horizon: int,
    benchmark_sessions: Sequence[str],
    benchmark_bars: Mapping[str, PriceBar],
    company_bars: Mapping[str, PriceBar],
    minimum_coverage: float = 0.90,
    entry_session_number: int = 0,
) -> ForwardLabel:
    if signal_date is None:
        return ForwardLabel(horizon, "MISSING_AVAILABILITY_DATE")
    entry_index = bisect.bisect_right(benchmark_sessions, signal_date)
    if entry_index >= len(benchmark_sessions):
        return ForwardLabel(horizon, "MISSING_BENCHMARK_ENTRY")
    entry_date = benchmark_sessions[entry_index]
    if entry_date not in company_bars:
        return ForwardLabel(horizon, "MISSING_ENTRY_PRICE", entry_date=entry_date)
    exit_index = entry_index + horizon if entry_session_number == 0 else entry_index + horizon - 1
    entry = company_bars[entry_date]
    benchmark_entry = benchmark_bars[entry_date]
    if exit_index >= len(benchmark_sessions):
        last = company_bars[max(company_bars)] if company_bars else None
        return ForwardLabel(
            horizon,
            "HORIZON_NOT_MATURED",
            entry_date=entry_date,
            entry_open=entry.open,
            last_market_date=last.session_date if last else None,
            last_market_close=last.close if last else None,
        )
    exit_date = benchmark_sessions[exit_index]
    benchmark_exit = benchmark_bars[exit_date]
    benchmark_return = benchmark_exit.close / benchmark_entry.open - 1.0
    later = any(day > exit_date for day in company_bars)
    if exit_date not in company_bars:
        last_days = [day for day in company_bars if day <= exit_date]
        last = company_bars[max(last_days)] if last_days else None
        return ForwardLabel(
            horizon,
            "MISSING_EXACT_EXIT_PRICE",
            entry_date=entry_date,
            exit_date=exit_date,
            entry_open=entry.open,
            benchmark_entry_open=benchmark_entry.open,
            benchmark_exit_close=benchmark_exit.close,
            benchmark_return=benchmark_return,
            last_market_date=last.session_date if last else None,
            last_market_close=last.close if last else None,
            trading_later_resumes=later,
        )
    window_dates = benchmark_sessions[entry_index : exit_index + 1]
    observed = [company_bars[day] for day in window_dates if day in company_bars]
    coverage = len(observed) / len(window_dates)
    if coverage < minimum_coverage:
        last = company_bars[max(day for day in company_bars if day <= exit_date)]
        return ForwardLabel(
            horizon,
            "INSUFFICIENT_SESSION_COVERAGE",
            entry_date=entry_date,
            exit_date=exit_date,
            entry_open=entry.open,
            benchmark_entry_open=benchmark_entry.open,
            benchmark_exit_close=benchmark_exit.close,
            benchmark_return=benchmark_return,
            session_coverage=coverage,
            last_market_date=last.session_date,
            last_market_close=last.close,
            trading_later_resumes=later,
        )
    exit_bar = company_bars[exit_date]
    company_return = exit_bar.close / entry.open - 1.0
    return ForwardLabel(
        horizon=horizon,
        status="LABEL_READY",
        entry_date=entry_date,
        exit_date=exit_date,
        entry_open=entry.open,
        exit_close=exit_bar.close,
        benchmark_entry_open=benchmark_entry.open,
        benchmark_exit_close=benchmark_exit.close,
        price_return=company_return,
        benchmark_return=benchmark_return,
        excess_return=company_return - benchmark_return,
        positive_return=int(company_return > 0),
        positive_excess=int(company_return - benchmark_return > 0),
        mfe=max(bar.high / entry.open - 1.0 for bar in observed),
        mae=min(bar.low / entry.open - 1.0 for bar in observed),
        session_coverage=coverage,
        last_market_date=max(company_bars),
        last_market_close=company_bars[max(company_bars)].close,
        trading_later_resumes=later,
    )


def assign_period(entry_date: str | None) -> str | None:
    if entry_date is None:
        return None
    for name, bounds in CONTRACT["periods"].items():
        if name in {"assignment_date", "prospective_future_name"}:
            continue
        start, end = bounds
        if start <= entry_date <= end:
            return name
    return None


def embargo_cutoffs(benchmark_sessions: Sequence[str]) -> dict[str, str | None]:
    cutoffs: dict[str, str | None] = {"DEVELOPMENT": None}
    for period in ("TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION", "FORWARD_REPORT_ONLY"):
        start = CONTRACT["periods"][period][0]
        index = bisect.bisect_left(benchmark_sessions, start)
        cutoff_index = index + 63
        cutoffs[period] = benchmark_sessions[cutoff_index] if cutoff_index < len(benchmark_sessions) else None
    return cutoffs


def partition_decision(
    *, entry_date: str | None, exit_date_63: str | None, benchmark_sessions: Sequence[str]
) -> tuple[str | None, str]:
    period = assign_period(entry_date)
    if period is None:
        return None, "OUTSIDE_LOCKED_PERIODS"
    if exit_date_63 is None:
        return period, "PRIMARY_LABEL_NOT_READY"
    if exit_date_63 > CONTRACT["periods"][period][1]:
        return period, "PURGED_LABEL_CROSSES_PERIOD_END"
    cutoff = embargo_cutoffs(benchmark_sessions).get(period)
    if cutoff is not None and entry_date is not None and entry_date < cutoff:
        return period, "EMBARGO_FIRST_63_SESSIONS"
    return period, "RETAINED"


def fundamental_band(value: float) -> str:
    if value < 40:
        return "<40"
    if value < 60:
        return "40-<60"
    if value < 80:
        return "60-<80"
    return "80-100"


def valuation_band(value: float) -> str:
    if value < 20:
        return "<20"
    if value < 40:
        return "20-<40"
    if value < 60:
        return "40-<60"
    if value < 80:
        return "60-<80"
    return "80-100"


def delta_band(value: float) -> str:
    if value < -10:
        return "<-10"
    if value < 0:
        return "-10-<0"
    if value == 0:
        return "0"
    if value <= 10:
        return ">0-10"
    return ">10"


def trajectory_band(value: float) -> str:
    if value < 4:
        return "<4"
    if value < 6:
        return "4-<6"
    if value < 8:
        return "6-<8"
    return "8-10"


def diagnostic_count_band(value: int) -> str:
    return "0" if value == 0 else "1" if value == 1 else "2+"


def stress_excess(label: ForwardLabel, view: str) -> float | None:
    if label.status == "LABEL_READY":
        return label.excess_return
    if label.status not in {"MISSING_EXACT_EXIT_PRICE", "INSUFFICIENT_SESSION_COVERAGE"}:
        return None
    if view == "NEUTRAL_ZERO_EXCESS_BOUND":
        return 0.0
    if view == "SEVERE_MINUS_100_COMPANY_RETURN_BOUND" and label.benchmark_return is not None:
        return -1.0 - label.benchmark_return
    return None


def tie_safe_quintiles(predictions: Sequence[float], keys: Sequence[tuple[int, int]]) -> list[int]:
    if len(predictions) != len(keys):
        raise ValueError("PREDICTION_KEY_LENGTH_MISMATCH")
    if not predictions:
        return []
    distinct = sorted(set(float(value) for value in predictions))
    if len(distinct) < 5:
        return [min(5, bisect.bisect_right(distinct, float(value))) for value in predictions]
    ordered = sorted(range(len(predictions)), key=lambda i: (float(predictions[i]), keys[i]))
    result = [0] * len(predictions)
    for position, index in enumerate(ordered):
        result[index] = min(5, position * 5 // len(ordered) + 1)
    return result


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) < 3 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    return float(stats.spearmanr(x, y).statistic)


def pearson(x: Sequence[float], y: Sequence[float]) -> float | None:
    if len(x) < 3 or len(set(x)) < 2 or len(set(y)) < 2:
        return None
    return float(stats.pearsonr(x, y).statistic)


def benjamini_hochberg(p_values: Mapping[str, float | None]) -> dict[str, float | None]:
    valid = sorted(((name, value) for name, value in p_values.items() if value is not None), key=lambda item: item[1])
    adjusted: dict[str, float | None] = {name: None for name in p_values}
    running = 1.0
    for reverse_index in range(len(valid) - 1, -1, -1):
        name, value = valid[reverse_index]
        rank = reverse_index + 1
        running = min(running, value * len(valid) / rank)
        adjusted[name] = min(1.0, running)
    return adjusted


def monthly_ic(rows: Sequence[Mapping[str, Any]], feature: str, target: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row["entry_date"])[:7], []).append(row)
    output = []
    for month, members in sorted(grouped.items()):
        pairs = [(float(row[feature]), float(row[target])) for row in members if row.get(feature) is not None and row.get(target) is not None]
        output.append({
            "month": month,
            "feature": feature,
            "n": len(pairs),
            "status": "READY" if len(pairs) >= 20 else "INSUFFICIENT_OBSERVATIONS",
            "spearman_ic": spearman([p[0] for p in pairs], [p[1] for p in pairs]) if len(pairs) >= 20 else None,
        })
    return output


def moving_block_interval(
    rows: Sequence[Mapping[str, Any]],
    statistic: Callable[[list[Mapping[str, Any]]], float | None],
    *, repetitions: int = 1000,
    block_sessions: int = 63,
    seed: int = 12012,
) -> tuple[float | None, float | None, int]:
    if not rows:
        return None, None, 0
    dates = sorted({str(row["entry_date"]) for row in rows})
    by_date = {day: [row for row in rows if row["entry_date"] == day] for day in dates}
    blocks = [dates[index : index + block_sessions] for index in range(len(dates))]
    rng = np.random.default_rng(seed)
    values: list[float] = []
    target_dates = len(dates)
    for _ in range(repetitions):
        sampled_dates: list[str] = []
        while len(sampled_dates) < target_dates:
            sampled_dates.extend(blocks[int(rng.integers(0, len(blocks)))])
        sample = [row for day in sampled_dates[:target_dates] for row in by_date[day]]
        value = statistic(sample)
        if value is not None and math.isfinite(value):
            values.append(float(value))
    if not values:
        return None, None, 0
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975)), len(values)


def label_dict(label: ForwardLabel) -> dict[str, Any]:
    return asdict(label)
