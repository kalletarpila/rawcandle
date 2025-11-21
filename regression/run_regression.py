#!/usr/bin/env python3
"""
run_regression.py

Tarkoitus:
- lukea kynttilädatasetti (kaikki rivit laskutrendistä)
- rakentaa tuottohorisontit (y2, y5, y10, y20)
- tehdä binäärilabelit "onnistuiko käänne?"
- erottaa kynttilät vs satunnaiset downtrend-päivät (pattern_koodi 0)
- ajaa logistinen regressio (todennäköisyys käänteelle)
- ajaa lineaarinen regressio (odotettu tuotto)
"""

from __future__ import annotations

import sqlite3
import warnings
from datetime import datetime
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.outliers_influence import variance_inflation_factor

from analysis.bullish_divergence_core_model import BullishDivergenceModel
from analysis.combo_features import (
    BULL_DIV_GENERAL_FEATURES,
    COMBO_FEATURE_COLUMNS,
)
from analysis.preprocess_utils import (
    apply_blackout_flags,
    load_blackout_dates,
    preprocess_signals,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "analysis.db"

RETURN_COLUMNS = ["t2", "t5", "t10", "t20"]
FEATURE_COLUMNS = [
    # Peruspsykologia ja kynttilä
    "vahvuus",
    "RSI14_t0",
    "t0_volyymi",
    "t0_close_norm",
    # Divergenssiengageeratut featuret (engineered)
    "is_divergence_today",  # divergence today (from divergence_data)
    "recent_divergence_min_distance",  # days since last divergence (1-5, else 6)
    "recent_divergence_decay_strength",  # strength / (1 + distance)
    "rolling_BullDiv_influence",  # windowed influence of last 5 days
    "bullDiv_offset",
    "bullDiv_last_1d",
    "bullDiv_last_2d",
    "bullDiv_last_3d",
    "bullDiv_last_3d_any",
    # Trendin syvyys ja volatiliteetti
    "t_10",
    "t_20",
    "t_10_hajonta",
    "t_20_hajonta",
    # Liukuvat keskiarvot
    "t0_50p_liukuva",
    "t0_200p_liukuva",
    # Uudet slope- ja kiihtyvyysfeaturet
    "RSI_slope_5",
    "Price_slope_5",
    "Price_slope_10",
    "Price_acceleration_5_10",
    # Uudet vola- ja rakennefeaturet
    "Volatility_ratio_10_20",
    "Gap_down_strength",
    "Body_ratio",
    "Shadow_ratio",
    # Volyymi-impulssi ja kontekstipiste
    "Volume_impulse",
    "Reversal_Context_Score",
    # Blackout-kattavuus
    "has_blackout_data",
    # Kriisi-ikkuna
    "is_crisis",
    # Päiväkohtaiset signaaliyhdistelmät
    "num_candles_same_day",
    "has_multi_candle_combo",
    "has_bullish_divergence_same_day",
    "signal_count_same_day",
    "unique_patterns_same_day",
    "max_strength_same_day",
    "second_best_strength_same_day",
    "sum_strength_same_day",
    "has_same_day_reversal_cluster",
    # Markkinaympäristö ja indeksivola
    "SPX_10",
    "SPX_20",
    "SPX_volatility_10",
    "NDX_10",
    "NDX_20",
    "NDX_volatility_10",
]
FEATURE_COLUMNS += COMBO_FEATURE_COLUMNS
PATTERN_COLUMN = "kynttila_koodi"
MARKET_COLUMN = "market"
CATEGORICAL_DUMMY_COLUMNS = [
    PATTERN_COLUMN,
    MARKET_COLUMN,
    "BullDiv_recent_offset",
    "signal_combo_code",
]
FEATURE_SELECTION_MARKER = "__ui_feature_selection__"
PATTERN_LABELS = {
    0: "Downtrend (kontrolli)",
    1: "Hammer",
    2: "Bullish Engulfing",
    3: "Piercing Pattern",
    4: "Three White Soldiers",
    5: "Morning Star",
    6: "Dragonfly Doji",
    7: "Bullish Divergence",
    8: "Bearish Divergence",
}
DEFAULT_SUCCESS_THRESHOLDS = {2: 0.02, 5: 0.03, 10: 0.05, 20: 0.08}
CRISIS_START = "2025-03-01"
CRISIS_END = "2025-04-30"
BINARY_FEATURES = {"is_crisis"}
BINARY_FEATURES.update(
    {"bullDiv_last_1d", "bullDiv_last_2d", "bullDiv_last_3d", "bullDiv_last_3d_any"}
)
BINARY_FEATURES.update(COMBO_FEATURE_COLUMNS)
BINARY_FEATURES.update(
    {
        "has_multi_candle_combo",
        "has_bullish_divergence_same_day",
        "has_same_day_reversal_cluster",
    }
)
BULL_DIV_DIAGNOSTIC_BASE = ["vahvuus", "Price_slope_10", "SPX_volatility_10"]
BULL_DIV_DIAGNOSTIC_FEATURES = BULL_DIV_DIAGNOSTIC_BASE + COMBO_FEATURE_COLUMNS
CRISIS_SUCCESS_LABELS = [f"success{h}" for h in sorted(DEFAULT_SUCCESS_THRESHOLDS.keys())]
FEATURE_SELECTION_STORE = PROJECT_ROOT / "data" / "regression_feature_selection.json"


def _friendly_feature_name(name: str) -> str:
    if name.startswith("kynttila_koodi_"):
        try:
            code = int(name.split("_")[-1])
            label = PATTERN_LABELS.get(code)
            if label:
                return f"{name} ({label})"
        except ValueError:
            pass
    return name


ALIAS_MAP = {
    "vahvuus": "signal_strength",
    "Bearish Divergence": "bearish_divergence",
    PATTERN_COLUMN: "candle_pattern",
}


def add_crisis_flag(df: pd.DataFrame) -> pd.DataFrame:
    """
    Merkitse rivit, jotka osuvat määriteltyyn kriisi-ikkunaan.
    """
    if df.empty:
        df["is_crisis"] = 0
        return df

    if "date" not in df.columns:
        df["is_crisis"] = 0
        return df

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    start = pd.Timestamp(CRISIS_START)
    end = pd.Timestamp(CRISIS_END)
    df["is_crisis"] = (
        (df["date"] >= start) & (df["date"] <= end)
    ).astype(int)
    return df


def load_feature_selection_preferences() -> List[str]:
    if not FEATURE_SELECTION_STORE.exists():
        return []
    try:
        data = json.loads(FEATURE_SELECTION_STORE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def save_feature_selection_preferences(selected_features: Iterable[str]) -> None:
    data_dir = FEATURE_SELECTION_STORE.parent
    data_dir.mkdir(parents=True, exist_ok=True)
    payload = [str(name) for name in selected_features]
    try:
        FEATURE_SELECTION_STORE.write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        pass


def load_divergence_data(db_path: Path | str = DEFAULT_DB_PATH) -> pd.DataFrame:
    """
    Lataa divergence_data-taulun (bullish/bearish divergencet) analysis.db-kannasta.

    Taulun schema:
        ticker TEXT NOT NULL
        date   TEXT NOT NULL
        bullish_strength REAL DEFAULT 0
        bearish_strength REAL DEFAULT 0
        rsi REAL
        PRIMARY KEY (ticker, date)
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Analysis-kantaa ei löytynyt: {db_path}")

    with sqlite3.connect(db_path) as conn:
        try:
            df = pd.read_sql_query(
                "SELECT ticker, date, bullish_strength FROM divergence_data",
                conn,
            )
        except sqlite3.OperationalError:
            return pd.DataFrame(columns=["ticker", "date", "bullish_strength"])

    if df.empty:
        return df

    df["ticker"] = df["ticker"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])
    df["bullish_strength"] = df["bullish_strength"].fillna(0.0).astype(float)
    return df




# ------------- 1. Datan luku -----------------


def load_data(
    db_path: Path | str = DEFAULT_DB_PATH, market: Optional[str] = None
) -> pd.DataFrame:
    """
    Lue data results_data-taulusta.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Analysis-kantaa ei löytynyt: {db_path}")

    query = "SELECT * FROM results_data"
    params: list = []
    if market and market.lower() not in {"", "__all__"}:
        query += " WHERE lower(market) = ?"
        params.append(market.strip().lower())

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if df.empty:
        return df

    # Luo Excel-tyyliset alias-sarakkeet
    for alias, source in ALIAS_MAP.items():
        if alias not in df.columns and source in df.columns:
            df[alias] = df[source]

    df = add_crisis_flag(df)
    return df


# ------------- 2. Labelien rakentaminen -----------------


def add_return_labels(
    df: pd.DataFrame, thresholds: Optional[Dict[int, float]] = None
) -> pd.DataFrame:
    """
    Rakentaa tuottomuuttujat ja binäärilabelit.
    Oletus: t2, t5, t10, t20 ovat suhteessa t0_low = 100.
    Esim. t5 = 105 => +5 % tuotto.
    """
    missing = [col for col in RETURN_COLUMNS if col not in df.columns]
    if missing:
        raise ValueError(f"Datasetistä puuttuu sarakkeet: {missing}")

    thresholds = {int(k): float(v) for k, v in (thresholds or {}).items()}

    for col in RETURN_COLUMNS:
        horizon = int(col[1:])
        ret_col = f"y{horizon}"
        df[ret_col] = (df[col] - 100.0) / 100.0

    for horizon, default_threshold in DEFAULT_SUCCESS_THRESHOLDS.items():
        threshold = thresholds.get(horizon, default_threshold)
        label_col = f"success{horizon}"
        df[label_col] = (df[f"y{horizon}"] > threshold).astype(int)
    return df


def add_divergence_features(
    df: pd.DataFrame,
    db_path: Path | str = DEFAULT_DB_PATH,
    divergence_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Rakentaa bullish divergence -featuret divergence_data-taulusta:
    erottelee tämän päivän tapahtumat, etäisyyden viimeiseen divergenceen sekä vaimenevan vaikutuksen.
    """

    defaults = {
        "is_divergence_today": 0,
        "recent_divergence_min_distance": 6,
        "recent_divergence_decay_strength": 0.0,
        "rolling_BullDiv_influence": 0.0,
    }

    def _apply_defaults(target: pd.DataFrame) -> pd.DataFrame:
        for col, value in defaults.items():
            target[col] = value
        return target

    if any(col not in df.columns for col in ["ticker", "date"]):
        return _apply_defaults(df.copy())

    working_df = df.copy()
    original_index = working_df.index
    working_df["ticker"] = working_df["ticker"].astype(str)
    working_df["date"] = pd.to_datetime(working_df["date"], errors="coerce")

    if divergence_df is None:
        divergence_df = load_divergence_data(db_path=db_path)

    if divergence_df.empty:
        return _apply_defaults(working_df)

    merge_cols = divergence_df[["ticker", "date", "bullish_strength"]].rename(
        columns={"bullish_strength": "_divergence_strength"}
    )
    working_df = working_df.merge(
        merge_cols,
        on=["ticker", "date"],
        how="left",
        sort=False,
    )
    strength_col = "_divergence_strength"
    working_df[strength_col] = working_df[strength_col].fillna(0.0).astype(float)

    working_df["is_divergence_today"] = (working_df[strength_col] > 0).astype(int)
    working_df["recent_divergence_min_distance"] = 6
    working_df["recent_divergence_decay_strength"] = 0.0
    working_df["rolling_BullDiv_influence"] = 0.0

    sorted_df = (
        working_df.sort_values(["ticker", "date"])
        .reset_index(drop=False)
        .rename(columns={"index": "_orig_index"})
    )

    n_rows = len(sorted_df)
    distances = np.full(n_rows, 6, dtype=int)
    decays = np.zeros(n_rows, dtype=float)
    influences = np.zeros(n_rows, dtype=float)

    for _, group in sorted_df.groupby("ticker", sort=False):
        group_idx = group.index.to_numpy()
        events = group["is_divergence_today"].to_numpy()
        strengths = group[strength_col].to_numpy()

        for local_i, global_pos in enumerate(group_idx):
            window_start = max(0, local_i - 5)
            last_event_local = -1
            for j in range(local_i - 1, window_start - 1, -1):
                if events[j] == 1:
                    last_event_local = j
                    break
            if last_event_local != -1:
                distance = local_i - last_event_local
                distances[global_pos] = distance
                decays[global_pos] = strengths[last_event_local] / (1 + distance)
            else:
                distances[global_pos] = 6
                decays[global_pos] = 0.0

            influence_total = 0.0
            for j in range(window_start, local_i):
                if events[j] == 1:
                    age = local_i - j
                    influence_total += strengths[j] * float(np.exp(-0.7 * age))
            influences[global_pos] = influence_total
    order = sorted_df["_orig_index"].to_numpy()
    working_df.loc[order, "recent_divergence_min_distance"] = distances
    working_df.loc[order, "recent_divergence_decay_strength"] = decays
    working_df.loc[order, "rolling_BullDiv_influence"] = influences
    working_df = working_df.drop(columns=[strength_col])
    working_df = working_df.loc[original_index]
    return working_df


# ------------- 3. Featurejen valinta -----------------


def build_feature_matrix(
    df: pd.DataFrame,
    feature_columns: list[str] | None = None,
    include_is_candle_day: bool = True,
    categorical_columns: Optional[Iterable[str]] = None,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Valitse psykologiset ja tekniset featuret sekä koodaa kategoriset.
    """
    feature_columns = feature_columns or FEATURE_COLUMNS

    required_cols = feature_columns + [PATTERN_COLUMN, MARKET_COLUMN]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Datasetistä puuttuu sarakkeet: {missing}")

    is_candle_series = (df[PATTERN_COLUMN].fillna(0).astype(int) != 0).astype(int)
    df["is_candle_day"] = is_candle_series

    binary_cols = [col for col in feature_columns if col in BINARY_FEATURES]
    continuous_cols = [col for col in feature_columns if col not in BINARY_FEATURES]
    feature_df = df[continuous_cols].copy()

    allowed_cats = set(categorical_columns) if categorical_columns is not None else None
    categorical_cols: list[str] = []
    for col in [PATTERN_COLUMN, MARKET_COLUMN]:
        if allowed_cats is None or col in allowed_cats:
            categorical_cols.append(col)
    offset_col = "BullDiv_recent_offset"
    if offset_col in df.columns and (allowed_cats is None or offset_col in allowed_cats):
        categorical_cols.append(offset_col)

    dummy_frames: list[pd.DataFrame] = []
    if include_is_candle_day:
        dummy_frames.append(
            pd.DataFrame(
                {"is_candle_day": is_candle_series.astype(float)}, index=df.index
            )
        )

    if binary_cols:
        dummy_frames.append(df[binary_cols].astype(float))

    if categorical_cols:
        categorical = df[categorical_cols].astype("category")
        categorical_dummies = pd.get_dummies(
            categorical, columns=categorical_cols, drop_first=True
        ).astype(float)
        drop_cols = [
            col
            for col in categorical_dummies.columns
            if col.startswith(f"{PATTERN_COLUMN}_7")
        ]
        if drop_cols:
            categorical_dummies = categorical_dummies.drop(columns=drop_cols)
        dummy_frames.append(categorical_dummies)

    if dummy_frames:
        dummy_df = pd.concat(dummy_frames, axis=1)
        feature_df = pd.concat([feature_df, dummy_df], axis=1)
    else:
        feature_df = feature_df.copy()

    dummy_cols = [col for col in feature_df.columns if col not in continuous_cols]
    return feature_df, continuous_cols, dummy_cols


def calculate_vif(X: pd.DataFrame) -> pd.DataFrame:
    """Laskee VIF-arvot (Variance Inflation Factor) featurematriisille X."""
    vif_rows: list[dict[str, float | str]] = []
    X_np = X.values
    for i in range(X.shape[1]):
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", category=RuntimeWarning)
                vif_val = variance_inflation_factor(X_np, i)
        except Exception:
            vif_val = float("nan")
        vif_rows.append({"feature": X.columns[i], "VIF": float(vif_val)})

    vif_df = pd.DataFrame(vif_rows)
    vif_df = vif_df.sort_values("VIF", ascending=False).reset_index(drop=True)
    return vif_df


# ------------- 4. Perusdiagnostiikka -----------------


def quick_summary(df: pd.DataFrame, label_column: str = "success5") -> str:
    """
    Palauta onnistumisprosentit success5-labelille.
    """

    def rate(mask: pd.Series) -> tuple[float, int]:
        sub = df.loc[mask]
        if sub.empty:
            return 0.0, 0
        return float(sub[label_column].mean()), len(sub)

    lines = [f"== Perusonnistumisprosentit ({label_column}) =="]
    all_rate, n_all = rate(df[label_column].notna())
    lines.append(f"Kaikki rivit:          {all_rate:.3f} (n={n_all})")

    candle_rate, n_candle = rate(df["is_candle_day"] == 1)
    lines.append(f"Kynttiläpäivät:        {candle_rate:.3f} (n={n_candle})")

    random_rate, n_random = rate(df["is_candle_day"] == 0)
    lines.append(f"Satunnaiset downtrend: {random_rate:.3f} (n={n_random})")
    return "\n".join(lines)


def compute_crisis_success_stats(
    df: pd.DataFrame,
    label_columns: Iterable[str],
    exclude_crisis_period: bool = False,
) -> Dict[str, object]:
    """
    Laske onnistumisprosentit kriisi-ikkunan sisällä vs. sen ulkopuolella.
    """
    info: Dict[str, object] = {
        "excluded": bool(exclude_crisis_period),
        "has_column": "is_crisis" in df.columns,
        "stats": {},
        "has_crisis_rows": False,
        "has_normal_rows": False,
    }
    if exclude_crisis_period or not info["has_column"] or df.empty:
        return info

    stats: Dict[str, Dict[str, float]] = {}
    crisis_mask = df["is_crisis"] == 1
    normal_mask = df["is_crisis"] == 0

    def _rate(mask: pd.Series, label: str) -> tuple[float, int]:
        subset = df.loc[mask, label].dropna()
        if subset.empty:
            return 0.0, 0
        return float(subset.mean()), int(len(subset))

    any_crisis = False
    any_normal = False
    for label in label_columns:
        if label not in df.columns:
            continue
        crisis_rate, crisis_n = _rate(crisis_mask, label)
        normal_rate, normal_n = _rate(normal_mask, label)
        any_crisis = any_crisis or crisis_n > 0
        any_normal = any_normal or normal_n > 0
        stats[label] = {
            "crisis_rate": crisis_rate,
            "crisis_n": crisis_n,
            "normal_rate": normal_rate,
            "normal_n": normal_n,
        }
    info["stats"] = stats
    info["has_crisis_rows"] = any_crisis
    info["has_normal_rows"] = any_normal
    return info


def compute_bull_div_distribution(df: pd.DataFrame) -> Dict[int, int]:
    if df.empty or "bullDiv_offset" not in df.columns:
        return {}
    counts = df["bullDiv_offset"].fillna(99).astype(int).value_counts().to_dict()
    return {int(k): int(v) for k, v in counts.items()}


def candle_bull_div_combo_analysis(
    df: pd.DataFrame, horizon: int
) -> Optional[List[str]]:
    if "bullDiv_offset" not in df.columns or "bullDiv_last_3d_any" not in df.columns:
        return None
    label = f"success{horizon}"
    if label not in df.columns:
        return None
    candle_mask = df[PATTERN_COLUMN].fillna(0).astype(int) != 0
    candle_df = df.loc[candle_mask].copy()
    if candle_df.empty:
        return None

    def _rate(mask: pd.Series) -> tuple[float, int]:
        sub = candle_df.loc[mask & candle_df[label].notna()]
        if sub.empty:
            return 0.0, 0
        return float(sub[label].mean()), len(sub)

    offset_series = candle_df["bullDiv_offset"].fillna(99).astype(int)
    last_any = candle_df["bullDiv_last_3d_any"].fillna(0).astype(int)
    lines = [f"== Candle + Bullish Divergence combo analysis (H{horizon}) =="]
    stats = [
        ("Candle only (no BullDiv last 3d)", last_any == 0),
        ("Candle + BullDiv t0", offset_series == 0),
        ("Candle + BullDiv t-1", offset_series == 1),
        ("Candle + BullDiv t-2", offset_series == 2),
        ("Candle + BullDiv last 3d (0-2)", last_any == 1),
    ]
    for desc, mask in stats:
        rate, count = _rate(mask)
        lines.append(f"{desc}: success{horizon} = {rate:.3f} (n={count})")
    lines.append("")
    return lines


# ------------- 5. Logistinen regressio -----------------


def run_logistic_regression(
    X: pd.DataFrame,
    y: pd.Series,
    continuous_cols: list[str],
    label_name: str = "success",
) -> Dict[str, object]:
    """
    Logistinen regressio P(success5=1 | featuret).
    """
    if y.nunique() < 2:
        raise ValueError(f"{label_name} sisältää vain yhden luokan – lisää dataa.")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    dummy_cols = [col for col in X.columns if col not in continuous_cols]
    scaler = StandardScaler() if continuous_cols else None
    if continuous_cols:
        X_train_cont = scaler.fit_transform(X_train[continuous_cols])
        X_test_cont = scaler.transform(X_test[continuous_cols])
    else:
        X_train_cont = np.empty((len(X_train), 0))
        X_test_cont = np.empty((len(X_test), 0))
    X_train_dummy = (
        X_train[dummy_cols].to_numpy(dtype=float)
        if dummy_cols
        else np.empty((len(X_train), 0))
    )
    X_test_dummy = (
        X_test[dummy_cols].to_numpy(dtype=float)
        if dummy_cols
        else np.empty((len(X_test), 0))
    )
    X_train_full = np.hstack([X_train_cont, X_train_dummy])
    X_test_full = np.hstack([X_test_cont, X_test_dummy])
    all_feature_names = continuous_cols + dummy_cols

    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        n_jobs=-1,
    )
    model.fit(X_train_full, y_train)

    y_proba = model.predict_proba(X_test_full)[:, 1]
    y_pred = (y_proba > 0.5).astype(int)

    auc = roc_auc_score(y_test, y_proba)
    report = classification_report(y_test, y_pred, digits=3)

    coef = pd.Series(model.coef_[0], index=all_feature_names)
    coef.index = [_friendly_feature_name(name) for name in coef.index]
    sorted_coef = coef.sort_values(ascending=False)
    pos = sorted_coef.head(min(15, len(sorted_coef)))
    neg = sorted_coef.tail(min(15, len(sorted_coef)))
    importance = coef.abs().sort_values(ascending=False)

    return {
        "auc": float(auc),
        "classification_report": report,
        "top_positive": pos,
        "top_negative": neg,
        "importance": importance,
        "model": model,
        "scaler": scaler,
        "continuous_cols": continuous_cols,
        "dummy_cols": dummy_cols,
    }


# ------------- 6. Lineaarinen regressio -----------------


def run_linear_regression(
    X: pd.DataFrame, y: pd.Series, continuous_cols: list[str]
) -> Dict[str, object]:
    """
    Lineaarinen regressio odotetulle tuotolle (y5).
    """
    dummy_cols = [col for col in X.columns if col not in continuous_cols]
    scaler = StandardScaler() if continuous_cols else None
    if continuous_cols:
        X_cont_scaled = scaler.fit_transform(X[continuous_cols])
    else:
        X_cont_scaled = np.empty((len(X), 0))
    X_dummy_raw = (
        X[dummy_cols].to_numpy(dtype=float) if dummy_cols else np.empty((len(X), 0))
    )
    X_full = np.hstack([X_cont_scaled, X_dummy_raw])

    X_scaled_df = pd.DataFrame(
        X_full, columns=continuous_cols + dummy_cols, index=X.index
    )
    friendly_cols = [_friendly_feature_name(name) for name in X_scaled_df.columns]
    X_scaled_df.columns = friendly_cols
    X_const = sm.add_constant(X_scaled_df)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=RuntimeWarning)
        model = sm.OLS(y, X_const).fit()
    cond_number = float(np.linalg.cond(X_const))
    warning = None
    if not np.isfinite(cond_number) or cond_number > 1e12:
        warning = (
            "Suuri condition number ("
            f"{cond_number:.2e}). Mallissa on mahdollisesti multikollineaarisuutta."
        )

    column_map_lines = ["OLS sarakeavain:"]
    for idx, name in enumerate(X_scaled_df.columns, 1):
        column_map_lines.append(f"x{idx}: {_friendly_feature_name(name)}")
    column_map_text = "\n".join(column_map_lines)

    params = model.params.drop("const", errors="ignore")
    importance = params.abs().sort_values(ascending=False)

    summary_text = f"{model.summary().as_text()}\n\n{column_map_text}"
    return {
        "summary": summary_text,
        "model": model,
        "scaler": scaler,
        "column_map": column_map_lines,
        "importance": importance,
        "condition_number": cond_number,
        "warning": warning,
        "continuous_cols": continuous_cols,
        "dummy_cols": dummy_cols,
    }


def run_candle_bull_div_diagnostic(
    df: pd.DataFrame, label_col: str
) -> Optional[Dict[str, object]]:
    if label_col not in df.columns:
        return None
    available_features = [
        col for col in BULL_DIV_DIAGNOSTIC_FEATURES if col in df.columns
    ]
    if any(base not in available_features for base in BULL_DIV_DIAGNOSTIC_BASE):
        return None
    subset = df.dropna(subset=available_features + [label_col]).copy()
    if subset.empty:
        return None
    subset = subset[subset[PATTERN_COLUMN].fillna(0).astype(int) != 0]
    if subset.empty or subset[label_col].nunique() < 2:
        return None

    X = subset[available_features]
    y = subset[label_col]
    try:
        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.2,
            random_state=42,
            stratify=y,
        )
    except ValueError:
        return None

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)
    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
    )
    model.fit(X_train_scaled, y_train)
    y_proba = model.predict_proba(X_test_scaled)[:, 1]
    auc = roc_auc_score(y_test, y_proba)
    coef = pd.Series(model.coef_[0], index=available_features)
    sorted_coef = coef.sort_values(ascending=False)
    importance = coef.abs().sort_values(ascending=False)
    return {
        "auc": float(auc),
        "coef": coef,
        "top_positive": sorted_coef.head(min(5, len(sorted_coef))),
        "top_negative": sorted_coef.tail(min(5, len(sorted_coef))),
        "importance": importance.head(min(10, len(importance))),
    }


# ------------- 7. Yhteenveto & rajapinta -----------------


def run_regression_for_market(
    market: Optional[str] = None,
    pattern_code: Optional[int] = None,
    success_horizons: Optional[List[int]] = None,
    success_thresholds: Optional[Dict[int, float]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
    write_report: bool = True,
    require_blackout_data: bool = False,
    exclude_crisis_period: bool = False,
    feature_columns: Optional[List[str]] = None,
) -> Dict[str, object]:
    """
    Suorita koko pipeline yhdelle markkinalle ja palauta tulokset.
    """
    if isinstance(pattern_code, str) and pattern_code == "BullishDivergenceOnly":
        thresholds_for_model = success_thresholds or DEFAULT_SUCCESS_THRESHOLDS
        horizon_targets = success_horizons or [2, 5, 10, 20]
        filtered_horizons = [h for h in horizon_targets if h in {2, 5, 10, 20}] or [2, 5, 10, 20]
        model = BullishDivergenceModel(
            market=market,
            exclude_crisis_period=exclude_crisis_period,
            require_blackout_data=require_blackout_data,
            crisis_start=CRISIS_START,
            crisis_end=CRISIS_END,
            db_path=db_path,
            horizon_list=filtered_horizons,
            success_thresholds=thresholds_for_model,
        )
        bd_results = model.run_all()
        report_text = _build_bullish_divergence_report(bd_results)
        return {
            "market": market,
            "pattern_code": "BullishDivergenceOnly",
            "report": report_text,
            "warnings": bd_results.get("warnings", []),
            "horizons": {},
            "bullish_divergence_model": bd_results,
        }

    default_feature_set = (
        list(FEATURE_COLUMNS) + ["is_candle_day"] + CATEGORICAL_DUMMY_COLUMNS
    )
    if feature_columns is None:
        selected_set = set(default_feature_set)
    else:
        selected_set = set(feature_columns)
        sentinel_present = FEATURE_SELECTION_MARKER in selected_set
        selected_set.discard(FEATURE_SELECTION_MARKER)
        if not sentinel_present:
            selected_set.update({"is_candle_day", *CATEGORICAL_DUMMY_COLUMNS})

    include_is_candle_day = "is_candle_day" in selected_set
    enabled_dummy_groups = [
        name for name in CATEGORICAL_DUMMY_COLUMNS if name in selected_set
    ]
    continuous_feature_columns = [
        name for name in FEATURE_COLUMNS if name in selected_set
    ]
    disabled_features = [name for name in default_feature_set if name not in selected_set]
    ordered_selected_features = [
        name for name in default_feature_set if name in selected_set
    ]

    df = load_data(db_path=db_path, market=market)
    if df.empty:
        friendly_market = "kaikki markkinat" if not market else market.upper()
        raise ValueError(
            f"Results-data tyhjä markkinalle: {friendly_market}. Suorita analyysi ensin."
        )

    df = add_return_labels(df, thresholds=success_thresholds)
    blackout_df = load_blackout_dates(db_path=db_path)
    df = apply_blackout_flags(df, blackout_df)
    divergence_source = load_divergence_data(db_path=db_path)
    df = add_divergence_features(
        df, db_path=db_path, divergence_df=divergence_source
    )
    df_full = df.copy()
    if require_blackout_data and "has_blackout_data" in df_full.columns:
        df_full = df_full.loc[df_full["has_blackout_data"] == 1].reset_index(drop=True)

    if "exclude_from_regression" in df_full.columns:
        train_mask = df_full["exclude_from_regression"].fillna(0) == 0
        df = df_full.loc[train_mask].reset_index(drop=True)
    else:
        df = df_full.copy().reset_index(drop=True)

    if exclude_crisis_period and "is_crisis" in df.columns:
        df = df.loc[df["is_crisis"] == 0].reset_index(drop=True)
        df_full = df_full.loc[df_full["is_crisis"] == 0].reset_index(drop=True)

    # Puhdistetaan signaalit: yksi rivi per (ticker, date) ja combo-featuret
    df = preprocess_signals(df)
    df_full = preprocess_signals(df_full)

    pattern_selection: Optional[List[int]]
    if pattern_code is None or (
        isinstance(pattern_code, str) and pattern_code in {"", "__all__"}
    ):
        pattern_selection = None
    else:
        raw_codes: Iterable[object]
        if isinstance(pattern_code, (list, tuple, set)):
            raw_codes = pattern_code
        else:
            raw_codes = [pattern_code]
        try:
            pattern_selection = sorted({int(code) for code in raw_codes})
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Pattern-koodien tulee olla kokonaislukuja tai lista kokonaisluvuista."
            ) from exc
        if not pattern_selection:
            pattern_selection = None

    filter_label = "Kaikki kynttilät (sis. downtrend)"

    def _pattern_label(code: int) -> str:
        return PATTERN_LABELS.get(code, f"Pattern {code}")

    if pattern_selection:
        pattern_series = df[PATTERN_COLUMN].astype(int)
        if pattern_selection == [0]:
            mask = pattern_series == 0
            if not mask.any():
                raise ValueError("Ei downtrend-rivejä analyysia varten.")
            df = df[mask].reset_index(drop=True)
            df_full = df_full[df_full[PATTERN_COLUMN].astype(int) == 0].reset_index(
                drop=True
            )
            filter_label = _pattern_label(0)
        else:
            selected_nonzero = [code for code in pattern_selection if code != 0]
            if not selected_nonzero:
                raise ValueError("Valitse vähintään yksi kynttilätyyppi.")
            filter_set = set(selected_nonzero) | {0}
            filtered = df[pattern_series.isin(filter_set)]
            if filtered.empty or not pattern_series.isin(selected_nonzero).any():
                missing = ", ".join(str(code) for code in selected_nonzero)
                raise ValueError(
                    f"Ei rivejä valituille pattern-koodeille: {missing} (downtrend lisättiin automaattisesti)."
                )
            df = filtered.reset_index(drop=True)
            df_full = df_full[
                df_full[PATTERN_COLUMN].astype(int).isin(filter_set)
            ].reset_index(drop=True)
            friendly = ", ".join(_pattern_label(code) for code in selected_nonzero)
            filter_label = f"{friendly} + downtrend"
    else:
        df_full = df_full.reset_index(drop=True)

    bull_div_distribution_all = compute_bull_div_distribution(df_full)
    candle_mask_full = df_full[PATTERN_COLUMN].fillna(0).astype(int) != 0
    bull_div_distribution_candles = compute_bull_div_distribution(
        df_full.loc[candle_mask_full]
    )

    if "has_blackout_data" in df_full.columns:
        total_rows_full = len(df_full)
        rows_with_bo = int((df_full["has_blackout_data"] == 1).sum())
        rows_without_bo = int((df_full["has_blackout_data"] == 0).sum())
        share_without_bo = (
            (rows_without_bo / total_rows_full * 100.0) if total_rows_full > 0 else 0.0
        )
        share_with_bo = (
            (rows_with_bo / total_rows_full * 100.0) if total_rows_full > 0 else 0.0
        )
        blackout_coverage = {
            "total_rows": total_rows_full,
            "with_bo_rows": rows_with_bo,
            "without_bo_rows": rows_without_bo,
            "with_bo_pct": share_with_bo,
            "without_bo_pct": share_without_bo,
        }
    else:
        blackout_coverage = {
            "total_rows": len(df_full),
            "with_bo_rows": 0,
            "without_bo_rows": len(df_full),
            "with_bo_pct": 0.0,
            "without_bo_pct": 100.0,
        }

    if df.empty:
        raise ValueError("Ei rivejä regressiota varten blackout-suodatuksen jälkeen.")
    horizons = success_horizons or [5]
    invalid = [h for h in horizons if h not in DEFAULT_SUCCESS_THRESHOLDS]
    if invalid:
        raise ValueError(
            f"Tuntemattomat horisontit: {invalid}. Sallittuja arvoja: "
            f"{sorted(DEFAULT_SUCCESS_THRESHOLDS.keys())}"
        )

    # Globaali VIF-analyysi: käytä kaikkia rivejä, joissa featuret ovat kunnossa
    vif_subset = df.dropna(
        subset=continuous_feature_columns + [PATTERN_COLUMN, MARKET_COLUMN]
    ).reset_index(drop=True)
    if vif_subset.empty:
        raise ValueError("Ei riittävästi dataa VIF-analyysiä varten.")
    X_vif, continuous_cols_vif, dummy_cols_vif = build_feature_matrix(
        vif_subset,
        feature_columns=continuous_feature_columns,
        include_is_candle_day=include_is_candle_day,
        categorical_columns=enabled_dummy_groups,
    )
    vif_all = calculate_vif(X_vif)
    if continuous_cols_vif:
        vif_continuous = calculate_vif(X_vif[continuous_cols_vif])
    else:
        vif_continuous = pd.DataFrame(columns=["feature", "VIF"])

    combo_feature_set = set(COMBO_FEATURE_COLUMNS)
    horizon_results: Dict[int, Dict[str, object]] = {}
    warning_messages: List[str] = []
    for horizon in horizons:
        success_label = f"success{horizon}"
        return_label = f"y{horizon}"
        subset_train = df.dropna(
            subset=continuous_feature_columns
            + [success_label, return_label, PATTERN_COLUMN, MARKET_COLUMN]
        ).reset_index(drop=True)
        subset_full = df_full.dropna(
            subset=continuous_feature_columns
            + [success_label, return_label, PATTERN_COLUMN, MARKET_COLUMN]
        ).reset_index(drop=True)

        if subset_train.empty:
            raise ValueError(
                f"Ei riittävästi dataa horisontille {horizon} valituilla suodattimilla."
            )

        crisis_stats = compute_crisis_success_stats(
            subset_train, CRISIS_SUCCESS_LABELS, exclude_crisis_period=exclude_crisis_period
        )
        combo_features_active = [
            col for col in continuous_feature_columns if col in combo_feature_set
        ]
        base_feature_columns = [
            col for col in continuous_feature_columns if col not in combo_feature_set
        ]
        y_success = subset_train[success_label]
        y_return = subset_train[return_label]

        logistic_base_result = None
        if combo_features_active and base_feature_columns:
            X_base, base_cont_cols, _ = build_feature_matrix(
                subset_train,
                feature_columns=base_feature_columns,
                include_is_candle_day=include_is_candle_day,
                categorical_columns=enabled_dummy_groups,
            )
            logistic_base_result = run_logistic_regression(
                X_base, y_success, base_cont_cols, label_name=success_label
            )

        X, continuous_cols, dummy_cols = build_feature_matrix(
            subset_train,
            feature_columns=continuous_feature_columns,
            include_is_candle_day=include_is_candle_day,
            categorical_columns=enabled_dummy_groups,
        )

        summary_text = quick_summary(subset_train, label_column=success_label)
        combo_lines = candle_bull_div_combo_analysis(subset_train, horizon)
        diag_logistic = None
        if horizon in {5, 10}:
            diag_logistic = run_candle_bull_div_diagnostic(subset_train, success_label)
        logistic_result = run_logistic_regression(
            X, y_success, continuous_cols, label_name=success_label
        )
        linear_result = run_linear_regression(X, y_return, continuous_cols)

        if "is_blackout_window" in subset_full.columns:
            mask_blackout = subset_full["is_blackout_window"] == 1
            mask_non_blackout = subset_full["is_blackout_window"] == 0

            def _rate(mask: pd.Series) -> tuple[float, int]:
                sub = subset_full.loc[mask]
                if sub.empty:
                    return 0.0, 0
                return float(sub[success_label].mean()), len(sub)

            blackout_rate, n_blackout = _rate(mask_blackout)
            non_rate, n_non = _rate(mask_non_blackout)
            blackout_stats = {
                "blackout_rate": blackout_rate,
                "blackout_n": n_blackout,
                "non_blackout_rate": non_rate,
                "non_blackout_n": n_non,
            }
        else:
            blackout_stats = {
                "blackout_rate": 0.0,
                "blackout_n": 0,
                "non_blackout_rate": 0.0,
                "non_blackout_n": 0,
            }

        horizon_results[horizon] = {
            "row_count": len(subset_train),
            "summary": summary_text,
            "logistic": logistic_result,
            "logistic_base": logistic_base_result,
            "linear": linear_result,
            "blackout_stats": blackout_stats,
            "crisis_stats": crisis_stats,
            "combo_lines": combo_lines,
            "diag_logistic": diag_logistic,
            "combo_features": combo_features_active,
        }
        if linear_result.get("warning"):
            warning_messages.append(f"H{horizon}: {linear_result['warning']}")

    thresholds_payload = {
        h: (
            success_thresholds.get(h, DEFAULT_SUCCESS_THRESHOLDS[h])
            if success_thresholds
            else DEFAULT_SUCCESS_THRESHOLDS[h]
        )
        for h in DEFAULT_SUCCESS_THRESHOLDS
    }

    report_features = ordered_selected_features.copy()
    report_text = _build_report_text(
        market,
        filter_label,
        horizons,
        thresholds_payload,
        horizon_results,
        warning_messages,
        blackout_coverage,
        vif_all,
        vif_continuous,
        feature_columns=report_features,
        excluded_features=disabled_features,
        bull_div_distribution=bull_div_distribution_all,
        bull_div_candle_distribution=bull_div_distribution_candles,
        exclude_crisis_period=exclude_crisis_period,
    )
    report_path = _write_report(report_text) if write_report else None

    single_pattern_code = (
        pattern_selection[0] if pattern_selection and len(pattern_selection) == 1 else None
    )

    return {
        "market": market,
        "row_count": len(df),
        "pattern_code": single_pattern_code,
        "selected_patterns": pattern_selection,
        "pattern_label": filter_label,
        "success_horizons": sorted(horizons),
        "success_thresholds": thresholds_payload,
        "horizons": horizon_results,
        "report": report_text,
        "report_path": report_path,
        "warnings": warning_messages,
        "vif_all": vif_all,
        "vif_continuous": vif_continuous,
        "blackout_coverage": blackout_coverage,
        "bull_div_distribution": bull_div_distribution_all,
        "bull_div_candle_distribution": bull_div_distribution_candles,
    }


def _build_report_text(
    market: Optional[str],
    pattern_label: str,
    horizons: List[int],
    thresholds: Dict[int, float],
    horizon_results: Dict[int, Dict[str, object]],
    warnings: Optional[List[str]] = None,
    blackout_coverage: Optional[Dict[str, float]] = None,
    vif_all: Optional[pd.DataFrame] = None,
    vif_continuous: Optional[pd.DataFrame] = None,
    feature_columns: Optional[List[str]] = None,
    excluded_features: Optional[List[str]] = None,
    bull_div_distribution: Optional[Dict[int, int]] = None,
    bull_div_candle_distribution: Optional[Dict[int, int]] = None,
    exclude_crisis_period: bool = False,
) -> str:
    market_label = (market or "Kaikki markkinat").upper()
    features_line = (
        "Käytetyt featuret: " + ", ".join(feature_columns or FEATURE_COLUMNS)
    )
    crisis_line = (
        "Kriisijakso poistettu analyyseista: "
        f"{'Kyllä' if exclude_crisis_period else 'Ei'} ({CRISIS_START} – {CRISIS_END})"
    )
    lines = [
        f"Markkina: {market_label}",
        f"Kynttilätyyppi: {pattern_label}",
        "Käytetyt horisontit: " + ", ".join(f"{h} pv" for h in sorted(horizons)),
        "Rajat (%): "
        + ", ".join(
            f"success{h}: {thresholds.get(h, float('nan')):.2f}"
            for h in sorted(DEFAULT_SUCCESS_THRESHOLDS.keys())
        ),
        crisis_line,
        features_line,
    ]
    if bull_div_distribution:
        formatted = ", ".join(
            f"{offset}: {count}" for offset, count in sorted(bull_div_distribution.items())
        )
        lines.append(
            f"Bullish Divergence offset -jakauma (koko datasetti): {formatted}"
        )
    if bull_div_candle_distribution:
        formatted = ", ".join(
            f"{offset}: {count}"
            for offset, count in sorted(bull_div_candle_distribution.items())
        )
        lines.append(
            f"Bullish Divergence offset -jakauma (kynttilärivit): {formatted}"
        )
    if excluded_features:
        lines.append(
            "Pois jätetyt featuret: " + ", ".join(excluded_features)
        )
    lines.append("")
    if blackout_coverage:
        lines.extend(
            [
                (
                    "Rivejä yhteensä (valitulla markkinalla/patternilla): "
                    f"{blackout_coverage.get('total_rows', 0)}"
                ),
                (
                    "Rivejä, joilla blackout-dataa: "
                    f"{blackout_coverage.get('with_bo_rows', 0)} "
                    f"({blackout_coverage.get('with_bo_pct', 0.0):.1f} %)"
                ),
                (
                    "Rivejä ilman blackout-dataa: "
                    f"{blackout_coverage.get('without_bo_rows', 0)} "
                    f"({blackout_coverage.get('without_bo_pct', 0.0):.1f} %)"
                ),
                "",
            ]
        )
    if warnings:
        lines.append("VAROITUKSET:")
        lines.extend(f"- {msg}" for msg in warnings)
        lines.append("")

    if vif_all is not None:
        lines.append("== VIF-analyysi (kaikki featuret) ==")
        lines.extend(vif_all.head(20).to_string(index=False).splitlines())
        lines.append("")
    if vif_continuous is not None:
        lines.append("== VIF-analyysi (vain jatkuvat featuret) ==")
        lines.extend(vif_continuous.head(20).to_string(index=False).splitlines())
        lines.append("")

    for horizon in sorted(horizon_results.keys()):
        section = horizon_results[horizon]
        logistic = section["logistic"]
        linear = section["linear"]
        lines.extend(
            [
                "=" * 60,
                f"== Horisontti: {horizon} päivää ==",
                f"Rivejä: {section['row_count']}",
                "",
                section["summary"],
                "",
            ]
        )
        blackout = section.get("blackout_stats") or {}
        if blackout:
            lines.extend(
                [
                    "== Blackout-ikkuna-analyysi ==",
                    (
                        f"Blackout-ikkuna (earnings/dividend): "
                        f"success{horizon} = {blackout.get('blackout_rate', 0.0):.3f} "
                        f"(n={blackout.get('blackout_n', 0)})"
                    ),
                    (
                        f"Ei blackout-ikkunaa: "
                        f"success{horizon} = {blackout.get('non_blackout_rate', 0.0):.3f} "
                        f"(n={blackout.get('non_blackout_n', 0)})"
                    ),
                    "",
                ]
            )
        crisis = section.get("crisis_stats") or {}
        crisis_stats = crisis.get("stats") or {}
        has_column = crisis.get("has_column", False)
        crisis_excluded = crisis.get("excluded", False)
        if crisis_excluded or has_column:
            lines.append("== Kriisijakso-analyysi ==")
            if crisis_excluded:
                lines.append(
                    "Kriisijakso on poistettu analyyseista (exclude_crisis_period = True)."
                )
            elif not has_column:
                lines.append("is_crisis-saraketta ei löytynyt datasta.")
            else:
                if not crisis.get("has_crisis_rows", False):
                    lines.append("Ei yhtään riviä kriisijaksolta (is_crisis = 1).")
                if not crisis_stats:
                    lines.append("Ei kriisi-/normaalijakaumaa laskettavaksi.")
                for label in CRISIS_SUCCESS_LABELS:
                    stats = crisis_stats.get(label)
                    if not stats:
                        continue
                    lines.append(
                        (
                            f"{label}: kriisi {stats['crisis_rate']:.3f} "
                            f"(n={stats['crisis_n']}) | normaali {stats['normal_rate']:.3f} "
                            f"(n={stats['normal_n']})"
                        )
                    )
            lines.append("")
        combo_lines = section.get("combo_lines")
        if combo_lines:
            lines.extend(combo_lines)
        diag = section.get("diag_logistic")
        if diag:
            lines.append(
                f"== Bullish Divergence + kynttiläkombo diagnostinen logistinen (H{horizon}) =="
            )
            lines.append(f"AUC: {diag.get('auc', float('nan')):.3f}")
            top_pos = diag.get("top_positive")
            if isinstance(top_pos, pd.Series) and not top_pos.empty:
                lines.append("Top positiiviset koefit:")
                lines.extend(_format_series(top_pos).splitlines())
            top_neg = diag.get("top_negative")
            if isinstance(top_neg, pd.Series) and not top_neg.empty:
                lines.append("Top negatiiviset koefit:")
                lines.extend(_format_series(top_neg).splitlines())
            lines.append("")
        lines.extend(
            [
                f"== Logistinen regressio (success{horizon}) ==",
                f"AUC: {logistic['auc']:.3f}",
                logistic["classification_report"].strip(),
                "",
                "Top 15 positiivista:",
                _format_series(logistic["top_positive"]),
                "",
                "Top 15 negatiivista:",
                _format_series(logistic["top_negative"]),
                "",
                "Feature importance (|coef|, top 20):",
                _format_series(logistic["importance"].head(20)),
                "",
                f"== Lineaarinen regressio (y{horizon}) ==",
                linear["summary"],
                "",
                "Feature importance (|beta|, top 20):",
                _format_series(linear["importance"].head(20)),
                "",
            ]
        )
    combo_summary_lines = _build_combo_summary_section(horizon_results)
    if combo_summary_lines:
        lines.extend(combo_summary_lines)
    return "\n".join(lines)


def _build_bullish_divergence_report(model_payload: Dict[str, object]) -> str:
    config = model_payload.get("config", {}) if model_payload else {}
    row_counts = model_payload.get("row_counts", {}) if model_payload else {}
    base_rates = model_payload.get("base_rates", {}) if model_payload else {}
    logistic = model_payload.get("logistic", {}) if model_payload else {}
    ols = model_payload.get("ols", {}) if model_payload else {}

    def _fmt(val: object) -> str:
        try:
            num = float(val)
        except (TypeError, ValueError):
            return "NaN"
        if np.isnan(num):
            return "NaN"
        return f"{num:.3f}"

    horizons = config.get("horizons", [])
    market_label = (config.get("market") or "__all__").upper()
    lines = [
        "== Bullish Divergence -ydinmalli ==",
        f"Markkina: {market_label}",
        "Horisontit: " + ", ".join(f"{h} pv" for h in horizons),
        (
            f"Rivejä yhteensä: {row_counts.get('total', 0)} | "
            f"BullDiv: {row_counts.get('bull_div_rows', 0)} | "
            f"Downtrend: {row_counts.get('downtrend_rows', 0)}"
        ),
        "",
    ]
    for horizon in horizons:
        lines.append("-" * 60)
        lines.append(f"Horisontti {horizon} päivää")
        base = base_rates.get(horizon, {})
        lines.append(
            "Base success% (Kaikki / BullDiv / Downtrend): "
            f"{_fmt(base.get('all'))} / {_fmt(base.get('bull_div'))} / {_fmt(base.get('downtrend'))}"
        )
        log_entry = logistic.get(horizon, {})
        if log_entry.get("error"):
            lines.append(f"Logistinen malli: {log_entry['error']}")
        else:
            lines.append(f"Logistinen AUC: {_fmt(log_entry.get('auc'))}")
            report = log_entry.get("classification_report")
            if report:
                lines.append(report.strip())
        ols_entry = ols.get(horizon, {})
        if ols_entry.get("error"):
            lines.append(f"OLS-malli: {ols_entry['error']}")
        else:
            lines.append(f"OLS R^2: {_fmt(ols_entry.get('r2'))}")
    return "\n".join(lines)


def _format_series(series: pd.Series) -> str:
    return "\n".join(f"{idx}: {val:.4f}" for idx, val in series.items())


def _build_combo_summary_section(
    horizon_results: Dict[int, Dict[str, object]]
) -> List[str]:
    lines: List[str] = []
    for horizon in (5, 10):
        section = horizon_results.get(horizon)
        if not section:
            continue
        combo_features = section.get("combo_features") or []
        if not combo_features:
            continue
        logistic_result = section.get("logistic") or {}
        combo_auc = logistic_result.get("auc")
        base_result = section.get("logistic_base") or {}
        base_auc = base_result.get("auc")
        if combo_auc is None:
            continue
        lines.append(
            f"== Bullish Divergence + kynttiläkombo -featuret (H{horizon}) =="
        )
        improvement = (
            combo_auc - base_auc if base_auc is not None else float("nan")
        )
        base_text = f"{base_auc:.3f}" if base_auc is not None else "N/A"
        lines.append(
            f"Base-malli ilman comboja: AUC={base_text} | Combo-malli: AUC={combo_auc:.3f} | Parannus: {improvement:.3f}"
        )
        importance = logistic_result.get("importance")
        if isinstance(importance, pd.Series):
            combo_importance = importance.loc[
                importance.index.isin(combo_features)
            ].head(min(5, len(combo_features)))
            if not combo_importance.empty:
                lines.append("Top combo-featuret (|coef|):")
                lines.extend(_format_series(combo_importance).splitlines())
        lines.append("")
    return lines


def _write_report(report_text: str) -> Path:
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = data_dir / f"regression_report_{timestamp}.txt"
    path.write_text(report_text, encoding="utf-8")
    return path


def run_results_data_diagnostics(
    db_path: Path | str = DEFAULT_DB_PATH,
    success_thresholds: Optional[Dict[int, float]] = None,
    market: Optional[str] = None,
) -> str:
    """
    Tarkistaa results_data-taulun terveyden:
    - puuttuvat t2/t5/t10/t20
    - success-labelien jakaumat
    - success-labelien arvot (0/1/NaN)
    - pattern-kohtaiset success-%:t
    - (ticker, date) duplikaatit

    Palauttaa tekstiraportin (str).
    """
    lines: List[str] = []

    df = load_data(db_path=db_path, market=market)
    if df.empty:
        return "results_data on tyhjä – generoi data ensin."

    lines.append("== RESULTS_DATA DIAGNOSTIIKKA ==")
    lines.append(f"Rivejä yhteensä: {len(df)}")
    if market:
        lines.append(f"Markkinafiltteri: {market}")
    lines.append("")

    missing_info: Dict[str, object] = {}
    for col in RETURN_COLUMNS:
        if col not in df.columns:
            missing_info[col] = "PUUTTUU SARAKESTA"
            continue
        n_missing = int(df[col].isna().sum())
        missing_info[col] = n_missing

    lines.append("== Puuttuvat tulevaisuuden hintasarakeet (t2/t5/t10/t20) ==")
    for col, val in missing_info.items():
        if isinstance(val, str):
            lines.append(f"{col}: {val}")
        else:
            pct = val / len(df) * 100.0
            lines.append(f"{col}: {val} riviä puuttuu ({pct:.2f} %)")
    lines.append("")

    try:
        df = add_return_labels(df.copy(), thresholds=success_thresholds)
    except ValueError as exc:
        lines.append("Virhe add_return_labels-funktiossa:")
        lines.append(str(exc))
        return "\n".join(lines)

    lines.append("== success-labelien arvoalueet ==")
    for horizon in sorted(DEFAULT_SUCCESS_THRESHOLDS.keys()):
        label_col = f"success{horizon}"
        if label_col not in df.columns:
            lines.append(f"{label_col}: sarake puuttuu")
            continue
        vals = df[label_col].dropna().unique()
        vals_sorted = sorted(vals.tolist())
        n_nan = int(df[label_col].isna().sum())
        lines.append(
            f"{label_col}: uniikit arvot (ilman NaN): {vals_sorted}, NaN: {n_nan}"
        )
    lines.append("")

    lines.append("== success5 %-jakauma pattern-koodeittain ==")
    label_col = "success5"
    if label_col in df.columns and PATTERN_COLUMN in df.columns:
        grp = df.groupby(PATTERN_COLUMN)[label_col].agg(
            success_mean="mean", count="count"
        )
        grp = grp.sort_index()
        for code, row in grp.iterrows():
            pattern_name = PATTERN_LABELS.get(code, f"Pattern {code}")
            rate = row["success_mean"]
            n = int(row["count"])
            rate_str = "NaN" if pd.isna(rate) else f"{rate:.3f}"
            lines.append(f"{code} ({pattern_name}): success5 = {rate_str} (n={n})")
    else:
        lines.append("Ei voitu laskea pattern-kohtaista jakaumaa.")
    lines.append("")

    if "ticker" in df.columns and "date" in df.columns:
        dup_mask = df.duplicated(subset=["ticker", "date"], keep=False)
        n_dups = int(dup_mask.sum())
        lines.append("== (ticker, date) duplikaatit ==")
        lines.append(f"Duplikaattirivejä: {n_dups}")
        if n_dups > 0:
            sample = df.loc[dup_mask, ["ticker", "date", PATTERN_COLUMN]].head(20)
            lines.append("Ensimmäiset 20 duplikaattia:")
            lines.append(sample.to_string(index=False))
    else:
        lines.append("Duplikaattitarkistus ohitettu (ticker/date-saraketta ei ole).")

    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    result = run_regression_for_market()
    print(result["report"])
    latest_horizon = max(result["horizons"].keys())
    logistic_result = result["horizons"][latest_horizon]["logistic"]
    linear_result = result["horizons"][latest_horizon]["linear"]
    print("\n== Logistinen feature importance (|coef|, top 20) ==")
    print(logistic_result["importance"].head(20))
    print("\n== Lineaarinen feature importance (|beta|, top 20) ==")
    print(linear_result["importance"].head(20))
    if result.get("report_path"):
        print(f"\nRaportti tallennettu: {result['report_path']}")

    print("\n" + "=" * 80)
    print("AJETAAN RESULTS_DATA-DIAGNOSTIIKKA...\n")
    diag_report = run_results_data_diagnostics()
    print(diag_report)
