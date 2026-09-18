from __future__ import annotations

import json
from collections import defaultdict
from statistics import mean
from typing import Any, Mapping, Sequence

from .score_math import (
    ANCHORS, balance_points, clamp, fiscal_ordinal, piecewise_score, safe_div, safe_growth,
)

# Keep the established scoring arithmetic and evidence schema while V2 owns its execution.
COMPONENTS = (
    "REVENUE_GROWTH", "EBIT_PROFITABILITY", "EBIT_MARGIN_DIRECTION",
    "FCF_MARGIN", "BALANCE_SHEET_RESILIENCE", "DILUTION", "FUNDAMENTAL_TRAJECTORY",
)
TRAJECTORY_TOLERANCES = {
    "revenue_qoq_ttm": 0.05,
    "ebit_margin_change_qoq": 0.05,
    "fcf_change_to_prior_revenue": 0.10,
}

def _number(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _continuous_chain(rows: Mapping[int, Mapping[str, Any]], start: int, end: int) -> bool:
    return all(ordinal in rows for ordinal in range(start, end + 1))


def _structural_regime(row: Mapping[str, Any] | None) -> str | None:
    if row is None:
        return None
    value = row.get("structural_regime_id")
    return str(value) if value not in {None, ""} else None


def _structural_ready(row: Mapping[str, Any] | None) -> bool:
    if row is None:
        return False
    status = row.get("structural_readiness_status")
    return status in {None, "", "STRUCTURAL_READY"}


def _same_structural_regime(current: Mapping[str, Any], other: Mapping[str, Any] | None) -> bool:
    if other is None:
        return False
    current_regime = _structural_regime(current)
    other_regime = _structural_regime(other)
    if current_regime is None and other_regime is None:
        return True
    return current_regime == other_regime and _structural_ready(current) and _structural_ready(other)


def _structural_chain_ok(rows: Mapping[int, Mapping[str, Any]], start: int, end: int) -> bool:
    window = [rows.get(ordinal) for ordinal in range(start, end + 1)]
    if any(row is None for row in window):
        return False
    regimes = {_structural_regime(row) for row in window}
    if regimes == {None}:
        return True
    return len(regimes) == 1 and all(_structural_ready(row) for row in window)


def _metric_levels(row: Mapping[str, Any], previous_year: Mapping[str, Any] | None, chain_ok: bool) -> dict[str, float | None]:
    revenue = _number(row.get("ttm_revenue"))
    ebit = _number(row.get("ttm_ebit"))
    fcf = _number(row.get("ttm_free_cashflow"))
    previous_revenue = _number(previous_year.get("ttm_revenue")) if previous_year and chain_ok else None
    previous_ebit = _number(previous_year.get("ttm_ebit")) if previous_year and chain_ok else None
    current_margin = safe_div(ebit, revenue) if revenue is not None and revenue > 0 else None
    previous_margin = safe_div(previous_ebit, previous_revenue) if previous_revenue is not None and previous_revenue > 0 else None
    return {
        "revenue_growth_yoy_ttm": safe_growth(revenue, previous_revenue),
        "ebit_margin_ttm": current_margin,
        "ebit_margin_direction": None if current_margin is None or previous_margin is None else current_margin - previous_margin,
        "fcf_margin_ttm": safe_div(fcf, revenue) if revenue is not None and revenue > 0 else None,
    }


def _split_matches(
    ticker: str,
    previous: Mapping[str, Any] | None,
    current: Mapping[str, Any],
    events: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, Any]]:
    if previous is None:
        return []
    start = str(previous["period_end"])
    end = str(current["period_end"])
    return [dict(event) for event in events.get(ticker, ()) if start < str(event["split_date"]) <= end]


def _evidence(
    *, metric: str, value: float | None, inputs: Mapping[str, Any], observed: bool,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    evidence = {
        "metric": metric,
        "metric_value": value,
        "inputs": dict(inputs),
        "value_status": "OBSERVED" if observed else "MISSING",
    }
    if extra:
        evidence.update(extra)
    return evidence


def trajectory_points(
    endpoint_ordinal: int,
    rows_by_ordinal: Mapping[int, Mapping[str, Any]],
) -> tuple[float | None, dict[str, Any]]:
    ordinals = list(range(endpoint_ordinal - 4, endpoint_ordinal + 1))
    window = [rows_by_ordinal.get(ordinal) for ordinal in ordinals]
    base_evidence: dict[str, Any] = {
        "required_ttm_snapshots": 5,
        "required_qoq_transitions": 4,
        "fiscal_ordinals": ordinals,
        "tolerances": TRAJECTORY_TOLERANCES,
    }
    if any(row is None for row in window):
        return None, {**base_evidence, "blocker": "NON_CONTIGUOUS_FIVE_SNAPSHOT_WINDOW"}
    snapshots = [row for row in window if row is not None]
    if not _structural_chain_ok(rows_by_ordinal, endpoint_ordinal - 4, endpoint_ordinal):
        return None, {**base_evidence, "blocker": "STRUCTURAL_REGIME_INCOMPATIBLE"}
    if any(int(row.get("core_ttm_ready") or 0) != 1 for row in snapshots):
        return None, {**base_evidence, "blocker": "WINDOW_TTM_NOT_CORE_READY"}
    if any(_number(row.get("ttm_revenue")) is None or float(row["ttm_revenue"]) <= 0.0 for row in snapshots):
        return None, {**base_evidence, "blocker": "WINDOW_REVENUE_NOT_POSITIVE"}
    if any(_number(row.get("ttm_ebit")) is None or _number(row.get("ttm_free_cashflow")) is None for row in snapshots):
        return None, {**base_evidence, "blocker": "WINDOW_EBIT_OR_FCF_MISSING"}

    transitions: list[dict[str, Any]] = []
    metric_points: dict[str, list[float]] = defaultdict(list)
    for previous, current in zip(snapshots, snapshots[1:]):
        previous_revenue = float(previous["ttm_revenue"])
        current_revenue = float(current["ttm_revenue"])
        revenue_signal = current_revenue / previous_revenue - 1.0
        previous_ebit_margin = float(previous["ttm_ebit"]) / previous_revenue
        current_ebit_margin = float(current["ttm_ebit"]) / current_revenue
        ebit_signal = current_ebit_margin - previous_ebit_margin
        fcf_signal = (float(current["ttm_free_cashflow"]) - float(previous["ttm_free_cashflow"])) / previous_revenue
        signals = {
            "revenue_qoq_ttm": revenue_signal,
            "ebit_margin_change_qoq": ebit_signal,
            "fcf_change_to_prior_revenue": fcf_signal,
        }
        points = {
            metric: clamp(5.0 + 5.0 * signal / TRAJECTORY_TOLERANCES[metric], 0.0, 10.0)
            for metric, signal in signals.items()
        }
        for metric, value in points.items():
            metric_points[metric].append(value)
        transitions.append({
            "from_quarter_id": previous["endpoint_quarter_id"],
            "to_quarter_id": current["endpoint_quarter_id"],
            "from_period_end": previous["period_end"],
            "to_period_end": current["period_end"],
            "signals": signals,
            "points": points,
        })
    metric_averages = {metric: mean(values) for metric, values in metric_points.items()}
    total = mean(metric_averages.values())
    return total, {
        **base_evidence,
        "blocker": None,
        "transition_scoring": "clamp(5 + 5 * signal / tolerance, 0, 10)",
        "metric_average_points": metric_averages,
        "transitions": transitions,
    }


def compute_score_rows(
    ttm_rows: Sequence[Mapping[str, Any]],
    split_events: Mapping[str, Sequence[Mapping[str, Any]]],
    *, generated_at: str,
    run_id: str,
    model_version: str,
    model_fingerprint: str,
) -> list[dict[str, Any]]:
    grouped: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in ttm_rows:
        grouped[int(row["company_id"])].append(row)
    output: list[dict[str, Any]] = []

    for company_rows in grouped.values():
        ordered = sorted(company_rows, key=lambda row: (fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"]), int(row["ttm_id"])))
        by_ordinal = {fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"]): row for row in ordered}
        levels: dict[int, dict[str, float | None]] = {}
        for row in ordered:
            ordinal = fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"])
            chain_ok = (
                _continuous_chain(by_ordinal, ordinal - 4, ordinal)
                and _structural_chain_ok(by_ordinal, ordinal - 4, ordinal)
            )
            levels[ordinal] = _metric_levels(row, by_ordinal.get(ordinal - 4), chain_ok)

        for row in ordered:
            ordinal = fiscal_ordinal(row["endpoint_fiscal_year"], row["endpoint_fiscal_quarter"])
            previous_year = by_ordinal.get(ordinal - 4)
            previous_quarter = by_ordinal.get(ordinal - 1)
            chain_ok = (
                _continuous_chain(by_ordinal, ordinal - 4, ordinal)
                and _structural_chain_ok(by_ordinal, ordinal - 4, ordinal)
            )
            current = levels[ordinal]
            shares = _number(row.get("shares_outstanding"))
            previous_shares = _number(previous_year.get("shares_outstanding")) if previous_year and chain_ok else None
            prior_quarter_shares = (
                _number(previous_quarter.get("shares_outstanding"))
                if _same_structural_regime(row, previous_quarter)
                else None
            )
            share_change_yoy = safe_growth(shares, previous_shares)
            share_change_qoq = safe_growth(shares, prior_quarter_shares)
            ticker = str(row["ticker"])
            split_matches = _split_matches(ticker, previous_year if chain_ok else None, row, split_events)
            trajectory, trajectory_evidence = trajectory_points(ordinal, by_ordinal)

            scores = {
                "REVENUE_GROWTH": piecewise_score(current["revenue_growth_yoy_ttm"], ANCHORS["revenue_growth_yoy_ttm"]),
                "EBIT_PROFITABILITY": piecewise_score(current["ebit_margin_ttm"], ANCHORS["ebit_margin_ttm"]),
                "EBIT_MARGIN_DIRECTION": piecewise_score(current["ebit_margin_direction"], ANCHORS["ebit_margin_direction"]),
                "FCF_MARGIN": piecewise_score(current["fcf_margin_ttm"], ANCHORS["fcf_margin_ttm"]),
                "BALANCE_SHEET_RESILIENCE": balance_points(row),
                "DILUTION": piecewise_score(share_change_yoy, ANCHORS["share_change_yoy"]),
                "FUNDAMENTAL_TRAJECTORY": trajectory,
            }
            evidence = {
                "REVENUE_GROWTH": _evidence(metric="revenue_growth_yoy_ttm", value=current["revenue_growth_yoy_ttm"], inputs={"ttm_revenue_current": row.get("ttm_revenue"), "ttm_revenue_4q_ago": previous_year.get("ttm_revenue") if previous_year and chain_ok else None}, observed=scores["REVENUE_GROWTH"] is not None, extra={"continuous_fiscal_chain": chain_ok}),
                "EBIT_PROFITABILITY": _evidence(metric="ebit_margin_ttm", value=current["ebit_margin_ttm"], inputs={"ttm_ebit": row.get("ttm_ebit"), "ttm_revenue": row.get("ttm_revenue")}, observed=scores["EBIT_PROFITABILITY"] is not None),
                "EBIT_MARGIN_DIRECTION": _evidence(metric="ebit_margin_direction", value=current["ebit_margin_direction"], inputs={"ebit_margin_current": current["ebit_margin_ttm"], "ebit_margin_4q_ago": levels.get(ordinal - 4, {}).get("ebit_margin_ttm") if chain_ok else None}, observed=scores["EBIT_MARGIN_DIRECTION"] is not None, extra={"continuous_fiscal_chain": chain_ok}),
                "FCF_MARGIN": _evidence(metric="fcf_margin_ttm", value=current["fcf_margin_ttm"], inputs={"ttm_free_cashflow": row.get("ttm_free_cashflow"), "ttm_revenue": row.get("ttm_revenue")}, observed=scores["FCF_MARGIN"] is not None),
                "BALANCE_SHEET_RESILIENCE": _evidence(metric="balance_sheet_resilience", value=scores["BALANCE_SHEET_RESILIENCE"], inputs={"cash": row.get("cash"), "total_debt": row.get("total_debt"), "ttm_ebit": row.get("ttm_ebit"), "ttm_free_cashflow": row.get("ttm_free_cashflow")}, observed=scores["BALANCE_SHEET_RESILIENCE"] is not None),
                "DILUTION": _evidence(metric="share_change_yoy", value=share_change_yoy, inputs={"shares_current": shares, "shares_4q_ago": previous_shares}, observed=scores["DILUTION"] is not None, extra={"share_change_qoq_evidence_only": share_change_qoq, "split_events_evidence_only": split_matches, "split_adjustment_applied": False, "large_positive_change_policy": "ASSUMED_GENUINE_DILUTION_BY_POLICY" if share_change_yoy is not None and share_change_yoy > 0.50 else "NOT_APPLICABLE"}),
                "FUNDAMENTAL_TRAJECTORY": _evidence(metric="fundamental_trajectory_points", value=trajectory, inputs={"window": "five_contiguous_ttm_snapshots", "transition_count": 4}, observed=trajectory is not None, extra=trajectory_evidence),
            }

            structural_ready = _structural_ready(row)
            structural_reason = row.get("structural_reason_code")
            if not structural_ready:
                for name in COMPONENTS:
                    scores[name] = None
                    evidence[name] = {
                        **evidence[name],
                        "value_status": "STRUCTURAL_NOT_READY",
                        "structural_readiness_status": row.get("structural_readiness_status"),
                        "structural_reason_code": structural_reason,
                        "structural_regime_id": row.get("structural_regime_id"),
                    }

            current_ready = (
                int(row.get("core_ttm_ready") or 0) == 1
                and bool(row.get("ttm_source_available_date"))
                and structural_ready
            )
            imputed_components: list[str] = []

            missing = [name for name in COMPONENTS if scores[name] is None]
            observed = [name for name in COMPONENTS if scores[name] is not None and name not in imputed_components]
            observed_points = sum(float(scores[name]) for name in observed)
            imputed_points = sum(float(scores[name]) for name in imputed_components)
            if not current_ready:
                status = "SCORE_NOT_READY"
                total_score = None
            elif not missing and not imputed_components:
                status = "SCORE_FULL"
                total_score = observed_points
            else:
                status = "SCORE_LIMITED"
                total_score = observed_points + imputed_points

            status_detail = {
                "missing_components": missing,
                "observed_components": observed,
                "imputed_components": imputed_components,
                "observed_component_count": len(observed),
                "observed_points": observed_points,
                "imputed_points": imputed_points,
                "ttm_core_ready": bool(row.get("core_ttm_ready")),
                "ttm_source_available_date": row.get("ttm_source_available_date"),
            }
            if row.get("structural_readiness_status") is not None:
                status_detail.update({
                    "structural_readiness_status": row.get("structural_readiness_status"),
                    "structural_reason_code": structural_reason,
                    "structural_regime_id": row.get("structural_regime_id"),
                    "structural_contract_fingerprint": row.get("structural_contract_fingerprint"),
                })
            output.append({
                "company_id": int(row["company_id"]),
                "quarter_id": int(row["endpoint_quarter_id"]),
                "ticker": ticker,
                "period_end": row["period_end"],
                "model_version": model_version,
                "model_fingerprint": model_fingerprint,
                "total_score": total_score,
                "readiness_status": status,
                "missing_input_reason": json.dumps(status_detail, sort_keys=True, separators=(",", ":")),
                "generated_at_utc": generated_at,
                "run_id": run_id,
                "components": [
                    {"component_name": name, "component_score": scores[name], "evidence_json": json.dumps(evidence[name], sort_keys=True, separators=(",", ":"))}
                    for name in COMPONENTS
                ],
            })
    return sorted(output, key=lambda item: (item["company_id"], item["quarter_id"]))
