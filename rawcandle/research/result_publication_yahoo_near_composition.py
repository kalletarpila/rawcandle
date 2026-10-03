from __future__ import annotations

import calendar
import csv
import hashlib
import json
import math
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any, Mapping, Sequence

from rawcandle.research.result_publication_matched_comparison import (
    absolute_gap_bucket,
    load_event_window,
    load_latest_market_caps,
    market_cap_bucket,
    market_cap_tertiles,
    pre_event_trend_bucket,
)


COMPOSITION_VERSION = "result_publication_yahoo_near_composition_v1"
EXPECTED_PRIOR_MATCHED_SHA256 = (
    "0e7725604a547fb62f5d5e0936554c492afc355c1ffc6d1608cb628bb9b54e7a"
)
YAHOO_METHOD = "YAHOO_NEAR_UNIQUE_SEC"
EXACT_METHOD = "CANONICAL_VERIFIED"
MIN_PRE_EVENT_OBSERVATIONS = 15
OUTCOMES = (
    "gap_pct",
    "D0_close_return_pct",
    "return_D5",
    "return_D10",
    "return_D20",
    "relative_return_D5",
    "relative_return_D20",
    "post_D0_to_D5",
    "post_D0_to_D10",
    "post_D0_to_D20",
)
PAIRED_OUTCOMES = (
    "D0_close_return_pct",
    "return_D5",
    "return_D10",
    "return_D20",
    "relative_return_D5",
    "relative_return_D20",
    "post_D0_to_D5",
    "post_D0_to_D20",
)
BUCKET_RANK = {"LOW": 0, "MID": 1, "HIGH": 2}


@dataclass(frozen=True)
class YahooNearComposition:
    rows: list[dict[str, Any]]
    unmatched: list[dict[str, Any]]
    prepared_rows: list[dict[str, Any]]
    summary: dict[str, Any]
    cutoffs: dict[str, tuple[float, float]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readonly(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _identity(row: Mapping[str, Any]) -> tuple[int, int, str]:
    return int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"])


def _float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def load_ticker_classifications(database: str | Path) -> dict[str, dict[str, str | None]]:
    connection = _readonly(Path(database))
    try:
        rows = connection.execute(
            "SELECT ticker,market,sector,industry FROM ticker_meta ORDER BY ticker"
        ).fetchall()
    finally:
        connection.close()
    return {
        str(row["ticker"]): {
            "market": str(row["market"]) if row["market"] else None,
            "sector": str(row["sector"]) if row["sector"] else None,
            "industry": str(row["industry"]) if row["industry"] else None,
        }
        for row in rows
    }


def calculate_pre_event_proxies(
    history: Sequence[Mapping[str, Any]],
    d0_index: int,
    *,
    minimum_observations: int = MIN_PRE_EVENT_OBSERVATIONS,
) -> dict[str, Any]:
    if d0_index < 0 or d0_index > len(history):
        raise ValueError("D0_INDEX_INVALID")
    prior = list(history[max(0, d0_index - 21) : d0_index])
    dollar_volumes = [
        float(row["close"]) * int(row["volume"])
        for row in prior[-20:]
        if row.get("close") is not None
        and float(row["close"]) > 0
        and row.get("volume") is not None
        and int(row["volume"]) >= 0
    ]
    returns = [
        (float(current["close"]) / float(previous["close"]) - 1.0) * 100.0
        for previous, current in zip(prior, prior[1:])
        if previous.get("close") is not None
        and current.get("close") is not None
        and float(previous["close"]) > 0
    ][-20:]
    return {
        "median_dollar_volume_Dm20_to_Dm1": (
            median(dollar_volumes) if len(dollar_volumes) >= minimum_observations else None
        ),
        "realized_volatility_Dm20_to_Dm1": (
            stdev(returns) if len(returns) >= minimum_observations else None
        ),
        "liquidity_observation_count": len(dollar_volumes),
        "volatility_return_count": len(returns),
    }


def load_pre_event_context(
    event_rows: Sequence[Mapping[str, Any]], database: str | Path
) -> dict[tuple[int, int, str], dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in event_rows:
        grouped[str(row["ticker"])].append(row)
    connection = _readonly(Path(database))
    result: dict[tuple[int, int, str], dict[str, Any]] = {}
    try:
        for ticker in sorted(grouped):
            history = [
                dict(row)
                for row in connection.execute(
                    "SELECT pvm,close,volume FROM osakedata WHERE osake=? ORDER BY pvm",
                    (ticker,),
                ).fetchall()
            ]
            indexes = {str(row["pvm"]): index for index, row in enumerate(history)}
            for event in grouped[ticker]:
                index = indexes.get(str(event.get("D0_date") or ""))
                if index is None:
                    context = {
                        "median_dollar_volume_Dm20_to_Dm1": None,
                        "realized_volatility_Dm20_to_Dm1": None,
                        "liquidity_observation_count": 0,
                        "volatility_return_count": 0,
                    }
                else:
                    context = calculate_pre_event_proxies(history, index)
                result[_identity(event)] = context
    finally:
        connection.close()
    return result


def tertile_cutoffs(values: Sequence[float]) -> tuple[float, float]:
    usable = sorted(float(value) for value in values if math.isfinite(float(value)))
    if len(usable) < 3:
        raise ValueError("TERTILE_SAMPLE_TOO_SMALL")
    return usable[len(usable) // 3], usable[(2 * len(usable)) // 3]


def tertile_bucket(value: float | None, cutoffs: tuple[float, float]) -> str | None:
    if value is None or not math.isfinite(value):
        return None
    if value < cutoffs[0]:
        return "LOW"
    if value < cutoffs[1]:
        return "MID"
    return "HIGH"


def prepare_composition_rows(
    all_event_rows: Sequence[Mapping[str, Any]],
    market_caps: Mapping[int, float],
    classifications: Mapping[str, Mapping[str, str | None]],
    pre_event_context: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, tuple[float, float]]]:
    population = [
        row for row in all_event_rows if row.get("research_method") in {YAHOO_METHOD, EXACT_METHOD}
    ]
    market_cap_cutoffs = market_cap_tertiles(all_event_rows, market_caps)
    liquidity_values = [
        float(context["median_dollar_volume_Dm20_to_Dm1"])
        for context in pre_event_context.values()
        if context.get("median_dollar_volume_Dm20_to_Dm1") is not None
    ]
    volatility_values = [
        float(context["realized_volatility_Dm20_to_Dm1"])
        for context in pre_event_context.values()
        if context.get("realized_volatility_Dm20_to_Dm1") is not None
    ]
    cutoffs = {
        "market_cap": market_cap_cutoffs,
        "liquidity": tertile_cutoffs(liquidity_values),
        "volatility": tertile_cutoffs(volatility_values),
    }
    prepared: list[dict[str, Any]] = []
    for source in population:
        row = dict(source)
        company_id = int(row["company_id"])
        context = dict(pre_event_context.get(_identity(row), {}))
        classification = classifications.get(str(row["ticker"]), {})
        cap = market_caps.get(company_id)
        liquidity = _float(context.get("median_dollar_volume_Dm20_to_Dm1"))
        volatility = _float(context.get("realized_volatility_Dm20_to_Dm1"))
        gap = _float(row.get("gap_pct"))
        trend = _float(row.get("return_Dm5_to_Dm1"))
        row.update(
            {
                "event_year": int(str(row["D0_date"])[:4]) if row.get("D0_date") else None,
                "market": classification.get("market"),
                "sector": classification.get("sector"),
                "industry": classification.get("industry"),
                "market_cap_proxy": cap,
                "market_cap_bucket": market_cap_bucket(cap, market_cap_cutoffs),
                "absolute_gap_pct": abs(gap) if gap is not None else None,
                "absolute_gap_bucket": absolute_gap_bucket(gap),
                "pre_event_trend": trend,
                "pre_event_trend_bucket": pre_event_trend_bucket(trend),
                **context,
                "liquidity_bucket": tertile_bucket(liquidity, cutoffs["liquidity"]),
                "volatility_bucket": tertile_bucket(volatility, cutoffs["volatility"]),
            }
        )
        prepared.append(row)
    return prepared, cutoffs


def _fully_eligible(row: Mapping[str, Any]) -> bool:
    return all(
        row.get(field) is not None
        for field in (
            "event_year",
            "market_cap_bucket",
            "absolute_gap_bucket",
            "pre_event_trend_bucket",
            "sector",
            "liquidity_bucket",
            "volatility_bucket",
        )
    )


def _fixed_stratum(row: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        row["event_year"],
        row["market_cap_bucket"],
        row["absolute_gap_bucket"],
        row["pre_event_trend_bucket"],
        row["sector"],
    )


def relaxation_level(treatment: Mapping[str, Any], control: Mapping[str, Any]) -> str | None:
    if _fixed_stratum(treatment) != _fixed_stratum(control):
        return None
    liquidity_distance = abs(
        BUCKET_RANK[str(treatment["liquidity_bucket"])]
        - BUCKET_RANK[str(control["liquidity_bucket"])]
    )
    volatility_distance = abs(
        BUCKET_RANK[str(treatment["volatility_bucket"])]
        - BUCKET_RANK[str(control["volatility_bucket"])]
    )
    if liquidity_distance == 0 and volatility_distance == 0:
        return "A_EXACT_ALL"
    if liquidity_distance <= 1 and volatility_distance == 0:
        return "B_ADJACENT_LIQUIDITY"
    if liquidity_distance <= 1 and volatility_distance <= 1:
        return "C_ADJACENT_LIQUIDITY_AND_VOLATILITY"
    return None


def _control_score(treatment: Mapping[str, Any], control: Mapping[str, Any]) -> tuple[Any, ...]:
    return (
        abs(float(treatment["absolute_gap_pct"]) - float(control["absolute_gap_pct"])),
        abs(float(treatment["pre_event_trend"]) - float(control["pre_event_trend"])),
        abs(
            math.log1p(float(treatment["median_dollar_volume_Dm20_to_Dm1"]))
            - math.log1p(float(control["median_dollar_volume_Dm20_to_Dm1"]))
        ),
        abs(
            float(treatment["realized_volatility_Dm20_to_Dm1"])
            - float(control["realized_volatility_Dm20_to_Dm1"])
        ),
        _identity(control),
    )


def _matched_row(
    treatment: Mapping[str, Any], control: Mapping[str, Any], level: str, match_id: int
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "match_id": match_id,
        "relaxation_level": level,
        "event_year": treatment["event_year"],
        "sector": treatment["sector"],
        "industry": treatment["industry"],
        "market_cap_bucket": treatment["market_cap_bucket"],
        "absolute_gap_bucket": treatment["absolute_gap_bucket"],
        "pre_event_trend_bucket": treatment["pre_event_trend_bucket"],
        "yahoo_liquidity_bucket": treatment["liquidity_bucket"],
        "exact_liquidity_bucket": control["liquidity_bucket"],
        "yahoo_volatility_bucket": treatment["volatility_bucket"],
        "exact_volatility_bucket": control["volatility_bucket"],
        "yahoo_company_id": int(treatment["company_id"]),
        "yahoo_ticker": treatment["ticker"],
        "yahoo_fiscal_year": int(treatment["fiscal_year"]),
        "yahoo_fiscal_quarter": treatment["fiscal_quarter"],
        "yahoo_D0_date": treatment["D0_date"],
        "exact_company_id": int(control["company_id"]),
        "exact_ticker": control["ticker"],
        "exact_fiscal_year": int(control["fiscal_year"]),
        "exact_fiscal_quarter": control["fiscal_quarter"],
        "exact_D0_date": control["D0_date"],
        "yahoo_market_cap_proxy": treatment["market_cap_proxy"],
        "exact_market_cap_proxy": control["market_cap_proxy"],
        "yahoo_absolute_gap_pct": treatment["absolute_gap_pct"],
        "exact_absolute_gap_pct": control["absolute_gap_pct"],
        "yahoo_pre_event_trend": treatment["pre_event_trend"],
        "exact_pre_event_trend": control["pre_event_trend"],
        "yahoo_median_dollar_volume": treatment["median_dollar_volume_Dm20_to_Dm1"],
        "exact_median_dollar_volume": control["median_dollar_volume_Dm20_to_Dm1"],
        "yahoo_realized_volatility": treatment["realized_volatility_Dm20_to_Dm1"],
        "exact_realized_volatility": control["realized_volatility_Dm20_to_Dm1"],
        "yahoo_largest_move_day": treatment.get("largest_move_day"),
        "exact_largest_move_day": control.get("largest_move_day"),
    }
    for field in ("date_Dm1", "Dm1_close", "D0_open", "D0_close", "date_Dp1", "Dp1_close"):
        result[f"yahoo_{field}"] = treatment.get(field)
    for outcome in OUTCOMES:
        yahoo_value = _float(treatment.get(outcome))
        exact_value = _float(control.get(outcome))
        result[f"yahoo_{outcome}"] = yahoo_value
        result[f"exact_{outcome}"] = exact_value
        result[f"difference_{outcome}"] = (
            yahoo_value - exact_value
            if yahoo_value is not None and exact_value is not None
            else None
        )
    return result


def match_yahoo_near(
    prepared_rows: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    treatment = [
        row for row in prepared_rows if row.get("research_method") == YAHOO_METHOD and _fully_eligible(row)
    ]
    controls = [
        row for row in prepared_rows if row.get("research_method") == EXACT_METHOD and _fully_eligible(row)
    ]
    candidates: dict[tuple[int, int, str], dict[str, list[Mapping[str, Any]]]] = {}
    levels = (
        "A_EXACT_ALL",
        "B_ADJACENT_LIQUIDITY",
        "C_ADJACENT_LIQUIDITY_AND_VOLATILITY",
    )
    for row in treatment:
        by_level = {level: [] for level in levels}
        for control in controls:
            level = relaxation_level(row, control)
            if level:
                by_level[level].append(control)
        candidates[_identity(row)] = by_level
    treatment.sort(
        key=lambda row: (
            sum(len(values) for values in candidates[_identity(row)].values()),
            sum(len(candidates[_identity(row)][level]) for level in levels[:2]),
            len(candidates[_identity(row)][levels[0]]),
            _identity(row),
        )
    )
    used: set[tuple[int, int, str]] = set()
    matches: list[dict[str, Any]] = []
    unmatched: list[dict[str, Any]] = []
    for row in treatment:
        selected: Mapping[str, Any] | None = None
        selected_level: str | None = None
        for level in levels:
            available = [
                control
                for control in candidates[_identity(row)][level]
                if _identity(control) not in used
            ]
            if available:
                selected = min(available, key=lambda control: _control_score(row, control))
                selected_level = level
                break
        if selected is None or selected_level is None:
            unmatched.append({**row, "unmatched_reason": "NO_UNUSED_CONTROL_AFTER_RELAXATION_C"})
            continue
        used.add(_identity(selected))
        matches.append(_matched_row(row, selected, selected_level, len(matches) + 1))
    matches.sort(key=lambda row: (int(row["yahoo_company_id"]), int(row["yahoo_fiscal_year"]), str(row["yahoo_fiscal_quarter"])))
    for index, row in enumerate(matches, 1):
        row["match_id"] = index
    return matches, unmatched


def _percentile(values: Sequence[float], percentile: int) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile / 100.0
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def _stats(values: Sequence[float | None]) -> dict[str, Any]:
    usable = [float(value) for value in values if value is not None]
    return {
        "n": len(usable),
        "median": median(usable) if usable else None,
        "p25": _percentile(usable, 25),
        "p75": _percentile(usable, 75),
        "mean": mean(usable) if usable else None,
        "positive_pct": sum(value > 0 for value in usable) / len(usable) * 100 if usable else None,
    }


def _distribution(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    counts = Counter(str(row[field]) for row in rows if row.get(field) is not None)
    total = sum(counts.values())
    return {
        key: {"count": count, "pct": count / total * 100 if total else None}
        for key, count in sorted(counts.items())
    }


def _categorical_balance(
    treatment: Sequence[Mapping[str, Any]], controls: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    result = {}
    for field in (
        "event_year",
        "sector",
        "market_cap_bucket",
        "absolute_gap_bucket",
        "pre_event_trend_bucket",
        "liquidity_bucket",
        "volatility_bucket",
    ):
        left = _distribution(treatment, field)
        right = _distribution(controls, field)
        keys = set(left) | set(right)
        result[field] = {
            "YAHOO_NEAR": left,
            "EXACT": right,
            "total_variation_percentage_points": 0.5
            * sum(
                abs(float(left.get(key, {}).get("pct") or 0) - float(right.get(key, {}).get("pct") or 0))
                for key in keys
            ),
        }
    return result


def _numeric_balance(
    treatment: Sequence[Mapping[str, Any]], controls: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    result = {}
    for field in (
        "market_cap_proxy",
        "absolute_gap_pct",
        "pre_event_trend",
        "median_dollar_volume_Dm20_to_Dm1",
        "realized_volatility_Dm20_to_Dm1",
    ):
        left = [_float(row.get(field)) for row in treatment]
        right = [_float(row.get(field)) for row in controls]
        left_values = [value for value in left if value is not None]
        right_values = [value for value in right if value is not None]
        left_mean = mean(left_values) if left_values else None
        right_mean = mean(right_values) if right_values else None
        variances = []
        for values, value_mean in ((left_values, left_mean), (right_values, right_mean)):
            if len(values) > 1 and value_mean is not None:
                variances.append(sum((value - value_mean) ** 2 for value in values) / (len(values) - 1))
        pooled = math.sqrt(sum(variances) / len(variances)) if variances else None
        result[field] = {
            "YAHOO_NEAR": _stats(left_values),
            "EXACT": _stats(right_values),
            "standardized_mean_difference": (
                (left_mean - right_mean) / pooled
                if left_mean is not None and right_mean is not None and pooled
                else None
            ),
        }
    return result


def _match_side_rows(matches: Sequence[Mapping[str, Any]], side: str) -> list[dict[str, Any]]:
    prefix = "yahoo" if side == "YAHOO_NEAR" else "exact"
    return [
        {
            "event_year": row["event_year"],
            "sector": row["sector"],
            "market_cap_bucket": row["market_cap_bucket"],
            "absolute_gap_bucket": row["absolute_gap_bucket"],
            "pre_event_trend_bucket": row["pre_event_trend_bucket"],
            "liquidity_bucket": row[f"{prefix}_liquidity_bucket"],
            "volatility_bucket": row[f"{prefix}_volatility_bucket"],
            "market_cap_proxy": row[f"{prefix}_market_cap_proxy"],
            "absolute_gap_pct": row[f"{prefix}_absolute_gap_pct"],
            "pre_event_trend": row[f"{prefix}_pre_event_trend"],
            "median_dollar_volume_Dm20_to_Dm1": row[f"{prefix}_median_dollar_volume"],
            "realized_volatility_Dm20_to_Dm1": row[f"{prefix}_realized_volatility"],
        }
        for row in matches
    ]


def _sector_summary(matches: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in matches:
        grouped[str(row["sector"])].append(row)
    return {
        sector: {
            "n": len(rows),
            "sparse": len(rows) < 10,
            "YAHOO_NEAR": {
                outcome: _stats([_float(row.get(f"yahoo_{outcome}")) for row in rows])
                for outcome in ("D0_close_return_pct", "return_D5", "return_D20")
            },
            "EXACT": {
                outcome: _stats([_float(row.get(f"exact_{outcome}")) for row in rows])
                for outcome in ("D0_close_return_pct", "return_D5", "return_D20")
            },
            "paired_D20": _stats([_float(row.get("difference_return_D20")) for row in rows]),
        }
        for sector, rows in sorted(grouped.items())
    }


def _stratified_summary(rows: Sequence[Mapping[str, Any]], field: str) -> dict[str, Any]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get(field) is not None:
            grouped[str(row[field])].append(row)
    return {
        bucket: {
            "n": len(values),
            **{
                outcome: _stats([_float(row.get(outcome)) for row in values])
                for outcome in ("D0_close_return_pct", "return_D5", "return_D20")
            },
        }
        for bucket, values in sorted(grouped.items(), key=lambda item: BUCKET_RANK[item[0]])
    }


def summarize_yahoo_near_composition(
    matches: Sequence[Mapping[str, Any]],
    unmatched: Sequence[Mapping[str, Any]],
    prepared_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    yahoo_all = [row for row in prepared_rows if row.get("research_method") == YAHOO_METHOD]
    exact_all = [row for row in prepared_rows if row.get("research_method") == EXACT_METHOD]
    yahoo_eligible = [row for row in yahoo_all if _fully_eligible(row)]
    exact_eligible = [row for row in exact_all if _fully_eligible(row)]
    matched_yahoo = _match_side_rows(matches, "YAHOO_NEAR")
    matched_exact = _match_side_rows(matches, "EXACT")
    outcomes = {
        outcome: {
            "YAHOO_NEAR": _stats([_float(row.get(f"yahoo_{outcome}")) for row in matches]),
            "EXACT": _stats([_float(row.get(f"exact_{outcome}")) for row in matches]),
        }
        for outcome in OUTCOMES
    }
    paired = {
        outcome: _stats([_float(row.get(f"difference_{outcome}")) for row in matches])
        for outcome in PAIRED_OUTCOMES
    }
    controls = Counter(
        (int(row["exact_company_id"]), int(row["exact_fiscal_year"]), str(row["exact_fiscal_quarter"]))
        for row in matches
    )
    existing_fields = (
        "event_year",
        "market_cap_bucket",
        "absolute_gap_bucket",
        "pre_event_trend_bucket",
    )
    existing_eligible = [
        row for row in yahoo_all if all(row.get(field) is not None for field in existing_fields)
    ]
    sector_eligible = [row for row in existing_eligible if row.get("sector") is not None]
    liquidity_eligible = [
        row for row in sector_eligible if row.get("liquidity_bucket") is not None
    ]
    volatility_eligible = [
        row for row in liquidity_eligible if row.get("volatility_bucket") is not None
    ]
    industry_counts = Counter(str(row["industry"]) for row in yahoo_all if row.get("industry"))
    return {
        "coverage": {
            "yahoo_near_total": len(yahoo_all),
            "rows_with_sector": sum(row.get("sector") is not None for row in yahoo_all),
            "rows_with_industry": sum(row.get("industry") is not None for row in yahoo_all),
            "rows_with_liquidity": sum(row.get("liquidity_bucket") is not None for row in yahoo_all),
            "rows_with_volatility": sum(row.get("volatility_bucket") is not None for row in yahoo_all),
            "rows_with_market_cap": sum(row.get("market_cap_bucket") is not None for row in yahoo_all),
            "fully_eligible": len(yahoo_eligible),
            "successfully_matched": len(matches),
            "unmatched_after_eligibility": len(unmatched),
            "ineligible": len(yahoo_all) - len(yahoo_eligible),
            "eligibility_funnel": {
                "total": len(yahoo_all),
                "existing_four_controls": len(existing_eligible),
                "plus_sector": len(sector_eligible),
                "plus_liquidity": len(liquidity_eligible),
                "plus_volatility_fully_eligible": len(volatility_eligible),
            },
            "exact_controls_used": len(controls),
            "control_reuse": {
                "maximum_uses": max(controls.values(), default=0),
                "controls_used_more_than_once": sum(value > 1 for value in controls.values()),
            },
            "relaxation_levels": dict(sorted(Counter(str(row["relaxation_level"]) for row in matches).items())),
            "unmatched_reasons": dict(
                sorted(Counter(str(row["unmatched_reason"]) for row in unmatched).items())
            ),
        },
        "balance": {
            "before": {
                "categorical": _categorical_balance(yahoo_eligible, exact_eligible),
                "numeric": _numeric_balance(yahoo_eligible, exact_eligible),
            },
            "after": {
                "categorical": _categorical_balance(matched_yahoo, matched_exact),
                "numeric": _numeric_balance(matched_yahoo, matched_exact),
            },
        },
        "outcomes": outcomes,
        "paired_differences_yahoo_near_minus_exact": paired,
        "shift_diagnostic": {
            "YAHOO_NEAR": dict(sorted(Counter(str(row.get("yahoo_largest_move_day") or "UNAVAILABLE") for row in matches).items())),
            "EXACT": dict(sorted(Counter(str(row.get("exact_largest_move_day") or "UNAVAILABLE") for row in matches).items())),
        },
        "sector_breakdown": _sector_summary(matches),
        "industry_descriptive": {
            "unique_industries": len(industry_counts),
            "industries_with_at_least_10_events": sum(count >= 10 for count in industry_counts.values()),
            "events_in_industries_below_10": sum(count for count in industry_counts.values() if count < 10),
            "largest_industries": dict(industry_counts.most_common(10)),
        },
        "liquidity_stratification_all_yahoo_near": _stratified_summary(yahoo_all, "liquidity_bucket"),
        "volatility_stratification_all_yahoo_near": _stratified_summary(yahoo_all, "volatility_bucket"),
    }


def build_yahoo_near_matched_comparison(
    all_event_rows: Sequence[Mapping[str, Any]],
    market_caps: Mapping[int, float],
    classifications: Mapping[str, Mapping[str, str | None]],
    pre_event_context: Mapping[tuple[int, int, str], Mapping[str, Any]],
) -> YahooNearComposition:
    prepared, cutoffs = prepare_composition_rows(
        all_event_rows, market_caps, classifications, pre_event_context
    )
    matches, unmatched = match_yahoo_near(prepared)
    return YahooNearComposition(
        rows=matches,
        unmatched=unmatched,
        prepared_rows=prepared,
        summary=summarize_yahoo_near_composition(matches, unmatched, prepared),
        cutoffs=cutoffs,
    )


def load_period_ends_and_calendar_patterns(
    canonical_db: str | Path, event_rows: Sequence[Mapping[str, Any]]
) -> tuple[dict[tuple[int, int, str], str], dict[tuple[int, int, str], str]]:
    keys = {_identity(row) for row in event_rows}
    connection = _readonly(Path(canonical_db))
    try:
        rows = connection.execute(
            "SELECT company_id,fiscal_year,fiscal_quarter,period_end FROM v4_quarter"
        ).fetchall()
    finally:
        connection.close()
    period_ends: dict[tuple[int, int, str], str] = {}
    patterns: dict[tuple[int, int, str], str] = {}
    for row in rows:
        key = (int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"]))
        if key not in keys:
            continue
        value = str(row["period_end"])
        parsed = date.fromisoformat(value)
        period_ends[key] = value
        if parsed.day != calendar.monthrange(parsed.year, parsed.month)[1]:
            patterns[key] = "WEEK_BASED_NON_MONTH_END"
        elif parsed.month in {3, 6, 9, 12}:
            patterns[key] = "CALENDAR_QUARTER_MONTH_END"
        else:
            patterns[key] = "NONSTANDARD_MONTH_END"
    return period_ends, patterns


def summarize_foreign_calendar(
    prepared_rows: Sequence[Mapping[str, Any]], calendar_patterns: Mapping[tuple[int, int, str], str]
) -> dict[str, Any]:
    yahoo = [row for row in prepared_rows if row.get("research_method") == YAHOO_METHOD]
    return {
        "market_counts": dict(sorted(Counter(str(row.get("market") or "UNKNOWN") for row in yahoo).items())),
        "non_usa_market_count": sum(str(row.get("market") or "").lower() != "usa" for row in yahoo),
        "foreign_issuer_classification": "UNAVAILABLE_IN_CURRENT_LOCAL_METADATA",
        "calendar_pattern_counts": dict(
            sorted(Counter(calendar_patterns.get(_identity(row), "UNAVAILABLE") for row in yahoo).items())
        ),
        "adr_classification": "UNAVAILABLE_IN_CURRENT_LOCAL_METADATA",
        "ticker_suffix_count": sum("." in str(row["ticker"]) for row in yahoo),
    }


def load_latest_eps_surprises(
    forecasts_db: str | Path,
    period_ends: Mapping[tuple[int, int, str], str],
) -> dict[tuple[int, int, str], float]:
    wanted = {(key[0], period_end): key for key, period_end in period_ends.items()}
    connection = _readonly(Path(forecasts_db))
    try:
        rows = connection.execute(
            """
            SELECT s.company_id,r.provider_quarter_date,r.surprise_percent,s.first_seen_at_utc
            FROM forecast_snapshot s
            JOIN forecast_earnings_history_reference r USING(snapshot_id)
            WHERE s.forecast_family='EARNINGS_HISTORY_REFERENCE'
              AND s.company_id IS NOT NULL
              AND r.surprise_percent_state='NUMERIC_VALUE'
            ORDER BY s.first_seen_at_utc,s.snapshot_id,r.occurrence_index
            """
        ).fetchall()
    finally:
        connection.close()
    latest: dict[tuple[int, str], float] = {}
    for row in rows:
        latest[(int(row["company_id"]), str(row["provider_quarter_date"]))] = float(
            row["surprise_percent"]
        )
    return {
        key: latest[(key[0], period_end)]
        for key, period_end in period_ends.items()
        if (key[0], period_end) in latest
    }


def summarize_eps_surprises(
    matches: Sequence[Mapping[str, Any]], surprises: Mapping[tuple[int, int, str], float]
) -> dict[str, Any]:
    values: dict[str, list[float]] = {"YAHOO_NEAR": [], "EXACT": []}
    for row in matches:
        yahoo_key = (
            int(row["yahoo_company_id"]),
            int(row["yahoo_fiscal_year"]),
            str(row["yahoo_fiscal_quarter"]),
        )
        exact_key = (
            int(row["exact_company_id"]),
            int(row["exact_fiscal_year"]),
            str(row["exact_fiscal_quarter"]),
        )
        if yahoo_key in surprises:
            values["YAHOO_NEAR"].append(surprises[yahoo_key])
        if exact_key in surprises:
            values["EXACT"].append(surprises[exact_key])
    return {
        side: {
            "available": len(side_values),
            "positive": sum(value > 0 for value in side_values),
            "zero": sum(value == 0 for value in side_values),
            "negative": sum(value < 0 for value in side_values),
            "median_surprise": median(side_values) if side_values else None,
        }
        for side, side_values in values.items()
    } | {
        "semantics": "latest observed Yahoo provider EPS surprise matched by company_id and canonical period_end"
    }


def load_yahoo_distance(
    publication_csv: str | Path,
) -> dict[tuple[int, int, str], int]:
    result = {}
    with Path(publication_csv).open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("research_method") != YAHOO_METHOD:
                continue
            value = row.get("trading_day_distance_to_yahoo")
            if value not in (None, ""):
                result[_identity(row)] = int(value)
    return result


def select_manual_qa(
    matches: Sequence[Mapping[str, Any]], yahoo_distance: Mapping[tuple[int, int, str], int]
) -> list[dict[str, Any]]:
    if not matches:
        return []
    sector_groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in matches:
        if row.get("yahoo_return_D20") is not None:
            sector_groups[str(row["sector"])].append(row)
    sector_medians = {
        sector: median(float(row["yahoo_return_D20"]) for row in rows)
        for sector, rows in sector_groups.items()
        if len(rows) >= 10
    }
    selectors: list[tuple[str, Mapping[str, Any]]] = [
        ("LOW_LIQUIDITY", min(matches, key=lambda row: (float(row["yahoo_median_dollar_volume"]), int(row["yahoo_company_id"])))),
        ("HIGH_LIQUIDITY", max(matches, key=lambda row: (float(row["yahoo_median_dollar_volume"]), -int(row["yahoo_company_id"])))),
        ("LOW_VOLATILITY", min(matches, key=lambda row: (float(row["yahoo_realized_volatility"]), int(row["yahoo_company_id"])))),
        ("HIGH_VOLATILITY", max(matches, key=lambda row: (float(row["yahoo_realized_volatility"]), -int(row["yahoo_company_id"])))),
    ]
    if sector_medians:
        for label, sector in (
            ("MOST_NEGATIVE_SECTOR_D20", min(sector_medians, key=lambda key: (sector_medians[key], key))),
            ("MOST_POSITIVE_SECTOR_D20", max(sector_medians, key=lambda key: (sector_medians[key], key))),
        ):
            candidates = sector_groups[sector]
            target = sector_medians[sector]
            selectors.append(
                (
                    label,
                    min(
                        candidates,
                        key=lambda row: (
                            abs(float(row["yahoo_return_D20"]) - target),
                            int(row["yahoo_company_id"]),
                            int(row["yahoo_fiscal_year"]),
                            str(row["yahoo_fiscal_quarter"]),
                        ),
                    ),
                )
            )
    edge = [
        row
        for row in matches
        if abs(
            yahoo_distance.get(
                (
                    int(row["yahoo_company_id"]),
                    int(row["yahoo_fiscal_year"]),
                    str(row["yahoo_fiscal_quarter"]),
                ),
                0,
            )
        )
        == 1
    ]
    if edge:
        selectors.append(("ONE_DAY_EDGE_YAHOO", min(edge, key=lambda row: (int(row["yahoo_company_id"]), int(row["yahoo_fiscal_year"]), str(row["yahoo_fiscal_quarter"])))))
    result = []
    for reason, row in selectors:
        key = (
            int(row["yahoo_company_id"]),
            int(row["yahoo_fiscal_year"]),
            str(row["yahoo_fiscal_quarter"]),
        )
        result.append(
            {
                "selection_reason": reason,
                "ticker": row["yahoo_ticker"],
                "fiscal_year": key[1],
                "fiscal_quarter": key[2],
                "method": YAHOO_METHOD,
                "event_boundary": row["yahoo_D0_date"],
                "date_Dm1": row.get("yahoo_date_Dm1"),
                "Dm1_close": _float(row.get("yahoo_Dm1_close")),
                "D0_open": _float(row.get("yahoo_D0_open")),
                "D0_close": _float(row.get("yahoo_D0_close")),
                "date_Dp1": row.get("yahoo_date_Dp1"),
                "Dp1_close": _float(row.get("yahoo_Dp1_close")),
                "liquidity": row["yahoo_median_dollar_volume"],
                "volatility": row["yahoo_realized_volatility"],
                "sector": row["sector"],
                "return_D5": row.get("yahoo_return_D5"),
                "return_D20": row.get("yahoo_return_D20"),
                "largest_move_day": row.get("yahoo_largest_move_day"),
                "yahoo_trading_day_distance": yahoo_distance.get(key),
            }
        )
    return result


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    if not rows:
        raise ValueError("OUTPUT_ROWS_EMPTY")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def validate_prior_matched_comparison(path: str | Path) -> None:
    source = Path(path)
    if _sha256(source) != EXPECTED_PRIOR_MATCHED_SHA256:
        raise ValueError("PRIOR_MATCHED_COMPARISON_SHA256_MISMATCH")
    with source.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 556:
        raise ValueError("PRIOR_MATCHED_COMPARISON_ROW_COUNT_MISMATCH")
    if sum(row.get("high_method") == YAHOO_METHOD for row in rows) != 471:
        raise ValueError("PRIOR_MATCHED_YAHOO_NEAR_COUNT_MISMATCH")


def write_composition_outputs(
    result: YahooNearComposition,
    output_csv: str | Path,
    output_metadata: str | Path,
    *,
    event_csv: str | Path,
    event_metadata: str | Path,
    matched_input: str | Path,
    market_cap_db: str | Path,
    canonical_db: str | Path,
    ohlc_db: str | Path,
    forecasts_db: str | Path,
    publication_csv: str | Path,
    extra_summary: Mapping[str, Any],
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    output = Path(output_csv)
    _write_csv(output, result.rows)
    metadata = {
        "artifact_version": COMPOSITION_VERSION,
        "generated_at_utc": generated_at_utc
        or datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "event_window": str(Path(event_csv).resolve()),
        "event_window_sha256": _sha256(Path(event_csv)),
        "event_window_metadata": str(Path(event_metadata).resolve()),
        "event_window_metadata_sha256": _sha256(Path(event_metadata)),
        "prior_matched_comparison": str(Path(matched_input).resolve()),
        "prior_matched_comparison_sha256": _sha256(Path(matched_input)),
        "publication_qa_input": str(Path(publication_csv).resolve()),
        "publication_qa_input_sha256": _sha256(Path(publication_csv)),
        "sources": {
            "market_cap_db": str(Path(market_cap_db).resolve()),
            "market_cap_db_sha256": _sha256(Path(market_cap_db)),
            "canonical_db": str(Path(canonical_db).resolve()),
            "canonical_db_sha256": _sha256(Path(canonical_db)),
            "ohlc_db": str(Path(ohlc_db).resolve()),
            "ohlc_db_sha256": _sha256(Path(ohlc_db)),
            "forecasts_db": str(Path(forecasts_db).resolve()),
            "forecasts_db_sha256": _sha256(Path(forecasts_db)),
        },
        "proxies": {
            "liquidity": "median(close * volume) over observed D-20 through D-1; minimum 15 observations",
            "volatility": "sample standard deviation of close-to-close percent returns ending D-1; up to 20 returns; minimum 15",
            "pre_event_only": True,
        },
        "bucket_cutoffs": {key: list(value) for key, value in result.cutoffs.items()},
        "matching": {
            "ratio": "1:1",
            "replacement": False,
            "never_relaxed": [
                "event_year",
                "market_cap_bucket",
                "absolute_gap_bucket",
                "pre_event_trend_bucket",
                "sector",
            ],
            "relaxation_order": [
                "A_EXACT_ALL",
                "B_ADJACENT_LIQUIDITY",
                "C_ADJACENT_LIQUIDITY_AND_VOLATILITY",
            ],
        },
        "summary": result.summary,
        **dict(extra_summary),
        "output_csv": str(output.resolve()),
        "output_csv_sha256": _sha256(output),
    }
    metadata_path = Path(output_metadata)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return metadata


def run_composition_research(
    event_csv: str | Path,
    event_metadata: str | Path,
    matched_input: str | Path,
    market_cap_db: str | Path,
    canonical_db: str | Path,
    ohlc_db: str | Path,
    forecasts_db: str | Path,
    publication_csv: str | Path,
    output_csv: str | Path,
    output_metadata: str | Path,
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    rows, metadata = load_event_window(event_csv, event_metadata)
    if metadata.get("counts", {}).get("method_counts", {}).get(YAHOO_METHOD) != 483:
        raise ValueError("YAHOO_NEAR_METHOD_COUNT_INVALID")
    validate_prior_matched_comparison(matched_input)
    classifications = load_ticker_classifications(ohlc_db)
    population = [row for row in rows if row.get("research_method") in {YAHOO_METHOD, EXACT_METHOD}]
    context = load_pre_event_context(population, ohlc_db)
    result = build_yahoo_near_matched_comparison(
        rows,
        load_latest_market_caps(market_cap_db),
        classifications,
        context,
    )
    period_ends, patterns = load_period_ends_and_calendar_patterns(canonical_db, result.prepared_rows)
    surprises = load_latest_eps_surprises(forecasts_db, period_ends)
    yahoo_distance = load_yahoo_distance(publication_csv)
    extra = {
        "earnings_surprise_check": summarize_eps_surprises(result.rows, surprises),
        "foreign_calendar_composition": summarize_foreign_calendar(result.prepared_rows, patterns),
        "manual_qa": select_manual_qa(result.rows, yahoo_distance),
    }
    return write_composition_outputs(
        result,
        output_csv,
        output_metadata,
        event_csv=event_csv,
        event_metadata=event_metadata,
        matched_input=matched_input,
        market_cap_db=market_cap_db,
        canonical_db=canonical_db,
        ohlc_db=ohlc_db,
        forecasts_db=forecasts_db,
        publication_csv=publication_csv,
        extra_summary=extra,
        generated_at_utc=generated_at_utc,
    )
