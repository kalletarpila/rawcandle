from __future__ import annotations

import datetime as dt
from typing import Dict, List, Optional, Sequence, Tuple

import plotly.graph_objects as go
from plotly.subplots import make_subplots

IndexSeries = List[Dict[str, object]]


def compute_dow_markers(series: IndexSeries, window: int = 5) -> Tuple[List[Dict], str]:
    """Laske pivotit (HH/HL/LH/LL) ja trendiyhteenveto."""
    if not series:
        return [], "NEUTRAL"
    values = [row["value"] for row in series]
    dates = [row["date"] for row in series]
    n = len(values)
    pivots: List[Tuple[int, str]] = []
    for i in range(n):
        start = max(0, i - window)
        end = min(n, i + window + 1)
        window_vals = values[start:end]
        if not window_vals:
            continue
        v = values[i]
        if v is None:
            continue
        if v == max(window_vals) and window_vals.count(v) == 1:
            pivots.append((i, "H"))
        elif v == min(window_vals) and window_vals.count(v) == 1:
            pivots.append((i, "L"))

    markers: List[Dict] = []
    last_high = None
    last_low = None
    trend = "NEUTRAL"
    last_change_date = None

    for idx, kind in pivots:
        val = values[idx]
        date = dates[idx]
        if kind == "H":
            if last_high is not None:
                label = "HH" if val > last_high[1] else "LH"
            else:
                label = "H"
            last_high = (date, val)
        else:
            if last_low is not None:
                label = "HL" if val > last_low[1] else "LL"
            else:
                label = "L"
            last_low = (date, val)
        markers.append({"date": date, "value": val, "label": label})
        last_change_date = date

    if markers:
        highs = [m for m in markers if m["label"].startswith("H")]
        lows = [m for m in markers if m["label"].startswith("L")]
        if highs and lows:
            last_high_label = highs[-1]["label"]
            last_low_label = lows[-1]["label"]
            if last_high_label == "HH" and last_low_label == "HL":
                trend = "UP"
            elif last_high_label == "LH" and last_low_label == "LL":
                trend = "DOWN"
    summary = f"{trend} (pivot {last_change_date})" if last_change_date else trend
    return markers, summary


def build_index_plot(
    index_series: Dict[str, IndexSeries],
    volume_series: Dict[str, IndexSeries],
    *,
    stock_series: Optional[IndexSeries] = None,
    include_market: bool = False,
) -> go.Figure:
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
            fig.add_trace(
                go.Scatter(
                    x=[m["date"] for m in markers],
                    y=[m["value"] for m in markers],
                    mode="markers+text",
                    text=[m["label"] for m in markers],
                    textposition="top center",
                    marker=dict(color=color, size=9, symbol="circle"),
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
    )
    fig.update_xaxes(rangebreaks=rangebreaks, row=1, col=1)
    fig.update_xaxes(rangebreaks=rangebreaks, row=2, col=1)
    fig.update_yaxes(title_text="Indeksi", row=1, col=1)
    fig.update_yaxes(title_text="Volyymi", row=2, col=1)

    return fig, dow_summaries
