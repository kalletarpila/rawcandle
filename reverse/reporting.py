from __future__ import annotations

import json
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


def export_json(obj: Any, path: Path) -> None:
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def _format_params(params: dict[str, Any]) -> str:
    lines = ["| Parametri | Arvo |", "| --- | --- |"]
    for key, value in params.items():
        lines.append(f"| {key} | {value} |")
    return "\n".join(lines)


def _format_top_features(compare_df: pd.DataFrame, limit: int = 10) -> str:
    if compare_df is None or compare_df.empty:
        return "_Ei dataa_\n"
    subset = compare_df.copy()
    if "pct_change" in subset.columns:
        subset["abs_pct"] = subset["pct_change"].abs()
        subset = subset.sort_values(by="abs_pct", ascending=False).head(limit)
    else:
        subset["abs_effect"] = subset.get("abs_effect", subset.get("diff", 0)).abs()
        subset = subset.sort_values(by="abs_effect", ascending=False).head(limit)
    lines = ["| Feature | diff | pct_change |", "| --- | --- | --- |"]
    for _, row in subset.iterrows():
        lines.append(
            f"| {row.get('feature','')} | {row.get('diff', 0):.4f} | {row.get('pct_change', 0):.2f} |"
        )
    return "\n".join(lines)


def _format_cluster_summary(cluster_summary: pd.DataFrame) -> str:
    if cluster_summary is None or cluster_summary.empty:
        return "_Ei klustereita_\n"
    lines = ["| cluster_id | count | avgres | top_features |", "| --- | --- | --- | --- |"]
    for _, row in cluster_summary.iterrows():
        avg_cols = [col for col in row.index if col.startswith("avg_t")]
        avg_val = row[avg_cols[0]] if avg_cols else ""
        top_feats = row["top_features"] if "top_features" in row else ""
        lines.append(
            f"| {row.get('cluster_id','')} | {row.get('count','')} | {avg_val} | {top_feats} |"
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

    compare_path = run_dir / "compare.txt"
    cluster_path = run_dir / "cluster_summary.txt"
    profiles_path = run_dir / "cluster_profiles.txt"
    similarity_path = run_dir / "similarity_top.txt"
    report_md_path = run_dir / "report.md"
    debug_dir = run_dir / "debug"
    debug_dir.mkdir(exist_ok=True)

    export_csv(results.get("compare"), compare_path)
    export_csv(results.get("cluster_summary"), cluster_path)
    export_csv(results.get("cluster_profiles"), profiles_path)
    similarity_df = results.get("similarity_top")
    if similarity_df is not None:
        export_csv(similarity_df, similarity_path)
    # debug artifacts
    try:
        export_json(params, debug_dir / "params.json")
    except Exception:
        pass
    try:
        export_json(
            {
                "feature_set": params.get("feature_set"),
                "used_features": results.get("used_features", []),
                "cluster_features_used": results.get("cluster_features_used", []),
                "profile_features_used": results.get("profile_features_used", []),
            },
            debug_dir / "used_features.json",
        )
    except Exception:
        pass
    try:
        uniq_td = None
        try:
            uniq_td = int(results.get("universe", pd.DataFrame())[["ticker", "date"]].drop_duplicates().shape[0])
        except Exception:
            uniq_td = None
        export_json(
            {
                "top_rows": len(results.get("top", [])),
                "universe_rows": len(results.get("universe", [])),
                "unique_ticker_date_universe": uniq_td,
                "horizon": params.get("horizon"),
                "top_n": params.get("top_n"),
                "dedupe_topN_by_ticker_date": bool(params.get("dedupe_topN_by_ticker_date", False)),
                "market": params.get("market"),
                "sector": params.get("sector"),
                "filters": {
                    "bullish_only": bool(params.get("bullish_only", False)),
                    "exclude_blackout": bool(params.get("exclude_blackout", False)),
                    "exclude_crisis": bool(params.get("exclude_crisis", False)),
                    "only_candle_days": bool(params.get("only_candle_days", False)),
                    "exclude_from_regression_only": bool(params.get("exclude_from_regression_only", False)),
                    "rsi_min": params.get("rsi_min"),
                    "rsi_max": params.get("rsi_max"),
                    "vola_min": params.get("vola_min"),
                    "vola_max": params.get("vola_max"),
                },
            },
            debug_dir / "run_summary.json",
        )
    except Exception:
        pass
    try:
        top_df = results.get("top", pd.DataFrame())
        horizon = params.get("horizon", 10)
        cols = ["ticker", "date", "candle_pattern", f"t{horizon}", "reverse_similarity", "cluster_id"]
        cols = [c for c in cols if c in top_df.columns]
        export_csv(top_df.head(200)[cols], debug_dir / "top_sample.csv")
    except Exception:
        pass
    try:
        comp_df = results.get("compare", pd.DataFrame())
        export_csv(comp_df.head(100), debug_dir / "compare_top100.csv")
    except Exception:
        pass
    try:
        export_csv(results.get("cluster_summary"), debug_dir / "cluster_summary.csv")
    except Exception:
        pass
    try:
        profiles = results.get("cluster_profiles")
        if profiles is not None and not getattr(profiles, "empty", True):
            prof = profiles.copy()
            prof["abs_delta"] = prof["delta_vs_top_mean"].abs()
            top_list = []
            for cid, grp in prof.groupby("cluster_id"):
                top_feats = grp.sort_values("abs_delta", ascending=False).head(10)
                top_list.append(top_feats)
            if top_list:
                export_csv(pd.concat(top_list, ignore_index=True), debug_dir / "cluster_profiles_top10.csv")
    except Exception:
        pass

    if results.get("stability"):
        stab = results["stability"]
        try:
            export_csv(stab.get("stability_matrix"), debug_dir / "stability_matrix.csv")
        except Exception:
            pass
        try:
            export_csv(stab.get("feature_stability"), debug_dir / "feature_stability.csv")
        except Exception:
            pass
        try:
            export_json(
                {
                    "stability_mode": stab.get("stability_mode"),
                    "stability_top_k": stab.get("stability_top_k"),
                    "split_keys": stab.get("split_keys"),
                },
                debug_dir / "stability_meta.json",
            )
        except Exception:
            pass

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
        "",
        "## Cluster profiles (top 10 delta features per cluster)",
        "",
        "## Top 20 universen riviä, jotka muistuttavat eniten TopN-profiilia",
    ]
    if similarity_df is not None and not getattr(similarity_df, "empty", True):
        top20 = similarity_df.head(20)
        lines.append("| ticker | date | candle_pattern | reverse_similarity |")
        lines.append("| --- | --- | --- | --- |")
        for _, row in top20.iterrows():
            lines.append(
                f"| {row.get('ticker','')} | {row.get('date','')} | {row.get('candle_pattern','')} | {row.get('reverse_similarity', 0):.4f} |"
            )
    else:
        lines.append("_Ei TopN-like rivejä_")
    profiles = results.get("cluster_profiles")
    if profiles is not None and not getattr(profiles, "empty", True):
        try:
            prof = profiles.copy()
            prof["abs_delta"] = prof["delta_vs_top_mean"].abs()
            for cid, grp in prof.groupby("cluster_id"):
                lines.append(f"### Cluster {cid}")
                top_feats = grp.sort_values("abs_delta", ascending=False).head(10)
                lines.append("| feature | median | q25 | q75 | delta_vs_top_mean |")
                lines.append("| --- | --- | --- | --- | --- |")
                for _, row in top_feats.iterrows():
                    lines.append(
                        f"| {row['feature']} | {row['median']:.4f} | {row['q25']:.4f} | {row['q75']:.4f} | {row['delta_vs_top_mean']:.4f} |"
                    )
                lines.append("")
        except Exception:
            lines.append("_Cluster profiles unavailable_")
    else:
        lines.append("_Cluster profiles unavailable_")
    report_md_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "run_dir": run_dir,
        "compare": compare_path,
        "cluster_summary": cluster_path,
        "cluster_profiles": profiles_path,
        "similarity_top": similarity_path,
        "report": report_md_path,
        "debug_dir": debug_dir,
        "debug_params": debug_dir / "params.json",
        "debug_used_features": debug_dir / "used_features.json",
        "debug_run_summary": debug_dir / "run_summary.json",
    }
