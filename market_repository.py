"""
Utilities for managing market metadata stored in osakedata.db.

Provides helpers to ensure the schema exists, list/update markets, and
read/write the per-ticker market assignments.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Dict, List, Optional


DEFAULT_MARKETS: List[Dict[str, str]] = [
    {"name": "Yhdysvallat", "abbreviation": "usa", "yahoo_suffix": ""},
    {"name": "Suomi", "abbreviation": "suomi", "yahoo_suffix": ".HE"},
    {"name": "Ruotsi", "abbreviation": "ruotsi", "yahoo_suffix": ".ST"},
    {"name": "Saksa", "abbreviation": "saksa", "yahoo_suffix": ".DE"},
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
            yahoo_suffix TEXT NOT NULL DEFAULT ''
        )
        """
    )
    cursor.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_markets_abbrev ON markets(abbreviation)"
    )

    cursor.execute("SELECT COUNT(*) FROM markets")
    if cursor.fetchone()[0] == 0:
        cursor.executemany(
            "INSERT INTO markets (name, abbreviation, yahoo_suffix) VALUES (?, ?, ?)",
            [
                (m["name"], m["abbreviation"], m["yahoo_suffix"])
                for m in DEFAULT_MARKETS
            ],
        )

    conn.commit()
    conn.close()


def list_markets(db_path: Optional[str] = None) -> List[Dict[str, str]]:
    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, abbreviation, yahoo_suffix FROM markets ORDER BY name COLLATE NOCASE"
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "abbreviation": row["abbreviation"],
            "yahoo_suffix": row["yahoo_suffix"],
        }
        for row in rows
    ]


def _normalize_abbreviation(abbreviation: str) -> str:
    return abbreviation.strip().lower()


def upsert_market(
    *,
    name: str,
    abbreviation: str,
    yahoo_suffix: str,
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

    ensure_market_schema(db_path)
    conn = _connect(db_path)
    cursor = conn.cursor()

    if market_id is None:
        cursor.execute(
            """
            INSERT INTO markets (name, abbreviation, yahoo_suffix)
            VALUES (?, ?, ?)
            """,
            (name.strip(), abbreviation, yahoo_suffix),
        )
        market_id = cursor.lastrowid
    else:
        cursor.execute(
            """
            UPDATE markets
            SET name = ?, abbreviation = ?, yahoo_suffix = ?
            WHERE id = ?
            """,
            (name.strip(), abbreviation, yahoo_suffix, market_id),
        )
        if cursor.rowcount == 0:
            raise ValueError("Market ID:tä ei löytynyt")

    conn.commit()
    conn.close()
    return market_id


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
