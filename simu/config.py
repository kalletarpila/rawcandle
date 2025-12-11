from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Database paths
ANALYSIS_DB_PATH = DATA_DIR / "analysis.db"
PRICE_DB_PATH = DATA_DIR / "osakedata.db"

# Indicator defaults
RSI_PERIOD = 14
VOLUME_SMA_WINDOW = 10


@dataclass(frozen=True)
class PatternDefinition:
    """Description of a candlestick pattern used by the simulator UI."""

    key: str  # canonical key used in code and UI data fields
    db_name: str  # value stored in analysis database
    label: str  # label shown to the user
    code: int  # numeric candle code


PATTERN_DEFINITIONS: tuple[PatternDefinition, ...] = (
    PatternDefinition("downtrend", "downtrend", "0 Random laskutrendipäivä", 0),
    PatternDefinition("hammer", "Hammer", "1 Hammer", 1),
    PatternDefinition(
        "bullish_engulfing", "Bullish Engulfing", "2 Bullish Engulfing", 2
    ),
    PatternDefinition("piercing_pattern", "Piercing Pattern", "3 Piercing Pattern", 3),
    PatternDefinition(
        "three_white_soldiers", "Three White Soldiers", "4 Three White Soldiers", 4
    ),
    PatternDefinition("morning_star", "Morning Star", "5 Morning Star", 5),
    PatternDefinition("dragonfly_doji", "Dragonfly Doji", "6 Dragonfly Doji", 6),
    PatternDefinition("bullish_divergence", "Bullish Divergence", "7 Bullish Divergence", 7),
    PatternDefinition(
        "bearish_divergence", "Bearish Divergence", "8 Bearish Divergence", 8
    ),
    PatternDefinition(
        "bulldiv_hammer_combo", "BullDiv & Hammer", "71 BullDiv & Hammer", 71
    ),
    PatternDefinition(
        "bulldiv_bullish_engulfing_combo",
        "BullDiv & Bullish Engulfing",
        "72 BullDiv & Bullish Engulfing",
        72,
    ),
    PatternDefinition(
        "bulldiv_piercing_combo",
        "BullDiv & Piercing Pattern",
        "73 BullDiv & Piercing Pattern",
        73,
    ),
    PatternDefinition(
        "bulldiv_three_white_combo",
        "BullDiv & Three White Soldiers",
        "74 BullDiv & Three White Soldiers",
        74,
    ),
    PatternDefinition(
        "bulldiv_morning_star_combo",
        "BullDiv & Morning Star",
        "75 BullDiv & Morning Star",
        75,
    ),
    PatternDefinition(
        "bulldiv_dragonfly_doji_combo",
        "BullDiv & Dragonfly Doji",
        "76 BullDiv & Dragonfly Doji",
        76,
    ),
)

PATTERN_MAP: dict[str, PatternDefinition] = {p.key: p for p in PATTERN_DEFINITIONS}
DB_PATTERN_TO_KEY: dict[str, str] = {
    p.db_name.lower(): p.key for p in PATTERN_DEFINITIONS
}
PATTERN_KEY_TO_NUMBER: dict[str, int] = {definition.key: definition.code for definition in PATTERN_DEFINITIONS}
DIVERGENCE_KEYS = {"bullish_divergence", "bearish_divergence"}
