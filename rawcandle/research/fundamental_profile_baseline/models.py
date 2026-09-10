from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    log_loss,
    mean_absolute_error,
    mean_squared_error,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

from .contract import RANDOM_SEED
from .engine import pearson, spearman, tie_safe_quintiles


LIFECYCLE_CATEGORIES = (
    "DECLINING",
    "DISTRESSED",
    "GROWTH",
    "SCALING",
    "STARTUP",
    "STRUGGLING",
    "TRANSITION",
)
MODEL_FEATURES = {
    "B1": ("fundamental_score",),
    "B2": ("valuation_score",),
    "B3": ("fundamental_score", "valuation_score"),
    "B4": (
        "fundamental_score",
        "valuation_score",
        "two_quarter_delta",
        "component_fundamental_trajectory",
        "diagnostic_flag_count",
    ),
}


@dataclass
class FittedBaseline:
    name: str
    scaler: StandardScaler | None
    regression: LinearRegression | None
    classification: LogisticRegression | None
    regression_constant: float | None
    classification_constant: float | None
    feature_names: tuple[str, ...]


def _raw_matrix(rows: Sequence[Mapping[str, Any]], model: str) -> tuple[np.ndarray, tuple[str, ...]]:
    if model == "B0":
        return np.empty((len(rows), 0)), ()
    names = list(MODEL_FEATURES[model])
    values = [[float(row[name]) for name in names] for row in rows]
    if model == "B4":
        for category in LIFECYCLE_CATEGORIES:
            names.append(f"lifecycle_{category}")
        for index, row in enumerate(rows):
            values[index].extend(float(row["lifecycle"] == category) for category in LIFECYCLE_CATEGORIES)
    matrix = np.asarray(values, dtype=float)
    if not np.isfinite(matrix).all():
        raise ValueError(f"NONFINITE_MODEL_INPUT:{model}")
    return matrix, tuple(names)


def fit_baseline(rows: Sequence[Mapping[str, Any]], model: str) -> FittedBaseline:
    if not rows:
        raise ValueError("EMPTY_DEVELOPMENT_COHORT")
    y = np.asarray([float(row["h63_excess_return"]) for row in rows])
    binary = np.asarray([int(row["h63_positive_excess"]) for row in rows])
    if model == "B0":
        return FittedBaseline(model, None, None, None, float(y.mean()), float(binary.mean()), ())
    raw, names = _raw_matrix(rows, model)
    continuous_count = len(MODEL_FEATURES[model])
    scaler = StandardScaler().fit(raw[:, :continuous_count])
    transformed = raw.copy()
    transformed[:, :continuous_count] = scaler.transform(raw[:, :continuous_count])
    regression = LinearRegression().fit(transformed, y)
    classification = LogisticRegression(
        penalty="l2", C=1.0, solver="lbfgs", max_iter=1000, random_state=RANDOM_SEED
    ).fit(transformed, binary)
    return FittedBaseline(model, scaler, regression, classification, None, None, names)


def predict(model: FittedBaseline, rows: Sequence[Mapping[str, Any]]) -> tuple[np.ndarray, np.ndarray]:
    if model.name == "B0":
        return (
            np.full(len(rows), model.regression_constant, dtype=float),
            np.full(len(rows), model.classification_constant, dtype=float),
        )
    raw, _ = _raw_matrix(rows, model.name)
    count = len(MODEL_FEATURES[model.name])
    raw[:, :count] = model.scaler.transform(raw[:, :count])
    return model.regression.predict(raw), model.classification.predict_proba(raw)[:, 1]


def coefficient_rows(model: FittedBaseline) -> list[dict[str, Any]]:
    if model.name == "B0":
        return [
            {"model": "B0", "target": "REGRESSION", "feature": "INTERCEPT", "coefficient": model.regression_constant},
            {"model": "B0", "target": "CLASSIFICATION", "feature": "BASE_RATE", "coefficient": model.classification_constant},
        ]
    output = []
    for target, estimator in (("REGRESSION", model.regression), ("CLASSIFICATION", model.classification)):
        output.append({"model": model.name, "target": target, "feature": "INTERCEPT", "coefficient": float(estimator.intercept_[0] if target == "CLASSIFICATION" else estimator.intercept_)})
        for name, value in zip(model.feature_names, estimator.coef_[0] if target == "CLASSIFICATION" else estimator.coef_):
            output.append({"model": model.name, "target": target, "feature": name, "coefficient": float(value)})
    return output


def continuous_metrics(rows: Sequence[Mapping[str, Any]], predictions: Sequence[float]) -> dict[str, Any]:
    actual = np.asarray([float(row["h63_excess_return"]) for row in rows])
    pred = np.asarray(predictions, dtype=float)
    quintiles = tie_safe_quintiles(pred.tolist(), [(int(row["company_id"]), int(row["quarter_id"])) for row in rows])
    quintile_means = []
    for quintile in range(1, 6):
        values = actual[np.asarray(quintiles) == quintile]
        quintile_means.append(float(values.mean()) if len(values) else None)
    available = [value for value in quintile_means if value is not None]
    return {
        "n": len(rows),
        "spearman": spearman(pred.tolist(), actual.tolist()),
        "pearson": pearson(pred.tolist(), actual.tolist()),
        "mae": float(mean_absolute_error(actual, pred)),
        "rmse": float(math.sqrt(mean_squared_error(actual, pred))),
        "sign_accuracy": float(np.mean((pred > 0) == (actual > 0))),
        "top_minus_bottom_quintile": available[-1] - available[0] if len(available) >= 2 else None,
        "quintile_means": quintile_means,
        "quintile_monotonic": all(a <= b for a, b in zip(available, available[1:])) if len(available) == 5 else False,
    }


def classification_metrics(rows: Sequence[Mapping[str, Any]], probabilities: Sequence[float]) -> dict[str, Any]:
    actual = np.asarray([int(row["h63_positive_excess"]) for row in rows])
    probability = np.clip(np.asarray(probabilities, dtype=float), 1e-15, 1 - 1e-15)
    if len(set(actual.tolist())) < 2:
        roc = pr = None
    else:
        roc = float(roc_auc_score(actual, probability))
        pr = float(average_precision_score(actual, probability))
    return {
        "n": len(rows),
        "base_rate": float(actual.mean()),
        "roc_auc": roc,
        "pr_auc": pr,
        "brier": float(brier_score_loss(actual, probability)),
        "log_loss": float(log_loss(actual, probability, labels=[0, 1])),
    }


def calibration_rows(period: str, model: str, rows: Sequence[Mapping[str, Any]], probabilities: Sequence[float]) -> list[dict[str, Any]]:
    bins = ((0.0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1.0 + 1e-12))
    output = []
    for low, high in bins:
        members = [(float(p), int(row["h63_positive_excess"])) for row, p in zip(rows, probabilities) if low <= p < high]
        output.append({
            "period": period,
            "model": model,
            "probability_band": f"[{low:.1f},{min(high, 1.0):.1f}{']' if high > 1 else ')'}",
            "n": len(members),
            "mean_prediction": float(np.mean([p for p, _ in members])) if members else None,
            "observed_rate": float(np.mean([y for _, y in members])) if members else None,
        })
    return output


def calibration_summary(
    period: str,
    model: str,
    rows: Sequence[Mapping[str, Any]],
    probabilities: Sequence[float],
) -> dict[str, Any]:
    actual = np.asarray([int(row["h63_positive_excess"]) for row in rows])
    probability = np.clip(np.asarray(probabilities, dtype=float), 1e-12, 1 - 1e-12)
    if len(rows) < 20 or len(set(actual.tolist())) < 2 or len(set(probability.tolist())) < 2:
        return {
            "period": period,
            "model": model,
            "calibration_intercept": None,
            "calibration_slope": None,
            "status": "NOT_ESTIMABLE",
        }
    logit = np.log(probability / (1.0 - probability)).reshape(-1, 1)
    fitted = LogisticRegression(
        penalty=None, solver="lbfgs", max_iter=1000, random_state=RANDOM_SEED
    ).fit(logit, actual)
    return {
        "period": period,
        "model": model,
        "calibration_intercept": float(fitted.intercept_[0]),
        "calibration_slope": float(fitted.coef_[0][0]),
        "status": "READY",
    }
