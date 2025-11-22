from __future__ import annotations

from typing import Iterable, Sequence
import logging

try:
    from analysis.database_manager import MASTER_FEATURE_COLUMNS as DB_MASTER_FEATURES
except Exception:  # pragma: no cover - defensive fallback
    DB_MASTER_FEATURES: list[str] = []

try:
    from regression import run_regression

    REGRESSION_FEATURES: list[str] = list(getattr(run_regression, "FEATURE_COLUMNS", []))
except Exception:  # pragma: no cover - fallback if regression module missing
    REGRESSION_FEATURES = []


def _deduplicate(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        ordered.append(item)
        seen.add(item)
    return ordered


EXCLUDE_COLUMNS: set[str] = {
    "id",
    "ticker",
    "date",
    "created_at",
    "market",
    "sector",
    # forward targets
    "t2",
    "t5",
    "t10",
    "t20",
}


def filter_predictor_features(cols: Sequence[str]) -> list[str]:
    return [c for c in cols if c not in EXCLUDE_COLUMNS]


MASTER_FEATURES: list[str] = _deduplicate(DB_MASTER_FEATURES + REGRESSION_FEATURES)

TOP20_FEATURES: list[str] = [
    "signal_strength",
    "RSI14_t0",
    "t0_volyymi",
    "t0_close_norm",
    "t_10_hajonta",
    "t_20_hajonta",
    "t0_50p_liukuva",
    "t0_200p_liukuva",
    "RSI_slope_5",
    "Price_acceleration_5_10",
    "Volatility_ratio_10_20",
    "Gap_down_strength",
    "Body_ratio",
    "Shadow_ratio",
    "Volume_impulse",
    "is_crisis",
    "SPX_10",
    "SPX_20",
    "SPX_volatility_10",
    "NDX_10",
]

DEFAULT_FEATURE_SET = "master"
FEATURE_SET_OPTIONS = ("master", "top20", "custom")


def get_features_for_mode(
    feature_mode: str, custom_features: Sequence[str] | None = None
) -> list[str]:
    """
    Map UI feature selection to a valid list of columns.
    """
    feature_mode = (feature_mode or DEFAULT_FEATURE_SET).strip().lower()
    if feature_mode == "top20":
        return filter_predictor_features(TOP20_FEATURES)
    if feature_mode == "custom":
        return filter_predictor_features(custom_features or [])
    # default master
    return filter_predictor_features(MASTER_FEATURES)


def validate_features(
    df,
    feature_cols: Sequence[str],
    *,
    logger: logging.Logger | None = None,
) -> list[str]:
    """
    Drop missing columns from feature list and log a warning so the caller knows.
    """
    available = [col for col in feature_cols if col in getattr(df, "columns", [])]
    missing = [col for col in feature_cols if col not in available]
    if missing and logger:
        logger.warning(
            "Seuraavat featuret puuttuvat results_data-datasta: %s",
            ", ".join(missing),
        )
    return available
