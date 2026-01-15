from __future__ import annotations

import base64
import threading
from pathlib import Path
import datetime as dt
from typing import Callable, Dict, List, Optional

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
from pages.index_page.index_trends import build_trend_chains_for_series


class IndexPage:
    def __init__(self, page: ft.Page, appbar_factory: Callable[[], ft.AppBar], active_market: str):
        self.page = page
        self._appbar_factory = appbar_factory
        self.price_db = Path("data/osakedata.db")
        self.active_market = (active_market or "").strip().lower()
        self.RANGE_PRESETS = [
            ("1M", "1 kk"),
            ("3M", "3 kk"),
            ("6M", "6 kk"),
            ("1Y", "1 v"),
            ("ALL", "Kaikki"),
        ]
        self.selected_range = "6M"

        self.market_dropdown: Optional[ft.Dropdown] = None
        self.sector_checkboxes: Dict[str, ft.Checkbox] = {}
        self.sector_column: Optional[ft.Column] = None
        self.stock_input: Optional[ft.TextField] = None
        self.show_market_checkbox: Optional[ft.Checkbox] = None
        self.normalize_checkbox: Optional[ft.Checkbox] = None
        self.update_button: Optional[ft.ElevatedButton] = None
        self.status_text: Optional[ft.Text] = None
        self.chart_container: Optional[ft.Container] = None
        self.dow_text: Optional[ft.Text] = None
        self.range_buttons: Dict[str, ft.ElevatedButton] = {}
        self.trend_table: Optional[ft.DataTable] = None
        self.trend_empty_text: Optional[ft.Text] = None
        self.trend_chains_cache: List[Dict] = []
        self.trend_sort_column: Optional[int] = None
        self.trend_sort_ascending: bool = False

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

        self.stock_input = ft.TextField(
            label="Osake (ticker, valinn.)",
            width=220,
            hint_text="Esim. AAPL",
            on_submit=self._on_stock_input_change,
            on_change=self._on_stock_input_change,
        )
        self.show_market_checkbox = ft.Checkbox(
            label="Näytä market-indeksi", value=True, on_change=self._on_toggle_market
        )
        self.normalize_checkbox = ft.Checkbox(
            label="Normalisoi näkyvään aikajaksoon",
            value=False,
            on_change=self._on_toggle_normalization,
        )
        self.update_button = ft.ElevatedButton(
            "Päivitä sektoreiden indeksit",
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
                    [self.market_dropdown, self.stock_input, self.show_market_checkbox, self.update_button],
                    alignment=ft.MainAxisAlignment.START,
                    wrap=True,
                ),
                sector_card,
                ft.Row([self._build_range_buttons(), self.normalize_checkbox], wrap=True, spacing=8),
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
                            self._build_trend_card(),
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

    def _build_range_buttons(self) -> ft.Row:
        buttons = []
        self.range_buttons = {}
        for key, label in self.RANGE_PRESETS:
            btn = ft.ElevatedButton(
                label,
                on_click=lambda e, k=key: self._on_range_selected(k),
                disabled=(key == self.selected_range),
                bgcolor=ft.Colors.GREY_200 if key != self.selected_range else ft.Colors.BLUE_200,
                color=ft.Colors.BLACK,
            )
            self.range_buttons[key] = btn
            buttons.append(btn)
        return ft.Row(buttons, spacing=8, wrap=True)

    def _build_trend_card(self) -> ft.Card:
        helper = ft.Text(
            "Kriteeri: vähintään 2 peräkkäistä HL–HH (nousu) tai LH–LL (lasku) -paria. Ketju alkaa aina HL/LH.",
            size=12,
            color=ft.Colors.GREY_700,
        )
        self.trend_empty_text = ft.Text("Ei vahvoja trendiketjuja nykyisellä näkymällä.", color=ft.Colors.GREY_600)
        self.trend_table = ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Objekti", weight=ft.FontWeight.BOLD), on_sort=self._on_trend_sort),
                ft.DataColumn(ft.Text("Nimi", weight=ft.FontWeight.BOLD), on_sort=self._on_trend_sort),
                ft.DataColumn(ft.Text("Suunta", weight=ft.FontWeight.BOLD), on_sort=self._on_trend_sort),
                ft.DataColumn(ft.Text("Alku", weight=ft.FontWeight.BOLD), on_sort=self._on_trend_sort),
                ft.DataColumn(ft.Text("Loppu", weight=ft.FontWeight.BOLD), on_sort=self._on_trend_sort),
                ft.DataColumn(ft.Text("Tapahtumia", weight=ft.FontWeight.BOLD), on_sort=self._on_trend_sort),
                ft.DataColumn(ft.Text("Pareja", weight=ft.FontWeight.BOLD), on_sort=self._on_trend_sort),
                ft.DataColumn(ft.Text("Confidence", weight=ft.FontWeight.BOLD), on_sort=self._on_trend_sort),
            ],
            rows=[],
            column_spacing=12,
            heading_row_color=ft.Colors.GREY_100,
        )
        content = ft.Column(
            [
                helper,
                ft.Container(
                    height=280,
                    content=ft.Column(
                        [
                            self.trend_empty_text,
                            self.trend_table,
                        ],
                        spacing=6,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                ),
            ],
            spacing=8,
        )
        return ft.Card(
            content=ft.Container(
                padding=12,
                content=ft.Column(
                    [
                        ft.Text("Vahvat trendiketjut", size=16, weight=ft.FontWeight.BOLD),
                        content,
                    ],
                    spacing=8,
                ),
            )
        )

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

    def _set_status(self, text: str, color=ft.Colors.GREY_700):
        if self.status_text:
            self.status_text.value = text
            self.status_text.color = color
            try:
                self.status_text.update()
            except Exception:
                pass

    def _schedule_initial_draw(self):
        def worker():
            import time

            time.sleep(0.1)
            self._refresh_chart()
            try:
                self.page.update()
            except Exception:
                pass

        threading.Thread(target=worker, daemon=True).start()

    def _on_stock_input_change(self, e):
        # Normalize and refresh chart
        if self.stock_input:
            self.stock_input.value = (self.stock_input.value or "").strip().upper()
        self._refresh_chart()
        try:
            self.page.update()
        except Exception:
            pass

    def _on_trend_sort(self, e: ft.DataTableSortEvent):
        try:
            self.trend_sort_column = e.column_index
            self.trend_sort_ascending = e.ascending
            if self.trend_table:
                self.trend_table.sort_column_index = e.column_index
                self.trend_table.sort_ascending = e.ascending
            self._update_trend_table(self.trend_chains_cache)
            try:
                self.page.update()
            except Exception:
                pass
        except Exception:
            pass

    def _update_trend_table(self, chains: List[Dict]):
        if not self.trend_table or not self.trend_empty_text:
            return
        self.trend_chains_cache = list(chains)
        if not chains:
            self.trend_table.rows = []
            self.trend_empty_text.visible = True
            return
        chains_to_render = self._sort_chains(chains)
        self.trend_empty_text.visible = False
        rows = []
        for chain in chains_to_render:
            rows.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(str(chain.get("object_type", "")))),
                        ft.DataCell(ft.Text(str(chain.get("object_name", "")))),
                        ft.DataCell(ft.Text(str(chain.get("direction", "")))),
                        ft.DataCell(ft.Text(str(chain.get("start_date", "")))),
                        ft.DataCell(ft.Text(str(chain.get("end_date", "")))),
                        ft.DataCell(ft.Text(str(chain.get("events_count", "")))),
                        ft.DataCell(ft.Text(str(chain.get("pairs_count", "")))),
                        ft.DataCell(ft.Text(str(chain.get("confidence", "")))),
                    ]
                )
            )
        self.trend_table.rows = rows

    def _sort_chains(self, chains: List[Dict]) -> List[Dict]:
        if self.trend_sort_column is None:
            return sorted(
                chains,
                key=lambda c: (c.get("confidence", 0), c.get("end_date")),
                reverse=True,
            )

        def sort_key(c: Dict):
            idx = self.trend_sort_column
            mapping = {
                0: c.get("object_type", ""),
                1: c.get("object_name", ""),
                2: c.get("direction", ""),
                3: c.get("start_date", ""),
                4: c.get("end_date", ""),
                5: c.get("events_count", 0),
                6: c.get("pairs_count", 0),
                7: c.get("confidence", 0),
            }
            val = mapping.get(idx, "")
            if isinstance(val, dt.date):
                return val
            # try parse date strings
            if isinstance(val, str):
                try:
                    return dt.date.fromisoformat(val)
                except Exception:
                    return val.lower()
            return val

        reverse = not self.trend_sort_ascending
        return sorted(chains, key=sort_key, reverse=reverse)

    def _fetch_stock_meta(self, ticker: str) -> tuple[Optional[str], Optional[str]]:
        try:
            with self._connect() as conn:
                # Try metadata table first
                try:
                    meta = conn.execute(
                        "SELECT sector, industry FROM ticker_meta WHERE ticker = ?", (ticker,)
                    ).fetchone()
                    if meta:
                        return meta["sector"], meta["industry"]
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
                return row["sector"], row["industry"]
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
            self._set_status("🔄 Päivitetään market-indeksi + kaikki markkinan sektorit...", ft.Colors.BLUE_600)
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

    # ------------------ Chart ------------------ #
    def _refresh_chart(self):
        market = self.active_market
        sectors = self._selected_sectors()
        include_market = bool(self.show_market_checkbox and self.show_market_checkbox.value)
        normalize_range = bool(self.normalize_checkbox and self.normalize_checkbox.value)
        ticker = (self.stock_input.value or "").strip().upper() if self.stock_input else ""
        if not market:
            return
        if (not sectors) and (not include_market):
            self.chart_container.content = ft.Text(
                "Valitse vähintään 1 sektori tai ruksaa 'Näytä market-indeksi'.",
                color=ft.Colors.GREY_600,
            )
            try:
                self.page.update()
            except Exception:
                pass
            return
        try:
            with self._connect() as conn:
                index_data = fetch_index_series(conn, market, sectors, include_market=include_market)
                volumes = {
                    key: [{"date": row["date"], "volume": row["volume"]} for row in series]
                    for key, series in index_data.items()
                }
                stock_series = None
                stock_sector = None
                stock_industry = None
                if ticker:
                    schema = self.schema_cache or introspect_schema(conn)
                    all_index_dates = [
                        row["date"] for series in index_data.values() for row in series
                    ]
                    min_date = min(all_index_dates).isoformat() if all_index_dates else None
                    max_date = max(all_index_dates).isoformat() if all_index_dates else None
                    stock_rows = fetch_stock_series(conn, schema, ticker, date_from=min_date, date_to=max_date)
                    if stock_rows:
                        stock_series = normalize_series_to_100(stock_rows)
                        stock_sector, stock_industry = self._fetch_stock_meta(ticker)
                    else:
                        stock_series = None
                        self._set_status(f"Ticker {ticker} ei löytynyt kannasta", ft.Colors.ORANGE_700)
                index_data, volumes, stock_series = self._apply_range_filter(index_data, volumes, stock_series)
                if normalize_range:
                    index_data = {k: normalize_series_to_100(v) for k, v in index_data.items()}
                    if stock_series:
                        stock_series = normalize_series_to_100(stock_series)
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
            fig, summaries = build_index_plot(index_data, volumes, stock_series=stock_series)
            html = fig.to_html(include_plotlyjs="cdn", full_html=False)
            data_url = "data:text/html;base64," + base64.b64encode(html.encode("utf-8")).decode("utf-8")
            self.chart_container.content = ft.WebView(
                url=data_url,
                enable_javascript=True,
                height=620,
            )
            summary_texts = [f"{k}: {v}" for k, v in summaries.items()]
            if stock_series:
                meta_parts = [ticker] if ticker else []
                try:
                    if stock_sector:
                        meta_parts.append(stock_sector)
                    if stock_industry:
                        meta_parts.append(stock_industry)
                except Exception:
                    pass
                if meta_parts:
                    summary_texts.append("Osake: " + " / ".join(meta_parts))
            self.dow_text.value = " | ".join(summary_texts)
            trend_chains = self._compute_trend_chains(index_data, stock_series, ticker if stock_series else None)
            self._update_trend_table(trend_chains)
            try:
                self.page.update()
            except Exception:
                pass
        except Exception as exc:
            self.chart_container.content = ft.Text(f"Virhe ladattaessa graafia: {exc}", color=ft.Colors.RED_600)
            try:
                self.page.update()
            except Exception:
                pass

    def _compute_trend_chains(self, index_data: Dict[str, List[Dict]], stock_series: Optional[List[Dict]], ticker: Optional[str]) -> List[Dict]:
        chains: List[Dict] = []
        # market
        for key, series in index_data.items():
            if key == "MARKET":
                chains.extend(build_trend_chains_for_series(series, "MARKET", "MARKET"))
            else:
                chains.extend(build_trend_chains_for_series(series, "SECTOR", key))
        if stock_series and ticker:
            chains.extend(build_trend_chains_for_series(stock_series, "STOCK", ticker))
        # sort by confidence desc, end_date desc
        chains.sort(key=lambda c: (c.get("confidence", 0), c.get("end_date")), reverse=True)
        return chains

    def _apply_range_filter(
        self,
        index_data: Dict[str, List[Dict]],
        volumes: Dict[str, List[Dict]],
        stock_series: Optional[List[Dict]],
    ):
        if self.selected_range == "ALL":
            return index_data, volumes, stock_series
        all_dates = [row["date"] for series in index_data.values() for row in series]
        if not all_dates:
            return index_data, volumes, stock_series
        max_date = max(all_dates)
        days_map = {"1M": 30, "3M": 90, "6M": 180, "1Y": 365}
        days = days_map.get(self.selected_range, 0)
        start_date = max_date - dt.timedelta(days=days)

        def filt(series):
            return [r for r in series if r["date"] >= start_date]

        filtered_index = {
            k: (filt(v) if filt(v) else v) for k, v in index_data.items()
        }
        filtered_volumes = {
            k: (filt(v) if filt(v) else v) for k, v in volumes.items()
        }
        filtered_stock = None
        if stock_series:
            filtered_stock = [r for r in stock_series if r["date"] >= start_date]
            if not filtered_stock:
                filtered_stock = stock_series
        return filtered_index, filtered_volumes, filtered_stock
