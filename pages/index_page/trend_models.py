from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional


@dataclass
class SwingPoint:
    date: dt.date
    value: float
    kind: str  # 'H' or 'L'


@dataclass
class TrendSnapshot:
    object_type: str
    object_name: str
    bias: str
    state: str
    confidence: int
    sh1: Optional[SwingPoint]
    sh2: Optional[SwingPoint]
    sl1: Optional[SwingPoint]
    sl2: Optional[SwingPoint]
    break_signal: str  # 'Up', 'Down', or '-'


@dataclass
class TrendChain:
    object_type: str
    object_name: str
    direction: str  # 'UP' or 'DOWN'
    start_date: dt.date
    end_date: dt.date
    events_count: int
    pairs_count: int
    confidence: int
