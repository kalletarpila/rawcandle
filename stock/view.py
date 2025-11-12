from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence

import flet as ft

try:
    from plotly.graph_objects import Bar, Candlestick, Scatter
    from plotly.subplots import make_subplots
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    Bar = Candlestick = Scatter = None  # type: ignore
    make_subplots = None  # type: ignore

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
            ),
        )

        return ft.View(
            "/stock",
            controls=[
                self._appbar_factory(),
                view_content,
            ],
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

        self._set_status(f"✅ Data haettu tickerille {ticker}", ft.Colors.GREEN_600)

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
        figure = _build_price_figure(self.price_records)
        if figure:
            self.chart_container.content = ft.PlotlyChart(
                figure,
                expand=True,
            )
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

def _build_price_figure(price_records: Sequence[Dict]) -> Optional[object]:
    if not price_records:
        return None
    if make_subplots is None or Bar is None or Candlestick is None or Scatter is None:
        return None

    x_values = [record["date"].isoformat() for record in price_records]
    opens = [record.get("open") for record in price_records]
    highs = [record.get("high") for record in price_records]
    lows = [record.get("low") for record in price_records]
    closes = [record.get("close") for record in price_records]
    volumes = [record.get("volume") or 0 for record in price_records]

    if not any(value is not None for value in closes):
        return None

    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.7, 0.3],
    )

    fig.add_trace(
        Candlestick(
            x=x_values,
            open=opens,
            high=highs,
            low=lows,
            close=closes,
            name="OHLC",
        ),
        row=1,
        col=1,
    )

    fig.add_trace(
        Bar(
            x=x_values,
            y=volumes,
            marker_color="#8884d8",
            name="Volyymi",
        ),
        row=2,
        col=1,
    )

    sma20 = [record.get("sma20") for record in price_records]
    if any(value is not None for value in sma20):
        fig.add_trace(
            Scatter(
                x=x_values,
                y=sma20,
                mode="lines",
                name="SMA20",
                line=dict(color="#F97316"),
            ),
            row=1,
            col=1,
        )

    sma50 = [record.get("sma50") for record in price_records]
    if any(value is not None for value in sma50):
        fig.add_trace(
            Scatter(
                x=x_values,
                y=sma50,
                mode="lines",
                name="SMA50",
                line=dict(color="#0EA5E9"),
            ),
            row=1,
            col=1,
        )

    fig.update_layout(
        margin=dict(t=10, r=10, l=10, b=0),
        template="plotly_white",
        showlegend=False,
        height=400,
    )
    fig.update_yaxes(title_text="Hinta", row=1, col=1)
    fig.update_yaxes(title_text="Volyymi", row=2, col=1)
    return fig


def _format_number(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_volume(value: Optional[float]) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}".replace(",", " ")
