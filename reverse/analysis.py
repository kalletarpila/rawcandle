from __future__ import annotations

from typing import Any, Sequence
import logging
from math import erf, sqrt

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler

from . import queries, schema
from .utils import notify_progress


logger = logging.getLogger(__name__)


def load_universe(
    conn,
    params: dict[str, Any],
) -> pd.DataFrame:
    """
    Load the analysis universe from results_data table using params.
    """
    sql, sql_params = queries.build_universe_query(params)
    df = queries.safe_read_results_data(conn, sql, sql_params)
    if df.empty:
        return df
    return df


def select_topN(
    df: pd.DataFrame,
    horizon: int,
    top_n: int,
    *,
    dedupe_ticker_date: bool = False,
) -> pd.DataFrame:
    """
    Select the Top-N rows based on forward return horizon.
    Optionally dedupe to one row per (ticker, date) by keeping max return row.
    """
    if df.empty:
        return df
    horizon_col = f"t{horizon}"
    if horizon_col not in df.columns:
        raise ValueError(f"Data set does not contain required column '{horizon_col}'")

    filtered = df[df[horizon_col].notna()].copy()
    if filtered.empty:
        return filtered

    filtered = filtered.sort_values(by=horizon_col, ascending=False)

    if dedupe_ticker_date:
        # keep one best row per ticker+date
        filtered = filtered.drop_duplicates(subset=["ticker", "date"], keep="first")
        filtered = filtered.sort_values(by=horizon_col, ascending=False)

    return filtered.head(max(1, int(top_n)))


def _norm_sf_two_sided(z: float) -> float:
    """Two-sided tail probability from z using error function (no scipy dependency)."""
    if np.isnan(z):
        return np.nan
    cdf = 0.5 * (1 + erf(z / sqrt(2)))
    return 2 * (1 - cdf if z >= 0 else cdf)


def _bh_q_values(p_values: list[float]) -> list[float]:
    """Benjamini–Hochberg FDR."""
    n = len(p_values)
    if n == 0:
        return []
    sorted_idx = np.argsort(p_values)
    p_sorted = np.array(p_values)[sorted_idx]
    q = np.empty(n)
    prev = 1.0
    for i in range(n - 1, -1, -1):
        rank = i + 1
        val = p_sorted[i] * n / rank
        prev = min(prev, val)
        q[i] = min(prev, 1.0)
    result = np.empty(n)
    result[sorted_idx] = q
    return result.tolist()


def compute_feature_scoring(
    top: pd.DataFrame,
    universe: pd.DataFrame,
    feature_cols: Sequence[str],
) -> pd.DataFrame:
    """
    Compute statistical scoring for features between Top-N and universe.
    Produces effect sizes, p-values and q-values (BH FDR).
    """
    if not feature_cols:
        return pd.DataFrame()

    rows: list[dict[str, Any]] = []
    p_values: list[float] = []

    def _is_binary(series: pd.Series) -> bool:
        non_null = series.dropna().unique()
        if len(non_null) == 0:
            return False
        return set(non_null).issubset({0, 1})

    for col in feature_cols:
        top_col = pd.to_numeric(top.get(col, pd.Series(dtype=float)), errors="coerce")
        uni_col = pd.to_numeric(universe.get(col, pd.Series(dtype=float)), errors="coerce")
        top_missing = float(top_col.isna().mean()) if len(top_col) else np.nan
        uni_missing = float(uni_col.isna().mean()) if len(uni_col) else np.nan

        entry: dict[str, Any] = {
            "feature": col,
            "top_missing_rate": top_missing,
            "universe_missing_rate": uni_missing,
            "kind": "numeric",
            "p_value": np.nan,
            "q_value": np.nan,
            "effect_size": np.nan,
        }

        if _is_binary(pd.concat([top_col, uni_col])):
            entry["kind"] = "binary"
            top_vals = top_col.dropna()
            uni_vals = uni_col.dropna()
            if len(top_vals) == 0 or len(uni_vals) == 0:
                rows.append(entry)
                p_values.append(np.nan)
                continue
            top_rate = float(top_vals.mean())
            uni_rate = float(uni_vals.mean())
            entry["top_rate"] = top_rate
            entry["universe_rate"] = uni_rate
            entry["diff"] = top_rate - uni_rate
            entry["pct_change"] = np.nan
            # effect size: log odds ratio with smoothing to avoid inf
            eps = 1e-6
            odds_top = (top_rate + eps) / (1 - top_rate + eps)
            odds_uni = (uni_rate + eps) / (1 - uni_rate + eps)
            entry["effect_size"] = float(np.log(odds_top) - np.log(odds_uni))

            try:
                from scipy.stats import fisher_exact

                table = [
                    [top_vals.sum(), len(top_vals) - top_vals.sum()],
                    [uni_vals.sum(), len(uni_vals) - uni_vals.sum()],
                ]
                _, p_val = fisher_exact(table, alternative="two-sided")
            except Exception:
                # two-proportion z-test fallback
                p_pool = ((top_vals.sum() + uni_vals.sum()) / (len(top_vals) + len(uni_vals)))
                denom = p_pool * (1 - p_pool) * (1 / len(top_vals) + 1 / len(uni_vals))
                if denom <= 0:
                    p_val = np.nan
                else:
                    z = (top_rate - uni_rate) / sqrt(denom)
                    p_val = _norm_sf_two_sided(abs(z))
            entry["p_value"] = p_val
            p_values.append(p_val)
            rows.append(entry)
            continue

        # numeric
        top_vals = top_col.dropna()
        uni_vals = uni_col.dropna()
        if len(top_vals) == 0 or len(uni_vals) == 0:
            rows.append(entry)
            p_values.append(np.nan)
            continue

        top_mean = float(top_vals.mean())
        uni_mean = float(uni_vals.mean())
        diff = top_mean - uni_mean
        entry["top_mean"] = top_mean
        entry["universe_mean"] = uni_mean
        entry["diff"] = diff
        denom = uni_mean if uni_mean != 0 else np.nan
        entry["pct_change"] = diff / denom if denom not in (0, np.nan) else np.nan

        # pooled std (Cohen's d)
        std_top = float(top_vals.std(ddof=1)) if len(top_vals) > 1 else np.nan
        std_uni = float(uni_vals.std(ddof=1)) if len(uni_vals) > 1 else np.nan
        pooled = np.nan
        if not np.isnan(std_top) and not np.isnan(std_uni):
            pooled = sqrt(
                (((len(top_vals) - 1) * std_top ** 2) + ((len(uni_vals) - 1) * std_uni ** 2))
                / (len(top_vals) + len(uni_vals) - 2)
            )
        if pooled and not np.isnan(pooled) and pooled > 0:
            entry["effect_size"] = diff / pooled

        try:
            from scipy.stats import mannwhitneyu

            _, p_val = mannwhitneyu(top_vals, uni_vals, alternative="two-sided")
        except Exception:
            # permutation test fallback
            combined = np.concatenate([top_vals.values, uni_vals.values])
            n1 = len(top_vals)
            obs = abs(diff)
            more_extreme = 0
            iters = min(200, max(20, len(combined)))
            rng = np.random.default_rng(42)
            for _ in range(iters):
                rng.shuffle(combined)
                new_top = combined[:n1]
                new_uni = combined[n1:]
                if abs(new_top.mean() - new_uni.mean()) >= obs:
                    more_extreme += 1
            p_val = more_extreme / iters if iters else np.nan
        entry["p_value"] = p_val
        p_values.append(p_val)
        rows.append(entry)

    # Apply BH FDR
    q_vals = _bh_q_values([pv if pv is not None else np.nan for pv in p_values])
    for row, q in zip(rows, q_vals):
        row["q_value"] = q
        row["abs_effect"] = abs(row.get("effect_size")) if row.get("effect_size") is not None else abs(row.get("diff", np.nan))

    df = pd.DataFrame(rows)
    df = df.sort_values(by="abs_effect", ascending=False)
    return df


def cluster_top(
    top: pd.DataFrame,
    feature_cols: Sequence[str],
    *,
    horizon: int,
    n_clusters: int = 5,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Cluster the Top-N winners and return labels + summary stats.
    """
    if top.empty or not feature_cols:
        return top.copy(), pd.DataFrame()

    numeric = top[feature_cols].apply(pd.to_numeric, errors="coerce")
    fill_values = numeric.median(numeric_only=True).fillna(0)
    numeric = numeric.fillna(fill_values).fillna(0)

    scaler = StandardScaler()
    scaled = scaler.fit_transform(numeric)
    cluster_count = max(1, min(int(n_clusters), len(top)))
    kmeans = KMeans(n_clusters=cluster_count, n_init=10, random_state=42)
    labels = kmeans.fit_predict(scaled)

    clustered = top.copy()
    clustered["cluster_id"] = labels

    horizon_col = f"t{horizon}"
    summaries: list[dict[str, Any]] = []
    global_means = numeric.mean()
    for cluster_id, group in clustered.groupby("cluster_id"):
        entry: dict[str, Any] = {
            "cluster_id": int(cluster_id),
            "count": int(len(group)),
        }
        if horizon_col in group.columns:
            entry[f"avg_{horizon_col}"] = float(group[horizon_col].mean())
        cluster_means = numeric.loc[group.index].mean()
        deltas = (cluster_means - global_means).abs().sort_values(ascending=False)
        entry["top_features"] = ", ".join(deltas.head(3).index.tolist())
        summaries.append(entry)
    summary_df = pd.DataFrame(summaries).sort_values("cluster_id")
    return clustered, summary_df


def run_reverse_pipeline(
    conn,
    params: dict[str, Any],
    *,
    feature_cols: Sequence[str],
    progress_cb=None,
) -> dict[str, Any]:
    """
    Run the full reverse analysis pipeline and return a result dictionary.
    """
    notify_progress(progress_cb, 0.05)
    universe = load_universe(conn, params)
    notify_progress(progress_cb, 0.15)
    if universe.empty:
        return {
            "top": pd.DataFrame(),
            "universe": universe,
            "compare": pd.DataFrame(),
            "clustered_top": pd.DataFrame(),
            "cluster_summary": pd.DataFrame(),
            "used_features": list(feature_cols),
            "params": params,
        }

    horizon = int(params.get("horizon", 10))
    top_n = int(params.get("top_n", 500))
    dedupe_topN = bool(params.get("dedupe_topN_by_ticker_date", False))

    logger.info(f"[reverse] Universe rows: {len(universe)}")
    try:
        uniq_td = universe[["ticker", "date"]].drop_duplicates().shape[0]
        logger.info(f"[reverse] Universe unique ticker+date: {uniq_td}")
    except Exception:
        logger.info("[reverse] Universe unique ticker+date: <failed to compute>")

    top = select_topN(universe, horizon, top_n, dedupe_ticker_date=dedupe_topN)
    logger.info(
        f"[reverse] TopN rows: {len(top)} using horizon t{horizon}, dedupe_ticker_date={dedupe_topN}"
    )

    validated_features = schema.validate_features(universe, feature_cols, logger=logger)
    if not validated_features:
        raise ValueError("Yhtään pyydetyistä featureista ei löytynyt results_data-taulusta.")

    compare = compute_feature_scoring(top, universe, validated_features)
    notify_progress(progress_cb, 0.5)
    clustered_top, cluster_summary = cluster_top(
        top, validated_features, horizon=horizon, n_clusters=params.get("clusters", 5)
    )
    notify_progress(progress_cb, 0.9)

    return {
        "top": top,
        "universe": universe,
        "compare": compare,
        "clustered_top": clustered_top,
        "cluster_summary": cluster_summary,
        "used_features": list(validated_features),
        "params": params,
        "dedupe_topN_by_ticker_date": dedupe_topN,
    }
