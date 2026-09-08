from __future__ import annotations

import hashlib
import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.operating_income_v2 import valuation
from rawcandle.fundamentals.relative_position.engine import (
    CURRENT_FRESHNESS_DAYS,
    MINIMUM_PEERS,
    EcosystemMembership,
    RelativeMeasure,
    RelativeObservation,
    calculate_snapshot,
)


MODEL_VERSION = "CURRENTLY_REVISED_RELATIVE_VALUATION_V1"
CURRENT_PRICE_MAX_AGE_DAYS = 7
FILING_PRICE_MAX_AGE_DAYS = 3
HISTORY_YEARS = 5
HISTORY_ENDPOINT_CAP = 20
READY_MINIMUM = 12
LIMITED_MINIMUM = 8
COMPONENTS = ("OPERATING_YIELD", "FCF_YIELD", "REPORTED_EARNINGS_YIELD")
WEIGHTS = {"OPERATING_YIELD": 0.4, "FCF_YIELD": 0.4, "REPORTED_EARNINGS_YIELD": 0.2}


class ComponentHistoryStatus(str, Enum):
    READY = "COMPONENT_HISTORY_READY"
    LIMITED = "COMPONENT_HISTORY_LIMITED"
    INSUFFICIENT = "COMPONENT_HISTORY_INSUFFICIENT"
    CURRENT_YIELD_NONPOSITIVE = "CURRENT_YIELD_NONPOSITIVE"
    CURRENT_COMPONENT_MISSING = "CURRENT_COMPONENT_MISSING"
    CURRENT_COMPONENT_NONFINITE = "CURRENT_COMPONENT_NONFINITE"
    CURRENT_VALUATION_NOT_READY = "CURRENT_VALUATION_NOT_READY"
    NOT_APPLICABLE = "VALUATION_NOT_APPLICABLE"


class OwnHistoryStatus(str, Enum):
    READY = "READY"
    LIMITED = "LIMITED_HISTORY"
    INSUFFICIENT = "INSUFFICIENT_HISTORY"
    CURRENT_YIELD_NOT_COMPARABLE = "CURRENT_YIELD_NOT_COMPARABLE"
    CURRENT_VALUATION_NOT_READY = "CURRENT_VALUATION_NOT_READY"
    NOT_APPLICABLE = "NOT_APPLICABLE"


MODEL_CONTRACT = {
    "model_version": MODEL_VERSION,
    "semantic_mode": "CURRENTLY_REVISED_NOT_PIT",
    "absolute_valuation": {
        "model_version": valuation.MODEL_VERSION,
        "model_fingerprint": valuation.MODEL_FINGERPRINT,
        "current_price": "latest_complete_valid_ohlc_on_or_before_as_of",
        "maximum_age_calendar_days": CURRENT_PRICE_MAX_AGE_DAYS,
        "fundamental_anchor": "latest_eligible_ttm_endpoint",
        "split_adjustment": None,
    },
    "filing_price_maximum_age_calendar_days": FILING_PRICE_MAX_AGE_DAYS,
    "current_fundamental_freshness_days": CURRENT_FRESHNESS_DAYS,
    "history": {
        "window_years": HISTORY_YEARS,
        "endpoint_cap": HISTORY_ENDPOINT_CAP,
        "order": "authoritative_fiscal_sequence",
        "positive_observations_selected_independently_per_component": True,
        "nonconsecutive_allowed": True,
        "interpolation": None,
    },
    "component_percentile": "100*(less_count+0.5*equal_count)/n",
    "median_even_count": "arithmetic_mean_of_two_middle_values",
    "ready_minimum_positive_observations": READY_MINIMUM,
    "limited_minimum_positive_observations": LIMITED_MINIMUM,
    "weights": WEIGHTS,
    "missing_component_reweighting": False,
    "peer": {
        "formula": "100*(average_rank-1)/(peer_count-1)",
        "ties": "exact_binary64_midrank",
        "minimums": {scope.value: count for scope, count in MINIMUM_PEERS.items()},
        "taxonomy_roles": ["CORE", "EXTENDED"],
        "company_deduplication": "once_per_ecosystem",
        "taxonomy_layer_ranking": False,
        "fallback": None,
    },
    "status_precedence": [
        "VALUATION_NOT_APPLICABLE",
        "CURRENT_FUNDAMENTAL_STALE_OR_VALUATION_NOT_READY",
        "CURRENT_COMPONENT_MISSING_OR_NONFINITE_OR_NONPOSITIVE",
        "INSUFFICIENT_POSITIVE_HISTORY",
        "LIMITED_HISTORY",
        "READY",
    ],
}


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _plain_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return json.loads(canonical_json(value))


MODEL_FINGERPRINT = hashlib.sha256(canonical_json(MODEL_CONTRACT).encode("ascii")).hexdigest()


@dataclass(frozen=True)
class HistoricalEndpoint:
    fiscal_sequence: int
    fiscal_year: int
    fiscal_quarter: str
    available_date: str
    valuation_status: str
    market_cap: float | None
    enterprise_value: float | None
    ttm_operating_income: float | None
    ttm_free_cashflow: float | None
    ttm_reported_common_earnings: float | None


@dataclass(frozen=True)
class RelativeValuationInput:
    company_id: int | None
    security_id: int | None
    ticker: str | None
    sector: str | None
    industry: str | None
    ecosystem_memberships: tuple[EcosystemMembership, ...]
    endpoint_available_date: str
    current_fresh: bool
    valuation_observation: valuation.ValuationObservation
    price_bars: tuple[valuation.PriceBar, ...]
    filing_valuation: Mapping[str, Any] | None
    filing_peer_results: tuple[Mapping[str, Any], ...]
    history: tuple[HistoricalEndpoint, ...]


@dataclass(frozen=True)
class ComponentHistoryResult:
    component: str
    current_yield: float | None
    historical_median_positive_yield: float | None
    historical_percentile: float | None
    component_observation_count: int
    positive_history_count: int
    nonpositive_history_count: int
    missing_or_invalid_history_count: int
    component_first_observation_date: str | None
    component_last_observation_date: str | None
    positive_history_start_date: str | None
    positive_history_end_date: str | None
    component_history_status: str
    reason_code: str


@dataclass(frozen=True)
class OwnHistoryResult:
    status: str
    reason_code: str
    percentile: float | None
    window_start_date: str
    window_end_date: str
    minimum_component_positive_history_count: int
    selected_endpoint_count: int
    fiscal_gap_count: int
    components: tuple[ComponentHistoryResult, ...]


@dataclass(frozen=True)
class CompanyRelativeValuationResult:
    company_id: int | None
    security_id: int | None
    ticker: str | None
    endpoint_available_date: str
    current_fresh: bool
    current_valuation: Mapping[str, Any]
    filing_valuation: Mapping[str, Any] | None
    score_change_due_to_current_price: float | None
    current_peer_results: tuple[Mapping[str, Any], ...]
    current_peer_coverage: tuple[Mapping[str, Any], ...]
    filing_peer_results: tuple[Mapping[str, Any], ...]
    own_history: OwnHistoryResult


@dataclass(frozen=True)
class RelativeValuationSnapshot:
    model_version: str
    model_fingerprint: str
    semantic_mode: str
    as_of_date: str
    source_fingerprint: str
    result_fingerprint: str
    companies: tuple[CompanyRelativeValuationResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return canonical_json(self.to_dict())


def subtract_calendar_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def historical_percentile(values: Sequence[float], current: float) -> float:
    if not values:
        raise ValueError("HISTORICAL_POPULATION_EMPTY")
    less = sum(value < current for value in values)
    equal = sum(value == current for value in values)
    return 100.0 * (less + 0.5 * equal) / len(values)


def select_history(
    history: Sequence[HistoricalEndpoint], *, as_of_date: str
) -> tuple[tuple[HistoricalEndpoint, ...], str, int]:
    end = date.fromisoformat(as_of_date)
    start = subtract_calendar_years(end, HISTORY_YEARS)
    selected = sorted(
        (
            row for row in history
            if row.valuation_status == "VALUATION_FULL"
            and start <= date.fromisoformat(row.available_date) <= end
        ),
        key=lambda row: (row.fiscal_sequence, row.available_date),
    )[-HISTORY_ENDPOINT_CAP:]
    gaps = sum(
        max(right.fiscal_sequence - left.fiscal_sequence - 1, 0)
        for left, right in zip(selected, selected[1:])
    )
    return tuple(selected), start.isoformat(), gaps


def calculate_current_price_valuation(
    observation: valuation.ValuationObservation,
    price_bars: Sequence[valuation.PriceBar],
    *,
    as_of_date: str,
) -> dict[str, Any]:
    selected = valuation.select_price(price_bars, as_of_date)
    base = {
        "price_date": selected.price_date,
        "price_age_calendar_days": selected.price_age_calendar_days,
        "selected_price": selected.selected_price,
    }
    if selected.selected_price is None or selected.price_date is None:
        return {**base, "valuation_status": "VALUATION_NOT_READY", "reason_code": selected.reason_code or "PRICE_MISSING"}
    if selected.price_age_calendar_days is None or selected.price_age_calendar_days > CURRENT_PRICE_MAX_AGE_DAYS:
        return {**base, "valuation_status": "VALUATION_NOT_READY", "reason_code": "CURRENT_PRICE_FALLBACK_TOO_OLD"}
    selected_bar = next(
        bar for bar in price_bars if bar.price_date == selected.price_date
    )
    current_observation = valuation.ValuationObservation(
        **{
            **asdict(observation),
            "fundamental_available_date": selected.price_date,
        }
    )
    result = valuation.calculate_valuation(current_observation, (selected_bar,)).to_dict()
    result.update(base)
    result["fundamental_anchor_available_date"] = observation.fundamental_available_date
    return result


def _raw_history_value(endpoint: HistoricalEndpoint, component: str) -> tuple[str, float | None]:
    if component == "OPERATING_YIELD":
        numerator, denominator = endpoint.ttm_operating_income, endpoint.enterprise_value
    elif component == "FCF_YIELD":
        numerator, denominator = endpoint.ttm_free_cashflow, endpoint.market_cap
    else:
        numerator, denominator = endpoint.ttm_reported_common_earnings, endpoint.market_cap
    numerator_value, denominator_value = _finite(numerator), _finite(denominator)
    if numerator_value is None or denominator_value is None or denominator_value <= 0:
        return "INVALID", None
    if numerator_value <= 0:
        return "NONPOSITIVE", numerator_value / denominator_value
    return "POSITIVE", numerator_value / denominator_value


def _current_key(component: str) -> str:
    return {
        "OPERATING_YIELD": "operating_income_yield",
        "FCF_YIELD": "fcf_yield",
        "REPORTED_EARNINGS_YIELD": "earnings_yield",
    }[component]


def calculate_own_history(
    current_valuation: Mapping[str, Any],
    history: Sequence[HistoricalEndpoint],
    *,
    as_of_date: str,
    current_fresh: bool,
) -> OwnHistoryResult:
    selected, window_start, gap_count = select_history(history, as_of_date=as_of_date)
    status = str(current_valuation.get("valuation_status") or "VALUATION_NOT_READY")
    component_results = []
    for component in COMPONENTS:
        raw_current = current_valuation.get(_current_key(component))
        current = _finite(raw_current)
        positive: list[tuple[str, float]] = []
        nonpositive = invalid = 0
        for endpoint in selected:
            kind, value = _raw_history_value(endpoint, component)
            if kind == "POSITIVE":
                assert value is not None
                positive.append((endpoint.available_date, value))
            elif kind == "NONPOSITIVE":
                nonpositive += 1
            else:
                invalid += 1
        if status == "VALUATION_NOT_APPLICABLE":
            component_status = ComponentHistoryStatus.NOT_APPLICABLE
            reason = "VALUATION_NOT_APPLICABLE"
        elif status != "VALUATION_FULL" or not current_fresh:
            component_status = ComponentHistoryStatus.CURRENT_VALUATION_NOT_READY
            reason = "CURRENT_FUNDAMENTAL_ENDPOINT_STALE" if not current_fresh else "CURRENT_VALUATION_NOT_READY"
        elif raw_current is None:
            component_status = ComponentHistoryStatus.CURRENT_COMPONENT_MISSING
            reason = "CURRENT_COMPONENT_MISSING"
        elif current is None:
            component_status = ComponentHistoryStatus.CURRENT_COMPONENT_NONFINITE
            reason = "CURRENT_COMPONENT_NONFINITE"
        elif current <= 0:
            component_status = ComponentHistoryStatus.CURRENT_YIELD_NONPOSITIVE
            reason = {
                "OPERATING_YIELD": "CURRENT_OPERATING_YIELD_NONPOSITIVE",
                "FCF_YIELD": "CURRENT_FCF_YIELD_NONPOSITIVE",
                "REPORTED_EARNINGS_YIELD": "CURRENT_REPORTED_EARNINGS_YIELD_NONPOSITIVE",
            }[component]
        elif len(positive) >= READY_MINIMUM:
            component_status = ComponentHistoryStatus.READY
            reason = "SUFFICIENT_POSITIVE_HISTORY"
        elif len(positive) >= LIMITED_MINIMUM:
            component_status = ComponentHistoryStatus.LIMITED
            reason = "LIMITED_POSITIVE_HISTORY"
        else:
            component_status = ComponentHistoryStatus.INSUFFICIENT
            reason = "INSUFFICIENT_POSITIVE_HISTORY"
        values = [value for _, value in positive]
        emit = (
            current is not None
            and current > 0
            and len(values) >= LIMITED_MINIMUM
            and component_status in {ComponentHistoryStatus.READY, ComponentHistoryStatus.LIMITED}
        )
        component_results.append(
            ComponentHistoryResult(
                component=component,
                current_yield=current,
                historical_median_positive_yield=statistics.median(values) if values else None,
                historical_percentile=historical_percentile(values, current) if emit else None,
                component_observation_count=len(selected),
                positive_history_count=len(values),
                nonpositive_history_count=nonpositive,
                missing_or_invalid_history_count=invalid,
                component_first_observation_date=(selected[0].available_date if selected else None),
                component_last_observation_date=(selected[-1].available_date if selected else None),
                positive_history_start_date=positive[0][0] if positive else None,
                positive_history_end_date=positive[-1][0] if positive else None,
                component_history_status=component_status.value,
                reason_code=reason,
            )
        )
    component_statuses = {row.component_history_status for row in component_results}
    if status == "VALUATION_NOT_APPLICABLE":
        aggregate_status, reason = OwnHistoryStatus.NOT_APPLICABLE, "VALUATION_NOT_APPLICABLE"
    elif status != "VALUATION_FULL" or not current_fresh:
        aggregate_status, reason = OwnHistoryStatus.CURRENT_VALUATION_NOT_READY, "CURRENT_VALUATION_NOT_READY"
    elif component_statuses & {
        ComponentHistoryStatus.CURRENT_YIELD_NONPOSITIVE.value,
        ComponentHistoryStatus.CURRENT_COMPONENT_MISSING.value,
        ComponentHistoryStatus.CURRENT_COMPONENT_NONFINITE.value,
    }:
        aggregate_status, reason = OwnHistoryStatus.CURRENT_YIELD_NOT_COMPARABLE, "CURRENT_COMPONENT_NOT_POSITIVE_FINITE"
    elif ComponentHistoryStatus.INSUFFICIENT.value in component_statuses:
        aggregate_status, reason = OwnHistoryStatus.INSUFFICIENT, "INSUFFICIENT_POSITIVE_HISTORY"
    elif ComponentHistoryStatus.LIMITED.value in component_statuses:
        aggregate_status, reason = OwnHistoryStatus.LIMITED, "LIMITED_POSITIVE_HISTORY"
    else:
        aggregate_status, reason = OwnHistoryStatus.READY, "SUFFICIENT_POSITIVE_HISTORY"
    can_emit = aggregate_status in {OwnHistoryStatus.READY, OwnHistoryStatus.LIMITED}
    percentile = (
        sum(WEIGHTS[row.component] * float(row.historical_percentile) for row in component_results)
        if can_emit
        else None
    )
    return OwnHistoryResult(
        status=aggregate_status.value,
        reason_code=reason,
        percentile=percentile,
        window_start_date=window_start,
        window_end_date=as_of_date,
        minimum_component_positive_history_count=min(row.positive_history_count for row in component_results),
        selected_endpoint_count=len(selected),
        fiscal_gap_count=gap_count,
        components=tuple(component_results),
    )


def calculate_relative_valuation(
    inputs: Sequence[RelativeValuationInput],
    *,
    as_of_date: str,
    classification_fingerprint: str,
    taxonomy_fingerprint: str,
) -> RelativeValuationSnapshot:
    date.fromisoformat(as_of_date)
    ordered = sorted(inputs, key=lambda row: (row.company_id if row.company_id is not None else -1, row.ticker or ""))
    company_ids = [row.company_id for row in ordered if row.company_id is not None]
    if len(company_ids) != len(set(company_ids)):
        raise ValueError("RELATIVE_VALUATION_DUPLICATE_COMPANY_ID")
    current_rows: list[dict[str, Any]] = []
    peer_inputs = []
    own_rows: list[OwnHistoryResult] = []
    for row in ordered:
        current = calculate_current_price_valuation(row.valuation_observation, row.price_bars, as_of_date=as_of_date)
        current_rows.append(current)
        own_rows.append(
            calculate_own_history(
                current,
                row.history,
                as_of_date=as_of_date,
                current_fresh=row.current_fresh,
            )
        )
        eligible = row.current_fresh and current.get("valuation_status") == "VALUATION_FULL"
        peer_inputs.append(
            RelativeObservation(
                source_observation_id=f"relative_valuation:{row.company_id}:{row.valuation_observation.quarter_id}",
                company_id=row.company_id,
                security_id=row.security_id,
                ticker=row.ticker,
                measure=RelativeMeasure.ABSOLUTE_VALUATION_SCORE,
                score=current.get("total_valuation_score"),
                source_status=str(current.get("valuation_status")),
                source_eligible=eligible,
                eligibility_reason="ELIGIBLE" if eligible else ("SOURCE_OBSERVATION_STALE" if not row.current_fresh else str(current.get("reason_code"))),
                source_observation_date=row.endpoint_available_date,
                source_model_version=valuation.MODEL_VERSION,
                source_model_fingerprint=valuation.MODEL_FINGERPRINT,
                source_result_fingerprint=str(current.get("result_fingerprint") or hashlib.sha256(canonical_json(current).encode()).hexdigest()),
                sector=row.sector,
                industry=row.industry,
                ecosystem_memberships=row.ecosystem_memberships,
            )
        )
    peer = calculate_snapshot(
        peer_inputs,
        snapshot_date=as_of_date,
        freshness_days=CURRENT_FRESHNESS_DAYS,
        classification_fingerprint=classification_fingerprint,
        taxonomy_fingerprint=taxonomy_fingerprint,
    )
    companies = []
    for row, current, own_history in zip(ordered, current_rows, own_rows):
        filing_score = _finite((row.filing_valuation or {}).get("total_valuation_score"))
        current_score = _finite(current.get("total_valuation_score"))
        same_anchor = bool(
            row.filing_valuation
            and int(row.filing_valuation.get("quarter_id")) == row.valuation_observation.quarter_id
        )
        current_peer_results = []
        for result in peer.results:
            if result.company_id != row.company_id:
                continue
            payload = _plain_mapping(result.to_dict())
            payload["model_version"] = MODEL_VERSION
            payload["model_fingerprint"] = MODEL_FINGERPRINT
            current_peer_results.append(payload)
        companies.append(
            CompanyRelativeValuationResult(
                company_id=row.company_id,
                security_id=row.security_id,
                ticker=row.ticker,
                endpoint_available_date=row.endpoint_available_date,
                current_fresh=row.current_fresh,
                current_valuation=current,
                filing_valuation=row.filing_valuation,
                score_change_due_to_current_price=(current_score - filing_score if same_anchor and current_score is not None and filing_score is not None else None),
                current_peer_results=tuple(current_peer_results),
                current_peer_coverage=tuple(
                    _plain_mapping(record.to_dict())
                    for record in peer.coverage
                    if record.company_id == row.company_id
                ),
                filing_peer_results=row.filing_peer_results,
                own_history=own_history,
            )
        )
    source_payload = {
        "as_of_date": as_of_date,
        "classification_fingerprint": classification_fingerprint,
        "taxonomy_fingerprint": taxonomy_fingerprint,
        "inputs": [asdict(row) for row in ordered],
    }
    source_fp = hashlib.sha256(canonical_json(source_payload).encode("ascii")).hexdigest()
    fingerprint_payload = {
        "model_version": MODEL_VERSION,
        "model_fingerprint": MODEL_FINGERPRINT,
        "semantic_mode": "CURRENTLY_REVISED_NOT_PIT",
        "as_of_date": as_of_date,
        "source_fingerprint": source_fp,
        "companies": [asdict(row) for row in companies],
    }
    result_fp = hashlib.sha256(canonical_json(fingerprint_payload).encode("ascii")).hexdigest()
    return RelativeValuationSnapshot(
        model_version=MODEL_VERSION,
        model_fingerprint=MODEL_FINGERPRINT,
        semantic_mode="CURRENTLY_REVISED_NOT_PIT",
        as_of_date=as_of_date,
        source_fingerprint=source_fp,
        result_fingerprint=result_fp,
        companies=tuple(companies),
    )
