"""
Yksikkötestit analysis.database_manager moduulille
"""

import pytest
import sqlite3
import tempfile
import os
import sys
from unittest.mock import patch, MagicMock

# Lisää projektin juurikansio Python path:iin ennen analysis-importteja
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Analysis import vaatii sys.path muutoksen
try:
    from analysis.database_manager import DatabaseManager
except ImportError as e:
    print(f"Import error: {e}")
    raise


class TestDatabaseManager:
    """Testit DatabaseManager luokalle"""

    def test_init_with_valid_path(self, temp_db):
        """Testaa DatabaseManager alustus oikealla polulla"""
        manager = DatabaseManager(temp_db)
        assert manager.db_path == temp_db
        assert os.path.exists(temp_db)

    def test_init_with_invalid_path(self):
        """Testaa DatabaseManager alustus väärällä polulla"""
        with pytest.raises((FileNotFoundError, OSError)):
            DatabaseManager("/invalid/path/database.db")

    def test_divergence_schema_migration_adds_radius_geometry_and_pivot2_columns(self, temp_db):
        raw_conn = sqlite3.connect(temp_db)
        raw_conn.execute(
            """
            CREATE TABLE divergence_data (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                bullish_strength REAL DEFAULT 0,
                bearish_strength REAL DEFAULT 0,
                rsi REAL,
                is_bullish_divergence INTEGER DEFAULT 1,
                is_bearish_divergence INTEGER DEFAULT 0,
                PRIMARY KEY (ticker, date)
            )
            """
        )
        raw_conn.execute(
            """
            INSERT INTO divergence_data
            (ticker, date, bullish_strength, bearish_strength, rsi, is_bullish_divergence, is_bearish_divergence)
            VALUES ('AAA', '2025-01-01', 0.5, 0.0, 45.0, 1, 0)
            """
        )
        raw_conn.commit()
        raw_conn.close()

        manager = DatabaseManager(temp_db)
        conn = manager.get_connection()
        columns = {
            row[1]: row[4]
            for row in conn.execute("PRAGMA table_info(divergence_data)").fetchall()
        }
        row = conn.execute(
            """
            SELECT is_bullish_divergence, is_bearish_divergence,
                   hidden_bullish_strength, hidden_bearish_strength,
                   is_hidden_bullish_divergence, is_hidden_bearish_divergence,
                   is_bullish_divergence_r2, is_bearish_divergence_r2,
                   is_hidden_bullish_divergence_r2, is_hidden_bearish_divergence_r2,
                   is_bullish_divergence_r3, is_bearish_divergence_r3,
                   is_hidden_bullish_divergence_r3, is_hidden_bearish_divergence_r3,
                   pivot_gap, pivot_drop_pct,
                   pivot_gap_r2, pivot_drop_pct_r2,
                   pivot2_date_r2,
                   pivot_gap_r3, pivot_drop_pct_r3,
                   pivot2_date_r3
            FROM divergence_data
            WHERE ticker = 'AAA' AND date = '2025-01-01'
            """
        ).fetchone()

        assert "is_bullish_divergence_r2" in columns
        assert "is_bearish_divergence_r2" in columns
        assert "is_bullish_divergence_r3" in columns
        assert "is_bearish_divergence_r3" in columns
        assert "hidden_bullish_strength" in columns
        assert "hidden_bearish_strength" in columns
        assert "is_hidden_bullish_divergence" in columns
        assert "is_hidden_bearish_divergence" in columns
        assert "is_hidden_bullish_divergence_r2" in columns
        assert "is_hidden_bearish_divergence_r2" in columns
        assert "is_hidden_bullish_divergence_r3" in columns
        assert "is_hidden_bearish_divergence_r3" in columns
        assert "pivot_gap" in columns
        assert "pivot_drop_pct" in columns
        assert "pivot_gap_r2" in columns
        assert "pivot_drop_pct_r2" in columns
        assert "pivot2_date_r2" in columns
        assert "pivot_gap_r3" in columns
        assert "pivot_drop_pct_r3" in columns
        assert "pivot2_date_r3" in columns
        assert tuple(row) == (
            1,
            0,
            0.0,
            0.0,
            0,
            0,
            1,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )

    def test_database_manager_adds_hidden_columns_to_existing_divergence_table(self, temp_db):
        raw_conn = sqlite3.connect(temp_db)
        raw_conn.execute(
            """
            CREATE TABLE divergence_data (
                ticker TEXT NOT NULL,
                date TEXT NOT NULL,
                bullish_strength REAL DEFAULT 0,
                bearish_strength REAL DEFAULT 0,
                rsi REAL,
                PRIMARY KEY (ticker, date)
            )
            """
        )
        raw_conn.commit()
        raw_conn.close()

        manager = DatabaseManager(temp_db)
        conn = manager.get_connection()
        columns = {row[1] for row in conn.execute("PRAGMA table_info(divergence_data)")}

        assert "hidden_bullish_strength" in columns
        assert "hidden_bearish_strength" in columns
        assert "is_hidden_bullish_divergence" in columns
        assert "is_hidden_bearish_divergence" in columns
        assert "is_hidden_bullish_divergence_r2" in columns
        assert "is_hidden_bearish_divergence_r2" in columns
        assert "is_hidden_bullish_divergence_r3" in columns
        assert "is_hidden_bearish_divergence_r3" in columns

    def test_excluded_tickers_table_created(self, temp_db):
        manager = DatabaseManager(temp_db)
        conn = manager.get_connection()
        columns = {
            row[1]: row[2] for row in conn.execute("PRAGMA table_info(excluded_tickers)")
        }

        assert "ticker" in columns
        assert "reason" in columns
        assert "category" in columns
        assert "active" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_excluded_ticker_crud_flow(self, temp_db):
        manager = DatabaseManager(temp_db)

        assert manager.upsert_excluded_ticker(
            ticker="spy",
            reason="ETF",
            category="etf",
            active=True,
        )

        rows = manager.list_excluded_tickers()
        assert len(rows) == 1
        assert rows[0]["ticker"] == "SPY"
        assert rows[0]["reason"] == "ETF"
        assert rows[0]["category"] == "etf"
        assert rows[0]["active"] == 1

        assert manager.set_excluded_ticker_active("SPY", False)
        rows = manager.list_excluded_tickers(active_only=False)
        assert rows[0]["active"] == 0

        active_rows = manager.list_excluded_tickers(active_only=True)
        assert active_rows == []

        inactive_rows = manager.list_excluded_tickers(active_only=False)
        assert len(inactive_rows) == 1

        assert manager.upsert_excluded_ticker(
            ticker="SPY",
            reason="ETF fund",
            category="fund",
            active=True,
        )
        rows = manager.list_excluded_tickers()
        assert rows[0]["reason"] == "ETF fund"
        assert rows[0]["category"] == "fund"
        assert rows[0]["active"] == 1

        assert manager.delete_excluded_ticker("SPY")
        assert manager.list_excluded_tickers() == []

    def test_get_connection(self, temp_db):
        """Testaa tietokantayhteyden muodostaminen"""
        manager = DatabaseManager(temp_db)
        conn = manager.get_connection()
        assert conn is not None
        assert isinstance(conn, sqlite3.Connection)
        # DatabaseManager handles connection

    def test_get_all_findings_empty_db(self, temp_db):
        """Testaa kaikkien löydösten haku tyhjästä tietokannasta"""
        manager = DatabaseManager(temp_db)
        findings = manager.get_all_findings()
        assert findings == []

    def test_get_all_findings_with_data(self, temp_db, sample_analysis_data):
        """Testaa kaikkien löydösten haku kun dataa on"""
        manager = DatabaseManager(temp_db)

        # Lisää testidata
        conn = manager.get_connection()
        cursor = conn.cursor()
        for item in sample_analysis_data:
            cursor.execute(
                """
                INSERT INTO analysis_findings 
                (ticker, date, pattern, signal_strength, price, volume, description, analysis_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    item["ticker"],
                    item["date"],
                    item["candle_pattern"],  # candle_pattern mappaa pattern kenttään
                    item[
                        "pattern_strength"
                    ],  # pattern_strength mappaa signal_strength kenttään
                    item["close_price"],  # close_price mappaa price kenttään
                    item["volume"],
                    f"Test pattern {item['candle_pattern']}",  # description
                    "2024-01-01T00:00:00",  # analysis_date
                ),
            )
        conn.commit()
        # Don't close connection here - let DatabaseManager handle it

        findings = manager.get_all_findings()
        assert len(findings) == 2
        # Check that both tickers are present (order may vary)
        tickers = [f["ticker"] for f in findings]
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_get_findings_by_ticker(self, temp_db, sample_analysis_data):
        """Testaa löydösten haku tickerin mukaan"""
        manager = DatabaseManager(temp_db)

        # Lisää testidata
        conn = manager.get_connection()
        cursor = conn.cursor()
        for item in sample_analysis_data:
            cursor.execute(
                """
                INSERT INTO analysis_findings 
                (ticker, date, pattern, signal_strength, price, volume, description, analysis_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    item["ticker"],
                    item["date"],
                    item["candle_pattern"],  # candle_pattern mappaa pattern kenttään
                    item[
                        "pattern_strength"
                    ],  # pattern_strength mappaa signal_strength kenttään
                    item["close_price"],  # close_price mappaa price kenttään
                    item["volume"],
                    f"Test pattern {item['candle_pattern']}",  # description
                    "2024-01-01T00:00:00",  # analysis_date
                ),
            )
        conn.commit()
        # Don't close connection here - let DatabaseManager handle it

        # Testaa AAPL löydökset
        aapl_findings = manager.get_findings_by_ticker("AAPL")
        assert len(aapl_findings) == 1
        assert aapl_findings[0]["ticker"] == "AAPL"
        assert aapl_findings[0]["pattern"] == "doji"  # Käytä oikeaa kenttänimeä

        # Testaa olematon ticker
        empty_findings = manager.get_findings_by_ticker("NONEXISTENT")
        assert empty_findings == []

    def test_get_findings_by_pattern(self, temp_db, sample_analysis_data):
        """Testaa löydösten haku kuvion mukaan"""
        manager = DatabaseManager(temp_db)

        # Lisää testidata
        conn = manager.get_connection()
        cursor = conn.cursor()
        for item in sample_analysis_data:
            cursor.execute(
                """
                INSERT INTO analysis_findings 
                (ticker, date, pattern, signal_strength, price, volume, description, analysis_date 
                 )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    item["ticker"],
                    item["date"],
                    item["candle_pattern"],  # maps to pattern
                    item["pattern_strength"],  # maps to signal_strength
                    item["close_price"],  # maps to price
                    item["volume"],
                    f"Test pattern {item['candle_pattern']}",  # description
                    "2024-01-01T00:00:00",  # analysis_date
                ),
            )
        conn.commit()
        # DatabaseManager handles connection

        # Testaa doji kuvio
        doji_findings = manager.get_findings_by_pattern("doji")
        assert len(doji_findings) == 1
        assert doji_findings[0]["ticker"] == "AAPL"

        # Testaa hammer kuvio
        hammer_findings = manager.get_findings_by_pattern("hammer")
        assert len(hammer_findings) == 1
        assert hammer_findings[0]["ticker"] == "MSFT"

    def test_get_findings_count(self, temp_db, sample_analysis_data):
        """Testaa löydösten määrän laskeminen"""
        manager = DatabaseManager(temp_db)

        # Tyhjä tietokanta
        assert manager.get_findings_count() == 0

        # Lisää testidata
        conn = manager.get_connection()
        cursor = conn.cursor()
        for item in sample_analysis_data:
            cursor.execute(
                """
                INSERT INTO analysis_findings 
                (ticker, date, pattern, signal_strength, price, volume, description, analysis_date 
                 )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    item["ticker"],
                    item["date"],
                    item["candle_pattern"],  # maps to pattern
                    item["pattern_strength"],  # maps to signal_strength
                    item["close_price"],  # maps to price
                    item["volume"],
                    f"Test pattern {item['candle_pattern']}",  # description
                    "2024-01-01T00:00:00",  # analysis_date
                ),
            )
        conn.commit()
        # DatabaseManager handles connection

        assert manager.get_findings_count() == 2

    def test_get_divergence_combo_pairs_filters(self, temp_db):
        """Testaa divergence combo -hakua suodattimilla."""
        manager = DatabaseManager(temp_db)
        conn = manager.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO results_data (ticker, date, candle_pattern, BullDiv_recent_strength, Has_BullDiv_recent)
            VALUES ('AAA', '2024-01-01', 1, 1.2, 1)
            """
        )
        cursor.execute(
            """
            INSERT INTO results_data (ticker, date, candle_pattern, bearish_divergence)
            VALUES ('BBB', '2024-01-02', 3, 1.5)
            """
        )
        cursor.execute(
            """
            INSERT INTO results_data (ticker, date, candle_pattern)
            VALUES ('CCC', '2024-01-03', 2)
            """
        )
        conn.commit()

        combos_all = manager.get_divergence_combo_pairs()
        assert combos_all == {("AAA", "2024-01-01"), ("BBB", "2024-01-02")}

        combos_hammer = manager.get_divergence_combo_pairs(candle_patterns=[1])
        assert combos_hammer == {("AAA", "2024-01-01")}

        combos_piercing = manager.get_divergence_combo_pairs(
            candle_patterns=[3], tickers=["BBB", "ZZZ"]
        )
        assert combos_piercing == {("BBB", "2024-01-02")}

    def test_get_available_tickers(self, temp_db, sample_analysis_data):
        """Testaa käytettävissä olevien tickereiden haku"""
        manager = DatabaseManager(temp_db)

        # Tyhjä tietokanta
        assert manager.get_available_tickers() == []

        # Lisää testidata
        conn = manager.get_connection()
        cursor = conn.cursor()
        for item in sample_analysis_data:
            cursor.execute(
                """
                INSERT INTO analysis_findings 
                (ticker, date, pattern, signal_strength, price, volume, description, analysis_date 
                 )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    item["ticker"],
                    item["date"],
                    item["candle_pattern"],  # maps to pattern
                    item["pattern_strength"],  # maps to signal_strength
                    item["close_price"],  # maps to price
                    item["volume"],
                    f"Test pattern {item['candle_pattern']}",  # description
                    "2024-01-01T00:00:00",  # analysis_date
                ),
            )
        conn.commit()
        # DatabaseManager handles connection

        tickers = manager.get_available_tickers()
        assert len(tickers) == 2
        assert "AAPL" in tickers
        assert "MSFT" in tickers

    def test_get_available_patterns(self, temp_db):
        """Testaa käytettävissä olevien kuvioiden haku"""
        manager = DatabaseManager(temp_db)
        patterns = manager.get_available_patterns()

        # Tarkista että kynttila_mapping data on ladattu
        assert len(patterns) == 5
        pattern_names = [p["pattern_name"] for p in patterns]
        assert "doji" in pattern_names
        assert "hammer" in pattern_names
        assert "shooting_star" in pattern_names

    def test_get_findings_with_filters(self, temp_db, sample_analysis_data):
        """Testaa löydösten haku suodattimilla"""
        manager = DatabaseManager(temp_db)

        # Lisää testidata
        conn = manager.get_connection()
        cursor = conn.cursor()
        for item in sample_analysis_data:
            cursor.execute(
                """
                INSERT INTO analysis_findings 
                (ticker, date, pattern, signal_strength, price, volume, description, analysis_date 
                 )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    item["ticker"],
                    item["date"],
                    item["candle_pattern"],  # maps to pattern
                    item["pattern_strength"],  # maps to signal_strength
                    item["close_price"],  # maps to price
                    item["volume"],
                    f"Test pattern {item['candle_pattern']}",  # description
                    "2024-01-01T00:00:00",  # analysis_date
                ),
            )
        conn.commit()
        # DatabaseManager handles connection

        # Testaa ticker filtteri
        findings = manager.get_findings_with_filters(ticker="AAPL")
        assert len(findings) == 1
        assert findings[0]["ticker"] == "AAPL"

        # Testaa pattern filtteri
        findings = manager.get_findings_with_filters(pattern="hammer")
        assert len(findings) == 1
        assert findings[0]["pattern"] == "hammer"

        # Skip sector filter test as current schema doesn't have sector field

    def test_database_error_handling(self, temp_db):
        """Testaa tietokannan virheenkäsittely"""
        manager = DatabaseManager(temp_db)

        # Simuloi tietokantavirhe
        with patch.object(manager, "get_connection") as mock_conn:
            mock_conn.side_effect = sqlite3.Error("Test database error")

            # Testaa että virheet käsitellään sievoimmin
            findings = manager.get_all_findings()
            assert findings == []

    def test_sql_injection_protection(self, temp_db, sample_analysis_data):
        """Testaa SQL-injektiosuojaus"""
        manager = DatabaseManager(temp_db)

        # Lisää testidata
        conn = manager.get_connection()
        cursor = conn.cursor()
        for item in sample_analysis_data:
            cursor.execute(
                """
                INSERT INTO analysis_findings 
                (ticker, date, pattern, signal_strength, price, volume, description, analysis_date 
                 )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    item["ticker"],
                    item["date"],
                    item["candle_pattern"],  # maps to pattern
                    item["pattern_strength"],  # maps to signal_strength
                    item["close_price"],  # maps to price
                    item["volume"],
                    f"Test pattern {item['candle_pattern']}",  # description
                    "2024-01-01T00:00:00",  # analysis_date
                ),
            )
        conn.commit()
        # DatabaseManager handles connection

        # Testaa SQL injection yritys
        malicious_ticker = "'; DROP TABLE analysis_findings; --"
        findings = manager.get_findings_by_ticker(malicious_ticker)

        # Taulun pitäisi olla vielä olemassa
        assert findings == []
        all_findings = manager.get_all_findings()
        assert len(all_findings) == 2  # Data säilynyt
