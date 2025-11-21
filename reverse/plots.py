from __future__ import annotations

import io
from pathlib import Path
from typing import Any, Sequence

try:  # pragma: no cover - optional dependency
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
except Exception:  # pragma: no cover
    matplotlib = None
    plt = None
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from .utils import ensure_data_dir, timestamp


def _finalize_fig(fig, *, prefix: str, output_dir: str | Path | None = None) -> dict[str, Any]:
    out_dir = ensure_data_dir(output_dir)
    filename = f"{prefix}_{timestamp()}.png"
    path = out_dir / filename
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return {"path": path, "data": buf.getvalue()}


def plot_feature_diffs(
    compare_df: pd.DataFrame, *, top_k: int = 25, output_dir: str | Path | None = None
) -> dict[str, Any] | None:
    if compare_df is None or compare_df.empty:
        return None
    if plt is None:
        return None
    subset = compare_df.copy()
    subset["abs_diff"] = subset["diff"].abs()
    subset = subset.sort_values(by="abs_diff", ascending=False).head(top_k)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.barh(subset["feature"], subset["diff"], color="#2196F3")
    ax.set_xlabel("Mean difference (Top-N - Universe)")
    ax.set_ylabel("Feature")
    ax.set_title("Top feature deviations")
    ax.axvline(0, color="#999999", linewidth=1)
    ax.invert_yaxis()
    return _finalize_fig(fig, prefix="feature_diffs", output_dir=output_dir)


def plot_cluster_counts(
    cluster_summary: pd.DataFrame, *, output_dir: str | Path | None = None
) -> dict[str, Any] | None:
    if cluster_summary is None or cluster_summary.empty:
        return None
    if plt is None:
        return None
    fig, ax = plt.subplots(figsize=(6, 4))
    ax.bar(
        cluster_summary["cluster_id"].astype(str),
        cluster_summary["count"],
        color="#FF9800",
    )
    ax.set_xlabel("Cluster")
    ax.set_ylabel("Count")
    ax.set_title("Cluster distribution")
    return _finalize_fig(fig, prefix="cluster_counts", output_dir=output_dir)


def plot_cluster_scatter(
    clustered_top: pd.DataFrame,
    feature_cols: Sequence[str],
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Any] | None:
    if clustered_top is None or clustered_top.empty or not feature_cols:
        return None
    if "cluster_id" not in clustered_top.columns:
        return None
    if plt is None:
        return None
    numeric = clustered_top[feature_cols].apply(pd.to_numeric, errors="coerce")
    numeric = numeric.fillna(numeric.median())
    scaler = StandardScaler()
    scaled = scaler.fit_transform(numeric)
    if scaled.shape[0] < 2:
        return None
    pca = PCA(n_components=2)
    coords = pca.fit_transform(scaled)
    fig, ax = plt.subplots(figsize=(6, 5))
    scatter = ax.scatter(
        coords[:, 0],
        coords[:, 1],
        c=clustered_top["cluster_id"],
        cmap="tab10",
        alpha=0.7,
    )
    ax.set_xlabel("PCA1")
    ax.set_ylabel("PCA2")
    ax.set_title("Top-N clusters (PCA projection)")
    legend1 = ax.legend(*scatter.legend_elements(), title="Cluster")
    ax.add_artist(legend1)
    return _finalize_fig(fig, prefix="cluster_scatter", output_dir=output_dir)
