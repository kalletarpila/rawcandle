from __future__ import annotations

from typing import Any, Sequence
import logging

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


def compute_feature_compare(
    top: pd.DataFrame,
    universe: pd.DataFrame,
    feature_cols: Sequence[str],
) -> pd.DataFrame:
    """
    Compare feature statistics between Top-N and the full universe.
    Missing values are preserved (NOT forced to 0) to avoid bias.
    Adds missing-rate diagnostics.
    """
    if not feature_cols:
        return pd.DataFrame()

    top_stats = top[feature_cols].apply(pd.to_numeric, errors="coerce")
    universe_stats = universe[feature_cols].apply(pd.to_numeric, errors="coerce")

    compare = pd.DataFrame(index=feature_cols)
    compare["top_mean"] = top_stats.mean()
    compare["top_median"] = top_stats.median()
    compare["universe_mean"] = universe_stats.mean()
    compare["universe_median"] = universe_stats.median()
    compare["top_q25"] = top_stats.quantile(0.25)
    compare["top_q75"] = top_stats.quantile(0.75)
    compare["universe_q25"] = universe_stats.quantile(0.25)
    compare["universe_q75"] = universe_stats.quantile(0.75)

    # Missing-rate diagnostics (0..1)
    compare["top_missing_rate"] = top_stats.isna().mean()
    compare["universe_missing_rate"] = universe_stats.isna().mean()

    compare["diff"] = compare["top_mean"] - compare["universe_mean"]

    denom = compare["universe_mean"].replace(0, np.nan)
    compare["pct_change"] = compare["diff"] / denom
    compare["pct_change"] = compare["pct_change"].replace([np.inf, -np.inf], np.nan)

    compare = compare.reset_index().rename(columns={"index": "feature"})
    compare["abs_diff"] = compare["diff"].abs()

    # NOTE: do NOT fillna(0) here; UI can decide display defaults later.
    compare = compare.sort_values(by="abs_diff", ascending=False)
    return compare


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

    compare = compute_feature_compare(top, universe, validated_features)
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
