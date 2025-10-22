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

    def __init__(self, db_path: str = "analysis/analysis.db"):
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
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

            conn = self.get_connection()
            cursor = conn.cursor()

            # Luo analysis_findings taulu
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS analysis_findings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    pattern TEXT NOT NULL,
                    signal_strength REAL NOT NULL,
                    price REAL NOT NULL,
                    volume INTEGER,
                    description TEXT,
                    analysis_date TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, date, pattern, signal_strength, price, volume)
                )
            """
            )

            conn.commit()  # Varmista että taulu on luotu ennen indeksejä

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
        pattern: str,
        signal_strength: float,
        price: float,
        volume: int = None,
        description: str = None,
    ) -> bool:
        """
        Lisää uusi löydös tietokantaan.

        Args:
            ticker: Osakkeen symboli
            date: Päivämäärä
            pattern: Kynttiläkuvio
            signal_strength: Signaalin vahvuus
            price: Hinta
            volume: Volyymi
            description: Kuvaus

        Returns:
            True jos lisäys onnistui
        """
        try:
            conn = self.get_connection()
            cursor = conn.cursor()

            analysis_date = datetime.now().isoformat()

            cursor.execute(
                """
                INSERT OR IGNORE INTO analysis_findings 
                (ticker, pattern, signal_strength, price, volume, description, analysis_date, date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    ticker,
                    pattern,
                    signal_strength,
                    price,
                    volume,
                    description,
                    analysis_date,
                    date,  # Use analysis_date as date for compatibility
                ),
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
        pattern: str,
        signal_strength: float,
        price: float,
        volume: int = None,
        description: str = None,
        analysis_date: str = None,
    ):
        """
        Tallenna analyysin löydös tietokantaan.

        Args:
            ticker: Osakkeen symboli
            date: Päivämäärä (YYYY-MM-DD)
            pattern: Kynttiläkuvio
            signal_strength: Signaalin vahvuus (0-1)
            price: Hinta
            volume: Volyymi
            description: Kuvaus
            analysis_date: Analyysin päivämäärä
        """
        return self.insert_finding(
            ticker=ticker,
            date=date,
            pattern=pattern,
            signal_strength=signal_strength,
            price=price,
            volume=volume,
            description=description,
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
