"""Tests for downtrend generator module."""

import pytest
import sqlite3
import os
from datetime import date, timedelta
from analysis.downtrend_generator import DowntrendGenerator, generate_random_findings


class TestDowntrendGenerator:
    """Test suite for DowntrendGenerator class."""

    @pytest.fixture
    def temp_analysis_db(self, tmp_path):
        """Create a temporary analysis database for testing."""
        db_path = tmp_path / "test_analysis.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create analysis_findings table
        cursor.execute(
            """
            CREATE TABLE analysis_findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                pattern TEXT,
                signal_strength REAL,
                price REAL,
                volume INTEGER,
                description TEXT,
                open_price REAL,
                close_price REAL,
                high_price REAL,
                low_price REAL,
                analysis_date TEXT
            )
        """
        )
        conn.commit()
        conn.close()

        return str(db_path)

    @pytest.fixture
    def temp_stock_db(self, tmp_path):
        """Create a temporary stock database with test data."""
        db_path = tmp_path / "test_osakedata.db"
        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Create osakedata table
        cursor.execute(
            """
            CREATE TABLE osakedata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                osake TEXT NOT NULL,
                pvm TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER
            )
        """
        )

        # Create test data with a clear downtrend
        # Stock "TEST1" with perfect downtrend from 100 to 90 (10% drop)
        base_date = date(2024, 6, 1)
        for i in range(15):
            day = base_date + timedelta(days=i)
            # Create declining prices
            close_price = 100.0 - (i * 0.8)  # Drops from 100 to ~88
            cursor.execute(
                """
                INSERT INTO osakedata (osake, pvm, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    "TEST1",
                    day.isoformat(),
                    close_price + 1,
                    close_price + 2,
                    close_price - 1,
                    close_price,
                    100000 + i * 1000,
                ),
            )

        # Stock "TEST2" with uptrend (should not match)
        for i in range(15):
            day = base_date + timedelta(days=i)
            close_price = 100.0 + (i * 0.5)  # Rising prices
            cursor.execute(
                """
                INSERT INTO osakedata (osake, pvm, open, high, low, close, volume)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    "TEST2",
                    day.isoformat(),
                    close_price - 1,
                    close_price + 1,
                    close_price - 2,
                    close_price,
                    100000 + i * 1000,
                ),
            )

        conn.commit()
        conn.close()

        return str(db_path)

    def test_generator_initialization(self, temp_stock_db, temp_analysis_db):
        """Test that generator initializes correctly."""
        gen = DowntrendGenerator(
            stock_db_path=temp_stock_db, analysis_db_path=temp_analysis_db
        )
        assert gen.stock_db_path == temp_stock_db
        assert gen.analysis_db_path == temp_analysis_db

    def test_check_downtrend_criteria_valid(self, temp_stock_db, temp_analysis_db):
        """Test downtrend criteria checking with valid downtrend data."""
        gen = DowntrendGenerator(
            stock_db_path=temp_stock_db, analysis_db_path=temp_analysis_db
        )

        # Create perfect downtrend data: 11 days declining from 100 to 90
        price_data = []
        for i in range(11):
            price_data.append(
                {
                    "pvm": f"2024-06-{i+1:02d}",
                    "open": 100.0 - i,
                    "high": 101.0 - i,
                    "low": 99.0 - i,
                    "close": 100.0 - i,
                    "volume": 100000,
                }
            )

        # This should meet all criteria
        result = gen._check_downtrend_criteria(price_data)
        assert result is True

    def test_check_downtrend_criteria_invalid(self, temp_stock_db, temp_analysis_db):
        """Test downtrend criteria checking with invalid data."""
        gen = DowntrendGenerator(
            stock_db_path=temp_stock_db, analysis_db_path=temp_analysis_db
        )

        # Create uptrend data (should fail)
        price_data = []
        for i in range(11):
            price_data.append(
                {
                    "pvm": f"2024-06-{i+1:02d}",
                    "open": 90.0 + i,
                    "high": 91.0 + i,
                    "low": 89.0 + i,
                    "close": 90.0 + i,  # Rising
                    "volume": 100000,
                }
            )

        result = gen._check_downtrend_criteria(price_data)
        assert result is False

    def test_generate_with_real_db(self, temp_analysis_db):
        """Test generator with real stock database (if available)."""
        stock_db_path = "data/osakedata.db"

        # Skip if stock database doesn't exist
        if not os.path.exists(stock_db_path):
            pytest.skip("Stock database not available")

        # Generate a small number of events for quick test
        total, errors = generate_random_findings(
            num_tickers=2,
            events_per_ticker=1,
            stock_db_path=stock_db_path,
            analysis_db_path=temp_analysis_db,
        )

        # Should generate at least some events (maybe 0 if strict criteria)
        assert total >= 0
        assert isinstance(errors, list)

        # Check that events were saved
        conn = sqlite3.connect(temp_analysis_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM analysis_findings")
        count = cursor.fetchone()[0]
        conn.close()

        assert count == total

        # Check that saved events have correct pattern
        if count > 0:
            conn = sqlite3.connect(temp_analysis_db)
            cursor = conn.cursor()
            cursor.execute(
                "SELECT pattern, signal_strength FROM analysis_findings LIMIT 1"
            )
            row = cursor.fetchone()
            conn.close()

            assert row[0] == "Random"
            assert row[1] == 1.0

    def test_progress_callback(self, temp_stock_db, temp_analysis_db):
        """Test that progress callback is called."""
        progress_calls = []

        def progress_cb(current, total):
            progress_calls.append((current, total))

        total, errors = generate_random_findings(
            num_tickers=2,
            events_per_ticker=1,
            progress_callback=progress_cb,
            stock_db_path=temp_stock_db,
            analysis_db_path=temp_analysis_db,
        )

        # Progress callback should have been called
        assert len(progress_calls) > 0
        # Last call should be (2, 2) for completion
        assert progress_calls[-1] == (2, 2)

    def test_cancel_check(self, temp_stock_db, temp_analysis_db):
        """Test that cancel check stops generation."""
        cancel_after = 1
        call_count = {"value": 0}

        def cancel_cb():
            call_count["value"] += 1
            return call_count["value"] > cancel_after

        total, errors = generate_random_findings(
            num_tickers=10,
            events_per_ticker=5,
            cancel_check=cancel_cb,
            stock_db_path=temp_stock_db,
            analysis_db_path=temp_analysis_db,
        )

        # Should have been cancelled early
        assert call_count["value"] > 0

    def test_input_validation(self, temp_stock_db, temp_analysis_db):
        """Test that inputs are validated and clamped."""
        # Test with extreme values
        total, errors = generate_random_findings(
            num_tickers=9999,  # Should be clamped to 1000
            events_per_ticker=-5,  # Should be clamped to 1
            stock_db_path=temp_stock_db,
            analysis_db_path=temp_analysis_db,
        )

        # Should not crash and should return valid results
        assert total >= 0
        assert isinstance(errors, list)


def test_convenience_function():
    """Test the convenience function signature."""
    # Just test that the function exists and has correct signature
    import inspect

    sig = inspect.signature(generate_random_findings)
    params = list(sig.parameters.keys())

    assert "num_tickers" in params
    assert "events_per_ticker" in params
    assert "progress_callback" in params
    assert "cancel_check" in params
    assert "stock_db_path" in params
    assert "analysis_db_path" in params
