from __future__ import annotations

import base64
import threading
from typing import Callable, List, Optional

import flet as ft

from .controller import ReverseController
from .utils import parse_multiline_text
from . import schema


class ReverseView:
    """
    Flet-based dashboard for reverse-engineering analysis.
    """

    def __init__(self, page: ft.Page, appbar_factory: Callable[[], ft.AppBar]):
        self.page = page
        self._appbar_factory = appbar_factory
        self.controller = ReverseController()
        self.current_results: Optional[dict] = None
        self.last_params: dict | None = None

        # UI controls placeholders
        self.horizon_dropdown: ft.Dropdown | None = None
        self.topn_field: ft.TextField | None = None
        self.market_dropdown: ft.Dropdown | None = None
        self.bullish_checkbox: ft.Checkbox | None = None
        self.exclude_blackout_checkbox: ft.Checkbox | None = None
        self.exclude_crisis_checkbox: ft.Checkbox | None = None
        self.max_rows_field: ft.TextField | None = None
        self.feature_set_dropdown: ft.Dropdown | None = None
        self.custom_features_field: ft.TextField | None = None
        self.run_button: ft.ElevatedButton | None = None
        self.export_button: ft.OutlinedButton | None = None
        self.progress_bar: ft.ProgressBar | None = None
        self.status_text: ft.Text | None = None
        self.log_field: ft.TextField | None = None
        self.top_summary_table: ft.DataTable | None = None
        self.cluster_summary_table: ft.DataTable | None = None
        self.plot_container: ft.ResponsiveRow | None = None

    def create_view(self) -> ft.View:
        """Build and return the Reverse dashboard view."""
        self._build_controls()

        page_content = ft.Container(
            padding=20,
            content=ft.Column(
                [
                    ft.Text(
                        "🔍 Reverse-engineering Dashboard",
                        size=28,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.BLUE_600,
                    ),
                    ft.Text(
                        "Analysoi Top-N voittajia ja vertaile heitä koko universumiin. "
                        "Tunnista feature-signatuurit, klusterit sekä generoi valmiit raportit.",
                        size=16,
                        color=ft.Colors.GREY_700,
                    ),
                    ft.ResponsiveRow(
                        [
                            ft.Container(self._build_parameter_card(), col={"xs": 12, "md": 6}),
                            ft.Container(self._build_status_card(), col={"xs": 12, "md": 6}),
                        ],
                        run_spacing=20,
                    ),
                    self._build_tables_section(),
                    self._build_plots_section(),
                ],
                spacing=18,
                expand=True,
            ),
        )

        return ft.View(
            "/reverse",
            controls=[
                self._appbar_factory(),
                page_content,
            ],
            scroll=ft.ScrollMode.AUTO,
        )

    # ------------------------------------------------------------------ #
    # UI Builders

    def _build_controls(self) -> None:
        market_options = self._build_market_options()
        self.horizon_dropdown = ft.Dropdown(
            label="Horizon (päivää)",
            options=[ft.dropdown.Option(str(v)) for v in (2, 5, 10, 20)],
            value="10",
            width=140,
        )
        self.topn_field = ft.TextField(
            label="Top-N",
            value="500",
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        self.max_rows_field = ft.TextField(
            label="Rivimäärän yläraja (universe)",
            value="0",
            width=180,
            keyboard_type=ft.KeyboardType.NUMBER,
            helper_text="0 = ei rajaa",
        )
        self.market_dropdown = ft.Dropdown(
            label="Market",
            options=market_options,
            value="__all__",
            width=180,
        )
        self.bullish_checkbox = ft.Checkbox(label="Vain bullish-signaalit", value=True)
        self.exclude_blackout_checkbox = ft.Checkbox(
            label="Exclude blackout", value=False
        )
        self.exclude_crisis_checkbox = ft.Checkbox(
            label="Exclude crisis window", value=False
        )
        self.feature_set_dropdown = ft.Dropdown(
            label="Feature set",
            options=[
                ft.dropdown.Option("master", "Master"),
                ft.dropdown.Option("top20", "Top 20"),
                ft.dropdown.Option("custom", "Custom"),
            ],
            value=schema.DEFAULT_FEATURE_SET,
            on_change=self._on_feature_set_change,
        )
        self.custom_features_field = ft.TextField(
            label="Custom features (comma tai rivinvaihto)",
            multiline=True,
            min_lines=3,
            max_lines=6,
            visible=False,
        )
        self.run_button = ft.ElevatedButton(
            text="Aja reverse-analyysi",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self._on_run_clicked,
        )
        self.export_button = ft.OutlinedButton(
            text="Vie raportti",
            icon=ft.Icons.DOWNLOAD,
            disabled=True,
            on_click=self._on_export_clicked,
        )
        self.progress_bar = ft.ProgressBar(width=400, value=0)
        self.status_text = ft.Text("Valmiina ajamaan analyysiä.", color=ft.Colors.GREY_600)
        self.log_field = ft.TextField(
            value="",
            multiline=True,
            read_only=True,
            min_lines=8,
            max_lines=12,
            expand=True,
            border_radius=8,
            border_color=ft.Colors.GREY_300,
            text_style=ft.TextStyle(font_family="monospace", size=13),
        )
        self.top_summary_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Feature", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Top-N mean")),
                ft.DataColumn(ft.Text("Universe mean")),
                ft.DataColumn(ft.Text("Diff")),
                ft.DataColumn(ft.Text("Pct change")),
            ],
            rows=[],
            column_spacing=20,
            heading_row_color=ft.Colors.GREY_100,
        )
        self.cluster_summary_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Cluster", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Count")),
                ft.DataColumn(ft.Text("Avg return")),
                ft.DataColumn(ft.Text("Top features")),
            ],
            rows=[],
            column_spacing=18,
            heading_row_color=ft.Colors.GREY_100,
        )
        self.plot_container = ft.ResponsiveRow([], spacing=10, run_spacing=10)

    def _build_market_options(self) -> List[ft.dropdown.Option]:
        options = [ft.dropdown.Option("__all__", "Kaikki")]
        try:
            markets = self.controller.list_markets()
            for market in markets:
                if market == "__all__":
                    continue
                options.append(
                    ft.dropdown.Option(market, market.upper())
                )
        except Exception:
            pass
        return options

    def _build_parameter_card(self) -> ft.Card:
        controls = [
            ft.Row(
                [
                    self.horizon_dropdown,
                    self.topn_field,
                    self.max_rows_field,
                    self.market_dropdown,
                ],
                spacing=12,
                wrap=True,
            ),
            ft.Row(
                [
                    self.bullish_checkbox,
                    self.exclude_blackout_checkbox,
                    self.exclude_crisis_checkbox,
                ],
                spacing=12,
                wrap=True,
            ),
            ft.Column(
                [
                    self.feature_set_dropdown,
                    self.custom_features_field,
                ]
            ),
            ft.Row(
                [
                    self.run_button,
                    self.export_button,
                ],
                spacing=20,
            ),
        ]
        return ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text(
                            "Parametripaneeli",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                        ),
                        *controls,
                    ],
                    spacing=12,
                ),
            )
        )

    def _build_status_card(self) -> ft.Card:
        return ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text("Status & logit", size=18, weight=ft.FontWeight.BOLD),
                        self.status_text,
                        self.progress_bar,
                        self.log_field,
                    ],
                    spacing=12,
                ),
            )
        )

    def _build_tables_section(self) -> ft.Card:
        return ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text("Top-N summary", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            height=260,
                            content=ft.Column([self.top_summary_table], scroll=ft.ScrollMode.AUTO),
                        ),
                        ft.Divider(),
                        ft.Text("Cluster summary", size=18, weight=ft.FontWeight.BOLD),
                        ft.Container(
                            height=200,
                            content=ft.Column([self.cluster_summary_table], scroll=ft.ScrollMode.AUTO),
                        ),
                    ],
                    spacing=16,
                ),
            )
        )

    def _build_plots_section(self) -> ft.Card:
        return ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text("Visualisoinnit", size=18, weight=ft.FontWeight.BOLD),
                        self.plot_container,
                    ],
                    spacing=12,
                ),
            )
        )

    # ------------------------------------------------------------------ #
    # Event handlers and helpers

    def _on_feature_set_change(self, _):
        if not self.custom_features_field or not self.feature_set_dropdown:
            return
        is_custom = self.feature_set_dropdown.value == "custom"
        self.custom_features_field.visible = is_custom
        self._safe_page_update()

    def _on_run_clicked(self, _):
        if self.run_button:
            self.run_button.disabled = True
        if self.export_button:
            self.export_button.disabled = True
        self.current_results = None
        params = self._collect_params()
        self.last_params = params
        self._set_status("Ajetaan analyysiä...", ft.Colors.BLUE_600)
        self._append_log("Käynnistetään reverse-analyysi.")
        threading.Thread(
            target=self._run_analysis_background, args=(params,), daemon=True
        ).start()

    def _run_analysis_background(self, params: dict):
        try:
            results = self.controller.run_reverse_analysis(
                params,
                log_cb=lambda msg: self._append_log(msg),
                progress_cb=self._update_progress,
            )
            self.current_results = results
            self._update_results(results)
            self._set_status("Analyysi valmis.", ft.Colors.GREEN_600)
            if self.export_button:
                self.export_button.disabled = False
        except Exception as exc:
            self._append_log(f"Virhe: {exc}")
            self._set_status("Analyysi epäonnistui.", ft.Colors.RED_600)
        finally:
            if self.run_button:
                self.run_button.disabled = False
            self._safe_page_update()

    def _on_export_clicked(self, _):
        if not self.current_results:
            self._append_log("Aja analyysi ennen vientiä.")
            return
        params = self.last_params or self._collect_params()

        def worker():
            try:
                paths = self.controller.export_report(self.current_results, params)
                self._append_log(
                    f"Raportti viety: {paths['report']} | Compare: {paths['compare']}"
                )
                self._set_status("Raportti tallennettu.", ft.Colors.GREEN_600)
            except Exception as exc:
                self._append_log(f"Raportin vienti epäonnistui: {exc}")
                self._set_status("Raportin vienti epäonnistui.", ft.Colors.RED_600)
            finally:
                self._safe_page_update()

        threading.Thread(target=worker, daemon=True).start()

    def _collect_params(self) -> dict:
        horizon = int(self.horizon_dropdown.value or 10) if self.horizon_dropdown else 10
        top_n = self._safe_int(self.topn_field.value if self.topn_field else "500", 500)
        market = self.market_dropdown.value if self.market_dropdown else "__all__"
        params = {
            "horizon": horizon,
            "top_n": top_n,
            "market": market or "__all__",
            "max_rows": self._safe_int(
                self.max_rows_field.value if self.max_rows_field else "0", 0
            ),
            "bullish_only": self.bullish_checkbox.value if self.bullish_checkbox else True,
            "exclude_blackout": self.exclude_blackout_checkbox.value
            if self.exclude_blackout_checkbox
            else False,
            "exclude_crisis": self.exclude_crisis_checkbox.value
            if self.exclude_crisis_checkbox
            else False,
            "feature_set": self.feature_set_dropdown.value
            if self.feature_set_dropdown
            else schema.DEFAULT_FEATURE_SET,
            "custom_features": parse_multiline_text(
                self.custom_features_field.value if self.custom_features_field else ""
            ),
            "clusters": 5,
        }
        return params

    def _safe_int(self, value: str, default: int) -> int:
        try:
            result = int(value.replace(" ", ""))
            return result if result > 0 else default
        except Exception:
            return default

    def _update_results(self, results: dict) -> None:
        self._update_top_summary(results.get("compare"))
        self._update_cluster_summary(
            results.get("cluster_summary"), horizon=results.get("params", {}).get("horizon", 10)
        )
        self._update_plots(results.get("plots", []))
        self._safe_page_update()

    def _update_top_summary(self, compare_df):
        if not self.top_summary_table:
            return
        rows = []
        if isinstance(compare_df, list):
            compare_df = None
        if compare_df is not None and not getattr(compare_df, "empty", True):
            subset = compare_df.head(20)
            for _, row in subset.iterrows():
                rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(row["feature"]))),
                            ft.DataCell(ft.Text(f"{row['top_mean']:.4f}")),
                            ft.DataCell(ft.Text(f"{row['universe_mean']:.4f}")),
                            ft.DataCell(ft.Text(f"{row['diff']:.4f}")),
                            ft.DataCell(ft.Text(f"{row['pct_change']:.2f}")),
                        ]
                    )
                )
        self.top_summary_table.rows = rows

    def _update_cluster_summary(self, cluster_df, *, horizon: int):
        if not self.cluster_summary_table:
            return
        rows = []
        horizon_col = f"avg_t{horizon}"
        if cluster_df is not None and not getattr(cluster_df, "empty", True):
            for _, row in cluster_df.iterrows():
                avg_val = ""
                for col in row.index:
                    if col.startswith("avg_t"):
                        avg_val = f"{row[col]:.4f}"
                        break
                rows.append(
                    ft.DataRow(
                        cells=[
                            ft.DataCell(ft.Text(str(row["cluster_id"]))),
                            ft.DataCell(ft.Text(str(row["count"]))),
                            ft.DataCell(ft.Text(avg_val)),
                            ft.DataCell(ft.Text(str(row["top_features"]))),
                        ]
                    )
                )
        self.cluster_summary_table.rows = rows

    def _update_plots(self, plots: list[dict]):
        if not self.plot_container:
            return
        controls: list[ft.Control] = []
        for artifact in plots:
            data = artifact.get("data")
            if not data:
                continue
            label = artifact.get("type", "plot")
            b64 = base64.b64encode(data).decode("ascii")
            controls.append(
                ft.Container(
                    col={"xs": 12, "md": 4},
                    content=ft.Column(
                        [
                            ft.Text(label.replace("_", " ").title()),
                            ft.Image(src_base64=b64, fit=ft.ImageFit.CONTAIN, height=240),
                        ],
                        spacing=6,
                    ),
                )
            )
        if not controls:
            controls = [ft.Text("Kuvaajia ei saatavilla.")]
        self.plot_container.controls = controls

    def _update_progress(self, value: float):
        if not self.progress_bar:
            return

        def _update():
            self.progress_bar.value = value
            self.progress_bar.update()

        self._run_on_ui_thread(_update)

    def _append_log(self, message: str):
        if not self.log_field:
            return

        def _update():
            existing = self.log_field.value.strip()
            new_value = f"{existing}\n{message}" if existing else message
            self.log_field.value = new_value[-5000:]
            self.log_field.update()

        self._run_on_ui_thread(_update)

    def _set_status(self, message: str, color):
        if not self.status_text:
            return

        def _update():
            self.status_text.value = message
            self.status_text.color = color
            self.status_text.update()

        self._run_on_ui_thread(_update)

    def _safe_page_update(self):
        try:
            self.page.update()
        except Exception:
            pass

    def _run_on_ui_thread(self, fn: Callable[[], None]):
        try:
            if hasattr(self.page, "call_from_thread") and callable(
                getattr(self.page, "call_from_thread")
            ):
                self.page.call_from_thread(fn)
            else:
                fn()
        except Exception:
            pass
