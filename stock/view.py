from __future__ import annotations

import math
import datetime as dt
from typing import Callable, Dict, List, Optional, Sequence

import flet as ft
from flet import canvas as cv

from stock import services


class StockView:
    """Rakentaa Stock-sivun, joka näyttää yksittäisen osakkeen tiedot."""

    PRICE_LIMIT = 200
    ANALYSIS_PAGE_SIZE = 25

    def __init__(self, page: ft.Page, appbar_factory: Callable[[], ft.AppBar]):
        self.page = page
        self._appbar_factory = appbar_factory

        # UI viittaukset
        self.ticker_field: Optional[ft.TextField] = None
        self.status_text: Optional[ft.Text] = None
        self.chart_container: Optional[ft.Container] = None
        self.analysis_table: Optional[ft.DataTable] = None
        self.analysis_pager_label: Optional[ft.Text] = None
        self.analysis_prev_btn: Optional[ft.IconButton] = None
        self.analysis_next_btn: Optional[ft.IconButton] = None
        self.price_table: Optional[ft.DataTable] = None

        # Data-tila
        self.current_ticker: Optional[str] = None
        self.price_records: List[Dict] = []
        self.analysis_total: int = 0
        self.analysis_page: int = 0

    # ------------------------------------------------------------------ #
    # Public API

    def create_view(self) -> ft.View:
        """Palauttaa Stock-sivun View-rakenteen."""
        text_input_action = getattr(ft, "TextInputAction", None)
        ticker_kwargs = dict(
            label="Osakkeen ticker",
            hint_text="Esim. AAPL",
            width=220,
            on_submit=self._on_fetch_clicked,
        )
        if text_input_action is not None:
            ticker_kwargs["text_input_action"] = getattr(
                text_input_action, "DONE", None
            )

        self.ticker_field = ft.TextField(**ticker_kwargs)

        fetch_button = ft.ElevatedButton(
            "Hae tiedot",
            icon=ft.Icons.SEARCH,
            on_click=self._on_fetch_clicked,
        )

        self.status_text = ft.Text(
            "Syötä ticker ja hae tiedot.",
            color=ft.Colors.GREY_600,
        )

        self.chart_container = ft.Container(
            height=420,
            bgcolor=ft.Colors.GREY_50,
            border_radius=10,
            padding=15,
            content=ft.Text(
                "Kynttilägrafiikka näytetään tässä haun jälkeen.",
                color=ft.Colors.GREY_600,
            ),
        )

        self.analysis_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Päivä", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Pattern", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Vahvuus", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("RSI14", weight=ft.FontWeight.BOLD)),
            ],
            rows=[],
            heading_row_color=ft.Colors.GREY_100,
            column_spacing=20,
        )

        self.analysis_prev_btn = ft.IconButton(
            ft.Icons.CHEVRON_LEFT,
            tooltip="Edellinen sivu",
            on_click=lambda _: self._change_analysis_page(-1),
            disabled=True,
        )
        self.analysis_next_btn = ft.IconButton(
            ft.Icons.CHEVRON_RIGHT,
            tooltip="Seuraava sivu",
            on_click=lambda _: self._change_analysis_page(1),
            disabled=True,
        )
        self.analysis_pager_label = ft.Text("0 / 0", color=ft.Colors.GREY_600)

        analysis_card = ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "Analysis-kannan tapahtumat",
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text("(25 viimeistä merkintää per sivu)"),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Container(
                            content=ft.Column([self.analysis_table], scroll=ft.ScrollMode.ADAPTIVE),
                            height=320,
                        ),
                        ft.Row(
                            [
                                self.analysis_prev_btn,
                                self.analysis_pager_label,
                                self.analysis_next_btn,
                            ],
                            alignment=ft.MainAxisAlignment.END,
                        ),
                    ],
                    spacing=12,
                ),
            )
        )

        self.price_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Päivä", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Open", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("High", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Low", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Close", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("Volyymi", weight=ft.FontWeight.BOLD)),
                ft.DataColumn(ft.Text("RSI14", weight=ft.FontWeight.BOLD)),
            ],
            rows=[],
            heading_row_color=ft.Colors.GREY_100,
            column_spacing=18,
        )

        price_card = ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(
                                    "OHLCV + RSI14",
                                    size=16,
                                    weight=ft.FontWeight.BOLD,
                                ),
                                ft.Text("(max 200 viimeisintä päivää)"),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        ft.Container(
                            content=ft.Column([self.price_table], scroll=ft.ScrollMode.ADAPTIVE),
                            height=360,
                        ),
                    ],
                    spacing=12,
                ),
            )
        )

        view_content = ft.Container(
            padding=20,
            expand=True,
            content=ft.Column(
                [
                    ft.Text("Stock", size=28, weight=ft.FontWeight.BOLD),
                    ft.Text("Tutki yksittäisen osakkeen hintaa ja analyysitietoja."),
                    ft.Row(
                        [
                            self.ticker_field,
                            fetch_button,
                        ],
                        spacing=12,
                    ),
                    self.status_text,
                    ft.Card(
                        content=ft.Container(
                            padding=20,
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.Text(
                                                "Kynttilägrafiikka + volyymit",
                                                size=16,
                                                weight=ft.FontWeight.BOLD,
                                            ),
                                            ft.Text(
                                                "SMA20 + SMA50",
                                                color=ft.Colors.GREY_600,
                                            ),
                                        ],
                                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                    ),
                                    self.chart_container,
                                ],
                                spacing=12,
                            ),
                        )
                    ),
                    analysis_card,
                    price_card,
                ],
                spacing=18,
                expand=True,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

        return ft.View(
            "/stock",
            controls=[
                self._appbar_factory(),
                view_content,
            ],
            scroll=ft.ScrollMode.AUTO,
        )

    # ------------------------------------------------------------------ #
    # Event handlers & rendering helpers

    def _on_fetch_clicked(self, e) -> None:
        ticker = (self.ticker_field.value or "").strip().upper() if self.ticker_field else ""
        if not ticker:
            self._set_status("Syötä osakkeen ticker.", ft.Colors.RED_600)
            return

        self._set_status(f"Haetaan tietoja tickerille {ticker}...", ft.Colors.BLUE_600)

        try:
            price_records = services.fetch_price_rows(
                ticker,
                limit=self.PRICE_LIMIT,
            )
            analysis_rows, total = services.fetch_analysis_records(
                ticker,
                page=0,
                page_size=self.ANALYSIS_PAGE_SIZE,
            )
        except services.StockDataError as exc:
            self._set_status(str(exc), ft.Colors.RED_600)
            self._clear_results()
            return
        except Exception as exc:  # pragma: no cover - defensive logging
            self._set_status(f"❌ Virhe haettaessa dataa: {exc}", ft.Colors.RED_600)
            self._clear_results()
            return

        if not price_records:
            self._set_status(f"ℹ️ Ei hintadataa tickerille {ticker}", ft.Colors.ORANGE_600)
            self._clear_results()
            return

        self.current_ticker = ticker
        self.price_records = price_records
        self.analysis_total = total
        self.analysis_page = 0

        self._render_chart()
        self._set_analysis_rows(analysis_rows)
        self._render_price_table()
        self._update_analysis_pager()

        self._set_status(
            f"✅ Data haettu tickerille {ticker} ({len(price_records)} päivää)",
            ft.Colors.GREEN_600,
        )

    def _set_status(self, message: str, color: str = ft.Colors.GREY_600) -> None:
        if not self.status_text:
            return
        self.status_text.value = message
        self.status_text.color = color
        self.status_text.update()

    def _clear_results(self) -> None:
        if self.chart_container:
            self.chart_container.content = ft.Text(
                "Kynttilägrafiikka näytetään tässä haun jälkeen.",
                color=ft.Colors.GREY_600,
            )
            self.chart_container.update()
        if self.analysis_table:
            self.analysis_table.rows = []
            self.analysis_table.update()
        if self.price_table:
            self.price_table.rows = []
            self.price_table.update()
        self.analysis_total = 0
        self._update_analysis_pager()

    def _render_chart(self) -> None:
        if not self.chart_container:
            return
        chart_content = _build_price_chart(self.price_records)
        if chart_content:
            self.chart_container.content = chart_content
        else:
            self.chart_container.content = ft.Text(
                "Ei riittävästi dataa kynttilägrafiikalle.",
                color=ft.Colors.GREY_600,
            )
        self.chart_container.update()

    def _set_analysis_rows(self, rows: Sequence[Dict]) -> None:
        if not self.analysis_table:
            return
        formatted_rows = []
        for row in rows:
            date_value = row.get("date")
            date_str = date_value.strftime("%d.%m.%Y") if date_value else "-"
            pattern = row.get("pattern") or "-"
            strength = row.get("signal_strength")
            strength_str = f"{strength:.2f}" if strength is not None else "-"
            rsi = row.get("rsi14")
            rsi_str = f"{rsi:.2f}" if isinstance(rsi, (int, float)) else "-"
            formatted_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(date_str)),
                        ft.DataCell(ft.Text(str(pattern))),
                        ft.DataCell(ft.Text(strength_str)),
                        ft.DataCell(ft.Text(rsi_str)),
                    ]
                )
            )

        self.analysis_table.rows = formatted_rows
        self.analysis_table.update()

    def _render_price_table(self) -> None:
        if not self.price_table:
            return
        display_rows = list(reversed(self.price_records))
        rendered_rows = []
        for record in display_rows:
            rendered_rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(record["date"].strftime("%d.%m.%Y"))),
                        ft.DataCell(ft.Text(_format_number(record.get("open")))),
                        ft.DataCell(ft.Text(_format_number(record.get("high")))),
                        ft.DataCell(ft.Text(_format_number(record.get("low")))),
                        ft.DataCell(ft.Text(_format_number(record.get("close")))),
                        ft.DataCell(ft.Text(_format_volume(record.get("volume")))),
                        ft.DataCell(ft.Text(_format_number(record.get("rsi")))),
                    ]
                )
            )

        self.price_table.rows = rendered_rows
        self.price_table.update()

    def _change_analysis_page(self, offset: int) -> None:
        if not self.current_ticker or self.analysis_total == 0:
            return
        total_pages = math.ceil(self.analysis_total / self.ANALYSIS_PAGE_SIZE)
        new_page = self.analysis_page + offset
        if new_page < 0 or new_page >= total_pages:
            return
        try:
            rows, _ = services.fetch_analysis_records(
                self.current_ticker,
                page=new_page,
                page_size=self.ANALYSIS_PAGE_SIZE,
            )
        except services.StockDataError as exc:
            self._set_status(str(exc), ft.Colors.RED_600)
            return
        except Exception as exc:  # pragma: no cover - defensive
            self._set_status(f"❌ Sivutus epäonnistui: {exc}", ft.Colors.RED_600)
            return

        self.analysis_page = new_page
        self._set_analysis_rows(rows)
        self._update_analysis_pager()

    def _update_analysis_pager(self) -> None:
        if not (self.analysis_pager_label and self.analysis_prev_btn and self.analysis_next_btn):
            return
        if self.analysis_total == 0:
            self.analysis_pager_label.value = "0 / 0"
            self.analysis_prev_btn.disabled = True
            self.analysis_next_btn.disabled = True
        else:
            total_pages = max(1, math.ceil(self.analysis_total / self.ANALYSIS_PAGE_SIZE))
            self.analysis_pager_label.value = f"Sivu {self.analysis_page + 1} / {total_pages}"
            self.analysis_prev_btn.disabled = self.analysis_page == 0
            self.analysis_next_btn.disabled = self.analysis_page >= total_pages - 1

        self.analysis_pager_label.update()
        self.analysis_prev_btn.update()
        self.analysis_next_btn.update()


# ---------------------------------------------------------------------- #
# Helpers

def _build_price_chart(price_records: Sequence[Dict]) -> Optional[ft.Control]:
    valid = [
        record
        for record in price_records
        if all(record.get(key) is not None for key in ("open", "high", "low", "close"))
    ]
    if len(valid) < 2:
        return None

    min_low = min(float(rec["low"]) for rec in valid)
    max_high = max(float(rec["high"]) for rec in valid)
    if max_high - min_low <= 0:
        return None

    price_height = 260
    volume_height = 110
    spacing = 8
    candle_width = 5
    x_offset = 20
    canvas_width = max(640, len(valid) * spacing + x_offset * 2)

    price_scale = price_height / (max_high - min_low)
    price_shapes = [
        cv.Line(
            0,
            price_height,
            canvas_width,
            price_height,
            paint=ft.Paint(stroke_width=1, color="#E5E7EB"),
        )
    ]

    for idx, record in enumerate(valid):
        open_val = float(record["open"])
        close_val = float(record["close"])
        high_val = float(record["high"])
        low_val = float(record["low"])

        x_center = x_offset + idx * spacing
        wick_color = "#22C55E" if close_val >= open_val else "#EF4444"
        paint_wick = ft.Paint(stroke_width=1, color=wick_color)
        high_y = price_height - (high_val - min_low) * price_scale
        low_y = price_height - (low_val - min_low) * price_scale
        price_shapes.append(cv.Line(x_center, high_y, x_center, low_y, paint=paint_wick))

        open_y = price_height - (open_val - min_low) * price_scale
        close_y = price_height - (close_val - min_low) * price_scale
        top = min(open_y, close_y)
        height = max(abs(open_y - close_y), 1)
        paint_body = ft.Paint(color=wick_color)
        price_shapes.append(
            cv.Rect(
                x_center - candle_width / 2,
                top,
                candle_width,
                height,
                paint=paint_body,
            )
        )

        record["x_center"] = x_center

        sma20 = record.get("sma20")
        record["sma20_y"] = (
            price_height - (sma20 - min_low) * price_scale
            if isinstance(sma20, (int, float))
            else None
        )
        sma50 = record.get("sma50")
        record["sma50_y"] = (
            price_height - (sma50 - min_low) * price_scale
            if isinstance(sma50, (int, float))
            else None
        )

    price_shapes.extend(_build_sma_paths(valid, "sma20_y", "#F97316"))
    price_shapes.extend(_build_sma_paths(valid, "sma50_y", "#0EA5E9"))

    price_canvas = cv.Canvas(
        shapes=price_shapes,
        width=canvas_width,
        height=price_height + 20,
    )

    max_volume = max(float(record.get("volume") or 0.0) for record in valid)
    volume_shapes = [
        cv.Line(
            0,
            volume_height,
            canvas_width,
            volume_height,
            paint=ft.Paint(stroke_width=1, color="#E5E7EB"),
        )
    ]
    if max_volume > 0:
        volume_scale = volume_height / max_volume
        for record in valid:
            volume = float(record.get("volume") or 0.0)
            bar_height = volume * volume_scale
            color = "#6366F1"
            volume_shapes.append(
                cv.Rect(
                    record["x_center"] - candle_width / 2,
                    volume_height - bar_height,
                    candle_width,
                    max(bar_height, 1),
                    paint=ft.Paint(color=color),
                )
            )

    volume_canvas = cv.Canvas(
        shapes=volume_shapes,
        width=canvas_width,
        height=volume_height + 20,
    )

    label_row = _build_label_row(valid, canvas_width)
    inner_column = ft.Column(
        [
            price_canvas,
            ft.Text("Hinta", size=12, color=ft.Colors.GREY_600),
            volume_canvas,
            ft.Text("Volyymi", size=12, color=ft.Colors.GREY_600),
            label_row,
        ],
        spacing=6,
        width=canvas_width,
    )

    return ft.Row(
        controls=[inner_column],
        scroll=ft.ScrollMode.AUTO,
    )


def _build_sma_paths(records: Sequence[Dict], key: str, color: str) -> List:
    points = [
        (record["x_center"], record[key])
        for record in records
        if record.get("x_center") is not None and record.get(key) is not None
    ]
    if len(points) < 2:
        return []
    shapes: List = []
    for idx in range(1, len(points)):
        x1, y1 = points[idx - 1]
        x2, y2 = points[idx]
        shapes.append(
            cv.Line(
                x1,
                y1,
                x2,
                y2,
                paint=ft.Paint(stroke_width=1.5, color=color),
            )
        )
    return shapes


def _build_label_row(records: Sequence[Dict], width: int) -> ft.Row:
    if not records:
        return ft.Row([])
    indices = [0, len(records) // 2, len(records) - 1]
    labels = []
    for idx in indices:
        idx = min(max(idx, 0), len(records) - 1)
        date_value = records[idx]["date"]
        if isinstance(date_value, (dt.date, dt.datetime)):
            label = date_value.strftime("%d.%m.%Y")
        else:
            label = str(date_value)
        labels.append(ft.Text(label, size=11, color=ft.Colors.GREY_600))
    return ft.Row(
        controls=[
            labels[0],
            ft.Container(expand=True),
            labels[1],
            ft.Container(expand=True),
            labels[2],
        ],
        width=width,
    )


def _format_number(value: Optional[float]) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "-"


def _format_volume(value: Optional[float]) -> str:
    if value is None:
        return "-"
    try:
        return f"{float(value):,.0f}".replace(",", " ")
    except (TypeError, ValueError):
        return "-"
