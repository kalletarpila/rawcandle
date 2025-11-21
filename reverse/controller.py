from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from . import analysis, plots, reporting, schema
from .queries import list_available_markets
from .utils import ensure_data_dir, notify, notify_progress


logger = logging.getLogger(__name__)


class ReverseController:
    """
    Controller responsible for running reverse analysis and exporting reports.
    """

    def __init__(
        self,
        analysis_db_path: str | Path = "data/analysis.db",
        *,
        output_dir: str | Path | None = None,
    ) -> None:
        self.analysis_db_path = Path(analysis_db_path)
        self.output_dir = ensure_data_dir(output_dir)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.analysis_db_path)
        return conn

    def list_markets(self) -> list[str]:
        try:
            with self._connect() as conn:
                markets = list_available_markets(conn)
        except Exception:
            markets = []
        ordered = ["__all__"]
        ordered.extend([m for m in markets if m not in ordered])
        return ordered

    def run_reverse_analysis(
        self,
        params: dict[str, Any],
        log_cb=None,
        progress_cb=None,
    ) -> dict[str, Any]:
        notify(log_cb, "Käynnistetään reverse-analyysi...")
        feature_cols = schema.get_features_for_mode(
            params.get("feature_set"), params.get("custom_features")
        )
        if not feature_cols:
            raise ValueError("Feature-lista on tyhjä. Valitse vähintään yksi feature.")

        with self._connect() as conn:
            results = analysis.run_reverse_pipeline(
                conn,
                params,
                feature_cols=feature_cols,
                progress_cb=lambda value: notify_progress(progress_cb, value),
            )
        notify(log_cb, "Analyysi valmis, muodostetaan kuvaajat...")
        self._attach_plots(results)
        notify_progress(progress_cb, 1.0)
        notify(log_cb, "Valmis.")
        return results

    def _attach_plots(self, results: dict[str, Any]) -> None:
        plot_items: list[dict[str, Any]] = []
        compare = results.get("compare")
        cluster_summary = results.get("cluster_summary")
        clustered_top = results.get("clustered_top")
        features = results.get("used_features") or []

        artifact = plots.plot_feature_diffs(compare, output_dir=self.output_dir)
        if artifact:
            plot_items.append({"type": "feature_diffs", **artifact})

        artifact = plots.plot_cluster_counts(cluster_summary, output_dir=self.output_dir)
        if artifact:
            plot_items.append({"type": "cluster_counts", **artifact})

        artifact = plots.plot_cluster_scatter(
            clustered_top, features, output_dir=self.output_dir
        )
        if artifact:
            plot_items.append({"type": "cluster_scatter", **artifact})

        results["plots"] = plot_items

    def export_report(self, results: dict[str, Any], params: dict[str, Any]) -> dict[str, Path]:
        if not results:
            raise ValueError("Aja analyysi ennen raportin vientiä.")
        paths = reporting.export_report(results, params, output_dir=self.output_dir)
        return paths
