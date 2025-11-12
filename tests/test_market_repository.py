import sqlite3
from pathlib import Path

from market_repository import (
    ensure_market_schema,
    get_market_info,
    list_markets,
    upsert_market,
)


def test_ensure_market_schema_sets_default_min_volume(tmp_path):
    db_path = Path(tmp_path) / "markets.db"
    ensure_market_schema(str(db_path))
    markets = list_markets(str(db_path))
    lookup = {m["abbreviation"]: m for m in markets}
    assert lookup["usa"]["min_volume"] == 100000
    assert lookup["suomi"]["min_volume"] == 25000


def test_upsert_market_with_min_volume(tmp_path):
    db_path = Path(tmp_path) / "markets2.db"
    ensure_market_schema(str(db_path))
    market_id = upsert_market(
        name="Test",
        abbreviation="test",
        yahoo_suffix=".XX",
        min_volume=12345,
        db_path=str(db_path),
    )
    assert market_id is not None
    info = get_market_info("test", db_path=str(db_path))
    assert info is not None
    assert info["min_volume"] == 12345
