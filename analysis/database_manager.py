"""
Analysis Database Manager
Hallinnoi analysis-tietokannan operaatiot.
"""

import sqlite3
import os
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging


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

            # Luo results_data taulu
            # Tallentaa prosessoidut tulokset (vain kynttiläkuviopäivät)
            # 84 saraketta (83 alkuperäistä + weekday)
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS results_data (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
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
                    weekday INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, date)
                )
            """
            )

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

    def get_divergences_for_dates(
        self, ticker: str, dates: List[str]
    ) -> Tuple[float, float]:
        """
        Hae divergenssit annetuille päiville (t0, t-1, t-2, t-3).

        Args:
            ticker: Osakkeen symboli
            dates: Lista päivämääriä

        Returns:
            Tuple (bearish_strength, bullish_strength) missä arvo on vahvin löydetty divergenssi
        """
        if not dates:
            return (0.0, 0.0)

        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            placeholders = ",".join("?" * len(dates))
            query = f"""
                SELECT bullish_strength, bearish_strength
                FROM divergence_data
                WHERE ticker = ? AND date IN ({placeholders})
            """

            cursor.execute(query, [ticker] + dates)
            results = cursor.fetchall()

            # Etsi vahvin divergenssi
            max_bullish = 0.0
            max_bearish = 0.0

            for row in results:
                bullish, bearish = row
                if bullish and bullish > max_bullish:
                    max_bullish = bullish
                if bearish and bearish > max_bearish:
                    max_bearish = bearish

            # Mutual exclusivity: jos bullish löytyy, bearish = 0
            if max_bullish > 0:
                return (0.0, max_bullish)
            elif max_bearish > 0:
                return (max_bearish, 0.0)
            else:
                return (0.0, 0.0)

        except Exception as e:
            self.logger.error(f"Get divergences for dates failed: {e}")
            return (0.0, 0.0)

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

    def get_results_max_date(self) -> Optional[str]:
        """
        Hae viimeisin päivämäärä results_data taulusta.

        Returns:
            Viimeisin päivämäärä tai None jos taulu tyhjä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT MAX(date) FROM results_data")
            result = cursor.fetchone()
            return result[0] if result else None

        except Exception as e:
            self.logger.error(f"Get results max date failed: {e}")
            return None

    def get_existing_results_tickers(self) -> set:
        """
        Hae kaikki tickerit joilla on jo dataa results_data taulussa.

        Returns:
            Set tickereistä
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute("SELECT DISTINCT ticker FROM results_data")
            return {row[0] for row in cursor.fetchall()}

        except Exception as e:
            self.logger.error(f"Get existing results tickers failed: {e}")
            return set()

    def insert_result_data(
        self,
        ticker: str,
        date: str,
        candle_pattern: int,
        signal_strength: Optional[float],
        t_1_alin: Optional[float],
        t_1_ylin: Optional[float],
        t_1_bodi: Optional[float],
        t_1_bodi_colour: Optional[int],
        t0_alin: Optional[float],
        t0_ylin: Optional[float],
        t0_bodi: Optional[float],
        t0_bodi_colour: Optional[int],
        t1_alin: Optional[float],
        t1_ylin: Optional[float],
        t1_bodi: Optional[float],
        t1_bodi_colour: Optional[int],
        t_2: Optional[float],
        t_5: Optional[float],
        t_10: Optional[float],
        t_15: Optional[float],
        t_20: Optional[float],
        t_2_hajonta: Optional[float],
        t_5_hajonta: Optional[float],
        t_10_hajonta: Optional[float],
        t_15_hajonta: Optional[float],
        t_20_hajonta: Optional[float],
        t2: Optional[float],
        t5: Optional[float],
        t10: Optional[float],
        t20: Optional[float],
        t_2_volyymi: Optional[float],
        t_5_volyymi: Optional[float],
        t_10_volyymi: Optional[float],
        t_15_volyymi: Optional[float],
        t_20_volyymi: Optional[float],
        t0_volyymi: Optional[float],
        t2_volyymi: Optional[float],
        t5_volyymi: Optional[float],
        t10_volyymi: Optional[float],
        t20_volyymi: Optional[float],
        t_2_5p_liukuva: Optional[float],
        t_2_10p_liukuva: Optional[float],
        t_2_20p_liukuva: Optional[float],
        t_5_5p_liukuva: Optional[float],
        t_5_10p_liukuva: Optional[float],
        t_5_20p_liukuva: Optional[float],
        t_10_5p_liukuva: Optional[float],
        t_10_10p_liukuva: Optional[float],
        t_10_20p_liukuva: Optional[float],
        t_15_5p_liukuva: Optional[float],
        t_15_10p_liukuva: Optional[float],
        t_15_20p_liukuva: Optional[float],
        t_20_5p_liukuva: Optional[float],
        t_20_10p_liukuva: Optional[float],
        t_20_20p_liukuva: Optional[float],
        t0_50p_liukuva: Optional[float],
        t0_200p_liukuva: Optional[float],
        SPX_0: Optional[float],
        SPX_2: Optional[float],
        SPX_5: Optional[float],
        SPX_10: Optional[float],
        SPX_15: Optional[float],
        SPX_20: Optional[float],
        SPX2: Optional[float],
        SPX5: Optional[float],
        SPX10: Optional[float],
        SPX15: Optional[float],
        SPX20: Optional[float],
        NDX_0: Optional[float],
        NDX_2: Optional[float],
        NDX_5: Optional[float],
        NDX_10: Optional[float],
        NDX_15: Optional[float],
        NDX_20: Optional[float],
        NDX2: Optional[float],
        NDX5: Optional[float],
        NDX10: Optional[float],
        NDX15: Optional[float],
        NDX20: Optional[float],
        RSI14_t0: Optional[float],
        t0_close_norm: Optional[float],
        bearish_divergence: Optional[float],
        bullish_divergence: Optional[float],
        weekday: int,
    ) -> bool:
        """
        Lisää rivi results_data tauluun.

        Returns:
            True jos onnistui
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            cursor.execute(
                """
                INSERT OR REPLACE INTO results_data
                (ticker, date, candle_pattern, signal_strength,
                 t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour,
                 t0_alin, t0_ylin, t0_bodi, t0_bodi_colour,
                 t1_alin, t1_ylin, t1_bodi, t1_bodi_colour,
                 t_2, t_5, t_10, t_15, t_20,
                 t_2_hajonta, t_5_hajonta, t_10_hajonta, t_15_hajonta, t_20_hajonta,
                 t2, t5, t10, t20,
                 t_2_volyymi, t_5_volyymi, t_10_volyymi, t_15_volyymi, t_20_volyymi,
                 t0_volyymi, t2_volyymi, t5_volyymi, t10_volyymi, t20_volyymi,
                 t_2_5p_liukuva, t_2_10p_liukuva, t_2_20p_liukuva,
                 t_5_5p_liukuva, t_5_10p_liukuva, t_5_20p_liukuva,
                 t_10_5p_liukuva, t_10_10p_liukuva, t_10_20p_liukuva,
                 t_15_5p_liukuva, t_15_10p_liukuva, t_15_20p_liukuva,
                 t_20_5p_liukuva, t_20_10p_liukuva, t_20_20p_liukuva,
                 t0_50p_liukuva, t0_200p_liukuva,
                 SPX_0, SPX_2, SPX_5, SPX_10, SPX_15, SPX_20,
                 SPX2, SPX5, SPX10, SPX15, SPX20,
                 NDX_0, NDX_2, NDX_5, NDX_10, NDX_15, NDX_20,
                 NDX2, NDX5, NDX10, NDX15, NDX20,
                 RSI14_t0, t0_close_norm, bearish_divergence, bullish_divergence, weekday)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?)
                """,
                (
                    ticker,
                    date,
                    candle_pattern,
                    signal_strength,
                    t_1_alin,
                    t_1_ylin,
                    t_1_bodi,
                    t_1_bodi_colour,
                    t0_alin,
                    t0_ylin,
                    t0_bodi,
                    t0_bodi_colour,
                    t1_alin,
                    t1_ylin,
                    t1_bodi,
                    t1_bodi_colour,
                    t_2,
                    t_5,
                    t_10,
                    t_15,
                    t_20,
                    t_2_hajonta,
                    t_5_hajonta,
                    t_10_hajonta,
                    t_15_hajonta,
                    t_20_hajonta,
                    t2,
                    t5,
                    t10,
                    t20,
                    t_2_volyymi,
                    t_5_volyymi,
                    t_10_volyymi,
                    t_15_volyymi,
                    t_20_volyymi,
                    t0_volyymi,
                    t2_volyymi,
                    t5_volyymi,
                    t10_volyymi,
                    t20_volyymi,
                    t_2_5p_liukuva,
                    t_2_10p_liukuva,
                    t_2_20p_liukuva,
                    t_5_5p_liukuva,
                    t_5_10p_liukuva,
                    t_5_20p_liukuva,
                    t_10_5p_liukuva,
                    t_10_10p_liukuva,
                    t_10_20p_liukuva,
                    t_15_5p_liukuva,
                    t_15_10p_liukuva,
                    t_15_20p_liukuva,
                    t_20_5p_liukuva,
                    t_20_10p_liukuva,
                    t_20_20p_liukuva,
                    t0_50p_liukuva,
                    t0_200p_liukuva,
                    SPX_0,
                    SPX_2,
                    SPX_5,
                    SPX_10,
                    SPX_15,
                    SPX_20,
                    SPX2,
                    SPX5,
                    SPX10,
                    SPX15,
                    SPX20,
                    NDX_0,
                    NDX_2,
                    NDX_5,
                    NDX_10,
                    NDX_15,
                    NDX_20,
                    NDX2,
                    NDX5,
                    NDX10,
                    NDX15,
                    NDX20,
                    RSI14_t0,
                    t0_close_norm,
                    bearish_divergence,
                    bullish_divergence,
                    weekday,
                ),
            )
            conn.commit()
            return True

        except Exception as e:
            self.logger.error(f"Insert result data failed: {e}")
            return False

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
            conn = self.get_connection()
            cursor = conn.cursor()
            inserted = 0

            for i in range(0, len(results), batch_size):
                batch = results[i : i + batch_size]

                for result in batch:
                    # Debug: laske tuple pituus
                    values_tuple = (
                        result["ticker"],
                        result["date"],
                        result["candle_pattern"],
                        result.get("signal_strength"),
                        result.get("t_1_alin"),
                        result.get("t_1_ylin"),
                        result.get("t_1_bodi"),
                        result.get("t_1_bodi_colour"),
                        result.get("t0_alin"),
                        result.get("t0_ylin"),
                        result.get("t0_bodi"),
                        result.get("t0_bodi_colour"),
                        result.get("t1_alin"),
                        result.get("t1_ylin"),
                        result.get("t1_bodi"),
                        result.get("t1_bodi_colour"),
                        result.get("t_2"),
                        result.get("t_5"),
                        result.get("t_10"),
                        result.get("t_15"),
                        result.get("t_20"),
                        result.get("t_2_hajonta"),
                        result.get("t_5_hajonta"),
                        result.get("t_10_hajonta"),
                        result.get("t_15_hajonta"),
                        result.get("t_20_hajonta"),
                        result.get("t2"),
                        result.get("t5"),
                        result.get("t10"),
                        result.get("t20"),
                        result.get("t_2_volyymi"),
                        result.get("t_5_volyymi"),
                        result.get("t_10_volyymi"),
                        result.get("t_15_volyymi"),
                        result.get("t_20_volyymi"),
                        result.get("t0_volyymi"),
                        result.get("t2_volyymi"),
                        result.get("t5_volyymi"),
                        result.get("t10_volyymi"),
                        result.get("t20_volyymi"),
                        result.get("t_2_5p_liukuva"),
                        result.get("t_2_10p_liukuva"),
                        result.get("t_2_20p_liukuva"),
                        result.get("t_5_5p_liukuva"),
                        result.get("t_5_10p_liukuva"),
                        result.get("t_5_20p_liukuva"),
                        result.get("t_10_5p_liukuva"),
                        result.get("t_10_10p_liukuva"),
                        result.get("t_10_20p_liukuva"),
                        result.get("t_15_5p_liukuva"),
                        result.get("t_15_10p_liukuva"),
                        result.get("t_15_20p_liukuva"),
                        result.get("t_20_5p_liukuva"),
                        result.get("t_20_10p_liukuva"),
                        result.get("t_20_20p_liukuva"),
                        result.get("t0_50p_liukuva"),
                        result.get("t0_200p_liukuva"),
                        result.get("SPX_0"),
                        result.get("SPX_2"),
                        result.get("SPX_5"),
                        result.get("SPX_10"),
                        result.get("SPX_15"),
                        result.get("SPX_20"),
                        result.get("SPX2"),
                        result.get("SPX5"),
                        result.get("SPX10"),
                        result.get("SPX15"),
                        result.get("SPX20"),
                        result.get("NDX_0"),
                        result.get("NDX_2"),
                        result.get("NDX_5"),
                        result.get("NDX_10"),
                        result.get("NDX_15"),
                        result.get("NDX_20"),
                        result.get("NDX2"),
                        result.get("NDX5"),
                        result.get("NDX10"),
                        result.get("NDX15"),
                        result.get("NDX20"),
                        result.get("RSI14_t0"),
                        result.get("t0_close_norm"),
                        result.get("bearish_divergence"),
                        result.get("bullish_divergence"),
                        result.get("weekday"),
                    )

                    if len(values_tuple) != 84:
                        self.logger.error(
                            f"VALUES tuple length is {len(values_tuple)}, expected 84"
                        )
                        self.logger.error(f"Result keys: {sorted(result.keys())}")

                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO results_data
                        (ticker, date, candle_pattern, signal_strength,
                         t_1_alin, t_1_ylin, t_1_bodi, t_1_bodi_colour,
                         t0_alin, t0_ylin, t0_bodi, t0_bodi_colour,
                         t1_alin, t1_ylin, t1_bodi, t1_bodi_colour,
                         t_2, t_5, t_10, t_15, t_20,
                         t_2_hajonta, t_5_hajonta, t_10_hajonta, t_15_hajonta, t_20_hajonta,
                         t2, t5, t10, t20,
                         t_2_volyymi, t_5_volyymi, t_10_volyymi, t_15_volyymi, t_20_volyymi,
                         t0_volyymi, t2_volyymi, t5_volyymi, t10_volyymi, t20_volyymi,
                         t_2_5p_liukuva, t_2_10p_liukuva, t_2_20p_liukuva,
                         t_5_5p_liukuva, t_5_10p_liukuva, t_5_20p_liukuva,
                         t_10_5p_liukuva, t_10_10p_liukuva, t_10_20p_liukuva,
                         t_15_5p_liukuva, t_15_10p_liukuva, t_15_20p_liukuva,
                         t_20_5p_liukuva, t_20_10p_liukuva, t_20_20p_liukuva,
                         t0_50p_liukuva, t0_200p_liukuva,
                         SPX_0, SPX_2, SPX_5, SPX_10, SPX_15, SPX_20,
                         SPX2, SPX5, SPX10, SPX15, SPX20,
                         NDX_0, NDX_2, NDX_5, NDX_10, NDX_15, NDX_20,
                         NDX2, NDX5, NDX10, NDX15, NDX20,
                         RSI14_t0, t0_close_norm, bearish_divergence, bullish_divergence, weekday)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                                ?, ?, ?, ?)
                        """,
                        values_tuple,
                    )
                    inserted += 1

                conn.commit()
                self.logger.debug(f"Committed batch {i // batch_size + 1}")

            return inserted

        except Exception as e:
            self.logger.error(f"Bulk insert results failed: {e}")
            if "85 values for 84 columns" in str(e):
                self.logger.error(
                    f"DEBUG: Last result dict had {len(result.keys())} keys"
                )
                self.logger.error(f"DEBUG: values_tuple length was {len(values_tuple)}")
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
    ) -> int:
        """
        Poista tulokset results_data taulusta pattern/ticker -filttereillä.

        Args:
            pattern_filter: Lista pattern-numeroista (0-8) joita poistetaan
            ticker_filter: Lista tickereistä joita poistetaan

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

            if not conditions:
                # Ei filttereitä, ei poisteta mitään
                return 0

            where_clause = " AND ".join(conditions)
            query = f"DELETE FROM results_data WHERE {where_clause}"

            cursor.execute(query, params)
            conn.commit()

            deleted = cursor.rowcount
            self.logger.info(
                f"Deleted {deleted} results by filters (patterns={pattern_filter}, tickers={ticker_filter})"
            )
            return deleted

        except Exception as e:
            self.logger.error(f"Delete results by filters failed: {e}")
            return 0

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
