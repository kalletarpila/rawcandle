#!/usr/bin/env python3
"""
Nosta results_data-tauluun BullDiv-komborivit (71–76) ja poista vastaavat
peruskynttilärivit (1–6) samoilta päiviltä.

- Etsii ticker+date, joilla on sekä kynttilä (1–6) että bullish_strength > 0
  divergence_data-taulussa.
- Valitsee päivältä pienimmän kynttiläkoodin 1–6 -> muuntaa komboksi (base+70).
- Lisää uuden rivin kopiona alkuperäisestä (candle_pattern päivitetty).
- Poistaa alkuperäisen kynttilärivin, jotta samalta päivältä ei jää kahta.

Oletuskanta: data/analysis.db. Käytä --dry-run jos haluat nähdä luvut ilman kirjoitusta.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple
import datetime

BASE_TO_COMBO = {i: i + 70 for i in range(1, 7)}


def get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def fetch_divergence_days(conn: sqlite3.Connection) -> set[Tuple[str, str]]:
    cur = conn.execute(
        "SELECT ticker, date FROM divergence_data WHERE bullish_strength > 0"
    )
    return {(row[0], row[1]) for row in cur.fetchall()}


def fetch_existing_combos(conn: sqlite3.Connection) -> set[Tuple[str, str]]:
    cur = conn.execute(
        "SELECT ticker, date FROM results_data WHERE candle_pattern BETWEEN 71 AND 76"
    )
    return {(row[0], row[1]) for row in cur.fetchall()}


def fetch_candle_rows(conn: sqlite3.Connection) -> Sequence[sqlite3.Row]:
    """Hae kaikki candle_pattern 1–6 rivit results_data-taulusta."""
    conn.row_factory = sqlite3.Row
    cur = conn.execute(
        "SELECT * FROM results_data WHERE candle_pattern BETWEEN 1 AND 6"
    )
    return cur.fetchall()


def pick_primary(rows: Sequence[sqlite3.Row]) -> Dict[Tuple[str, str], sqlite3.Row]:
    """
    Valitse jokaiselle (ticker, date) yhdelle riville pienin candle_pattern (1–6).
    """
    best: Dict[Tuple[str, str], sqlite3.Row] = {}
    for row in rows:
        key = (row["ticker"], row["date"])
        current = best.get(key)
        if current is None or row["candle_pattern"] < current["candle_pattern"]:
            best[key] = row
    return best


def insert_combo_rows(
    conn: sqlite3.Connection,
    rows: Iterable[sqlite3.Row],
    columns: List[str],
) -> int:
    cols_for_insert = [c for c in columns if c != "id"]
    placeholders = ", ".join("?" for _ in cols_for_insert)
    sql = f"INSERT INTO results_data ({', '.join(cols_for_insert)}) VALUES ({placeholders})"
    to_insert: List[Tuple] = []
    for row in rows:
        combo_code = BASE_TO_COMBO.get(row["candle_pattern"])
        if combo_code is None:
            continue
        values = []
        for col in cols_for_insert:
            if col == "candle_pattern":
                values.append(combo_code)
            elif col == "is_candle_day":
                values.append(1)
            else:
                values.append(row[col])
        to_insert.append(tuple(values))

    if to_insert:
        conn.executemany(sql, to_insert)
    return len(to_insert)


def delete_original_rows(conn: sqlite3.Connection, row_ids: Iterable[int]) -> int:
    ids = list(row_ids)
    if not ids:
        return 0
    conn.executemany("DELETE FROM results_data WHERE id = ?", [(i,) for i in ids])
    return len(ids)


def main(db_path: Path, dry_run: bool = False) -> None:
    conn = sqlite3.connect(db_path)
    try:
        columns = get_columns(conn, "results_data")
        if "candle_pattern" not in columns:
            raise RuntimeError("results_data: candle_pattern-sarake puuttuu.")

        divergence_days = fetch_divergence_days(conn)
        existing_combos = fetch_existing_combos(conn)
        rows = fetch_candle_rows(conn)

        # Ryhmittele per (ticker, date)
        by_day: Dict[Tuple[str, str], List[sqlite3.Row]] = {}
        for row in rows:
            by_day.setdefault((row["ticker"], row["date"]), []).append(row)

        add_rows: List[sqlite3.Row] = []
        delete_ids: List[int] = []
        for (ticker, date_str), candidates in by_day.items():
            if (ticker, date_str) in existing_combos:
                continue
            has_div_t0 = (ticker, date_str) in divergence_days
            try:
                d_obj = datetime.date.fromisoformat(date_str)
                prev_date = (d_obj - datetime.timedelta(days=1)).isoformat()
            except Exception:
                prev_date = None
            has_div_t1 = prev_date and (ticker, prev_date) in divergence_days
            if not (has_div_t0 or has_div_t1):
                continue
            chosen = min(candidates, key=lambda r: r["candle_pattern"])
            add_rows.append(chosen)
            delete_ids.append(chosen["id"])

        if dry_run:
            dist: Dict[int, int] = {}
            for row in add_rows:
                combo_code = BASE_TO_COMBO.get(row["candle_pattern"])
                if combo_code is not None:
                    dist[combo_code] = dist.get(combo_code, 0) + 1
            print(f"[dry-run] Lisättävät komborivit: {len(add_rows)} => {dist}")
            print(f"[dry-run] Poistettavat alkuperäiset rivit: {len(delete_ids)}")
            return

        conn.execute("BEGIN")
        inserted = insert_combo_rows(conn, add_rows, columns)
        deleted = delete_original_rows(conn, delete_ids)
        conn.commit()

        dist: Dict[int, int] = {}
        for row in add_rows:
            combo_code = BASE_TO_COMBO.get(row["candle_pattern"])
            if combo_code is not None:
                dist[combo_code] = dist.get(combo_code, 0) + 1

        print(f"Päivitetty results_data: lisätty {inserted} komboriviä, poistettu {deleted} perusriviä.")
        print(f"Kombojakauma: {dist if dist else '{}'}")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Luo BullDiv-kombo (71–76) -rivit results_data-tauluun ja poista korvatut peruskynttilät."
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("data/analysis.db"),
        help="Polku analysis.db -tietokantaan (oletus: data/analysis.db)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ei kirjoituksia; raportoi vain lisättävät ja poistettavat.",
    )
    args = parser.parse_args()
    main(args.db, dry_run=args.dry_run)
