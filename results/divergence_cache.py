"""
Divergence Cache Manager

Manages a persistent SQLite database for storing RSI and divergence calculations.
This avoids recalculating divergences for the same ticker data repeatedly.
"""

import sqlite3
from pathlib import Path
import pandas as pd
from typing import Dict, Set, Tuple, Optional

from analysis.candlestick_patterns import (
    calculate_rsi,
    is_bullish_divergence,
    is_bearish_divergence,
)


class DivergenceCache:
    """Manages persistent cache for RSI and divergence data."""

    def __init__(self, db_path: str = "data/rsi_divers.db"):
        """Initialize cache with database path."""
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Create database table if it doesn't exist."""
        with sqlite3.connect(self.db_path) as conn:
            # Try to create table with new schema
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS divergence_cache (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    rsi REAL,
                    bullish_divergence INTEGER DEFAULT 0,
                    bearish_divergence INTEGER DEFAULT 0,
                    bullish_strength INTEGER DEFAULT 0,
                    bearish_strength INTEGER DEFAULT 0,
                    PRIMARY KEY (ticker, date)
                )
            """
            )

            # Check if strength columns exist, add them if not (for existing databases)
            cursor = conn.execute("PRAGMA table_info(divergence_cache)")
            columns = [row[1] for row in cursor.fetchall()]

            if "bullish_strength" not in columns:
                conn.execute(
                    "ALTER TABLE divergence_cache ADD COLUMN bullish_strength INTEGER DEFAULT 0"
                )

            if "bearish_strength" not in columns:
                conn.execute(
                    "ALTER TABLE divergence_cache ADD COLUMN bearish_strength INTEGER DEFAULT 0"
                )

            conn.commit()

    def has_ticker(self, ticker: str) -> bool:
        """Check if ticker exists in cache."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT COUNT(*) FROM divergence_cache WHERE ticker = ?", (ticker,)
            )
            count = cursor.fetchone()[0]
            return count > 0

    def get_divergences(self, ticker: str) -> Dict[str, Tuple[int, int]]:
        """
        Get divergence data for a ticker.

        Returns:
            Dict mapping date -> (bullish_divergence, bearish_divergence)
            where values are 0 or 1
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                """
                SELECT date, bullish_divergence, bearish_divergence
                FROM divergence_cache
                WHERE ticker = ?
                ORDER BY date
            """,
                (ticker,),
            )

            result = {}
            for row in cursor.fetchall():
                date, bullish, bearish = row
                result[date] = (bullish, bearish)

            return result

    def calculate_and_cache_ticker(
        self,
        ticker: str,
        df: pd.DataFrame,
        date_col: str = "pvm",
        close_col: str = "close",
        lookback_days: int = 30,
        rsi_period: int = 14,
        min_rsi_change: float = 3.0,
        sensitivity_days: int = 7,
    ):
        """
        Calculate RSI and divergences for a ticker and cache results.

        Args:
            ticker: Stock ticker symbol
            df: DataFrame with stock data (must have date and close columns)
            date_col: Name of date column
            close_col: Name of close price column
            lookback_days: Days to look back for divergence detection
            rsi_period: RSI calculation period
            min_rsi_change: Minimum RSI change for divergence
            sensitivity_days: Days for local extremes detection
        """
        if df.empty:
            return

        # Calculate RSI
        df_with_rsi = calculate_rsi(df, period=rsi_period)

        if "RSI" not in df_with_rsi.columns:
            print(f"⚠️ RSI calculation failed for {ticker}")
            return

        # Prepare data for batch insert
        records = []

        for idx in range(len(df_with_rsi)):
            row = df_with_rsi.iloc[idx]
            date = str(row[date_col])
            rsi = row["RSI"]

            # Check for divergences at this point
            bullish = 0
            bearish = 0
            bullish_strength = 0
            bearish_strength = 0

            # Need enough data for divergence detection
            if idx >= lookback_days and not pd.isna(rsi):
                # Get historical window
                window_df = df_with_rsi.iloc[
                    max(0, idx - lookback_days) : idx + 1
                ].copy()

                if len(window_df) > sensitivity_days:
                    # Check bullish divergence
                    bullish_result = is_bullish_divergence(
                        window_df,
                        idx_in_window=len(window_df) - 1,
                        lookback_days=lookback_days,
                        min_rsi_gain=min_rsi_change,
                        min_days_between=3,
                    )

                    if bullish_result and bullish_result.get("found"):
                        bullish = 1
                        bullish_strength = bullish_result.get("strength", 1)

                    # Check bearish divergence (only if no bullish)
                    else:
                        bearish_result = is_bearish_divergence(
                            window_df,
                            idx_in_window=len(window_df) - 1,
                            lookback_days=lookback_days,
                            min_rsi_loss=min_rsi_change,
                            min_days_between=3,
                        )

                        if bearish_result and bearish_result.get("found"):
                            bearish = 1
                            bearish_strength = bearish_result.get("strength", 1)

            records.append(
                (
                    ticker,
                    date,
                    rsi,
                    bullish,
                    bearish,
                    bullish_strength,
                    bearish_strength,
                )
            )

        # Batch insert to database
        with sqlite3.connect(self.db_path) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO divergence_cache 
                (ticker, date, rsi, bullish_divergence, bearish_divergence, bullish_strength, bearish_strength)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                records,
            )
            conn.commit()

        print(f"✅ Cached {len(records)} divergence records for {ticker}")

    def get_divergence_for_dates(
        self,
        ticker: str,
        dates: list,
    ) -> Tuple[int, int]:
        """
        Check if divergence occurred on any of the given dates.

        Args:
            ticker: Stock ticker
            dates: List of date strings to check

        Returns:
            Tuple (bearish_strength, bullish_strength) where:
            - bearish_strength = strength (1-3) if bearish divergence found, else 0
            - bullish_strength = strength (1-3) if bullish divergence found, else 0
            - Mutual exclusivity: if one is > 0, the other is automatically 0
        """
        if not dates:
            return (0, 0)

        placeholders = ",".join("?" * len(dates))
        query = f"""
            SELECT bullish_divergence, bearish_divergence, bullish_strength, bearish_strength
            FROM divergence_cache
            WHERE ticker = ? AND date IN ({placeholders})
        """

        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(query, [ticker] + dates)
            results = cursor.fetchall()

        # Find the strongest divergence across all dates
        max_bullish_strength = 0
        max_bearish_strength = 0

        for row in results:
            bullish, bearish, bullish_str, bearish_str = row
            if bullish == 1 and bullish_str > max_bullish_strength:
                max_bullish_strength = bullish_str
            if bearish == 1 and bearish_str > max_bearish_strength:
                max_bearish_strength = bearish_str

        # Mutual exclusivity: if one is found, the other must be 0
        # Return in order: (bearish_strength, bullish_strength) to match Excel column order
        if max_bullish_strength > 0:
            return (0, max_bullish_strength)
        elif max_bearish_strength > 0:
            return (max_bearish_strength, 0)
        else:
            return (0, 0)
            return (0, 0)

    def clear_ticker(self, ticker: str):
        """Remove all cached data for a ticker."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM divergence_cache WHERE ticker = ?", (ticker,))
            conn.commit()

    def clear_all(self):
        """Clear entire cache."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM divergence_cache")
            conn.commit()
