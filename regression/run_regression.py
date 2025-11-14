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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "analysis.db"

RETURN_COLUMNS = ["t2", "t5", "t10", "t20"]
FEATURE_COLUMNS = [
    "vahvuus",
    "RSI14_t0",
    "Bullish Divergence",
    "t0_volyymi",
    "t_10_hajonta",
    "t_20_hajonta",
    "t_10",
    "t_20",
    "SPX_10",
    "NDX_10",
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

ALIAS_MAP = {
    "vahvuus": "signal_strength",
    "Bullish Divergence": "bullish_divergence",
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

def build_feature_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """
    Valitse psykologiset ja tekniset featuret sekä koodaa kategoriset.
    """
    required_cols = FEATURE_COLUMNS + [PATTERN_COLUMN, MARKET_COLUMN]
    missing = [col for col in required_cols if col not in df.columns]
    if missing:
        raise ValueError(f"Datasetistä puuttuu sarakkeet: {missing}")

    df["is_candle_day"] = (df[PATTERN_COLUMN].fillna(0).astype(int) != 0).astype(int)

    feature_df = df[FEATURE_COLUMNS + ["is_candle_day"]].copy()
    categorical = df[[PATTERN_COLUMN, MARKET_COLUMN]].astype("category")
    feature_df = feature_df.join(categorical)
    feature_df = pd.get_dummies(
        feature_df, columns=[PATTERN_COLUMN, MARKET_COLUMN], drop_first=True
    )
    return feature_df


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
    X: pd.DataFrame, y: pd.Series
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

    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled = scaler.transform(X_test)

    model = LogisticRegression(
        max_iter=1000,
        class_weight="balanced",
        n_jobs=-1,
    )
    model.fit(X_train_scaled, y_train)

    y_proba = model.predict_proba(X_test_scaled)[:, 1]
    y_pred = (y_proba > 0.5).astype(int)

    auc = roc_auc_score(y_test, y_proba)
    report = classification_report(y_test, y_pred, digits=3)

    coef = pd.Series(model.coef_[0], index=X.columns).sort_values(ascending=False)
    pos = coef.head(min(15, len(coef)))
    neg = coef.tail(min(15, len(coef)))

    return {
        "auc": float(auc),
            "classification_report": report,
            "top_positive": pos,
            "top_negative": neg,
            "model": model,
        "scaler": scaler,
    }


# ------------- 6. Lineaarinen regressio -----------------

def run_linear_regression(
    X: pd.DataFrame, y: pd.Series
) -> Dict[str, object]:
    """
    Lineaarinen regressio odotetulle tuotolle (y5).
    """
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    X_scaled_df = pd.DataFrame(X_scaled, columns=X.columns, index=X.index)
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
    for idx, name in enumerate(X.columns, 1):
        column_map_lines.append(f"x{idx}: {name}")
    column_map_text = "\n".join(column_map_lines)

    summary_text = f"{model.summary().as_text()}\n\n{column_map_text}"
    return {
        "summary": summary_text,
        "model": model,
        "scaler": scaler,
        "column_map": column_map_lines,
        "condition_number": cond_number,
        "warning": warning,
    }


# ------------- 7. Yhteenveto & rajapinta -----------------

def run_regression_for_market(
    market: Optional[str] = None,
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

        X = build_feature_matrix(subset)
        y_success = subset[success_label]
        y_return = subset[return_label]

        summary_text = quick_summary(subset, label_column=success_label)
        logistic_result = run_logistic_regression(X, y_success)
        linear_result = run_linear_regression(X, y_return)

        horizon_results[horizon] = {
            "row_count": len(subset),
            "summary": summary_text,
            "logistic": logistic_result,
            "linear": linear_result,
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
        "Kaikki kynttilät (sis. downtrend)",
        horizons,
        thresholds_payload,
        horizon_results,
        warning_messages,
    )
    report_path = _write_report(report_text) if write_report else None

    return {
        "market": market,
        "row_count": overall_row_count,
        "pattern_code": None,
        "pattern_label": "Kaikki kynttilät (sis. downtrend)",
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
                f"== Lineaarinen regressio (y{horizon}) ==",
                linear["summary"],
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
    if result["report_path"]:
        print(f"\nRaportti tallennettu: {result['report_path']}")
