from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .utils import ensure_data_dir, timestamp


def build_run_id(params: dict[str, Any], ts: str | None = None) -> str:
    ts = ts or timestamp()
    horizon = int(params.get("horizon", 10))
    top_n = int(params.get("top_n", 500))
    market = (params.get("market") or "__all__").strip().lower()
    dedupe = int(bool(params.get("dedupe_topN_by_ticker_date", False)))
    return f"reverse_{ts}_h{horizon}_top{top_n}_m{market}_dedupe{dedupe}"


def export_csv(df: pd.DataFrame | None, path: Path) -> None:
    if df is None:
        df = pd.DataFrame()
    df.to_csv(path, index=False)


def _format_params(params: dict[str, Any]) -> str:
    lines = ["| Parametri | Arvo |", "| --- | --- |"]
    for key, value in params.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


def _format_top_features(compare_df: pd.DataFrame, limit: int = 10) -> str:
    if compare_df is None or compare_df.empty:
        return "_Ei dataa_\n"
    subset = compare_df.copy()
    subset["abs_pct"] = subset["pct_change"].abs()
    subset = subset.sort_values(by="abs_pct", ascending=False).head(limit)
    lines = ["| Feature | diff | pct_change |", "| --- | --- | --- |"]
    for _, row in subset.iterrows():
        lines.append(
            f"| {row['feature']} | {row['diff']:.4f} | {row['pct_change']:.2f} |"
        )
    return "\n".join(lines)


def _format_cluster_summary(cluster_summary: pd.DataFrame) -> str:
    if cluster_summary is None or cluster_summary.empty:
        return "_Ei klustereita_\n"
    lines = ["| cluster_id | count | avgres | top_features |", "| --- | --- | --- | --- |"]
    for _, row in cluster_summary.iterrows():
        avg_cols = [col for col in row.index if col.startswith("avg_t")]
        avg_val = row[avg_cols[0]] if avg_cols else ""
        lines.append(
            f"| {row['cluster_id']} | {row['count']} | {avg_val} | {row['top_features']} |"
        )
    return "\n".join(lines)


def export_report(
    results: dict[str, Any],
    params: dict[str, Any],
    *,
    output_dir: str | Path | None = None,
) -> dict[str, Path]:
    """
    Write CSV + Markdown report files and return their paths.
    """
    out_dir = ensure_data_dir(output_dir)
    run_id = build_run_id(params)
    run_dir = out_dir / run_id
    figures_dir = run_dir / "figures"
    run_dir.mkdir(parents=True, exist_ok=True)
    figures_dir.mkdir(parents=True, exist_ok=True)

    compare_path = run_dir / "compare.csv"
    cluster_path = run_dir / "cluster_summary.csv"
    report_md_path = run_dir / "report.md"

    export_csv(results.get("compare"), compare_path)
    export_csv(results.get("cluster_summary"), cluster_path)

    lines: list[str] = [
        "# Reverse-analyysin raportti",
        "",
        "## Parametrit",
        _format_params(params),
        "",
        "## Rivimäärät",
        f"- Top-N: {len(results.get('top', []))}",
        f"- Universe: {len(results.get('universe', []))}",
        "",
        "## Top 10 erottuvinta featurea",
        _format_top_features(results.get("compare")),
        "",
        "## Klusterikooste",
        _format_cluster_summary(results.get("cluster_summary")),
    ]
    report_md_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "run_dir": run_dir,
        "compare": compare_path,
        "cluster_summary": cluster_path,
        "report": report_md_path,
    }
