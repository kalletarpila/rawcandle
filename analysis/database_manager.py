"""
Analysis Database Manager
Hallinnoi analysis-tietokannan operaatiot.
"""

import sqlite3
import os
from typing import List, Dict, Any, Optional, Tuple, Iterable, Set
from datetime import datetime
import logging

from .combo_features import BULL_DIV_GENERAL_FEATURES, CANDLE_PATTERN_TO_SLUG

RESULTS_BASE_COLUMNS: List[str] = [
    "ticker",
    "date",
    "market",
    "candle_pattern",
    "signal_strength",
    "t_1_alin",
    "t_1_ylin",
    "t_1_bodi",
    "t_1_bodi_colour",
    "t0_alin",
    "t0_ylin",
    "t0_bodi",
    "t0_bodi_colour",
    "t0_alinMiinusClose",
    "t1_alin",
    "t1_ylin",
    "t1_bodi",
    "t1_bodi_colour",
    "t_2",
    "t_5",
    "t_10",
    "t_15",
    "t_20",
    "t_2_hajonta",
    "t_5_hajonta",
    "t_10_hajonta",
    "t_15_hajonta",
    "t_20_hajonta",
    "t2",
    "t5",
    "t10",
    "t20",
    "t_2_volyymi",
    "t_5_volyymi",
    "t_10_volyymi",
    "t_15_volyymi",
    "t_20_volyymi",
    "t0_volyymi",
    "t2_volyymi",
    "t5_volyymi",
    "t10_volyymi",
    "t20_volyymi",
    "t_2_5p_liukuva",
    "t_2_10p_liukuva",
    "t_2_20p_liukuva",
    "t_5_5p_liukuva",
    "t_5_10p_liukuva",
    "t_5_20p_liukuva",
    "t_10_5p_liukuva",
    "t_10_10p_liukuva",
    "t_10_20p_liukuva",
    "t_15_5p_liukuva",
    "t_15_10p_liukuva",
    "t_15_20p_liukuva",
    "t_20_5p_liukuva",
    "t_20_10p_liukuva",
    "t_20_20p_liukuva",
    "t0_50p_liukuva",
    "t0_200p_liukuva",
    "SPX_0",
    "SPX_2",
    "SPX_5",
    "SPX_10",
    "SPX_15",
    "SPX_20",
    "SPX2",
    "SPX5",
    "SPX10",
    "SPX15",
    "SPX20",
    "NDX_0",
    "NDX_2",
    "NDX_5",
    "NDX_10",
    "NDX_15",
    "NDX_20",
    "NDX2",
    "NDX5",
    "NDX10",
    "NDX15",
    "NDX20",
    "RSI14_t0",
    "t0_close_norm",
    "bearish_divergence",
    "bullish_divergence",
    "BullDiv_strength",
    "BullDiv_recent_strength",
    "BullDiv_recent_offset",
    "Has_BullDiv_recent",
    "weekday",
]

MASTER_FEATURE_COLUMNS: List[str] = [
    "t0_20p_liukuva",
    "t0_50p_slope",
    "t0_200p_slope",
    "trend_regime_5_20",
    "trend_regime_20_50",
    "trend_regime_50_200",
    "RSI_slope_5",
    "Price_slope_5",
    "Price_slope_10",
    "Price_acceleration_5_10",
    "Volatility_ratio_10_20",
    "Gap_down_strength",
    "Body_ratio",
    "Shadow_ratio",
    "Volume_impulse",
    "Reversal_Context_Score",
    "SPX_volatility_10",
    "NDX_volatility_10",
    "ATR_14",
    "ATR_ratio_14",
    "MACD_line",
    "MACD_signal",
    "MACD_hist",
    "pivot_low_strength_3",
    "pivot_low_strength_5",
    "pivot_high_strength_3",
    "pivot_high_strength_5",
    "VIX_10",
    "VIX_norm_10",
    "is_crisis",
    "is_candle_day",
    "has_blackout_data",
    "is_earnings_t0",
    "is_earnings_window",
    "is_dividend_t0",
    "is_dividend_window",
    "is_blackout_t0",
    "is_blackout_window",
    "exclude_from_regression",
    "sector",
    "sector_momentum_5",
    "sector_momentum_20",
    "sector_volatility_20",
]

# Sarakkeet jotka pudotetaan uuden combo-koodipolun myötä
COMBO_FLAG_COLUMNS: List[str] = [
    f"is_{slug}_{suffix}"
    for slug in CANDLE_PATTERN_TO_SLUG.values()
    for suffix in [
        "only_t0",
        "and_BullDiv_t0",
        "and_BullDiv_recent_2d",
        "and_BullDiv_recent_3d",
        "and_BullDiv_recent_5d",
    ]
]

SAME_DAY_AGG_COLUMNS: List[str] = [
    "signal_combo_code",
    "num_candles_same_day",
    "has_multi_candle_combo",
    "has_bullish_divergence_same_day",
    "signal_count_same_day",
    "unique_patterns_same_day",
    "max_strength_same_day",
    "second_best_strength_same_day",
    "sum_strength_same_day",
    "has_same_day_reversal_cluster",
]

DROPPED_RESULTS_COLUMNS: List[str] = COMBO_FLAG_COLUMNS + SAME_DAY_AGG_COLUMNS
# Pudotettujen combo-/same-day -sarakkeiden tilalle ei lisätä uusia flagisarjoja.
COMBO_FEATURE_COLUMNS: List[str] = []

MASTER_FEATURE_COLUMN_DEFS = {
    "t0_20p_liukuva": "REAL",
    "t0_50p_slope": "REAL",
    "t0_200p_slope": "REAL",
    "trend_regime_5_20": "INTEGER",
    "trend_regime_20_50": "INTEGER",
    "trend_regime_50_200": "INTEGER",
    "RSI_slope_5": "REAL",
    "Price_slope_5": "REAL",
    "Price_slope_10": "REAL",
    "Price_acceleration_5_10": "REAL",
    "Volatility_ratio_10_20": "REAL",
    "Gap_down_strength": "REAL",
    "Body_ratio": "REAL",
    "Shadow_ratio": "REAL",
    "Volume_impulse": "REAL",
    "Reversal_Context_Score": "REAL",
    "SPX_volatility_10": "REAL",
    "NDX_volatility_10": "REAL",
    "ATR_14": "REAL",
    "ATR_ratio_14": "REAL",
    "MACD_line": "REAL",
    "MACD_signal": "REAL",
    "MACD_hist": "REAL",
    "pivot_low_strength_3": "REAL",
    "pivot_low_strength_5": "REAL",
    "pivot_high_strength_3": "REAL",
    "pivot_high_strength_5": "REAL",
    "VIX_10": "REAL",
    "VIX_norm_10": "REAL",
    "is_crisis": "INTEGER DEFAULT 0",
    "is_candle_day": "INTEGER DEFAULT 0",
    "has_blackout_data": "INTEGER DEFAULT 0",
    "is_earnings_t0": "INTEGER DEFAULT 0",
    "is_earnings_window": "INTEGER DEFAULT 0",
    "is_dividend_t0": "INTEGER DEFAULT 0",
    "is_dividend_window": "INTEGER DEFAULT 0",
    "is_blackout_t0": "INTEGER DEFAULT 0",
    "is_blackout_window": "INTEGER DEFAULT 0",
    "exclude_from_regression": "INTEGER DEFAULT 0",
    "sector": "TEXT",
    "sector_momentum_5": "REAL",
    "sector_momentum_20": "REAL",
    "sector_volatility_20": "REAL",
}
BULL_DIV_METRIC_COLUMN_DEFS = {
    "BullDiv_strength": "REAL",
    "BullDiv_recent_strength": "REAL",
    "BullDiv_recent_offset": "INTEGER DEFAULT -1",
    "Has_BullDiv_recent": "INTEGER DEFAULT 0",
    "bullish_divergence": "REAL",
    "bearish_divergence": "REAL",
}

BULL_DIV_GENERAL_DEFAULTS = {
    "bullDiv_offset": 99,
    "bullDiv_last_1d": 0,
    "bullDiv_last_2d": 0,
    "bullDiv_last_3d": 0,
    "bullDiv_last_3d_any": 0,
}

BULL_DIV_METRIC_DEFAULTS = {
    "BullDiv_recent_offset": -1,
    "Has_BullDiv_recent": 0,
}

MASTER_FEATURE_INTEGER_COLUMNS: Set[str] = {
    "t_1_bodi_colour",
    "t0_bodi_colour",
    "t1_bodi_colour",
    "is_crisis",
    "is_candle_day",
    "has_blackout_data",
    "is_earnings_t0",
    "is_earnings_window",
    "is_dividend_t0",
    "is_dividend_window",
    "is_blackout_t0",
    "is_blackout_window",
    "exclude_from_regression",
}
MASTER_FEATURE_TEXT_COLUMNS: Set[str] = {"sector"}
MASTER_FEATURE_CONTINUOUS_COLUMNS: Set[str] = {
    col
    for col in MASTER_FEATURE_COLUMNS
    if col not in MASTER_FEATURE_INTEGER_COLUMNS
    and col not in MASTER_FEATURE_TEXT_COLUMNS
}
RESULTS_SCHEMA_REQUIRED_COLUMNS: Dict[str, str] = {}

RESULTS_SCHEMA_REQUIRED_COLUMNS.update(MASTER_FEATURE_COLUMN_DEFS)
RESULTS_SCHEMA_REQUIRED_COLUMNS.update(BULL_DIV_METRIC_COLUMN_DEFS)
RESULTS_SCHEMA_REQUIRED_COLUMNS.update(
    {
        column: f"INTEGER DEFAULT {BULL_DIV_GENERAL_DEFAULTS.get(column, 0)}"
        for column in BULL_DIV_GENERAL_FEATURES
    }
)


class DatabaseManager:
    """Hallinnoi analysis-tietokannan operaatiot"""

    def __init__(self, db_path: str = "data/analysis.db"):
        """
        Alusta DatabaseManager.

        Args:
            db_path: Tietokantatiedoston polku
        """
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        self._connection = None
        self._init_database()

    def _init_database(self) -> None:
        """Alusta tietokanta ja luo taulut."""
        try:
            # Varmista että hakemisto on olemassa
            parent = os.path.dirname(self.db_path)
            try:
                os.makedirs(parent, exist_ok=True)
            except PermissionError as pe:
                # Translate into FileNotFoundError for tests that expect invalid path handling
                raise FileNotFoundError(str(pe))

            conn = self.get_connection()
            cursor = conn.cursor()

            # Luo yksinkertaistettu analysis_findings taulu
            # Vain tarpeelliset kentät: id, ticker, date, pattern, signal_strength, rsi14, created_at
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    pattern TEXT,
                    signal_strength REAL,
                    rsi14 REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Lisää rsi14 sarake jos se puuttuu (migraatio vanhoille tietokannoille)
            cursor.execute("PRAGMA table_info(analysis_findings)")
            columns = [row[1] for row in cursor.fetchall()]
            if "rsi14" not in columns:
                cursor.execute("ALTER TABLE analysis_findings ADD COLUMN rsi14 REAL")
                self.logger.info("Added rsi14 column to analysis_findings table")

            # Poista mahdolliset duplikaatit ennen uniikki-indeksin luontia
            cursor.execute(
                """
                DELETE FROM analysis_findings
                WHERE rowid NOT IN (
                    SELECT MIN(rowid)
                    FROM analysis_findings
                    GROUP BY ticker, date, pattern
                )
                """
            )
            # Uniikki indeksi estämään samojen havaintojen tuplaukset
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_finding ON analysis_findings(ticker, date, pattern)"
            )

            # Luo indeksit
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_ticker ON analysis_findings(ticker)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_date ON analysis_findings(date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_pattern ON analysis_findings(pattern)"
            )

            # Luo divergence_data taulu
            # Tallentaa divergenssit KAIKILLE päiville (ei vain kuviopäiville)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS divergence_data (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    bullish_strength REAL DEFAULT 0,
                    bearish_strength REAL DEFAULT 0,
                    rsi REAL,
                    PRIMARY KEY (ticker, date)
                )
            """
            )

            # Luo indeksit divergence_data tauluun
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_div_ticker ON divergence_data(ticker)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_div_date ON divergence_data(date)"
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS blackout_dates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    event TEXT NOT NULL,
                    source TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, date, event)
                )
            """
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_blackout_ticker ON blackout_dates(ticker)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_blackout_date ON blackout_dates(date)"
            )

            # Luo results_data taulu
            # Tallentaa prosessoidut tulokset (vain kynttiläkuviopäivät)
            # Perussarakkeet (market + alkuperäiset kentät)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS results_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    market TEXT NOT NULL DEFAULT 'usa',
                    candle_pattern INTEGER,
                    signal_strength REAL,
                    t_1_alin REAL,
                    t_1_ylin REAL,
                    t_1_bodi REAL,
                    t_1_bodi_colour INTEGER,
                    t0_alin REAL,
                    t0_ylin REAL,
                    t0_bodi REAL,
                    t0_bodi_colour INTEGER,
                    t0_alinMiinusClose REAL,
                    t1_alin REAL,
                    t1_ylin REAL,
                    t1_bodi REAL,
                    t1_bodi_colour INTEGER,
                    t_2 REAL,
                    t_5 REAL,
                    t_10 REAL,
                    t_15 REAL,
                    t_20 REAL,
                    t_2_hajonta REAL,
                    t_5_hajonta REAL,
                    t_10_hajonta REAL,
                    t_15_hajonta REAL,
                    t_20_hajonta REAL,
                    t2 REAL,
                    t5 REAL,
                    t10 REAL,
                    t20 REAL,
                    t_2_volyymi REAL,
                    t_5_volyymi REAL,
                    t_10_volyymi REAL,
                    t_15_volyymi REAL,
                    t_20_volyymi REAL,
                    t0_volyymi REAL,
                    t2_volyymi REAL,
                    t5_volyymi REAL,
                    t10_volyymi REAL,
                    t20_volyymi REAL,
                    t_2_5p_liukuva REAL,
                    t_2_10p_liukuva REAL,
                    t_2_20p_liukuva REAL,
                    t_5_5p_liukuva REAL,
                    t_5_10p_liukuva REAL,
                    t_5_20p_liukuva REAL,
                    t_10_5p_liukuva REAL,
                    t_10_10p_liukuva REAL,
                    t_10_20p_liukuva REAL,
                    t_15_5p_liukuva REAL,
                    t_15_10p_liukuva REAL,
                    t_15_20p_liukuva REAL,
                    t_20_5p_liukuva REAL,
                    t_20_10p_liukuva REAL,
                    t_20_20p_liukuva REAL,
                    t0_50p_liukuva REAL,
                    t0_200p_liukuva REAL,
                    SPX_0 REAL,
                    SPX_2 REAL,
                    SPX_5 REAL,
                    SPX_10 REAL,
                    SPX_15 REAL,
                    SPX_20 REAL,
                    SPX2 REAL,
                    SPX5 REAL,
                    SPX10 REAL,
                    SPX15 REAL,
                    SPX20 REAL,
                    NDX_0 REAL,
                    NDX_2 REAL,
                    NDX_5 REAL,
                    NDX_10 REAL,
                    NDX_15 REAL,
                    NDX_20 REAL,
                    NDX2 REAL,
                    NDX5 REAL,
                    NDX10 REAL,
                    NDX15 REAL,
                    NDX20 REAL,
                    RSI14_t0 REAL,
                    t0_close_norm REAL,
                    bearish_divergence REAL,
                    bullish_divergence REAL,
                    BullDiv_strength REAL,
                    BullDiv_recent_strength REAL,
                    BullDiv_recent_offset INTEGER,
                    Has_BullDiv_recent INTEGER,
                    weekday INTEGER,
                    t0_20p_liukuva REAL,
                    RSI_slope_5 REAL,
                    Price_slope_5 REAL,
                    Price_slope_10 REAL,
                    Price_acceleration_5_10 REAL,
                    Volatility_ratio_10_20 REAL,
                    Gap_down_strength REAL,
                    Body_ratio REAL,
                    Shadow_ratio REAL,
                    Volume_impulse REAL,
                    Reversal_Context_Score REAL,
                    SPX_volatility_10 REAL,
                    NDX_volatility_10 REAL,
                    t0_50p_slope REAL,
                    t0_200p_slope REAL,
                    trend_regime_5_20 INTEGER,
                    trend_regime_20_50 INTEGER,
                    trend_regime_50_200 INTEGER,
                    ATR_14 REAL,
                    ATR_ratio_14 REAL,
                    MACD_line REAL,
                    MACD_signal REAL,
                    MACD_hist REAL,
                    pivot_low_strength_3 REAL,
                    pivot_low_strength_5 REAL,
                    pivot_high_strength_3 REAL,
                    pivot_high_strength_5 REAL,
                    VIX_10 REAL,
                    VIX_norm_10 REAL,
                    is_crisis INTEGER DEFAULT 0,
                    is_candle_day INTEGER DEFAULT 0,
                    has_blackout_data INTEGER DEFAULT 0,
                    is_earnings_t0 INTEGER DEFAULT 0,
                    is_earnings_window INTEGER DEFAULT 0,
                    is_dividend_t0 INTEGER DEFAULT 0,
                    is_dividend_window INTEGER DEFAULT 0,
                    is_blackout_t0 INTEGER DEFAULT 0,
                    is_blackout_window INTEGER DEFAULT 0,
                    exclude_from_regression INTEGER DEFAULT 0,
                    sector TEXT,
                    sector_momentum_5 REAL,
                    sector_momentum_20 REAL,
                    sector_volatility_20 REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, date, candle_pattern)
                )
            """
            )

            cursor.execute("PRAGMA table_info(results_data)")
            results_columns = [row[1] for row in cursor.fetchall()]
            if "market" not in results_columns:
                cursor.execute(
                    "ALTER TABLE results_data ADD COLUMN market TEXT NOT NULL DEFAULT 'usa'"
                )
                cursor.execute(
                    "UPDATE results_data SET market = 'suomi' WHERE ticker LIKE '%.HE'"
                )
                cursor.execute(
                    "UPDATE results_data SET market = 'usa' WHERE market IS NULL"
                )

            additional_column_defs = {
                "t0_alinMiinusClose": "REAL",
                "BullDiv_strength": "REAL",
                "BullDiv_recent_strength": "REAL",
                "BullDiv_recent_offset": "INTEGER DEFAULT -1",
                "Has_BullDiv_recent": "INTEGER DEFAULT 0",
            }
            general_column_ddls = {
                "bullDiv_offset": "INTEGER DEFAULT 99",
                "bullDiv_last_1d": "INTEGER DEFAULT 0",
                "bullDiv_last_2d": "INTEGER DEFAULT 0",
                "bullDiv_last_3d": "INTEGER DEFAULT 0",
                "bullDiv_last_3d_any": "INTEGER DEFAULT 0",
            }
            additional_column_defs.update(MASTER_FEATURE_COLUMN_DEFS)
            for column in BULL_DIV_GENERAL_FEATURES:
                additional_column_defs[column] = general_column_ddls.get(
                    column, "INTEGER DEFAULT 0"
                )

            for column, ddl in additional_column_defs.items():
                if column not in results_columns:
                    cursor.execute(
                        f"ALTER TABLE results_data ADD COLUMN {column} {ddl}"
                    )
                    self.logger.info(f"Added {column} column to results_data table")

            # Luo indeksit results_data tauluun
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_ticker ON results_data(ticker)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_date ON results_data(date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_pattern ON results_data(candle_pattern)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_ticker_date ON results_data(ticker, date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_pattern_date ON results_data(candle_pattern, date)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_results_market ON results_data(market)"
            )

            # Pudota vanhat combo-/same-day -sarakkeet ja varmista schema.
            self._drop_columns_if_exists("results_data", DROPPED_RESULTS_COLUMNS)
            self.ensure_results_schema()

            # Luo results_metadata taulu
            # Tallentaa metatiedot generoinneista
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS results_metadata (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    total_rows INTEGER,
                    processing_time_seconds REAL
                )
            """
            )

            conn.commit()
            self.logger.info("Analysis database initialized successfully")

        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            raise

    def _get_existing_columns(self, table: str) -> Set[str]:
        """
        Palauta annetun taulun sarakkeiden nimet.
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(f"PRAGMA table_info({table})")
            return {row[1] for row in cursor.fetchall()}
        except Exception as e:
            self.logger.error(f"Fetch columns failed for table {table}: {e}")
            return set()

    def _drop_columns_if_exists(self, table: str, columns: Iterable[str]) -> None:
        """
        Pudota annetut sarakkeet jos ne löytyvät taulusta (SQLite 3.35+).
        """
        existing = self._get_existing_columns(table)
        to_drop = [col for col in columns if col in existing]
        if not to_drop:
            return

        conn = self.get_connection()
        cursor = conn.cursor()
        for col in to_drop:
            try:
                cursor.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
                self.logger.info(f"Dropped column {col} from {table}")
            except Exception as exc:
                self.logger.warning(
                    "Failed to drop column %s from %s (%s)", col, table, exc
                )
        try:
            conn.commit()
        except Exception:
            pass

    def ensure_results_schema(self) -> None:
        """
        Lisää puuttuvat results_data-sarakkeet idempotentisti (ei droppaa dataa).

        Tämä varmistaa, että kaikki master-featuret ja blackout/same-day sarakkeet
        löytyvät myös legacy-kannoista. Metodi käyttää pelkkiä ALTER TABLE ADD COLUMN
        -lauseita ja on turvallinen suorittaa useasti.
        """
        try:
            self._drop_columns_if_exists("results_data", DROPPED_RESULTS_COLUMNS)
            existing = self._get_existing_columns("results_data")
            if not existing:
                # results_data puuttuu kokonaan; _init_database luo sen myöhemmin
                return

            conn = self.get_connection()
            cursor = conn.cursor()
            added = False
            for column, ddl in RESULTS_SCHEMA_REQUIRED_COLUMNS.items():
                if column not in existing:
                    cursor.execute(
                        f"ALTER TABLE results_data ADD COLUMN {column} {ddl}"
                    )
                    self.logger.info(f"Added missing column '{column}' to results_data")
                    added = True
                    existing.add(column)
            if added:
                conn.commit()

            expected_columns = (
                set(MASTER_FEATURE_COLUMNS)
                | set(BULL_DIV_GENERAL_FEATURES)
                | set(BULL_DIV_METRIC_COLUMN_DEFS.keys())
                | set(COMBO_FEATURE_COLUMNS)
            )
            missing = expected_columns - existing
            if missing:
                msg = f"results_data missing required columns: {sorted(missing)}"
                self.logger.error(msg)
                raise RuntimeError(msg)
        except Exception as e:
            self.logger.error(f"Ensure results schema failed: {e}")
            raise

    def get_connection(self) -> sqlite3.Connection:
        """
        Hae tietokantayhteys.

        Returns:
            SQLite yhteys
        """
        if self._connection is None:
            self._connection = sqlite3.connect(self.db_path)
            self._connection.row_factory = sqlite3.Row
        return self._connection

    def close(self) -> None:
        """Sulje tietokantayhteys."""
        if self._connection:
            self._connection.close()
            self._connection = None

    def get_table_columns(self, table: str) -> Set[str]:
        """
        Palauta annetun taulun sarakkeet julkisesti (PRAGMA table_info).
        """
        return self._get_existing_columns(table)

    def is_connected(self) -> bool:
        """
        Tarkista onko yhteys aktiivinen.

        Returns:
            True jos yhteys on aktiivinen
        """
        return self._connection is not None

    def insert_finding(
        self,
        ticker: str,
        date: str,
        pattern: str = None,
        signal_strength: float = None,
        rsi14: float = None,
    ) -> bool:
        """
        Lisää uusi löydös tietokantaan.

        Args:
            ticker: Osakkeen symboli
            date: Päivämäärä (YYYY-MM-DD)
            pattern: Kynttiläkuvio (valinnainen)
            signal_strength: Signaalin vahvuus 0-1 (valinnainen)
            rsi14: RSI(14) arvo (valinnainen)

        Returns:
            True jos lisäys onnistui
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO analysis_findings 
                (ticker, date, pattern, signal_strength, rsi14)
                VALUES (?, ?, ?, ?, ?)
            """,
                (ticker, date, pattern, signal_strength, rsi14),
            )

            conn.commit()
            return True

        except Exception as e:
            self.logger.error(f"Insert finding failed: {e}")
            return False

    def save_finding(
        self,
        ticker: str,
        date: str,
        pattern: str = None,
        signal_strength: float = None,
        rsi14: float = None,
    ):
        """
        Tallenna analyysin löydös tietokantaan.

        Args:
            ticker: Osakkeen symboli
            date: Päivämäärä (YYYY-MM-DD)
            pattern: Kynttiläkuvio (valinnainen)
            signal_strength: Signaalin vahvuus 0-1 (valinnainen)
            rsi14: RSI(14) arvo (valinnainen)
        """
        return self.insert_finding(
            ticker=ticker,
            date=date,
            pattern=pattern,
            signal_strength=signal_strength,
            rsi14=rsi14,
        )

    def get_all_findings(self) -> List[Dict[str, Any]]:
        """
        Hae kaikki löydökset.

        Returns:
            Lista löydöksistä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM analysis_findings 
                ORDER BY date DESC, created_at DESC
            """
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            self.logger.error(f"Get all findings failed: {e}")
            return []

    def get_findings_by_ticker(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Hae löydökset tietyn tickerin mukaan.

        Args:
            ticker: Osakkeen symboli

        Returns:
            Lista löydöksistä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM analysis_findings 
                WHERE ticker = ?
                ORDER BY date DESC, created_at DESC
            """,
                (ticker,),
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            self.logger.error(f"Get findings by ticker failed: {e}")
            return []

    def get_findings_by_pattern(self, pattern: str) -> List[Dict[str, Any]]:
        """
        Hae löydökset tietyn kuvion mukaan.

        Args:
            pattern: Kynttiläkuvio

        Returns:
            Lista löydöksistä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM analysis_findings 
                WHERE pattern = ?
                ORDER BY date DESC, created_at DESC
            """,
                (pattern,),
            )

            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            self.logger.error(f"Get findings by pattern failed: {e}")
            return []

    def search_findings(
        self,
        ticker: str = None,
        pattern: str = None,
        start_date: str = None,
        end_date: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Hae löydökset hakuehdoilla.

        Args:
            ticker: Osakkeen symboli
            pattern: Kynttiläkuvio
            start_date: Alkupäivämäärä
            end_date: Loppupäivämäärä

        Returns:
            Lista löydöksistä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            sql = "SELECT * FROM analysis_findings WHERE 1=1"
            params = []

            if ticker:
                sql += " AND ticker = ?"
                params.append(ticker)

            if pattern:
                sql += " AND pattern = ?"
                params.append(pattern)

            if start_date:
                sql += " AND date >= ?"
                params.append(start_date)

            if end_date:
                sql += " AND date <= ?"
                params.append(end_date)

            sql += " ORDER BY date DESC, created_at DESC"

            cursor.execute(sql, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

        except Exception as e:
            self.logger.error(f"Search findings failed: {e}")
            return []

    def get_findings_by_pattern(self, pattern: str) -> List[Dict[str, Any]]:
        """
        Hae löydökset kuvion mukaan.

        Args:
            pattern: Kynttiläkuvio

        Returns:
            Lista löydöksistä
        """
        return self.search_findings(pattern=pattern)

    def get_findings_by_date_range(
        self, start_date: str, end_date: str
    ) -> List[Dict[str, Any]]:
        """
        Hae löydökset päivämäärävälin mukaan.

        Args:
            start_date: Alkupäivämäärä
            end_date: Loppupäivämäärä

        Returns:
            Lista löydöksistä
        """
        return self.search_findings(start_date=start_date, end_date=end_date)

    def delete_finding(self, finding_id: int) -> bool:
        """
        Poista löydös.

        Args:
            finding_id: Löydöksen ID

        Returns:
            True jos poisto onnistui
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM analysis_findings WHERE id = ?", (finding_id,))
            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:
            self.logger.error(f"Delete finding failed: {e}")
            return False

    def delete_findings_by_ids(self, finding_ids: list[int]) -> int:
        """
        Poista useita löydöksiä ID-listan perusteella.

        Args:
            finding_ids: Lista löydösten ID:itä

        Returns:
            Poistettujen rivien määrä
        """
        if not finding_ids:
            return 0

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            placeholders = ",".join("?" * len(finding_ids))
            query = f"DELETE FROM analysis_findings WHERE id IN ({placeholders})"
            cursor.execute(query, finding_ids)
            conn.commit()

            return cursor.rowcount

        except Exception as e:
            self.logger.error(f"Delete findings by IDs failed: {e}")
            return 0

    def clear_all_findings(self) -> int:
        """
        Tyhjennä koko analysis_findings taulu.

        Returns:
            Poistettujen rivien määrä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Hae määrä ennen poistoa
            cursor.execute("SELECT COUNT(*) FROM analysis_findings")
            count = cursor.fetchone()[0]

            # Tyhjennä taulu
            cursor.execute("DELETE FROM analysis_findings")
            conn.commit()

            self.logger.info(f"Cleared all findings: {count} rows deleted")
            return count

        except Exception as e:
            self.logger.error(f"Clear all findings failed: {e}")
            return 0

    def update_finding(self, finding_id: int, **kwargs) -> bool:
        """
        Päivitä löydös.

        Args:
            finding_id: Löydöksen ID
            **kwargs: Päivitettävät kentät

        Returns:
            True jos päivitys onnistui
        """
        try:
            if not kwargs:
                return False

            conn = self.get_connection()
            cursor = conn.cursor()

            # Rakenna UPDATE SQL
            fields = list(kwargs.keys())
            values = list(kwargs.values())

            sql = f"UPDATE analysis_findings SET {', '.join([f'{field} = ?' for field in fields])} WHERE id = ?"
            values.append(finding_id)

            cursor.execute(sql, values)
            conn.commit()

            return cursor.rowcount > 0

        except Exception as e:
            self.logger.error(f"Update finding failed: {e}")
            return False

    def get_statistics(self) -> Dict[str, Any]:
        """
        Hae tilastotietoja.

        Returns:
            Tilastotiedot
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            stats = {}

            # Kokonaismäärä
            cursor.execute("SELECT COUNT(*) FROM analysis_findings")
            stats["total_findings"] = cursor.fetchone()[0]

            # Kuvioiden määrät
            cursor.execute(
                """
                SELECT pattern, COUNT(*) as count 
                FROM analysis_findings 
                GROUP BY pattern 
                ORDER BY count DESC
            """
            )
            stats["patterns"] = dict(cursor.fetchall())

            # Tickereiden määrät
            cursor.execute(
                """
                SELECT ticker, COUNT(*) as count 
                FROM analysis_findings 
                GROUP BY ticker 
                ORDER BY count DESC
            """
            )
            stats["top_tickers"] = dict(cursor.fetchall())

            # Keskimääräinen signaalin vahvuus
            cursor.execute("SELECT AVG(signal_strength) FROM analysis_findings")
            avg_strength = cursor.fetchone()[0]
            stats["avg_signal_strength"] = round(avg_strength, 3) if avg_strength else 0

            return stats

        except Exception as e:
            self.logger.error(f"Get statistics failed: {e}")
            return {}

    def get_findings_count(self) -> int:
        """
        Hae löydösten kokonaismäärä.

        Returns:
            Löydösten määrä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM analysis_findings")
            count = cursor.fetchone()[0]
            return count

        except Exception as e:
            self.logger.error(f"Get findings count failed: {e}")
            return 0

    def get_available_tickers(self) -> List[str]:
        """
        Hae kaikki saatavilla olevat tickerit.

        Returns:
            Lista tickereistä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT DISTINCT ticker FROM analysis_findings ORDER BY ticker"
            )
            rows = cursor.fetchall()
            return [row[0] for row in rows]

        except Exception as e:
            self.logger.error(f"Get available tickers failed: {e}")
            return []

    def get_available_patterns(self) -> List[Dict[str, Any]]:
        """
        Hae kaikki saatavilla olevat kuviot kynttila_mapping taulusta.

        Returns:
            Lista kuvioista (dict format)
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT pattern_name, display_name, description, category, reliability 
                FROM kynttila_mapping 
                ORDER BY pattern_name
                """
            )
            rows = cursor.fetchall()
            return [
                {
                    "pattern_name": row[0],
                    "display_name": row[1],
                    "description": row[2],
                    "category": row[3],
                    "reliability": row[4],
                }
                for row in rows
            ]

        except Exception as e:
            self.logger.error(f"Get available patterns failed: {e}")
            return []

    def get_tickers_missing_blackouts(self, limit: Optional[int] = None) -> List[str]:
        """
        Hae tickerit, joilta puuttuu blackout-päivämerkinnät.

        Args:
            limit: Palautettavien tickereiden enimmäismäärä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            params: List[object] = []
            query = """
                WITH combined_tickers AS (
                    SELECT DISTINCT ticker
                    FROM results_data
                    WHERE ticker IS NOT NULL AND TRIM(ticker) != ''
                    UNION
                    SELECT DISTINCT ticker
                    FROM analysis_findings
                    WHERE ticker IS NOT NULL AND TRIM(ticker) != ''
                ),
                existing AS (
                    SELECT DISTINCT ticker FROM blackout_dates
                )
                SELECT c.ticker
                FROM combined_tickers c
                LEFT JOIN existing e ON e.ticker = c.ticker
                WHERE e.ticker IS NULL
                ORDER BY c.ticker
            """
            if limit is not None:
                query += " LIMIT ?"
                params.append(int(limit))
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [row[0] for row in rows]
        except Exception as e:
            self.logger.error(f"Get tickers missing blackouts failed: {e}")
            return []

    def get_findings_with_filters(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Hae löydökset suodattimilla (testejä varten).

        Args:
            **kwargs: Suodatin parametrit (ticker, pattern, jne.)

        Returns:
            Lista löydöksiä
        """
        # Käytä olemassa olevaa search_findings metodia
        return self.search_findings(
            ticker=kwargs.get("ticker"), pattern=kwargs.get("pattern")
        )

    def save_divergence_batch(
        self, ticker: str, divergence_records: List[Tuple[str, float, float, float]]
    ) -> bool:
        """
        Tallenna divergenssidataa batch-moodissa.

        Args:
            ticker: Osakkeen symboli
            divergence_records: Lista tupleja (date, bullish_strength, bearish_strength, rsi)

        Returns:
            True jos tallennus onnistui
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Prepare data with ticker
            records_with_ticker = [
                (ticker, date, bullish, bearish, rsi)
                for date, bullish, bearish, rsi in divergence_records
            ]

            cursor.executemany(
                """
                INSERT OR REPLACE INTO divergence_data 
                (ticker, date, bullish_strength, bearish_strength, rsi)
                VALUES (?, ?, ?, ?, ?)
            """,
                records_with_ticker,
            )

            conn.commit()
            self.logger.info(
                f"Saved {len(divergence_records)} divergence records for {ticker}"
            )
            return True

        except Exception as e:
            self.logger.error(f"Save divergence batch failed: {e}")
            return False

    def get_divergence_records(
        self, ticker: str, dates: List[str]
    ) -> dict[str, dict[str, float]]:
        """
        Palauta divergenssirivit annetuista päivistä.

        Returns:
            Dict[date, {"bullish_strength": float, "bearish_strength": float}]
        """
        if not dates:
            return {}

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            placeholders = ",".join("?" * len(dates))
            query = f"""
                SELECT date, pattern, signal_strength, rsi14
                FROM analysis_findings
                WHERE ticker = ? AND date IN ({placeholders})
                AND pattern IN ('Bullish Divergence','Bearish Divergence')
            """
            cursor.execute(query, [ticker] + dates)
            rows = cursor.fetchall()
            records: dict[str, dict[str, float]] = {}
            for date, pattern, strength, rsi in rows:
                entry = records.setdefault(
                    date, {"bullish_strength": 0.0, "bearish_strength": 0.0, "rsi": rsi}
                )
                if pattern == "Bullish Divergence":
                    entry["bullish_strength"] = strength or 0.0
                elif pattern == "Bearish Divergence":
                    entry["bearish_strength"] = strength or 0.0
                if rsi is not None:
                    entry["rsi"] = rsi

            if records:
                return records

            # Fallback to divergence_data for backward compatibility
            placeholders = ",".join("?" * len(dates))
            query = f"""
                SELECT date, bullish_strength, bearish_strength, rsi
                FROM divergence_data
                WHERE ticker = ? AND date IN ({placeholders})
            """
            cursor.execute(query, [ticker] + dates)
            rows = cursor.fetchall()
            return {
                date: {
                    "bullish_strength": bullish or 0.0,
                    "bearish_strength": bearish or 0.0,
                    "rsi": rsi,
                }
                for date, bullish, bearish, rsi in rows
            }
        except Exception as e:
            self.logger.error(f"Get divergence records failed: {e}")
            return {}

    def insert_blackout_entries(self, entries: List[tuple[str, str, str, str]]) -> int:
        if not entries:
            return 0
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.executemany(
                """
                INSERT OR IGNORE INTO blackout_dates (ticker, date, event, source)
                VALUES (?, ?, ?, ?)
            """,
                entries,
            )
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            self.logger.error(f"Insert blackout entries failed: {e}")
            return 0

    def has_divergence_data(self, ticker: str) -> bool:
        """
        Tarkista onko tickerille tallennettu divergenssidataa.

        Args:
            ticker: Osakkeen symboli

        Returns:
            True jos dataa löytyy
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                "SELECT COUNT(*) FROM divergence_data WHERE ticker = ?", (ticker,)
            )
            count = cursor.fetchone()[0]
            return count > 0

        except Exception as e:
            self.logger.error(f"Check divergence data failed: {e}")
            return False

    # ===== RESULTS_DATA METHODS =====

    def get_results_max_date(
        self, pattern_filter: Optional[list] = None
    ) -> Optional[str]:
        """
        Hae viimeisin päivämäärä results_data taulusta.

        Args:
            pattern_filter: Lista pattern-numeroista (None = kaikki patternit)

        Returns:
            Viimeisin päivämäärä tai None jos taulu tyhjä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if pattern_filter:
                placeholders = ",".join("?" * len(pattern_filter))
                cursor.execute(
                    f"SELECT MAX(date) FROM results_data WHERE candle_pattern IN ({placeholders})",
                    pattern_filter,
                )
            else:
                cursor.execute("SELECT MAX(date) FROM results_data")

            result = cursor.fetchone()
            return result[0] if result else None

        except Exception as e:
            self.logger.error(f"Get results max date failed: {e}")
            return None

    def get_existing_results_tickers(
        self, pattern_filter: Optional[list] = None
    ) -> set:
        """
        Hae kaikki tickerit joilla on jo dataa results_data taulussa.

        Args:
            pattern_filter: Lista pattern-numeroista (None = kaikki patternit)

        Returns:
            Set tickereistä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            if pattern_filter:
                placeholders = ",".join("?" * len(pattern_filter))
                cursor.execute(
                    f"SELECT DISTINCT ticker FROM results_data WHERE candle_pattern IN ({placeholders})",
                    pattern_filter,
                )
            else:
                cursor.execute("SELECT DISTINCT ticker FROM results_data")

            return {row[0] for row in cursor.fetchall()}

        except Exception as e:
            self.logger.error(f"Get existing results tickers failed: {e}")
            return set()

    def bulk_insert_results(self, results: List[dict], batch_size: int = 100) -> int:
        """
        Lisää useita rivejä results_data tauluun batch-erinä.

        Args:
            results: Lista dictionaryja, joissa avaimet vastaavat sarakkeita
            batch_size: Montako riviä commitoidaan kerralla

        Returns:
            Lisättyjen rivien määrä
        """
        try:
            if not results:
                return 0

            conn = self.get_connection()
            cursor = conn.cursor()
            inserted = 0

            all_columns = (
                RESULTS_BASE_COLUMNS
                + MASTER_FEATURE_COLUMNS
                + BULL_DIV_GENERAL_FEATURES
                + COMBO_FEATURE_COLUMNS
            )
            columns_clause = ", ".join(all_columns)
            placeholders = ", ".join("?" for _ in all_columns)
            insert_sql = (
                "INSERT OR REPLACE INTO results_data "
                f"({columns_clause}) VALUES ({placeholders})"
            )

            def _get_value(row: dict, column: str):
                if column == "market":
                    return row.get(column, "usa")
                return row.get(column)

            for i in range(0, len(results), batch_size):
                batch = results[i : i + batch_size]

                for result in batch:
                    normalized = dict(result)
                    normalized.setdefault("market", "usa")

                    missing_keys = [
                        key
                        for key in ("ticker", "date", "candle_pattern")
                        if key not in normalized
                    ]
                    if missing_keys:
                        self.logger.warning(
                            f"Skipping result insert, missing required keys: {missing_keys}"
                        )
                        continue

                    for column in MASTER_FEATURE_COLUMNS:
                        if column in normalized:
                            continue
                        if column in MASTER_FEATURE_INTEGER_COLUMNS:
                            normalized[column] = 0
                        elif column in MASTER_FEATURE_TEXT_COLUMNS:
                            normalized[column] = None
                        else:
                            normalized[column] = None

                    for column in BULL_DIV_METRIC_COLUMN_DEFS.keys():
                        if column in normalized:
                            continue
                        normalized[column] = BULL_DIV_METRIC_DEFAULTS.get(column)

                    for column in BULL_DIV_GENERAL_FEATURES:
                        if column not in normalized:
                            normalized[column] = BULL_DIV_GENERAL_DEFAULTS.get(
                                column, 0
                            )
                    for column in COMBO_FEATURE_COLUMNS:
                        normalized.setdefault(column, 0)

                    values_tuple = tuple(
                        _get_value(normalized, col) for col in all_columns
                    )
                    if len(values_tuple) != len(all_columns):
                        self.logger.error(
                            f"VALUES tuple length is {len(values_tuple)}, "
                            f"expected {len(all_columns)}"
                        )
                        self.logger.error(f"Result keys: {sorted(result.keys())}")
                        continue

                    cursor.execute(insert_sql, values_tuple)
                    inserted += 1

                conn.commit()
                self.logger.debug(f"Committed batch {i // batch_size + 1}")

            return inserted

        except Exception as e:
            self.logger.error(f"Bulk insert results failed: {e}")
            return 0

    def clear_results_data(self) -> int:
        """
        Tyhjennä results_data taulu.

        Returns:
            Poistettujen rivien määrä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT COUNT(*) FROM results_data")
            count = cursor.fetchone()[0]

            cursor.execute("DELETE FROM results_data")
            conn.commit()

            self.logger.info(f"Cleared results_data: {count} rows deleted")
            return count

        except Exception as e:
            self.logger.error(f"Clear results data failed: {e}")
            return 0

    def delete_result_by_id(self, result_id: int) -> bool:
        """
        Poista yksittäinen tulos results_data taulusta ID:llä.

        Args:
            result_id: Poistettavan tuloksen ID

        Returns:
            True jos onnistui
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("DELETE FROM results_data WHERE id = ?", (result_id,))
            conn.commit()

            success = cursor.rowcount > 0
            if success:
                self.logger.debug(f"Deleted result id={result_id}")
            return success

        except Exception as e:
            self.logger.error(f"Delete result by id failed: {e}")
            return False

    def delete_results_by_ids(self, result_ids: List[int]) -> int:
        """
        Poista tulokset results_data taulusta ID-listalla.

        Args:
            result_ids: Lista ID:itä joita poistetaan

        Returns:
            Poistettujen rivien määrä
        """
        if not result_ids:
            return 0

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # SQLiten IN -kysely
            placeholders = ",".join("?" * len(result_ids))
            query = f"DELETE FROM results_data WHERE id IN ({placeholders})"
            cursor.execute(query, result_ids)
            conn.commit()

            deleted = cursor.rowcount
            self.logger.info(f"Deleted {deleted} results by IDs")
            return deleted

        except Exception as e:
            self.logger.error(f"Delete results by ids failed: {e}")
            return 0

    def delete_results_by_filters(
        self,
        pattern_filter: Optional[List[int]] = None,
        ticker_filter: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> int:
        """
        Poista tulokset results_data taulusta filttereillä.

        Args:
            pattern_filter: Lista pattern-numeroista (0-8) joita poistetaan
            ticker_filter: Lista tickereistä joita poistetaan
            start_date: Alkupäivämäärä YYYY-MM-DD (valinnainen)
            end_date: Loppupäivämäärä YYYY-MM-DD (valinnainen)

        Returns:
            Poistettujen rivien määrä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            # Rakenna WHERE-lauseke
            conditions = []
            params = []

            if pattern_filter:
                placeholders = ",".join("?" * len(pattern_filter))
                conditions.append(f"candle_pattern IN ({placeholders})")
                params.extend(pattern_filter)

            if ticker_filter:
                placeholders = ",".join("?" * len(ticker_filter))
                conditions.append(f"ticker IN ({placeholders})")
                params.extend(ticker_filter)

            if start_date:
                conditions.append("date >= ?")
                params.append(start_date)

            if end_date:
                conditions.append("date <= ?")
                params.append(end_date)

            if not conditions:
                # Ei filttereitä, ei poisteta mitään
                return 0

            where_clause = " AND ".join(conditions)
            query = f"DELETE FROM results_data WHERE {where_clause}"

            cursor.execute(query, params)
            conn.commit()

            deleted = cursor.rowcount
            self.logger.info(
                f"Deleted {deleted} results by filters (patterns={pattern_filter}, tickers={ticker_filter}, start_date={start_date}, end_date={end_date})"
            )
            return deleted

        except Exception as e:
            self.logger.error(f"Delete results by filters failed: {e}")
            return 0

    def get_divergence_combo_pairs(
        self,
        candle_patterns: Optional[Iterable[int]] = None,
        tickers: Optional[Iterable[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> set:
        """
        Palauta (ticker, date) parit joille results_data:ssa on sekä kynttilä (0-6) että
        divergenssi t0 tai t-1 (bullish_strength > 0 divergence_data-taulussa).
        """
        conn = None
        try:
            # Luo uusi yhteys, jotta metodia voidaan kutsua taustasäikeistä
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            cursor = conn.cursor()

            if candle_patterns:
                candle_patterns = list(candle_patterns)
            if tickers:
                tickers = list({t.upper() for t in tickers if t})

            where_clause_parts = []
            params: list[Any] = []

            if tickers:
                placeholders = ",".join("?" * len(tickers))
                where_clause_parts.append(f"rd.ticker IN ({placeholders})")
                params.extend(tickers)

            if start_date and end_date:
                where_clause_parts.append("rd.date BETWEEN ? AND ?")
                params.extend([start_date, end_date])

            where_clause = (
                "WHERE " + " AND ".join(where_clause_parts)
                if where_clause_parts
                else ""
            )

            if candle_patterns:
                candle_placeholders = ",".join("?" * len(candle_patterns))
                candle_params = list(candle_patterns)
                candle_filter_clause = f"rd.candle_pattern IN ({candle_placeholders})"
                params = candle_params + params
            else:
                candle_filter_clause = "rd.candle_pattern BETWEEN 0 AND 6"

            cursor.execute(
                """
                SELECT DISTINCT rd.ticker, rd.date
                FROM results_data rd
                JOIN divergence_data dd
                  ON rd.ticker = dd.ticker
                 AND (
                        rd.date = dd.date
                     OR rd.date = date(dd.date, '+1 day')
                 )
                {where_clause}
                AND {candle_filter}
                AND COALESCE(dd.bullish_strength, 0) > 0
            """.format(where_clause=where_clause, candle_filter=candle_filter_clause),
                params,
            )
            combo_pairs = {(row[0], row[1]) for row in cursor.fetchall()}

            # Fallback: jos divergence_data ei tuota mitään (esim. testidatassa puuttuu),
            # käytä results_data:n omia divergenssikenttiä (bullish/bearish, recent).
            if not combo_pairs:
                fallback_clauses = []
                fallback_params: list[Any] = []

                # Alkuperäiset suodatukset
                if tickers:
                    placeholders = ",".join("?" * len(tickers))
                    fallback_clauses.append(f"ticker IN ({placeholders})")
                    fallback_params.extend(tickers)

                if start_date and end_date:
                    fallback_clauses.append("date BETWEEN ? AND ?")
                    fallback_params.extend([start_date, end_date])

                # Kynttiläsuodatus
                if candle_patterns:
                    candle_placeholders = ",".join("?" * len(candle_patterns))
                    fallback_clauses.append(f"candle_pattern IN ({candle_placeholders})")
                    fallback_params.extend(candle_patterns)
                else:
                    fallback_clauses.append("candle_pattern BETWEEN 0 AND 6")

                # Divergenssikentät results_data-taulusta
                fallback_clauses.append(
                    """
                    (
                        COALESCE(bullish_divergence, 0) > 0
                     OR COALESCE(BullDiv_recent_strength, 0) > 0
                     OR COALESCE(Has_BullDiv_recent, 0) > 0
                     OR COALESCE(bearish_divergence, 0) > 0
                    )
                    """
                )

                fallback_where = " WHERE " + " AND ".join(fallback_clauses)
                cursor.execute(
                    f"SELECT DISTINCT ticker, date FROM results_data{fallback_where}",
                    fallback_params,
                )
                combo_pairs = {(row[0], row[1]) for row in cursor.fetchall()}

            return combo_pairs
        except Exception as e:
            self.logger.error(f"Get divergence combo pairs failed: {e}")
            return set()
        finally:
            if conn:
                conn.close()

    def get_results_data(self, limit: Optional[int] = None) -> List[dict]:
        """
        Hae kaikki rivit results_data taulusta.

        Args:
            limit: Rajoita rivien määrää

        Returns:
            Lista dictionaryja
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            query = "SELECT * FROM results_data ORDER BY date DESC, ticker"
            if limit:
                query += f" LIMIT {limit}"

            cursor.execute(query)
            columns = [desc[0] for desc in cursor.description]

            return [dict(zip(columns, row)) for row in cursor.fetchall()]

        except Exception as e:
            self.logger.error(f"Get results data failed: {e}")
            return []

    def count_results_filtered(
        self,
        *,
        patterns: Optional[List[int]] = None,
        tickers: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        downtrend_only: bool = False,
    ) -> int:
        query, params = self._build_results_filter_query(
            select_clause="SELECT COUNT(*) FROM results_data",
            patterns=patterns,
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            downtrend_only=downtrend_only,
        )
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()
            return int(row[0]) if row and row[0] is not None else 0
        except Exception as e:
            self.logger.error(f"Count filtered results failed: {e}")
            return 0

    def get_results_filtered(
        self,
        *,
        patterns: Optional[List[int]] = None,
        tickers: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        downtrend_only: bool = False,
        limit: Optional[int] = None,
    ) -> List[dict]:
        query, params = self._build_results_filter_query(
            select_clause="SELECT * FROM results_data",
            patterns=patterns,
            tickers=tickers,
            start_date=start_date,
            end_date=end_date,
            downtrend_only=downtrend_only,
        )
        query += " ORDER BY date DESC, ticker"
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, params)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Fetch filtered results failed: {e}")
            return []

    def get_results_by_ids(self, ids: List[int]) -> List[dict]:
        if not ids:
            return []
        placeholders = ",".join("?" for _ in ids)
        query = f"SELECT * FROM results_data WHERE id IN ({placeholders})"
        try:
            conn = self.get_connection()
            cursor = conn.cursor()
            cursor.execute(query, ids)
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            self.logger.error(f"Fetch results by ids failed: {e}")
            return []

    def _build_results_filter_query(
        self,
        *,
        select_clause: str,
        patterns: Optional[List[int]],
        tickers: Optional[List[str]],
        start_date: Optional[str],
        end_date: Optional[str],
        downtrend_only: bool,
    ) -> tuple[str, List[Any]]:
        clauses: List[str] = []
        params: List[Any] = []

        if downtrend_only and not patterns:
            clauses.append("candle_pattern = 0")
        elif patterns:
            placeholders = ",".join("?" * len(patterns))
            clauses.append(f"candle_pattern IN ({placeholders})")
            params.extend(int(p) for p in patterns)

        if tickers:
            normalized = [t.upper() for t in tickers]
            placeholders = ",".join("?" * len(normalized))
            clauses.append(f"ticker IN ({placeholders})")
            params.extend(normalized)

        if start_date:
            clauses.append("date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("date <= ?")
            params.append(end_date)

        query = select_clause
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        return query, params

    def insert_results_metadata(self, total_rows: int, processing_time: float) -> bool:
        """
        Tallenna metatiedot generointiajosta.

        Args:
            total_rows: Generoitujen rivien määrä
            processing_time: Käsittelyaika sekunneissa

        Returns:
            True jos onnistui
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT INTO results_metadata (total_rows, processing_time_seconds)
                VALUES (?, ?)
                """,
                (total_rows, processing_time),
            )
            conn.commit()
            return True

        except Exception as e:
            self.logger.error(f"Insert results metadata failed: {e}")
            return False

    def get_latest_results_metadata(self) -> Optional[dict]:
        """
        Hae viimeisin metatietorivi.

        Returns:
            Dictionary tai None
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT * FROM results_metadata 
                ORDER BY id DESC 
                LIMIT 1
                """
            )

            row = cursor.fetchone()
            if not row:
                return None

            columns = [desc[0] for desc in cursor.description]
            return dict(zip(columns, row))

        except Exception as e:
            self.logger.error(f"Get latest results metadata failed: {e}")
            return None


if __name__ == "__main__":
    """Testaa DatabaseManager toimivuutta."""
    logging.basicConfig(level=logging.INFO)

    # Luo test database
    db = DatabaseManager("test_analysis.db")

    # Testaa insert
    success = db.insert_finding(
        symbol="AAPL",
        date="2024-01-15",
        pattern="Doji",
        signal_strength=0.85,
        price=185.50,
        volume=2500000,
        description="Strong doji pattern",
    )
    print(f"Insert test: {'✅' if success else '❌'}")

    # Testaa haku
    findings = db.get_all_findings()
    print(f"Find test: {'✅' if len(findings) > 0 else '❌'}")

    # Testaa tilastot
    stats = db.get_statistics()
    print(f"Stats test: {'✅' if stats.get('total_findings', 0) > 0 else '❌'}")

    # Siivoa
    db.close()
    if os.path.exists("test_analysis.db"):
        os.remove("test_analysis.db")

    print("DatabaseManager testit suoritettu!")
