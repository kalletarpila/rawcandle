"""
Konfiguraatio testeille
"""

import pytest
import tempfile
import os
import sqlite3
from pathlib import Path
import shutil

from rawcandle.testing.database_isolation import (
    capture_protected_file_inventory,
    install_sqlite_guard,
    inventory_differences,
)


_PRODUCTION_DATABASE_INVENTORY = None


def pytest_configure(config):
    """Reject writable production SQLite connections in tests and subprocesses."""
    root = str(Path(__file__).resolve().parents[1])
    pythonpath = os.environ.get("PYTHONPATH", "")
    entries = [entry for entry in pythonpath.split(os.pathsep) if entry]
    if root not in entries:
        os.environ["PYTHONPATH"] = os.pathsep.join([root, *entries])
    os.environ["RAWCANDLE_TEST_DATABASE_GUARD"] = "1"
    install_sqlite_guard()


def pytest_sessionstart(session):
    """Capture byte identities before any collected test executes."""
    global _PRODUCTION_DATABASE_INVENTORY
    _PRODUCTION_DATABASE_INVENTORY = capture_protected_file_inventory()


def pytest_sessionfinish(session, exitstatus):
    """Fail the run if a protected production database changed."""
    if _PRODUCTION_DATABASE_INVENTORY is None:
        return
    after = capture_protected_file_inventory()
    differences = inventory_differences(_PRODUCTION_DATABASE_INVENTORY, after)
    if not differences:
        return
    reporter = session.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_sep("=", "PROTECTED PRODUCTION DATABASE MUTATION")
        for difference in differences:
            reporter.write_line(difference)
    session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture
def temp_db():
    """Luo väliaikainen tietokanta testeille"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_analysis.db")

    # Luo tietokanta ja taulut
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Luo analysis_findings taulu (yhteensopiva database_manager.py:n kanssa)
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
            analysis_date TEXT,
            market_cap REAL,
            sector TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Luo kynttila_mapping taulu
    cursor.execute(
        """
        CREATE TABLE kynttila_mapping (
            id INTEGER PRIMARY KEY,
            pattern_name TEXT UNIQUE NOT NULL,
            display_name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            reliability REAL DEFAULT 0.5
        )
    """
    )

    # Lisää testidata kynttila_mapping
    test_patterns = [
        ("doji", "Doji", "Tasapainotilaa kuvaava kynttiläkuvio", "reversal", 0.7),
        ("hammer", "Vasara", "Nouseva kääntökuvio", "reversal", 0.8),
        ("shooting_star", "Tähdenlento", "Laskeva kääntökuvio", "reversal", 0.75),
        (
            "bullish_engulfing",
            "Nouseva nielaiseva",
            "Voimakas nousukuvio",
            "continuation",
            0.85,
        ),
        (
            "bearish_engulfing",
            "Laskeva nielaiseva",
            "Voimakas laskukuvio",
            "continuation",
            0.85,
        ),
    ]

    cursor.executemany(
        """
        INSERT INTO kynttila_mapping (pattern_name, display_name, description, category, reliability)
        VALUES (?, ?, ?, ?, ?)
    """,
        test_patterns,
    )

    conn.commit()
    conn.close()

    yield db_path

    # Siivoa
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_osakedata_db():
    """Luo väliaikainen osakedata tietokanta testeille"""
    temp_dir = tempfile.mkdtemp()
    db_path = os.path.join(temp_dir, "test_osakedata.db")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Luo price_data taulu (analyzer.py odottaa tätä nimeä)
    cursor.execute(
        """
        CREATE TABLE price_data (
            id INTEGER PRIMARY KEY,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            UNIQUE(ticker, date)
        )
    """
    )

    # Luo stocks taulu (analyzer.py odottaa tätä nimeä)
    cursor.execute(
        """
        CREATE TABLE stocks (
            ticker TEXT PRIMARY KEY,
            company_name TEXT,
            sector TEXT,
            industry TEXT,
            market_cap REAL,
            country TEXT
        )
    """
    )

    # Lisää testidata
    test_stock_data = [
        ("AAPL", "2024-01-01", 150.0, 155.0, 148.0, 152.0, 1000000),
        ("AAPL", "2024-01-02", 152.0, 158.0, 151.0, 157.0, 1200000),
        ("MSFT", "2024-01-01", 300.0, 305.0, 298.0, 302.0, 800000),
        ("MSFT", "2024-01-02", 302.0, 308.0, 300.0, 306.0, 900000),
    ]

    cursor.executemany(
        """
        INSERT INTO price_data (ticker, date, open, high, low, close, volume)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        test_stock_data,
    )

    test_stock_info = [
        (
            "AAPL",
            "Apple Inc.",
            "Technology",
            "Consumer Electronics",
            3000000000000,
            "USA",
        ),
        (
            "MSFT",
            "Microsoft Corporation",
            "Technology",
            "Software",
            2800000000000,
            "USA",
        ),
    ]

    cursor.executemany(
        """
        INSERT INTO stocks (ticker, company_name, sector, industry, market_cap, country)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        test_stock_info,
    )

    conn.commit()
    conn.close()

    yield db_path

    # Siivoa
    shutil.rmtree(temp_dir)


@pytest.fixture
def sample_analysis_data():
    """Testidataa analyysille"""
    return [
        {
            "ticker": "AAPL",
            "date": "2024-01-01",
            "candle_pattern": "doji",
            "open_price": 150.0,
            "high_price": 155.0,
            "low_price": 148.0,
            "close_price": 152.0,
            "volume": 1000000,
            "pattern_strength": 0.8,
            "market_cap": 3000000000000,
            "sector": "Technology",
        },
        {
            "ticker": "MSFT",
            "date": "2024-01-01",
            "candle_pattern": "hammer",
            "open_price": 300.0,
            "high_price": 305.0,
            "low_price": 298.0,
            "close_price": 302.0,
            "volume": 800000,
            "pattern_strength": 0.9,
            "market_cap": 2800000000000,
            "sector": "Technology",
        },
    ]


class MockPage:
    """Mock Flet Page objekti testeille"""

    def __init__(self):
        self.controls = []
        self.dialog = None
        self.overlay = []
        self.title = "Test App"
        self.theme_mode = "light"

    def add(self, control):
        self.controls.append(control)

    def update(self):
        pass

    def show_snack_bar(self, snack_bar):
        pass


class MockProgressDialog:
    """Mock progress dialog testeille"""

    def __init__(self):
        self.open = False
        self.content = None

    def show(self, page):
        self.open = True

    def hide(self, page):
        self.open = False

    def update_progress(self, value, text):
        pass
