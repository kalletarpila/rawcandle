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
) -> Tuple[go.Figure, Dict[str, str]]:
    fig = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
    )

    colors = ["#2563eb", "#16a34a", "#f97316"]
    idx = 0
    dow_summaries = {}
    all_dates = set()

    for key in index_series:
        series = index_series[key]
        if not series:
            continue
        color = colors[idx % len(colors)]
        idx += 1
        dates = [row["date"] for row in series]
        vals = [row["value"] for row in series]
        all_dates.update(dates)
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
        markers, summary = compute_dow_markers(series)
        dow_summaries[key] = summary
        if markers:
            colors = []
            texts = []
            for m in markers:
                label = m["label"]
                texts.append(label)
                if label.startswith("LH") or label.startswith("LL"):
                    colors.append("#dc2626")
                else:
                    colors.append(color)
            fig.add_trace(
                go.Scatter(
                    x=[m["date"] for m in markers],
                    y=[m["value"] for m in markers],
                    mode="markers+text",
                    text=texts,
                    textposition="top center",
                    marker=dict(color=colors, size=9, symbol="circle"),
                    name=f"Pivot {key}",
                    showlegend=False,
                ),
                row=1,
                col=1,
            )
        vol = volume_series.get(key, [])
        if vol:
            fig.add_trace(
                go.Bar(
                    x=[row["date"] for row in vol],
                    y=[row["volume"] for row in vol],
                    name=f"Volyymi {key}",
                    marker_color=color,
                    opacity=0.6,
                ),
                row=2,
                col=1,
            )

    if stock_series:
        dates = [row["date"] for row in stock_series]
        vals = [row["value"] for row in stock_series]
        all_dates.update(dates)
        fig.add_trace(
            go.Scatter(
                x=dates,
                y=vals,
                mode="lines",
                name="Osake (norm)",
                line=dict(color="#111827", width=1.5, dash="dash"),
            ),
            row=1,
            col=1,
        )

    rangebreaks = [dict(bounds=["sat", "mon"])]
    if all_dates:
        date_list = sorted(all_dates)
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
