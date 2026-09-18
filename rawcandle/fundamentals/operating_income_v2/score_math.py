from __future__ import annotations

import math
from typing import Any, Mapping, Sequence


ANCHORS = {
    "revenue_growth_yoy_ttm": ((-0.10, 0.0), (0.0, 7.0), (0.10, 12.0), (0.20, 16.0), (0.30, 20.0)),
    "ebit_margin_ttm": ((0.0, 0.0), (0.10, 7.5), (0.25, 15.0)),
    "ebit_margin_direction": ((-0.05, 0.0), (0.0, 7.5), (0.05, 15.0)),
    "fcf_margin_ttm": ((-0.05, 0.0), (0.0, 3.0), (0.05, 7.0), (0.10, 11.0), (0.20, 15.0)),
    "share_change_yoy": ((-0.02, 10.0), (0.0, 8.0), (0.02, 5.0), (0.05, 2.0), (0.10, 0.0)),
}


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or abs(denominator) <= 1e-12:
        return None
    value = numerator / denominator
    return value if math.isfinite(value) else None


def safe_growth(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous <= 1e-12:
        return None
    value = current / previous - 1.0
    return value if math.isfinite(value) else None


def clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def piecewise_score(value: float | None, anchors: Sequence[tuple[float, float]]) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    if value <= anchors[0][0]:
        return anchors[0][1]
    if value >= anchors[-1][0]:
        return anchors[-1][1]
    for (left_x, left_y), (right_x, right_y) in zip(anchors, anchors[1:]):
        if left_x <= value <= right_x:
            fraction = (value - left_x) / (right_x - left_x)
            return left_y + fraction * (right_y - left_y)
    raise AssertionError("piecewise interval not found")


def fiscal_ordinal(year: Any, quarter: Any) -> int:
    return int(year) * 4 + int(str(quarter).removeprefix("Q")) - 1


def _float(value: Any) -> float | None:
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def balance_points(row: Mapping[str, Any], floor: float = 4.0) -> float | None:
    cash = _float(row.get("cash"))
    debt = _float(row.get("total_debt"))
    ebit = _float(row.get("ttm_ebit"))
    fcf = _float(row.get("ttm_free_cashflow"))
    if cash is None or debt is None or ebit is None or fcf is None:
        return None
    net_debt = debt - cash
    if ebit > 0:
        return piecewise_score(net_debt / ebit, ((0.0, 15.0), (1.0, 12.0), (2.0, 8.0), (3.0, 4.0), (floor, 0.0)))
    if net_debt <= 0 and fcf >= 0:
        return 10.0
    if net_debt <= 0 and fcf < 0:
        return 5.0
    return 0.0
