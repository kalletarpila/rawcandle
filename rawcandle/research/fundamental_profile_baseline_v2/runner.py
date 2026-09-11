from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy import stats

from rawcandle.fundamentals.phase12d import compare_production_inventory, production_inventory
from rawcandle.research.fundamental_profile_baseline.engine import benjamini_hochberg, partition_decision, spearman, stable_hash
from rawcandle.research.fundamental_profile_baseline.models import (
    calibration_rows,
    calibration_summary,
    classification_metrics,
    coefficient_rows,
    continuous_metrics,
    fit_baseline,
    predict,
)
from rawcandle.research.fundamental_profile_baseline.runner import eligibility_reason
from rawcandle.research.fundamental_profile_baseline.source import (
    ResearchPaths,
    build_research_rows,
    source_fingerprint,
)

from .contract import (
    BOOTSTRAP_REPETITIONS,
    COMPONENTS,
    CONTRACT,
    CONTRACT_FINGERPRINT,
    CONTRACT_VERSION,
    PERMUTATION_REPETITIONS,
    RANDOM_SEED,
)


PERIODS = ("DEVELOPMENT", "TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION", "FORWARD_REPORT_ONLY")
MODELS = ("B0", "B1", "B2", "B3", "B4")


@dataclass(frozen=True)
class RunResult:
    outcome: str
    contract_fingerprint: str
    source_fingerprint: str
    sample_fingerprint: str
    result_fingerprint: str
    output_dir: str


def _jsonable(value: Any) -> Any:
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(_jsonable(value), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True, separators=(",", ":")) if isinstance(value, (dict, list, tuple)) else value for key, value in row.items()})


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    entry_sessions = len({str(row["entry_date"]) for row in rows})
    return {
        "rows": len(rows),
        "companies": len({int(row["company_id"]) for row in rows}),
        "months": len({str(row["entry_date"])[:7] for row in rows}),
        "entry_sessions": entry_sessions,
        "effective_63_session_blocks": math.ceil(entry_sessions / 63),
        "first_entry": min((str(row["entry_date"]) for row in rows), default=None),
        "last_entry": max((str(row["entry_date"]) for row in rows), default=None),
        "first_exit": min((str(row["h63_exit_date"]) for row in rows if row.get("h63_exit_date")), default=None),
        "last_exit": max((str(row["h63_exit_date"]) for row in rows if row.get("h63_exit_date")), default=None),
    }


def window_boundaries(sessions: Sequence[str]) -> dict[str, Any]:
    first_validation = CONTRACT["periods"]["validation_first_entry_session"]
    first_confirmation = CONTRACT["periods"]["confirmation_first_entry_session"]
    first_2026 = CONTRACT["periods"]["reserved_2026_first_session"]
    index = {session: position for position, session in enumerate(sessions)}
    for session in (first_validation, first_confirmation, first_2026):
        if session not in index:
            raise RuntimeError(f"LOCKED_BOUNDARY_SESSION_MISSING:{session}")
    development_last_index = index[first_validation] - 64
    if development_last_index < 0:
        raise RuntimeError("DEVELOPMENT_BOUNDARY_NOT_DERIVABLE")
    return {
        "development_first_entry": "2021-01-04",
        "development_last_entry_session": sessions[development_last_index],
        "validation_first_entry_session": first_validation,
        "validation_last_entry_session": CONTRACT["periods"]["validation_last_entry_session"],
        "confirmation_first_entry_session": first_confirmation,
        "confirmation_last_entry_session": CONTRACT["periods"]["confirmation_last_entry_session"],
        "reserved_2026_first_session": first_2026,
        "session_indices": {session: index[session] for session in (first_validation, first_confirmation, first_2026)},
        "equality_rule": "earlier exit index must be strictly less than next first-entry index",
    }


def assign_corrected_periods(rows: list[dict[str, Any]], sessions: Sequence[str]) -> dict[str, Any]:
    boundaries = window_boundaries(sessions)
    index = {session: position for position, session in enumerate(sessions)}
    dev_last = str(boundaries["development_last_entry_session"])
    for row in rows:
        entry = row.get("entry_date")
        exit_date = row.get("h63_exit_date")
        row["period"] = None
        row["partition_status"] = "OUTSIDE_CORRECTED_WINDOWS"
        if entry is None:
            row["partition_status"] = "NO_TRADABLE_ENTRY"
        elif "2021-01-01" <= entry <= dev_last:
            row["period"] = "DEVELOPMENT"
            row["partition_status"] = "PRIMARY_LABEL_NOT_READY" if exit_date is None else "RETAINED" if index[exit_date] < index[boundaries["validation_first_entry_session"]] else "PURGED_AT_NEXT_PERIOD_BOUNDARY"
        elif "2023-07-01" <= entry <= "2024-06-30":
            row["period"] = "TEMPORAL_VALIDATION"
            row["partition_status"] = "PRIMARY_LABEL_NOT_READY" if exit_date is None else "RETAINED" if index[exit_date] < index[boundaries["confirmation_first_entry_session"]] else "PURGED_AT_NEXT_PERIOD_BOUNDARY"
        elif "2024-10-01" <= entry <= "2025-09-30":
            row["period"] = "RETROSPECTIVE_CONFIRMATION"
            row["partition_status"] = "PRIMARY_LABEL_NOT_READY" if exit_date is None else "RETAINED" if index[exit_date] < index[boundaries["reserved_2026_first_session"]] else "PURGED_AT_NEXT_PERIOD_BOUNDARY"
        elif "2026-01-01" <= entry <= "2026-12-31":
            row["period"] = "FORWARD_REPORT_ONLY"
            row["partition_status"] = "RETAINED" if row.get("h63_status") == "LABEL_READY" else "PRIMARY_LABEL_NOT_READY"
        row["feature_eligibility"] = eligibility_reason(row, require_label=False)
        row["common_eligibility"] = eligibility_reason(row, require_label=True)
    return boundaries


def retained(rows: Sequence[Mapping[str, Any]], period: str) -> list[Mapping[str, Any]]:
    return [row for row in rows if row.get("period") == period and row.get("partition_status") == "RETAINED" and row.get("common_eligibility") == "ELIGIBLE"]


def bootstrap_indices(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str], repetitions: int = BOOTSTRAP_REPETITIONS) -> list[np.ndarray]:
    session_index = {day: index for index, day in enumerate(sessions)}
    by_index: dict[int, list[int]] = defaultdict(list)
    for row_index, row in enumerate(rows):
        by_index[session_index[str(row["entry_date"])]].append(row_index)
    starts = sorted(by_index)
    rng = np.random.default_rng(RANDOM_SEED)
    output = []
    for _ in range(repetitions):
        selected: list[int] = []
        while len(selected) < len(rows):
            start = int(rng.choice(starts))
            for offset in range(63):
                selected.extend(by_index.get(start + offset, ()))
        output.append(np.asarray(selected[: len(rows)], dtype=np.int64))
    return output


def effect_value(rows: Sequence[Mapping[str, Any]], hypothesis: str) -> float | None:
    y = np.asarray([float(row["h63_excess_return"]) for row in rows])
    if hypothesis in {"H1", "H2", "H7"}:
        field = {"H1": "fundamental_score", "H2": "valuation_score", "H7": "diagnostic_flag_count"}[hypothesis]
        return spearman([float(row[field]) for row in rows], y.tolist())
    h4 = np.asarray([float(row["fundamental_score"]) >= 80 and float(row["valuation_score"]) >= 60 for row in rows])
    delta = np.asarray([float(row["two_quarter_delta"]) > 0 for row in rows])
    treatment = delta if hypothesis == "H3" else h4 if hypothesis == "H4" else h4 & delta
    comparator = ~delta if hypothesis == "H3" else ~h4 if hypothesis == "H4" else h4 & ~delta
    return float(y[treatment].mean() - y[comparator].mean()) if treatment.any() and comparator.any() else None


def arm_rows(rows: Sequence[Mapping[str, Any]], hypothesis: str) -> tuple[list[Mapping[str, Any]], list[Mapping[str, Any]]]:
    def h4(row: Mapping[str, Any]) -> bool:
        return float(row["fundamental_score"]) >= 80 and float(row["valuation_score"]) >= 60
    if hypothesis == "H3":
        treatment = lambda row: float(row["two_quarter_delta"]) > 0
        comparator = lambda row: float(row["two_quarter_delta"]) <= 0
    elif hypothesis == "H4":
        treatment, comparator = h4, lambda row: not h4(row)
    else:
        treatment = lambda row: h4(row) and float(row["two_quarter_delta"]) > 0
        comparator = lambda row: h4(row) and float(row["two_quarter_delta"]) <= 0
    return [row for row in rows if treatment(row)], [row for row in rows if comparator(row)]


def arm_summary(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    per_month = Counter(str(row["entry_date"])[:7] for row in rows)
    values = sorted(per_month.values())
    base = summary(rows)
    return {**base, "minimum_per_present_month": min(values) if values else 0, "median_per_present_month": statistics.median(values) if values else 0,
            "maximum_per_present_month": max(values) if values else 0,
            "largest_sector_share": max(Counter(str(row.get("sector") or "MISSING") for row in rows).values(), default=0) / len(rows) if rows else None,
            "largest_lifecycle_share": max(Counter(str(row.get("lifecycle") or "MISSING") for row in rows).values(), default=0) / len(rows) if rows else None}


def arm_gate(values: Mapping[str, Any], *, monthly_median: bool = True) -> bool:
    gate = CONTRACT["group_sample_gate"]
    return (
        values["rows"] >= gate["minimum_observations"]
        and values["companies"] >= gate["minimum_companies"]
        and values["months"] >= gate["minimum_calendar_months"]
        and values["entry_sessions"] >= gate["minimum_unique_entry_sessions"]
        and (not monthly_median or values["median_per_present_month"] >= gate["minimum_median_observations_per_present_month"])
    )


def bootstrap_test(rows: Sequence[Mapping[str, Any]], hypothesis: str, indices: Sequence[np.ndarray], direction: int) -> dict[str, Any]:
    observed = effect_value(rows, hypothesis)
    if observed is None:
        return {"effect": None, "ci_low": None, "ci_high": None, "raw_p": None}
    boot = [effect_value([rows[int(i)] for i in sample], hypothesis) for sample in indices]
    values = np.asarray([value for value in boot if value is not None and math.isfinite(value)], dtype=float)
    centered = values - observed
    if direction > 0:
        p_value = (1 + int(np.sum(centered >= observed))) / (len(centered) + 1)
    else:
        p_value = (1 + int(np.sum(centered <= observed))) / (len(centered) + 1)
    return {"effect": observed, "ci_low": float(np.quantile(values, 0.025)), "ci_high": float(np.quantile(values, 0.975)), "raw_p": float(p_value), "bootstrap_mean": float(values.mean())}


def concentration_survives(rows: Sequence[Mapping[str, Any]], hypothesis: str, direction: int) -> tuple[bool, list[dict[str, Any]]]:
    checks = []
    for dimension, field in (("COMPANY", "company_id"), ("SECTOR", "sector"), ("LIFECYCLE", "lifecycle")):
        largest = Counter(str(row.get(field) or "MISSING") for row in rows).most_common(1)[0][0]
        sample = [row for row in rows if str(row.get(field) or "MISSING") != largest]
        value = effect_value(sample, hypothesis)
        checks.append({"check": f"DROP_LARGEST_{dimension}", "removed_member": largest, "n": len(sample), "effect": value, "direction_survives": value is not None and value * direction > 0})
    y = np.asarray([float(row["h63_excess_return"]) for row in rows])
    low, high = np.quantile(y, [0.01, 0.99])
    winsor = [dict(row, h63_excess_return=float(np.clip(float(row["h63_excess_return"]), low, high))) for row in rows]
    value = effect_value(winsor, hypothesis)
    checks.append({"check": "WINSOR_TARGET_1_99", "removed_member": None, "n": len(rows), "effect": value, "direction_survives": value is not None and value * direction > 0})
    return all(row["direction_survives"] for row in checks), checks


def hypothesis_results(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    results, groups, robustness = [], [], []
    cache = {period: bootstrap_indices(retained(rows, period), sessions) for period in PERIODS[:3]}
    direction = {"H1": 1, "H2": 1, "H3": 1, "H4": 1, "H5": 1, "H7": -1}
    for period in PERIODS[:3]:
        members = retained(rows, period)
        for hypothesis in direction:
            test = bootstrap_test(members, hypothesis, cache[period], direction[hypothesis])
            gate_passed = True
            if hypothesis in {"H3", "H4", "H5"}:
                left, right = arm_rows(members, hypothesis)
                left_summary, right_summary = arm_summary(left), arm_summary(right)
                for arm, values in (("TREATMENT", left_summary), ("COMPARATOR", right_summary)):
                    groups.append({"hypothesis": hypothesis, "period": period, "arm": arm, **values, "gate_passed": arm_gate(values)})
                gate_passed = arm_gate(left_summary) and arm_gate(right_summary)
            survives, detail = concentration_survives(members, hypothesis, direction[hypothesis])
            robustness.extend({"hypothesis": hypothesis, "period": period, **item} for item in detail)
            stress_checks = []
            for view in ("MISSING_EXIT_NEUTRAL", "MISSING_EXIT_ADVERSE"):
                stress_sample = []
                for source in rows:
                    if source.get("period") != period or source.get("feature_eligibility") != "ELIGIBLE":
                        continue
                    target = source.get("h63_excess_return") if source.get("h63_status") == "LABEL_READY" else None
                    if source.get("h63_status") in {"MISSING_EXACT_EXIT_PRICE", "INSUFFICIENT_SESSION_COVERAGE"}:
                        target = 0.0 if view.endswith("NEUTRAL") else -1.0 - float(source.get("h63_benchmark_return") or 0.0)
                    if target is not None:
                        stress_sample.append(dict(source, h63_excess_return=target))
                value = effect_value(stress_sample, hypothesis)
                check = {"check": view, "removed_member": None, "n": len(stress_sample), "effect": value,
                         "direction_survives": value is not None and value * direction[hypothesis] > 0}
                stress_checks.append(check)
                robustness.append({"hypothesis": hypothesis, "period": period, **check})
            stress_survives = all(item["direction_survives"] for item in stress_checks)
            results.append({"hypothesis": hypothesis, "period": period, "expected_direction": direction[hypothesis], **summary(members), **test,
                            "sample_gate_passed": gate_passed, "concentration_direction_survives": survives,
                            "missing_exit_direction_survives": stress_survives,
                            "multiplicity_family": "CONFIRMATORY_STYLE_REPLAY", "raw_p": test["raw_p"] if gate_passed else None,
                            "status": "EVALUATED" if gate_passed else "NOT_TESTABLE_SAMPLE_GATE_FAILED"})
    for period in PERIODS[:3]:
        period_rows = [row for row in results if row["period"] == period and row["raw_p"] is not None]
        adjusted = benjamini_hochberg({row["hypothesis"]: row["raw_p"] for row in period_rows})
        for row in results:
            if row["period"] == period:
                row["adjusted_q"] = adjusted.get(row["hypothesis"])
                row["family_test_count"] = len(period_rows)
    for hypothesis, expected in direction.items():
        period_rows = [row for row in results if row["hypothesis"] == hypothesis]
        same = all(row["effect"] is not None and row["effect"] * expected > 0 for row in period_rows)
        later = [row for row in period_rows if row["period"] != "DEVELOPMENT"]
        repeated = same and all(row["sample_gate_passed"] and row["adjusted_q"] is not None and row["adjusted_q"] <= 0.10 and row["concentration_direction_survives"] and row["missing_exit_direction_survives"] and ((row["ci_low"] > 0) if expected > 0 else (row["ci_high"] < 0)) for row in later)
        classification = "REPEATED_EXPLORATORY_EVIDENCE" if repeated else "NOT_TESTABLE_SAMPLE_GATE_FAILED" if any(not row["sample_gate_passed"] for row in period_rows) else "WEAK_OR_UNCERTAIN_EVIDENCE" if same else "NO_REPEATED_EVIDENCE"
        for row in period_rows:
            row["evidence_class"] = classification
    return results, groups, robustness


def _design(rows: Sequence[Mapping[str, Any]], means: tuple[float, float], scales: tuple[float, float], categories: Sequence[str], full: bool) -> np.ndarray:
    values = []
    reference = "MATURE"
    encoded = [category for category in categories if category != reference]
    for row in rows:
        valuation = (float(row["valuation_score"]) - means[0]) / scales[0]
        delta = (float(row["two_quarter_delta"]) - means[1]) / scales[1]
        base = [1.0, valuation, delta] + [float(row["lifecycle"] == category) for category in encoded]
        if full:
            base += [valuation * float(row["lifecycle"] == category) for category in encoded]
            base += [delta * float(row["lifecycle"] == category) for category in encoded]
        values.append(base)
    return np.asarray(values, dtype=float)


def _ols_f(y: np.ndarray, base: np.ndarray, full: np.ndarray) -> tuple[float, float, np.ndarray, np.ndarray]:
    base_coef = np.linalg.lstsq(base, y, rcond=None)[0]
    full_coef = np.linalg.lstsq(full, y, rcond=None)[0]
    base_residual = y - base @ base_coef
    full_residual = y - full @ full_coef
    rss_base, rss_full = float(base_residual @ base_residual), float(full_residual @ full_residual)
    df_num, df_den = full.shape[1] - base.shape[1], len(y) - full.shape[1]
    f_value = ((rss_base - rss_full) / df_num) / (rss_full / df_den) if df_num > 0 and df_den > 0 and rss_full > 0 else 0.0
    partial_r2 = (rss_base - rss_full) / rss_base if rss_base > 0 else 0.0
    return max(f_value, 0.0), max(partial_r2, 0.0), base @ base_coef, base_residual


def h6_results(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> list[dict[str, Any]]:
    development = retained(rows, "DEVELOPMENT")
    val = np.asarray([float(row["valuation_score"]) for row in development])
    delta = np.asarray([float(row["two_quarter_delta"]) for row in development])
    means = (float(val.mean()), float(delta.mean()))
    scales = (float(val.std()) or 1.0, float(delta.std()) or 1.0)
    output = []
    for period in PERIODS[:3]:
        members = retained(rows, period)
        lifecycle_groups = []
        for lifecycle in sorted({str(row["lifecycle"]) for row in members}):
            group = [row for row in members if row["lifecycle"] == lifecycle]
            values = arm_summary(group)
            lifecycle_groups.append({"lifecycle": lifecycle, **values, "included": arm_gate(values, monthly_median=False)})
        included = [item["lifecycle"] for item in lifecycle_groups if item["included"]]
        sample = [row for row in members if row["lifecycle"] in included]
        status = "EVALUATED" if len(included) >= 2 else "NOT_TESTABLE_SAMPLE_GATE_FAILED"
        if status != "EVALUATED":
            output.append({"period": period, "status": status, "included_lifecycles": included, "group_audit": lifecycle_groups, **summary(sample), "partial_f": None, "partial_r2": None, "raw_p": None})
            continue
        base = _design(sample, means, scales, included, False)
        full = _design(sample, means, scales, included, True)
        y = np.asarray([float(row["h63_excess_return"]) for row in sample])
        observed, partial_r2, fitted, residual = _ols_f(y, base, full)
        by_block: dict[int, list[int]] = defaultdict(list)
        first_session = min(str(row["entry_date"]) for row in sample)
        session_index = {day: index for index, day in enumerate(sessions)}
        origin = session_index[first_session]
        for index_, row in enumerate(sample):
            by_block[(session_index[str(row["entry_date"])] - origin) // 63].append(index_)
        rng = np.random.default_rng(RANDOM_SEED)
        permuted = []
        for _ in range(PERMUTATION_REPETITIONS):
            shifted = residual.copy()
            for indices in by_block.values():
                shifted[indices] = rng.permutation(shifted[indices])
            permuted.append(_ols_f(fitted + shifted, base, full)[0])
        p_value = (1 + sum(value >= observed for value in permuted)) / (PERMUTATION_REPETITIONS + 1)
        block_samples = bootstrap_indices(sample, sessions)
        boot_r2 = []
        for selected in block_samples:
            boot_r2.append(_ols_f(y[selected], base[selected], full[selected])[1])
        slopes = {}
        for lifecycle in included:
            group = [row for row in sample if row["lifecycle"] == lifecycle]
            slopes[lifecycle] = {"valuation_spearman": spearman([float(row["valuation_score"]) for row in group], [float(row["h63_excess_return"]) for row in group]),
                                 "delta_spearman": spearman([float(row["two_quarter_delta"]) for row in group], [float(row["h63_excess_return"]) for row in group])}
        output.append({"period": period, "status": status, "included_lifecycles": included, "group_audit": lifecycle_groups, **summary(sample),
                       "partial_f": observed, "partial_r2": partial_r2, "raw_p": p_value, "adjusted_q": p_value,
                       "partial_r2_ci_low": float(np.quantile(boot_r2, 0.025)), "partial_r2_ci_high": float(np.quantile(boot_r2, 0.975)),
                       "permutations": PERMUTATION_REPETITIONS, "lifecycle_specific_effects": slopes})
    later = [row for row in output if row["period"] != "DEVELOPMENT"]
    repeated = all(row["status"] == "EVALUATED" and row["raw_p"] < 0.05 and row["partial_r2"] > 0 for row in later)
    for row in output:
        row["evidence_class"] = "REPEATED_EXPLORATORY_EVIDENCE" if repeated else "NOT_TESTABLE_SAMPLE_GATE_FAILED" if row["status"] != "EVALUATED" else "NO_REPEATED_EVIDENCE"
    return output


def model_results(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> tuple[dict[str, list[dict[str, Any]]], dict[str, Any]]:
    development = retained(rows, "DEVELOPMENT")
    fitted = {name: fit_baseline(development, name) for name in MODELS}
    continuous, classification, calibration, calibration_summaries, coefficients, predictions = [], [], [], [], [], []
    by_period_model: dict[tuple[str, str], tuple[list[Mapping[str, Any]], np.ndarray, np.ndarray]] = {}
    for name, model in fitted.items():
        coefficients.extend(coefficient_rows(model))
        for period in PERIODS:
            members = retained(rows, period)
            if not members:
                continue
            regression, probability = predict(model, members)
            by_period_model[(period, name)] = (members, regression, probability)
            continuous.append({"model": name, "period": period, **continuous_metrics(members, regression),
                               "prediction_std": float(np.std(regression)), "near_constant": float(np.std(regression)) < 1e-8})
            classification.append({"model": name, "period": period, **classification_metrics(members, probability),
                                   "prediction_std": float(np.std(probability)), "near_constant": float(np.std(probability)) < 1e-8})
            calibration.extend(calibration_rows(period, name, members, probability))
            calibration_summaries.append(calibration_summary(period, name, members, probability))
            predictions.extend({"company_id": row["company_id"], "quarter_id": row["quarter_id"], "period": period, "model": name,
                                "entry_date": row["entry_date"], "actual_excess": row["h63_excess_return"], "actual_positive": row["h63_positive_excess"],
                                "regression_prediction": float(reg), "classification_probability": float(prob)} for row, reg, prob in zip(members, regression, probability))
    comparisons, h8_intervals, metric_intervals = [], [], []
    for period in PERIODS[:3]:
        cont = {row["model"]: row for row in continuous if row["period"] == period}
        cls = {row["model"]: row for row in classification if row["period"] == period}
        for complex_, simple in (("B3", "B1"), ("B3", "B2"), ("B4", "B3")):
            comparisons.append({"period": period, "comparison": f"{complex_}_vs_{simple}",
                                "spearman_difference": (cont[complex_]["spearman"] or 0) - (cont[simple]["spearman"] or 0),
                                "brier_improvement": cls[simple]["brier"] - cls[complex_]["brier"]})
        members, b4_reg, b4_prob = by_period_model[(period, "B4")]
        _, b3_reg, b3_prob = by_period_model[(period, "B3")]
        actual = [float(row["h63_excess_return"]) for row in members]
        binary = np.asarray([int(row["h63_positive_excess"]) for row in members])
        indices = bootstrap_indices(members, sessions)
        actual_np = np.asarray(actual)
        for name in MODELS:
            _, regression, probability = by_period_model[(period, name)]
            spearman_boot, brier_boot = [], []
            for sample in indices:
                value = spearman(regression[sample].tolist(), actual_np[sample].tolist())
                if value is not None:
                    spearman_boot.append(value)
                brier_boot.append(float(np.mean((probability[sample] - binary[sample]) ** 2)))
            metric_intervals.append({"model": name, "period": period, "metric": "SPEARMAN", "point": next(row["spearman"] for row in continuous if row["model"] == name and row["period"] == period),
                                     "ci_low": float(np.quantile(spearman_boot, 0.025)) if spearman_boot else None, "ci_high": float(np.quantile(spearman_boot, 0.975)) if spearman_boot else None})
            metric_intervals.append({"model": name, "period": period, "metric": "BRIER", "point": next(row["brier"] for row in classification if row["model"] == name and row["period"] == period),
                                     "ci_low": float(np.quantile(brier_boot, 0.025)), "ci_high": float(np.quantile(brier_boot, 0.975))})
        point_s = (spearman(b4_reg.tolist(), actual) or 0) - (spearman(b3_reg.tolist(), actual) or 0)
        point_b = float(np.mean((b3_prob - binary) ** 2) - np.mean((b4_prob - binary) ** 2))
        boot_s, boot_b = [], []
        for sample in indices:
            boot_s.append((spearman(b4_reg[sample].tolist(), actual_np[sample].tolist()) or 0) - (spearman(b3_reg[sample].tolist(), actual_np[sample].tolist()) or 0))
            boot_b.append(float(np.mean((b3_prob[sample] - binary[sample]) ** 2) - np.mean((b4_prob[sample] - binary[sample]) ** 2)))
        h8_intervals.append({"period": period, "spearman_improvement": point_s, "spearman_ci_low": float(np.quantile(boot_s, 0.025)), "spearman_ci_high": float(np.quantile(boot_s, 0.975)),
                             "brier_improvement": point_b, "brier_ci_low": float(np.quantile(boot_b, 0.025)), "brier_ci_high": float(np.quantile(boot_b, 0.975))})
    h8 = CONTRACT["hypotheses"]["H8"]
    required = [row for row in h8_intervals if row["period"] in {"TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION"}]
    passed = all(row["spearman_improvement"] >= h8["minimum_regression_improvement"] and row["brier_improvement"] >= h8["minimum_classification_improvement"] and row["spearman_ci_low"] > 0 and row["brier_ci_low"] > 0 for row in required)
    h8_result = {"hypothesis": "H8", "passed": passed, "evidence_class": "REPEATED_EXPLORATORY_EVIDENCE" if passed else "NO_REPEATED_EVIDENCE", "periods": h8_intervals}
    return {"continuous": continuous, "classification": classification, "calibration": calibration, "calibration_summary": calibration_summaries,
            "coefficients": coefficients, "predictions": predictions, "comparisons": comparisons, "h8_intervals": h8_intervals,
            "metric_intervals": metric_intervals}, h8_result


def component_results(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    results, quantiles, robustness = [], [], []
    caps = {"REVENUE_GROWTH": 20.0, "OPERATING_PROFITABILITY": 15.0, "OPERATING_MARGIN_DIRECTION": 15.0,
            "FCF_MARGIN": 15.0, "BALANCE_SHEET_RESILIENCE": 15.0, "FUNDAMENTAL_TRAJECTORY": 10.0, "DILUTION": 10.0}
    development = retained(rows, "DEVELOPMENT")
    cuts = {}
    for component in COMPONENTS:
        field = f"component_{component.lower()}"
        values = np.asarray([float(row[field]) for row in development if row.get(field) is not None])
        cuts[component] = np.quantile(values, [0.2, 0.4, 0.6, 0.8]).tolist() if len(values) else []
    for period in PERIODS[:3]:
        members = retained(rows, period)
        indices = bootstrap_indices(members, sessions)
        period_rows = []
        for component in COMPONENTS:
            field = f"component_{component.lower()}"
            evidence_field = f"{field}_evidence_json"
            observed = [row for row in members if row.get(field) is not None]
            points = [float(row[field]) for row in observed]
            target = [float(row["h63_excess_return"]) for row in observed]
            effect = spearman(points, target)
            boot = []
            for sample in indices:
                sample_rows = [members[int(i)] for i in sample if members[int(i)].get(field) is not None]
                value = spearman([float(row[field]) for row in sample_rows], [float(row["h63_excess_return"]) for row in sample_rows])
                if value is not None:
                    boot.append(value)
            centered = np.asarray(boot) - float(effect)
            p_value = (1 + int(np.sum(np.abs(centered) >= abs(float(effect))))) / (len(centered) + 1)
            raw_values = []
            raw_status = Counter()
            for row in observed:
                evidence = json.loads(row.get(evidence_field) or "{}")
                metric = evidence.get("metric_value")
                if isinstance(metric, (int, float)) and math.isfinite(float(metric)):
                    raw_values.append(float(metric))
                raw_status[str(evidence.get("value_status") or "MISSING")] += 1
            item = {"component": component, "period": period, **summary(observed), "coverage": len(observed) / len(members) if members else None,
                    "missing": len(members) - len(observed), "point_mean": statistics.fmean(points) if points else None, "point_ceiling_rate": sum(value >= caps[component] for value in points) / len(points) if points else None,
                    "raw_metric_mean": statistics.fmean(raw_values) if raw_values else None, "raw_metric_n": len(raw_values), "raw_value_statuses": dict(raw_status),
                    "spearman": effect, "ci_low": float(np.quantile(boot, 0.025)), "ci_high": float(np.quantile(boot, 0.975)), "raw_p": p_value,
                    "multiplicity_family": "SEVEN_COMPONENT_EXPLORATORY"}
            period_rows.append(item)
            for dimension, key in (("COMPANY", "company_id"), ("SECTOR", "sector"), ("LIFECYCLE", "lifecycle")):
                largest = Counter(str(row.get(key) or "MISSING") for row in observed).most_common(1)[0][0]
                selected = [row for row in observed if str(row.get(key) or "MISSING") != largest]
                value = spearman([float(row[field]) for row in selected], [float(row["h63_excess_return"]) for row in selected])
                robustness.append({"component": component, "period": period, "check": f"DROP_LARGEST_{dimension}", "removed_member": largest,
                                   "n": len(selected), "spearman": value, "same_direction": value is not None and effect is not None and value * effect > 0})
            y = np.asarray(target)
            low, high = np.quantile(y, [0.01, 0.99])
            value = spearman(points, np.clip(y, low, high).tolist())
            robustness.append({"component": component, "period": period, "check": "WINSOR_TARGET_1_99", "removed_member": None,
                               "n": len(observed), "spearman": value, "same_direction": value is not None and effect is not None and value * effect > 0})
            for band in range(5):
                selected = [row for row in observed if int(np.searchsorted(cuts[component], float(row[field]), side="right")) == band]
                quantiles.append({"component": component, "period": period, "development_fixed_band": band + 1, **summary(selected),
                                  "mean_excess": statistics.fmean(float(row["h63_excess_return"]) for row in selected) if selected else None})
        adjusted = benjamini_hochberg({row["component"]: row["raw_p"] for row in period_rows})
        for row in period_rows:
            row["adjusted_q"] = adjusted[row["component"]]
            row["family_test_count"] = len(period_rows)
        results.extend(period_rows)
    return results, quantiles, robustness


def interval_audit(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    index = {day: position for position, day in enumerate(sessions)}
    output = []
    for period in PERIODS[:3]:
        for row in retained(rows, period):
            output.append({"company_id": row["company_id"], "quarter_id": row["quarter_id"], "fiscal_year": row["fiscal_year"], "fiscal_quarter": row["fiscal_quarter"],
                           "availability_date": row["source_availability_date"], "entry_date": row["entry_date"], "entry_session_index": index[row["entry_date"]],
                           "exit_date": row["h63_exit_date"], "exit_session_index": index[row["h63_exit_date"]], "period": period,
                           "label_status": row["h63_status"], "boundary_decision": row["partition_status"]})
    duplicate = len(output) - len({(row["company_id"], row["quarter_id"]) for row in output})
    maximum = {period: max((row["exit_session_index"] for row in output if row["period"] == period), default=None) for period in PERIODS[:3]}
    minimum = {period: min((row["entry_session_index"] for row in output if row["period"] == period), default=None) for period in PERIODS[:3]}

    def overlap_count(period: str) -> int:
        intervals = sorted({
            (row["entry_session_index"], row["exit_session_index"])
            for row in output if row["period"] == period
        })
        return sum(
            1
            for index_, (_, exit_index) in enumerate(intervals)
            for next_entry, _ in intervals[index_ + 1 :]
            if next_entry <= exit_index
        )

    checks = {
        "duplicate_endpoints": duplicate,
        "development_before_validation": maximum["DEVELOPMENT"] < minimum["TEMPORAL_VALIDATION"],
        "validation_before_confirmation": maximum["TEMPORAL_VALIDATION"] < minimum["RETROSPECTIVE_CONFIRMATION"],
        "confirmation_before_2026": maximum["RETROSPECTIVE_CONFIRMATION"] < index[CONTRACT["periods"]["reserved_2026_first_session"]],
        "all_exact_63_offsets": all(row["exit_session_index"] - row["entry_session_index"] == 63 for row in output),
        "within_period_unique_interval_overlap_pairs": {
            period: overlap_count(period) for period in PERIODS[:3]
        },
    }
    checks["passed"] = duplicate == 0 and all(value for key, value in checks.items() if key != "duplicate_endpoints")
    return output, checks


def reconciliation(original_dir: Path, hypotheses: Sequence[Mapping[str, Any]], models: Mapping[str, Sequence[Mapping[str, Any]]], cohort: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output = []
    original_h = list(csv.DictReader((original_dir / "primary_hypothesis_results.csv").open()))
    for row in hypotheses:
        match = next((item for item in original_h if item["hypothesis"] == row["hypothesis"] and item["period"] == row["period"]), None)
        output.append({"kind": "HYPOTHESIS", "identity": row["hypothesis"], "period": row["period"], "original_effect": match.get("effect") if match else None,
                       "corrected_effect": row["effect"], "original_status": match.get("evidence_class") if match else None, "corrected_status": row["evidence_class"]})
    for filename, key in (("continuous_model_results.csv", "continuous"), ("classification_model_results.csv", "classification")):
        original = list(csv.DictReader((original_dir / filename).open()))
        for row in models[key]:
            if row["period"] not in PERIODS[:3]:
                continue
            match = next((item for item in original if item["model"] == row["model"] and item["period"] == row["period"]), None)
            metric = "spearman" if key == "continuous" else "roc_auc"
            output.append({"kind": key.upper(), "identity": row["model"], "period": row["period"], "metric": metric,
                           "original_effect": match.get(metric) if match else None, "corrected_effect": row[metric]})
    return output


def cohort_reconciliation(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> dict[str, Any]:
    original: dict[str, set[tuple[int, int]]] = defaultdict(set)
    corrected: dict[str, set[tuple[int, int]]] = defaultdict(set)
    labels = {}
    for row in rows:
        key = (int(row["company_id"]), int(row["quarter_id"]))
        if row.get("entry_date"):
            old_period, old_status = partition_decision(entry_date=row["entry_date"], exit_date_63=row.get("h63_exit_date"), benchmark_sessions=sessions)
            if old_period in PERIODS[:3] and old_status == "RETAINED" and eligibility_reason(row, require_label=True) == "ELIGIBLE":
                original[old_period].add(key)
                labels[key] = row.get("h63_excess_return")
        if row.get("period") in PERIODS[:3] and row.get("partition_status") == "RETAINED" and row.get("common_eligibility") == "ELIGIBLE":
            corrected[str(row["period"])].add(key)
            labels[key] = row.get("h63_excess_return")
    periods = []
    for period in PERIODS[:3]:
        shared = original[period] & corrected[period]
        periods.append({"period": period, "original_rows": len(original[period]), "corrected_rows": len(corrected[period]),
                        "shared_same_named_period": len(shared), "newly_included": len(corrected[period] - original[period]),
                        "excluded_from_original_period": len(original[period] - corrected[period])})
    all_original = set().union(*original.values())
    all_corrected = set().union(*corrected.values())
    common = all_original & all_corrected
    return {"periods": periods, "all_original": len(all_original), "all_corrected": len(all_corrected),
            "retained_in_both_any_period": len(common), "newly_included_any_period": len(all_corrected - all_original),
            "excluded_any_period": len(all_original - all_corrected),
            "common_label_fingerprint": stable_hash([{"company_id": key[0], "quarter_id": key[1], "h63_excess_return": labels[key]} for key in sorted(common)])}


def render_report(decision: Mapping[str, Any], cohort: Sequence[Mapping[str, Any]], hypotheses: Sequence[Mapping[str, Any]], groups: Sequence[Mapping[str, Any]], h6: Sequence[Mapping[str, Any]], h8: Mapping[str, Any], models: Mapping[str, Sequence[Mapping[str, Any]]], components: Sequence[Mapping[str, Any]], checks: Mapping[str, Any]) -> str:
    lines = ["# Phase 12B.2 Methodology-Corrected Replay", "", f"**{decision['outcome']}**", "", "Status: `REVISED_HISTORY_EXPLORATORY_ONLY`", "",
             "## Cohorts", "", "| Period | Rows | Companies | Months | Sessions | First entry | Last entry | Last exit |", "| --- | ---: | ---: | ---: | ---: | --- | --- | --- |"]
    for period in PERIODS:
        values = summary(retained(cohort, period))
        lines.append(f"| {period} | {values['rows']:,} | {values['companies']:,} | {values['months']} | {values['entry_sessions']} | {values['first_entry']} | {values['last_entry']} | {values['last_exit']} |")
    lines += ["", f"Cross-period label audit passed: `{checks['passed']}`.",
              f"Within-period overlapping unique label-interval pairs: `{checks['within_period_unique_interval_overlap_pairs']}`.",
              "", "## H1-H8", "", "| H | Period | Effect | 95% CI | p | q | Gate | Status |", "| --- | --- | ---: | --- | ---: | ---: | --- | --- |"]
    for row in hypotheses:
        lines.append(f"| {row['hypothesis']} | {row['period']} | {row['effect']} | [{row['ci_low']}, {row['ci_high']}] | {row['raw_p']} | {row['adjusted_q']} | {row['sample_gate_passed']} | {row['evidence_class']} |")
    for row in h6:
        lines.append(f"| H6 | {row['period']} | partial R2={row.get('partial_r2')} | [{row.get('partial_r2_ci_low')}, {row.get('partial_r2_ci_high')}] | {row.get('raw_p')} | {row.get('adjusted_q')} | {row['status']} | {row['evidence_class']} |")
    lines.append(f"| H8 | Validation + Confirmation | B4 vs B3 | paired block intervals | | | {h8['passed']} | {h8['evidence_class']} |")
    lines += ["", "## H4/H5 arm gates", "", "| H | Period | Arm | Rows | Companies | Months | Sessions | Gate |", "| --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for row in groups:
        if row["hypothesis"] in {"H4", "H5"}:
            lines.append(f"| {row['hypothesis']} | {row['period']} | {row['arm']} | {row['rows']} | {row['companies']} | {row['months']} | {row['entry_sessions']} | {row['gate_passed']} |")
    lines += ["", "## B0-B4", "", "| Model | Period | Spearman | RMSE | AUC | Brier |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    continuous = {(row["model"], row["period"]): row for row in models["continuous"]}
    classification = {(row["model"], row["period"]): row for row in models["classification"]}
    for key, row in continuous.items():
        cls = classification[key]
        lines.append(f"| {key[0]} | {key[1]} | {row['spearman']} | {row['rmse']} | {cls['roc_auc']} | {cls['brier']} |")
    lines += ["", "## Components", "", "| Component | Period | Point Spearman | 95% CI | q |", "| --- | --- | ---: | --- | ---: |"]
    for row in components:
        lines.append(f"| {row['component']} | {row['period']} | {row['spearman']} | [{row['ci_low']}, {row['ci_high']}] | {row['adjusted_q']} |")
    lines += ["", "The corrected study is retrospective, revised-history, non-PIT, and not authorization for production modeling or investment use.", ""]
    return "\n".join(lines)


def run(paths: ResearchPaths, output_dir: Path, *, contract_fingerprint: str, original_dir: Path) -> RunResult:
    if contract_fingerprint != CONTRACT_FINGERPRINT:
        raise ValueError("PHASE12B2_CONTRACT_FINGERPRINT_MISMATCH")
    output_dir = output_dir.resolve()
    if "temp" not in output_dir.parts or output_dir.exists():
        raise ValueError("PHASE12B2_NEW_TEMP_OUTPUT_REQUIRED")
    output_dir.mkdir(parents=True)
    preflight = production_inventory()
    write_json(output_dir / "production_preflight.json", preflight)
    rows, sessions = build_research_rows(paths, include_phase12a_reconciliation=False)
    source_fp = source_fingerprint(rows)
    if source_fp != CONTRACT["input_identity"]["accepted_source_fingerprint"]:
        raise RuntimeError("PHASE12B2_SOURCE_FINGERPRINT_DRIFT")
    boundaries = assign_corrected_periods(rows, sessions)
    intervals, interval_checks = interval_audit(rows, sessions)
    if not interval_checks["passed"]:
        raise RuntimeError("PHASE12B2_LABEL_INTERVAL_AUDIT_FAILED")
    cohort = []
    for period in PERIODS:
        cohort.append({"period": period, **summary(retained(rows, period)), "month_list": sorted({str(row["entry_date"])[:7] for row in retained(rows, period)})})
    for period in ("TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION"):
        if next(row for row in cohort if row["period"] == period)["months"] != 12:
            raise RuntimeError(f"PHASE12B2_TWELVE_MONTH_GATE_FAILED:{period}")
    sample_fp = stable_hash([{key: row.get(key) for key in ("company_id", "quarter_id", "entry_date", "h63_exit_date", "h63_excess_return", "period", "partition_status", "common_eligibility")} for row in rows])
    hypotheses, groups, robustness = hypothesis_results(rows, sessions)
    h6 = h6_results(rows, sessions)
    models, h8 = model_results(rows, sessions)
    components, component_quantiles, component_robustness = component_results(rows, sessions)
    classes = {row["hypothesis"]: row["evidence_class"] for row in hypotheses if row["period"] == "TEMPORAL_VALIDATION"}
    classes["H6"] = next(row["evidence_class"] for row in h6 if row["period"] == "TEMPORAL_VALIDATION")
    classes["H8"] = h8["evidence_class"]
    repeated_core = [name for name in ("H1", "H2", "H3", "H4", "H5", "H7") if classes[name] == "REPEATED_EXPLORATORY_EVIDENCE"]
    h6_repeated = classes["H6"] == "REPEATED_EXPLORATORY_EVIDENCE"
    outcome_code = "A" if h8["passed"] and repeated_core else "B" if repeated_core or h6_repeated else "C"
    outcome = {
        "A": "OUTCOME A - CORRECTED RESEARCH WINDOWS AND METHODS PRODUCE REPEATED EVIDENCE SUFFICIENT FOR A SEPARATE MODEL-CANDIDATE PHASE",
        "B": "OUTCOME B - SOME REPEATABLE ASSOCIATIONS EXIST, BUT NO PRODUCTION MODEL IS JUSTIFIED",
        "C": "OUTCOME C - NO REPEATABLE EVIDENCE UNDER THE CORRECTED CONTRACT",
    }[outcome_code]
    decision = {"outcome": outcome, "outcome_code": outcome_code, "hypothesis_classes": classes, "repeated_core_hypotheses": repeated_core,
                "h8_passed": h8["passed"], "status": CONTRACT["status"], "production_authorized": False}
    original_reconciliation = reconciliation(original_dir, hypotheses, models, rows)
    cohort_comparison = cohort_reconciliation(rows, sessions)
    monthly = []
    for month in [f"{year}-{month:02d}" for year in range(2021, 2027) for month in range(1, 13)]:
        members = [row for row in rows if row.get("entry_date") and str(row["entry_date"])[:7] == month]
        final = [row for row in members if row.get("partition_status") == "RETAINED" and row.get("common_eligibility") == "ELIGIBLE"]
        monthly.append({"month": month, "all_entry_rows": len(members), "final_rows": len(final), "companies": len({row["company_id"] for row in final}),
                        "assigned_periods": sorted({row["period"] for row in final}),
                        "partition_status_counts": dict(sorted(Counter(str(row.get("partition_status")) for row in members).items())),
                        "common_eligibility_counts": dict(sorted(Counter(str(row.get("common_eligibility")) for row in members).items()))})
    write_json(output_dir / "locked_corrected_contract.json", {"contract": CONTRACT, "fingerprint": CONTRACT_FINGERPRINT})
    logical_sources = {
        "phase12d_candidate": "candidate_a",
        "canonical_database": paths.canonical_db.name,
        "analysis_database": paths.analysis_db.name,
        "provider_database": paths.provider_db.name,
        "market_database": paths.market_db.name,
        "taxonomy_database": paths.taxonomy_db.name,
    }
    write_json(output_dir / "source_manifest.json", {"source_fingerprint": source_fp, "logical_sources": logical_sources, "accepted_market_hash": CONTRACT["input_identity"]["accepted_market_sha256"], "current_market_hash": preflight["databases"]["market"]["sha256"]})
    write_json(output_dir / "sample_manifest.json", {"sample_fingerprint": sample_fp, "cohorts": cohort})
    write_json(output_dir / "session_boundary_derivation.json", boundaries)
    write_csv(output_dir / "period_assignment_table.csv", [{"company_id": row["company_id"], "quarter_id": row["quarter_id"], "entry_date": row.get("entry_date"), "exit_date": row.get("h63_exit_date"), "period": row.get("period"), "partition_status": row.get("partition_status"), "common_eligibility": row.get("common_eligibility")} for row in rows])
    write_csv(output_dir / "label_interval_non_overlap_audit.csv", intervals)
    write_json(output_dir / "label_interval_non_overlap_summary.json", interval_checks)
    write_csv(output_dir / "monthly_cohort_waterfall.csv", monthly)
    write_csv(output_dir / "h1_h8_results.csv", hypotheses + [{"hypothesis": "H6", **row} for row in h6])
    write_csv(output_dir / "h3_h4_h5_group_size_audit.csv", groups)
    write_json(output_dir / "h6_interaction_results.json", h6)
    write_json(output_dir / "h8_model_gate.json", h8)
    multiplicity_rows = list(hypotheses) + [
        {"hypothesis": "H6", "period": row["period"], "raw_p": row.get("raw_p"), "adjusted_q": row.get("adjusted_q"),
         "multiplicity_family": "H6_EXPLORATORY_SINGLE_TEST", "family_test_count": 1, "status": row["status"],
         "effect": row.get("partial_r2"), "ci_low": row.get("partial_r2_ci_low"), "ci_high": row.get("partial_r2_ci_high")}
        for row in h6
    ] + [
        {"hypothesis": "H8", "period": row["period"], "raw_p": None, "adjusted_q": None,
         "multiplicity_family": "H8_COMPOUND_MODEL_GATE", "family_test_count": 1,
         "status": "PASSED" if h8["passed"] else "NOT_PASSED",
         "effect": row["spearman_improvement"], "ci_low": row["spearman_ci_low"], "ci_high": row["spearman_ci_high"],
         "classification_effect": row["brier_improvement"], "classification_ci_low": row["brier_ci_low"],
         "classification_ci_high": row["brier_ci_high"]}
        for row in h8["periods"]
    ] + list(components)
    write_csv(output_dir / "multiple_testing_table.csv", multiplicity_rows)
    write_csv(output_dir / "seven_component_annual_results.csv", components)
    write_csv(output_dir / "seven_component_fixed_band_results.csv", component_quantiles)
    write_csv(output_dir / "seven_component_robustness_results.csv", component_robustness)
    for name, values in models.items():
        write_csv(output_dir / f"b0_b4_{name}.csv", values)
    write_csv(output_dir / "robustness_results.csv", robustness)
    write_csv(output_dir / "original_vs_corrected_reconciliation.csv", original_reconciliation)
    write_json(output_dir / "original_vs_corrected_cohort_reconciliation.json", cohort_comparison)
    write_json(output_dir / "decision.json", decision)
    report = render_report(decision, rows, hypotheses, groups, h6, h8, models, components, interval_checks)
    (output_dir / "PHASE12B2_CORRECTED_REPLAY_REPORT.md").write_text(report, encoding="utf-8")
    postflight = production_inventory()
    write_json(output_dir / "production_postflight.json", postflight)
    isolation = compare_production_inventory(preflight, postflight)
    write_json(output_dir / "production_immutability.json", isolation)
    if not isolation["identical"]:
        raise RuntimeError("PHASE12B2_PRODUCTION_IMMUTABILITY_FAILED")
    excluded = {"production_preflight.json", "production_postflight.json", "production_immutability.json", "commands_run.txt", "artifact_manifest.json"}
    economic = {path.name: sha256(path) for path in sorted(output_dir.iterdir()) if path.is_file() and path.name not in excluded}
    result_fp = stable_hash(economic)
    write_json(output_dir / "artifact_manifest.json", {"economic_artifacts": economic, "result_fingerprint": result_fp})
    (output_dir / "commands_run.txt").write_text("python3 -m rawcandle.cli.run_phase12b2_corrected_replay --output <new-temp-path>\n", encoding="utf-8")
    return RunResult(outcome, CONTRACT_FINGERPRINT, source_fp, sample_fp, result_fp, str(output_dir))
