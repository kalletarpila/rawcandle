from __future__ import annotations

from datetime import date
import math
from typing import Any

import flet as ft

from analysis.divergence_research_query import (
    fetch_divergence_events,
    fetch_divergence_heatmap,
    summarize_divergence_events,
)


class DivergencePage:
    def __init__(
        self,
        page: ft.Page,
        create_appbar,
        analysis_db_path: str = "data/analysis.db",
        stock_db_path: str = "data/osakedata.db",
    ) -> None:
        self.page = page
        self.create_appbar = create_appbar
        self.analysis_db_path = analysis_db_path
        self.stock_db_path = stock_db_path

        self.sort_by = "date"
        self.sort_desc = True
        self.page_size = 100
        self.page_index = 0

        self.event_class_dropdown: ft.Dropdown | None = None
        self.radius_dropdown: ft.Dropdown | None = None
        self.min_gap_slider: ft.Slider | None = None
        self.max_gap_slider: ft.Slider | None = None
        self.min_drop_slider: ft.Slider | None = None
        self.max_drop_slider: ft.Slider | None = None
        self.start_date_field: ft.TextField | None = None
        self.end_date_field: ft.TextField | None = None
        self.summary_text: ft.Text | None = None
        self.filter_error_text: ft.Text | None = None
        self.table: ft.DataTable | None = None
        self.pagination_text: ft.Text | None = None
        self.heatmap_container: ft.Column | None = None

    def create_view(self) -> ft.View:
        self.event_class_dropdown = ft.Dropdown(
            label="Event class",
            width=180,
            value="All",
            options=[
                ft.dropdown.Option("All"),
                ft.dropdown.Option("R2_ONLY"),
                ft.dropdown.Option("R3_ONLY"),
                ft.dropdown.Option("R2_AND_R3"),
            ],
            on_change=self._on_filter_change,
        )
        self.radius_dropdown = ft.Dropdown(
            label="Radius",
            width=140,
            value="R3",
            options=[ft.dropdown.Option("R2"), ft.dropdown.Option("R3")],
            on_change=self._on_filter_change,
        )
        self.min_gap_slider = ft.Slider(min=5, max=24, divisions=19, value=5, label="{value}", on_change_end=self._on_filter_change)
        self.max_gap_slider = ft.Slider(min=5, max=24, divisions=19, value=24, label="{value}", on_change_end=self._on_filter_change)
        self.min_drop_slider = ft.Slider(min=0, max=50, divisions=50, value=0, label="{value}", on_change_end=self._on_filter_change)
        self.max_drop_slider = ft.Slider(min=0, max=50, divisions=50, value=50, label="{value}", on_change_end=self._on_filter_change)
        self.start_date_field = ft.TextField(
            label="Start date",
            width=160,
            hint_text="YYYY-MM-DD",
            on_submit=self._on_filter_change,
            on_blur=self._on_filter_change,
        )
        self.end_date_field = ft.TextField(
            label="End date",
            width=160,
            hint_text="YYYY-MM-DD",
            on_submit=self._on_filter_change,
            on_blur=self._on_filter_change,
        )

        self.summary_text = ft.Text(size=14)
        self.filter_error_text = ft.Text(size=12, color=ft.Colors.RED_700)
        self.pagination_text = ft.Text("Page 1", size=12)
        self.table = self._build_table()
        self.heatmap_container = ft.Column(spacing=4)

        refresh_button = ft.ElevatedButton(
            "Refresh",
            icon=ft.Icons.REFRESH,
            on_click=self._refresh,
        )
        prev_button = ft.OutlinedButton("Prev", on_click=self._prev_page)
        next_button = ft.OutlinedButton("Next", on_click=self._next_page)

        self._refresh()

        return ft.View(
            "/divergence",
            [
                self.create_appbar(),
                ft.Container(
                    padding=20,
                    content=ft.Column(
                        [
                            ft.Text(
                                "Divergence Research",
                                size=30,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ORANGE_700,
                            ),
                            ft.Card(
                                content=ft.Container(
                                    padding=16,
                                    content=ft.Column(
                                        [
                                            ft.Text("Filters", weight=ft.FontWeight.BOLD, size=18),
                                            ft.Row(
                                                [
                                                    self.event_class_dropdown,
                                                    self.radius_dropdown,
                                                    self.start_date_field,
                                                    self.end_date_field,
                                                    refresh_button,
                                                ],
                                                wrap=True,
                                                spacing=16,
                                            ),
                                            self.filter_error_text,
                                            ft.Text("Pivot gap"),
                                            ft.Row(
                                                [
                                                    ft.Column([ft.Text("Min gap"), self.min_gap_slider], expand=True),
                                                    ft.Column([ft.Text("Max gap"), self.max_gap_slider], expand=True),
                                                ],
                                                spacing=16,
                                            ),
                                            ft.Text("Pivot drop"),
                                            ft.Row(
                                                [
                                                    ft.Column([ft.Text("Min drop"), self.min_drop_slider], expand=True),
                                                    ft.Column([ft.Text("Max drop"), self.max_drop_slider], expand=True),
                                                ],
                                                spacing=16,
                                            ),
                                        ],
                                        spacing=12,
                                    ),
                                )
                            ),
                            ft.Card(content=ft.Container(padding=16, content=self.summary_text)),
                            ft.Card(
                                content=ft.Container(
                                    padding=16,
                                    content=ft.Column(
                                        [
                                            ft.Text("Heatmap", weight=ft.FontWeight.BOLD, size=18),
                                            self.heatmap_container,
                                        ],
                                        spacing=8,
                                    ),
                                )
                            ),
                            ft.Row(
                                [prev_button, self.pagination_text, next_button],
                                alignment=ft.MainAxisAlignment.END,
                                spacing=12,
                            ),
                            ft.Container(content=self.table, expand=True),
                        ],
                        spacing=16,
                    ),
                ),
            ],
        )

    def _build_table(self) -> ft.DataTable:
        return ft.DataTable(
            columns=[
                self._sortable_column("ticker", "Ticker"),
                self._sortable_column("date", "Date"),
                self._sortable_column("event_class", "Event class"),
                self._sortable_column("pivot_gap_r2", "Gap R2"),
                self._sortable_column("pivot_drop_pct_r2", "Drop R2"),
                self._sortable_column("pivot_gap_r3", "Gap R3"),
                self._sortable_column("pivot_drop_pct_r3", "Drop R3"),
                self._sortable_column("rsi", "RSI"),
                self._sortable_column("ret_5d", "Ret 5d"),
                self._sortable_column("ret_10d", "Ret 10d"),
                self._sortable_column("ret_20d", "Ret 20d"),
                self._sortable_column("ret_30d", "Ret 30d"),
            ],
            rows=[],
            border=ft.border.all(1, ft.Colors.GREY_400),
            border_radius=8,
            vertical_lines=ft.border.BorderSide(1, ft.Colors.GREY_300),
            horizontal_lines=ft.border.BorderSide(1, ft.Colors.GREY_300),
        )

    def _sortable_column(self, key: str, label: str) -> ft.DataColumn:
        return ft.DataColumn(
            ft.Text(label, weight=ft.FontWeight.BOLD),
            on_sort=lambda e, sort_key=key: self._sort(sort_key),
        )

    def _get_filters(self) -> dict[str, Any]:
        min_gap = int(self.min_gap_slider.value)
        max_gap = int(self.max_gap_slider.value)
        min_drop = float(self.min_drop_slider.value)
        max_drop = float(self.max_drop_slider.value)
        if min_gap > max_gap:
            min_gap, max_gap = max_gap, min_gap
        if min_drop > max_drop:
            min_drop, max_drop = max_drop, min_drop
        event_class = self.event_class_dropdown.value
        if event_class == "All":
            event_class = None
        start_date = (self.start_date_field.value or "").strip()
        end_date = (self.end_date_field.value or "").strip()
        validation_error = self.validate_date_range(start_date, end_date)
        if validation_error is not None:
            raise ValueError(validation_error)
        return {
            "event_class": event_class,
            "radius": self.radius_dropdown.value,
            "min_gap": min_gap,
            "max_gap": max_gap,
            "min_drop": min_drop,
            "max_drop": max_drop,
            "start_date": start_date or None,
            "end_date": end_date or None,
        }

    def _refresh(self, _e=None) -> None:
        try:
            filters = self._get_filters()
        except ValueError as exc:
            if self.filter_error_text is not None:
                self.filter_error_text.value = str(exc)
            if self.page is not None:
                self.page.update()
            return
        if self.filter_error_text is not None:
            self.filter_error_text.value = ""
        summary = summarize_divergence_events(
            self.analysis_db_path,
            stock_db_path=self.stock_db_path,
            **filters,
        )
        events = fetch_divergence_events(
            self.analysis_db_path,
            stock_db_path=self.stock_db_path,
            limit=self.page_size,
            offset=self.page_index * self.page_size,
            sort_by=self.sort_by,
            sort_desc=self.sort_desc,
            **filters,
        )
        heatmap = fetch_divergence_heatmap(
            self.analysis_db_path,
            stock_db_path=self.stock_db_path,
            **filters,
        )
        self._update_summary(summary)
        self._update_table(events)
        self._update_heatmap(heatmap)
        if self.pagination_text is not None:
            self.pagination_text.value = f"Page {self.page_index + 1}"
        self.page.update()

    def _update_summary(self, summary: dict[str, Any]) -> None:
        if self.summary_text is None:
            return
        self.summary_text.value = (
            f"n={summary['n']} | "
            f"winrate_30d={self._fmt_pct(summary['winrate_30d'], ratio=True)} | "
            f"mean_ret_30d={self._fmt_pct(summary['mean_ret_30d'])} | "
            f"median_ret_30d={self._fmt_pct(summary['median_ret_30d'])} | "
            f"winsor_30d={self._fmt_pct(summary['winsor_30d'])}"
        )

    def _update_table(self, rows: list[dict[str, Any]]) -> None:
        if self.table is None:
            return
        self.table.rows = [
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(str(row["ticker"]))),
                    ft.DataCell(ft.Text(str(row["date"]))),
                    ft.DataCell(ft.Text(str(row["event_class"]))),
                    ft.DataCell(ft.Text(self._fmt_int(row["pivot_gap_r2"]))),
                    ft.DataCell(ft.Text(self._fmt_pct(row["pivot_drop_pct_r2"]))),
                    ft.DataCell(ft.Text(self._fmt_int(row["pivot_gap_r3"]))),
                    ft.DataCell(ft.Text(self._fmt_pct(row["pivot_drop_pct_r3"]))),
                    ft.DataCell(ft.Text(self._fmt_num(row["rsi"]))),
                    ft.DataCell(ft.Text(self._fmt_pct(row["ret_5d"]))),
                    ft.DataCell(ft.Text(self._fmt_pct(row["ret_10d"]))),
                    ft.DataCell(ft.Text(self._fmt_pct(row["ret_20d"]))),
                    ft.DataCell(ft.Text(self._fmt_pct(row["ret_30d"]))),
                ]
            )
            for row in rows
        ]

    def _update_heatmap(self, heatmap_rows: list[dict[str, Any]]) -> None:
        if self.heatmap_container is None:
            return
        cells: list[ft.Control] = []
        if heatmap_rows:
            max_abs = max(abs(row["avg_ret_30d"]) for row in heatmap_rows) or 1.0
            for row in heatmap_rows[:80]:
                intensity = min(1.0, abs(row["avg_ret_30d"]) / max_abs)
                green = int(80 + 120 * intensity) if row["avg_ret_30d"] >= 0 else 80
                red = int(80 + 120 * intensity) if row["avg_ret_30d"] < 0 else 80
                color = f"#{red:02x}{green:02x}80"
                cells.append(
                    ft.Container(
                        width=90,
                        height=56,
                        bgcolor=color,
                        border_radius=6,
                        padding=6,
                        content=ft.Column(
                            [
                                ft.Text(f"G{row['gap']} D{row['drop']}", size=10),
                                ft.Text(self._fmt_pct(row["avg_ret_30d"]), size=11, weight=ft.FontWeight.BOLD),
                                ft.Text(f"n={row['n']}", size=10),
                            ],
                            spacing=1,
                        ),
                    )
                )
        self.heatmap_container.controls = [
            ft.Row(cells[idx : idx + 6], spacing=6)
            for idx in range(0, len(cells), 6)
        ] or [ft.Text("No heatmap cells for current filters.")]

    def _sort(self, sort_key: str) -> None:
        if self.sort_by == sort_key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_by = sort_key
            self.sort_desc = True
        self.page_index = 0
        self._refresh()

    def _prev_page(self, _e) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._refresh()

    def _next_page(self, _e) -> None:
        self.page_index += 1
        self._refresh()

    def _on_filter_change(self, _e) -> None:
        self.page_index = 0
        self._refresh()

    @staticmethod
    def validate_date_range(start_date: str, end_date: str) -> str | None:
        start_value = start_date.strip()
        end_value = end_date.strip()
        start_parsed = None
        end_parsed = None
        if start_value:
            try:
                start_parsed = date.fromisoformat(start_value)
            except ValueError:
                return "Start date must use YYYY-MM-DD format."
        if end_value:
            try:
                end_parsed = date.fromisoformat(end_value)
            except ValueError:
                return "End date must use YYYY-MM-DD format."
        if start_parsed is not None and end_parsed is not None and start_parsed > end_parsed:
            return "Start date cannot be after end date."
        return None

    @staticmethod
    def _fmt_num(value: Any) -> str:
        if value is None:
            return ""
        return f"{float(value):.2f}"

    @staticmethod
    def _fmt_int(value: Any) -> str:
        if value is None:
            return ""
        return str(int(value))

    @staticmethod
    def _fmt_pct(value: Any, *, ratio: bool = False) -> str:
        if value is None:
            return ""
        number = float(value) * 100.0 if ratio else float(value)
        return f"{number:.2f}%"
