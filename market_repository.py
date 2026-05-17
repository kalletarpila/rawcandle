"""
Utilities for managing market metadata stored in osakedata.db.

Provides helpers to ensure the schema exists, list/update markets, and
read/write the per-ticker market assignments.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional


MARKET_VOLUME_DEFAULTS: Dict[str, int] = {
    "usa": 100_000,
    "suomi": 25_000,
    "ruotsi": 40_000,
    "saksa": 80_000,
}

DEFAULT_MARKETS: List[Dict[str, str]] = [
    {
        "name": "Yhdysvallat",
        "abbreviation": "usa",
        "yahoo_suffix": "",
    },
    {
        "name": "Suomi",
        "abbreviation": "suomi",
        "yahoo_suffix": ".HE",
    },
    {
        "name": "Ruotsi",
        "abbreviation": "ruotsi",
        "yahoo_suffix": ".ST",
    },
    {
        "name": "Saksa",
        "abbreviation": "saksa",
        "yahoo_suffix": ".DE",
    },
]


def _normalize_db_path(db_path: Optional[str]) -> Path:
    if db_path is None:
        base = Path(__file__).resolve().parent
        db_path = base / "data" / "osakedata.db"
    else:
        db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return db_path


def _connect(db_path: Optional[str] = None) -> sqlite3.Connection:
    path = _normalize_db_path(db_path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_market_schema(db_path: Optional[str] = None) -> None:
    """Ensure osakedata table has a market column and markets metadata exists."""

    conn = _connect(db_path)
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS osakedata (
            osake TEXT NOT NULL,
            pvm TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            market TEXT NOT NULL DEFAULT 'usa',
            PRIMARY KEY (osake, pvm)
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS splits_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            osake TEXT NOT NULL,
            split_date TEXT NOT NULL,
            split_ratio REAL NOT NULL,
            is_price_data_corrected INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(osake, split_date)
        )
        """
    )
    cursor.execute("PRAGMA table_info(splits_data)")
    splits_columns = {row[1] for row in cursor.fetchall()}
    if "is_price_data_corrected" not in splits_columns:
        cursor.execute(
            "ALTER TABLE splits_data ADD COLUMN is_price_data_corrected INTEGER NOT NULL DEFAULT 0"
        )

    cursor.execute("PRAGMA table_info(osakedata)")
    columns = {row[1] for row in cursor.fetchall()}
    if "market" not in columns:
        cursor.execute(
            "ALTER TABLE osakedata ADD COLUMN market TEXT NOT NULL DEFAULT 'usa'"
        )
        cursor.execute("UPDATE osakedata SET market = 'suomi' WHERE osake LIKE '%.HE'")
        cursor.execute("UPDATE osakedata SET market = 'usa' WHERE market IS NULL")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS markets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            abbreviation TEXT NOT NULL UNIQUE,
            yahoo_suffix TEXT NOT NULL DEFAULT '',
            min_volume INTEGER NOT NULL DEFAULT 100000
        )
        """
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_markets_abbrev ON markets(abbreviation)"
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_osakedata_market_ticker_date
        ON osakedata(market, osake, pvm)
        """
    )

    cursor.execute("PRAGMA table_info(markets)")
    market_columns = {row[1] for row in cursor.fetchall()}
    if "min_volume" not in market_columns:
        cursor.execute(
            "ALTER TABLE markets ADD COLUMN min_volume INTEGER NOT NULL DEFAULT 100000"
        )
        for abbreviation, min_vol in MARKET_VOLUME_DEFAULTS.items():
            cursor.execute(
                "UPDATE markets SET min_volume = ? WHERE abbreviation = ?",
                (min_vol, abbreviation),
            )

    cursor.execute("SELECT COUNT(*) FROM markets")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            """
            INSERT INTO markets (name, abbreviation, yahoo_suffix, min_volume)
            VALUES (?, ?, ?, ?)
            """,
            [
                (
                    m["name"],
                    m["abbreviation"],
                    m["yahoo_suffix"],
                    MARKET_VOLUME_DEFAULTS.get(m["abbreviation"], 100_000),
                )
                for m in DEFAULT_MARKETS
            ],
    )

    conn.commit()

    # Luo indeksi price_data-tauluun (käytetään analyysissä tiheästi)
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='price_data'"
    )
    if cursor.fetchone():
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_price_data_ticker_date ON price_data(ticker, date)"
        )
        conn.commit()

    conn.close()


def list_markets(db_path: Optional[str] = None) -> List[Dict[str, str]]:
    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, abbreviation, yahoo_suffix, min_volume FROM markets ORDER BY name COLLATE NOCASE"
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "abbreviation": row["abbreviation"],
            "yahoo_suffix": row["yahoo_suffix"],
            "min_volume": row["min_volume"],
        }
        for row in rows
    ]


def _normalize_abbreviation(abbreviation: str) -> str:
    return abbreviation.strip().lower()


def _normalize_min_volume(min_volume: Optional[str | int | float]) -> int:
    if min_volume is None or min_volume == "":
        return 0
    if isinstance(min_volume, (int, float)):
        value = int(min_volume)
    else:
        value = int(str(min_volume).replace(" ", ""))
    if value < 0:
        raise ValueError("Minimivolyymi ei voi olla negatiivinen")
    return value


def upsert_market(
    *,
    name: str,
    abbreviation: str,
    yahoo_suffix: str,
    min_volume: int | str,
    market_id: Optional[int] = None,
    db_path: Optional[str] = None,
) -> int:
    """Insert or update a market entry. Returns the market id."""

    if not name.strip():
        raise ValueError("Markkinan nimi ei voi olla tyhjä")

    abbreviation = _normalize_abbreviation(abbreviation)
    if not abbreviation or len(abbreviation) > 10:
        raise ValueError("Lyhenteen tulee olla 1-10 merkkiä")

    yahoo_suffix = yahoo_suffix.strip()
    if len(yahoo_suffix) > 5:
        raise ValueError("Yahoo-lyhenne saa olla korkeintaan 5 merkkiä")

    min_volume_value = _normalize_min_volume(min_volume)

    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()

    try:
        if market_id is None:
            cursor.execute(
                """
                INSERT INTO markets (name, abbreviation, yahoo_suffix, min_volume)
                VALUES (?, ?, ?, ?)
                """,
                (name.strip(), abbreviation, yahoo_suffix, min_volume_value),
            )
            market_id = cursor.lastrowid
        else:
            cursor.execute(
                """
                UPDATE markets
                SET name = ?, abbreviation = ?, yahoo_suffix = ?, min_volume = ?
                WHERE id = ?
                """,
                (name.strip(), abbreviation, yahoo_suffix, min_volume_value, market_id),
            )
            if cursor.rowcount == 0:
                raise ValueError("Market ID:tä ei löytynyt")

        conn.commit()
        return market_id

    except sqlite3.IntegrityError as exc:
        conn.rollback()
        raise ValueError("Markkinan lyhenne on jo käytössä") from exc
    finally:
        conn.close()


def delete_market(market_id: int, db_path: Optional[str] = None) -> None:
    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT abbreviation FROM markets WHERE id = ?", (market_id,))
    row = cursor.fetchone()
    if row is None:
        conn.close()
        raise ValueError("Markkinaa ei löytynyt")

    abbreviation = row["abbreviation"]
    cursor.execute("SELECT COUNT(*) FROM markets")
    remaining = cursor.fetchone()[0]
    if remaining <= 1:
        conn.close()
        raise ValueError("Viimeistä markkinaa ei voi poistaa")

    cursor.execute(
        "SELECT COUNT(DISTINCT osake) FROM osakedata WHERE market = ?", (abbreviation,)
    )
    if cursor.fetchone()[0] > 0:
        conn.close()
        raise ValueError("Markkinaa käytetään osakedatassa eikä sitä voi poistaa")

    cursor.execute("DELETE FROM markets WHERE id = ?", (market_id,))
    conn.commit()
    conn.close()


def get_market_info(
    abbreviation: str, db_path: Optional[str] = None
) -> Optional[Dict[str, str]]:
    """Return market metadata dict or None."""
    abbreviation = _normalize_abbreviation(abbreviation)
    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, name, abbreviation, yahoo_suffix, min_volume
        FROM markets
        WHERE abbreviation = ? COLLATE NOCASE
        LIMIT 1
        """,
        (abbreviation,),
    )
    row = cursor.fetchone()
    conn.close()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "abbreviation": row["abbreviation"],
        "yahoo_suffix": row["yahoo_suffix"],
        "min_volume": row["min_volume"],
    }


def get_market_min_volume(
    abbreviation: str, db_path: Optional[str] = None
) -> int:
    info = get_market_info(abbreviation, db_path=db_path)
    if info and info.get("min_volume") is not None:
        return int(info["min_volume"])
    return MARKET_VOLUME_DEFAULTS.get(_normalize_abbreviation(abbreviation), 100_000)


def get_market_for_ticker(
    ticker: str, db_path: Optional[str] = None, default: str = "usa"
) -> str:
    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT market FROM osakedata WHERE osake = ? ORDER BY pvm DESC LIMIT 1",
        (ticker,),
    )
    row = cursor.fetchone()
    conn.close()
    if row and row["market"]:
        return row["market"]
    return default


def set_ticker_market(ticker: str, market: str, db_path: Optional[str] = None) -> None:
    abbreviation = _normalize_abbreviation(market)
    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT 1 FROM markets WHERE abbreviation = ?", (abbreviation,))
    if cursor.fetchone() is None:
        conn.close()
        raise ValueError(f"Tuntematon markkina: {abbreviation}")

    cursor.execute(
        "UPDATE osakedata SET market = ? WHERE osake = ?", (abbreviation, ticker)
    )
    conn.commit()
    conn.close()


def ticker_exists(ticker: str, db_path: Optional[str] = None) -> bool:
    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM osakedata WHERE osake = ? LIMIT 1", (ticker,))
    exists = cursor.fetchone() is not None
    conn.close()
    return exists


def validate_market(abbreviation: str, db_path: Optional[str] = None) -> bool:
    abbreviation = _normalize_abbreviation(abbreviation)
    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT 1 FROM markets WHERE abbreviation = ? COLLATE NOCASE LIMIT 1",
        (abbreviation,),
    )
    is_valid = cursor.fetchone() is not None
    conn.close()
    return is_valid
