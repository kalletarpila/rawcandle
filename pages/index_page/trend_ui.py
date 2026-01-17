from __future__ import annotations

import datetime as dt
from typing import List

import flet as ft

from pages.index_page.trend_models import TrendChain, TrendSnapshot


def _hdr(text: str, tooltip: str | None = None) -> ft.Control:
    return ft.Text(text, weight=ft.FontWeight.BOLD, tooltip=tooltip) if tooltip else ft.Text(text, weight=ft.FontWeight.BOLD)


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
            ft.DataColumn(_hdr("Objekti"), on_sort=on_sort),
            ft.DataColumn(_hdr("Nimi"), on_sort=on_sort),
            ft.DataColumn(
                _hdr("Bias", "Trendin perussuunta (UP/DOWN/NEUTRAL) Dow-rakenteen mukaan."),
                on_sort=on_sort,
            ),
            ft.DataColumn(
                _hdr("State", "Trendin tila: CONTINUATION, WARNING tai REVERSAL."),
                on_sort=on_sort,
            ),
            ft.DataColumn(
                _hdr("Current Confidence", "Kuinka ehjä trendi on nyt?"),
                on_sort=on_sort,
            ),
            ft.DataColumn(
                _hdr("SH1", "Viimeisin swing high (huippu), käytetään arvioimaan uusia huippuja."),
                on_sort=on_sort,
            ),
            ft.DataColumn(
                _hdr("SL1", "Viimeisin swing low (pohja), seuraa pysyykö rakenne ehjänä."),
                on_sort=on_sort,
            ),
            ft.DataColumn(
                _hdr("Break?", "Kertoo rikottiinko viimeisin huippu (Up) tai pohja (Down)."),
                on_sort=on_sort,
            ),
        ],
        rows=[],
        column_spacing=10,
        heading_row_color=ft.Colors.GREY_100,
    )


def create_chain_table(on_sort=None) -> ft.DataTable:
    return ft.DataTable(
        columns=[
            ft.DataColumn(_hdr("Objekti"), on_sort=on_sort),
            ft.DataColumn(_hdr("Nimi"), on_sort=on_sort),
            ft.DataColumn(_hdr("Suunta"), on_sort=on_sort),
            ft.DataColumn(_hdr("Alku"), on_sort=on_sort),
            ft.DataColumn(_hdr("Loppu"), on_sort=on_sort),
            ft.DataColumn(_hdr("Tapahtumia"), on_sort=on_sort),
            ft.DataColumn(_hdr("Pareja"), on_sort=on_sort),
            ft.DataColumn(
                _hdr("Structural Confidence", "Kuinka vahva trendi on ollut historiassa."),
                tooltip="Kuinka vahva trendi on ollut historiassa.",
                on_sort=on_sort,
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
    snapshot_view = ft.Container(height=280, content=snapshot_table)
    chains_view = ft.Container(height=320, content=chain_table)

    info_panel = ft.ExpansionTile(
        title=ft.Text("Mitä kentät tarkoittavat?"),
        controls=[
            ft.Text(
                "Trend Snapshot taulukko\n***********************\n\nBias\n=====\nTrendin perussuunta Dow-logiikan mukaan.\nUP = nouseva rakenne (Higher High + Higher Low)\nDOWN = laskeva rakenne (Lower High + Lower Low)\nNEUTRAL = ei selkeää trendirakennetta\n\nState\n=====\nTrendin nykyinen tila suhteessa viimeisimpiin hintoihin.\nCONTINUATION = trendi jatkuu normaalisti\nREVERSAL = merkkejä trendin kääntymisestä\nWARNING = rakenne heikko tai epäselvä\n\nCurrent Confidence\n==================\nKuvaa, kuinka selkeä ja ehjä trendirakenne on tällä hetkellä viimeisimmän hintakehityksen perusteella.\nLuku perustuu huippujen ja pohjien määrään, niiden keskinäiseen suhteeseen sekä siihen, onko rakenne pysynyt ehjänä.\nEi ole ennuste, vaan nykytilan rakenteellinen mittari.\n\nCC\tTulkinta\n--      ---------\n0–30\tRakenne heikko tai epäselvä\n30–50\tVarovainen trendi, vaatii vahvistusta\n50–70\tSelkeä ja toimiva trendi\n70–85\tVahva ja johdonmukainen trendi\n85–100\tErittäin selkeä rakenne\nUseimmiten 40–70 on “normaali” alue elävälle markkinalle.\n\nSH1 (Latest Swing High)\n=======================\nViimeisin tunnistettu merkittävä huippu (Swing High).\nKäytetään arvioimaan, tekeekö hinta uusia huippuja vai jääkö nousu vajaaksi.\n\nSL1 (Latest Swing Low)\n=======================\nViimeisin tunnistettu merkittävä pohja (Swing Low).\nKäytetään arvioimaan, pysyykö trendi ehjänä vai rikkoutuuko rakenne.\n\nBreak\n=====\nKertoo, onko viimeisin hinta rikkonut trendille tärkeän tason.\nUp = hinta rikkoi edellisen huipun\nDown = hinta rikkoi edellisen pohjan\n– = ei merkittävää rikkomista\n\n\nTrend Chains taulukko\n*********************\n\nStructural Confidence\n=====================\n\nStructural Confidence kuvaa, kuinka vahva ja johdonmukainen trendirakenne on ollut koko trendijakson aikana, perustuen tunnistettuihin trendiketjuihin (Trend Chains).\nSe ei kuvaa nykyhetken tilannetta, vaan trendin rakennetta kokonaisuutena\n\nSC \tTulkinta\n--      ---------\n0–40\tLyhyt tai heikko trendirakenne\n40–60\tKohtalainen trendi\n60–80\tVahva ja johdonmukainen trendi\n80–100\tErittäin vahva, pitkäkestoinen rakenne\n\nKorkea Structural Confidence ei tarkoita, että trendi on yhä voimassa – vain että se on ollut rakenteellisesti vahva\n\nYHDESSÄ\n\n🧠 Yhdessä Current Confidence:n kanssa\n\nMOLEMMAT YHDESSÄ\n================\nCC      SC      Tulkinta\nKorkea  Korkea  Vahva trendi, jatkuu todennäköisesti\nMatala  Korkea  Vahva trendi heikentymässä\nKorkea  Matala  Uusi tai vasta muodostuva trendi\nMatala  Matala  Ei selkeää trendiä"
            ),
        ],
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
                    info_panel,
                    ft.Text("Trend Snapshot", weight=ft.FontWeight.BOLD),
                    snapshot_view,
                    ft.Divider(),
                    ft.Text("Trend Chains", weight=ft.FontWeight.BOLD),
                    chains_view,
                ],
                spacing=8,
            ),
        )
    )
