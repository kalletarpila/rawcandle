from __future__ import annotations

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
                        self.run_button,
                    ],
                    spacing=16,
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
        feature_payload = selected_features + [run_regression.FEATURE_SELECTION_MARKER]
        self._set_status("Ajetaan regressioanalyysiä...", ft.Colors.BLUE_600)
        self.run_button.disabled = True
        self.page.update()

        try:
            require_blackout = bool(self.require_blackout_checkbox.value)
            result = run_regression.run_regression_for_market(
                market_value,
                pattern_code=selected_patterns,
                success_horizons=selected_horizons,
                success_thresholds=thresholds,
                require_blackout_data=require_blackout,
                feature_columns=feature_payload,
            )
            self.output_field.value = result["report"]
            status_msg = "Analyysi valmis."
            if result.get("report_path"):
                status_msg += f" Raportti tallennettu: {result['report_path']}"
            if result.get("warnings"):
                status_msg += " | Varoitukset: " + "; ".join(result["warnings"])
            self._set_status(status_msg, ft.Colors.GREEN_600)
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

    def _get_selected_patterns(self) -> List[int]:
        selected = [
            code for code, checkbox in self.pattern_checkboxes.items() if checkbox.value
        ]
        return sorted(selected)

    def _get_selected_features(self) -> List[str]:
        selected = [
            name for name in self.feature_names if self.feature_checkboxes[name].value
        ]
        if not selected:
            return list(self.feature_names)
        return selected
