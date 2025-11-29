#!/usr/bin/env python3
"""
Täyttää results_data.t0_alinMiinusClose -kentän olemassa olevan t0_alin-arvon perusteella.

Kaava: t0_alinMiinusClose = t0_alin - 100.

Oletus on dry-run; käytä --apply kirjoittaaksesi muutokset kantaan.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional


COLUMN_NAME = "t0_alinMiinusClose"


@dataclass
class FieldUpdate:
    row_id: int
    value: float


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(results_data)")
    columns = {row[1] for row in cursor.fetchall()}
    if "t0_alin" not in columns:
        raise RuntimeError("results_data taulusta puuttuu t0_alin, backfilliä ei voi ajaa.")
    if COLUMN_NAME not in columns:
        conn.execute(f"ALTER TABLE results_data ADD COLUMN {COLUMN_NAME} REAL")
        conn.commit()


def compute_t0_alin_minus_close(t0_alin: Optional[float]) -> Optional[float]:
    if t0_alin is None:
        return None
    try:
        return float(t0_alin) - 100.0
    except (TypeError, ValueError):
        return None


def _almost_equal(a: float, b: float, tol: float = 1e-9) -> bool:
    return abs(a - b) <= tol


def build_updates(rows: Iterable[sqlite3.Row]) -> List[FieldUpdate]:
    updates: List[FieldUpdate] = []
    for row in rows:
        current = row[COLUMN_NAME]
        computed = compute_t0_alin_minus_close(row["t0_alin"])
        if computed is None:
            continue
        if current is None or not _almost_equal(float(current), computed):
            updates.append(FieldUpdate(row_id=row["id"], value=computed))
    return updates


def fetch_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    cursor = conn.execute(
        f"SELECT id, t0_alin, {COLUMN_NAME} FROM results_data"
    )
    return cursor.fetchall()


def apply_updates(conn: sqlite3.Connection, updates: List[FieldUpdate]) -> int:
    cursor = conn.cursor()
    affected = 0
    for upd in updates:
        cursor.execute(
            f"UPDATE results_data SET {COLUMN_NAME} = ? WHERE id = ?",
            (upd.value, upd.row_id),
        )
        affected += cursor.rowcount
    conn.commit()
    return affected


def backfill(db_path: Path, apply: bool = False) -> int:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    _ensure_columns(conn)

    rows = fetch_rows(conn)
    updates = build_updates(rows)

    if not apply:
        print(
            f"Kuivaharjoitus: {len(updates)} riviä tarvitsee päivityksen "
            f"({len(rows)} riviä luettu). Käytä --apply kirjoittaaksesi muutokset."
        )
        return 0

    applied = apply_updates(conn, updates)
    print(f"Päivitettiin {applied} riviä ({len(updates)} laskettu päivitys).")
    return applied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Laske ja täytä results_data.t0_alinMiinusClose kenttä."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/analysis.db"),
        help="Polku analysis.db tietokantaan (oletus: data/analysis.db)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Kirjoita muutokset tietokantaan (oletus: dry-run)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    backfill(args.db, apply=args.apply)


if __name__ == "__main__":
    main()
