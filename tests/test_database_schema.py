import sqlite3
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis.database_manager import (
    DatabaseManager,
    MASTER_FEATURE_COLUMNS,
    RESULTS_SCHEMA_REQUIRED_COLUMNS,
    BULL_DIV_METRIC_COLUMN_DEFS,
    COMBO_FEATURE_COLUMNS,
)
from analysis.combo_features import BULL_DIV_GENERAL_FEATURES


class TestResultsSchemaManagement(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        self.db_path = str(Path(self.temp_dir.name) / "analysis.db")
        self.db_manager = DatabaseManager(self.db_path)

    def tearDown(self):
        self.db_manager.close()
        self.temp_dir.cleanup()

    def _reset_results_table(self):
        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute("DROP TABLE IF EXISTS results_data")
        cursor.execute(
            """
            CREATE TABLE results_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                date TEXT
            )
            """
        )
        conn.commit()

    def test_ensure_results_schema_adds_missing_columns(self):
        self._reset_results_table()
        self.db_manager.ensure_results_schema()
        existing = self.db_manager._get_existing_columns("results_data")
        for column in RESULTS_SCHEMA_REQUIRED_COLUMNS:
            self.assertIn(column, existing, f"{column} puuttuu results_data taulusta")

    def test_ensure_results_schema_is_idempotent(self):
        self._reset_results_table()
        self.db_manager.ensure_results_schema()
        first_columns = self.db_manager._get_existing_columns("results_data")
        self.db_manager.ensure_results_schema()
        second_columns = self.db_manager._get_existing_columns("results_data")
        self.assertEqual(first_columns, second_columns)

    def test_bulk_insert_accepts_master_feature_columns(self):
        self.db_manager.clear_results_data()
        row = {
            "ticker": "TEST",
            "date": "2024-01-01",
            "market": "usa",
            "candle_pattern": 1,
            "signal_strength": 0.5,
        }

        inserted = self.db_manager.bulk_insert_results([row])
        self.assertEqual(inserted, 1)

        conn = self.db_manager.get_connection()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT ATR_14, t0_50p_slope, Volume_impulse, trend_regime_5_20, is_candle_day
            FROM results_data
            WHERE ticker = ?
            """,
            ("TEST",),
        )
        stored = cursor.fetchone()
        self.assertIsNotNone(stored)
        self.assertIsNone(stored[0])
        self.assertIsNone(stored[1])
        self.assertIsNone(stored[2])
        self.assertIsNone(stored[3])
        self.assertEqual(stored[4], 0)

        cursor.execute(
            """
            SELECT BullDiv_recent_offset, Has_BullDiv_recent
            FROM results_data
            WHERE ticker = ?
            """,
            ("TEST",),
        )
        bull_defaults = cursor.fetchone()
        self.assertEqual(bull_defaults[0], -1)
        self.assertEqual(bull_defaults[1], 0)

    def test_required_schema_columns_cover_feature_sets(self):
        required = set(RESULTS_SCHEMA_REQUIRED_COLUMNS)
        all_cols = set(
            MASTER_FEATURE_COLUMNS
            + BULL_DIV_GENERAL_FEATURES
            + list(BULL_DIV_METRIC_COLUMN_DEFS.keys())
            + COMBO_FEATURE_COLUMNS
        )
        missing = all_cols - required
        self.assertFalse(
            missing,
            f"RESULTS_SCHEMA_REQUIRED_COLUMNS missing columns: {sorted(missing)}",
        )


if __name__ == "__main__":
    unittest.main()
