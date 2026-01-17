from __future__ import annotations

import datetime as dt
from typing import List

import flet as ft

from pages.index_page.trend_models import TrendChain, TrendSnapshot


def format_date_val(sp) -> str:
    if not sp:
        return "-"
    if not isinstance(sp.date, dt.date):
        return "-"
    return f"{sp.date} @ {sp.value:.2f}"


def snapshot_rows(snapshots: List[TrendSnapshot]) -> List[ft.DataRow]:
    rows = []
    for s in snapshots:
        rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(s.object_type)),
                    ft.DataCell(ft.Text(s.object_name)),
                    ft.DataCell(ft.Text(s.bias)),
                    ft.DataCell(ft.Text(s.state)),
                    ft.DataCell(ft.Text(str(s.confidence))),
                    ft.DataCell(ft.Text(format_date_val(s.sh1))),
                    ft.DataCell(ft.Text(format_date_val(s.sl1))),
                    ft.DataCell(ft.Text(s.break_signal)),
                ]
            )
        )
    return rows


def chain_rows(chains: List[TrendChain]) -> List[ft.DataRow]:
    rows = []
    for c in chains:
        rows.append(
            ft.DataRow(
                cells=[
                    ft.DataCell(ft.Text(c.object_type)),
                    ft.DataCell(ft.Text(c.object_name)),
                    ft.DataCell(ft.Text(c.direction)),
                    ft.DataCell(ft.Text(str(c.start_date))),
                    ft.DataCell(ft.Text(str(c.end_date))),
                    ft.DataCell(ft.Text(str(c.events_count))),
                    ft.DataCell(ft.Text(str(c.pairs_count))),
                    ft.DataCell(ft.Text(str(c.confidence))),
                ]
            )
        )
    return rows


def create_snapshot_table(on_sort=None) -> ft.DataTable:
    return ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Objekti", weight=ft.FontWeight.BOLD), on_sort=on_sort),
            ft.DataColumn(ft.Text("Nimi", weight=ft.FontWeight.BOLD), on_sort=on_sort),
            ft.DataColumn(
                ft.Text("Bias", weight=ft.FontWeight.BOLD),
                tooltip="Trendin perussuunta (UP/DOWN/NEUTRAL) Dow-rakenteen mukaan.",
                on_sort=on_sort,
            ),
            ft.DataColumn(
                ft.Text("State", weight=ft.FontWeight.BOLD),
                tooltip="Trendin tila: CONTINUATION, WARNING tai REVERSAL.",
                on_sort=on_sort,
            ),
            ft.DataColumn(
                ft.Text("Current Confidence", weight=ft.FontWeight.BOLD),
                tooltip="Kuinka ehjä trendi on nyt?",
                on_sort=on_sort,
            ),
            ft.DataColumn(
                ft.Text("SH1", weight=ft.FontWeight.BOLD),
                tooltip="Viimeisin swing high (huippu), käytetään arvioimaan uusia huippuja.",
                on_sort=on_sort,
            ),
            ft.DataColumn(
                ft.Text("SL1", weight=ft.FontWeight.BOLD),
                tooltip="Viimeisin swing low (pohja), seuraa pysyykö rakenne ehjänä.",
                on_sort=on_sort,
            ),
            ft.DataColumn(
                ft.Text("Break?", weight=ft.FontWeight.BOLD),
                tooltip="Kertoo rikottiinko viimeisin huippu (Up) tai pohja (Down).",
                on_sort=on_sort,
            ),
        ],
        rows=[],
        column_spacing=10,
        heading_row_color=ft.Colors.GREY_100,
    )


def create_chain_table() -> ft.DataTable:
    return ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Objekti", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Nimi", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Suunta", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Alku", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Loppu", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Tapahtumia", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Pareja", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(
                ft.Text("Structural Confidence", weight=ft.FontWeight.BOLD),
                tooltip="Kuinka vahva trendi on ollut historiassa.",
            ),
        ],
        rows=[],
        column_spacing=10,
        heading_row_color=ft.Colors.GREY_100,
    )


def build_trend_card(
    snapshot_table: ft.DataTable,
    chain_table: ft.DataTable,
    selected_x: int,
    selected_k: int,
) -> ft.Card:
    snapshot_view = ft.Container(
        height=280, content=ft.Column([snapshot_table], scroll=ft.ScrollMode.AUTO)
    )
    chains_view = ft.Container(
        height=320, content=ft.Column([chain_table], scroll=ft.ScrollMode.AUTO)
    )

    tabs = ft.Tabs(
        tabs=[
            ft.Tab(text="Trend Snapshot", content=snapshot_view),
            ft.Tab(text="Trend Chains", content=chains_view),
        ],
        expand=1,
    )

    return ft.Card(
        content=ft.Container(
            padding=12,
            content=ft.Column(
                [
                    ft.Text(
                        f"Trendit (X={selected_x}, k={selected_k})",
                        size=16,
                        weight=ft.FontWeight.BOLD,
                    ),
                    tabs,
                ],
                spacing=8,
            ),
        )
    )
