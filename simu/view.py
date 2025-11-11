import datetime
import re
from typing import Callable, Optional

import flet as ft

from . import config
from .engine import SimulationSettings
from .main import SimulationService
from .results import SimulationResult
from .utils import parse_ui_date


class SimuView:
    """Rakentaa ja hallinnoi simulaatio-välilehden käyttöliittymää."""

    def __init__(
        self,
        page: ft.Page,
        appbar_factory: Callable[[], ft.AppBar],
        service: SimulationService,
    ):
        self.page = page
        self._appbar_factory = appbar_factory
        self._service = service

        # Tallennetaan simulaation tulokset, jotta näkymä voidaan rakentaa uudelleen.
        self._results_data: list[SimulationResult] = []
        self.results_text: Optional[ft.Text] = None
        self._result_counter = 0

        # UI-komponenttien oletusviittaukset (asetetaan create_view-metodissa)
        self.ticker_field: Optional[ft.TextField] = None
        self.start_date_field: Optional[ft.TextField] = None
        self.end_date_field: Optional[ft.TextField] = None
        self.invest_amount_field: Optional[ft.TextField] = None
        self.investment_share_field: Optional[ft.TextField] = None
        self.drop_threshold_field: Optional[ft.TextField] = None
        self.rise_threshold_field: Optional[ft.TextField] = None
        self.strength_field: Optional[ft.TextField] = None
        self.rsi_field: Optional[ft.TextField] = None
        self.volume_growth_field: Optional[ft.TextField] = None
        self.pattern_checkboxes: list[ft.Checkbox] = []
        self.require_combo_checkbox: Optional[ft.Checkbox] = None
        self.combo_summary_text: Optional[ft.Text] = None
        self.start_button: Optional[ft.ElevatedButton] = None
        self.results_table: Optional[ft.DataTable] = None

    # ---- Julkinen API -------------------------------------------------

    def create_view(self) -> ft.View:
        """Palauttaa simulaatio-välilehden ft.View-rakenteena."""
        percent_filter = ft.InputFilter(r"[0-9,]", allow=True)
        int_filter = ft.InputFilter(r"[0-9]", allow=True)
        ticker_filter = ft.InputFilter(r"[A-Za-z0-9,\\s]", allow=True)
        date_filter = ft.InputFilter(r"[0-9.]", allow=True)

        self.ticker_field = ft.TextField(
            label="Osakkeen tickerit",
            multiline=True,
            min_lines=2,
            max_lines=4,
            hint_text="Esim. AAPL, MSFT tai yksi per rivi",
            helper_text="Erota pilkulla tai rivinvaihdolla.",
            input_filter=ticker_filter,
            expand=True,
        )
        self.ticker_field.on_change = (
            lambda e, fld=self.ticker_field: self._clear_error(fld)
        )

        self.start_date_field = ft.TextField(
            label="Aloituspäivä",
            value="1.1.2024",
            helper_text="Muoto dd.mm.yyyy.",
            input_filter=date_filter,
            expand=True,
        )
        self.start_date_field.on_change = (
            lambda e, fld=self.start_date_field: self._clear_error(fld)
        )
        self.start_date_field.on_blur = self._make_date_blur_handler(
            self.start_date_field, "01.01.2024"
        )

        self.end_date_field = ft.TextField(
            label="Lopetuspäivä",
            value="30.9.2025",
            helper_text="Muoto dd.mm.yyyy.",
            input_filter=date_filter,
            expand=True,
        )
        self.end_date_field.on_change = (
            lambda e, fld=self.end_date_field: self._clear_error(fld)
        )
        self.end_date_field.on_blur = self._make_date_blur_handler(
            self.end_date_field, "31.12.2024"
        )

        self.invest_amount_field = ft.TextField(
            label="Sijoitettava summa",
            value="100",
            helper_text="Anna kokonaisluku (1-100) – arvo tulkitaan tuhansina (100 → 100 000).",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=int_filter,
            expand=True,
        )
        self.invest_amount_field.on_change = (
            lambda e, fld=self.invest_amount_field: self._clear_error(fld)
        )
        self.invest_amount_field.on_blur = (
            lambda e, fld=self.invest_amount_field: self._clamp_integer_field(
                fld, 1, 100
            )
        )

        self.investment_share_field = ft.TextField(
            label="Kerralla sijoitettava osuus pääomasta",
            value="25",
            suffix_text="%",
            helper_text="Anna prosentti (1-100).",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=percent_filter,
            expand=True,
        )
        self.investment_share_field.on_change = (
            lambda e, fld=self.investment_share_field: self._normalize_decimal_comma(
                fld
            )
        )
        self.investment_share_field.on_blur = (
            lambda e, fld=self.investment_share_field: self._clamp_integer_field(
                fld, 1, 100
            )
        )

        self.drop_threshold_field = ft.TextField(
            label="Kurssilaskuraja",
            value="5",
            suffix_text="%",
            helper_text="Anna prosentti (1-100).",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=percent_filter,
            expand=True,
        )
        self.drop_threshold_field.on_change = (
            lambda e, fld=self.drop_threshold_field: self._normalize_decimal_comma(fld)
        )
        self.drop_threshold_field.on_blur = (
            lambda e, fld=self.drop_threshold_field: self._clamp_integer_field(
                fld, 1, 100
            )
        )

        self.drop_average_days_field = ft.TextField(
            label="Kurssialarajan keskiarvon päivät",
            value="5",
            helper_text="Kuinka monen edeltävän päivän keskiarvoa verrataan (1-60).",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=int_filter,
            expand=True,
        )
        self.drop_average_days_field.on_change = (
            lambda e, fld=self.drop_average_days_field: self._clear_error(fld)
        )
        self.drop_average_days_field.on_blur = (
            lambda e, fld=self.drop_average_days_field: self._clamp_integer_field(
                fld, 1, 60
            )
        )

        self.rise_threshold_field = ft.TextField(
            label="Kurssinousuraja",
            value="15",
            suffix_text="%",
            helper_text="Anna prosentti (1-100).",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=percent_filter,
            expand=True,
        )
        self.rise_threshold_field.on_change = (
            lambda e, fld=self.rise_threshold_field: self._normalize_decimal_comma(fld)
        )
        self.rise_threshold_field.on_blur = (
            lambda e, fld=self.rise_threshold_field: self._clamp_integer_field(
                fld, 1, 100
            )
        )

        self.strength_field = ft.TextField(
            label="Kynttilän vahvuus",
            value="0,8",
            helper_text="Anna luku väliltä 0,1 – 1,0 (pilkku desimaalina).",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=percent_filter,
            expand=True,
        )
        self.strength_field.on_change = (
            lambda e, fld=self.strength_field: self._normalize_decimal_comma(fld)
        )
        self.strength_field.on_blur = (
            lambda e, fld=self.strength_field: self._clamp_decimal_field(
                fld, 0.1, 1.0, decimals=1
            )
        )

        self.rsi_field = ft.TextField(
            label="RSI korkeintaan t0 päivänä",
            value="30",
            helper_text="Anna kokonaisluku (0-100).",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=int_filter,
            expand=True,
        )
        self.rsi_field.on_change = lambda e, fld=self.rsi_field: self._clear_error(fld)
        self.rsi_field.on_blur = (
            lambda e, fld=self.rsi_field: self._clamp_integer_field(fld, 0, 100)
        )

        self.volume_growth_field = ft.TextField(
            label="Volyymin kasvu t0",
            value="30",
            suffix_text="%",
            helper_text="Anna prosentti (1-100).",
            keyboard_type=ft.KeyboardType.NUMBER,
            input_filter=percent_filter,
            expand=True,
        )
        self.volume_growth_field.on_change = (
            lambda e, fld=self.volume_growth_field: self._normalize_decimal_comma(fld)
        )
        self.volume_growth_field.on_blur = (
            lambda e, fld=self.volume_growth_field: self._clamp_integer_field(
                fld, 1, 100
            )
        )

        inputs_column = ft.Column(
            [
                self.ticker_field,
                self.start_date_field,
                self.end_date_field,
                self.invest_amount_field,
                self.investment_share_field,
                self.drop_threshold_field,
                self.drop_average_days_field,
                self.rise_threshold_field,
                self.strength_field,
                self.rsi_field,
                self.volume_growth_field,
            ],
            spacing=12,
            tight=True,
        )

        self.pattern_checkboxes = []
        for definition in config.PATTERN_DEFINITIONS:
            cb = ft.Checkbox(
                label=definition.label,
                value=definition.key == "hammer",
                data=definition.key,
            )
            cb.on_change = self._on_pattern_checkbox_change
            self.pattern_checkboxes.append(cb)

        self.require_combo_checkbox = ft.Checkbox(
            label="Vain kynttilä + divergenssi",
            value=False,
            tooltip=(
                "Kauppa avataan vain jos valittu kynttiläkuvio (myös downtrend) "
                "ja divergenssi esiintyvät samana päivänä."
            ),
        )
        self.require_combo_checkbox.on_change = self._on_pattern_checkbox_change
        self.combo_summary_text = ft.Text(
            "",
            size=12,
            color=ft.Colors.BLUE_600,
            visible=False,
        )

        checkbox_column = ft.Column(
            [
                ft.Text(
                    "Valitse kynttiläkuviot",
                    size=16,
                    weight=ft.FontWeight.BOLD,
                ),
                ft.Column(self.pattern_checkboxes, spacing=6),
                self.require_combo_checkbox,
                self.combo_summary_text,
            ],
            spacing=12,
        )

        self.start_button = ft.ElevatedButton(
            "Aloita simulaatio",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self.on_start,
            bgcolor=ft.Colors.ORANGE_600,
            color=ft.Colors.WHITE,
            tooltip="Käynnistä simulaatio valituilla parametreilla",
        )

        # Batch-simulaatio nappi
        self.batch_button = ft.ElevatedButton(
            "Simuloi kaikki osakkeet",
            icon=ft.Icons.PLAYLIST_PLAY,
            on_click=self.on_batch_start,
            bgcolor=ft.Colors.BLUE_700,
            color=ft.Colors.WHITE,
            tooltip="Suorita simulaatio kaikille kannassa oleville osakkeille",
        )

        # Progressbar batch-simulaatiolle
        self.batch_progress_bar = ft.ProgressBar(visible=False, width=400)
        self.batch_progress_text = ft.Text(value="", visible=False)
        self.batch_cancel_button = ft.ElevatedButton(
            "Keskeytä",
            icon=ft.Icons.STOP,
            on_click=self.on_batch_cancel,
            bgcolor=ft.Colors.RED_700,
            color=ft.Colors.WHITE,
            visible=False,
            tooltip="Pysäytä käynnissä oleva batch-simulaatio",
        )
        self.trade_summary_text = ft.Text(
            value="",
            visible=False,
            color=ft.Colors.BLUE_600,
            size=13,
        )

        controls_row = ft.ResponsiveRow(
            controls=[
                ft.Container(
                    content=inputs_column,
                    padding=ft.padding.all(16),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=8,
                    col={"sm": 12, "md": 6},
                ),
                ft.Container(
                    content=ft.Column(
                        [
                            checkbox_column,
                            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                            self.start_button,
                            ft.Divider(height=5, color=ft.Colors.TRANSPARENT),
                            self.batch_button,
                            ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                            self.batch_progress_bar,
                            self.batch_progress_text,
                            self.batch_cancel_button,
                            self.trade_summary_text,
                        ],
                        spacing=16,
                        horizontal_alignment=ft.CrossAxisAlignment.START,
                    ),
                    padding=ft.padding.all(16),
                    bgcolor=ft.Colors.GREY_50,
                    border_radius=8,
                    col={"sm": 12, "md": 6},
                ),
            ],
            run_spacing=16,
            alignment=ft.MainAxisAlignment.START,
        )

        self.results_text = ft.Text(
            value="Ei simulaatiotuloksia vielä.",
            selectable=True,
            expand=True,
        )
        if self._results_data:
            self._update_results_view()

        results_card = ft.Card(
            content=ft.Container(
                content=ft.Column(
                    [
                        ft.Text(
                            "Simulaation tulokset",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            "Uudet rivit lisätään taulukon loppuun.",
                            color=ft.Colors.GREY_600,
                            size=13,
                        ),
                        ft.Container(content=self.results_text, expand=True),
                    ],
                    spacing=12,
                    expand=True,
                ),
                padding=20,
                expand=True,
            ),
            elevation=2,
        )

        view = ft.View(
            "/simu",
            [
                self._appbar_factory(),
                ft.Container(
                    content=ft.Column(
                        [
                            ft.Text(
                                "Simulaatio",
                                size=32,
                                weight=ft.FontWeight.BOLD,
                                color=ft.Colors.ORANGE_700,
                            ),
                            ft.Text(
                                "Määritä parametrit ja valitse kynttiläkuviot ennen simulaation käynnistämistä.",
                                size=15,
                                color=ft.Colors.GREY_600,
                            ),
                            controls_row,
                            results_card,
                        ],
                        spacing=24,
                        scroll=ft.ScrollMode.AUTO,
                        expand=True,
                    ),
                    padding=ft.padding.symmetric(horizontal=24, vertical=24),
                    expand=True,
                ),
            ],
            scroll=ft.ScrollMode.AUTO,
        )
        self._update_combo_summary()
        return view

    def append_result(
        self,
        stock_name: str,
        start_amount: str,
        end_amount: str,
        growth_pct: str,
        trades: str,
    ):
        """Julkinen rajapinta simulaatiolaskennan tulosten lisäämiselle."""
        self._append_result(stock_name, start_amount, end_amount, growth_pct, trades)

    # ---- Sisäiset apumetodit -----------------------------------------

    def on_start(self, e):
        """Käynnistää simulaation palvelun kautta."""
        valid, error_message = self._validate_inputs()
        if not valid:
            self._show_snack(
                error_message
                or "Korjaa virheelliset syötteet ennen simulaation käynnistämistä.",
                ft.Colors.RED_600,
            )
            return

        tickers = self._parse_tickers() or []
        if not tickers:
            self._show_snack("Anna vähintään yksi ticker.", ft.Colors.RED_600)
            return

        try:
            settings = self._build_settings()
        except ValueError as exc:
            self._show_snack(str(exc), ft.Colors.RED_600)
            return

        self._toggle_start_button(True)
        try:
            results_generated = False
            for result in self._service.run_for_tickers(tickers, settings):
                self._append_result(result)
                results_generated = True
            if results_generated:
                self._show_snack("Simulaatio valmis.", ft.Colors.GREEN_600)
            else:
                self._show_snack(
                    "Simulaatio ei tuottanut tuloksia.", ft.Colors.ORANGE_400
                )
        except Exception as exc:
            self._show_snack(f"Simulaatio epäonnistui: {exc}", ft.Colors.RED_600)
        finally:
            self._toggle_start_button(False)

    def _show_snack(self, message: str, color: str):
        try:
            if hasattr(self.page, "show_snack_bar"):
                self.page.show_snack_bar(
                    ft.SnackBar(
                        ft.Text(message),
                        bgcolor=color,
                    )
                )
        except Exception:
            pass

    def _toggle_start_button(self, disabled: bool) -> None:
        if self.start_button is None:
            return
        try:
            self.start_button.disabled = disabled
            self.start_button.update()
        except Exception:
            pass

    def _selected_patterns(self) -> list[str]:
        if not self.pattern_checkboxes:
            return []
        return [
            cb.data
            for cb in self.pattern_checkboxes
            if cb.value and isinstance(cb.data, str)
        ]

    def _on_pattern_checkbox_change(self, e):
        self._update_combo_summary()

    def _resolve_combo_tickers(
        self, settings: SimulationSettings
    ) -> Optional[list[str]]:
        """Palauta lista tickereistä joilla on combo-tapahtumia."""
        candle_keys = [
            key
            for key in settings.selected_patterns
            if key not in config.DIVERGENCE_KEYS
        ]
        if not candle_keys:
            return []
        candle_numbers = [
            config.PATTERN_KEY_TO_NUMBER.get(key)
            for key in candle_keys
            if key in config.PATTERN_KEY_TO_NUMBER
        ]
        candle_numbers = [num for num in candle_numbers if num is not None]
        if not candle_numbers:
            return []

        try:
            from analysis.database_manager import DatabaseManager

            db_mgr = DatabaseManager("data/analysis.db")
            combo_pairs = db_mgr.get_divergence_combo_pairs(
                candle_patterns=candle_numbers,
                start_date=settings.start_date.isoformat(),
                end_date=settings.end_date.isoformat(),
            )
            tickers = sorted({ticker for ticker, _ in combo_pairs})
            return tickers
        except Exception as exc:
            print(f"[SIMU][BATCH] Combo ticker lookup failed: {exc}")
            return []

    def _safe_parse_date(self, field: Optional[ft.TextField]) -> Optional[datetime.date]:
        if field is None:
            return None
        try:
            return parse_ui_date(field.value or "")
        except Exception:
            return None

    def _update_combo_summary(self):
        if not self.combo_summary_text:
            return

        text = self.combo_summary_text

        if not self.require_combo_checkbox or not self.require_combo_checkbox.value:
            text.value = ""
            text.visible = False
            self._refresh_combo_summary_text()
            return

        start_date = self._safe_parse_date(self.start_date_field)
        end_date = self._safe_parse_date(self.end_date_field)

        if start_date is None or end_date is None:
            text.value = "Anna kelvollinen aikaväli yhteenvetoon."
            text.visible = True
            self._refresh_combo_summary_text()
            return

        selected = self._selected_patterns()
        candle_keys = [key for key in selected if key not in config.DIVERGENCE_KEYS]
        divergence_keys = [key for key in selected if key in config.DIVERGENCE_KEYS]
        if not divergence_keys and self.require_combo_checkbox and self.require_combo_checkbox.value:
            # Ehkä valittiin vain kynttilä, lisätään toinen oletukseksi? Ei, anna varoitus ja näytä ohje
            text.value = "Valitse myös divergenssi (7/8) comboyhteenvedon näkemiseksi."
            text.visible = True
            self._refresh_combo_summary_text()
            return

        if not candle_keys or not divergence_keys:
            text.value = "Valitse sekä kynttiläkuvio että divergenssi yhteenvetoa varten."
            text.visible = True
            self._refresh_combo_summary_text()
            return

        candle_numbers = [
            config.PATTERN_KEY_TO_NUMBER.get(key) for key in candle_keys
        ]
        candle_numbers = [num for num in candle_numbers if num is not None]
        if not candle_numbers:
            text.value = "Kynttiläkuvioille ei löytynyt numeroarvoa."
            text.visible = True
            self._refresh_combo_summary_text()
            return

        try:
            from analysis.database_manager import DatabaseManager

            db_mgr = DatabaseManager("data/analysis.db")
            combo_pairs = db_mgr.get_divergence_combo_pairs(
                candle_patterns=candle_numbers,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
        except Exception as exc:
            text.value = f"Combo-yhteenveto epäonnistui: {exc}"
            text.visible = True
            self._refresh_combo_summary_text()
            return

        ticker_count = len({ticker for ticker, _ in combo_pairs})
        total_days = len(combo_pairs)
        text.value = (
            f"Kombot: {ticker_count} osaketta / {total_days} t0-päivää "
            f"({start_date.strftime('%d.%m.%Y')} – {end_date.strftime('%d.%m.%Y')}). "
            "Divergenssi huomioidaan ikkunoissa t0…t-3."
        )
        text.visible = True
        self._refresh_combo_summary_text()

    def _refresh_combo_summary_text(self):
        try:
            if self.combo_summary_text:
                self.combo_summary_text.update()
            if self.page:
                self.page.update()
        except Exception:
            pass

    def _parse_float_value(self, field: Optional[ft.TextField]) -> float:
        if field is None:
            raise ValueError("Arvo puuttuu")
        raw = (field.value or "").strip().replace(" ", "").replace(",", ".")
        if not raw:
            raise ValueError("Arvo puuttuu")
        return float(raw)

    def _build_settings(self) -> SimulationSettings:
        if (
            self.start_date_field is None
            or self.end_date_field is None
            or self.invest_amount_field is None
            or self.investment_share_field is None
            or self.drop_threshold_field is None
            or self.rise_threshold_field is None
            or self.strength_field is None
            or self.rsi_field is None
            or self.volume_growth_field is None
        ):
            raise ValueError("Käyttöliittymän kentät eivät ole käytettävissä.")

        start_date = parse_ui_date(self.start_date_field.value or "")
        end_date = parse_ui_date(self.end_date_field.value or "")
        invest_amount = int(self._parse_float_value(self.invest_amount_field))
        invest_percent = self._parse_float_value(self.investment_share_field)
        drop_percent = self._parse_float_value(self.drop_threshold_field)
        drop_avg_days = int(self._parse_float_value(self.drop_average_days_field))
        rise_percent = self._parse_float_value(self.rise_threshold_field)
        min_strength = self._parse_float_value(self.strength_field)
        max_rsi = self._parse_float_value(self.rsi_field)
        min_volume_growth = self._parse_float_value(self.volume_growth_field)

        return SimulationSettings(
            start_date=start_date,
            end_date=end_date,
            capital_thousands=invest_amount,
            invest_percent=invest_percent,
            drop_percent=drop_percent,
            drop_average_days=drop_avg_days,
            rise_percent=rise_percent,
            min_strength=min_strength,
            max_rsi=max_rsi,
            min_volume_growth=min_volume_growth,
            selected_patterns=self._selected_patterns(),
            require_divergence_combo=bool(
                self.require_combo_checkbox and self.require_combo_checkbox.value
            ),
        )

    def _update_results_view(self):
        if self.results_text is None:
            print("[SIMU][UI] results_text missing, skipping update")
            return
        print("[SIMU][UI] refreshing results", len(self._results_data))
        if not self._results_data:
            self.results_text.value = "Ei simulaatiotuloksia vielä."
        else:
            lines = []
            for idx, result in enumerate(self._results_data, start=1):
                lines.append(
                    " | ".join(
                        [
                            f"{idx}. {result.ticker}",
                            f"Aloitus (kassa): {result.start_capital:,.2f}",
                            f"Kassa nyt: {result.end_cash:,.2f}",
                            f"Osakkeiden arvo: {result.end_position_value:,.2f}",
                            f"Yhteensä: {result.end_capital:,.2f}",
                            f"Kasvu: {result.growth_pct:.2f} %",
                            f"Ostoja: {result.buy_trades}",
                        ]
                    )
                )
            self.results_text.value = "\n".join(lines)
        try:
            self.results_text.update()
        except Exception as exc:
            print("[SIMU][UI][TEXT] update failed", exc)
        if getattr(self.page, "update", None):
            try:
                self.page.update()
            except Exception as exc:
                print("[SIMU][UI][PAGE] update failed", exc)

    def _clear_error(self, field: Optional[ft.TextField]):
        if field is None:
            return
        if getattr(field, "error_text", None):
            field.error_text = None
            try:
                field.update()
            except Exception:
                pass

    def _set_error(self, field: Optional[ft.TextField], message: str):
        if field is None:
            return
        field.error_text = message
        try:
            field.update()
        except Exception:
            pass

    def _normalize_decimal_comma(self, field: Optional[ft.TextField]):
        if field is None:
            return
        try:
            raw = (field.value or "").strip()
            if not raw:
                self._clear_error(field)
                return
            raw = raw.replace(".", ",")
            if raw.count(",") > 1:
                parts = raw.split(",")
                raw = parts[0] + "," + "".join(parts[1:]).replace(",", "")
                self._set_error(
                    field,
                    "Liian monta pilkkua – ylimääräiset poistettiin.",
                )
            else:
                self._clear_error(field)
            field.value = raw
            field.update()
        except Exception:
            self._set_error(field, "Syötteen muotoilu epäonnistui.")

    def _clamp_integer_field(
        self, field: Optional[ft.TextField], minimum: int, maximum: int
    ):
        if field is None:
            return
        try:
            raw = (field.value or "").strip()
            if not raw:
                self._set_error(
                    field, f"Kenttä ei voi olla tyhjä. Oletusarvo {minimum} asetettu."
                )
                value = minimum
            else:
                normalized = raw.replace(" ", "").replace(",", ".")
                value_float = float(normalized)
                if not value_float.is_integer():
                    self._set_error(
                        field,
                        "Syötä kokonaisluku ilman desimaaleja. Pyöristettiin lähimpään kokonaislukuun.",
                    )
                value = int(round(value_float))
                if value < minimum or value > maximum:
                    clamped = max(minimum, min(maximum, value))
                    if value != clamped:
                        self._set_error(
                            field,
                            f"Arvon tulee olla välillä {minimum}–{maximum}. "
                            f"Korjattu arvoon {clamped}.",
                        )
                    value = clamped
                else:
                    self._clear_error(field)
            field.value = str(value)
            field.update()
        except Exception:
            self._set_error(
                field, "Syötä kelvollinen kokonaisluku. Käytettiin oletusarvoa."
            )
            field.value = str(minimum)
            try:
                field.update()
            except Exception:
                pass

    def _clamp_decimal_field(
        self,
        field: Optional[ft.TextField],
        minimum: float,
        maximum: float,
        decimals: int = 1,
    ):
        if field is None:
            return
        try:
            raw = (field.value or "").strip()
            if not raw:
                self._set_error(
                    field, f"Kenttä ei voi olla tyhjä. Oletusarvo {minimum} asetettu."
                )
                value = minimum
            else:
                normalized = raw.replace(" ", "").replace(",", ".")
                value = float(normalized)
                if value < minimum or value > maximum:
                    clamped = max(minimum, min(maximum, value))
                    if value != clamped:
                        self._set_error(
                            field,
                            f"Arvon tulee olla välillä {minimum}–{maximum}. "
                            f"Korjattu arvoon {clamped:.{decimals}f}.",
                        )
                    value = clamped
                else:
                    self._clear_error(field)
            formatted = f"{value:.{decimals}f}".replace(".", ",")
            field.value = formatted
            field.update()
        except Exception:
            formatted = f"{minimum:.{decimals}f}".replace(".", ",")
            self._set_error(
                field, "Syötä kelvollinen desimaaliluku. Käytettiin oletusarvoa."
            )
            field.value = formatted
            try:
                field.update()
            except Exception:
                pass

    def _sanitize_date_field(
        self, field: Optional[ft.TextField], default_value: str, fmt: str = "%d.%m.%Y"
    ):
        if field is None:
            return
        try:
            raw = (field.value or "").strip()
            if not raw:
                self._set_error(
                    field,
                    f"Anna päivämäärä muodossa pp.kk.vvvv. "
                    f"Oletusarvo {default_value} asetettu.",
                )
                field.value = default_value
            else:
                parsed = datetime.datetime.strptime(raw, fmt)
                field.value = parsed.strftime(fmt)
                self._clear_error(field)
            field.update()
        except Exception:
            self._set_error(field, "Anna päivämäärä muodossa pp.kk.vvvv.")
        finally:
            self._update_combo_summary()

    def _make_date_blur_handler(self, field: Optional[ft.TextField], default_value: str):
        def handler(e):
            self._sanitize_date_field(field, default_value)

        return handler

    def _parse_tickers(self) -> Optional[list[str]]:
        if self.ticker_field is None:
            return None
        raw = (self.ticker_field.value or "").strip()
        if not raw:
            self._set_error(self.ticker_field, "Anna vähintään yksi ticker.")
            return None
        tokens = [
            token.strip().upper() for token in re.split(r"[,\n]", raw) if token.strip()
        ]
        if not tokens:
            self._set_error(self.ticker_field, "Anna vähintään yksi ticker.")
            return None
        invalid = [t for t in tokens if not re.fullmatch(r"[A-Z0-9.-]{1,12}", t)]
        if invalid:
            self._set_error(
                self.ticker_field,
                "Tickerit voivat sisältää vain kirjaimia, numeroita sekä .-merkkejä.",
            )
            return None
        self._clear_error(self.ticker_field)
        return tokens

    def _validate_int_input(
        self,
        field: Optional[ft.TextField],
        minimum: int,
        maximum: int,
        label: str,
    ) -> Optional[int]:
        if field is None:
            return None
        raw = (field.value or "").strip()
        if not raw:
            self._set_error(field, f"{label} on pakollinen.")
            return None
        try:
            normalized = raw.replace(" ", "").replace(",", ".")
            value_float = float(normalized)
        except Exception:
            self._set_error(
                field, f"{label}: syötä kokonaisluku väliltä {minimum}–{maximum}."
            )
            return None
        if not value_float.is_integer():
            self._set_error(field, f"{label}: käytä kokonaislukua ilman desimaaleja.")
            return None
        value = int(value_float)
        if value < minimum or value > maximum:
            self._set_error(
                field, f"{label}: arvo täytyy olla välillä {minimum}–{maximum}."
            )
            return None
        field.value = str(value)
        self._clear_error(field)
        return value

    def _validate_decimal_input(
        self,
        field: Optional[ft.TextField],
        minimum: float,
        maximum: float,
        label: str,
        decimals: int = 1,
    ) -> Optional[float]:
        if field is None:
            return None
        raw = (field.value or "").strip()
        if not raw:
            self._set_error(field, f"{label} on pakollinen.")
            return None
        try:
            normalized = raw.replace(" ", "").replace(",", ".")
            value = float(normalized)
        except Exception:
            self._set_error(
                field, f"{label}: syötä desimaaliluku pilkulla (esim. 0,8)."
            )
            return None
        if value < minimum or value > maximum:
            self._set_error(
                field,
                f"{label}: arvo täytyy olla välillä {minimum:.1f}–{maximum:.1f}.",
            )
            return None
        formatted = f"{value:.{decimals}f}".replace(".", ",")
        field.value = formatted
        self._clear_error(field)
        return value

    def _validate_date_input(
        self, field: Optional[ft.TextField], label: str, fmt: str = "%d.%m.%Y"
    ) -> Optional[datetime.date]:
        if field is None:
            return None
        raw = (field.value or "").strip()
        if not raw:
            self._set_error(field, f"{label} on pakollinen.")
            return None
        try:
            parsed = datetime.datetime.strptime(raw, fmt).date()
        except Exception:
            self._set_error(field, f"{label}: anna päivämäärä muodossa pp.kk.vvvv.")
            return None
        field.value = parsed.strftime(fmt)
        self._clear_error(field)
        return parsed

    def _validate_inputs(self) -> tuple[bool, Optional[str]]:
        valid = True
        error_message: Optional[str] = None
        tickers = self._parse_tickers()
        if tickers is None:
            valid = False
            error_message = error_message or "Ticker-syötteessä on virheitä."

        start_date = self._validate_date_input(self.start_date_field, "Aloituspäivä")
        end_date = self._validate_date_input(self.end_date_field, "Lopetuspäivä")
        if start_date and end_date and start_date > end_date:
            err = "Aloituspäivän tulee olla aikaisempi tai sama kuin lopetuspäivän."
            self._set_error(self.start_date_field, err)
            self._set_error(self.end_date_field, err)
            valid = False
            error_message = error_message or err
        elif start_date and end_date:
            # ensure any previous error removed
            self._clear_error(self.start_date_field)
            self._clear_error(self.end_date_field)

        if (
            self._validate_int_input(
                self.invest_amount_field, 1, 100, "Sijoitettava summa"
            )
            is None
        ):
            valid = False
            error_message = (
                error_message or "Sijoitettava summa ei ole sallituissa rajoissa."
            )
        if (
            self._validate_int_input(
                self.investment_share_field,
                1,
                100,
                "Kerralla sijoitettava osuus pääomasta (%)",
            )
            is None
        ):
            valid = False
            error_message = (
                error_message or "Kerralla sijoitettava osuus on virheellinen."
            )
        if (
            self._validate_int_input(
                self.drop_threshold_field, 1, 100, "Kurssilaskuraja (%)"
            )
            is None
        ):
            valid = False
            error_message = error_message or "Kurssilaskuraja on virheellinen."
        if (
            self._validate_int_input(
                self.drop_average_days_field, 1, 60, "Kurssialarajan keskiarvon päivät"
            )
            is None
        ):
            valid = False
            error_message = error_message or "Keskiarvopäivien määrä on virheellinen."
        if (
            self._validate_int_input(
                self.rise_threshold_field, 1, 100, "Kurssinousuraja (%)"
            )
            is None
        ):
            valid = False
            error_message = error_message or "Kurssinousuraja on virheellinen."
        if (
            self._validate_decimal_input(
                self.strength_field,
                0.1,
                1.0,
                "Kynttilän vahvuus",
                decimals=1,
            )
            is None
        ):
            valid = False
            error_message = error_message or "Kynttilän vahvuus on virheellinen."
        if self._validate_int_input(self.rsi_field, 0, 100, "RSI t0 päivänä") is None:
            valid = False
            error_message = error_message or "RSI-arvo on virheellinen."
        if (
            self._validate_int_input(
                self.volume_growth_field, 1, 100, "Volyymin kasvu t0 (%)"
            )
            is None
        ):
            valid = False
            error_message = error_message or "Volyymin kasvu on virheellinen."

        if self.pattern_checkboxes:
            if not any(cb.value for cb in self.pattern_checkboxes):
                error_message = (
                    error_message
                    or "Valitse vähintään yksi kynttiläkuvio ennen simulaatiota."
                )
                valid = False
            elif self.require_combo_checkbox and self.require_combo_checkbox.value:
                selected_patterns = self._selected_patterns()
                divergence_keys = {"bullish_divergence", "bearish_divergence"}
                has_candle = any(
                    pattern not in divergence_keys for pattern in selected_patterns
                )
                has_divergence = any(
                    pattern in divergence_keys for pattern in selected_patterns
                )
                if not has_candle or not has_divergence:
                    valid = False
                    error_message = error_message or (
                        "Kombovaatimus edellyttää sekä kynttiläkuvion että "
                        "divergenssin valintaa."
                    )

        return valid, error_message

    def _append_result(self, result: SimulationResult):
        self._result_counter += 1
        print(
            "[SIMU][UI][APPEND]",
            result.ticker,
            f"start={result.start_capital:.2f}",
            f"end={result.end_capital:.2f}",
            f"growth={result.growth_pct:.2f}%",
            f"trades={result.buy_trades}",
        )
        self._results_data.append(result)
        self._update_results_view()

    # ---- Batch Simulation Methods ------------------------------------

    def on_batch_start(self, e):
        """Aloita batch-simulaatio kaikille osakkeille"""
        import os
        from .batch_simulator import BatchSimulator

        # Validoi ensin parametrit
        settings = self._build_settings()
        if settings is None:
            return

        combo_tickers: Optional[list[str]] = None
        if settings.require_divergence_combo:
            combo_tickers = self._resolve_combo_tickers(settings)
            if not combo_tickers:
                self._show_snack(
                    "Yhdistelmäsäännön täyttäviä osakkeita ei löytynyt.",
                    ft.Colors.ORANGE_400,
                )
                return

        # Piiloita normaali nappi, näytä progress
        self.batch_button.visible = False
        self.start_button.disabled = True
        self.batch_progress_bar.visible = True
        self.batch_progress_bar.value = 0
        self.batch_progress_text.visible = True
        if self.trade_summary_text:
            self.trade_summary_text.visible = False
            self.trade_summary_text.value = ""
        if combo_tickers is not None:
            self.batch_progress_text.value = (
                f"Valmistellaan {len(combo_tickers)} osaketta..."
            )
        else:
            self.batch_progress_text.value = "Valmistellaan..."
        self.batch_cancel_button.visible = True
        self.page.update()

        # Luo BatchSimulator
        data_dir = os.path.join(os.path.dirname(__file__), "..", "data")
        batch_sim = BatchSimulator(data_dir=data_dir)

        # Kerää parametrit
        parameters = {
            "initial_capital": settings.capital_thousands,
            "start_date": settings.start_date.strftime("%Y-%m-%d"),
            "end_date": settings.end_date.strftime("%Y-%m-%d"),
            "invest_percent": settings.invest_percent,
            "drop_percent": settings.drop_percent,
            "drop_average_days": settings.drop_average_days,
            "rise_percent": settings.rise_percent,
            "min_strength": settings.min_strength,
            "max_rsi": settings.max_rsi if settings.max_rsi < 101 else None,
            "min_volume_growth": settings.min_volume_growth,
            "selected_patterns": ", ".join(settings.selected_patterns),
            "require_divergence_combo": settings.require_divergence_combo,
        }

        # Määritä simulaatio-funktio
        def simulation_wrapper(ticker: str, params: dict):
            """Wrapper joka suorittaa simulaation yhdelle osakkeelle"""
            try:
                from .engine import SimulationRequest
                from .main import SimulationService

                # Luo uusi service-instanssi jokaiselle simulaatiolle
                # Tämä välttää SQLite-ongelmat eri säikeiden välillä
                service = SimulationService()

                try:
                    # Luo request
                    request = SimulationRequest(ticker=ticker, settings=settings)

                    # Suorita simulaatio
                    result = service.engine.run(request)

                    # Palauta tulokset batch_simulatorin ymmärtämässä muodossa
                    profit_eur = result.end_capital - result.start_capital

                    return (
                        True,
                        {
                            "initial_capital": result.start_capital,
                            "final_capital": result.end_capital,
                            "profit_eur": profit_eur,
                            "profit_pct": result.growth_pct,
                            "total_trades": result.buy_trades,
                            "winning_trades": result.winning_trades,
                            "losing_trades": result.losing_trades,
                        },
                        "",
                    )
                finally:
                    # Sulje yhteydet
                    service.close()

            except Exception as ex:
                return (False, {}, str(ex))

        # Progress callback
        def progress_callback(current: int, total: int, ticker: str):
            """Päivitä UI edistymisestä"""
            progress = current / total
            self.batch_progress_bar.value = progress
            self.batch_progress_text.value = (
                f"Käsitellään: {ticker} ({current}/{total})"
            )
            self.page.update()

        # Tallenna batch_sim instanssi jotta cancel toimii
        self._batch_sim = batch_sim

        try:
            # Suorita batch-simulaatio
            excel_path, trades_count = batch_sim.run_batch_simulation(
                simulation_func=simulation_wrapper,
                parameters=parameters,
                progress_callback=progress_callback,
                tickers=combo_tickers,
            )

            # Valmis
            if batch_sim.cancelled:
                self.batch_progress_text.value = f"Keskeytetty. Tulokset: {excel_path}"
            else:
                self.batch_progress_text.value = f"✅ Valmis! Tulokset: {excel_path}"

            if self.trade_summary_text:
                self.trade_summary_text.visible = True
                self.trade_summary_text.value = (
                    f"Kauppoja tehtiin {trades_count} osakkeelle."
                    if trades_count
                    else "Yhtään kauppaa ei tehty valituilla parametreilla."
                )
                self.trade_summary_text.update()

        except Exception as ex:
            self.batch_progress_text.value = f"❌ Virhe: {str(ex)}"

        finally:
            # Palauta UI
            self.batch_button.visible = True
            self.start_button.disabled = False
            self.batch_cancel_button.visible = False
            self.page.update()

    def on_batch_cancel(self, e):
        """Keskeytä batch-simulaatio"""
        if hasattr(self, "_batch_sim") and self._batch_sim:
            self._batch_sim.cancel()
            self.batch_progress_text.value = "Keskeytetään..."
            self.page.update()
