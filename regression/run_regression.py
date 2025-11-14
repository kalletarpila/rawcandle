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
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.outliers_influence import variance_inflation_factor

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "analysis.db"

RETURN_COLUMNS = ["t2", "t5", "t10", "t20"]
FEATURE_COLUMNS = [
    # Peruspsykologia ja kynttilä
    "vahvuus",
    "RSI14_t0",
    "t0_volyymi",
    "t0_close_norm",
    "BullDiv_strength",
    "BullDiv_recent_strength",
    "BullDiv_recent_offset",
    "Has_BullDiv_recent",

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

    # Markkinaympäristö ja indeksivola
    "SPX_10",
    "SPX_20",
    "SPX_volatility_10",
    "NDX_10",
    "NDX_20",
    "NDX_volatility_10",
]
PATTERN_COLUMN = "kynttila_koodi"
MARKET_COLUMN = "market"
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


# ------------- 3. Featurejen valinta -----------------

def build_feature_matrix(
    df: pd.DataFrame,
) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Valitse psykologiset ja tekniset featuret sekä koodaa kategoriset.
    """
    required_cols = FEATURE_COLUMNS + [PATTERN_COLUMN, MARKET_COLUMN]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Datasetistä puuttuu sarakkeet: {missing}")

    df["is_candle_day"] = (df[PATTERN_COLUMN].fillna(0).astype(int) != 0).astype(int)

    continuous_cols = FEATURE_COLUMNS.copy()
    feature_df = df[continuous_cols].copy()

    categorical = df[[PATTERN_COLUMN, MARKET_COLUMN]].astype("category")
    dummy_df = pd.DataFrame({"is_candle_day": df["is_candle_day"]})
    dummy_df = dummy_df.join(categorical)
    dummy_df = pd.get_dummies(
        dummy_df, columns=[PATTERN_COLUMN, MARKET_COLUMN], drop_first=True
    )
    dummy_df = dummy_df.astype(float)
    feature_df = pd.concat([feature_df, dummy_df], axis=1)
    dummy_cols = [col for col in feature_df.columns if col not in continuous_cols]
    return feature_df, continuous_cols, dummy_cols


def calculate_vif(X: pd.DataFrame) -> pd.DataFrame:
    """Laskee VIF-arvot (Variance Inflation Factor) featurematriisille X."""
    vif_rows: list[dict[str, float | str]] = []
    X_np = X.values
    for i in range(X.shape[1]):
        try:
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


# ------------- 5. Logistinen regressio -----------------

def run_logistic_regression(
    X: pd.DataFrame, y: pd.Series, continuous_cols: list[str]
) -> Dict[str, object]:
    """
    Logistinen regressio P(success5=1 | featuret).
    """
    if y.nunique() < 2:
        raise ValueError("success5 sisältää vain yhden luokan – lisää dataa.")

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    dummy_cols = [col for col in X.columns if col not in continuous_cols]
    scaler = StandardScaler()
    X_train_cont = scaler.fit_transform(X_train[continuous_cols])
    X_test_cont = scaler.transform(X_test[continuous_cols])
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
    scaler = StandardScaler()
    X_cont_scaled = scaler.fit_transform(X[continuous_cols])
    X_dummy_raw = (
        X[dummy_cols].to_numpy(dtype=float)
        if dummy_cols
        else np.empty((len(X), 0))
    )
    X_full = np.hstack([X_cont_scaled, X_dummy_raw])

    X_scaled_df = pd.DataFrame(
        X_full, columns=continuous_cols + dummy_cols, index=X.index
    )
    friendly_cols = [_friendly_feature_name(name) for name in X_scaled_df.columns]
    X_scaled_df.columns = friendly_cols
    X_const = sm.add_constant(X_scaled_df)
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


# ------------- 7. Yhteenveto & rajapinta -----------------

def run_regression_for_market(
    market: Optional[str] = None,
    pattern_code: Optional[int] = None,
    success_horizons: Optional[List[int]] = None,
    success_thresholds: Optional[Dict[int, float]] = None,
    db_path: Path | str = DEFAULT_DB_PATH,
    write_report: bool = True,
) -> Dict[str, object]:
    """
    Suorita koko pipeline yhdelle markkinalle ja palauta tulokset.
    """
    df = load_data(db_path=db_path, market=market)
    if df.empty:
        friendly_market = "kaikki markkinat" if not market else market.upper()
        raise ValueError(
            f"Results-data tyhjä markkinalle: {friendly_market}. Suorita analyysi ensin."
        )

    df = add_return_labels(df, thresholds=success_thresholds)
    overall_row_count = len(df)
    filter_label = "Kaikki kynttilät (sis. downtrend)"

    if pattern_code is not None:
        try:
            pattern_code = int(pattern_code)
        except ValueError as exc:
            raise ValueError("Pattern-koodin tulee olla kokonaisluku") from exc
        pattern_mask = df[PATTERN_COLUMN].astype(int) == pattern_code
        downtrend_mask = df[PATTERN_COLUMN].astype(int) == 0
        filtered = df[pattern_mask | downtrend_mask]
        if filtered.empty or not pattern_mask.any():
            raise ValueError(
                f"Ei rivejä valitulle patternille {pattern_code} (downtrend lisättiin automaattisesti)."
            )
        df = filtered
        friendly = PATTERN_LABELS.get(pattern_code, f"Pattern {pattern_code}")
        filter_label = f"{friendly} + downtrend"
    horizons = success_horizons or [5]
    invalid = [h for h in horizons if h not in DEFAULT_SUCCESS_THRESHOLDS]
    if invalid:
        raise ValueError(
            f"Tuntemattomat horisontit: {invalid}. Sallittuja arvoja: "
            f"{sorted(DEFAULT_SUCCESS_THRESHOLDS.keys())}"
        )

    horizon_results: Dict[int, Dict[str, object]] = {}
    warning_messages: List[str] = []
    for horizon in horizons:
        success_label = f"success{horizon}"
        return_label = f"y{horizon}"
        subset = df.dropna(
            subset=FEATURE_COLUMNS
            + [success_label, return_label, PATTERN_COLUMN, MARKET_COLUMN]
        ).reset_index(drop=True)

        if subset.empty:
            raise ValueError(
                f"Ei riittävästi dataa horisontille {horizon} valituilla suodattimilla."
            )

        X, continuous_cols, dummy_cols = build_feature_matrix(subset)
        vif_df = calculate_vif(X)
        y_success = subset[success_label]
        y_return = subset[return_label]

        summary_text = quick_summary(subset, label_column=success_label)
        logistic_result = run_logistic_regression(X, y_success, continuous_cols)
        linear_result = run_linear_regression(X, y_return, continuous_cols)

        horizon_results[horizon] = {
            "row_count": len(subset),
            "summary": summary_text,
            "logistic": logistic_result,
            "linear": linear_result,
            "vif": vif_df,
        }
        if linear_result.get("warning"):
            warning_messages.append(f"H{horizon}: {linear_result['warning']}")

    thresholds_payload = {
        h: success_thresholds.get(h, DEFAULT_SUCCESS_THRESHOLDS[h])
        if success_thresholds
        else DEFAULT_SUCCESS_THRESHOLDS[h]
        for h in DEFAULT_SUCCESS_THRESHOLDS
    }

    report_text = _build_report_text(
        market,
        filter_label,
        horizons,
        thresholds_payload,
        horizon_results,
        warning_messages,
    )
    report_path = _write_report(report_text) if write_report else None

    return {
        "market": market,
        "row_count": len(df),
        "pattern_code": pattern_code,
        "pattern_label": filter_label,
        "success_horizons": sorted(horizons),
        "success_thresholds": thresholds_payload,
        "horizons": horizon_results,
        "report": report_text,
        "report_path": report_path,
        "warnings": warning_messages,
    }


def _build_report_text(
    market: Optional[str],
    pattern_label: str,
    horizons: List[int],
    thresholds: Dict[int, float],
    horizon_results: Dict[int, Dict[str, object]],
    warnings: Optional[List[str]] = None,
) -> str:
    market_label = (market or "Kaikki markkinat").upper()
    lines = [
        f"Markkina: {market_label}",
        f"Kynttilätyyppi: {pattern_label}",
        "Käytetyt horisontit: " + ", ".join(f"{h} pv" for h in sorted(horizons)),
        "Rajat (%): "
        + ", ".join(
            f"success{h}: {thresholds.get(h, float('nan')):.2f}"
            for h in sorted(DEFAULT_SUCCESS_THRESHOLDS.keys())
        ),
        "",
    ]
    if warnings:
        lines.append("VAROITUKSET:")
        lines.extend(f"- {msg}" for msg in warnings)
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
    return "\n".join(lines)


def _format_series(series: pd.Series) -> str:
    return "\n".join(f"{idx}: {val:.4f}" for idx, val in series.items())


def _write_report(report_text: str) -> Path:
    data_dir = PROJECT_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = data_dir / f"regression_report_{timestamp}.txt"
    path.write_text(report_text, encoding="utf-8")
    return path


if __name__ == "__main__":
    result = run_regression_for_market()
    print(result["report"])
    first_horizon = sorted(result["horizons"].keys())[0]
    vif_df = result["horizons"][first_horizon]["vif"]
    print("\n== VIF-analyysi (Variance Inflation Factor) ==")
    print(vif_df.head(20))
    latest_horizon = max(result["horizons"].keys())
    logistic_result = result["horizons"][latest_horizon]["logistic"]
    linear_result = result["horizons"][latest_horizon]["linear"]
    print("\n== Logistinen feature importance (|coef|, top 20) ==")
    print(logistic_result["importance"].head(20))
    print("\n== Lineaarinen feature importance (|beta|, top 20) ==")
    print(linear_result["importance"].head(20))
    if result.get("report_path"):
        print(f"\nRaportti tallennettu: {result['report_path']}")
