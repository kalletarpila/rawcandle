"""Yhteiset määrittelyt Bullish Divergence + kynttilä -kombofeatureille."""

from __future__ import annotations

from typing import Dict, List

CANDLE_PATTERN_TO_SLUG: Dict[str, str] = {
    "Hammer": "Hammer",
    "Bullish Engulfing": "Bullish_Engulfing",
    "Piercing Pattern": "Piercing_Pattern",
    "Three White Soldiers": "Three_White_Soldiers",
    "Morning Star": "Morning_Star",
    "Dragonfly Doji": "Dragonfly_Doji",
}

COMBO_SUFFIXES: List[str] = [
    "only_t0",
    "and_BullDiv_t0",
    "and_BullDiv_recent_2d",
    "and_BullDiv_recent_3d",
    "and_BullDiv_recent_5d",
]

COMBO_FEATURE_COLUMNS: List[str] = [
    f"is_{slug}_{suffix}"
    for slug in CANDLE_PATTERN_TO_SLUG.values()
    for suffix in COMBO_SUFFIXES
]

BULL_DIV_GENERAL_FEATURES: List[str] = [
    "bullDiv_offset",
    "bullDiv_last_1d",
    "bullDiv_last_2d",
    "bullDiv_last_3d",
    "bullDiv_last_3d_any",
]
