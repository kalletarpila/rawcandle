from __future__ import annotations

import base64
import math
import datetime as dt
from typing import Callable, Dict, List, Optional, Sequence, Set

import flet as ft
from flet import canvas as cv
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from stock import services


class StockView:
    """Rakentaa Stock-sivun, joka näyttää yksittäisen osakkeen tiedot."""

    PRICE_LIMIT = None  # fetch all data so "Kaikki" preset shows entire range
    ANALYSIS_PAGE_SIZE = 25
    RANGE_PRESETS = [
        ("1M", "1 kk"),
        ("3M", "3 kk"),
        ("6M", "6 kk"),
        ("1Y", "1 v"),
        ("ALL", "Kaikki"),
    ]
    PATTERN_OPTIONS = [
        ("downtrend", "Downtrend"),
        ("Hammer", "Hammer"),
        ("Bullish Engulfing", "Bullish Engulfing"),
        ("Piercing Pattern", "Piercing Pattern"),
        ("Three White Soldiers", "Three White Soldiers"),
        ("Morning Star", "Morning Star"),
        ("Dragonfly Doji", "Dragonfly Doji"),
        ("Bullish Divergence", "Bullish Divergence"),
        ("BullDiv & Hammer", "BullDiv & Hammer"),
        ("BullDiv & Bullish Engulfing", "BullDiv & Bullish Engulfing"),
        ("BullDiv & Piercing Pattern", "BullDiv & Piercing Pattern"),
        ("BullDiv & Three White Soldiers", "BullDiv & Three White Soldiers"),
        ("BullDiv & Morning Star", "BullDiv & Morning Star"),
        ("BullDiv & Dragonfly Doji", "BullDiv & Dragonfly Doji"),
    ]
    PATTERN_COLORS = {
        "downtrend": "#dc2626",  # kirkas punainen
        "Hammer": "#0ea5e9",  # turkoosi
        "Bullish Engulfing": "#16a34a",  # vihreä
        "Piercing Pattern": "#f97316",  # oranssi
        "Three White Soldiers": "#9333ea",  # violetti
        "Morning Star": "#d97706",  # ruskea/oranssi
        "Dragonfly Doji": "#14b8a6",  # vihertävä sininen
        "Bullish Divergence": "#f43f5e",  # pinkki
        "BullDiv & Hammer": "#0284c7",
        "BullDiv & Bullish Engulfing": "#0f766e",
        "BullDiv & Piercing Pattern": "#ea580c",
        "BullDiv & Three White Soldiers": "#7e22ce",
        "BullDiv & Morning Star": "#b45309",
        "BullDiv & Dragonfly Doji": "#0d9488",
    }

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
        self.ma20_checkbox: Optional[ft.Checkbox] = None
        self.ma50_checkbox: Optional[ft.Checkbox] = None
        self.ma200_checkbox: Optional[ft.Checkbox] = None
        self.rsi_checkbox: Optional[ft.Checkbox] = None
        self.range_button_map: Dict[str, ft.Button] = {}
        self.pattern_checkboxes: Dict[str, ft.Checkbox] = {}
        self.pattern_select_all: Optional[ft.Checkbox] = None

        # Data-tila
        self.current_ticker: Optional[str] = None
        self.price_records: List[Dict] = []
        self.analysis_events: List[Dict] = []
        self.analysis_total: int = 0
        self.analysis_page: int = 0
        self.selected_range: str = "6M"
        self.total_days: int = 0
        self.show_ma5 = True
        self.show_ma20 = True
        self.show_ma50 = True
        self.show_ma200 = True
        self.show_rsi = True
        self.blackout_dates: Set[dt.date] = set()

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
        filters_card = self._build_filters_card()

        self.chart_container = ft.Container(
            height=600,
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
                    filters_card,
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
                                                "MA20 / MA50 / MA200",
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

    def _build_filters_card(self) -> ft.Card:
        self.range_button_map = {}
        range_buttons = []
        for key, label in self.RANGE_PRESETS:
            btn = ft.FilledButton(
                label,
                on_click=lambda e, preset=key: self._on_range_preset_click(preset),
            )
            self.range_button_map[key] = btn
            range_buttons.append(btn)
        self._update_range_button_styles()

        self.ma5_checkbox = ft.Checkbox(
            label="MA5",
            value=True,
            data="ma5",
            on_change=self._on_indicator_toggle,
        )
        self.ma20_checkbox = ft.Checkbox(
            label="MA20",
            value=True,
            data="ma20",
            on_change=self._on_indicator_toggle,
        )
        self.ma50_checkbox = ft.Checkbox(
            label="MA50",
            value=True,
            data="ma50",
            on_change=self._on_indicator_toggle,
        )
        self.ma200_checkbox = ft.Checkbox(
            label="MA200",
            value=True,
            data="ma200",
            on_change=self._on_indicator_toggle,
        )
        self.rsi_checkbox = ft.Checkbox(
            label="RSI",
            value=True,
            data="rsi",
            on_change=self._on_indicator_toggle,
        )

        self.pattern_checkboxes = {}
        self.pattern_select_all = ft.Checkbox(
            label="Valitse kaikki löydöt",
            value=True,
            on_change=self._on_pattern_select_all,
        )
        pattern_controls: List[ft.Control] = []
        for key, label in self.PATTERN_OPTIONS:
            cb = ft.Checkbox(
                label=label,
                value=True,
                data=key,
                on_change=self._on_pattern_toggle,
            )
            self.pattern_checkboxes[key] = cb
            pattern_controls.append(cb)

        indicator_section = ft.ExpansionTile(
            title=ft.Text("Indikaattorit", weight=ft.FontWeight.BOLD),
            initially_expanded=False,
            controls=[
                ft.Column(
                    [
                        self.ma5_checkbox,
                        self.ma20_checkbox,
                        self.ma50_checkbox,
                        self.ma200_checkbox,
                        self.rsi_checkbox,
                    ],
                    spacing=4,
                    alignment=ft.MainAxisAlignment.START,
                )
            ],
        )

        findings_section = ft.ExpansionTile(
            title=ft.Text("Löydöt", weight=ft.FontWeight.BOLD),
            initially_expanded=False,
            controls=[
                ft.Column(
                    [
                        self.pattern_select_all,
                        *pattern_controls,
                    ],
                    spacing=4,
                    alignment=ft.MainAxisAlignment.START,
                )
            ],
        )

        combined_wrap = ft.Column(
            [indicator_section, findings_section],
            spacing=8,
        )

        return ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text("Aikaikkuna & indikaattorit", weight=ft.FontWeight.BOLD),
                        ft.Row(range_buttons, spacing=8, wrap=True),
                        combined_wrap,
                    ],
                    spacing=12,
                ),
            )
        )

    def _update_range_button_styles(self) -> None:
        for key, btn in self.range_button_map.items():
            is_selected = key == self.selected_range
            btn.style = ft.ButtonStyle(
                bgcolor=ft.Colors.BLUE_700 if is_selected else ft.Colors.GREY_200,
                color=ft.Colors.WHITE if is_selected else ft.Colors.BLACK,
            )
            try:
                btn.update()
            except Exception:
                pass

    def _on_range_preset_click(self, preset: str) -> None:
        if preset == self.selected_range:
            return
        self.selected_range = preset
        self._update_range_button_styles()
        self._render_chart()

    def _on_indicator_toggle(self, e) -> None:
        control = e.control
        flag = control.data
        value = bool(control.value)
        if flag == "ma5":
            self.show_ma5 = value
        elif flag == "ma50":
            self.show_ma50 = value
        elif flag == "ma20":
            self.show_ma20 = value
        elif flag == "ma200":
            self.show_ma200 = value
        elif flag == "rsi":
            self.show_rsi = value
        self._render_chart()

    def _on_pattern_select_all(self, e) -> None:
        value = bool(e.control.value)
        for checkbox in self.pattern_checkboxes.values():
            checkbox.value = value
            try:
                checkbox.update()
            except Exception:
                pass
        self._render_chart()

    def _on_pattern_toggle(self, e) -> None:
        if not self.pattern_select_all:
            return
        all_selected = all(cb.value for cb in self.pattern_checkboxes.values())
        self.pattern_select_all.value = all_selected
        try:
            self.pattern_select_all.update()
        except Exception:
            pass
        self._render_chart()

    def _get_selected_patterns(self) -> Set[str]:
        if not self.pattern_checkboxes:
            return {key for key, _ in self.PATTERN_OPTIONS}
        selected = {
            key for key, checkbox in self.pattern_checkboxes.items() if checkbox.value
        }
        return selected

    # ------------------------------------------------------------------ #
    # Event handlers & rendering helpers

    def _on_fetch_clicked(self, e) -> None:
        ticker = (self.ticker_field.value or "").strip().upper() if self.ticker_field else ""
        if not ticker:
            self._set_status("Syötä osakkeen ticker.", ft.Colors.RED_600)
            return

        self._set_status(f"Haetaan tietoja tickerille {ticker}...", ft.Colors.BLUE_600)

        try:
            price_records, total_rows = services.fetch_price_rows(
                ticker,
                limit=self.PRICE_LIMIT,
            )
            analysis_events = (
                services.fetch_analysis_events(
                    ticker,
                    start_date=price_records[0]["date"],
                    end_date=price_records[-1]["date"],
                )
                if price_records
                else []
            )
            analysis_rows, total = services.fetch_analysis_records(
                ticker,
                page=0,
                page_size=self.ANALYSIS_PAGE_SIZE,
            )
            blackout_dates = services.fetch_blackout_dates(ticker)
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
        self.total_days = total_rows
        self.analysis_events = analysis_events
        self.analysis_total = total
        self.analysis_page = 0
        self.blackout_dates = blackout_dates or set()

        self._render_chart()
        self._set_analysis_rows(analysis_rows)
        self._render_price_table()
        self._update_analysis_pager()

        self._set_status(
            f"✅ Data haettu tickerille {ticker} ({self.total_days} päivää)",
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
        self.analysis_events = []
        self._update_analysis_pager()

    def _render_chart(self) -> None:
        if not self.chart_container:
            return
        filtered = self._filter_price_records()
        if not filtered:
            self.chart_container.content = ft.Text(
                "Ei riittävästi dataa valitulla aikavälillä.",
                color=ft.Colors.GREY_600,
            )
            self.chart_container.update()
            return

        events = self._get_filtered_events(filtered)
        fig = self._build_plotly_figure(filtered, events)
        html = fig.to_html(include_plotlyjs="cdn", full_html=False)
        data_url = "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode("utf-8")
        self.chart_container.content = ft.WebView(
            url=data_url,
            enable_javascript=True,
            height=600,
        )
        self.chart_container.update()

    def _filter_price_records(self) -> List[Dict]:
        if not self.price_records:
            return []
        if self.selected_range == "ALL":
            return self.price_records

        end_date = self.price_records[-1]["date"]
        start_date = self._calculate_range_start(end_date)
        return [rec for rec in self.price_records if rec["date"] >= start_date]

    def _calculate_range_start(self, end_date: dt.date) -> dt.date:
        range_days = {
            "1M": 30,
            "3M": 90,
            "6M": 180,
            "1Y": 365,
        }
        days = range_days.get(self.selected_range, 365 * 10)
        start_candidate = end_date - dt.timedelta(days=days)
        first_date = self.price_records[0]["date"]
        return max(first_date, start_candidate)

    def _get_filtered_events(self, records: Sequence[Dict]) -> List[Dict]:
        if not self.analysis_events:
            return []
        selected_patterns = self._get_selected_patterns()
        if not selected_patterns:
            return []
        start = records[0]["date"]
        end = records[-1]["date"]
        return [
            event
            for event in self.analysis_events
            if start <= event["date"] <= end
            and event.get("pattern") in selected_patterns
        ]

    def _build_plotly_figure(
        self, records: Sequence[Dict], events: Sequence[Dict]
    ) -> go.Figure:
        dates = [rec["date"] for rec in records]
        opens = [rec.get("open") for rec in records]
        highs = [rec.get("high") for rec in records]
        lows = [rec.get("low") for rec in records]
        closes = [rec.get("close") for rec in records]
        volumes = [rec.get("volume") or 0 for rec in records]
        price_values = [val for val in highs + lows + closes if val is not None]
        if not price_values:
            price_values = [0.0]
        price_min = min(price_values)
        price_max = max(price_values)

        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            row_heights=[0.58, 0.17, 0.33],
            vertical_spacing=0.05,
            specs=[
                [{"secondary_y": False}],
                [{"secondary_y": False}],
                [{"secondary_y": False}],
            ],
        )

        fig.add_trace(
            go.Candlestick(
                x=dates,
                open=opens,
                high=highs,
                low=lows,
                close=closes,
                name="Hinta",
                increasing_line_color="#16a34a",
                decreasing_line_color="#ef4444",
            ),
            row=1,
            col=1,
        )

        price_by_date = {
            rec["date"]: rec.get("high") or rec.get("close") for rec in records
        }
        record_by_date = {rec["date"]: rec for rec in records}

        if self.show_ma20:
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=[rec.get("sma20") for rec in records],
                    mode="lines",
                    name="MA20",
                    line=dict(color="#f97316", width=1.5),
                ),
                row=1,
                col=1,
            )

        if self.show_ma5:
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=[rec.get("sma5") for rec in records],
                    mode="lines",
                    name="MA5",
                    line=dict(color="#d1d5db", width=1.5),
                ),
                row=1,
                col=1,
            )

        if self.show_ma50:
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=[rec.get("sma50") for rec in records],
                    mode="lines",
                    name="MA50",
                    line=dict(color="#0ea5e9", width=1.5),
                ),
                row=1,
                col=1,
            )

        if self.show_ma200:
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=[rec.get("sma200") for rec in records],
                    mode="lines",
                    name="MA200",
                    line=dict(color="#374151", width=1.5),
                ),
                row=1,
                col=1,
            )

        if volumes:
            blackout_set = getattr(self, "blackout_dates", set()) or set()
            volume_colors = [
                "#dc2626" if rec["date"] in blackout_set else "#6366f1"
                for rec in records
            ]
            fig.add_trace(
                go.Bar(
                    x=dates,
                    y=volumes,
                    name="Volyymi",
                    marker_color=volume_colors,
                    opacity=0.7,
                ),
                row=2,
                col=1,
            )
            fig.update_yaxes(title_text="Volyymi", row=2, col=1)

        if self.show_rsi:
            rsi_values = [rec.get("rsi") for rec in records]
            fig.add_trace(
                go.Scatter(
                    x=dates,
                    y=rsi_values,
                    mode="lines",
                    name="RSI",
                    line=dict(color="#f43f5e", width=1.2),
                ),
                row=3,
                col=1,
            )
            fig.add_shape(
                type="line",
                x0=dates[0],
                x1=dates[-1],
                y0=70,
                y1=70,
                xref="x3",
                yref="y3",
                line=dict(color="#1e3a8a", dash="dash", width=1),
            )
            fig.add_shape(
                type="line",
                x0=dates[0],
                x1=dates[-1],
                y0=30,
                y1=30,
                xref="x3",
                yref="y3",
                line=dict(color="#1e3a8a", dash="dash", width=1),
            )
            fig.update_yaxes(title_text="RSI", row=3, col=1, range=[0, 100])

        if events:
            grouped: Dict[str, List[Dict]] = {}
            for event in events:
                grouped.setdefault(event.get("pattern") or "", []).append(event)

            for pattern, items in grouped.items():
                color = self.PATTERN_COLORS.get(pattern, "#94a3b8")
                scatter_x: List[dt.date] = []
                scatter_y: List[float] = []
                hover_texts: List[str] = []
                line_x: List[Optional[dt.date]] = []
                line_y: List[Optional[float]] = []
                line_hover: List[Optional[str]] = []
                for entry in items:
                    date = entry["date"]
                    hover_text = self._format_event_tooltip(
                        pattern or "Pattern",
                        entry,
                        record_by_date.get(date),
                    )
                    hover_texts.append(hover_text)
                    scatter_x.append(date)
                    base_y = price_by_date.get(date) or price_max
                    scatter_y.append(base_y * 1.01)

                    # pystysuora katkoviiva
                    line_x.extend([date, date, None])
                    line_y.extend([price_min, price_max, None])
                    line_hover.extend([hover_text, hover_text, None])

                if line_x:
                    fig.add_trace(
                        go.Scatter(
                            x=line_x,
                            y=line_y,
                            mode="lines",
                            line=dict(color=color, dash="dot", width=1),
                            hovertemplate="%{text}<extra></extra>",
                            text=line_hover,
                            name=f"{pattern or 'Löydöt'}-viiva",
                            showlegend=False,
                        ),
                        row=1,
                        col=1,
                    )

                fig.add_trace(
                    go.Scatter(
                        x=scatter_x,
                        y=scatter_y,
                        mode="markers",
                        name=pattern or "Löydöt",
                        marker=dict(color=color, symbol="triangle-up", size=9),
                        hovertemplate="%{text}<extra></extra>",
                        text=hover_texts,
                    ),
                    row=1,
                    col=1,
                )

        fig.update_layout(
            template="plotly_white",
            height=520,
            margin=dict(t=30, l=40, r=20, b=20),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            xaxis_rangeslider=dict(visible=False),
            updatemenus=[
                dict(
                    type="buttons",
                    direction="left",
                    buttons=[
                        dict(
                            label="Reset zoom",
                            method="relayout",
                            args=[
                                {
                                    "xaxis.autorange": True,
                                    "yaxis.autorange": True,
                                    "yaxis2.autorange": True,
                                    "yaxis3.autorange": True,
                                }
                            ],
                        )
                    ],
                    x=0.0,
                    y=1.1,
                    xanchor="left",
                    yanchor="bottom",
                    showactive=False,
                )
            ],
        )
        fig.update_yaxes(title_text="Hinta", row=1, col=1)

        # build rangebreaks for weekends + missing market days (e.g. holidays)
        rangebreaks = [dict(bounds=["sat", "mon"])]
        if dates:
            date_set = {d for d in dates}
            cur = dates[0]
            missing = []
            while cur <= dates[-1]:
                if cur not in date_set:
                    missing.append(cur)
                cur += dt.timedelta(days=1)
            if missing:
                rangebreaks.append(dict(values=[d.isoformat() for d in missing]))

        fig.update_xaxes(
            showspikes=True,
            spikemode="across",
            spikethickness=1,
            rangebreaks=rangebreaks,
            row=1,
            col=1,
        )
        fig.update_xaxes(rangebreaks=rangebreaks, row=2, col=1)
        fig.update_xaxes(rangebreaks=rangebreaks, row=3, col=1)

        return fig

    def _format_event_tooltip(
        self,
        pattern_name: str,
        event: Dict,
        record: Optional[Dict],
    ) -> str:
        """Muodosta tooltip-teksti kynttilä- ja tapahtumatiedoista."""

        def fmt(value: Optional[float]) -> str:
            return f"{value:.2f}" if isinstance(value, (int, float)) else "-"

        date_value = event.get("date")
        if isinstance(date_value, dt.date):
            date_str = date_value.strftime("%d.%m.%Y")
        else:
            date_str = str(date_value)

        strength = event.get("signal_strength")
        strength_str = fmt(strength)
        if strength is None:
            strength_str = "-"

        open_val = record.get("open") if record else None
        high_val = record.get("high") if record else None
        low_val = record.get("low") if record else None
        close_val = record.get("close") if record else None
        rsi_val = record.get("rsi") if record else None

        return (
            f"{pattern_name} ({date_str})<br>"
            f"Vahvuus: {strength_str}<br>"
            f"Open: {fmt(open_val)}<br>"
            f"High: {fmt(high_val)}<br>"
            f"Low: {fmt(low_val)}<br>"
            f"Close: {fmt(close_val)}<br>"
            f"RSI14: {fmt(rsi_val)}"
        )

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

        sma5 = record.get("sma5")
        record["sma5_y"] = (
            price_height - (sma5 - min_low) * price_scale
            if isinstance(sma5, (int, float))
            else None
        )
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

    price_shapes.extend(_build_sma_paths(valid, "sma5_y", "#D1D5DB"))
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
