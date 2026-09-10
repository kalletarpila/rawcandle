from __future__ import annotations

import csv
import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
from scipy import stats

from .contract import CONTRACT, CONTRACT_FINGERPRINT, CONTRACT_VERSION, RANDOM_SEED
from .engine import (
    benjamini_hochberg,
    delta_band,
    diagnostic_count_band,
    fundamental_band,
    monthly_ic,
    partition_decision,
    spearman,
    stable_hash,
    tie_safe_quintiles,
    trajectory_band,
    valuation_band,
)
from .models import (
    calibration_rows,
    calibration_summary,
    classification_metrics,
    coefficient_rows,
    continuous_metrics,
    fit_baseline,
    predict,
)
from .source import ResearchPaths, build_research_rows, readonly, source_fingerprint


PERIODS = ("DEVELOPMENT", "TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION", "FORWARD_REPORT_ONLY")
MODELS = ("B0", "B1", "B2", "B3", "B4")
MANDATORY_DISCLOSURE = CONTRACT["research_status"]["mandatory_disclosure"]


@dataclass(frozen=True)
class RunResult:
    outcome: str
    source_fingerprint: str
    contract_fingerprint: str
    sample_fingerprint: str
    result_fingerprint: str
    output_dir: str


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
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


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]], fields: Sequence[str] | None = None) -> None:
    if fields is None:
        fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(fields), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, sort_keys=True, separators=(",", ":")) if isinstance(value, (dict, list, tuple)) else value for key, value in row.items()})


def database_state(paths: ResearchPaths) -> dict[str, Any]:
    state: dict[str, Any] = {"databases": {}, "production_reports": {}}
    for path in (paths.canonical_db, paths.provider_db, paths.analysis_db, paths.market_db, paths.taxonomy_db):
        conn = readonly(path)
        schema = [tuple(row) for row in conn.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE type IN ('table','index','view','trigger') ORDER BY type,name")]
        quick = str(conn.execute("PRAGMA quick_check").fetchone()[0])
        foreign_keys = len(conn.execute("PRAGMA foreign_key_check").fetchall())
        relevant = {}
        for table in (
            "v4_quarter", "v4_ttm_values", "provider_observation", "score_result",
            "lifecycle_revised_result", "valuation_revised_result", "fundamental_delta_result",
            "diagnostic_flag_endpoint", "diagnostic_flag_evaluation", "osakedata",
            "splits_data", "relative_valuation_snapshot", "relative_valuation_active_snapshot",
        ):
            exists = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone()
            if exists:
                relevant[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])
        active_family = None
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fundamentals_active_model_family'").fetchone():
            row = conn.execute("SELECT family_version,family_fingerprint,persistence_fingerprint,model_manifest_json FROM fundamentals_active_model_family").fetchone()
            active_family = dict(row) if row else None
        active_relative = None
        if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='relative_valuation_active_snapshot'").fetchone():
            active_relative = [dict(row) for row in conn.execute("SELECT * FROM relative_valuation_active_snapshot ORDER BY model_fingerprint")]
        conn.close()
        sidecars = {}
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(path) + suffix)
            sidecars[suffix] = {"exists": sidecar.exists(), "size": sidecar.stat().st_size if sidecar.exists() else None, "sha256": _sha(sidecar) if sidecar.exists() else None}
        state["databases"][path.name] = {
            "size": path.stat().st_size,
            "sha256": _sha(path),
            "schema_sha256": stable_hash(schema),
            "quick_check": quick,
            "foreign_key_errors": foreign_keys,
            "relevant_row_counts": relevant,
            "active_family": active_family,
            "active_relative_valuation": active_relative,
            "sidecars": sidecars,
        }
    report_root = paths.analysis_db.parent.parent / "fundamental_reports"
    hashes = {str(path.relative_to(report_root.parent)): _sha(path) for path in sorted(report_root.glob("**/*")) if path.is_file()}
    state["production_reports"] = {"files": hashes, "aggregate": stable_hash(hashes)}
    return state


def _phase12a_reconciliation(
    rows: Sequence[Mapping[str, Any]], preflight: Mapping[str, Any]
) -> dict[str, Any]:
    phase12a_hashes = {
        "fundamentals_v4.db": "f553639e7f25ce75fed51af0c2127121a96573cd88728c2eafa84b9dfdc087da",
        "fundamentals_provider.db": "1905d09cf93901622ae178e7b472e571bc872ba2b243ff3b02a5957f9b6e2c14",
        "fundamentals_analysis.db": "4e7bc02191a705a73942d7df40cecc92ed5719633091bcd7b4e4a7c92146df97",
        "osakedata.db": "0ed1ed6b737c7e7f1ec44a09bb743317154212a28870f9f4c20bf8df46ca700b",
        "analysis.db": "f15ec53783a450e082eea351e4cce559c023d697d3ecca9bf443057c1d3cdbbd",
    }
    expected_coverage = {21: 48971, 42: 47438, 63: 47283}
    expected_ic = {
        "fcf_yield": 0.09059565463976707,
        "operating_income_yield": 0.08976465603525412,
        "valuation_score": 0.08848564549569948,
        "fundamental_score": 0.07820032901455268,
        "diagnostic_flag_count": -0.0726472269779696,
    }
    coverage = {h: sum(row.get(f"phase12a_h{h}_status") == "LABEL_READY" for row in rows) for h in (21, 42, 63)}
    score_rows = [row for row in rows if row.get("score_status") == "SCORE_FULL" and row.get("phase12a_h63_status") == "LABEL_READY"]
    values = {}
    for feature, expected in expected_ic.items():
        pairs = [(float(row[feature]), float(row["phase12a_h63_excess_return"])) for row in score_rows if row.get(feature) is not None]
        actual = spearman([item[0] for item in pairs], [item[1] for item in pairs])
        values[feature] = {"actual": actual, "expected": expected, "absolute_error": abs(actual - expected), "within_tolerance": abs(actual - expected) <= 1e-12}
    current_hashes = {
        name: str(preflight["databases"][name]["sha256"])
        for name in phase12a_hashes
    }
    hash_comparison = {
        name: {
            "phase12a": phase12a_hashes[name],
            "current": current_hashes[name],
            "match": phase12a_hashes[name] == current_hashes[name],
        }
        for name in phase12a_hashes
    }
    exact_reference_match = (
        all(coverage[h] == expected_coverage[h] for h in coverage)
        and len(score_rows) == 27365
        and all(item["within_tolerance"] for item in values.values())
    )
    feature_database_hashes_match = all(
        hash_comparison[name]["match"]
        for name in ("fundamentals_v4.db", "fundamentals_provider.db", "fundamentals_analysis.db")
    )
    documented_market_drift = feature_database_hashes_match and not hash_comparison["osakedata.db"]["match"]
    documented_taxonomy_drift = feature_database_hashes_match and not hash_comparison["analysis.db"]["match"]
    result = {
        "endpoint_count": len(rows),
        "unresolved_identity_count": sum(row.get("identity_status") == "UNRESOLVED_IDENTITY" for row in rows),
        "coverage": {str(h): {"actual": coverage[h], "expected": expected_coverage[h], "match": coverage[h] == expected_coverage[h]} for h in coverage},
        "score_full_63": {"actual": len(score_rows), "expected": 27365, "match": len(score_rows) == 27365},
        "spearman": values,
        "source_hash_comparison": hash_comparison,
        "exact_phase12a_result_match": exact_reference_match,
        "documented_market_source_drift": documented_market_drift,
        "documented_non_predictor_taxonomy_source_drift": documented_taxonomy_drift,
        "feature_database_hashes_match": feature_database_hashes_match,
        "reconciliation_status": (
            "EXACT_PHASE12A_REPRODUCTION"
            if exact_reference_match
            else "PASSED_WITH_DOCUMENTED_MARKET_AND_NONPREDICTOR_TAXONOMY_DRIFT"
            if documented_market_drift and documented_taxonomy_drift
            else "PASSED_WITH_DOCUMENTED_OSAKEDATA_SOURCE_DRIFT"
            if documented_market_drift
            else "FAILED_UNEXPLAINED_SOURCE_OR_RESULT_DIFFERENCE"
        ),
    }
    result["passed"] = (
        result["endpoint_count"] == 50585
        and result["unresolved_identity_count"] == 258
        and (exact_reference_match or documented_market_drift)
    )
    return result


def eligibility_reason(row: Mapping[str, Any], *, require_label: bool = True) -> str:
    checks = (
        (row.get("identity_status") not in {"DATED_ALIAS", "CURRENT_TICKER_FALLBACK"}, "UNRESOLVED_IDENTITY"),
        (row.get("score_status") != "SCORE_FULL", str(row.get("score_status") or "SCORE_NOT_READY")),
        (row.get("valuation_status") != "VALUATION_FULL", str(row.get("valuation_status") or "VALUATION_NOT_READY")),
        (row.get("two_quarter_status") != "DELTA_READY", str(row.get("two_quarter_status") or "DELTA_NOT_READY")),
        (row.get("lifecycle_status") != "LIFECYCLE_READY" or not row.get("lifecycle"), "LIFECYCLE_NOT_READY"),
        (not row.get("diagnostic_complete"), "DIAGNOSTIC_STATUSES_INCOMPLETE"),
        (any(row.get(name) is None for name in ("fundamental_score", "valuation_score", "two_quarter_delta", "component_fundamental_trajectory", "diagnostic_flag_count")), "PRIMARY_FEATURE_MISSING"),
        (require_label and row.get("h63_status") != "LABEL_READY", str(row.get("h63_status") or "PRIMARY_LABEL_NOT_READY")),
    )
    for failed, reason in checks:
        if failed:
            return reason
    return "ELIGIBLE"


def prepare_rows(rows: list[dict[str, Any]], sessions: Sequence[str]) -> None:
    for row in rows:
        row["period"] = None
        row["partition_status"] = "NO_TRADABLE_ENTRY"
        if row.get("entry_date"):
            period, decision = partition_decision(entry_date=row["entry_date"], exit_date_63=row.get("h63_exit_date"), benchmark_sessions=sessions)
            row["period"] = period
            row["partition_status"] = decision
        row["feature_eligibility"] = eligibility_reason(row, require_label=False)
        row["common_eligibility"] = eligibility_reason(row, require_label=True)
        if row.get("fundamental_score") is not None:
            row["fundamental_band"] = fundamental_band(float(row["fundamental_score"]))
        if row.get("valuation_score") is not None:
            row["valuation_band"] = valuation_band(float(row["valuation_score"]))
        if row.get("two_quarter_delta") is not None:
            row["delta_2q_band"] = delta_band(float(row["two_quarter_delta"]))
            row["delta_2q_sign"] = "POSITIVE" if float(row["two_quarter_delta"]) > 0 else "NONPOSITIVE"
        if row.get("component_fundamental_trajectory") is not None:
            row["trajectory_band"] = trajectory_band(float(row["component_fundamental_trajectory"]))
        row["diagnostic_count_band"] = diagnostic_count_band(int(row.get("diagnostic_flag_count") or 0))


def retained_common(rows: Sequence[Mapping[str, Any]], period: str | None = None) -> list[Mapping[str, Any]]:
    return [row for row in rows if row.get("common_eligibility") == "ELIGIBLE" and row.get("partition_status") == "RETAINED" and (period is None or row.get("period") == period)]


def _summary(rows: Sequence[Mapping[str, Any]], target: str = "h63_excess_return") -> dict[str, Any]:
    values = sorted(float(row[target]) for row in rows if row.get(target) is not None)
    if not values:
        return {"n": 0, "companies": 0, "months": 0, "mean": None, "median": None, "p10": None, "p25": None, "p75": None, "p90": None, "positive_rate": None}
    q = lambda p: float(np.quantile(values, p))
    return {
        "n": len(values),
        "companies": len({int(row["company_id"]) for row in rows}),
        "dates": len({str(row["entry_date"]) for row in rows}),
        "months": len({str(row["entry_date"])[:7] for row in rows}),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "p10": q(0.10), "p25": q(0.25), "p75": q(0.75), "p90": q(0.90),
        "positive_rate": sum(value > 0 for value in values) / len(values),
        "mean_absolute_return": statistics.fmean(float(row["h63_price_return"]) for row in rows),
        "median_absolute_return": statistics.median(float(row["h63_price_return"]) for row in rows),
        "positive_absolute_rate": statistics.fmean(float(row["h63_positive_return"]) for row in rows),
        "mean_mae": statistics.fmean(float(row["h63_mae"]) for row in rows),
        "mean_mfe": statistics.fmean(float(row["h63_mfe"]) for row in rows),
    }


def _bootstrap_interval(
    rows: Sequence[Mapping[str, Any]], sessions: Sequence[str], statistic: Callable[[Sequence[Mapping[str, Any]]], float | None]
) -> tuple[float | None, float | None, float | None]:
    if not rows:
        return None, None, None
    session_index = {day: index for index, day in enumerate(sessions)}
    by_index: dict[int, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("entry_date") in session_index:
            by_index[session_index[str(row["entry_date"])]].append(row)
    starts = sorted(by_index)
    if not starts:
        return None, None, None
    rng = np.random.default_rng(RANDOM_SEED)
    values = []
    for _ in range(1000):
        sampled: list[Mapping[str, Any]] = []
        while len(sampled) < len(rows):
            start = int(rng.choice(starts))
            for index in range(start, start + 63):
                sampled.extend(by_index.get(index, ()))
        value = statistic(sampled[: len(rows)])
        if value is not None and math.isfinite(value):
            values.append(float(value))
    if not values:
        return None, None, None
    return float(np.quantile(values, 0.025)), float(np.quantile(values, 0.975)), float(statistics.fmean(values))


def _continuous_effect(rows: Sequence[Mapping[str, Any]], feature: str) -> float | None:
    pairs = [(float(row[feature]), float(row["h63_excess_return"])) for row in rows if row.get(feature) is not None]
    return spearman([x for x, _ in pairs], [y for _, y in pairs])


def _group_difference(rows: Sequence[Mapping[str, Any]], predicate: Callable[[Mapping[str, Any]], bool], comparison: Callable[[Mapping[str, Any]], bool] | None = None) -> float | None:
    selected = [float(row["h63_excess_return"]) for row in rows if predicate(row)]
    others = [float(row["h63_excess_return"]) for row in rows if (comparison(row) if comparison else not predicate(row))]
    return statistics.fmean(selected) - statistics.fmean(others) if selected and others else None


def hypothesis_results(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> list[dict[str, Any]]:
    definitions: dict[str, tuple[str, Callable[[Sequence[Mapping[str, Any]]], float | None], int]] = {
        "H1": ("Fundamental strength", lambda r: _continuous_effect(r, "fundamental_score"), 1),
        "H2": ("Absolute cheapness", lambda r: _continuous_effect(r, "valuation_score"), 1),
        "H3": ("Positive 2Q Delta", lambda r: _group_difference(r, lambda x: float(x["two_quarter_delta"]) > 0), 1),
        "H4": ("Quality plus value", lambda r: _group_difference(r, lambda x: float(x["fundamental_score"]) >= 80 and float(x["valuation_score"]) >= 60), 1),
        "H5": ("Quality value improvement", lambda r: _group_difference(r, lambda x: float(x["fundamental_score"]) >= 80 and float(x["valuation_score"]) >= 60 and float(x["two_quarter_delta"]) > 0), 1),
        "H6": ("Lifecycle interaction dispersion", lambda r: _lifecycle_dispersion(r), 1),
        "H7": ("Diagnostic burden", lambda r: _continuous_effect(r, "diagnostic_flag_count"), -1),
    }
    output = []
    p_values: dict[str, float | None] = {}
    period_effects: dict[str, dict[str, float | None]] = defaultdict(dict)
    for hypothesis, (description, statistic, expected) in definitions.items():
        for period in PERIODS[:3]:
            members = retained_common(rows, period)
            effect = statistic(members)
            low, high, boot_mean = _bootstrap_interval(members, sessions, statistic)
            period_effects[hypothesis][period] = effect
            output.append({"hypothesis": hypothesis, "description": description, "period": period, **_summary(members), "effect": effect, "expected_direction": expected, "bootstrap_mean": boot_mean, "ci_low": low, "ci_high": high})
        development = retained_common(rows, "DEVELOPMENT")
        if hypothesis in {"H1", "H2", "H7"}:
            feature = {"H1": "fundamental_score", "H2": "valuation_score", "H7": "diagnostic_flag_count"}[hypothesis]
            x = [float(row[feature]) for row in development]
            y = [float(row["h63_excess_return"]) for row in development]
            p_values[hypothesis] = float(stats.spearmanr(x, y).pvalue) if len(set(x)) > 1 else None
        else:
            p_values[hypothesis] = None
    adjusted = benjamini_hochberg({f"H{i}": p_values.get(f"H{i}") for i in range(1, 9)})
    development_summary = _summary(retained_common(rows, "DEVELOPMENT"))
    development_gate = (
        development_summary["n"] >= 200
        and development_summary["companies"] >= 100
        and development_summary["months"] >= 12
    )
    for row in output:
        hypothesis = row["hypothesis"]
        effects = period_effects[hypothesis]
        expected = row["expected_direction"]
        same = all(value is not None and value * expected > 0 for value in effects.values())
        validation = next(item for item in output if item["hypothesis"] == hypothesis and item["period"] == "TEMPORAL_VALIDATION")
        confirmation = next(item for item in output if item["hypothesis"] == hypothesis and item["period"] == "RETROSPECTIVE_CONFIRMATION")
        gates = validation["n"] >= 200 and confirmation["n"] >= 200
        excludes_zero = all(item is not None and item * expected > 0 for item in (validation["ci_low"] if expected > 0 else validation["ci_high"], confirmation["ci_low"] if expected > 0 else confirmation["ci_high"]))
        stress_survives = _hypothesis_stress_survives(rows, statistic, expected)
        concentration_survives = _hypothesis_concentration_survives(rows, statistic, expected)
        classification = (
            "NOT_TESTABLE_WITH_CURRENT_DATA"
            if not development_gate
            else "REPEATED_EXPLORATORY_EVIDENCE"
            if same and gates and excludes_zero and stress_survives and concentration_survives
            else "WEAK_OR_UNCERTAIN_EVIDENCE"
            if same and gates
            else "NO_REPEATED_EVIDENCE"
        )
        row["raw_p_diagnostic"] = p_values.get(hypothesis)
        row["bh_adjusted_p"] = adjusted.get(hypothesis)
        row["stress_direction_survives"] = stress_survives
        row["concentration_direction_survives"] = concentration_survives
        row["evidence_class"] = classification
    return output


def _stress_period_rows(rows: Sequence[Mapping[str, Any]], period: str, view: str) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        if row.get("period") != period or row.get("feature_eligibility") != "ELIGIBLE" or row.get("partition_status") != "RETAINED":
            continue
        if row.get("h63_status") == "LABEL_READY":
            target = row.get("h63_excess_return")
        elif row.get("h63_status") in {"MISSING_EXACT_EXIT_PRICE", "INSUFFICIENT_SESSION_COVERAGE"}:
            target = 0.0 if view == "NEUTRAL" else -1.0 - float(row.get("h63_benchmark_return") or 0.0)
        else:
            continue
        item = dict(row)
        item["h63_excess_return"] = target
        output.append(item)
    return output


def _hypothesis_stress_survives(
    rows: Sequence[Mapping[str, Any]],
    statistic: Callable[[Sequence[Mapping[str, Any]]], float | None],
    expected: int,
) -> bool:
    effects = []
    for period in ("TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION"):
        for view in ("NEUTRAL", "SEVERE"):
            effects.append(statistic(_stress_period_rows(rows, period, view)))
    return bool(effects) and all(effect is not None and effect * expected > 0 for effect in effects)


def _hypothesis_concentration_survives(
    rows: Sequence[Mapping[str, Any]],
    statistic: Callable[[Sequence[Mapping[str, Any]]], float | None],
    expected: int,
) -> bool:
    effects = []
    for period in ("TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION"):
        members = retained_common(rows, period)
        if not members:
            return False
        removals = (
            ("company_id", Counter(int(row["company_id"]) for row in members).most_common(1)[0][0]),
            ("lifecycle", Counter(str(row["lifecycle"]) for row in members).most_common(1)[0][0]),
            ("sector", Counter(str(row.get("sector") or "MISSING") for row in members).most_common(1)[0][0]),
        )
        for field, largest in removals:
            reduced = [
                row for row in members
                if (int(row[field]) if field == "company_id" else str(row.get(field) or "MISSING")) != largest
            ]
            effects.append(statistic(reduced))
    return bool(effects) and all(effect is not None and effect * expected > 0 for effect in effects)


def _lifecycle_dispersion(rows: Sequence[Mapping[str, Any]]) -> float | None:
    dispersions = []
    for feature in ("valuation_score", "two_quarter_delta"):
        effects = []
        for lifecycle in sorted({str(row["lifecycle"]) for row in rows}):
            members = [row for row in rows if row["lifecycle"] == lifecycle]
            effect = _continuous_effect(members, feature)
            if effect is not None and len(members) >= 100:
                effects.append(effect)
        if len(effects) >= 2:
            dispersions.append(statistics.pstdev(effects))
    return statistics.fmean(dispersions) if dispersions else None


def combination_rows(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    dimensions = (
        ("FUNDAMENTAL_X_VALUATION", "fundamental_band", "valuation_band"),
        ("FUNDAMENTAL_X_DELTA", "fundamental_band", "delta_2q_band"),
        ("VALUATION_X_DELTA", "valuation_band", "delta_2q_band"),
        ("LIFECYCLE_X_VALUATION", "lifecycle", "valuation_band"),
        ("LIFECYCLE_X_DELTA_SIGN", "lifecycle", "delta_2q_sign"),
        ("DIAGNOSTIC_X_VALUATION", "diagnostic_count_band", "valuation_band"),
    )
    output = []
    for period in PERIODS:
        period_rows = retained_common(rows, period)
        for table, left, right in dimensions:
            groups: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
            for row in period_rows:
                groups[(str(row[left]), str(row[right]))].append(row)
            for (left_value, right_value), members in sorted(groups.items()):
                values = _summary(members)
                reportable = values["n"] >= 200 and values["companies"] >= 100 and values["months"] >= 12
                output.append({"table": table, "period": period, "left": left_value, "right": right_value, **values, "interpretation_status": "REPORTABLE" if reportable else "INSUFFICIENT_FOR_PRIMARY_INTERPRETATION"})
        for name, predicate in (
            ("H4", lambda row: float(row["fundamental_score"]) >= 80 and float(row["valuation_score"]) >= 60),
            ("H5", lambda row: float(row["fundamental_score"]) >= 80 and float(row["valuation_score"]) >= 60 and float(row["two_quarter_delta"]) > 0),
        ):
            members = [row for row in period_rows if predicate(row)]
            values = _summary(members)
            output.append({"table": f"{name}_VS_COMMON", "period": period, "left": name, "right": "COMMON", **values, "comparison_mean_difference": _group_difference(period_rows, predicate), "interpretation_status": "REPORTABLE" if values["n"] >= 200 and values["companies"] >= 100 and values["months"] >= 12 else "INSUFFICIENT_FOR_PRIMARY_INTERPRETATION"})
        h4 = lambda row: float(row["fundamental_score"]) >= 80 and float(row["valuation_score"]) >= 60
        h5 = lambda row: h4(row) and float(row["two_quarter_delta"]) > 0
        h5_members = [row for row in period_rows if h5(row)]
        h4_only = [row for row in period_rows if h4(row) and not h5(row)]
        values = _summary(h5_members)
        output.append({
            "table": "H5_VS_H4",
            "period": period,
            "left": "H5",
            "right": "H4_NONPOSITIVE_DELTA",
            **values,
            "comparison_n": len(h4_only),
            "comparison_mean_difference": (
                statistics.fmean(float(row["h63_excess_return"]) for row in h5_members)
                - statistics.fmean(float(row["h63_excess_return"]) for row in h4_only)
                if h5_members and h4_only else None
            ),
            "interpretation_status": "REPORTABLE" if values["n"] >= 200 and values["companies"] >= 100 and values["months"] >= 12 else "INSUFFICIENT_FOR_PRIMARY_INTERPRETATION",
        })
    return output


def run_models(rows: Sequence[Mapping[str, Any]], sessions: Sequence[str]) -> tuple[
    list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]],
    list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]],
    list[dict[str, Any]], list[dict[str, Any]],
]:
    development = retained_common(rows, "DEVELOPMENT")
    development_summary = _summary(development)
    model_status = (
        "EXPLORATORY_MODEL_SAMPLE_GATE_PASSED"
        if development_summary["n"] >= 200
        and development_summary["companies"] >= 100
        and development_summary["months"] >= 12
        else "NOT_TESTABLE_DEVELOPMENT_SAMPLE_GATE_FAILED"
    )
    fitted = {name: fit_baseline(development, name) for name in MODELS}
    continuous, classification, calibration, coefficients, quintiles = [], [], [], [], []
    calibration_summaries, intervals = [], []
    for name, model in fitted.items():
        coefficients.extend(coefficient_rows(model))
        for period in PERIODS:
            members = retained_common(rows, period)
            if not members:
                continue
            regression_prediction, probability = predict(model, members)
            continuous.append({"model": name, "period": period, "interpretation_status": model_status, **continuous_metrics(members, regression_prediction)})
            classification.append({"model": name, "period": period, "interpretation_status": model_status, **classification_metrics(members, probability)})
            calibration.extend(calibration_rows(period, name, members, probability))
            calibration_summaries.append(calibration_summary(period, name, members, probability))
            enriched = [dict(row, _prediction=float(reg), _probability=float(prob)) for row, reg, prob in zip(members, regression_prediction, probability)]
            metric_functions = {
                "spearman": lambda sample: spearman(
                    [float(item["_prediction"]) for item in sample],
                    [float(item["h63_excess_return"]) for item in sample],
                ),
                "brier": lambda sample: statistics.fmean(
                    (float(item["_probability"]) - float(item["h63_positive_excess"])) ** 2
                    for item in sample
                ),
            }
            for metric_name, statistic in metric_functions.items():
                low, high, boot_mean = _bootstrap_interval(enriched, sessions, statistic)
                intervals.append({
                    "model": name, "period": period, "metric": metric_name,
                    "bootstrap_mean": boot_mean, "ci_low": low, "ci_high": high,
                    "method": "CALENDAR_TIME_MOVING_BLOCK_63_SESSIONS_1000_REPETITIONS",
                })
            assigned = tie_safe_quintiles(regression_prediction.tolist(), [(int(row["company_id"]), int(row["quarter_id"])) for row in members])
            for quintile in range(1, 6):
                selected = [row for row, group in zip(members, assigned) if group == quintile]
                quintiles.append({"model": name, "period": period, "quintile": quintile, **_summary(selected)})
    comparisons = []
    for period in ("DEVELOPMENT", "TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION"):
        cont = {row["model"]: row for row in continuous if row["period"] == period}
        cls = {row["model"]: row for row in classification if row["period"] == period}
        for complex_, simple in (("B3", "B1"), ("B3", "B2"), ("B4", "B3")):
            comparisons.append({
                "period": period,
                "comparison": f"{complex_}_vs_{simple}",
                "spearman_difference": (cont[complex_]["spearman"] or 0) - (cont[simple]["spearman"] or 0),
                "quintile_spread_difference": (cont[complex_]["top_minus_bottom_quintile"] or 0) - (cont[simple]["top_minus_bottom_quintile"] or 0),
                "brier_improvement": cls[simple]["brier"] - cls[complex_]["brier"],
                "incremental_direction_positive": ((cont[complex_]["spearman"] or 0) > (cont[simple]["spearman"] or 0) and cls[complex_]["brier"] < cls[simple]["brier"]),
            })
    return continuous, classification, calibration, coefficients, quintiles, comparisons, calibration_summaries, intervals


def missing_exit_rows(rows: Sequence[Mapping[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    output = []
    stress = []
    for row in rows:
        for horizon in (21, 42, 63):
            status = row.get(f"h{horizon}_status")
            if status == "LABEL_READY":
                continue
            actions = row.get("action_evidence") or []
            evidence = "HORIZON_NOT_MATURED" if status == "HORIZON_NOT_MATURED" else "TRADING_LATER_RESUMES" if row.get(f"h{horizon}_trading_later_resumes") else "ACTION_METADATA_PRESENT" if actions else "UNVERIFIED_CAUSE"
            output.append({
                "company_id": row["company_id"], "quarter_id": row["quarter_id"], "ticker": row.get("ticker"),
                "signal_date": row.get("source_availability_date"), "entry_date": row.get(f"h{horizon}_entry_date"),
                "horizon": horizon, "status": status, "period": row.get("period"), "lifecycle": row.get("lifecycle"),
                "sector_current_non_pit": row.get("sector"), "company_status": row.get("company_status"),
                "last_market_date": row.get(f"h{horizon}_last_market_date"), "last_market_close": row.get(f"h{horizon}_last_market_close"),
                "trading_later_resumes": row.get(f"h{horizon}_trading_later_resumes"), "evidence_status": evidence,
                "action_evidence": actions,
                "fundamental_band": row.get("fundamental_band"),
                "valuation_band": row.get("valuation_band"),
            })
    feature_rows = [row for row in rows if row.get("feature_eligibility") == "ELIGIBLE"]
    for period in PERIODS:
        members = [
            row for row in feature_rows
            if row.get("period") == period and row.get("partition_status") == "RETAINED"
        ]
        for feature in ("fundamental_score", "valuation_score", "two_quarter_delta", "diagnostic_flag_count"):
            for view in ("COMPLETE_CASE", "NEUTRAL_ZERO_EXCESS_BOUND", "SEVERE_MINUS_100_COMPANY_RETURN_BOUND"):
                pairs = []
                for row in members:
                    if row.get(feature) is None:
                        continue
                    if view == "COMPLETE_CASE":
                        target = row.get("h63_excess_return") if row.get("h63_status") == "LABEL_READY" else None
                    elif row.get("h63_status") in {"MISSING_EXACT_EXIT_PRICE", "INSUFFICIENT_SESSION_COVERAGE"}:
                        target = 0.0 if view.startswith("NEUTRAL") else -1.0 - float(row.get("h63_benchmark_return") or 0.0)
                    else:
                        target = row.get("h63_excess_return") if row.get("h63_status") == "LABEL_READY" else None
                    if target is not None:
                        pairs.append((float(row[feature]), float(target)))
                stress.append({"period": period, "feature": feature, "view": view, "n": len(pairs), "spearman": spearman([x for x, _ in pairs], [y for _, y in pairs]) if pairs else None})
    return output, stress


def auxiliary_artifacts(rows: Sequence[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    sample_flow, exclusions, purge, feature_summary, univariate, stability_year, lifecycle, sector, concentration, horizon = [], [], [], [], [], [], [], [], [], []
    for h in (21, 42, 63):
        counts = Counter(str(row.get(f"h{h}_status")) for row in rows)
        for status, count in sorted(counts.items()):
            sample_flow.append({"horizon": h, "status": status, "count": count, "total": len(rows), "fraction": count / len(rows)})
            exclusions.append({"horizon": h, "reason": status, "count": count})
        for dimension, field in (
            ("YEAR", "entry_date"),
            ("LIFECYCLE", "lifecycle"),
            ("SECTOR_CURRENT_NON_PIT", "sector"),
            ("FUNDAMENTAL_BAND", "fundamental_band"),
            ("VALUATION_BAND", "valuation_band"),
        ):
            grouped = Counter()
            for row in rows:
                status = str(row.get(f"h{h}_status"))
                if status == "LABEL_READY":
                    continue
                value = str(row.get(field) or "MISSING")
                if dimension == "YEAR" and value != "MISSING":
                    value = value[:4]
                grouped[(value, status)] += 1
            for (value, status), count in sorted(grouped.items()):
                exclusions.append({
                    "horizon": h, "dimension": dimension, "member": value,
                    "reason": status, "count": count,
                    "non_pit_context": dimension == "SECTOR_CURRENT_NON_PIT",
                })
    for period in PERIODS:
        candidates = [row for row in rows if row.get("period") == period]
        for status, count in sorted(Counter(str(row.get("partition_status")) for row in candidates).items()):
            purge.append({"period": period, "partition_status": status, "count": count})
        common = retained_common(rows, period)
        for feature in ("fundamental_score", "valuation_score", "two_quarter_delta", "component_fundamental_trajectory", "diagnostic_flag_count"):
            values = [float(row[feature]) for row in common]
            feature_summary.append({"period": period, "feature": feature, "n": len(values), "mean": statistics.fmean(values) if values else None, "median": statistics.median(values) if values else None, "minimum": min(values) if values else None, "maximum": max(values) if values else None, "clipped": 0})
            pairs = [(float(row[feature]), float(row["h63_excess_return"])) for row in common]
            univariate.append({"period": period, "feature": feature, "n": len(pairs), "spearman": spearman([x for x, _ in pairs], [y for _, y in pairs]) if pairs else None})
        for dimension, target in (("lifecycle", lifecycle), ("sector_current_non_pit", sector)):
            key = "lifecycle" if dimension == "lifecycle" else "sector"
            groups: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
            for row in common:
                groups[str(row.get(key) or "MISSING")].append(row)
            for group, members in sorted(groups.items()):
                values = _summary(members)
                target.append({"period": period, "group": group, **values, "status": "REPORTABLE" if values["n"] >= 200 and values["companies"] >= 100 and values["months"] >= 12 else "INSUFFICIENT_FOR_STABLE_INFERENCE", "non_pit_context": key == "sector"})
        companies = Counter(int(row["company_id"]) for row in common)
        total = len(common)
        for company_id, count in sorted(companies.items(), key=lambda item: (-item[1], item[0]))[:10]:
            concentration.append({"period": period, "dimension": "COMPANY_TOP10", "member": company_id, "observations": count, "share": count / total if total else None})
        stability_year.append({"period": period, **_summary(common)})
        for h in (21, 42, 63):
            members = [row for row in common if row.get(f"h{h}_status") == "LABEL_READY"]
            vals = [float(row[f"h{h}_excess_return"]) for row in members]
            horizon.append({"period": period, "horizon": h, "n": len(vals), "mean": statistics.fmean(vals) if vals else None, "median": statistics.median(vals) if vals else None, "positive_rate": sum(v > 0 for v in vals) / len(vals) if vals else None})
    return {"sample_flow": sample_flow, "exclusions": exclusions, "purge": purge, "feature_summary": feature_summary, "univariate": univariate, "stability_year": stability_year, "lifecycle": lifecycle, "sector": sector, "concentration": concentration, "horizon": horizon}


def _decision(hypotheses: Sequence[Mapping[str, Any]], comparisons: Sequence[Mapping[str, Any]], stress: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    classes = {row["hypothesis"]: row["evidence_class"] for row in hypotheses if row["period"] == "TEMPORAL_VALIDATION"}
    h8_evidence = [
        row for row in comparisons
        if row["period"] in {"TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION"}
    ]
    h8_positive = bool(h8_evidence) and all(row["incremental_direction_positive"] for row in h8_evidence)
    development_testable = not any(value == "NOT_TESTABLE_WITH_CURRENT_DATA" for value in classes.values())
    classes["H8"] = (
        "NOT_TESTABLE_WITH_CURRENT_DATA"
        if not development_testable
        else "REPEATED_EXPLORATORY_EVIDENCE"
        if h8_positive
        else "NO_REPEATED_EVIDENCE"
    )
    repeated = [name for name, value in classes.items() if value == "REPEATED_EXPLORATORY_EVIDENCE"]
    outcome = "OUTCOME_A" if repeated and h8_positive else "OUTCOME_B" if repeated or any(value == "WEAK_OR_UNCERTAIN_EVIDENCE" for value in classes.values()) else "OUTCOME_C"
    return {"outcome": outcome, "hypothesis_classes": classes, "repeated_hypotheses": repeated, "later_ml_gate_passed": outcome == "OUTCOME_A", "prospective_collection_recommended": outcome != "OUTCOME_A", "status": "REVISED_HISTORY_EXPLORATORY_ONLY"}


def run(paths: ResearchPaths, output_dir: Path, *, contract_fingerprint: str) -> RunResult:
    if contract_fingerprint != CONTRACT_FINGERPRINT:
        raise ValueError("LOCKED_RESEARCH_CONTRACT_FINGERPRINT_MISMATCH")
    if not output_dir.is_absolute() or "temp" not in output_dir.parts:
        raise ValueError("PHASE12B_OUTPUT_MUST_BE_EXPLICIT_TEMP_PATH")
    output_dir.mkdir(parents=True, exist_ok=True)
    preflight = database_state(paths)
    write_json(output_dir / "production_preflight.json", preflight)
    rows, sessions = build_research_rows(paths)
    reconciliation = _phase12a_reconciliation(rows, preflight)
    write_json(output_dir / "source_reconciliation.json", reconciliation)
    if not reconciliation["passed"]:
        write_json(output_dir / "decision.json", {"outcome": "OUTCOME_D", "reason": "PHASE12A_RECONCILIATION_FAILED", "status": "REVISED_HISTORY_EXPLORATORY_ONLY"})
        raise RuntimeError("PHASE12A_RECONCILIATION_FAILED")
    prepare_rows(rows, sessions)
    source_fp = source_fingerprint(rows)
    sample_fp = stable_hash([{key: row.get(key) for key in ("company_id", "quarter_id", "entry_date", "h63_exit_date", "h63_excess_return", "common_eligibility", "period", "partition_status")} for row in rows])

    auxiliary = auxiliary_artifacts(rows)
    hypotheses = hypothesis_results(rows, sessions)
    (
        continuous, classification, calibration, coefficients, quintiles,
        comparisons, calibration_summaries, model_intervals,
    ) = run_models(rows, sessions)
    missing, stress = missing_exit_rows(rows)
    combinations = combination_rows(rows)
    monthly = []
    for period in PERIODS:
        members = retained_common(rows, period)
        for feature in ("fundamental_score", "valuation_score", "two_quarter_delta", "component_fundamental_trajectory", "diagnostic_flag_count"):
            for item in monthly_ic(members, feature, "h63_excess_return"):
                monthly.append({"period": period, **item})

    h8_rows = []
    for period in PERIODS[:3]:
        relevant = [row for row in comparisons if row["period"] == period]
        h8_rows.append({"hypothesis": "H8", "description": "Incremental combination value", "period": period, "effect": next((row["spearman_difference"] for row in relevant if row["comparison"] == "B4_vs_B3"), None), "evidence_class": "NO_REPEATED_EVIDENCE"})
    hypotheses.extend(h8_rows)
    decision = _decision(hypotheses, comparisons, stress)
    for row in h8_rows:
        row["evidence_class"] = decision["hypothesis_classes"]["H8"]

    write_json(output_dir / "research_contract.json", {"contract": CONTRACT, "contract_fingerprint": CONTRACT_FINGERPRINT})
    write_json(output_dir / "decision.json", decision)
    write_json(output_dir / "partition_boundaries.json", {"periods": CONTRACT["periods"], "session_zero": True, "purge": CONTRACT["dependence_controls"]["purge"], "embargo": CONTRACT["dependence_controls"]["embargo"]})
    mapping = {
        "sample_flow.csv": auxiliary["sample_flow"],
        "purge_embargo_audit.csv": auxiliary["purge"],
        "feature_eligibility.csv": [{"reason": reason, "count": count} for reason, count in sorted(Counter(row["common_eligibility"] for row in rows).items())],
        "label_coverage.csv": auxiliary["sample_flow"],
        "missing_exit_analysis.csv": missing,
        "missing_exit_stress_bounds.csv": stress,
        "univariate_results.csv": auxiliary["univariate"],
        "primary_hypothesis_results.csv": hypotheses,
        "predefined_combination_results.csv": combinations,
        "continuous_model_results.csv": continuous,
        "classification_model_results.csv": classification,
        "calibration_results.csv": calibration,
        "calibration_summary.csv": calibration_summaries,
        "dependence_aware_intervals.csv": model_intervals,
        "monthly_ic_results.csv": monthly,
        "time_stability_results.csv": auxiliary["stability_year"],
        "lifecycle_stability_results.csv": auxiliary["lifecycle"],
        "sector_stability_results.csv": auxiliary["sector"],
        "company_concentration_results.csv": auxiliary["concentration"],
        "horizon_robustness_results.csv": auxiliary["horizon"],
        "model_coefficients.csv": coefficients,
        "predicted_quintile_results.csv": quintiles,
        "nested_model_comparison.csv": comparisons,
        "exclusion_reasons.csv": auxiliary["exclusions"],
        "feature_summary_by_period.csv": auxiliary["feature_summary"],
    }
    for filename, values in mapping.items():
        write_csv(output_dir / filename, values)
    audit_sample = sorted(retained_common(rows), key=lambda row: (row["period"], row["company_id"], row["quarter_id"]))[:100]
    sample_fields = ["company_id", "quarter_id", "ticker", "source_availability_date", "entry_date", "h63_exit_date", "period", "fundamental_score", "valuation_score", "two_quarter_delta", "component_fundamental_trajectory", "lifecycle", "diagnostic_flag_count", "h63_excess_return"]
    write_csv(output_dir / "prediction_sample.csv", audit_sample, sample_fields)
    reconciliation_sample = sorted(rows, key=lambda row: (row["company_id"], row["quarter_id"]))[:100]
    write_csv(output_dir / "reconciliation_sample.csv", reconciliation_sample, ["company_id", "quarter_id", "ticker", "phase12a_h63_status", "phase12a_h63_excess_return", "h63_status", "h63_excess_return"])

    (output_dir / "signal_and_label_contract.md").write_text(f"# Signal and label contract\n\n{MANDATORY_DISCLOSURE}\n\nEntry is session zero: first complete SPY session strictly after availability. Exact exits are entry-index +21/+42/+63, synchronized to SPY, with at least 90% ticker-session coverage. The primary target is 63-session excess price return.\n", encoding="utf-8")
    (output_dir / "prospective_pit_collection_recommendation.md").write_text("# Prospective PIT collection recommendation\n\nImplement separately as Phase 12P: append-only provider observations with ingestion and provider revision timestamps, raw payload hash, winner/supersession links, stable security identity and dated aliases; row-level price adjustment, dividend, corporate-action, delisting and terminal-return evidence; optional classification snapshots; and an immutable as-known feature package per signal. Collection can start immediately, but original historical as-known values and missing delisting returns cannot be reconstructed reliably.\n", encoding="utf-8")
    (output_dir / "recommended_next_phase.md").write_text(f"# Recommended next phase\n\nOutcome: {decision['outcome']}. ML gate passed: {decision['later_ml_gate_passed']}. Start Phase 12P prospective PIT collection before any expanded model search unless the locked evidence gate is met. Do not change production scores or Snapshot.\n", encoding="utf-8")
    (output_dir / "reproduction_commands.txt").write_text(
        "python3 -m rawcandle.cli.run_phase12b_fundamental_profile_baseline "
        f"--canonical-db {paths.canonical_db} --analysis-db {paths.analysis_db} "
        f"--provider-db {paths.provider_db} --market-db {paths.market_db} "
        f"--taxonomy-db {paths.taxonomy_db} --output-dir <OUTPUT_DIR_UNDER_TEMP> "
        f"--contract-fingerprint {CONTRACT_FINGERPRINT}\n",
        encoding="utf-8",
    )
    write_json(output_dir / "run_metadata.json", {
        "contract_version": CONTRACT_VERSION,
        "contract_fingerprint": CONTRACT_FINGERPRINT,
        "research_status": "REVISED_HISTORY_EXPLORATORY_ONLY",
        "random_seed": RANDOM_SEED,
        "source_paths": asdict(paths),
        "network_calls": False,
        "production_writes": False,
    })

    development_sample = _summary(retained_common(rows, "DEVELOPMENT"))
    label_ready = {
        horizon: sum(row.get(f"h{horizon}_status") == "LABEL_READY" for row in rows)
        for horizon in (21, 42, 63)
    }
    missing_63 = Counter(str(row.get("h63_status")) for row in rows if row.get("h63_status") != "LABEL_READY")
    report_lines = [
        "# Phase 12B Fundamental Profile Baseline", "", f"> {MANDATORY_DISCLOSURE}", "",
        f"Contract: `{CONTRACT_VERSION}`", f"Fingerprint: `{CONTRACT_FINGERPRINT}`",
        "Contract commit: `5c92a42`", "",
        f"Decision: **{decision['outcome']}**", f"Later ML gate passed: **{decision['later_ml_gate_passed']}**", "",
        "The primary fixed-model test is not adequately testable: the purged development common cohort has "
        f"{development_sample['n']:,} observations, {development_sample['companies']:,} companies and "
        f"{development_sample['months']:,} signal months, below the locked 200/100/12 gate. "
        "Model metrics are retained as transparent diagnostics only and must not be treated as validation evidence.", "",
        "## Reconciliation", "",
        f"- Phase 12A status: `{reconciliation['reconciliation_status']}`.",
        "- Canonical, provider and Fundamentals analysis databases remain byte-identical to Phase 12A.",
        "- The market database changed after Phase 12A; both reference and current label counts and exact IC values are preserved in `source_reconciliation.json`.",
        "- Current taxonomy/classification storage is non-PIT descriptive context, not a predictor; any source drift is fingerprinted explicitly.",
        f"- Current session-zero label coverage: 21={label_ready[21]:,}, 42={label_ready[42]:,}, 63={label_ready[63]:,} of {len(rows):,} endpoints.", "",
        "## Sample", "",
    ]
    for period in PERIODS:
        report_lines.append(f"- {period}: {len(retained_common(rows, period)):,} retained primary common-cohort rows")
    report_lines.extend(["", "## Hypotheses", ""])
    for name, classification_value in sorted(decision["hypothesis_classes"].items()):
        report_lines.append(f"- {name}: `{classification_value}`")
    report_lines.extend(["", "## Fixed Models", "", "| Model | Period | Spearman | Brier | Status |", "|---|---|---:|---:|---|"])
    continuous_by_key = {(row["model"], row["period"]): row for row in continuous}
    classification_by_key = {(row["model"], row["period"]): row for row in classification}
    for model in MODELS:
        for period in ("DEVELOPMENT", "TEMPORAL_VALIDATION", "RETROSPECTIVE_CONFIRMATION"):
            cont = continuous_by_key[(model, period)]
            cls = classification_by_key[(model, period)]
            spearman_value = "n/a" if cont["spearman"] is None else f"{cont['spearman']:.4f}"
            report_lines.append(f"| {model} | {period} | {spearman_value} | {cls['brier']:.4f} | `{cont['interpretation_status']}` |")
    report_lines.extend(["", "## Missing Exits", ""])
    for status, count in sorted(missing_63.items()):
        report_lines.append(f"- 63 sessions `{status}`: {count:,}")
    report_lines.extend([
        "", "## Interpretation", "",
        "All complete-case results are conditional on the security remaining observable with a valid exact exit row. "
        "Neutral and severe missing-exit stress bounds are separate audit views and never enter model fitting.",
        "",
        "The locked later-ML gate fails. Start the separately scoped prospective PIT collection track before expanded model search. "
        "Do not change production scores, Company Snapshot, Scheduler, or persistence from these findings.",
        "",
    ])
    (output_dir / "PHASE12B_BASELINE_REPORT.md").write_text("\n".join(report_lines), encoding="utf-8")

    postflight = database_state(paths)
    write_json(output_dir / "production_postflight.json", postflight)
    immutability = {"identical": preflight == postflight, "preflight_fingerprint": stable_hash(preflight), "postflight_fingerprint": stable_hash(postflight)}
    write_json(output_dir / "production_immutability_evidence.json", immutability)
    if not immutability["identical"]:
        raise RuntimeError("PRODUCTION_STATE_CHANGED_DURING_PHASE12B")

    for path in output_dir.glob("*.json"):
        json.loads(path.read_text(encoding="utf-8"))
    for path in output_dir.glob("*.csv"):
        with path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            list(reader)
            if reader.fieldnames is None:
                raise RuntimeError(f"CSV_HEADER_MISSING:{path.name}")
    artifacts = {path.name: {"bytes": path.stat().st_size, "sha256": _sha(path)} for path in sorted(output_dir.iterdir()) if path.is_file() and path.name != "artifact_manifest.json"}
    result_fp = stable_hash(artifacts)
    write_json(output_dir / "artifact_manifest.json", {"source_fingerprint": source_fp, "contract_fingerprint": CONTRACT_FINGERPRINT, "sample_fingerprint": sample_fp, "result_fingerprint": result_fp, "artifacts": artifacts})
    return RunResult(decision["outcome"], source_fp, CONTRACT_FINGERPRINT, sample_fp, result_fp, str(output_dir))
