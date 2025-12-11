#!/usr/bin/env python3
"""
Päivitä analysis_findings-taulu tukemaan uusia BullDiv + kynttilä -kombokoodeja.

- Luo candle_pattern-sarakkeen jos sitä ei ole.
- Mapittaa pattern-tekstin peruskoodiksi (1–6,7,8).
- Jos ticker+date löytyy divergence_data-taulusta bullish_strength > 0, nostaa
  kyseisen päivän pienimmän kynttiläkoodin (1–6) kombokoodiin 71–76 ja muuttaa
  pattern-tekstin muotoon "BullDiv & <Nimi>".
- Muut kynttilät samalta päivältä jätetään ennalleen.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

BASE_PATTERN_CODES: Dict[str, int] = {
    "hammer": 1,
    "bullish engulfing": 2,
    "piercing pattern": 3,
    "three white soldiers": 4,
    "morning star": 5,
    "dragonfly doji": 6,
    "bullish divergence": 7,
    "bearish divergence": 8,
}

COMBO_NAME_BY_BASE: Dict[int, str] = {
    1: "BullDiv & Hammer",
    2: "BullDiv & Bullish Engulfing",
    3: "BullDiv & Piercing Pattern",
    4: "BullDiv & Three White Soldiers",
    5: "BullDiv & Morning Star",
    6: "BullDiv & Dragonfly Doji",
}


def get_columns(conn: sqlite3.Connection, table: str) -> List[str]:
    cur = conn.execute(f"PRAGMA table_info({table})")
    return [row[1] for row in cur.fetchall()]


def ensure_candle_pattern_column(conn: sqlite3.Connection) -> None:
    if "candle_pattern" in get_columns(conn, "analysis_findings"):
        return
    conn.execute("ALTER TABLE analysis_findings ADD COLUMN candle_pattern INTEGER DEFAULT 0")
    conn.commit()


def load_divergence_days(conn: sqlite3.Connection) -> set[Tuple[str, str]]:
    cur = conn.execute(
        "SELECT ticker, date FROM divergence_data WHERE bullish_strength > 0"
    )
    return {(row[0], row[1]) for row in cur.fetchall()}


def fetch_findings(conn: sqlite3.Connection) -> Sequence[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    cur = conn.execute("SELECT id, ticker, date, pattern FROM analysis_findings")
    return cur.fetchall()


def normalize_pattern(pattern: str | None) -> str:
    return (pattern or "").strip().lower()


def main(db_path: Path, dry_run: bool = False) -> None:
    conn = sqlite3.connect(db_path)
    try:
        ensure_candle_pattern_column(conn)
        divergence_days = load_divergence_days(conn)
        rows = fetch_findings(conn)

        base_candidates: Dict[Tuple[str, str], List[Tuple[int, int]]] = {}
        for row in rows:
            base_code = BASE_PATTERN_CODES.get(normalize_pattern(row["pattern"]), 0)
            if base_code in {1, 2, 3, 4, 5, 6}:
                base_candidates.setdefault((row["ticker"], row["date"]), []).append(
                    (base_code, row["id"])
                )

        # Valitse päivän pienin kynttiläkoodi komboksi jos divergenssi t0 tai t-1
        combo_target: Dict[int, int] = {}
        for key, items in base_candidates.items():
            ticker, date_str = key
            if key in divergence_days:
                base_code, row_id = min(items, key=lambda x: x[0])
                combo_target[row_id] = base_code
                continue

            # tarkista t-1
            try:
                from datetime import date, timedelta

                dt = date.fromisoformat(date_str)
                prev_day = (dt - timedelta(days=1)).isoformat()
            except Exception:
                prev_day = None

            if prev_day and (ticker, prev_day) in divergence_days:
                base_code, row_id = min(items, key=lambda x: x[0])
                combo_target[row_id] = base_code

        updates: List[Tuple[int, str, int]] = []
        combo_counts: Dict[int, int] = {}
        combo_name_to_base = {name.lower(): base for base, name in COMBO_NAME_BY_BASE.items()}
        for row in rows:
            pattern_raw = row["pattern"] or ""
            norm = normalize_pattern(pattern_raw)
            existing_code = row["candle_pattern"] if "candle_pattern" in row.keys() else None

            # Jätä valmiit kombot ennalleen
            if isinstance(existing_code, int) and existing_code in {71, 72, 73, 74, 75, 76}:
                updates.append((existing_code, pattern_raw, row["id"]))
                continue
            if norm in combo_name_to_base:
                base = combo_name_to_base[norm]
                candle_code = base + 70
                updates.append((candle_code, pattern_raw, row["id"]))
                combo_counts[candle_code] = combo_counts.get(candle_code, 0) + 1
                continue

            base_code = BASE_PATTERN_CODES.get(norm, existing_code if isinstance(existing_code, int) else 0)
            candle_code = base_code
            pattern_text = pattern_raw

            if row["id"] in combo_target:
                base = combo_target[row["id"]]
                candle_code = base + 70
                pattern_text = COMBO_NAME_BY_BASE[base]
                combo_counts[candle_code] = combo_counts.get(candle_code, 0) + 1

            updates.append((candle_code, pattern_text, row["id"]))

        if dry_run:
            print(f"[dry-run] Rows to update: {len(updates)}")
            print(f"[dry-run] Combo rows: {sum(combo_counts.values())} -> {combo_counts}")
            return

        conn.executemany(
            "UPDATE analysis_findings SET candle_pattern = ?, pattern = ? WHERE id = ?",
            updates,
        )
        conn.commit()

        print(f"Päivitetty rivejä: {len(updates)}")
        if combo_counts:
            print("Kombokoodit päivitetty:", combo_counts)
        else:
            print("Ei yhdistettäviä kynttilöitä löytynyt divergence-päiviltä.")
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Nosta analysis_findings-taulun kynttiläkoodit kombomuotoon (71–76) divergence-päiville."
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
        help="Älä kirjoita muutoksia, raportoi vain päivitettävien rivien määrät.",
    )
    args = parser.parse_args()
    main(args.db, dry_run=args.dry_run)
