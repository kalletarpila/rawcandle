"""Downtrend event generator for analysis_findings.

This module generates realistic analysis events by finding actual downtrend patterns
in real stock data from osakedata.db and storing them to analysis.db.
"""

import sqlite3
import random
from typing import Optional, Callable, Dict, List, Tuple
from datetime import datetime, date
import logging
import pandas as pd

from analysis.database_manager import DatabaseManager
from analysis.candlestick_patterns import calculate_rsi


logger = logging.getLogger(__name__)


class DowntrendGenerator:
    """Generates downtrend events from real stock data."""

    MIN_DOWNTREND_HISTORY = 10
    RSI_PERIOD = 14

    def __init__(
        self,
        stock_db_path: str = "data/osakedata.db",
        analysis_db_path: str = "data/analysis.db",
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

    def _select_random_tickers(
        self, conn: sqlite3.Connection, num_tickers: int
    ) -> List[str]:
        """Select multiple random tickers from stock database.

        Args:
            conn: Database connection
            num_tickers: Number of unique tickers to select

        Returns:
            List of unique ticker symbols
        """
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DISTINCT osake 
                FROM osakedata 
                WHERE pvm >= '2024-01-01'
                ORDER BY RANDOM() 
                LIMIT ?
            """,
                (num_tickers,),
            )
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            self.logger.error(f"Failed to select random tickers: {e}")
            return []

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
        self,
        db_manager: DatabaseManager,
        ticker: str,
        price_record: Dict,
        stock_conn: sqlite3.Connection,
    ) -> bool:
        """Save downtrend event to analysis database using DatabaseManager.

        Args:
            db_manager: DatabaseManager instance
            ticker: Stock ticker
            price_record: Price data for the event (t0)
            stock_conn: Connection to stock database for RSI calculation

        Returns:
            True if save succeeded
        """
        try:
            # Laske RSI14 t0-päivämäärälle
            rsi14 = self._calculate_rsi14(stock_conn, ticker, price_record["pvm"])

            return db_manager.save_finding(
                ticker=ticker,
                date=price_record["pvm"],
                pattern="downtrend",
                signal_strength=1.0,
                rsi14=rsi14,
            )
        except Exception as e:
            self.logger.error(f"Failed to save to analysis: {e}")
            return False

    def _backfill_missing_rsi(
        self, db_manager: DatabaseManager, stock_conn: sqlite3.Connection
    ) -> int:
        """
        Backfill RSI14 values for downtrend findings that are missing it.

        Args:
            db_manager: DatabaseManager instance
            stock_conn: Connection to stock database for RSI calculation

        Returns:
            Number of findings successfully updated
        """
        try:
            conn = db_manager.get_connection()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, ticker, date
                FROM analysis_findings
                WHERE pattern = 'downtrend' AND (rsi14 IS NULL OR rsi14 = '')
                ORDER BY date
            """
            )
            rows = cursor.fetchall()
            if not rows:
                return 0

            updated = 0
            skipped = 0
            for row in rows:
                ticker = row["ticker"]
                date_value = row["date"]
                rsi14 = self._calculate_rsi14(stock_conn, ticker, date_value)
                if rsi14 is None:
                    skipped += 1
                    continue
                if db_manager.update_finding(row["id"], rsi14=rsi14):
                    updated += 1

            if updated:
                self.logger.info(
                    f"Backfilled RSI14 for {updated} downtrend findings (skipped {skipped})"
                )
            else:
                self.logger.info(
                    "No RSI14 values were backfilled for downtrend findings (all calculations failed)"
                )
            return updated

        except Exception as e:
            self.logger.error(f"Failed to backfill RSI14 values: {e}", exc_info=True)
            return 0

    def _calculate_rsi14(
        self, conn: sqlite3.Connection, ticker: str, target_date: str
    ) -> Optional[float]:
        """Calculate RSI(14) for a specific date.

        Args:
            conn: Database connection
            ticker: Stock ticker
            target_date: Target date (YYYY-MM-DD)

        Returns:
            RSI(14) value or None if calculation fails
        """
        try:
            period = self.RSI_PERIOD

            # Hae hintadata (tarvitaan vähintään RSI_PERIOD päivää)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT pvm, close
                FROM osakedata
                WHERE osake = ? AND pvm <= ?
                ORDER BY pvm DESC
                LIMIT 50
            """,
                (ticker, target_date),
            )

            rows = cursor.fetchall()
            if len(rows) < period:
                return None

            # Muunna pandas DataFrameksi
            df = pd.DataFrame(rows, columns=["pvm", "Close"])
            df = df.sort_values("pvm").reset_index(drop=True)

            # Laske RSI
            df = calculate_rsi(df, period=period, close_col="Close")

            # Hae RSI arvo target_date:lle
            target_row = df[df["pvm"] == target_date]
            if target_row.empty:
                return None

            rsi_value = target_row.iloc[0].get("RSI")
            return float(rsi_value) if pd.notna(rsi_value) else None

        except Exception as e:
            self.logger.warning(
                f"RSI14 calculation failed for {ticker} {target_date}: {e}"
            )
            return None

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
            db_manager = DatabaseManager(self.analysis_db_path)
        except Exception as e:
            errors.append(f"Database connection failed: {e}")
            return 0, errors

        try:
            # Valitse ensin kaikki tickerit kerralla
            tickers = self._select_random_tickers(stock_conn, num_tickers)
            if not tickers:
                errors.append("Failed to select any tickers")
                return 0, errors

            self.logger.info(
                f"Selected {len(tickers)} unique tickers for event generation"
            )

            for ticker_idx, ticker in enumerate(tickers):
                # Check for cancellation
                if cancel_check and cancel_check():
                    self.logger.info("Generation cancelled by user")
                    break

                # Update progress
                if progress_callback:
                    progress_callback(ticker_idx, len(tickers))

                # Get all available dates for this ticker
                available_dates = self._get_ticker_dates(stock_conn, ticker)
                if len(available_dates) < 11:
                    errors.append(f"Ticker {ticker}: insufficient data (< 11 days)")
                    continue

                # Try to find downtrend events
                events_found = 0
                attempts = 0
                max_attempts = 500
                used_dates = set()  # Pidä kirjaa jo käytetyistä päivämääristä

                while events_found < events_per_ticker and attempts < max_attempts:
                    # Check for cancellation
                    if cancel_check and cancel_check():
                        break

                    attempts += 1

                    # Select random date (must have at least 10 days before it)
                    # Skip first 10 dates to ensure we have t-10 data
                    if len(available_dates) < 11:
                        break

                    # Valitse päivämäärä jota ei ole vielä käytetty
                    history_offset = max(
                        self.MIN_DOWNTREND_HISTORY, self.RSI_PERIOD
                    )
                    available_unused_dates = [
                        d for d in available_dates[history_offset:] if d not in used_dates
                    ]

                    # Jos kaikki päivämäärät on käytetty, lopeta
                    if not available_unused_dates:
                        self.logger.info(
                            f"Ticker {ticker}: all available dates exhausted after {events_found} events"
                        )
                        break

                    target_date = random.choice(available_unused_dates)
                    used_dates.add(target_date)  # Merkitse päivämäärä käytetyksi

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
                            db_manager, ticker, price_data[-1], stock_conn
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
                progress_callback(len(tickers), len(tickers))

            # Backfill RSI14 for any existing downtrend findings missing it
            try:
                backfilled = self._backfill_missing_rsi(db_manager, stock_conn)
                if backfilled:
                    self.logger.info(
                        f"RSI14 backfill completed for {backfilled} existing downtrend findings"
                    )
            except Exception:
                # Detailed error already logged inside helper
                pass

        except Exception as e:
            errors.append(f"Generation error: {e}")
            self.logger.error(f"Generation failed: {e}", exc_info=True)

        finally:
            stock_conn.close()
            db_manager.close()

        return total_saved, errors


def generate_random_findings(
    num_tickers: int = 100,
    events_per_ticker: int = 20,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
    stock_db_path: str = "data/osakedata.db",
    analysis_db_path: str = "data/analysis.db",
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
