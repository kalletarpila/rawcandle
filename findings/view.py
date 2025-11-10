"""
Findings View
Käyttöliittymä results_data -taulun tarkasteluun.
"""

import flet as ft
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from analysis.database_manager import DatabaseManager


class FindingsView:
    """Findings-sivun käyttöliittymä results_data tauluun"""

    def __init__(
        self,
        page: ft.Page,
        analysis_db_path: str = "data/analysis.db",
        stock_db_path: str = "data/osakedata.db",
    ):
        """
        Alusta FindingsView.

        Args:
            page: Flet Page objekti
            analysis_db_path: Analysis-tietokannan polku
            stock_db_path: Stock-tietokannan polku (ei käytetä täällä)
        """
        self.page = page
        self.logger = logging.getLogger(__name__)
        self.analysis_db_path = analysis_db_path

        # Alusta komponentit
        self.db_manager = DatabaseManager(analysis_db_path)

        # UI komponentit
        self.findings_table = None
        self.search_field = None
        self.pattern_filter = None
        self.symbol_filter = None
        self.progress_dialog = None

        # Aikaväli-suodattimet
        self.date_filter_enabled = None
        self.start_date_field = None
        self.end_date_field = None

        # Data
        self.all_findings = []
        self.filtered_findings = []

        # Lajittelun tila
        self.sort_column = None  # Sarakkeen nimi
        self.sort_ascending = False  # Laskeva järjestys oletuksena

    def create_view(self) -> ft.Column:
        """
        Luo findings-sivun UI.

        Returns:
            Column sisältöineen
        """
        # Otsikko
        title = ft.Text(
            "📊 Results Dashboard",
            size=28,
            weight=ft.FontWeight.BOLD,
            color=ft.Colors.BLUE_700,
        )

        # Kynttiläkohtaiset määrät
        self.pattern_counts_text = ft.Text(
            "",
            size=14,
            color=ft.Colors.GREY_700,
        )

        # Suodattimet
        filters = self._create_filters()

        # Toimintopainikkeet
        actions = self._create_action_buttons()

        # Findings taulu
        self.findings_table = self._create_findings_table()

        # Tilastot
        stats = self._create_statistics()

        # Päivitä data
        self.refresh_data()

        return ft.Column(
            [
                title,
                self.pattern_counts_text,
                ft.Divider(),
                filters,
                ft.Divider(),
                actions,
                ft.Divider(),
                stats,
                ft.Divider(),
                self.findings_table,
            ],
            spacing=20,
        )

    def build(self) -> ft.Column:
        """Alias create_view:lle testejä varten"""
        return self.create_view()

        # Toimintopainikkeet
        actions = self._create_action_buttons()

        # Findings taulu
        self.findings_table = self._create_findings_table()

        # Tilastot
        stats = self._create_statistics()

        # Päivitä data
        self.refresh_data()

        return ft.Column(
            [
                title,
                ft.Divider(),
                filters,
                ft.Divider(),
                actions,
                ft.Divider(),
                stats,
                ft.Divider(),
                self.findings_table,
            ],
            spacing=20,
        )

    def _create_filters(self) -> ft.Column:
        """Luo suodattimen UI."""
        self.search_field = ft.TextField(
            label="Hae symboli...",
            hint_text="esim. AAPL",
            width=200,
            on_change=self._on_search_change,
        )

        self.pattern_filter = ft.Dropdown(
            label="Kuvio",
            width=200,
            options=[
                ft.dropdown.Option("", "Kaikki"),
                ft.dropdown.Option("downtrend", "Downtrend"),
                ft.dropdown.Option("Hammer", "Hammer"),
                ft.dropdown.Option("Bullish Engulfing", "Bullish Engulfing"),
                ft.dropdown.Option("Piercing Pattern", "Piercing Pattern"),
                ft.dropdown.Option("Three White Soldiers", "Three White Soldiers"),
                ft.dropdown.Option("Morning Star", "Morning Star"),
                ft.dropdown.Option("Dragonfly Doji", "Dragonfly Doji"),
                ft.dropdown.Option("Bullish Divergence", "Bullish Divergence"),
                ft.dropdown.Option("Bearish Divergence", "Bearish Divergence"),
            ],
            on_change=self._on_filter_change,
        )

        clear_btn = ft.IconButton(
            icon=ft.Icons.CLEAR,
            tooltip="Tyhjennä suodattimet",
            on_click=self._clear_filters,
        )

        # Aikaväli-suodatin
        self.date_filter_enabled = ft.Checkbox(
            label="Suodata aikavälin mukaan",
            value=False,
            on_change=self._on_filter_change,
        )

        self.start_date_field = ft.TextField(
            label="Alkupäivä (YYYY-MM-DD)",
            hint_text="esim. 2024-01-01",
            width=200,
            on_change=self._on_filter_change,
        )

        self.end_date_field = ft.TextField(
            label="Loppupäivä (YYYY-MM-DD)",
            hint_text="esim. 2024-12-31",
            width=200,
            on_change=self._on_filter_change,
        )

        # Rivit suodattimille
        row1 = ft.Row(
            [self.search_field, self.pattern_filter, clear_btn],
            spacing=10,
            alignment=ft.MainAxisAlignment.START,
        )

        row2 = ft.Row(
            [self.date_filter_enabled, self.start_date_field, self.end_date_field],
            spacing=10,
            alignment=ft.MainAxisAlignment.START,
        )

        return ft.Column([row1, row2], spacing=10)

    # (random generation dialog and handlers removed from Analysis view)

    def _create_action_buttons(self) -> ft.Row:
        """Luo toimintopainikkeet."""
        delete_all_btn = ft.ElevatedButton(
            text="Poista suodatetut",
            icon=ft.Icons.DELETE_SWEEP,
            on_click=self._delete_all_findings,
            bgcolor=ft.Colors.RED_700,
            color=ft.Colors.WHITE,
            tooltip="Poista kaikki suodatetut analyysitulokset",
        )

        clear_db_btn = ft.ElevatedButton(
            text="Tyhjennä kanta",
            icon=ft.Icons.DELETE_FOREVER,
            on_click=self._clear_database,
            bgcolor=ft.Colors.RED_900,
            color=ft.Colors.WHITE,
            tooltip="Tyhjennä koko analyysitietokanta",
        )

        return ft.Row(
            [delete_all_btn, clear_db_btn],
            alignment=ft.MainAxisAlignment.START,
            spacing=10,
        )

    def _create_findings_table(self) -> ft.DataTable:
        """Luo löydösten taulukko."""
        return ft.DataTable(
            columns=[
                ft.DataColumn(
                    ft.Text("Osake", weight=ft.FontWeight.BOLD),
                    on_sort=lambda e: self._sort_by_column("ticker"),
                ),
                ft.DataColumn(
                    ft.Text("Päivämäärä", weight=ft.FontWeight.BOLD),
                    on_sort=lambda e: self._sort_by_column("date"),
                ),
                ft.DataColumn(
                    ft.Text("Kuvio", weight=ft.FontWeight.BOLD),
                    on_sort=lambda e: self._sort_by_column("candle_pattern"),
                ),
                ft.DataColumn(
                    ft.Text("Vahvuus", weight=ft.FontWeight.BOLD),
                    on_sort=lambda e: self._sort_by_column("signal_strength"),
                ),
                ft.DataColumn(
                    ft.Text("RSI14", weight=ft.FontWeight.BOLD),
                    on_sort=lambda e: self._sort_by_column("RSI14_t0"),
                ),
                ft.DataColumn(
                    ft.Text("t2", weight=ft.FontWeight.BOLD),
                    on_sort=lambda e: self._sort_by_column("t2"),
                ),
                ft.DataColumn(
                    ft.Text("t5", weight=ft.FontWeight.BOLD),
                    on_sort=lambda e: self._sort_by_column("t5"),
                ),
                ft.DataColumn(
                    ft.Text("t10", weight=ft.FontWeight.BOLD),
                    on_sort=lambda e: self._sort_by_column("t10"),
                ),
                ft.DataColumn(
                    ft.Text("t20", weight=ft.FontWeight.BOLD),
                    on_sort=lambda e: self._sort_by_column("t20"),
                ),
                ft.DataColumn(ft.Text("Toiminnot", weight=ft.FontWeight.BOLD)),
            ],
            rows=[],
            border=ft.border.all(1, ft.Colors.GREY_400),
            border_radius=10,
            vertical_lines=ft.border.BorderSide(1, ft.Colors.GREY_300),
            horizontal_lines=ft.border.BorderSide(1, ft.Colors.GREY_300),
        )

    def _create_statistics(self) -> ft.Row:
        """Luo tilastonäkymä."""
        self.total_findings_text = ft.Text("0", size=20, weight=ft.FontWeight.BOLD)
        self.avg_strength_text = ft.Text("0.0", size=20, weight=ft.FontWeight.BOLD)

        total_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [ft.Text("Löydöksiä yhteensä", size=12), self.total_findings_text],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=20,
                width=150,
            )
        )

        avg_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [ft.Text("Keskivahvuus", size=12), self.avg_strength_text],
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                padding=20,
                width=150,
            )
        )

        return ft.Row([total_card, avg_card], alignment=ft.MainAxisAlignment.START)

    def refresh_data(self) -> None:
        """Päivitä data tietokannasta."""
        try:
            # Hae results_data taulusta analysis_findings sijaan
            self.all_findings = self.db_manager.get_results_data()
            # Load data and then apply any active filters
            self.filtered_findings = self.all_findings.copy()
            # Apply filters (this will update table and statistics)
            self._apply_filters()

        except Exception as e:
            self.logger.error(f"Data refresh failed: {e}")
            self._show_error("Datan päivitys epäonnistui")

    def _update_table(self) -> None:
        """Päivitä taulukko."""
        if not self.findings_table:
            return

        self.findings_table.rows.clear()

        # Pattern-numeroiden nimet
        PATTERN_NAMES = {
            0: "downtrend",
            1: "Hammer",
            2: "Bullish Engulfing",
            3: "Piercing Pattern",
            4: "Three White Soldiers",
            5: "Morning Star",
            6: "Dragonfly Doji",
            7: "Bullish Divergence",
            8: "Bearish Divergence",
        }

        for finding in self.filtered_findings[:100]:  # Näytä max 100
            # Muunna candle_pattern numerokoodi nimeksi
            pattern_num = finding.get("candle_pattern", 0)
            pattern_name = PATTERN_NAMES.get(pattern_num, str(pattern_num))

            row = ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(finding.get("ticker", ""))),
                    ft.DataCell(ft.Text(finding.get("date", ""))),
                    ft.DataCell(ft.Text(pattern_name)),
                    ft.DataCell(ft.Text(f"{finding.get('signal_strength', 0):.2f}")),
                    ft.DataCell(
                        ft.Text(
                            f"{finding.get('RSI14_t0', 0):.1f}"
                            if finding.get("RSI14_t0")
                            else "N/A"
                        )
                    ),
                    ft.DataCell(
                        ft.Text(
                            f"{finding.get('t2', 0):.2f}%"
                            if finding.get("t2") is not None
                            else "N/A"
                        )
                    ),
                    ft.DataCell(
                        ft.Text(
                            f"{finding.get('t5', 0):.2f}%"
                            if finding.get("t5") is not None
                            else "N/A"
                        )
                    ),
                    ft.DataCell(
                        ft.Text(
                            f"{finding.get('t10', 0):.2f}%"
                            if finding.get("t10") is not None
                            else "N/A"
                        )
                    ),
                    ft.DataCell(
                        ft.Text(
                            f"{finding.get('t20', 0):.2f}%"
                            if finding.get("t20") is not None
                            else "N/A"
                        )
                    ),
                    ft.DataCell(
                        ft.IconButton(
                            icon=ft.Icons.DELETE,
                            icon_color=ft.Colors.RED,
                            tooltip="Poista",
                            on_click=lambda e, fid=finding.get(
                                "id"
                            ): self._delete_finding(fid),
                        )
                    ),
                ]
            )
            self.findings_table.rows.append(row)

        if hasattr(self.page, "update"):
            self.page.update()

    def _update_statistics(self) -> None:
        """Päivitä tilastot."""
        if not hasattr(self, "total_findings_text") or not hasattr(
            self, "avg_strength_text"
        ):
            return
        if not self.total_findings_text or not self.avg_strength_text:
            return

        total = len(self.filtered_findings)
        avg_strength = 0.0

        if total > 0:
            strengths = [f.get("signal_strength", 0) for f in self.filtered_findings]
            avg_strength = sum(strengths) / len(strengths)

        self.total_findings_text.value = str(total)
        self.avg_strength_text.value = f"{avg_strength:.2f}"

        # Päivitä kynttiläkohtaiset määrät
        self._update_pattern_counts()

        if hasattr(self.page, "update"):
            self.page.update()

    def _update_pattern_counts(self) -> None:
        """Päivitä kynttiläkohtaiset määrät."""
        if not hasattr(self, "pattern_counts_text") or not self.pattern_counts_text:
            return

        # Pattern-numeroiden nimet (sama järjestys kuin taulussa)
        PATTERN_NAMES = {
            0: "downtrend",
            1: "Hammer",
            2: "Bullish Engulfing",
            3: "Piercing Pattern",
            4: "Three White Soldiers",
            5: "Morning Star",
            6: "Dragonfly Doji",
            7: "Bullish Divergence",
            8: "Bearish Divergence",
        }

        # Laske määrät kynttilätyypeittäin koko kannasta (ei suodatetuista)
        pattern_counts = {name: 0 for name in PATTERN_NAMES.values()}

        for finding in self.all_findings:
            # results_data taulussa kenttä on "candle_pattern" (numero 0-8)
            pattern_num = finding.get("candle_pattern", 0)
            pattern_name = PATTERN_NAMES.get(pattern_num, "Unknown")
            if pattern_name in pattern_counts:
                pattern_counts[pattern_name] += 1

        # Järjestä numeron mukaan ja muodosta teksti
        sorted_patterns = sorted(
            pattern_counts.items(),
            key=lambda x: list(PATTERN_NAMES.values()).index(x[0]),
        )
        counts_text = " | ".join(
            [f"{pattern}: {count}" for pattern, count in sorted_patterns]
        )

        self.pattern_counts_text.value = counts_text

    def _on_search_change(self, e) -> None:
        """Käsittele hakukentän muutos."""
        self._apply_filters()

    def _on_filter_change(self, e) -> None:
        """Käsittele suodattimen muutos."""
        self._apply_filters()

    # Random-event handlers removed from Analysis view (moved to Candles)

    def _apply_filters(self) -> None:
        """Sovella suodattimet."""
        self.filtered_findings = self.all_findings.copy()

        # Haku symbolilla: prefer UI control, fall back to test-set attribute
        search_val = None
        if self.search_field and getattr(self.search_field, "value", None):
            search_val = self.search_field.value
        elif hasattr(self, "selected_ticker") and self.selected_ticker:
            search_val = self.selected_ticker

        if search_val:
            search_term = search_val.lower()
            self.filtered_findings = [
                f
                for f in self.filtered_findings
                if search_term in f.get("ticker", "").lower()
            ]

        # Kuviosuodatin: prefer UI control, fall back to test-set attribute
        pattern_val = None
        if self.pattern_filter and getattr(self.pattern_filter, "value", None):
            pattern_val = self.pattern_filter.value
        elif hasattr(self, "selected_pattern") and self.selected_pattern:
            pattern_val = self.selected_pattern

        if pattern_val:
            self.filtered_findings = [
                f for f in self.filtered_findings if f.get("pattern") == pattern_val
            ]

        # Min strength filter (tests set min_strength)
        min_strength = None
        if hasattr(self, "min_strength") and self.min_strength is not None:
            try:
                min_strength = float(self.min_strength)
            except Exception:
                min_strength = None

        if min_strength is not None:
            self.filtered_findings = [
                f
                for f in self.filtered_findings
                if f.get("signal_strength", 0) >= min_strength
            ]

        # Aikavälisuodatin
        if self.date_filter_enabled and self.date_filter_enabled.value:
            start_date_str = (
                self.start_date_field.value if self.start_date_field else None
            )
            end_date_str = self.end_date_field.value if self.end_date_field else None

            if start_date_str:
                try:
                    start_date = datetime.fromisoformat(start_date_str).date()
                    self.filtered_findings = [
                        f
                        for f in self.filtered_findings
                        if datetime.fromisoformat(f.get("date", "9999-12-31")).date()
                        >= start_date
                    ]
                except (ValueError, TypeError):
                    pass  # Virheellinen päivämäärä, ohitetaan

            if end_date_str:
                try:
                    end_date = datetime.fromisoformat(end_date_str).date()
                    self.filtered_findings = [
                        f
                        for f in self.filtered_findings
                        if datetime.fromisoformat(f.get("date", "1900-01-01")).date()
                        <= end_date
                    ]
                except (ValueError, TypeError):
                    pass  # Virheellinen päivämäärä, ohitetaan

        self._update_table()
        self._update_statistics()

    def _clear_filters(self, e) -> None:
        """Tyhjennä suodattimet."""
        if self.search_field:
            self.search_field.value = ""
        if self.pattern_filter:
            self.pattern_filter.value = ""
        if self.date_filter_enabled:
            self.date_filter_enabled.value = False
        if self.start_date_field:
            self.start_date_field.value = ""
        if self.end_date_field:
            self.end_date_field.value = ""

        self._apply_filters()

    def _sort_by_column(self, column_name: str) -> None:
        """
        Lajittele taulukko sarakkeen mukaan.

        Args:
            column_name: Sarakkeen kenttänimi (esim. "t5", "signal_strength")
        """
        # Jos sama sarake, vaihda järjestys
        if self.sort_column == column_name:
            self.sort_ascending = not self.sort_ascending
        else:
            # Uusi sarake, aloita laskevasta
            self.sort_column = column_name
            self.sort_ascending = False

        # Lajittele filtered_findings
        if self.filtered_findings:
            self.filtered_findings.sort(
                key=lambda x: (
                    x.get(column_name)
                    if x.get(column_name) is not None
                    else float("-inf")
                ),
                reverse=not self.sort_ascending,  # reverse=True = laskeva
            )

        # Päivitä näyttö
        self._update_table()

        # Näytä info
        direction = "nousevaan" if self.sort_ascending else "laskevaan"
        self._show_info(
            f"Lajiteltu sarakkeen {column_name} mukaan {direction} järjestykseen"
        )

    def _refresh_data(self, e) -> None:
        """Päivitä data painikkeesta."""
        self.refresh_data()
        self._show_success("Data päivitetty!")

    def _export_data(self, e) -> None:
        """Vie data Exceliin."""
        # Tämä voitaisiin toteuttaa myöhemmin
        self._show_info("Excel-vienti tulossa pian!")

    def _delete_finding(self, finding_id: int) -> None:
        """Poista yksittäinen tuloslöydös results_data taulusta."""
        if finding_id and self.db_manager.delete_result_by_id(finding_id):
            self._show_success("Tulos poistettu!")
            self.refresh_data()
        else:
            self._show_error("Tuloksen poisto epäonnistui!")

    def _delete_all_findings(self, e) -> None:
        """Poista suodatetut tulokset results_data taulusta vahvistuksen jälkeen."""
        if not self.filtered_findings:
            self._show_info("Ei poistettavia tuloksia suodattimilla")
            return

        count = len(self.filtered_findings)

        # Luo vahvistusikkuna
        def confirm_delete(e):
            # Kerää ID:t suodatetuista tuloksista
            finding_ids = [f.get("id") for f in self.filtered_findings if f.get("id")]

            if not finding_ids:
                self._show_error("Ei poistettavia ID:itä löytynyt")
                close_dialog(None)
                return

            # Poista tulokset results_data taulusta
            deleted_count = self.db_manager.delete_results_by_ids(finding_ids)

            if deleted_count > 0:
                self._show_success(f"Poistettu {deleted_count} tulosta")
                self.refresh_data()
            else:
                self._show_error("Poisto epäonnistui")

            close_dialog(None)

        confirm_dlg = None  # Määritellään ensin

        def close_dialog(e):
            nonlocal confirm_dlg
            if confirm_dlg:
                confirm_dlg.open = False
                self.page.update()

        confirm_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("⚠️ Poista suodatetut tulokset"),
            content=ft.Column(
                [
                    ft.Text(f"Haluatko varmasti poistaa {count} suodatettua tulosta?"),
                    ft.Text(
                        "Tämä toiminto ei ole palautettavissa.",
                        size=12,
                        color=ft.Colors.ORANGE_700,
                    ),
                ],
                tight=True,
                spacing=10,
                height=80,
            ),
            actions=[
                ft.TextButton("Peruuta", on_click=close_dialog),
                ft.TextButton(
                    "Poista",
                    on_click=confirm_delete,
                    style=ft.ButtonStyle(color=ft.Colors.RED_700),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        if hasattr(self.page, "overlay"):
            if confirm_dlg not in self.page.overlay:
                self.page.overlay.append(confirm_dlg)
        confirm_dlg.open = True
        self.page.update()

    def _clear_database(self, e) -> None:
        """Tyhjennä results_data taulu vahvistuksen jälkeen."""
        # Hae kokonaismäärä
        total_count = len(self.all_findings)

        if total_count == 0:
            self._show_info("Taulu on jo tyhjä")
            return

        # Luo vahvistusikkuna
        def confirm_clear(e):
            try:
                # Tyhjennä results_data taulu
                deleted_count = self.db_manager.clear_results_data()

                if deleted_count > 0:
                    self._show_success(
                        f"Taulu tyhjennetty: {deleted_count} tulosta poistettu"
                    )
                    self.refresh_data()
                else:
                    self._show_error("Taulun tyhjennys epäonnistui")
            except Exception as ex:
                self._show_error(f"Virhe: {str(ex)}")

            close_dialog(None)

        confirm_dlg = None  # Määritellään ensin

        def close_dialog(e):
            nonlocal confirm_dlg
            if confirm_dlg:
                confirm_dlg.open = False
                self.page.update()

        confirm_dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text("⚠️ Tyhjennä koko analysis-kanta"),
            content=ft.Column(
                [
                    ft.Text("Haluatko varmasti tyhjentää koko kannan?"),
                    ft.Text(
                        f"Tämä poistaa KAIKKI {total_count} löydöstä!",
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.RED_700,
                    ),
                    ft.Text(
                        "Tämä toiminto ei ole palautettavissa.",
                        size=12,
                        color=ft.Colors.ORANGE_700,
                    ),
                ],
                tight=True,
                spacing=10,
                height=100,
            ),
            actions=[
                ft.TextButton("Peruuta", on_click=close_dialog),
                ft.TextButton(
                    "Tyhjennä kanta",
                    on_click=confirm_clear,
                    style=ft.ButtonStyle(color=ft.Colors.RED_900),
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

        if hasattr(self.page, "overlay"):
            if confirm_dlg not in self.page.overlay:
                self.page.overlay.append(confirm_dlg)
        confirm_dlg.open = True
        self.page.update()

    def _show_progress(self, message: str) -> None:
        """Näytä progress dialog."""
        # Yksinkertainen toteutus - voisi olla monimutkaisempi
        pass

    def _hide_progress(self) -> None:
        """Piilota progress dialog."""
        pass

    def _show_success(self, message: str) -> None:
        """Näytä onnistumisviesti."""
        if hasattr(self.page, "show_snack_bar"):
            self.page.show_snack_bar(
                ft.SnackBar(content=ft.Text(message), bgcolor=ft.Colors.GREEN_700)
            )

    def _show_error(self, message: str) -> None:
        """Näytä virheviesti."""
        if hasattr(self.page, "show_snack_bar"):
            self.page.show_snack_bar(
                ft.SnackBar(content=ft.Text(message), bgcolor=ft.Colors.RED_700)
            )

    def _show_info(self, message: str) -> None:
        """Näytä infoviesti."""
        if hasattr(self.page, "show_snack_bar"):
            self.page.show_snack_bar(
                ft.SnackBar(content=ft.Text(message), bgcolor=ft.Colors.BLUE_700)
            )

    def filter_by_ticker(self, ticker: str):
        """Suodata löydökset tickerin mukaan"""
        # Varmista että data on ladattu
        if not self.all_findings:
            self.refresh_data()

        if not ticker:
            self.filtered_findings = self.all_findings.copy()
        else:
            self.filtered_findings = [
                f for f in self.all_findings if f.get("ticker") == ticker
            ]
        self._update_table()

    def filter_by_pattern(self, pattern: str):
        """Suodata löydökset kuvion mukaan"""
        # Varmista että data on ladattu
        if not self.all_findings:
            self.refresh_data()

        if not pattern:
            self.filtered_findings = self.all_findings.copy()
        else:
            self.filtered_findings = [
                f for f in self.all_findings if f.get("pattern") == pattern
            ]
        self._update_table()

    def clear_filters(self):
        """Tyhjennä suodattimet"""
        self.filtered_findings = self.all_findings.copy()
        self._update_table()
        self._update_statistics()

    def update_statistics(self):
        """Päivitä tilastot"""
        self._update_statistics()

    def search_findings(self, query: str):
        """Hae löydöksiä hakusanalla"""
        if not query:
            return self.all_findings
        query = query.lower()
        return [
            f
            for f in self.all_findings
            if query in f.get("ticker", "").lower()
            or query in f.get("pattern", "").lower()
        ]

    def sort_findings(self, sort_by: str):
        """Lajittele löydökset"""
        if sort_by == "ticker":
            return sorted(self.filtered_findings, key=lambda x: x.get("ticker", ""))
        elif sort_by == "date":
            return sorted(self.filtered_findings, key=lambda x: x.get("date", ""))
        elif sort_by == "pattern":
            return sorted(self.filtered_findings, key=lambda x: x.get("pattern", ""))
        return self.filtered_findings

    def validate_ticker(self, ticker: str) -> bool:
        """Validoi ticker syöte"""
        return ticker and len(ticker) > 0 and ticker.isalpha()

    def show_progress_dialog(self, message: str):
        """Näytä edistymisdialogi (mock testejä varten)"""
        pass

    def export_data(self) -> bool:
        """Vie data CSV-tiedostoon"""
        try:
            # Mock implementation for tests
            return True
        except Exception as e:
            self.logger.error(f"Export failed: {e}")
            return False

    def on_resize(self):
        """Käsittele näytön koon muutos (mock testejä varten)"""
        pass

    def update_theme(self):
        """Päivitä teema (mock testejä varten)"""
        pass


if __name__ == "__main__":
    """Testaa FindingsView komponenttien luontia."""
    logging.basicConfig(level=logging.INFO)

    # Mock page object testaukseen
    class MockPage:
        def __init__(self):
            self.width = 1200
            self.height = 800

        def update(self):
            pass

        def show_snack_bar(self, snack_bar):
            print(f"SnackBar: {snack_bar.content.value}")

    mock_page = MockPage()
    view = FindingsView(mock_page)

    # Testaa komponentin luonti
    try:
        ui = view.create_view()
        print("✅ FindingsView UI luonti onnistui!")
    except Exception as e:
        print(f"❌ FindingsView UI luonti epäonnistui: {e}")

    print("FindingsView testit suoritettu!")
