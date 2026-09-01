from __future__ import annotations

from typing import Sequence


Anchor = tuple[float, float]

ANCHORS: dict[str, tuple[Anchor, ...]] = {
    "ebit_yield": (
        (0.00, 0.0),
        (0.02, 6.0),
        (0.04, 14.0),
        (0.06, 22.0),
        (0.09, 31.0),
        (0.15, 40.0),
    ),
    "fcf_yield": (
        (0.00, 0.0),
        (0.02, 5.0),
        (0.04, 12.0),
        (0.06, 20.0),
        (0.10, 30.0),
        (0.20, 40.0),
    ),
    "earnings_yield": (
        (0.00, 0.0),
        (0.02, 3.0),
        (0.04, 7.0),
        (0.06, 11.0),
        (0.09, 16.0),
        (0.15, 20.0),
    ),
}


def piecewise_points(value: float, anchors: Sequence[Anchor]) -> float:
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x0 <= value <= x1:
            return y0 + (value - x0) * (y1 - y0) / (x1 - x0)
    raise ValueError("anchors must be ordered and cover the input")
