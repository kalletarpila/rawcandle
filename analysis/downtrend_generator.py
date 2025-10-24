"""Downtrend event generator for analysis_findings.

This module generates realistic analysis events by finding actual downtrend patterns
in real stock data from osakedata.db and storing them to analysis.db.
"""

import sqlite3
import random
from typing import Optional, Callable, Dict, List, Tuple
from datetime import datetime, date
import logging


logger = logging.getLogger(__name__)


class DowntrendGenerator:
    """Generates downtrend events from real stock data."""

    def __init__(
        self,
        stock_db_path: str = "data/osakedata.db",
        analysis_db_path: str = "analysis/analysis.db",
    ):
        """Initialize generator with database paths.

        Args:
            stock_db_path: Path to stock data database (osakedata.db)
            analysis_db_path: Path to analysis database (analysis.db)
        """
        self.stock_db_path = stock_db_path
        self.analysis_db_path = analysis_db_path
        self.logger = logging.getLogger(__name__)

    def _get_stock_connection(self) -> sqlite3.Connection:
        """Get connection to stock database."""
        try:
            conn = sqlite3.connect(self.stock_db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            self.logger.error(f"Failed to connect to stock database: {e}")
            raise

    def _get_analysis_connection(self) -> sqlite3.Connection:
        """Get connection to analysis database."""
        try:
            conn = sqlite3.connect(self.analysis_db_path)
            conn.row_factory = sqlite3.Row
            return conn
        except Exception as e:
            self.logger.error(f"Failed to connect to analysis database: {e}")
            raise

    def _select_random_ticker(self, conn: sqlite3.Connection) -> Optional[str]:
        """Select a random ticker from stock database.

        Args:
            conn: Database connection

        Returns:
            Random ticker symbol or None if error
        """
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT osake 
                FROM osakedata 
                WHERE pvm >= '2024-01-01'
                ORDER BY RANDOM() 
                LIMIT 1
            """
            )
            row = cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            self.logger.error(f"Failed to select random ticker: {e}")
            return None

    def _get_price_data(
        self,
        conn: sqlite3.Connection,
        ticker: str,
        target_date: str,
        days_back: int = 10,
    ) -> Optional[List[Dict]]:
        """Get historical price data for a ticker around a specific date.

        Args:
            conn: Database connection
            ticker: Stock ticker symbol
            target_date: Target date (t0)
            days_back: Number of days to fetch before target date

        Returns:
            List of price records sorted by date (oldest first), or None if insufficient data
        """
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT pvm, open, high, low, close, volume
                FROM osakedata
                WHERE osake = ?
                  AND pvm <= ?
                ORDER BY pvm DESC
                LIMIT ?
            """,
                (ticker, target_date, days_back + 1),
            )

            rows = cursor.fetchall()
            if len(rows) < days_back + 1:
                return None

            # Reverse to get chronological order (oldest first)
            return [dict(row) for row in reversed(rows)]
        except Exception as e:
            self.logger.error(f"Failed to get price data for {ticker}: {e}")
            return None

    def _check_downtrend_criteria(self, price_data: List[Dict]) -> bool:
        """Check if price data meets all three downtrend criteria.

        Args:
            price_data: List of 11 price records [t-10, t-9, ..., t-1, t0]

        Returns:
            True if all criteria are met
        """
        if len(price_data) != 11:
            return False

        # Extract closing prices
        closes = [d["close"] for d in price_data]

        # Criterion 1: Progressive decline (strictly decreasing at checkpoints)
        # t-10 > t-5 > t-2 > t0
        t_minus_10 = closes[0]  # index 0
        t_minus_5 = closes[5]  # index 5
        t_minus_2 = closes[8]  # index 8
        t0 = closes[10]  # index 10

        if not (t_minus_10 > t_minus_5 > t_minus_2 > t0):
            return False

        # Criterion 2: Minimum 3% drop over 10 days
        drop_pct = ((t_minus_10 - t0) / t_minus_10) * 100
        if drop_pct < 3.0:
            return False

        # Criterion 3: Moving average filter
        # MA5 = average of [t-5, t-4, t-3, t-2, t-1] (indices 5-9)
        # MA10 = average of [t-10, t-9, ..., t-2, t-1] (indices 0-9)
        ma5_closes = closes[5:10]  # [t-5, t-4, t-3, t-2, t-1]
        ma10_closes = closes[0:10]  # [t-10, t-9, ..., t-2, t-1]

        ma5 = sum(ma5_closes) / len(ma5_closes)
        ma10 = sum(ma10_closes) / len(ma10_closes)

        # Both conditions must be true: close(t0) < MA10 AND MA5 < MA10
        if not (t0 < ma10 and ma5 < ma10):
            return False

        return True

    def _save_to_analysis(
        self, conn: sqlite3.Connection, ticker: str, price_record: Dict
    ) -> bool:
        """Save downtrend event to analysis database.

        Args:
            conn: Analysis database connection
            ticker: Stock ticker
            price_record: Price data for the event (t0)

        Returns:
            True if save succeeded
        """
        try:
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO analysis_findings (
                    ticker, date, pattern, signal_strength
                ) VALUES (?, ?, ?, ?)
            """,
                (
                    ticker,
                    price_record["pvm"],
                    "downtrend",
                    1.0,
                ),
            )

            conn.commit()
            return True
        except Exception as e:
            self.logger.error(f"Failed to save to analysis: {e}")
            return False

    def _get_ticker_dates(self, conn: sqlite3.Connection, ticker: str) -> List[str]:
        """Get all dates for a ticker starting from 2024-01-01.

        Args:
            conn: Database connection
            ticker: Stock ticker

        Returns:
            List of dates (as strings)
        """
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT pvm
                FROM osakedata
                WHERE osake = ?
                  AND pvm >= '2024-01-01'
                ORDER BY pvm
            """,
                (ticker,),
            )

            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to get dates for {ticker}: {e}")
            return []

    def generate_random_findings(
        self,
        num_tickers: int = 100,
        events_per_ticker: int = 20,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        cancel_check: Optional[Callable[[], bool]] = None,
    ) -> Tuple[int, List[str]]:
        """Generate downtrend events from real stock data.

        This function:
        1. Selects random stocks from osakedata.db
        2. Finds dates that meet downtrend criteria
        3. Saves matching events to analysis.db

        Downtrend criteria (all three required):
        1. Progressive decline: close(t-10) > close(t-5) > close(t-2) > close(t0)
        2. Minimum 3% drop: ((close(t-10) - close(t0)) / close(t-10)) * 100 >= 3
        3. MA filter: close(t0) < MA10 AND MA5 < MA10
           where MA5 = avg([t-5..t-1]), MA10 = avg([t-10..t-1])

        Args:
            num_tickers: Number of stocks to process (1..1000)
            events_per_ticker: Target events per stock (1..200)
            progress_callback: Optional callback(current, total) for progress updates
            cancel_check: Optional callback() -> bool to check if user cancelled

        Returns:
            Tuple of (total_events_saved, list_of_error_messages)
        """
        # Validate inputs
        num_tickers = max(1, min(1000, int(num_tickers)))
        events_per_ticker = max(1, min(200, int(events_per_ticker)))

        total_saved = 0
        errors = []

        try:
            stock_conn = self._get_stock_connection()
            analysis_conn = self._get_analysis_connection()
        except Exception as e:
            errors.append(f"Database connection failed: {e}")
            return 0, errors

        try:
            for ticker_idx in range(num_tickers):
                # Check for cancellation
                if cancel_check and cancel_check():
                    self.logger.info("Generation cancelled by user")
                    break

                # Update progress
                if progress_callback:
                    progress_callback(ticker_idx, num_tickers)

                # Select random ticker
                ticker = self._select_random_ticker(stock_conn)
                if not ticker:
                    errors.append(f"Failed to select ticker {ticker_idx + 1}")
                    continue

                # Get all available dates for this ticker
                available_dates = self._get_ticker_dates(stock_conn, ticker)
                if len(available_dates) < 11:
                    errors.append(f"Ticker {ticker}: insufficient data (< 11 days)")
                    continue

                # Try to find downtrend events
                events_found = 0
                attempts = 0
                max_attempts = 500

                while events_found < events_per_ticker and attempts < max_attempts:
                    # Check for cancellation
                    if cancel_check and cancel_check():
                        break

                    attempts += 1

                    # Select random date (must have at least 10 days before it)
                    # Skip first 10 dates to ensure we have t-10 data
                    if len(available_dates) < 11:
                        break

                    target_date = random.choice(available_dates[10:])

                    # Get price data [t-10 ... t0]
                    price_data = self._get_price_data(
                        stock_conn, ticker, target_date, days_back=10
                    )

                    if not price_data:
                        continue

                    # Check downtrend criteria
                    if self._check_downtrend_criteria(price_data):
                        # Save to analysis database (t0 is the last record)
                        if self._save_to_analysis(
                            analysis_conn, ticker, price_data[-1]
                        ):
                            events_found += 1
                            total_saved += 1

                if events_found < events_per_ticker:
                    self.logger.info(
                        f"Ticker {ticker}: found only {events_found}/{events_per_ticker} "
                        f"events after {attempts} attempts"
                    )

            # Final progress update
            if progress_callback:
                progress_callback(num_tickers, num_tickers)

        except Exception as e:
            errors.append(f"Generation error: {e}")
            self.logger.error(f"Generation failed: {e}", exc_info=True)

        finally:
            stock_conn.close()
            analysis_conn.close()

        return total_saved, errors


def generate_random_findings(
    num_tickers: int = 100,
    events_per_ticker: int = 20,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    stock_db_path: str = "data/osakedata.db",
    analysis_db_path: str = "analysis/analysis.db",
) -> Tuple[int, List[str]]:
    """Convenience function for generating downtrend events.

    See DowntrendGenerator.generate_random_findings() for full documentation.

    Returns:
        Tuple of (total_events_saved, list_of_error_messages)
    """
    generator = DowntrendGenerator(stock_db_path, analysis_db_path)
    return generator.generate_random_findings(
        num_tickers=num_tickers,
        events_per_ticker=events_per_ticker,
        progress_callback=progress_callback,
        cancel_check=cancel_check,
    )
