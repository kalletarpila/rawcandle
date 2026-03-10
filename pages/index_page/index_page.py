from __future__ import annotations

import base64
import json
import threading
from pathlib import Path
import datetime as dt
from typing import Callable, Dict, List, Optional, Tuple

import flet as ft

from pages.index_page.index_calc import (
    compute_indices_incremental,
    ensure_index_table,
    ensure_ticker_metadata,
    fetch_index_series,
    fetch_stock_series,
    get_available_markets,
    get_sectors_for_market,
    introspect_schema,
    normalize_series_to_100,
    _connect,
)
from pages.index_page.index_plot import build_index_plot
from pages.index_page import trend_calc
from pages.index_page import trend_ui
from pages.index_page import trend_interpretation


class IndexPage:
    def __init__(
        self, page: ft.Page, appbar_factory: Callable[[], ft.AppBar], active_market: str
    ):
        self.page = page
        self._appbar_factory = appbar_factory
        self.price_db = Path("data/osakedata.db")
        self.active_market = (active_market or "").strip().lower()
        self.recent_file = Path("data/recent_tickers.json")
        self.RANGE_PRESETS = [
            ("1M", "1 kk"),
            ("3M", "3 kk"),
            ("6M", "6 kk"),
            ("1Y", "1 v"),
            ("ALL", "Kaikki"),
        ]
        self.selected_range = "6M"
        self.lookback_days = 15
        self.pivot_k = 2
        self.pivot_window = 3
        self.favorite_tickers = ["^NDX", "^GSPC", "^OMXH25", "^DJI", "^DJT"]
        self._recent_tickers: List[str] = self._load_recent_tickers()
        self.selected_stocks: List[str] = []

        self.market_dropdown: Optional[ft.Dropdown] = None
        self.sector_checkboxes: Dict[str, ft.Checkbox] = {}
        self.sector_column: Optional[ft.Column] = None
        self.stock_input: Optional[ft.TextField] = None
        self.show_market_checkbox: Optional[ft.Checkbox] = None
        self.normalize_checkbox: Optional[ft.Checkbox] = None
        self.update_button: Optional[ft.ElevatedButton] = None
        self.update_industry_button: Optional[ft.ElevatedButton] = None
        self.status_text: Optional[ft.Text] = None
        self.chart_container: Optional[ft.Container] = None
        self.dow_text: Optional[ft.Text] = None
        self.stock_meta_text: Optional[ft.Text] = None
        self.range_buttons: Dict[str, ft.ElevatedButton] = {}
        self.trend_table: Optional[ft.DataTable] = None
        self.trend_empty_text: Optional[ft.Text] = None
        self.lookback_field: Optional[ft.TextField] = None
        self.pivot_window_field: Optional[ft.TextField] = None
        self.pivot_k_dropdown: Optional[ft.Dropdown] = None
        self.trend_card_container: Optional[ft.Container] = None
        self.trend_snapshot_table: Optional[ft.DataTable] = None
        self.trend_chain_table: Optional[ft.DataTable] = None
        self.trend_interpretation_table: Optional[ft.DataTable] = None
        self._last_snapshot_sort: tuple[int, bool] | None = None
        self._last_chain_sort: tuple[int, bool] | None = None
        self.quick_fav_row: Optional[ft.Row] = None
        self.quick_recent_row: Optional[ft.Row] = None

        self.schema_cache: Optional[Dict[str, str]] = None
        self._initial_draw_scheduled = False

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
                        ft.Text("Sektorit (max 5)", weight=ft.FontWeight.BOLD),
                        self.sector_column,
                    ],
                    spacing=8,
                ),
            )
        )
        quicklinks_card = self._build_quicklinks_card()

        self.stock_input = ft.TextField(
            label="Osake (ticker, valinn.)",
            width=220,
            hint_text="Esim. AAPL",
            on_submit=self._on_stock_input_change,
        )
        self.show_market_checkbox = ft.Checkbox(
            label="Näytä market-indeksi", value=True, on_change=self._on_toggle_market
        )
        self.normalize_checkbox = ft.Checkbox(
            label="Normalisoi näkyvään aikajaksoon",
            value=False,
            on_change=self._on_toggle_normalization,
        )
        self.lookback_field = ft.TextField(
            label="Lookback (pv)",
            width=140,
            value=str(self.lookback_days),
            on_submit=self._on_lookback_change,
            tooltip=(
                "Kuinka monen viimeisen pörssipäivän hintaa käytetään trendin tunnistamiseen.\n"
                "Pieni arvo = herkempi, nopeampi reagointi\n"
                "Suuri arvo = vakaampi, pidempi trendi"
            ),
        )
        self.pivot_window_field = ft.TextField(
            label="Pivot window",
            width=140,
            value=str(self.pivot_window),
            on_submit=self._on_pivot_window_change,
            tooltip="Vaikuttaa graafiin ja trendiketjuihin. Snapshot käyttää hieman herkempiä pivotteja",
        )
        self.pivot_k_dropdown = ft.Dropdown(
            label="Pivot-herkkyys (k)",
            width=160,
            options=[ft.dropdown.Option(str(v)) for v in (2, 3, 4)],
            value=str(self.pivot_k),
            on_change=self._on_pivot_k_change,
            tooltip=(
                "Määrittää kuinka merkittävä huipun/pohjan pitää olla (k-arvo kertoo ikkunan aikavälin eli  t-k..t+k).\n"
                "Pieni arvo = herkkä, lyhyet muutokset näkyvät\n"
                "Suuri arvo = vahvempi, pidempi trendi"
            ),
        )
        self.update_button = ft.ElevatedButton(
            "Päivitä sektoreiden indeksit",
            icon=ft.Icons.UPDATE,
            on_click=self._on_update_click,
            bgcolor=ft.Colors.BLUE_600,
            color=ft.Colors.WHITE,
        )
        self.update_industry_button = ft.ElevatedButton(
            "Päivitä industryjen indeksit",
            icon=ft.Icons.UPDATE,
            on_click=self._on_update_industry_click,
            bgcolor=ft.Colors.GREY_200,
            color=ft.Colors.BLACK,
        )
        self.status_text = ft.Text("", color=ft.Colors.GREY_600)
        self.chart_container = ft.Container(
            height=620,
            bgcolor=ft.Colors.GREY_50,
            border_radius=10,
            padding=10,
            content=ft.Text(
                "Valitse markkina/sektori ja päivitä indeksit.",
                color=ft.Colors.GREY_600,
            ),
        )
        self.dow_text = ft.Text("", color=ft.Colors.GREY_700)

        controls = ft.Column(
            [
                ft.Row(
                    [
                        self.market_dropdown,
                        self.stock_input,
                        self.show_market_checkbox,
                        self.update_button,
                        self.update_industry_button,
                        self.lookback_field,
                        self.pivot_window_field,
                        self.pivot_k_dropdown,
                    ],
                    alignment=ft.MainAxisAlignment.START,
                    wrap=True,
                ),
                quicklinks_card,
                sector_card,
                ft.Row(
                    [self._build_range_buttons(), self.normalize_checkbox],
                    wrap=True,
                    spacing=8,
                ),
                self.status_text,
            ],
            spacing=10,
        )

        self.stock_meta_text = ft.Text("", color=ft.Colors.GREY_700)

        view = ft.View(
            "/index",
            [
                self._appbar_factory(),
                ft.Container(
                    padding=15,
                    content=ft.Column(
                        [
                            ft.Text(
                                "Markkina- ja sektorindeksit",
                                size=24,
                                weight=ft.FontWeight.BOLD,
                            ),
                            controls,
                            ft.Divider(height=10),
                            self.stock_meta_text,
                            self.chart_container,
                            self._build_trend_tabs_card(),
                            self.dow_text,
                        ],
                        spacing=12,
                    ),
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
        )
        self._refresh_sectors()
        # NOTE: do NOT call _refresh_chart() here; view is not mounted yet.
        if not self._initial_draw_scheduled:
            self._schedule_initial_draw()
            self._initial_draw_scheduled = True
        return view

    # ------------------ Data helpers ------------------ #
    def _connect(self):
        return _connect(str(self.price_db))

    def _load_markets(self):
        try:
            with self._connect() as conn:
                self.schema_cache = introspect_schema(conn)
                ensure_index_table(conn)
                ensure_ticker_metadata(conn, self.schema_cache)
                markets = get_available_markets(conn, self.schema_cache)
        except Exception:
            markets = []
            print("[INDEX] Failed to load markets", flush=True)
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
                ensure_ticker_metadata(conn, schema)
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
        return

    def _build_quicklinks_card(self) -> ft.Card:
        def _link_row(ticker: str) -> ft.Row:
            return ft.Row(
                [
                    ft.Checkbox(
                        value=ticker in self.selected_stocks,
                        on_change=lambda e, tk=ticker: self._on_toggle_stock(
                            tk, e.control.value
                        ),
                    ),
                    ft.Text(ticker, size=14),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )

        self.quick_fav_row = ft.Column(
            [_link_row(t) for t in self.favorite_tickers],
            spacing=6,
        )
        self.quick_recent_row = ft.Column(
            spacing=6,
        )
        self._refresh_recent_links()
        return ft.Card(
            content=ft.Container(
                padding=10,
                content=ft.Column(
                    [
                        ft.Text("Pikalinkit", weight=ft.FontWeight.BOLD),
                        ft.Row(
                            [
                                ft.Column(
                                    [
                                        ft.Text("Suositut:", weight=ft.FontWeight.BOLD),
                                        self.quick_fav_row,
                                    ],
                                    spacing=4,
                                    width=220,
                                ),
                                ft.Column(
                                    [
                                        ft.Text(
                                            "Viimeksi valitut:",
                                            weight=ft.FontWeight.BOLD,
                                        ),
                                        self.quick_recent_row,
                                    ],
                                    spacing=4,
                                    width=220,
                                ),
                            ],
                            spacing=12,
                        ),
                    ],
                    spacing=6,
                ),
            )
        )

    def _refresh_recent_links(self):
        if not self.quick_recent_row:
            return
        buttons = []
        for t in self._recent_tickers:
            buttons.append(
                ft.Row(
                    [
                        ft.Checkbox(
                            value=t in self.selected_stocks,
                            on_change=lambda e, ticker=t: self._on_toggle_stock(
                                ticker, e.control.value
                            ),
                        ),
                        ft.Text(t, size=14),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        if not buttons:
            buttons = [ft.Text("Ei historiatietoja", color=ft.Colors.GREY_600)]
        self.quick_recent_row.controls = buttons

    def _on_quick_select(self, ticker: str):
        if self.stock_input:
            self.stock_input.value = ticker
        self._on_stock_input_change(None)
        # quick select also toggles on if within limit
        self._on_toggle_stock(ticker, True)

    def _load_recent_tickers(self) -> List[str]:
        try:
            if self.recent_file.exists():
                data = json.loads(self.recent_file.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    return [
                        str(t).strip().upper()
                        for t in data
                        if isinstance(t, str) and str(t).strip()
                    ][:5]
        except Exception:
            pass
        return []

    def _save_recent_tickers(self):
        try:
            self.recent_file.parent.mkdir(parents=True, exist_ok=True)
            self.recent_file.write_text(
                json.dumps(self._recent_tickers), encoding="utf-8"
            )
        except Exception:
            pass

    def _add_recent_ticker(self, ticker: str):
        t = (ticker or "").strip().upper()
        if not t:
            return
        new_list = [t] + [x for x in self._recent_tickers if x != t]
        self._recent_tickers = new_list[:5]
        self._save_recent_tickers()
        self._refresh_recent_links()

    def _on_toggle_stock(self, ticker: str, show: bool):
        t = (ticker or "").strip().upper()
        if not t:
            return
        if show:
            if t in self.selected_stocks:
                self._add_recent_ticker(t)
                return
            if len(self.selected_stocks) >= 5:
                self._set_status("Max 5 osaketta kerrallaan", ft.Colors.ORANGE_700)
                return
            self.selected_stocks.append(t)
            self._add_recent_ticker(t)
        else:
            self.selected_stocks = [x for x in self.selected_stocks if x != t]
        self._refresh_recent_links()
        self._refresh_chart()
        try:
            self.page.update()
        except Exception:
            pass

    def _build_range_buttons(self) -> ft.Row:
        buttons = []
        self.range_buttons = {}
        for key, label in self.RANGE_PRESETS:
            btn = ft.ElevatedButton(
                label,
                on_click=lambda e, k=key: self._on_range_selected(k),
                disabled=(key == self.selected_range),
                bgcolor=(
                    ft.Colors.GREY_200
                    if key != self.selected_range
                    else ft.Colors.BLUE_200
                ),
                color=ft.Colors.BLACK,
            )
            self.range_buttons[key] = btn
            buttons.append(btn)
        return ft.Row(buttons, spacing=8, wrap=True)

    def _build_trend_tabs_card(self) -> ft.Container:
        # Placeholder; content replaced in _update_trend_tabs
        self.trend_snapshot_table = trend_ui.create_snapshot_table(
            on_sort=self._on_snapshot_sort
        )
        self.trend_chain_table = trend_ui.create_chain_table(
            on_sort=self._on_chain_sort
        )
        self.trend_interpretation_table = trend_ui.create_interpretation_table()
        placeholder_card = trend_ui.build_trend_card(
            self.trend_snapshot_table,
            self.trend_chain_table,
            self.trend_interpretation_table,
            self.lookback_days,
            self.pivot_k,
        )
        self.trend_card_container = ft.Container(content=placeholder_card)
        return self.trend_card_container

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
        if len(selected) > 5:
            # perutaan uusin valinta
            for sec, cb in self.sector_checkboxes.items():
                if cb == e.control:
                    cb.value = False
                    break
            if self.status_text:
                self.status_text.value = "Max 5 sektoria."
                self.status_text.color = ft.Colors.ORANGE_700
        self._refresh_stock_options()
        self._refresh_chart()
        self.page.update()

    def _on_toggle_market(self, e):
        self._refresh_chart()
        self.page.update()

    def _on_toggle_normalization(self, e):
        self._refresh_chart()
        try:
            self.page.update()
        except Exception:
            pass
        # On successful overlay, update recents
        try:
            if ticker and stock_series_overlay:
                self._add_recent_ticker(ticker)
        except Exception:
            pass

    def _set_status(self, text: str, color=ft.Colors.GREY_700):
        if self.status_text:
            self.status_text.value = text
            self.status_text.color = color
            try:
                self.status_text.update()
            except Exception:
                pass

    def _schedule_initial_draw(self):
        try:
            if hasattr(self.page, "run_task"):

                async def task():
                    self._refresh_chart()
                    try:
                        self.page.update()
                    except Exception:
                        pass

                self.page.run_task(task)
                return
        except Exception:
            pass
        try:
            self.page.call_later(
                0.1, lambda: (self._refresh_chart(), self.page.update())
            )
        except Exception:
            pass

    def _on_stock_input_change(self, e):
        # Normalize and refresh chart
        raw = (self.stock_input.value if self.stock_input else "") or ""
        tokens = [t.strip().upper() for t in raw.split(",") if t.strip()]
        added_any = False
        for tk in tokens:
            if tk in self.selected_stocks:
                continue
            if len(self.selected_stocks) >= 5:
                self._set_status("Max 5 osaketta kerrallaan", ft.Colors.ORANGE_700)
                break
            self.selected_stocks.append(tk)
            added_any = True
        if self.stock_input:
            # normalize field to comma-joined cleaned tokens
            self.stock_input.value = ", ".join(tokens)
        self._refresh_chart()
        try:
            self.page.update()
        except Exception:
            pass

    def _on_lookback_change(self, e):
        try:
            val = int(self.lookback_field.value or "0")
        except Exception:
            val = 15
        if val < 5:
            val = 5
        if val > 120:
            val = 120
        self.lookback_days = val
        self.lookback_field.value = str(val)
        # lighter: just refresh trends using latest data
        try:
            self._refresh_trends_last()
        except Exception:
            self._refresh_chart()
        try:
            self.page.update()
        except Exception:
            pass

    def _on_pivot_k_change(self, e):
        try:
            val = int(self.pivot_k_dropdown.value or "2")
        except Exception:
            val = 2
        if val not in (2, 3, 4):
            val = 2
        self.pivot_k = val
        self.pivot_k_dropdown.value = str(val)
        try:
            self._refresh_trends_last()
        except Exception:
            self._refresh_chart()
        try:
            self.page.update()
        except Exception:
            pass

    def _on_pivot_window_change(self, e):
        try:
            val = int(self.pivot_window_field.value or "3")
        except Exception:
            val = 5
        if val < 2:
            val = 2
        self.pivot_window = val
        self.pivot_window_field.value = str(val)
        try:
            self._refresh_chart()
        except Exception:
            pass
        try:
            self.page.update()
        except Exception:
            pass

    def _update_trend_tabs(self, snapshots, chains, interpretations):
        snap_rows = trend_ui.snapshot_rows(snapshots)
        chain_rows = trend_ui.chain_rows(chains)
        interp_rows = trend_ui.interpretation_rows(interpretations)
        # Rebuild tables to ensure headers/tooltips/sort are fresh
        self.trend_snapshot_table = trend_ui.create_snapshot_table(
            on_sort=self._on_snapshot_sort
        )
        self.trend_chain_table = trend_ui.create_chain_table(
            on_sort=self._on_chain_sort
        )
        self.trend_interpretation_table = trend_ui.create_interpretation_table()
        self.trend_snapshot_table.rows = snap_rows
        self.trend_chain_table.rows = chain_rows
        self.trend_interpretation_table.rows = interp_rows
        card = trend_ui.build_trend_card(
            self.trend_snapshot_table,
            self.trend_chain_table,
            self.trend_interpretation_table,
            self.lookback_days,
            self.pivot_k,
        )
        if not self.trend_card_container:
            self.trend_card_container = ft.Container()
        self.trend_card_container.content = card
        try:
            if self.page:
                self.page.update()
        except Exception:
            pass

    def _on_snapshot_sort(self, e: ft.DataTableSortEvent):
        try:
            col = e.column_index
            asc = e.ascending
            self._last_snapshot_sort = (col, asc)
            # rebuild rows with sort applied
            snap_rows = (
                self.trend_snapshot_table.rows if self.trend_snapshot_table else []
            )

            def sort_key(row: ft.DataRow):
                cells = row.cells
                val = cells[col].content.value if col < len(cells) else ""
                return val

            sorted_rows = sorted(snap_rows, key=sort_key, reverse=not asc)
            if self.trend_snapshot_table:
                self.trend_snapshot_table.sort_column_index = col
                self.trend_snapshot_table.sort_ascending = asc
                self.trend_snapshot_table.rows = sorted_rows
                self.trend_snapshot_table.update()
            if self.page:
                self.page.update()
        except Exception:
            pass

    def _on_chain_sort(self, e: ft.DataTableSortEvent):
        try:
            col = e.column_index
            asc = e.ascending
            self._last_chain_sort = (col, asc)
            chain_rows = (
                list(self.trend_chain_table.rows) if self.trend_chain_table else []
            )

            def sort_key(row: ft.DataRow):
                cells = row.cells
                val = cells[col].content.value if col < len(cells) else ""
                return val

            sorted_rows = sorted(chain_rows, key=sort_key, reverse=not asc)
            if self.trend_chain_table:
                self.trend_chain_table.sort_column_index = col
                self.trend_chain_table.sort_ascending = asc
                self.trend_chain_table.rows = sorted_rows
                self.trend_chain_table.update()
            if self.page:
                self.page.update()
        except Exception:
            pass

    def _fetch_stock_meta(self, ticker: str) -> tuple[Optional[str], Optional[str]]:
        try:
            with self._connect() as conn:
                # Try metadata table first
                try:
                    meta = conn.execute(
                        "SELECT sector, industry FROM ticker_meta WHERE ticker = ?",
                        (ticker,),
                    ).fetchone()
                    if meta:
                        sector_val = meta["sector"] or "ei löydetty"
                        industry_val = meta["industry"] or "ei löydetty"
                        return sector_val, industry_val
                except Exception:
                    pass
                # Fallback to osakedata if metadata missing
                schema = self.schema_cache or introspect_schema(conn)
                ticker_col = schema.get("ticker")
                sector_col = schema.get("sector")
                industry_col = schema.get("industry")
                if not (ticker_col and (sector_col or industry_col)):
                    return None, None
                cursor = conn.execute(
                    f"""
                    SELECT MAX({sector_col}) AS sector, MAX({industry_col}) AS industry
                    FROM osakedata
                    WHERE {ticker_col} = ?
                    """,
                    (ticker,),
                )
                row = cursor.fetchone()
                if not row:
                    return None, None
                sector_val = row["sector"] or "ei löydetty"
                industry_val = row["industry"] or "ei löydetty"
                return sector_val, industry_val
        except Exception:
            return None, None

    def _on_range_selected(self, key: str):
        if key not in {k for k, _ in self.RANGE_PRESETS}:
            return
        self.selected_range = key
        for k, btn in self.range_buttons.items():
            btn.disabled = k == key
            btn.bgcolor = ft.Colors.BLUE_200 if k == key else ft.Colors.GREY_200
        self._refresh_chart()
        try:
            self.page.update()
        except Exception:
            pass

    def _on_update_click(self, e):
        if not self.active_market:
            self._set_status("Valitse markkina", ft.Colors.RED_600)
            return
        sectors_selected = self._selected_sectors()
        try:
            with self._connect() as conn:
                schema = self.schema_cache or introspect_schema(conn)
                ensure_ticker_metadata(conn, schema)
                sectors_all = get_sectors_for_market(conn, schema, self.active_market)
        except Exception:
            sectors_all = []

        btn = self.update_button
        if btn:
            btn.disabled = True
            btn.update()
        if not sectors_selected:
            self._set_status(
                "🔄 Päivitetään market-indeksi + kaikki markkinan sektorit...",
                ft.Colors.BLUE_600,
            )
        else:
            self._set_status(
                f"🔄 Päivitetään market + {len(sectors_all)} sektoria (valittuja {len(sectors_selected)})...",
                ft.Colors.BLUE_600,
            )

        def worker():
            try:
                with self._connect() as conn:
                    summary = compute_indices_incremental(
                        conn,
                        self.active_market,
                        sectors_all,
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

    def _on_update_industry_click(self, e):
        if not self.active_market:
            self._set_status("Valitse markkina", ft.Colors.RED_600)
            return
        try:
            with self._connect() as conn:
                schema = self.schema_cache or introspect_schema(conn)
                ensure_ticker_metadata(conn, schema)
                sectors_all = get_sectors_for_market(conn, schema, self.active_market)
        except Exception:
            sectors_all = []

        btn = self.update_industry_button
        if btn:
            btn.disabled = True
            btn.update()
        self._set_status(
            "🔄 Päivitetään industry-indeksit (kaikki sektorit)...",
            ft.Colors.BLUE_600,
        )

        def worker():
            try:
                with self._connect() as conn:
                    summary = compute_indices_incremental(
                        conn,
                        self.active_market,
                        sectors_all,
                        logger=lambda msg: print(msg),
                        include_industries=True,
                    )
                msg = f"✅ Industry-indeksit päivitetty ({summary.get('updated_rows',0)} riviä)"
                color = ft.Colors.GREEN_600
            except Exception as exc:
                msg = f"❌ Virhe industry-päivityksessä: {exc}"
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
        include_market = bool(
            self.show_market_checkbox and self.show_market_checkbox.value
        )
        normalize_range = bool(
            self.normalize_checkbox and self.normalize_checkbox.value
        )
        ticker = (
            (self.stock_input.value or "").strip().upper() if self.stock_input else ""
        )
        selected_stocks = list(self.selected_stocks)
        if not market:
            return
        if (not sectors) and (not include_market) and (not selected_stocks):
            self.chart_container.content = ft.Text(
                "Valitse vähintään 1 sektori tai ruksaa 'Näytä market-indeksi'.",
                color=ft.Colors.GREY_600,
            )
            self._update_trend_tabs([], [], [])
            try:
                self.page.update()
            except Exception:
                pass
            return
        try:
            with self._connect() as conn:
                index_data_full = fetch_index_series(
                    conn, market, sectors, include_market=True
                )

                # Industry overlay for selected stocks
                industry_meta: List[Tuple[str, str]] = []
                industry_display: Dict[str, str] = {}
                industry_series_full: Dict[str, List[Dict]] = {}
                industry_vols_full: Dict[str, List[Dict]] = {}
                industry_counts: Dict[str, int] = {}

                # Stock series map for multiple overlays
                stock_series_raw_map: Dict[str, List[Dict]] = {}
                stock_series_overlay_map: Dict[str, List[Dict]] = {}
                stock_meta_map: Dict[str, Tuple[Optional[str], Optional[str]]] = {}

                if selected_stocks:
                    schema = self.schema_cache or introspect_schema(conn)
                    all_index_dates = [
                        row["date"]
                        for series in index_data_full.values()
                        for row in series
                    ]

                    def _to_iso(x):
                        try:
                            if isinstance(x, dt.date):
                                return x.isoformat()
                            return dt.date.fromisoformat(str(x)).isoformat()
                        except Exception:
                            return None

                    all_index_dates_iso = [
                        _to_iso(d) for d in all_index_dates if _to_iso(d)
                    ]
                    min_date = min(all_index_dates_iso) if all_index_dates_iso else None
                    max_date = max(all_index_dates_iso) if all_index_dates_iso else None
                    for tk in selected_stocks:
                        stock_rows = fetch_stock_series(
                            conn, schema, tk, date_from=min_date, date_to=max_date
                        )
                        if stock_rows:
                            stock_series_raw_map[tk] = stock_rows
                            stock_series_overlay_map[tk] = normalize_series_to_100(
                                stock_rows
                            )
                            stock_meta_map[tk] = self._fetch_stock_meta(tk)
                            meta = stock_meta_map.get(tk)
                            if meta:
                                sec = meta[0] or ""
                                ind = meta[1] or ""
                                if sec and ind:
                                    industry_meta.append((sec, ind))
                        else:
                            self._set_status(
                                f"Ticker {tk} ei löytynyt kannasta",
                                ft.Colors.ORANGE_700,
                            )

                # fetch industry series
                if industry_meta:
                    industry_meta_uniq = list({(s, i) for s, i in industry_meta})
                    for sec, ind in industry_meta_uniq:
                        rows_ind = conn.execute(
                            """
                            SELECT date, index_value, volume_sum, n_stocks
                            FROM index_daily
                            WHERE level='industry' AND market=? AND sector=? AND industry=?
                            ORDER BY date ASC
                            """,
                            (market, sec, ind),
                        ).fetchall()
                        if not rows_ind:
                            continue
                        key = f"INDUSTRY:{sec}:{ind}"
                        industry_series_full[key] = [
                            {"date": r["date"], "value": r["index_value"]}
                            for r in rows_ind
                        ]
                        industry_vols_full[key] = [
                            {"date": r["date"], "volume": r["volume_sum"] or 0.0}
                            for r in rows_ind
                        ]
                        latest = rows_ind[-1]
                        industry_counts[key] = latest["n_stocks"] or 0
                        industry_display[key] = (
                            f"Industry {ind} (n={industry_counts[key]})"
                        )

                # Range filter affects plot series; keep raw stock for trend calcs
                vols_full = {
                    key: [
                        {"date": row["date"], "volume": row.get("volume", 0.0)}
                        for row in series
                    ]
                    for key, series in index_data_full.items()
                }
                (
                    index_data_full,
                    vols_full,
                    stock_series_overlay_map,
                    industry_series_full,
                    industry_vols_full,
                ) = self._apply_range_filter(
                    index_data_full,
                    vols_full,
                    stock_series_overlay_map,
                    industry_series_full,
                    industry_vols_full,
                )

                # Prepare plotting data with checkbox respect
                index_data = dict(index_data_full)
                volumes = dict(vols_full)
                if industry_series_full:
                    index_data.update(industry_series_full)
                if industry_vols_full:
                    volumes.update(industry_vols_full)
                if not include_market and "MARKET" in index_data:
                    index_data.pop("MARKET", None)
                    volumes.pop("MARKET", None)

                if normalize_range:
                    index_data = {
                        k: normalize_series_to_100(v) for k, v in index_data.items()
                    }
                    if stock_series_overlay_map:
                        stock_series_overlay_map = {
                            k: normalize_series_to_100(v)
                            for k, v in stock_series_overlay_map.items()
                        }
                    if industry_series_full:
                        industry_series_full = {
                            k: normalize_series_to_100(v)
                            for k, v in industry_series_full.items()
                        }

            if not index_data:
                self.chart_container.content = ft.Text(
                    "Ei indeksidataa. Päivitä indeksit ensin.",
                    color=ft.Colors.GREY_600,
                )
                try:
                    self.page.update()
                except Exception:
                    pass
                return

            fig, summaries = build_index_plot(
                index_data,
                volumes,
                stock_series_map=(
                    stock_series_overlay_map if stock_series_overlay_map else None
                ),
                display_names=industry_display if industry_display else None,
                pivot_window=self.pivot_window,
            )
            html = fig.to_html(include_plotlyjs="cdn", full_html=False)
            data_url = "data:text/html;base64," + base64.b64encode(
                html.encode("utf-8")
            ).decode("utf-8")
            self.chart_container.content = ft.WebView(
                url=data_url,
                enable_javascript=True,
                height=620,
            )

            summary_texts = [f"{k}: {v}" for k, v in summaries.items()]
            stock_meta_parts = []
            if stock_series_overlay_map:
                for tk, meta in stock_meta_map.items():
                    sector_txt = (meta[0] if meta else None) or "ei löydetty"
                    industry_txt = (meta[1] if meta else None) or "ei löydetty"
                    stock_meta_parts.append(
                        f"{tk} | Sektori: {sector_txt} | Industry: {industry_txt}"
                    )
                summary_texts.extend(stock_meta_parts)

            self.dow_text.value = " | ".join(summary_texts)
            if self.stock_meta_text is not None:
                if stock_meta_parts:
                    self.stock_meta_text.value = " | ".join(stock_meta_parts)
                    self.stock_meta_text.visible = True
                else:
                    self.stock_meta_text.value = ""
                    self.stock_meta_text.visible = False
            # Remove any lingering summary text under tables
            self.dow_text.visible = False

            # pass full data + plotting data for trends so chains match visible pivots
            # Update recents for all successfully loaded stocks
            try:
                if stock_series_overlay_map:
                    for tk in stock_series_overlay_map.keys():
                        self._add_recent_ticker(tk)
            except Exception:
                pass

            self._refresh_trends(
                index_data_full,
                index_data,
                stock_series_overlay_map if stock_series_overlay_map else None,
                (
                    list(stock_series_overlay_map.keys())
                    if stock_series_overlay_map
                    else None
                ),
                stock_meta_map,
                industry_series_full if industry_series_full else None,
                industry_vols_full if industry_vols_full else None,
                industry_display if industry_display else None,
            )

            try:
                self.page.update()
            except Exception:
                pass

        except Exception as exc:
            self.chart_container.content = ft.Text(
                f"Virhe ladattaessa graafia: {exc}",
                color=ft.Colors.RED_600,
            )
            try:
                self.page.update()
            except Exception:
                pass

    def _refresh_trends(
        self,
        index_data_full: Dict[str, List[Dict]],
        index_data_plot: Dict[str, List[Dict]],
        stock_series_map: Optional[Dict[str, List[Dict]]],
        tickers: Optional[List[str]],
        stock_meta_map: Optional[Dict[str, Tuple[Optional[str], Optional[str]]]] = None,
        industry_series: Optional[Dict[str, List[Dict]]] = None,
        industry_volumes: Optional[Dict[str, List[Dict]]] = None,
        industry_display: Optional[Dict[str, str]] = None,
    ):
        # cache last datasets for lighter refresh on lookback/pivot changes
        self._last_trend_index_data_full = index_data_full
        self._last_trend_index_data_plot = index_data_plot
        self._last_trend_stock_series_map = stock_series_map
        self._last_trend_stock_tickers = tickers
        self._last_trend_stock_meta_map = stock_meta_map
        self._last_industry_series = industry_series
        lookback = self.lookback_days
        k = self.pivot_k
        pivot_window = self.pivot_window
        snapshots = []
        chains = []
        # market and sectors (plotted)
        for key, series in index_data_plot.items():
            otype = "MARKET" if key == "MARKET" else "SECTOR"
            oname = "MARKET" if key == "MARKET" else key
            snap = trend_calc.compute_snapshot(series, otype, oname, lookback, k)
            snapshots.append(snap)
            chain_lookback = len(series)
            chains.extend(
                trend_calc.compute_chains(
                    series, otype, oname, chain_lookback, pivot_window
                )
            )
        # Ensure market snapshot/chain even if not plotted but exists in full data
        if "MARKET" in index_data_full and not any(
            s.object_type == "MARKET" and s.object_name == "MARKET" for s in snapshots
        ):
            series = index_data_full["MARKET"]
            snap = trend_calc.compute_snapshot(series, "MARKET", "MARKET", lookback, k)
            snapshots.append(snap)
            chain_lookback = len(series)
            chains.extend(
                trend_calc.compute_chains(
                    series, "MARKET", "MARKET", chain_lookback, pivot_window
                )
            )
        if stock_series_map and tickers:
            for tk in tickers:
                series = stock_series_map.get(tk)
                if not series:
                    continue
                snap = trend_calc.compute_snapshot(series, "STOCK", tk, lookback, k)
                snapshots.append(snap)
                chain_lookback = len(series)
                chains.extend(
                    trend_calc.compute_chains(
                        series, "STOCK", tk, chain_lookback, pivot_window
                    )
                )
        # sort chains
        chains.sort(key=lambda c: (c.confidence, c.end_date), reverse=True)
        # plotted objects: market if exists in full, sectors from plotted data, stock if exists
        plotted_objects = []
        if "MARKET" in index_data_full:
            plotted_objects.append(("MARKET", "MARKET"))
        for key in index_data_plot.keys():
            if key == "MARKET":
                continue
            plotted_objects.append(("SECTOR", key))
        if stock_series_map and tickers:
            for tk in tickers:
                plotted_objects.append(("STOCK", tk))
        interpretations = trend_interpretation.build_interpretation_items(
            snapshots,
            chains,
            plotted_objects,
            stock_sector=(
                (stock_meta_map or {}).get(tickers[0], (None, None))[0]
                if tickers
                else None
            ),
        )
        # update UI
        self._update_trend_tabs(snapshots, chains, interpretations)

    def _refresh_trends_last(self):
        data_full = getattr(self, "_last_trend_index_data_full", None)
        data_plot = getattr(self, "_last_trend_index_data_plot", None)
        stock_map = getattr(self, "_last_trend_stock_series_map", None)
        tickers = getattr(self, "_last_trend_stock_tickers", None)
        stock_meta_map = getattr(self, "_last_trend_stock_meta_map", None)
        if data_full is None or data_plot is None:
            self._refresh_chart()
        else:
            self._refresh_trends(
                data_full, data_plot, stock_map, tickers, stock_meta_map
            )

    def _apply_range_filter(
        self,
        index_data: Dict[str, List[Dict]],
        volumes: Dict[str, List[Dict]],
        stock_series_map: Optional[Dict[str, List[Dict]]],
        extra_series: Optional[Dict[str, List[Dict]]] = None,
        extra_volumes: Optional[Dict[str, List[Dict]]] = None,
    ):
        def _to_date(val):
            if isinstance(val, dt.date):
                return val
            try:
                return dt.date.fromisoformat(str(val))
            except Exception:
                return None

        if self.selected_range == "ALL":
            return index_data, volumes, stock_series_map, extra_series, extra_volumes
        all_dates = [
            _to_date(row["date"]) for series in index_data.values() for row in series
        ]
        if not all_dates:
            return index_data, volumes, stock_series_map, extra_series, extra_volumes
        all_dates = [d for d in all_dates if d is not None]
        if not all_dates:
            return index_data, volumes, stock_series_map, extra_series, extra_volumes
        max_date = max(all_dates)
        days_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
        days = days_map.get(self.selected_range, 0)
        start_date = max_date - dt.timedelta(days=days)

        def filt(series):
            filtered = []
            for r in series:
                rd = _to_date(r["date"])
                if rd is None:
                    filtered.append(r)
                elif rd >= start_date:
                    filtered.append(r)
            return filtered

        filtered_index = {k: (filt(v) if filt(v) else v) for k, v in index_data.items()}
        filtered_volumes = {k: (filt(v) if filt(v) else v) for k, v in volumes.items()}

        filtered_stock_map = None
        if stock_series_map:
            filtered_stock_map = {}
            for tk, series in stock_series_map.items():
                filtered = []
                for r in series:
                    rd = _to_date(r["date"])
                    if rd is None or rd >= start_date:
                        filtered.append({**r, "date": rd or r["date"]})
                filtered_stock_map[tk] = filtered if filtered else series
        filtered_extra = None
        if extra_series:
            filtered_extra = {}
            for k, series in extra_series.items():
                filtered = []
                for r in series:
                    rd = _to_date(r["date"])
                    if rd is None or rd >= start_date:
                        filtered.append({**r, "date": rd or r["date"]})
                filtered_extra[k] = filtered if filtered else series
        filtered_extra_vol = None
        if extra_volumes:
            filtered_extra_vol = {}
            for k, series in extra_volumes.items():
                filtered = []
                for r in series:
                    rd = _to_date(r["date"])
                    if rd is None or rd >= start_date:
                        filtered.append({**r, "date": rd or r["date"]})
                filtered_extra_vol[k] = filtered if filtered else series

        return (
            filtered_index,
            filtered_volumes,
            filtered_stock_map,
            filtered_extra,
            filtered_extra_vol,
        )
