#!/usr/bin/env python3
"""
Täyttää Bullish Divergence -mittarit results_data-tauluun:
- BullDiv_strength
- BullDiv_recent_strength
- BullDiv_recent_offset
- Has_BullDiv_recent

Lähdedata: analysis_findings (ensisijainen) ja divergence_data (fallback).
Käyttää samaa 0…-5 päivän tarkasteluikkunaa kuin results_generator.

Oletus on dry-run; käytä --apply kirjoittaaksesi muutokset.
"""

from __future__ import annotations

import argparse
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

BULL_COLUMNS = [
    "BullDiv_strength",
    "BullDiv_recent_strength",
    "BullDiv_recent_offset",
    "Has_BullDiv_recent",
]

OFFSETS = [0, -1, -2, -3, -4, -5]
BULLISH_PATTERN = "Bullish Divergence"
BEARISH_PATTERN = "Bearish Divergence"


@dataclass
class DivergenceRecord:
    bullish_strength: float = 0.0
    bearish_strength: float = 0.0
    rsi: Optional[float] = None


@dataclass
class RowUpdate:
    row_id: int
    values: Dict[str, Optional[float]]


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cursor = conn.execute("PRAGMA table_info(results_data)")
    cols = {row[1] for row in cursor.fetchall()}
    missing = set(BULL_COLUMNS) - cols
    if missing:
        raise RuntimeError(f"results_data puuttuu sarakkeet: {sorted(missing)}")


def _dates_for_offsets(date_str: str) -> List[str]:
    base = datetime.strptime(date_str, "%Y-%m-%d").date()
    dates = []
    for offset in OFFSETS:
        d = base + timedelta(days=offset)
        dates.append(d.isoformat())
    return dates


def _fetch_results_rows(conn: sqlite3.Connection) -> Dict[str, List[Tuple[int, str, Optional[float]]]]:
    cursor = conn.execute("SELECT id, ticker, date, RSI14_t0 FROM results_data")
    grouped: Dict[str, List[Tuple[int, str, Optional[float]]]] = {}
    for row_id, ticker, date_str, rsi in cursor.fetchall():
        grouped.setdefault(ticker, []).append((row_id, date_str, rsi))
    return grouped


def _build_needed_dates(rows_by_ticker: Dict[str, List[Tuple[int, str, Optional[float]]]]) -> Dict[str, List[str]]:
    needed: Dict[str, List[str]] = {}
    for ticker, rows in rows_by_ticker.items():
        dates = set()
        for _, date_str, _ in rows:
            dates.update(_dates_for_offsets(date_str))
        needed[ticker] = sorted(dates)
    return needed


def _load_divergence_from_findings(
    conn: sqlite3.Connection, ticker: str, dates: List[str]
) -> Dict[str, DivergenceRecord]:
    if not dates:
        return {}
    placeholders = ",".join("?" * len(dates))
    query = f"""
        SELECT date, pattern, signal_strength, rsi14
        FROM analysis_findings
        WHERE ticker = ?
          AND date IN ({placeholders})
          AND pattern IN (?, ?)
    """
    params = [ticker] + dates + [BULLISH_PATTERN, BEARISH_PATTERN]
    cursor = conn.execute(query, params)
    records: Dict[str, DivergenceRecord] = {}
    for date_str, pattern, strength, rsi in cursor.fetchall():
        entry = records.setdefault(date_str, DivergenceRecord())
        if pattern == BULLISH_PATTERN:
            entry.bullish_strength = strength or 0.0
        elif pattern == BEARISH_PATTERN:
            entry.bearish_strength = strength or 0.0
        if rsi is not None:
            try:
                entry.rsi = float(rsi)
            except (TypeError, ValueError):
                pass
    return records


def _load_divergence_from_fallback(
    conn: sqlite3.Connection, ticker: str, dates: List[str], existing: Dict[str, DivergenceRecord]
) -> None:
    missing = [d for d in dates if d not in existing]
    if not missing:
        return
    placeholders = ",".join("?" * len(missing))
    query = f"""
        SELECT date, bullish_strength, bearish_strength, rsi
        FROM divergence_data
        WHERE ticker = ?
          AND date IN ({placeholders})
    """
    params = [ticker] + missing
    cursor = conn.execute(query, params)
    for date_str, bull, bear, rsi in cursor.fetchall():
        entry = existing.setdefault(date_str, DivergenceRecord())
        entry.bullish_strength = bull or 0.0
        entry.bearish_strength = bear or 0.0
        if rsi is not None:
            try:
                entry.rsi = float(rsi)
            except (TypeError, ValueError):
                pass


def _compute_metrics(
    date_str: str,
    rsi14_t0: Optional[float],
    divergence_records: Dict[str, DivergenceRecord],
) -> Dict[str, Optional[float]]:
    BullDiv_strength = 0.0
    BullDiv_recent_strength = 0.0
    BullDiv_recent_offset = -1
    rsi_values_by_offset: Dict[int, float] = {}

    for relative_offset in OFFSETS:
        check_date = (
            datetime.strptime(date_str, "%Y-%m-%d").date()
            + timedelta(days=relative_offset)
        ).isoformat()
        record = divergence_records.get(check_date)
        if not record:
            continue
        abs_offset = abs(relative_offset)
        bull = record.bullish_strength or 0.0

        if abs_offset == 0 and bull > 0:
            BullDiv_strength = bull

        if bull > BullDiv_recent_strength:
            BullDiv_recent_strength = bull

        if bull > 0 and BullDiv_recent_offset == -1:
            BullDiv_recent_offset = abs_offset

        if record.rsi is not None:
            rsi_values_by_offset[abs_offset] = record.rsi

    rsi_t0_value = rsi14_t0 if rsi14_t0 is not None else rsi_values_by_offset.get(0)
    rsi_t5_value = rsi_values_by_offset.get(5)
    if rsi_t0_value is not None and rsi_t5_value is not None:
        rsi_slope_5 = (rsi_t0_value - rsi_t5_value) / 5.0
    else:
        rsi_slope_5 = None

    Has_BullDiv_recent = 1 if BullDiv_recent_strength > 0 else 0
    if not Has_BullDiv_recent:
        BullDiv_recent_offset = -1

    return {
        "BullDiv_strength": BullDiv_strength,
        "BullDiv_recent_strength": BullDiv_recent_strength,
        "BullDiv_recent_offset": BullDiv_recent_offset,
        "Has_BullDiv_recent": Has_BullDiv_recent,
        "RSI_slope_5": rsi_slope_5,  # hyödyllinen täyttö, ei kirjoiteta oletuksena
    }


def build_updates(
    rows_by_ticker: Dict[str, List[Tuple[int, str, Optional[float]]]],
    findings_conn: sqlite3.Connection,
) -> List[RowUpdate]:
    needed_dates = _build_needed_dates(rows_by_ticker)
    updates: List[RowUpdate] = []

    for ticker, rows in rows_by_ticker.items():
        dates = needed_dates.get(ticker, [])
        divergence_map = _load_divergence_from_findings(findings_conn, ticker, dates)
        _load_divergence_from_fallback(findings_conn, ticker, dates, divergence_map)

        for row_id, date_str, rsi14 in rows:
            metrics = _compute_metrics(date_str, rsi14, divergence_map)
            updates.append(
                RowUpdate(
                    row_id=row_id,
                    values={
                        "BullDiv_strength": metrics["BullDiv_strength"],
                        "BullDiv_recent_strength": metrics["BullDiv_recent_strength"],
                        "BullDiv_recent_offset": metrics["BullDiv_recent_offset"],
                        "Has_BullDiv_recent": metrics["Has_BullDiv_recent"],
                    },
                )
            )

    return updates


def apply_updates(conn: sqlite3.Connection, updates: List[RowUpdate]) -> int:
    if not updates:
        return 0
    cursor = conn.cursor()
    set_clause = ", ".join(f"{col} = ?" for col in BULL_COLUMNS)
    total = 0
    for upd in updates:
        params = [upd.values.get(col) for col in BULL_COLUMNS] + [upd.row_id]
        cursor.execute(f"UPDATE results_data SET {set_clause} WHERE id = ?", params)
        total += cursor.rowcount
    conn.commit()
    return total


def backfill(db_path: Path, apply: bool = False) -> int:
    conn = sqlite3.connect(db_path)
    _ensure_columns(conn)
    rows_by_ticker = _fetch_results_rows(conn)
    updates = build_updates(rows_by_ticker, conn)

    if not apply:
        print(
            f"Kuivaharjoitus: {len(updates)} riviä tarvitsee päivityksen "
            f"({sum(len(v) for v in rows_by_ticker.values())} riviä luettu). "
            "Käytä --apply kirjoittaaksesi muutokset."
        )
        return 0

    applied = apply_updates(conn, updates)
    print(f"Päivitettiin {applied} riviä ({len(updates)} laskettu päivitys).")
    return applied


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Täytä BullDiv-mittarit results_data-tauluun (analysis_findings + divergence_data)."
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
