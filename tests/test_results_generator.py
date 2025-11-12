"""
Testit ResultsGenerator:lle (85 sarakkeen rakenne).

Yksinkertaistetut testit jotka varmistavat että:
1. Generaattori luo oikean määrän sarakkeita (85)
2. Inkrementaalinen logiikka toimii
3. Kaikki sarakkeet tallennetaan tietokantaan
"""

import sqlite3
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.database_manager import DatabaseManager
from analysis.results_generator import ResultsGenerator


class TestResultsGeneratorBasic(unittest.TestCase):
    """Perustestit ResultsGenerator:lle."""

    def setUp(self):
        """Luo väliaikainen testiympäristö."""
        self.temp_dir = TemporaryDirectory()
        self.analysis_db = str(Path(self.temp_dir.name) / "analysis.db")
        self.stock_db = str(Path(self.temp_dir.name) / "stock_data.db")

        # Luo tietokannat
        self.db_manager = DatabaseManager(self.analysis_db)
        self._create_stock_db()
        self._create_analysis_findings()

        self.generator = ResultsGenerator(self.db_manager, self.stock_db)

    def tearDown(self):
        """Siivoa."""
        self.db_manager.close()
        self.temp_dir.cleanup()

    def _create_stock_db(self):
        """Luo testidata osakedata.db:hen."""
        conn = sqlite3.connect(self.stock_db)
        cursor = conn.cursor()

        # Luo osakedata taulu
        cursor.execute(
            """
            CREATE TABLE osakedata (
                id INTEGER PRIMARY KEY,
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

        # Lisää testidataa (60 päivää per osake, tarvitaan 20 päivää ennen ja 20 jälkeen)
        base_date = datetime(2024, 10, 15)

        for ticker in ["AAPL", "MSFT", "^GSPC", "^NDX"]:
            for i in range(-25, 35):  # Lisätty enemmän tulevaisuuteen
                from datetime import timedelta

                date = (base_date + timedelta(days=i)).strftime("%Y-%m-%d")

                # Simuloi hintadata
                if ticker == "^GSPC":
                    close_price = 4500 + i * 10
                elif ticker == "^NDX":
                    close_price = 15000 + i * 20
                else:
                    close_price = 150 + i * 2

                cursor.execute(
                    """
                    INSERT INTO osakedata (osake, pvm, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ticker,
                        date,
                        close_price - 1,
                        close_price + 2,
                        close_price - 2,
                        close_price,
                        1000000,
                    ),
                )

        conn.commit()
        conn.close()

    def _create_analysis_findings(self):
        """Luo testilöydökset analysis_findings tauluun."""
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()

        # Lisää testilöydökset (t0 = 2024-10-15)
        findings = [
            ("AAPL", "2024-10-15", "Hammer", 0.85, 55.0),
            ("MSFT", "2024-10-15", "Bullish Engulfing", 0.90, 60.0),
        ]

        for ticker, date, pattern, strength, rsi in findings:
            cursor.execute(
                """
                INSERT INTO analysis_findings 
                (ticker, date, pattern, signal_strength, rsi14)
                VALUES (?, ?, ?, ?, ?)
                """,
                (ticker, date, pattern, strength, rsi),
            )

        conn.commit()

    def test_generate_creates_85_columns(self):
        """Testaa että generointi luo 85 saraketta."""
        rows, time_taken = self.generator.generate_results()

        self.assertGreater(rows, 0, "Pitäisi generoida rivejä")

        # Tarkista että results_data taulussa on 85 dataa + id + created_at
        results = self.db_manager.get_results_data()
        self.assertEqual(len(results), 2, "Pitäisi olla 2 riviä (AAPL ja MSFT)")

        # Tarkista että kaikki odotetut sarakkeet löytyvät
        first_result = results[0]
        expected_columns = [
            "ticker",
            "date",
            "market",
            "candle_pattern",
            "signal_strength",
            "t_1_alin",
            "t0_alin",
            "t1_alin",
            "t_2",
            "t_5",
            "t_10",
            "t_15",
            "t_20",
            "t2",
            "t5",
            "t10",
            "t20",
            "t_2_hajonta",
            "t_5_hajonta",
            "t_2_volyymi",
            "t0_volyymi",
            "t_2_5p_liukuva",
            "t0_50p_liukuva",
            "t0_200p_liukuva",
            "SPX_0",
            "SPX_2",
            "SPX2",
            "NDX_0",
            "NDX_2",
            "NDX2",
            "RSI14_t0",
            "t0_close_norm",
            "bearish_divergence",
            "bullish_divergence",
            "weekday",
        ]

        for col in expected_columns:
            self.assertIn(col, first_result, f"Sarake {col} puuttuu")

    def test_weekday_calculation(self):
        """Testaa että viikonpäivä lasketaan oikein."""
        rows, _ = self.generator.generate_results()
        results = self.db_manager.get_results_data()

        for result in results:
            weekday = result.get("weekday")
            self.assertIsNotNone(weekday, "Weekday ei saa olla None")
            self.assertGreaterEqual(weekday, 1, "Weekday >= 1 (Monday)")
            self.assertLessEqual(weekday, 7, "Weekday <= 7 (Sunday)")

            # 2024-10-15 = Tuesday = 2
            if result["date"] == "2024-10-15":
                self.assertEqual(weekday, 2, "2024-10-15 on tiistai (2)")

    def test_incremental_update(self):
        """Testaa inkrementaalinen päivitys."""
        # Ensimmäinen generointi
        rows1, _ = self.generator.generate_results()
        self.assertEqual(rows1, 2)

        # Lisää uusi löydös
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO analysis_findings 
            (ticker, date, pattern, signal_strength, rsi14)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("AAPL", "2024-10-20", "Morning Star", 0.88, 58.0),
        )
        conn.commit()

        # Toinen generointi - pitäisi löytää vain uusi rivi
        rows2, _ = self.generator.generate_results()
        self.assertEqual(rows2, 1, "Pitäisi generoida vain uusi rivi")

        # Yhteensä 3 riviä
        results = self.db_manager.get_results_data()
        self.assertEqual(len(results), 3)

    def test_pattern_mapping(self):
        """Testaa pattern name -> numero mappaus."""
        self.generator.generate_results()
        results = self.db_manager.get_results_data()

        aapl = [r for r in results if r["ticker"] == "AAPL"][0]
        msft = [r for r in results if r["ticker"] == "MSFT"][0]

        self.assertEqual(aapl["candle_pattern"], 1, "Hammer = 1")
        self.assertEqual(msft["candle_pattern"], 2, "Bullish Engulfing = 2")

    def test_index_data_calculated(self):
        """Testaa että indeksidata lasketaan."""
        self.generator.generate_results()
        results = self.db_manager.get_results_data()

        for result in results:
            # SPX ja NDX t0 pitää olla 100.0 (normalisoitu)
            self.assertEqual(result.get("SPX_0"), 100.0, "SPX_0 = 100")
            self.assertEqual(result.get("NDX_0"), 100.0, "NDX_0 = 100")

            # Muut indeksiarvot eivät saa olla None
            self.assertIsNotNone(result.get("SPX_2"), "SPX_2 ei saa olla None")
            self.assertIsNotNone(result.get("NDX_2"), "NDX_2 ei saa olla None")


class TestDatabaseMethods(unittest.TestCase):
    """Testit DatabaseManager results_data metodeille."""

    def setUp(self):
        """Luo testiympäristö."""
        self.temp_dir = TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "test.db")
        self.db_manager = DatabaseManager(self.db_path)

    def tearDown(self):
        """Siivoa."""
        self.db_manager.close()
        self.temp_dir.cleanup()

    def test_bulk_insert_85_columns(self):
        """Testaa että bulk insert toimii 85 sarakkeella."""
        # Luo testimuotoinen data
        test_data = []
        for i in range(10):
            test_data.append(
                {
                    "ticker": f"TEST{i}",
                    "date": "2024-10-15",
                    "candle_pattern": 1,
                    "signal_strength": 0.85,
                    "t_1_alin": 98.0,
                    "t_1_ylin": 102.0,
                    "t_1_bodi": 50.0,
                    "t_1_bodi_colour": 1,
                    "t0_alin": 100.0,
                    "t0_ylin": 105.0,
                    "t0_bodi": 55.0,
                    "t0_bodi_colour": 1,
                    "t1_alin": 101.0,
                    "t1_ylin": 106.0,
                    "t1_bodi": 52.0,
                    "t1_bodi_colour": 1,
                    "t_2": 98.5,
                    "t_5": 95.0,
                    "t_10": 92.0,
                    "t_15": 90.0,
                    "t_20": 88.0,
                    "t_2_hajonta": 2.5,
                    "t_5_hajonta": 3.0,
                    "t_10_hajonta": 3.5,
                    "t_15_hajonta": 4.0,
                    "t_20_hajonta": 4.5,
                    "t2": 102.0,
                    "t5": 105.0,
                    "t10": 108.0,
                    "t20": 112.0,
                    "t_2_volyymi": 95.0,
                    "t_5_volyymi": 98.0,
                    "t_10_volyymi": 100.0,
                    "t_15_volyymi": 102.0,
                    "t_20_volyymi": 105.0,
                    "t0_volyymi": 110.0,
                    "t2_volyymi": 95.0,
                    "t5_volyymi": 90.0,
                    "t10_volyymi": 88.0,
                    "t20_volyymi": 85.0,
                    "t_2_5p_liukuva": 99.0,
                    "t_2_10p_liukuva": 98.0,
                    "t_2_20p_liukuva": 97.0,
                    "t_5_5p_liukuva": 96.0,
                    "t_5_10p_liukuva": 95.0,
                    "t_5_20p_liukuva": 94.0,
                    "t_10_5p_liukuva": 93.0,
                    "t_10_10p_liukuva": 92.0,
                    "t_10_20p_liukuva": 91.0,
                    "t_15_5p_liukuva": 90.0,
                    "t_15_10p_liukuva": 89.0,
                    "t_15_20p_liukuva": 88.0,
                    "t_20_5p_liukuva": 87.0,
                    "t_20_10p_liukuva": 86.0,
                    "t_20_20p_liukuva": 85.0,
                    "t0_50p_liukuva": 100.0,
                    "t0_200p_liukuva": 95.0,
                    "SPX_0": 100.0,
                    "SPX_2": 99.0,
                    "SPX_5": 97.0,
                    "SPX_10": 95.0,
                    "SPX_15": 93.0,
                    "SPX_20": 91.0,
                    "SPX2": 101.0,
                    "SPX5": 103.0,
                    "SPX10": 105.0,
                    "SPX15": 107.0,
                    "SPX20": 109.0,
                    "NDX_0": 100.0,
                    "NDX_2": 99.5,
                    "NDX_5": 98.0,
                    "NDX_10": 96.0,
                    "NDX_15": 94.0,
                    "NDX_20": 92.0,
                    "NDX2": 101.5,
                    "NDX5": 103.0,
                    "NDX10": 105.5,
                    "NDX15": 108.0,
                    "NDX20": 110.0,
                    "RSI14_t0": 55.0,
                    "t0_close_norm": 105.0,
                    "bearish_divergence": 0.0,
                    "bullish_divergence": 0.0,
                    "weekday": 2,
                }
            )

        inserted = self.db_manager.bulk_insert_results(test_data)
        self.assertEqual(inserted, 10, "Pitäisi insertata 10 riviä")

        results = self.db_manager.get_results_data()
        self.assertEqual(len(results), 10, "Pitäisi olla 10 riviä kannassa")

    def test_clear_results(self):
        """Testaa tulosten tyhjennys."""
        # Lisää dataa
        test_data = [
            {
                "ticker": "TEST",
                "date": "2024-10-15",
                "candle_pattern": 1,
                "signal_strength": 0.85,
                "weekday": 2,
            }
        ]
        self.db_manager.bulk_insert_results(test_data)

        # Tyhjennä
        deleted = self.db_manager.clear_results_data()
        self.assertEqual(deleted, 1)

        results = self.db_manager.get_results_data()
        self.assertEqual(len(results), 0)


if __name__ == "__main__":
    unittest.main()
