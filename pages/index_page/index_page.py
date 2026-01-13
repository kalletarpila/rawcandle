from __future__ import annotations

import base64
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional

import flet as ft

from pages.index_page.index_calc import (
    compute_indices_incremental,
    ensure_index_table,
    fetch_index_series,
    fetch_stock_series,
    get_available_markets,
    get_sectors_for_market,
    get_tickers_for_market_sectors,
    introspect_schema,
    normalize_series_to_100,
    _connect,
)
from pages.index_page.index_plot import build_index_plot


class IndexPage:
    def __init__(self, page: ft.Page, appbar_factory: Callable[[], ft.AppBar], active_market: str):
        self.page = page
        self._appbar_factory = appbar_factory
        self.price_db = Path("data/osakedata.db")
        self.active_market = (active_market or "").strip().lower()

        self.market_dropdown: Optional[ft.Dropdown] = None
        self.sector_checkboxes: Dict[str, ft.Checkbox] = {}
        self.sector_column: Optional[ft.Column] = None
        self.stock_dropdown: Optional[ft.Dropdown] = None
        self.show_market_checkbox: Optional[ft.Checkbox] = None
        self.update_button: Optional[ft.ElevatedButton] = None
        self.status_text: Optional[ft.Text] = None
        self.chart_container: Optional[ft.Container] = None
        self.dow_text: Optional[ft.Text] = None

        self.schema_cache: Optional[Dict[str, str]] = None

    # ------------------ UI ------------------ #
    def create_view(self) -> ft.View:
        self.market_dropdown = ft.Dropdown(
            label="Markkina",
            width=200,
            options=[],
            on_change=self._on_market_change,
        )
        self._load_markets()

        self.sector_column = ft.Column(spacing=4)
        sector_card = ft.Card(
            content=ft.Container(
                padding=10,
                content=ft.Column(
                    [
                        ft.Text("Sektorit (max 2)", weight=ft.FontWeight.BOLD),
                        self.sector_column,
                    ],
                    spacing=8,
                ),
            )
        )

        self.stock_dropdown = ft.Dropdown(label="Osake (valinn.)", width=220, options=[])
        self.show_market_checkbox = ft.Checkbox(
            label="Näytä market-indeksi (vain näkymä)", value=False, on_change=self._on_toggle_market
        )
        self.update_button = ft.ElevatedButton(
            "Päivitä indeksit",
            icon=ft.Icons.UPDATE,
            on_click=self._on_update_click,
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
        )
        self.status_text = ft.Text("", color=ft.Colors.GREY_600)
        self.chart_container = ft.Container(
            height=620,
            bgcolor=ft.Colors.GREY_50,
            border_radius=10,
            padding=10,
            content=ft.Text("Valitse markkina/sektori ja päivitä indeksit.", color=ft.Colors.GREY_600),
        )
        self.dow_text = ft.Text("", color=ft.Colors.GREY_700)

        controls = ft.Column(
            [
                ft.Row(
                    [self.market_dropdown, self.stock_dropdown, self.show_market_checkbox, self.update_button],
                    alignment=ft.MainAxisAlignment.START,
                    wrap=True,
                ),
                sector_card,
                self.status_text,
            ],
            spacing=10,
        )

        view = ft.View(
            "/index",
            [
                self._appbar_factory(),
                ft.Container(
                    padding=15,
                    content=ft.Column(
                        [
                            ft.Text("Markkina- ja sektorindeksit", size=24, weight=ft.FontWeight.BOLD),
                            controls,
                            ft.Divider(height=10),
                            self.chart_container,
                            self.dow_text,
                        ],
                        spacing=12,
                    ),
                ),
            ],
        )
        self._refresh_sectors()
        self._refresh_stock_options()
        self._refresh_chart()
        return view

    # ------------------ Data helpers ------------------ #
    def _connect(self):
        return _connect(str(self.price_db))

    def _load_markets(self):
        try:
            with self._connect() as conn:
                self.schema_cache = introspect_schema(conn)
                ensure_index_table(conn)
                markets = get_available_markets(conn, self.schema_cache)
        except Exception:
            markets = []
        options = [ft.dropdown.Option(m) for m in markets]
        if self.market_dropdown:
            self.market_dropdown.options = options
            default = self.active_market or (options[0].key if options else None)
            self.market_dropdown.value = default
            self.active_market = (default or "").lower()

    def _refresh_sectors(self):
        market = self.active_market
        sectors = []
        try:
            with self._connect() as conn:
                schema = self.schema_cache or introspect_schema(conn)
                sectors = get_sectors_for_market(conn, schema, market) if market else []
        except Exception:
            sectors = []
        self.sector_checkboxes = {}
        rows = []
        for sec in sectors:
            cb = ft.Checkbox(label=sec, value=False, on_change=self._on_sector_toggle)
            self.sector_checkboxes[sec] = cb
            rows.append(cb)
        if self.sector_column:
            self.sector_column.controls = rows

    def _refresh_stock_options(self):
        market = self.active_market
        selected_sectors = self._selected_sectors()
        tickers = []
        try:
            with self._connect() as conn:
                schema = self.schema_cache or introspect_schema(conn)
                tickers = get_tickers_for_market_sectors(conn, schema, market, selected_sectors)
        except Exception:
            tickers = []
        if self.stock_dropdown:
            self.stock_dropdown.options = [ft.dropdown.Option(t) for t in tickers]
            if tickers:
                self.stock_dropdown.value = None

    def _selected_sectors(self) -> List[str]:
        return [sec for sec, cb in self.sector_checkboxes.items() if cb.value]

    # ------------------ Event handlers ------------------ #
    def _on_market_change(self, e):
        self.active_market = (self.market_dropdown.value or "").lower()
        self._refresh_sectors()
        self._refresh_stock_options()
        self._refresh_chart()
        self.page.update()

    def _on_sector_toggle(self, e):
        selected = self._selected_sectors()
        if len(selected) > 2:
            # perutaan uusin valinta
            for sec, cb in self.sector_checkboxes.items():
                if cb == e.control:
                    cb.value = False
                    break
            if self.status_text:
                self.status_text.value = "Max 2 sektoria."
                self.status_text.color = ft.Colors.ORANGE_700
        self._refresh_stock_options()
        self._refresh_chart()
        self.page.update()

    def _on_toggle_market(self, e):
        self._refresh_chart()
        self.page.update()

    def _set_status(self, text: str, color=ft.Colors.GREY_700):
        if self.status_text:
            self.status_text.value = text
            self.status_text.color = color
            try:
                self.status_text.update()
            except Exception:
                pass

    def _on_update_click(self, e):
        if not self.active_market:
            self._set_status("Valitse markkina", ft.Colors.RED_600)
            return
        sectors = self._selected_sectors()
        btn = self.update_button
        if btn:
            btn.disabled = True
            btn.update()
        if not sectors:
            self._set_status("🔄 Päivitetään market-indeksi...", ft.Colors.BLUE_600)
        else:
            self._set_status(f"🔄 Päivitetään market + {len(sectors)} sektoria...", ft.Colors.BLUE_600)

        def worker():
            try:
                with self._connect() as conn:
                    summary = compute_indices_incremental(
                        conn,
                        self.active_market,
                        sectors,
                        logger=lambda msg: print(msg),
                    )
                msg = f"✅ Päivitys valmis ({summary.get('updated_rows',0)} riviä)"
                color = ft.Colors.GREEN_600
            except Exception as exc:
                msg = f"❌ Virhe indeksipäivityksessä: {exc}"
                color = ft.Colors.RED_600
            finally:
                try:
                    if btn:
                        btn.disabled = False
                    self._set_status(msg, color)
                    self._refresh_chart()
                    self.page.update()
                except Exception:
                    pass

        threading.Thread(target=worker, daemon=True).start()

    # ------------------ Chart ------------------ #
    def _refresh_chart(self):
        market = self.active_market
        sectors = self._selected_sectors()
        include_market = bool(self.show_market_checkbox and self.show_market_checkbox.value)
        ticker = self.stock_dropdown.value if self.stock_dropdown else None
        if not market:
            return
        try:
            with self._connect() as conn:
                index_data = fetch_index_series(conn, market, sectors, include_market=include_market)
                volumes = {
                    key: [{"date": row["date"], "volume": row["volume"]} for row in series]
                    for key, series in index_data.items()
                }
                stock_series = None
                if ticker:
                    schema = self.schema_cache or introspect_schema(conn)
                    stock_series = normalize_series_to_100(
                        fetch_stock_series(conn, schema, ticker)
                    )
            if not index_data:
                self.chart_container.content = ft.Text(
                    "Ei indeksidataa. Päivitä indeksit ensin.",
                    color=ft.Colors.GREY_600,
                )
                self.chart_container.update()
                return
            fig, summaries = build_index_plot(index_data, volumes, stock_series=stock_series)
            html = fig.to_html(include_plotlyjs="cdn", full_html=False)
            data_url = "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode("utf-8")
            self.chart_container.content = ft.WebView(
                url=data_url,
                enable_javascript=True,
                height=620,
            )
            summary_texts = [f"{k}: {v}" for k, v in summaries.items()]
            self.dow_text.value = " | ".join(summary_texts)
            self.chart_container.update()
            self.dow_text.update()
        except Exception as exc:
            self.chart_container.content = ft.Text(f"Virhe ladattaessa graafia: {exc}", color=ft.Colors.RED_600)
            try:
                self.chart_container.update()
            except Exception:
                pass
