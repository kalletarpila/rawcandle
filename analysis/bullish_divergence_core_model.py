from __future__ import annotations

import sqlite3
import warnings
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

from analysis.regression_shared_utils import (
    apply_blackout_flags,
    load_blackout_dates,
    preprocess_signals,
)
from analysis.same_day_aggregates import add_same_day_aggregate_features


class BullishDivergenceModel:
    """
    Core Bullish Divergence regression engine.
    """

    RETURN_COLUMNS = ["t2", "t5", "t10", "t20"]
    PATTERN_COLUMN = "kynttila_koodi"
    DATE_CANDIDATES = ["date", "t0_date"]
    BULLISH_PATTERN = 7
    DOWNTREND_PATTERN = 0
    DEFAULT_FEATURES = [
        "vahvuus",
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
        "num_candles_same_day",
        "has_multi_candle_combo",
        "has_bullish_divergence_same_day",
        "signal_combo_code",
        "num_signals_same_day",
        "num_unique_patterns_same_day",
        "max_signal_strength_same_day",
        "second_best_strength_same_day",
        "sum_signal_strength_same_day",
        "has_same_day_cluster",
        "has_same_day_reversal_cluster",
        "is_candle_day",
    ]
    EXCLUDED_COLUMNS = {
        "recent_divergence_min_distance",
        "recent_divergence_decay_strength",
        "rolling_BullDiv_influence",
        "bullDiv_offset",
        "bullDiv_last_1d",
        "bullDiv_last_2d",
        "bullDiv_last_3d",
        "bullDiv_last_3d_any",
        "Price_slope_5",
        "Price_slope_10",
        "Reversal_Context_Score",
        "reversal_context_score",
    }
    BINARY_FEATURES = {
        "is_crisis",
        "is_candle_day",
        "has_multi_candle_combo",
        "has_bullish_divergence_same_day",
        "has_same_day_cluster",
        "has_same_day_reversal_cluster",
    }
    ALLOWED_HORIZONS = (2, 5, 10, 20)
    ALIAS_MAP = {
        PATTERN_COLUMN: "candle_pattern",
        "vahvuus": "signal_strength",
    }

    def __init__(
        self,
        market: Optional[str] = None,
        exclude_crisis_period: bool = False,
        require_blackout_data: bool = False,
        crisis_start: Optional[str] = None,
        crisis_end: Optional[str] = None,
        horizon_list: Optional[Iterable[int]] = None,
        success_thresholds: Optional[Dict[int | str, float]] = None,
        feature_include: Optional[Iterable[str]] = None,
        feature_exclude: Optional[Iterable[str]] = None,
        db_path: Path | str = Path(__file__).resolve().parents[1]
        / "data"
        / "analysis.db",
    ) -> None:
        self.market = market
        self.exclude_crisis_period = bool(exclude_crisis_period)
        self.require_blackout_data = bool(require_blackout_data)
        self.crisis_start = crisis_start
        self.crisis_end = crisis_end
        default_horizons = list(self.ALLOWED_HORIZONS)
        requested = horizon_list or default_horizons
        filtered = [int(h) for h in requested if int(h) in self.ALLOWED_HORIZONS]
        self.horizons = filtered or default_horizons
        self.db_path = Path(db_path)
        self.success_thresholds = self._normalize_thresholds(success_thresholds)
        include = (
            list(feature_include) if feature_include else list(self.DEFAULT_FEATURES)
        )
        exclude = set(feature_exclude or [])
        self.feature_whitelist = [col for col in include if col not in exclude]
        self.feature_exclusions = set(feature_exclude or []) | self.EXCLUDED_COLUMNS
        self.date_column: Optional[str] = None
        self._warnings: List[str] = []

    @staticmethod
    def _normalize_thresholds(
        thresholds: Optional[Dict[int | str, float]],
    ) -> Dict[int, float]:
        defaults = {2: 0.02, 5: 0.03, 10: 0.05, 20: 0.08}
        if not thresholds:
            return defaults
        normalized: Dict[int, float] = {}
        for key, value in thresholds.items():
            if isinstance(key, str) and key.startswith("success"):
                key = key.replace("success", "")
            try:
                horizon = int(key)
            except (TypeError, ValueError):
                continue
            normalized[horizon] = float(value)
        for h, default_val in defaults.items():
            normalized.setdefault(h, default_val)
        return normalized

    def run_all(self) -> Dict[str, object]:
        df_full = self._load_data()
        blackout_df = load_blackout_dates(db_path=self.db_path)
        df_full = apply_blackout_flags(df_full, blackout_df)

        if self.require_blackout_data:
            if "has_blackout_data" in df_full.columns:
                mask_bo = df_full["has_blackout_data"] == 1
                df_full = df_full.loc[mask_bo].reset_index(drop=True)
            else:
                self._warnings.append(
                    "has_blackout_data-saraketta ei löytynyt; blackout-vaatimus ohitettiin."
                )

        df_train = df_full
        if "exclude_from_regression" in df_train.columns:
            train_mask = df_train["exclude_from_regression"].fillna(0) == 0
            df_train = df_train.loc[train_mask].reset_index(drop=True)
        else:
            df_train = df_train.copy().reset_index(drop=True)

        df_full = self._filter_bullish_divergence_cases(df_full)
        df_train = self._filter_bullish_divergence_cases(df_train)

        df_full = self._apply_crisis_exclusion(df_full)
        df_train = self._apply_crisis_exclusion(df_train)

        if df_train.empty:
            raise ValueError(
                "Ei rivejä Bullish Divergence -mallia varten suodatusten jälkeen."
            )

        df_full_raw = df_full.copy()
        df_train_raw = df_train.copy()

        df_full = preprocess_signals(df_full)
        df_full = add_same_day_aggregate_features(
            df_full_raw, df_full, self.PATTERN_COLUMN
        )
        df_train = preprocess_signals(df_train)
        df_train = add_same_day_aggregate_features(
            df_train_raw, df_train, self.PATTERN_COLUMN
        )

        df_full = self._add_return_labels(df_full)
        df_train = self._add_return_labels(df_train)

        feature_df, feature_cols, continuous_cols = self._prepare_features(df_train)
        base_rates = self._compute_base_rates(df_train)
        vif_all, vif_cont = self._run_vif(feature_df, feature_cols, continuous_cols)

        logistic_results: Dict[int, Dict[str, object]] = {}
        ols_results: Dict[int, Dict[str, object]] = {}
        used_counts: Dict[int, int] = {}

        for horizon in self.horizons:
            label_col = f"success{horizon}"
            target = (
                df_train[label_col]
                if label_col in df_train.columns
                else pd.Series(dtype=float)
            )
            logistic_results[horizon] = self._run_logistic_regression(
                feature_df, target, continuous_cols, feature_cols, label_col
            )
            used_counts[horizon] = logistic_results[horizon].get("row_count", 0)

            return_col = f"y{horizon}"
            target_return = (
                df_train[return_col]
                if return_col in df_train.columns
                else pd.Series(dtype=float)
            )
            ols_results[horizon] = self._run_ols_regression(
                feature_df, target_return, continuous_cols, feature_cols, return_col
            )

        total_rows = len(df_train)
        pattern_series = df_train[self.PATTERN_COLUMN].fillna(0).astype(int)
        full_pattern_series = df_full[self.PATTERN_COLUMN].fillna(0).astype(int)
        row_counts = {
            "total": total_rows,
            "bull_div_rows": int((pattern_series == self.BULLISH_PATTERN).sum()),
            "downtrend_rows": int((pattern_series == self.DOWNTREND_PATTERN).sum()),
            "used_for_regression": used_counts,
            "total_full": len(df_full),
            "bull_div_rows_full": int(
                (full_pattern_series == self.BULLISH_PATTERN).sum()
            ),
            "downtrend_rows_full": int(
                (full_pattern_series == self.DOWNTREND_PATTERN).sum()
            ),
        }

        return {
            "config": {
                "market": self.market,
                "horizons": self.horizons,
                "success_thresholds": self.success_thresholds,
                "exclude_crisis_period": self.exclude_crisis_period,
                "require_blackout_data": self.require_blackout_data,
                "crisis_start": self.crisis_start,
                "crisis_end": self.crisis_end,
                "feature_columns": feature_cols,
            },
            "row_counts": row_counts,
            "base_rates": base_rates,
            "vif": {"all": vif_all, "continuous": vif_cont},
            "logistic": logistic_results,
            "ols": ols_results,
            "warnings": list(self._warnings),
        }

    def _load_data(self) -> pd.DataFrame:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Analysis-kantaa ei löytynyt: {self.db_path}")
        query = "SELECT * FROM results_data"
        params: List[object] = []
        if self.market and self.market not in {"", "__all__"}:
            query += " WHERE lower(market) = ?"
            params.append(self.market.strip().lower())
        with sqlite3.connect(self.db_path) as conn:
            df = pd.read_sql_query(query, conn, params=params)
        if df.empty:
            return df
        df = self._apply_alias_columns(df)
        for candidate in self.DATE_CANDIDATES:
            if candidate in df.columns:
                self.date_column = candidate
                df[candidate] = pd.to_datetime(df[candidate], errors="coerce")
                break
        columns_to_drop = [col for col in self.EXCLUDED_COLUMNS if col in df.columns]
        if columns_to_drop:
            df = df.drop(columns=columns_to_drop)
        if self.PATTERN_COLUMN in df.columns:
            df[self.PATTERN_COLUMN] = df[self.PATTERN_COLUMN].fillna(0).astype(int)
        return df

    def _apply_alias_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        for alias, source in self.ALIAS_MAP.items():
            if alias not in df.columns and source in df.columns:
                df[alias] = df[source]
        return df

    def _filter_bullish_divergence_cases(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or self.PATTERN_COLUMN not in df.columns:
            return df
        mask = df[self.PATTERN_COLUMN].isin(
            {self.BULLISH_PATTERN, self.DOWNTREND_PATTERN}
        )
        return df.loc[mask].reset_index(drop=True)

    def _apply_crisis_exclusion(self, df: pd.DataFrame) -> pd.DataFrame:
        if (
            not self.exclude_crisis_period
            or not self.crisis_start
            or not self.crisis_end
            or not self.date_column
            or self.date_column not in df.columns
        ):
            return df
        start = pd.Timestamp(self.crisis_start)
        end = pd.Timestamp(self.crisis_end)
        mask = (df[self.date_column] < start) | (df[self.date_column] > end)
        return df.loc[mask].reset_index(drop=True)

    def _add_return_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        missing = [col for col in self.RETURN_COLUMNS if col not in df.columns]
        if missing:
            raise ValueError(f"Datasetistä puuttuu sarakkeet: {missing}")
        for col in self.RETURN_COLUMNS:
            horizon = int(col[1:])
            ret_col = f"y{horizon}"
            df[ret_col] = (df[col] - 100.0) / 100.0
        for horizon, threshold in self.success_thresholds.items():
            label_col = f"success{horizon}"
            ret_col = f"y{horizon}"
            if ret_col in df.columns:
                df[label_col] = (df[ret_col] > threshold).astype(int)
        return df

    def _prepare_features(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, List[str], List[str]]:
        if df.empty:
            return df.copy(), [], []
        df = df.copy()
        if self.PATTERN_COLUMN in df.columns:
            df["is_candle_day"] = (
                df[self.PATTERN_COLUMN].fillna(0).astype(int) != 0
            ).astype(int)
        available = [col for col in self.feature_whitelist if col in df.columns]
        available = [col for col in available if col not in self.feature_exclusions]
        feature_df = df[available].copy()
        for col in available:
            feature_df[col] = pd.to_numeric(feature_df[col], errors="coerce")
        continuous_cols = [col for col in available if col not in self.BINARY_FEATURES]
        return feature_df, available, continuous_cols

    def _compute_base_rates(self, df: pd.DataFrame) -> Dict[int, Dict[str, float]]:
        rates: Dict[int, Dict[str, float]] = {}
        if df.empty or self.PATTERN_COLUMN not in df.columns:
            return rates
        pattern_series = df[self.PATTERN_COLUMN].fillna(0).astype(int)
        for horizon in self.horizons:
            label = f"success{horizon}"
            if label not in df.columns:
                continue
            series = df[label]

            def _mean(mask: pd.Series) -> float:
                subset = series.loc[mask & series.notna()]
                return float(subset.mean()) if not subset.empty else float("nan")

            base = series.dropna()
            rates[horizon] = {
                "all": float(base.mean()) if not base.empty else float("nan"),
                "bull_div": _mean(pattern_series == self.BULLISH_PATTERN),
                "downtrend": _mean(pattern_series == self.DOWNTREND_PATTERN),
            }
        return rates

    def _run_vif(
        self,
        feature_df: pd.DataFrame,
        feature_cols: List[str],
        continuous_cols: List[str],
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        if not feature_cols:
            empty = pd.DataFrame(columns=["feature", "VIF"])
            return empty, empty
        data_all = feature_df.dropna(subset=feature_cols)
        if data_all.empty:
            empty = pd.DataFrame(columns=["feature", "VIF"])
            return empty, empty
        X_all = data_all[feature_cols]
        vif_rows = []
        for idx, col in enumerate(X_all.columns):
            try:
                with warnings.catch_warnings():
                    warnings.filterwarnings("ignore", category=RuntimeWarning)
                    vif_val = variance_inflation_factor(X_all.values, idx)
            except Exception:
                vif_val = float("nan")
            vif_rows.append({"feature": col, "VIF": float(vif_val)})
        vif_all = pd.DataFrame(vif_rows)
        if continuous_cols:
            cont_data = data_all[continuous_cols]
            vif_cont_rows = []
            for idx, col in enumerate(cont_data.columns):
                try:
                    with warnings.catch_warnings():
                        warnings.filterwarnings("ignore", category=RuntimeWarning)
                        vif_val = variance_inflation_factor(cont_data.values, idx)
                except Exception:
                    vif_val = float("nan")
                vif_cont_rows.append({"feature": col, "VIF": float(vif_val)})
            vif_cont = pd.DataFrame(vif_cont_rows)
        else:
            vif_cont = pd.DataFrame(columns=["feature", "VIF"])
        return vif_all, vif_cont

    def _run_logistic_regression(
        self,
        feature_df: pd.DataFrame,
        target: pd.Series,
        continuous_cols: List[str],
        feature_cols: List[str],
        label_col: str,
    ) -> Dict[str, object]:
        if not feature_cols:
            return {"row_count": 0, "error": "Ei featureja logistista mallia varten."}
        subset = feature_df.join(target.rename(label_col))
        subset = subset.dropna(subset=feature_cols + [label_col])
        row_count = len(subset)
        if row_count == 0 or subset[label_col].nunique() < 2:
            return {
                "row_count": row_count,
                "error": "Ei riittävästi dataa logistiselle mallille.",
            }
        X = subset[feature_cols]
        y = subset[label_col]
        binary_cols = [col for col in feature_cols if col not in continuous_cols]
        scaler = StandardScaler() if continuous_cols else None
        try:
            X_train, X_test, y_train, y_test = train_test_split(
                X,
                y,
                test_size=0.2,
                random_state=42,
                stratify=y,
            )
        except ValueError as exc:
            return {
                "row_count": row_count,
                "error": f"Train/test jako epäonnistui: {exc}",
            }

        if continuous_cols:
            scaler.fit(X_train[continuous_cols])

        def _stack(data: pd.DataFrame) -> np.ndarray:
            parts: List[np.ndarray] = []
            if continuous_cols:
                assert scaler is not None
                parts.append(scaler.transform(data[continuous_cols]))
            if binary_cols:
                parts.append(data[binary_cols].to_numpy(dtype=float))
            return np.hstack(parts) if parts else np.empty((len(data), 0))

        X_train_full = _stack(X_train)
        X_test_full = _stack(X_test)
        feature_names = continuous_cols + binary_cols
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
        coef = pd.Series(model.coef_[0], index=feature_names)
        importance = coef.abs().sort_values(ascending=False)
        return {
            "row_count": row_count,
            "auc": float(auc),
            "classification_report": report,
            "coef": coef,
            "importance": importance,
            "model": model,
            "scaler": scaler,
            "feature_names": feature_names,
        }

    def _run_ols_regression(
        self,
        feature_df: pd.DataFrame,
        target: pd.Series,
        continuous_cols: List[str],
        feature_cols: List[str],
        target_col: str,
    ) -> Dict[str, object]:
        subset = feature_df.join(target.rename(target_col))
        subset = subset.dropna(subset=feature_cols + [target_col])
        row_count = len(subset)
        if row_count == 0:
            return {"row_count": 0, "error": "Ei riittävästi dataa OLS-mallille."}
        if not feature_cols:
            return {"row_count": row_count, "error": "Ei featureja OLS-mallille."}
        X = subset[feature_cols]
        y = subset[target_col]
        binary_cols = [col for col in feature_cols if col not in continuous_cols]
        scaler = StandardScaler() if continuous_cols else None
        matrices: List[np.ndarray] = []
        if continuous_cols:
            matrices.append(scaler.fit_transform(X[continuous_cols]))
        if binary_cols:
            matrices.append(X[binary_cols].to_numpy(dtype=float))
        X_full = np.hstack(matrices) if matrices else np.empty((len(X), 0))
        feature_names = continuous_cols + binary_cols
        X_df = pd.DataFrame(X_full, columns=feature_names, index=X.index)
        X_const = sm.add_constant(X_df, has_constant="add")
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=RuntimeWarning)
            model = sm.OLS(y, X_const).fit()
        coef = model.params.drop("const", errors="ignore")
        importance = coef.abs().sort_values(ascending=False)
        summary_text = model.summary().as_text()
        return {
            "row_count": row_count,
            "r2": float(model.rsquared),
            "summary": summary_text,
            "coef": coef,
            "importance": importance,
            "model": model,
        }
