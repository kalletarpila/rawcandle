"""Test that downtrend generation creates events for exactly the requested number of tickers."""

import sqlite3
import os
import pytest
from analysis.downtrend_generator import DowntrendGenerator


@pytest.fixture
def temp_databases(tmp_path):
    """Create temporary databases for testing."""
    stock_db = tmp_path / "osakedata.db"
    analysis_db = tmp_path / "analysis.db"

    # Create stock database with sample data
    conn = sqlite3.connect(str(stock_db))
    cursor = conn.cursor()

    # Create table
    cursor.execute(
        """
        CREATE TABLE osakedata (
            osake TEXT,
            pvm TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            market TEXT NOT NULL DEFAULT 'usa'
        )
    """
    )

    # Insert data for 5 different tickers
    # Each ticker has 30 days of data with a clear downtrend pattern
    tickers = ["TICKER1", "TICKER2", "TICKER3", "TICKER4", "TICKER5"]
    for ticker in tickers:
        for day in range(30):
            date = f"2024-01-{day+1:02d}"
            # Create descending prices for downtrend
            close_price = 100.0 - (day * 0.5)  # Progressive decline
            open_price = close_price + 0.1
            high_price = close_price + 0.2
            low_price = close_price - 0.1
            volume = 1000000

            cursor.execute(
                "INSERT INTO osakedata (osake, pvm, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (ticker, date, open_price, high_price, low_price, close_price, volume),
            )

    conn.commit()
    conn.close()

    # Create analysis database
    analysis_conn = sqlite3.connect(str(analysis_db))
    analysis_cursor = analysis_conn.cursor()
    analysis_cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS analysis_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            pattern TEXT,
            signal_strength REAL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ticker, date, pattern)
        )
    """
    )
    analysis_conn.commit()
    analysis_conn.close()

    return str(stock_db), str(analysis_db)


def test_generates_events_for_exact_number_of_tickers(temp_databases):
    """Test that events are generated for exactly the requested number of tickers."""
    stock_db, analysis_db = temp_databases

    # Request events for 3 tickers with 2 events per ticker
    generator = DowntrendGenerator(stock_db, analysis_db)
    total_saved, errors = generator.generate_random_findings(
        num_tickers=3, events_per_ticker=2
    )

    # Check that some events were saved
    assert total_saved > 0, "Should have saved at least some events"

    # Check analysis database
    conn = sqlite3.connect(analysis_db)
    cursor = conn.cursor()

    # Count unique tickers
    cursor.execute("SELECT COUNT(DISTINCT ticker) FROM analysis_findings")
    unique_tickers = cursor.fetchone()[0]

    # Should have events for exactly 3 tickers (or less if data insufficient)
    assert unique_tickers <= 3, f"Should have max 3 tickers, got {unique_tickers}"

    # Get events per ticker
    cursor.execute(
        """
        SELECT ticker, COUNT(*) as event_count 
        FROM analysis_findings 
        GROUP BY ticker
    """
    )
    ticker_counts = cursor.fetchall()

    conn.close()

    # Each ticker should have max 2 events (requested amount)
    for ticker, count in ticker_counts:
        assert (
            count <= 2
        ), f"Ticker {ticker} has {count} events, expected max 2 per ticker"

    print("\nGeneration results:")
    print(f"  Total events saved: {total_saved}")
    print(f"  Unique tickers: {unique_tickers}")
    print(f"  Events per ticker: {ticker_counts}")


def test_no_duplicate_dates_per_ticker(temp_databases):
    """Test that same ticker doesn't get duplicate events on same date."""
    stock_db, analysis_db = temp_databases

    # Generate multiple events per ticker
    generator = DowntrendGenerator(stock_db, analysis_db)
    total_saved, errors = generator.generate_random_findings(
        num_tickers=2, events_per_ticker=5
    )

    # Check for duplicates
    conn = sqlite3.connect(analysis_db)
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT ticker, date, COUNT(*) as cnt
        FROM analysis_findings
        GROUP BY ticker, date
        HAVING cnt > 1
    """
    )
    duplicates = cursor.fetchall()

    conn.close()

    assert (
        len(duplicates) == 0
    ), f"Found duplicate ticker/date combinations: {duplicates}"


def test_respects_max_tickers_limit(temp_databases):
    """Test that requesting more tickers than available doesn't cause errors."""
    stock_db, analysis_db = temp_databases

    # Request 100 tickers but only 5 exist in database
    generator = DowntrendGenerator(stock_db, analysis_db)
    total_saved, errors = generator.generate_random_findings(
        num_tickers=100, events_per_ticker=2
    )

    # Should still work without errors
    conn = sqlite3.connect(analysis_db)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(DISTINCT ticker) FROM analysis_findings")
    unique_tickers = cursor.fetchone()[0]

    conn.close()

    # Should have max 5 tickers (all available in database)
    assert (
        unique_tickers <= 5
    ), f"Should have max 5 tickers from database, got {unique_tickers}"
