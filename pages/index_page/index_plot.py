from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Tuple

import plotly.graph_objects as go
from plotly.subplots import make_subplots

from pages.index_page.index_utils import compute_dow_markers

IndexSeries = List[Dict[str, object]]


def build_index_plot(
    index_series: Dict[str, IndexSeries],
    volume_series: Dict[str, IndexSeries],
    *,
    stock_series: Optional[IndexSeries] = None,
    pivot_window: int = 5,
) -> Tuple[go.Figure, Dict[str, str]]:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
    )

    market_color = "#2563eb"
    sector_colors = ["#f97316", "#16a34a", "#8b5cf6", "#0ea5e9", "#22c55e"]
    sector_color_idx = 0
    sectors_present = any(k != "MARKET" for k in index_series.keys())
    allow_market_volume = not sectors_present
    dow_summaries = {}
    index_dates_union = set()
    index_date_sets = []

    for key in sorted(index_series.keys()):
        series = index_series[key]
        if not series:
            continue
        if key == "MARKET":
            color = market_color
        else:
            color = sector_colors[sector_color_idx % len(sector_colors)]
            sector_color_idx += 1
        dates = [row["date"] for row in series]
        vals = [row["value"] for row in series]
        index_dates_union.update(dates)
        index_date_sets.append(set(dates))
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=vals,
                mode="lines",
                name=f"Indeksi {key}",
                line=dict(color=color, width=2),
            ),
            row=1,
            col=1,
        )
        markers, summary = compute_dow_markers(series, window=pivot_window)
        dow_summaries[key] = summary
        if markers:
            colors = []
            customdata = []
            for m in markers:
                label = m["label"]
                customdata.append((label, m["date"]))
                if label.startswith("LH") or label.startswith("LL"):
                    colors.append("#dc2626")
                else:
                    colors.append("#2563eb")
            fig.add_trace(
                go.Scatter(
                    x=[m["date"] for m in markers],
                    y=[m["value"] for m in markers],
                    mode="markers",
                    marker=dict(color=colors, size=9, symbol="circle"),
                    name=f"Pivot {key}",
                    showlegend=False,
                    customdata=customdata,
                    hovertemplate="Pivot: %{customdata[0]}<br>Pvm: %{customdata[1]|%m-%d}<br>Arvo: %{y:.2f}<extra></extra>",
                ),
                row=1,
                col=1,
            )
        vol = volume_series.get(key, [])
        if vol and (key != "MARKET" or allow_market_volume):
            fig.add_trace(
                go.Bar(
                    x=[row["date"] for row in vol],
                    y=[row["volume"] for row in vol],
                    name=f"Volyymi {key}",
                    marker=dict(color=color),
                    opacity=0.6,
                ),
                row=2,
                col=1,
            )

    if stock_series:
        dates = [row["date"] for row in stock_series]
        vals = [row["value"] for row in stock_series]
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=vals,
                mode="lines",
                name="Osake (norm)",
                line=dict(color="#111827", width=2),
            ),
            row=1,
            col=1,
        )
        stock_markers, _ = compute_dow_markers(stock_series, window=pivot_window)
        if stock_markers:
            colors_stock = []
            customdata_stock = []
            for m in stock_markers:
                lab = m["label"]
                customdata_stock.append((lab, m["date"]))
                if lab.startswith("LH") or lab.startswith("LL"):
                    colors_stock.append("#dc2626")
                else:
                    colors_stock.append("#2563eb")
            fig.add_trace(
                go.Scatter(
                    x=[m["date"] for m in stock_markers],
                    y=[m["value"] for m in stock_markers],
                    mode="markers",
                    marker=dict(color=colors_stock, size=8, symbol="circle"),
                    name="Osake pivots",
                    showlegend=False,
                    customdata=customdata_stock,
                    hovertemplate="Pivot: %{customdata[0]}<br>Pvm: %{customdata[1]|%m-%d}<br>Arvo: %{y:.2f}<extra></extra>",
                ),
                row=1,
                col=1,
            )

    rangebreaks = [dict(bounds=["sat", "mon"])]
    if index_dates_union:
        common_dates = set.intersection(*index_date_sets) if index_date_sets else set()
        base_dates = common_dates if common_dates else index_dates_union
        date_list = sorted(base_dates)
        date_set = set(date_list)
        missing = []
        cur = date_list[0]
        while cur <= date_list[-1]:
            if cur not in date_set:
                missing.append(cur.isoformat())
            cur += dt.timedelta(days=1)
        if missing:
            rangebreaks.append(dict(values=missing))

    fig.update_layout(
        template="plotly_white",
        height=600,
        margin=dict(t=30, l=40, r=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        barmode="group",
        updatemenus=[
            dict(
                type="buttons",
                direction="left",
                buttons=[
                    dict(
                        label="Reset zoom",
                        method="relayout",
                        args=[
                            {
                                "xaxis.autorange": True,
                                "yaxis.autorange": True,
                                "yaxis2.autorange": True,
                            }
                        ],
                    )
                ],
                x=0.0,
                y=1.1,
                xanchor="left",
                yanchor="bottom",
                showactive=False,
            )
        ],
    )
    fig.update_xaxes(rangebreaks=rangebreaks, row=1, col=1)
    fig.update_xaxes(rangebreaks=rangebreaks, row=2, col=1)
    fig.update_yaxes(title_text="Indeksi", row=1, col=1)
    fig.update_yaxes(title_text="Volyymi", row=2, col=1)

    return fig, dow_summaries
