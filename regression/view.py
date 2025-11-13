from __future__ import annotations

from typing import Callable

import flet as ft


class RegressionView:
    """Yksinkertainen dummy-näkymä regressiotyökalujen tulevalle toteutukselle."""

    def __init__(self, page: ft.Page, appbar_factory: Callable[[], ft.AppBar]):
        self.page = page
        self._appbar_factory = appbar_factory

    def create_view(self) -> ft.View:
        """Palauta placeholder-näkymä."""
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

        placeholder_card = ft.Card(
            content=ft.Container(
                padding=25,
                content=ft.Column(
                    [
                        ft.Text(
                            "Tila varattu tulosten visualisoinnille",
                            size=18,
                            weight=ft.FontWeight.BOLD,
                        ),
                        ft.Text(
                            "Kun regressiomoottori on valmis, tähän ilmestyy graafeja "
                            "ja tunnuslukuja mallien vertailuun.",
                            color=ft.Colors.GREY_600,
                        ),
                        ft.Container(
                            alignment=ft.alignment.center,
                            padding=ft.padding.symmetric(vertical=20),
                            content=ft.Icon(
                                ft.Icons.INSERT_CHART,
                                size=80,
                                color=ft.Colors.ORANGE_400,
                            ),
                        ),
                    ],
                    spacing=12,
                ),
            )
        )

        body = ft.Container(
            padding=ft.padding.only(left=24, right=24, top=24, bottom=40),
            content=ft.Column(
                [hero, info_cards, placeholder_card],
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
