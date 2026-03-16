from __future__ import annotations

import asyncio
from datetime import date
import math
from typing import Any

import flet as ft

from analysis.divergence_research_query import (
    export_divergence_events_csv,
    fetch_divergence_events,
    fetch_divergence_heatmap,
    summarize_divergence_events,
)
from market_repository import list_markets


class DivergencePage:
    TABLE_COLUMNS = [
        ("ticker", "Ticker"),
        ("date", "Date"),
        ("event_class", "Event class"),
        ("pivot_gap_r2", "Gap R2"),
        ("pivot_drop_pct_r2", "Drop R2"),
        ("pivot_gap_r3", "Gap R3"),
        ("pivot_drop_pct_r3", "Drop R3"),
        ("rsi", "RSI"),
        ("ret_5d", "Ret 5d"),
        ("ret_10d", "Ret 10d"),
        ("ret_20d", "Ret 20d"),
        ("ret_30d", "Ret 30d"),
    ]

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
        self.current_rows: list[dict[str, Any]] = []

        self.event_class_dropdown: ft.Dropdown | None = None
        self.market_dropdown: ft.Dropdown | None = None
        self.min_gap_slider: ft.Slider | None = None
        self.max_gap_slider: ft.Slider | None = None
        self.min_drop_slider: ft.Slider | None = None
        self.max_drop_slider: ft.Slider | None = None
        self.min_rsi_slider: ft.Slider | None = None
        self.max_rsi_slider: ft.Slider | None = None
        self.start_date_field: ft.TextField | None = None
        self.end_date_field: ft.TextField | None = None
        self.summary_text: ft.Text | None = None
        self.filter_error_text: ft.Text | None = None
        self.export_status_text: ft.Text | None = None
        self.table: ft.DataTable | None = None
        self.pagination_text: ft.Text | None = None
        self.heatmap_container: ft.Column | None = None
        self.refresh_dialog: ft.AlertDialog | None = None
        self.refresh_progress_text: ft.Text | None = None
        self._refresh_cancelled = False
        self._refresh_generation = 0

    def create_view(self) -> ft.View:
        self.event_class_dropdown = ft.Dropdown(
            label="Event class",
            width=180,
            value="All",
            options=[
                ft.dropdown.Option("All"),
                ft.dropdown.Option("R2"),
                ft.dropdown.Option("R3"),
                ft.dropdown.Option("R2_ONLY"),
                ft.dropdown.Option("R3_ONLY"),
                ft.dropdown.Option("R2_AND_R3"),
            ],
            on_change=self._on_filter_change,
        )
        market_options = [ft.dropdown.Option("All Markets")] + [
            ft.dropdown.Option(market["abbreviation"])
            for market in list_markets(self.stock_db_path)
        ]
        self.market_dropdown = ft.Dropdown(
            label="Markets",
            width=180,
            value="All Markets",
            options=market_options,
            on_change=self._on_filter_change,
        )
        self.min_gap_slider = ft.Slider(min=5, max=24, divisions=19, value=5, label="{value}", on_change_end=self._on_filter_change)
        self.max_gap_slider = ft.Slider(min=5, max=24, divisions=19, value=24, label="{value}", on_change_end=self._on_filter_change)
        self.min_drop_slider = ft.Slider(min=0, max=50, divisions=50, value=0, label="{value}", on_change_end=self._on_filter_change)
        self.max_drop_slider = ft.Slider(min=0, max=50, divisions=50, value=50, label="{value}", on_change_end=self._on_filter_change)
        self.min_rsi_slider = ft.Slider(min=1, max=100, divisions=99, value=1, label="{value}", on_change_end=self._on_filter_change)
        self.max_rsi_slider = ft.Slider(min=1, max=100, divisions=99, value=100, label="{value}", on_change_end=self._on_filter_change)
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
        self.export_status_text = ft.Text(size=12)
        self.pagination_text = ft.Text("Page 1", size=12)
        self.table = self._build_table()
        self.heatmap_container = ft.Column(spacing=4)

        refresh_button = ft.ElevatedButton(
            "Refresh",
            icon=ft.Icons.REFRESH,
            on_click=self._refresh,
        )
        export_button = ft.ElevatedButton(
            "Export CSV",
            icon=ft.Icons.DOWNLOAD,
            on_click=self._export_csv,
        )
        prev_button = ft.OutlinedButton("Prev", on_click=self._prev_page)
        next_button = ft.OutlinedButton("Next", on_click=self._next_page)

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
                                                    self.market_dropdown,
                                                    self.start_date_field,
                                                    self.end_date_field,
                                                    refresh_button,
                                                    export_button,
                                                ],
                                                wrap=True,
                                                spacing=16,
                                            ),
                                            self.filter_error_text,
                                            self.export_status_text,
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
                                            ft.Text("RSI"),
                                            ft.Row(
                                                [
                                                    ft.Column([ft.Text("Min RSI"), self.min_rsi_slider], expand=True),
                                                    ft.Column([ft.Text("Max RSI"), self.max_rsi_slider], expand=True),
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
            scroll=ft.ScrollMode.AUTO,
        )

    def _build_table(self) -> ft.DataTable:
        return ft.DataTable(
            columns=[
                self._sortable_column(key, label)
                for key, label in self.TABLE_COLUMNS
            ],
            rows=[],
            sort_column_index=self._sort_column_index(),
            sort_ascending=not self.sort_desc,
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

    def _sort_column_index(self) -> int:
        for index, (key, _label) in enumerate(self.TABLE_COLUMNS):
            if key == self.sort_by:
                return index
        return 0

    def _get_filters(self) -> dict[str, Any]:
        min_gap = int(self.min_gap_slider.value)
        max_gap = int(self.max_gap_slider.value)
        min_drop = float(self.min_drop_slider.value)
        max_drop = float(self.max_drop_slider.value)
        min_rsi = float(self.min_rsi_slider.value)
        max_rsi = float(self.max_rsi_slider.value)
        if min_gap > max_gap:
            min_gap, max_gap = max_gap, min_gap
        if min_drop > max_drop:
            min_drop, max_drop = max_drop, min_drop
        if min_rsi > max_rsi:
            min_rsi, max_rsi = max_rsi, min_rsi
        event_class = self.event_class_dropdown.value
        if event_class == "All":
            event_class = None
        market = self.market_dropdown.value
        if market == "All Markets":
            market = None
        start_date = (self.start_date_field.value or "").strip()
        end_date = (self.end_date_field.value or "").strip()
        validation_error = self.validate_date_range(start_date, end_date)
        if validation_error is not None:
            raise ValueError(validation_error)
        return {
            "event_class": event_class,
            "market": market,
            "min_gap": min_gap,
            "max_gap": max_gap,
            "min_drop": min_drop,
            "max_drop": max_drop,
            "min_rsi": min_rsi,
            "max_rsi": max_rsi,
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
        self._start_refresh_worker(filters)

    def _start_refresh_worker(self, filters: dict[str, Any]) -> None:
        self._refresh_generation += 1
        generation = self._refresh_generation
        self._refresh_cancelled = False
        self._show_refresh_dialog()
        self.page.run_task(self._run_refresh_task, generation, filters)

    async def _run_refresh_task(
        self, generation: int, filters: dict[str, Any]
    ) -> None:
        try:
            await self._set_refresh_progress(generation, "Loading summary...")
            summary = await asyncio.to_thread(
                summarize_divergence_events,
                self.analysis_db_path,
                stock_db_path=self.stock_db_path,
                **filters,
            )
            if generation != self._refresh_generation or self._refresh_cancelled:
                return

            await self._set_refresh_progress(generation, "Loading event rows...")
            events = await asyncio.to_thread(
                fetch_divergence_events,
                self.analysis_db_path,
                stock_db_path=self.stock_db_path,
                limit=self.page_size,
                offset=self.page_index * self.page_size,
                sort_by=self.sort_by,
                sort_desc=self.sort_desc,
                **filters,
            )
            if generation != self._refresh_generation or self._refresh_cancelled:
                return

            await self._set_refresh_progress(generation, "Building heatmap...")
            heatmap = await asyncio.to_thread(
                fetch_divergence_heatmap,
                self.analysis_db_path,
                stock_db_path=self.stock_db_path,
                **filters,
            )
            if generation != self._refresh_generation or self._refresh_cancelled:
                return

            self._update_summary(summary)
            self._update_table(events)
            self._update_heatmap(heatmap)
            if self.pagination_text is not None:
                self.pagination_text.value = f"Page {self.page_index + 1}"
            self._close_refresh_dialog()
            self.page.update()
        except Exception as exc:
            if generation != self._refresh_generation:
                return
            self._close_refresh_dialog()
            if self.filter_error_text is not None:
                self.filter_error_text.value = f"Refresh failed: {exc}"
            try:
                self.page.update()
            except Exception:
                pass

    async def _set_refresh_progress(self, generation: int, message: str) -> None:
        if generation != self._refresh_generation or self._refresh_cancelled:
            return
        if self.refresh_progress_text is not None:
            self.refresh_progress_text.value = message
        try:
            self.page.update()
        except Exception:
            pass

    def _show_refresh_dialog(self) -> None:
        progress_ring = ft.ProgressRing(width=36, height=36)
        self.refresh_progress_text = ft.Text("Loading summary...", size=14)

        def cancel_refresh(_e) -> None:
            self._refresh_cancelled = True
            self._refresh_generation += 1
            self._close_refresh_dialog()

        self.refresh_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Refreshing divergence research"),
            content=ft.Column(
                [
                    ft.Row([progress_ring, self.refresh_progress_text], spacing=16),
                    ft.Text(
                        "Query is running. You can cancel before results are applied.",
                        size=12,
                        color=ft.Colors.GREY_600,
                    ),
                ],
                tight=True,
                spacing=12,
            ),
            actions=[ft.TextButton("Cancel", on_click=cancel_refresh)],
        )
        try:
            self.page.open(self.refresh_dialog)
        except Exception:
            pass

    def _close_refresh_dialog(self) -> None:
        dialog = self.refresh_dialog
        if dialog is None:
            return
        try:
            self.page.close(dialog)
        except Exception:
            pass
        self.refresh_dialog = None
        self.refresh_progress_text = None

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
        self.current_rows = list(rows)
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

    def _sorted_current_rows(self) -> list[dict[str, Any]]:
        def sort_value(row: dict[str, Any]) -> tuple[int, Any]:
            value = row.get(self.sort_by)
            if value is None:
                return (1, "")
            if isinstance(value, str):
                return (0, value)
            return (0, float(value))

        return sorted(
            self.current_rows,
            key=sort_value,
            reverse=self.sort_desc,
        )

    def _update_heatmap(self, heatmap_rows: list[dict[str, Any]]) -> None:
        if self.heatmap_container is None:
            return
        cells: list[ft.Control] = []
        if heatmap_rows:
            for row in heatmap_rows[:80]:
                winsor_ret_30d = float(row["winsor_ret_30d"])
                if winsor_ret_30d < 0:
                    color = "#c44e52"
                elif winsor_ret_30d > 20:
                    color = "#55a868"
                elif winsor_ret_30d >= 0:
                    color = "#ddcc77"
                else:
                    color = "#505080"
                cells.append(
                    ft.Container(
                        width=90,
                        height=72,
                        bgcolor=color,
                        border_radius=6,
                        padding=6,
                        content=ft.Column(
                            [
                                ft.Text(
                                    f"G{row['gap']} D{row['drop']}",
                                    size=10,
                                    color=ft.Colors.WHITE,
                                ),
                                ft.Text(
                                    self._fmt_pct(row["avg_ret_30d"]),
                                    size=11,
                                    weight=ft.FontWeight.BOLD,
                                    color=ft.Colors.WHITE,
                                ),
                                ft.Text(
                                    f"W {self._fmt_pct(row['winsor_ret_30d'])}",
                                    size=9,
                                    color=ft.Colors.WHITE,
                                ),
                                ft.Text(
                                    f"n={row['n']}",
                                    size=10,
                                    color=ft.Colors.WHITE,
                                ),
                            ],
                            spacing=1,
                        ),
                    )
                )
        self.heatmap_container.controls = [
            ft.Row(cells[idx : idx + 10], spacing=6)
            for idx in range(0, len(cells), 10)
        ] or [ft.Text("No heatmap cells for current filters.")]

    def _sort(self, sort_key: str) -> None:
        if self.sort_by == sort_key:
            self.sort_desc = not self.sort_desc
        else:
            self.sort_by = sort_key
            self.sort_desc = True
        if self.table is not None:
            self.table.sort_column_index = self._sort_column_index()
            self.table.sort_ascending = not self.sort_desc
        if self.current_rows:
            self._update_table(self._sorted_current_rows())
        self.page.update()

    def _prev_page(self, _e) -> None:
        if self.page_index > 0:
            self.page_index -= 1
            self._refresh()

    def _next_page(self, _e) -> None:
        self.page_index += 1
        self._refresh()

    def _on_filter_change(self, _e) -> None:
        self.page_index = 0

    def _export_csv(self, _e) -> None:
        try:
            filters = self._get_filters()
        except ValueError as exc:
            if self.filter_error_text is not None:
                self.filter_error_text.value = str(exc)
            if self.export_status_text is not None:
                self.export_status_text.value = ""
            self.page.update()
            return
        if self.filter_error_text is not None:
            self.filter_error_text.value = ""
        try:
            saved_path = export_divergence_events_csv(
                self.analysis_db_path,
                stock_db_path=self.stock_db_path,
                **filters,
            )
            if self.export_status_text is not None:
                self.export_status_text.value = f"Exported CSV: {saved_path}"
                self.export_status_text.color = ft.Colors.GREEN_700
        except Exception as exc:
            if self.export_status_text is not None:
                self.export_status_text.value = f"CSV export failed: {exc}"
                self.export_status_text.color = ft.Colors.RED_700
        self.page.update()

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
