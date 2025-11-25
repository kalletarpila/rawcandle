from __future__ import annotations

from datetime import datetime
from typing import Callable, Dict, List

import flet as ft

from market_repository import list_markets
from regression import run_regression


class RegressionView:
    """Yksinkertainen dummy-näkymä regressiotyökalujen tulevalle toteutukselle."""

    def __init__(self, page: ft.Page, appbar_factory: Callable[[], ft.AppBar]):
        self.page = page
        self._appbar_factory = appbar_factory

    def create_view(self) -> ft.View:
        """Palauta placeholder-näkymä."""
        self.market_dropdown = ft.Dropdown(
            label="Valitse markkina",
            width=240,
            options=self._build_market_options(),
            value="__all__",
        )
        available_years = self._load_year_options()
        self.year_checkboxes = {
            year: ft.Checkbox(label=str(year), value=True) for year in available_years
        }
        self.horizon_checkboxes = {
            2: ft.Checkbox(label="2 päivää", value=False),
            5: ft.Checkbox(label="5 päivää", value=True),
            10: ft.Checkbox(label="10 päivää", value=False),
            20: ft.Checkbox(label="20 päivää", value=False),
        }
        self.require_blackout_checkbox = ft.Checkbox(
            label="Käytä vain tickereitä, joilla blackout-data (earnings/dividend) löytyi",
            value=False,
        )
        self.exclude_crisis_checkbox = ft.Checkbox(
            label="Poista kriisiaika analyyseista",
            value=False,
            tooltip=(
                "Poistaa kriisijakson 2025-03-01 – 2025-04-30 analyysidatasta "
                "(is_crisis = 1 rivit)."
            ),
        )
        self.success_threshold_fields = {
            2: ft.TextField(
                label="success2 raja",
                width=130,
                value=f"{run_regression.DEFAULT_SUCCESS_THRESHOLDS[2]:.2f}",
            ),
            5: ft.TextField(
                label="success5 raja",
                width=130,
                value=f"{run_regression.DEFAULT_SUCCESS_THRESHOLDS[5]:.2f}",
            ),
            10: ft.TextField(
                label="success10 raja",
                width=130,
                value=f"{run_regression.DEFAULT_SUCCESS_THRESHOLDS[10]:.2f}",
            ),
            20: ft.TextField(
                label="success20 raja",
                width=130,
                value=f"{run_regression.DEFAULT_SUCCESS_THRESHOLDS[20]:.2f}",
            ),
        }
        continuous_features = list(run_regression.FEATURE_COLUMNS)
        dummy_features = [
            run_regression.PATTERN_COLUMN,
            run_regression.MARKET_COLUMN,
            "BullDiv_recent_offset",
        ]
        self.feature_names = continuous_features + ["is_candle_day"] + dummy_features
        seen = set()
        ordered_feature_names: list[str] = []
        for name in self.feature_names:
            if name not in seen:
                ordered_feature_names.append(name)
                seen.add(name)
        self.feature_names = ordered_feature_names
        feature_type_map = {name: "Jatkuva" for name in continuous_features}
        for name in ["is_candle_day"] + dummy_features:
            feature_type_map[name] = "Dummy"
        self.feature_checkboxes: Dict[str, ft.Checkbox] = {
            name: ft.Checkbox(label=f"{name} ({feature_type_map[name]})", value=True)
            for name in self.feature_names
        }
        self._apply_saved_feature_selection()
        pattern_codes = [
            (code, label)
            for code, label in run_regression.PATTERN_LABELS.items()
            if 0 <= code <= 7
        ]
        self.pattern_checkboxes: Dict[int, ft.Checkbox] = {
            code: ft.Checkbox(
                label=f"{label} (koodi {code})",
                value=(code != 0),
            )
            for code, label in pattern_codes
        }
        self.bullish_divergence_only_checkbox = ft.Checkbox(
            label="Bullish Divergence -ydinmalli (vain downtrend + Bullish Divergence)",
            value=False,
            tooltip=(
                "Ajaa erillisen ydinkehikon: analysoi vain downtrend (0) ja Bullish Divergence (7) rivit."
            ),
            on_change=self._toggle_bullish_divergence_mode,
        )
        self.run_button = ft.ElevatedButton(
            "Aja regressio",
            icon=ft.Icons.PLAY_ARROW,
            on_click=self._on_run_clicked,
        )
        self.status_text = ft.Text(
            "Valitse markkina ja käynnistä analyysi.",
            color=ft.Colors.GREY_600,
        )
        self.output_field = ft.TextField(
            value="",
            read_only=True,
            multiline=True,
            min_lines=20,
            max_lines=40,
            expand=True,
            border_radius=8,
            border_color=ft.Colors.GREY_300,
            text_style=ft.TextStyle(font_family="monospace", size=13),
        )

        hero = ft.Column(
            [
                ft.Text(
                    "📈 Regression Toolkit",
                    size=30,
                    weight=ft.FontWeight.BOLD,
                    color=ft.Colors.BLUE_600,
                ),
                ft.Text(
                    "Tämä on placeholder-näkymä tulevaa regressioanalyysiä varten. "
                    "Lisäämme tänne mallien valinnan, datan tuonnin ja tulosten "
                    "visualisoinnin heti kun laskentamoottori on valmis.",
                    size=16,
                    color=ft.Colors.GREY_600,
                ),
                ft.Row(
                    [
                        self.market_dropdown,
                        self.require_blackout_checkbox,
                        self.exclude_crisis_checkbox,
                        self.run_button,
                    ],
                    spacing=16,
                ),
                ft.Row(
                    [
                        ft.Text("Vuosifiltteri:", weight=ft.FontWeight.BOLD),
                        *list(self.year_checkboxes.values()),
                    ],
                    spacing=10,
                    wrap=True,
                ),
                ft.Row(
                    list(self.horizon_checkboxes.values()),
                    spacing=10,
                ),
                ft.ResponsiveRow(
                    [
                        ft.Container(
                            padding=ft.padding.symmetric(vertical=6),
                            content=field,
                            col={"xs": 6, "sm": 3, "md": 2},
                        )
                        for field in self.success_threshold_fields.values()
                    ]
                ),
                self.status_text,
            ],
            spacing=10,
        )

        pattern_selection_card = ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text(
                            "Valitse analyysiin sisällytettävät kynttilätyypit",
                            weight=ft.FontWeight.BOLD,
                            size=18,
                        ),
                        ft.Text(
                            "Downtrend (0) analysoidaan erikseen vain, jos valitset sen yksin. "
                            "Muulloin downtrend lisätään automaattisesti muiden valittujen kuvioiden rinnalle.",
                            color=ft.Colors.GREY_600,
                        ),
                        ft.ResponsiveRow(
                            [
                                ft.Container(
                                    padding=5,
                                    content=self.pattern_checkboxes[code],
                                    col={"xs": 12, "sm": 6, "md": 4},
                                )
                                for code in sorted(self.pattern_checkboxes.keys())
                            ],
                            spacing=10,
                            run_spacing=5,
                        ),
                        ft.Divider(),
                        ft.Text(
                            "Tai valitse erillinen Bullish Divergence -ydinmalli (downtrend + BullDiv):",
                            weight=ft.FontWeight.BOLD,
                            size=16,
                        ),
                        self.bullish_divergence_only_checkbox,
                    ],
                    spacing=10,
                ),
            )
        )

        feature_selection_card = ft.Card(
            content=ft.Container(
                padding=20,
                content=ft.Column(
                    [
                        ft.Text(
                            "Valitse regressioon käytettävät featurit",
                            weight=ft.FontWeight.BOLD,
                            size=18,
                        ),
                        ft.Text(
                            "Voit kytkeä featuureita päälle/pois ilman, että ohjelmakoodia tarvitsee muuttaa.",
                            color=ft.Colors.GREY_600,
                        ),
                        ft.ResponsiveRow(
                            [
                                ft.Container(
                                    padding=5,
                                    content=self.feature_checkboxes[name],
                                    col={"xs": 12, "sm": 6, "md": 4, "lg": 3},
                                )
                                for name in self.feature_names
                            ],
                            spacing=10,
                            run_spacing=5,
                        ),
                    ],
                    spacing=10,
                ),
            )
        )

        info_cards = ft.ResponsiveRow(
            [
                ft.Container(
                    col={"xs": 12, "sm": 6},
                    padding=10,
                    content=ft.Card(
                        content=ft.Container(
                            padding=20,
                            content=ft.Column(
                                [
                                    ft.Text(
                                        "Vaihe 1: Datan valinta",
                                        weight=ft.FontWeight.BOLD,
                                        size=18,
                                    ),
                                    ft.Text(
                                        "Sijoita tänne kontrollit, joilla valitaan regressioon "
                                        "käytettävät datasetit ja aikavälit.",
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=8,
                            ),
                        )
                    ),
                ),
                ft.Container(
                    col={"xs": 12, "sm": 6},
                    padding=10,
                    content=ft.Card(
                        content=ft.Container(
                            padding=20,
                            content=ft.Column(
                                [
                                    ft.Text(
                                        "Vaihe 2: Mallien konfigurointi",
                                        weight=ft.FontWeight.BOLD,
                                        size=18,
                                    ),
                                    ft.Text(
                                        "Tähän lisätään valinnat eri regressiomalleille "
                                        "ja hyperparametreille.",
                                        color=ft.Colors.GREY_600,
                                    ),
                                ],
                                spacing=8,
                            ),
                        )
                    ),
                ),
            ]
        )

        body = ft.Container(
            padding=ft.padding.only(left=24, right=24, top=24, bottom=40),
            content=ft.Column(
                [
                    hero,
                    pattern_selection_card,
                    feature_selection_card,
                    info_cards,
                    ft.Card(
                        content=ft.Container(
                            padding=20,
                            content=self.output_field,
                        )
                    ),
                ],
                spacing=24,
                scroll=ft.ScrollMode.AUTO,
            ),
        )

        return ft.View(
            "/regression",
            controls=[
                self._appbar_factory(),
                body,
            ],
            scroll=ft.ScrollMode.AUTO,
        )

    # ---------------------- Helpers ---------------------- #

    def _build_market_options(self) -> List[ft.dropdown.Option]:
        options = [ft.dropdown.Option("__all__", "Kaikki markkinat")]
        try:
            markets = list_markets()
            for market in markets:
                label = f"{market['name']} ({market['abbreviation'].upper()})"
                options.append(
                    ft.dropdown.Option(market["abbreviation"].lower(), label)
                )
        except Exception:
            pass
        return options

    def _load_year_options(self) -> List[int]:
        """
        Palauttaa saatavilla olevat vuodet results_data-taulusta.
        Jos lataus epäonnistuu, käytä väliä 2018 - kuluvan vuoden loppuun.
        """
        try:
            years = run_regression.list_available_years()
            if years:
                return years
        except Exception:
            pass
        current_year = datetime.now().year
        return list(range(2018, current_year + 1))

    def _set_status(self, message: str, color: str = ft.Colors.GREY_600) -> None:
        self.status_text.value = message
        self.status_text.color = color
        try:
            self.page.update()
        except Exception:
            pass

    def _on_run_clicked(self, _):
        market_value = self.market_dropdown.value or "__all__"
        selected_horizons = self._get_selected_horizons()
        if not selected_horizons:
            self._set_status(
                "Valitse vähintään yksi horisontti.",
                ft.Colors.RED_600,
            )
            self.run_button.disabled = False
            self.page.update()
            return
        selected_years = self._get_selected_years()
        if not selected_years:
            self._set_status(
                "Valitse vähintään yksi vuosi.",
                ft.Colors.RED_600,
            )
            self.run_button.disabled = False
            self.page.update()
            return

        thresholds = self._get_thresholds()
        selected_patterns = self._get_selected_patterns()
        if not selected_patterns:
            self._set_status(
                "Valitse vähintään yksi kynttilätyyppi.",
                ft.Colors.RED_600,
            )
            self.run_button.disabled = False
            self.page.update()
            return
        selected_features = self._get_selected_features()
        raw_feature_selection = self._get_selected_features(allow_empty=True)
        feature_payload = selected_features + [run_regression.FEATURE_SELECTION_MARKER]
        self._set_status("Ajetaan regressioanalyysiä...", ft.Colors.BLUE_600)
        self.run_button.disabled = True
        self.page.update()

        try:
            require_blackout = bool(self.require_blackout_checkbox.value)
            exclude_crisis = bool(self.exclude_crisis_checkbox.value)
            result = run_regression.run_regression_for_market(
                market_value,
                pattern_code=selected_patterns,
                success_horizons=selected_horizons,
                success_thresholds=thresholds,
                require_blackout_data=require_blackout,
                exclude_crisis_period=exclude_crisis,
                feature_columns=feature_payload,
                year_filter=selected_years,
            )
            self.output_field.value = result["report"]
            status_msg = "Analyysi valmis."
            if result.get("report_path"):
                status_msg += f" Raportti tallennettu: {result['report_path']}"
            if result.get("warnings"):
                status_msg += " | Varoitukset: " + "; ".join(result["warnings"])
            self._set_status(status_msg, ft.Colors.GREEN_600)
            persisted_selection = raw_feature_selection
            try:
                run_regression.save_feature_selection_preferences(
                    persisted_selection,
                    market=market_value,
                    horizons=selected_horizons,
                    thresholds=thresholds,
                    years=selected_years,
                )
            except TypeError:
                # Yhteensopivuus vanhojen implementaatioiden kanssa
                run_regression.save_feature_selection_preferences(persisted_selection)
        except Exception as exc:
            self.output_field.value = f"Virhe: {exc}"
            self._set_status("Analyysi epäonnistui.", ft.Colors.RED_600)
        finally:
            self.run_button.disabled = False
            try:
                self.page.update()
            except Exception:
                pass

    def _get_thresholds(self) -> Dict[int, float]:
        thresholds: Dict[int, float] = {}
        for horizon, field in self.success_threshold_fields.items():
            try:
                value = float(field.value)
                thresholds[horizon] = value
                field.error_text = None
            except (TypeError, ValueError):
                field.error_text = "Anna luku (esim. 0.03)"
        return thresholds

    def _get_selected_horizons(self) -> List[int]:
        horizons = [
            h for h, checkbox in self.horizon_checkboxes.items() if checkbox.value
        ]
        return sorted(horizons)

    def _get_selected_years(self) -> List[int]:
        if not hasattr(self, "year_checkboxes"):
            # Luodaan oletukset, jos kontrolli puuttuu (esim. testifixtureissä).
            self.year_checkboxes = {
                year: type("Box", (), {"value": True})
                for year in self._load_year_options()
            }
        years = [y for y, checkbox in self.year_checkboxes.items() if checkbox.value]
        return sorted(years)

    def _get_selected_patterns(self):
        if getattr(self, "bullish_divergence_only_checkbox", None):
            if self.bullish_divergence_only_checkbox.value:
                return "BullishDivergenceOnly"
        selected = [
            code for code, checkbox in self.pattern_checkboxes.items() if checkbox.value
        ]
        return sorted(selected)

    def _apply_saved_feature_selection(self) -> None:
        saved = run_regression.load_feature_selection_preferences()
        if not saved:
            return
        if isinstance(saved, list):
            feature_list = saved
            saved_market = None
            saved_horizons = set()
            saved_thresholds: Dict[int, float] = {}
            saved_years = set()
        else:
            feature_list = saved.get("features") or []
            saved_market = saved.get("market")
            saved_horizons = set(saved.get("horizons") or [])
            saved_thresholds = saved.get("thresholds") or {}
            saved_years = set(saved.get("years") or [])
        saved_set = set(feature_list)
        for name, checkbox in self.feature_checkboxes.items():
            checkbox.value = name in saved_set
        if saved_market:
            option_keys = {
                getattr(opt, "key", None) or getattr(opt, "value", None)
                for opt in self.market_dropdown.options
            }
            if saved_market in option_keys:
                self.market_dropdown.value = saved_market
        if saved_horizons:
            for h, checkbox in self.horizon_checkboxes.items():
                checkbox.value = h in saved_horizons
        if saved_thresholds:
            for horizon, field in self.success_threshold_fields.items():
                if horizon in saved_thresholds:
                    field.value = str(saved_thresholds[horizon])
        if saved_years and hasattr(self, "year_checkboxes"):
            for year, checkbox in self.year_checkboxes.items():
                checkbox.value = year in saved_years

    def _get_selected_features(self, allow_empty: bool = False) -> List[str]:
        selected = [
            name for name in self.feature_names if self.feature_checkboxes[name].value
        ]
        if selected or allow_empty:
            return selected
        return list(self.feature_names)

    def _toggle_bullish_divergence_mode(self, _):
        enabled = not self.bullish_divergence_only_checkbox.value
        for checkbox in self.pattern_checkboxes.values():
            checkbox.disabled = not enabled
        if self.bullish_divergence_only_checkbox.value:
            for horizon in self.horizon_checkboxes.values():
                horizon.value = True
                horizon.disabled = True
        else:
            for horizon in self.horizon_checkboxes.values():
                horizon.disabled = False
        try:
            self.page.update()
        except Exception:
            pass
