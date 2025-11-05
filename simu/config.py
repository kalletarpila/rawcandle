from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# Base directories
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

# Database paths
ANALYSIS_DB_PATH = BASE_DIR / "analysis" / "analysis.db"
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


PATTERN_DEFINITIONS: tuple[PatternDefinition, ...] = (
    PatternDefinition("downtrend", "downtrend", "0 Random laskutrendipäivä"),
    PatternDefinition("hammer", "Hammer", "1 Hammer"),
    PatternDefinition("bullish_engulfing", "Bullish Engulfing", "2 Bullish Engulfing"),
    PatternDefinition("piercing_pattern", "Piercing Pattern", "3 Piercing Pattern"),
    PatternDefinition(
        "three_white_soldiers", "Three White Soldiers", "4 Three White Soldiers"
    ),
    PatternDefinition("morning_star", "Morning Star", "5 Morning Star"),
    PatternDefinition("dragonfly_doji", "Dragonfly Doji", "6 Dragonfly Doji"),
    PatternDefinition(
        "bullish_divergence", "Bullish Divergence", "7 Bullish Divergence"
    ),
    PatternDefinition(
        "bearish_divergence", "Bearish Divergence", "8 Bearish Divergence"
    ),
)

PATTERN_MAP: dict[str, PatternDefinition] = {p.key: p for p in PATTERN_DEFINITIONS}
DB_PATTERN_TO_KEY: dict[str, str] = {
    p.db_name.lower(): p.key for p in PATTERN_DEFINITIONS
}
