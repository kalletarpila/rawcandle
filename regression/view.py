from __future__ import annotations

from typing import Callable, Dict, List

import flet as ft
import pandas as pd

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
        self.pattern_dropdown = ft.Dropdown(
            label="Valitse kynttilätyyppi",
            width=240,
            options=self._build_pattern_options(),
            value="__all__",
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
                        self.pattern_dropdown,
                        self.run_button,
                    ],
                    spacing=16,
                ),
                self.status_text,
            ],
            spacing=10,
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

    def _build_pattern_options(self) -> List[ft.dropdown.Option]:
        options = [ft.dropdown.Option("__all__", "Kaikki kynttilät")]
        for code, label in run_regression.PATTERN_LABELS.items():
            options.append(ft.dropdown.Option(str(code), label))
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
        pattern_value = self.pattern_dropdown.value or "__all__"
        self._set_status("Ajetaan regressioanalyysiä...", ft.Colors.BLUE_600)
        self.run_button.disabled = True
        self.page.update()

        try:
            if pattern_value in {"", "__all__"}:
                pattern_code = None
            else:
                pattern_code = int(pattern_value)
            result = run_regression.run_regression_for_market(
                market_value, pattern_code
            )
            formatted = self._format_result_text(result, market_value)
            self.output_field.value = formatted
            self._set_status("Analyysi valmis.", ft.Colors.GREEN_600)
        except Exception as exc:
            self.output_field.value = f"Virhe: {exc}"
            self._set_status("Analyysi epäonnistui.", ft.Colors.RED_600)
        finally:
            self.run_button.disabled = False
            try:
                self.page.update()
            except Exception:
                pass

    def _format_result_text(self, result: Dict[str, object], market_value: str) -> str:
        market_label = (
            "Kaikki markkinat" if market_value in {"", "__all__"} else market_value.upper()
        )
        logistic = result["logistic"]
        linear = result["linear"]
        pattern_label = result.get("pattern_label", "Kaikki kynttilät")

        top_pos = logistic["top_positive"]
        top_neg = logistic["top_negative"]

        def format_series(series: pd.Series) -> str:
            return "\n".join(f"{idx}: {val:.4f}" for idx, val in series.items())

        lines = [
            f"Markkina: {market_label}",
            f"Kynttilätyyppi: {pattern_label}",
            f"Rivejä analyysissä: {result['row_count']}",
            "",
            result["summary"],
            "",
            "== Logistinen regressio (success5) ==",
            f"AUC: {logistic['auc']:.3f}",
            logistic["classification_report"].strip(),
            "",
            "Top 15 positiivista featurea:",
            format_series(top_pos),
            "",
            "Top 15 negatiivista featurea:",
            format_series(top_neg),
            "",
            "== Lineaarinen regressio (y5) ==",
            linear["summary"],
        ]
        return "\n".join(lines)
