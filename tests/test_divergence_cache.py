"""
Test divergence cache functionality.
NOTE: DivergenceCache siirretty deprecated/-hakemistoon (ei käytössä tuotannossa)
"""

import sqlite3
import tempfile
from pathlib import Path
import pandas as pd
import pytest

from deprecated.divergence_cache import DivergenceCache


def test_divergence_cache_initialization():
    """Test that cache database is created correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_divers.db"
        cache = DivergenceCache(db_path=str(db_path))

        # Check database exists
        assert db_path.exists()

        # Check table exists
        with sqlite3.connect(db_path) as conn:
            cursor = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='divergence_cache'"
            )
            assert cursor.fetchone() is not None


def test_has_ticker():
    """Test ticker existence check."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = DivergenceCache(db_path=str(Path(tmpdir) / "test.db"))

        # Initially no ticker
        assert not cache.has_ticker("AAPL")

        # Add some data
        with sqlite3.connect(cache.db_path) as conn:
            conn.execute(
                "INSERT INTO divergence_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("AAPL", "2024-01-01", 50.0, 0, 0, 0, 0),
            )
            conn.commit()

        # Now ticker exists
        assert cache.has_ticker("AAPL")


def test_get_divergence_for_dates():
    """Test divergence lookup for multiple dates."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = DivergenceCache(db_path=str(Path(tmpdir) / "test.db"))

        # Add test data
        with sqlite3.connect(cache.db_path) as conn:
            conn.executemany(
                "INSERT INTO divergence_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("AAPL", "2024-01-01", 50.0, 0, 0, 0, 0),
                    (
                        "AAPL",
                        "2024-01-02",
                        52.0,
                        1,
                        0,
                        2.15,
                        0,
                    ),  # Bullish divergence strength 2.15
                    ("AAPL", "2024-01-03", 48.0, 0, 0, 0, 0),
                    ("AAPL", "2024-01-04", 45.0, 0, 0, 0, 0),
                ],
            )
            conn.commit()

        # Test: bullish found on t-1 with strength 2.15
        bearish, bullish = cache.get_divergence_for_dates(
            "AAPL", ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
        )
        assert bullish == 2.15  # Strength value
        assert bearish == 0  # Mutual exclusivity


def test_mutual_exclusivity():
    """Test that if one divergence is found, the other is 0."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = DivergenceCache(db_path=str(Path(tmpdir) / "test.db"))

        # Add data with bearish divergence
        with sqlite3.connect(cache.db_path) as conn:
            conn.executemany(
                "INSERT INTO divergence_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("MSFT", "2024-01-01", 50.0, 0, 0, 0, 0),
                    (
                        "MSFT",
                        "2024-01-02",
                        52.0,
                        0,
                        1,
                        0,
                        2.87,
                    ),  # Bearish divergence strength 2.87
                    ("MSFT", "2024-01-03", 48.0, 0, 0, 0, 0),
                    ("MSFT", "2024-01-04", 45.0, 0, 0, 0, 0),
                ],
            )
            conn.commit()

        # Test: bearish found with strength 2.87
        bearish, bullish = cache.get_divergence_for_dates(
            "MSFT", ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
        )
        assert bearish == 2.87  # Strength value
        assert bullish == 0  # Mutual exclusivity


def test_no_divergence():
    """Test when no divergence is found."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = DivergenceCache(db_path=str(Path(tmpdir) / "test.db"))

        # Add data with no divergences
        with sqlite3.connect(cache.db_path) as conn:
            conn.executemany(
                "INSERT INTO divergence_cache VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("TSLA", "2024-01-01", 50.0, 0, 0, 0, 0),
                    ("TSLA", "2024-01-02", 52.0, 0, 0, 0, 0),
                    ("TSLA", "2024-01-03", 48.0, 0, 0, 0, 0),
                    ("TSLA", "2024-01-04", 45.0, 0, 0, 0, 0),
                ],
            )
            conn.commit()

        # Test: no divergence
        bearish, bullish = cache.get_divergence_for_dates(
            "TSLA", ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
        )
        assert bearish == 0
        assert bullish == 0


def test_empty_dates():
    """Test with empty date list."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = DivergenceCache(db_path=str(Path(tmpdir) / "test.db"))

        bearish, bullish = cache.get_divergence_for_dates("AAPL", [])
        assert bearish == 0
        assert bullish == 0


def test_calculate_and_cache_ticker():
    """Test the full calculate_and_cache_ticker flow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache = DivergenceCache(db_path=str(Path(tmpdir) / "test.db"))

        # Create sample data
        dates = pd.date_range("2024-01-01", periods=60, freq="D")
        df = pd.DataFrame(
            {
                "pvm": dates,
                "Close": [100 + i * 0.5 for i in range(60)],  # Gradually increasing
            }
        )

        # This should not raise any errors
        cache.calculate_and_cache_ticker(
            ticker="TEST",
            df=df,
            date_col="pvm",
            close_col="Close",
            lookback_days=30,
            rsi_period=14,
            min_rsi_change=3.0,
            sensitivity_days=7,
        )

        # Verify ticker was cached
        assert cache.has_ticker("TEST")
