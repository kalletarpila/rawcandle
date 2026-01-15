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


def build_trend_card(snapshot_rows_ctrl: List[ft.DataRow], chain_rows_ctrl: List[ft.DataRow], selected_x: int, selected_k: int) -> ft.Card:
    snapshot_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Objekti", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Nimi", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Bias", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("State", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Confidence", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("SH1", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("SL1", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Break?", weight=ft.FontWeight.BOLD)),
        ],
        rows=snapshot_rows_ctrl,
        column_spacing=10,
        heading_row_color=ft.Colors.GREY_100,
    )
    snapshot_view = ft.Container(
        height=280,
        content=ft.Column([snapshot_table], scroll=ft.ScrollMode.AUTO),
    )

    chains_table = ft.DataTable(
        columns=[
            ft.DataColumn(ft.Text("Objekti", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Nimi", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Suunta", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Alku", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Loppu", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Tapahtumia", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Pareja", weight=ft.FontWeight.BOLD)),
            ft.DataColumn(ft.Text("Confidence", weight=ft.FontWeight.BOLD)),
        ],
        rows=chain_rows_ctrl,
        column_spacing=10,
        heading_row_color=ft.Colors.GREY_100,
    )
    chains_view = ft.Container(
        height=320,
        content=ft.Column([chains_table], scroll=ft.ScrollMode.AUTO),
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
                    ft.Text(f"Trendit (X={selected_x}, k={selected_k})", size=16, weight=ft.FontWeight.BOLD),
                    tabs,
                ],
                spacing=8,
            ),
        )
    )
