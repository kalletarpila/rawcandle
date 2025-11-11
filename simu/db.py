from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import datetime as _dt

from . import config
from .utils import ensure_upper_ticker, parse_iso_date


@dataclass(frozen=True)
class AnalysisEvent:
    ticker: str
    date: _dt.date
    pattern_key: str
    raw_pattern: str
    strength: float


@dataclass(frozen=True)
class PriceRow:
    date: _dt.date
    open: float
    high: float
    low: float
    close: float
    volume: float


class AnalysisRepository:
    """Access layer for analysis findings."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or config.ANALYSIS_DB_PATH)
        self._conn: Optional[sqlite3.Connection] = None
        self._pattern_column: str = "pattern"
        self._strength_column: Optional[str] = None
        self._initialise_metadata()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _initialise_metadata(self) -> None:
        conn = self._get_connection()
        cursor = conn.execute("PRAGMA table_info(analysis_findings)")
        columns = [row["name"] for row in cursor.fetchall()]
        if "pattern" in columns:
            self._pattern_column = "pattern"
        elif "candle" in columns:
            self._pattern_column = "candle"
        else:
            raise RuntimeError("analysis_findings table lacks pattern/candle column")
        if "signal_strength" in columns:
            self._strength_column = "signal_strength"

    def fetch_events(
        self,
        ticker: str,
        start_date: _dt.date,
        end_date: _dt.date,
    ) -> list[AnalysisEvent]:
        ticker = ensure_upper_ticker(ticker)
        conn = self._get_connection()
        strength_select = (
            f"{self._strength_column} AS signal_strength"
            if self._strength_column
            else "NULL AS signal_strength"
        )
        query = f"""
            SELECT
                ticker,
                date,
                {self._pattern_column} AS pattern_value,
                {strength_select}
            FROM analysis_findings
            WHERE ticker = ?
              AND date BETWEEN ? AND ?
            ORDER BY date ASC
        """
        rows = conn.execute(
            query, (ticker, start_date.isoformat(), end_date.isoformat())
        ).fetchall()
        events: list[AnalysisEvent] = []
        for row in rows:
            pattern_raw = (row["pattern_value"] or "").strip()
            strength = row["signal_strength"]
            if strength is None:
                strength = 1.0 if pattern_raw.lower() == "downtrend" else 0.0
            events.append(
                AnalysisEvent(
                    ticker=ticker,
                    date=parse_iso_date(row["date"]),
                    pattern_key=config.DB_PATTERN_TO_KEY.get(
                        pattern_raw.lower(), pattern_raw.lower()
                    ),
                    raw_pattern=pattern_raw,
                    strength=float(strength),
                )
            )
        return events

    def fetch_divergences(
        self,
        ticker: str,
        start_date: _dt.date,
        end_date: _dt.date,
    ) -> list[AnalysisEvent]:
        """Fetch bullish and bearish divergences from divergence_data table."""
        ticker = ensure_upper_ticker(ticker)
        conn = self._get_connection()
        query = """
            SELECT
                ticker,
                date,
                bullish_strength,
                bearish_strength
            FROM divergence_data
            WHERE ticker = ?
              AND date BETWEEN ? AND ?
            ORDER BY date ASC
        """
        rows = conn.execute(
            query, (ticker, start_date.isoformat(), end_date.isoformat())
        ).fetchall()
        events: list[AnalysisEvent] = []
        for row in rows:
            bullish = float(row["bullish_strength"] or 0.0)
            bearish = float(row["bearish_strength"] or 0.0)

            # Add bullish divergence event if strength > 0
            if bullish > 0:
                events.append(
                    AnalysisEvent(
                        ticker=ticker,
                        date=parse_iso_date(row["date"]),
                        pattern_key="bullish_divergence",
                        raw_pattern="Bullish Divergence",
                        strength=bullish,
                    )
                )

            # Add bearish divergence event if strength > 0
            if bearish > 0:
                events.append(
                    AnalysisEvent(
                        ticker=ticker,
                        date=parse_iso_date(row["date"]),
                        pattern_key="bearish_divergence",
                        raw_pattern="Bearish Divergence",
                        strength=bearish,
                    )
                )

        return events


class PriceSeries:
    """Helper around price rows with date-based lookup utilities."""

    def __init__(self, rows: Iterable[PriceRow]) -> None:
        ordered = sorted(rows, key=lambda r: r.date)
        self._rows = ordered
        self._index = {row.date: idx for idx, row in enumerate(ordered)}

    def __len__(self) -> int:
        return len(self._rows)

    def dates(self) -> list[_dt.date]:
        return [row.date for row in self._rows]

    def rows(self) -> list[PriceRow]:
        return list(self._rows)

    def between(self, start: _dt.date, end: _dt.date) -> list[PriceRow]:
        return [row for row in self._rows if start <= row.date <= end]

    def dates_between(self, start: _dt.date, end: _dt.date) -> list[_dt.date]:
        return [row.date for row in self._rows if start <= row.date <= end]

    def get(self, date_value: _dt.date) -> Optional[PriceRow]:
        idx = self._index.get(date_value)
        if idx is None:
            return None
        return self._rows[idx]

    def next_date(self, current: _dt.date) -> Optional[_dt.date]:
        idx = self._index.get(current)
        if idx is None:
            return None
        if idx + 1 >= len(self._rows):
            return None
        return self._rows[idx + 1].date

    def next_date_within(
        self, current: _dt.date, end_date: _dt.date
    ) -> Optional[_dt.date]:
        idx = self._index.get(current)
        if idx is None:
            return None
        for row in self._rows[idx + 1 :]:
            if row.date <= end_date:
                return row.date
            break
        return None

    def previous_on_or_before(self, date_value: _dt.date) -> Optional[PriceRow]:
        candidates = [row for row in self._rows if row.date <= date_value]
        return candidates[-1] if candidates else None

    def previous_closes(self, date_value: _dt.date, days: int) -> list[float]:
        if days <= 0:
            return []
        idx = self._index.get(date_value)
        if idx is None:
            return []
        start = max(0, idx - days)
        return [self._rows[i].close for i in range(start, idx)]


class PriceRepository:
    """Access layer for historical price data."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or config.PRICE_DB_PATH)
        self._conn: Optional[sqlite3.Connection] = None
        self._ticker_column = "osake"
        self._date_column = "pvm"
        self._open_column = "open"
        self._high_column = "high"
        self._low_column = "low"
        self._close_column = "close"
        self._volume_column = "volume"
        self._initialise_metadata()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            self._conn = conn
        return self._conn

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def _initialise_metadata(self) -> None:
        conn = self._get_connection()
        cursor = conn.execute("PRAGMA table_info(osakedata)")
        columns = {row["name"] for row in cursor.fetchall()}
        # Support possible alternative column names
        if "ticker" in columns:
            self._ticker_column = "ticker"
        if "date" in columns:
            self._date_column = "date"
        if "open_price" in columns:
            self._open_column = "open_price"
        if "high_price" in columns:
            self._high_column = "high_price"
        if "low_price" in columns:
            self._low_column = "low_price"
        if "close_price" in columns:
            self._close_column = "close_price"
        if "volume" not in columns and "vol" in columns:
            self._volume_column = "vol"

    def fetch_price_series(self, ticker: str) -> PriceSeries:
        ticker = ensure_upper_ticker(ticker)
        conn = self._get_connection()
        query = f"""
            SELECT
                {self._date_column} AS date_value,
                {self._open_column} AS open_value,
                {self._high_column} AS high_value,
                {self._low_column} AS low_value,
                {self._close_column} AS close_value,
                {self._volume_column} AS volume_value
            FROM osakedata
            WHERE {self._ticker_column} = ?
            ORDER BY {self._date_column} ASC
        """
        rows = conn.execute(query, (ticker,)).fetchall()
        price_rows: list[PriceRow] = []
        for row in rows:
            try:
                date_value = parse_iso_date(row["date_value"])
                open_val = row["open_value"]
                high_val = row["high_value"]
                low_val = row["low_value"]
                close_val = row["close_value"]
                volume_val = row["volume_value"]

                if None in (open_val, high_val, low_val, close_val, volume_val):
                    continue

                price_rows.append(
                    PriceRow(
                        date=date_value,
                        open=float(open_val),
                        high=float(high_val),
                        low=float(low_val),
                        close=float(close_val),
                        volume=float(volume_val),
                    )
                )
            except (TypeError, ValueError):
                continue

        return PriceSeries(price_rows)
