"""
Test Data Generator
Apuluokka testitietojen generointiin.
"""

import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Tuple, Dict
import random


class TestDataGenerator:
    """Generoi testidata analysis-moduulin testaamiseen."""

    @staticmethod
    def create_sample_osakedata(db_path: str, num_days: int = 100) -> None:
        """
        Luo sample osakedata-tietokannan.

        Args:
            db_path: Tietokantapolku
            num_days: Päivien määrä
        """
        if os.path.exists(db_path):
            os.remove(db_path)

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Luo taulut
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY,
                symbol TEXT UNIQUE,
                name TEXT,
                sector TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS price_data (
                id INTEGER PRIMARY KEY,
                stock_id INTEGER,
                date TEXT,
                open_price REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,
                volume INTEGER,
                FOREIGN KEY (stock_id) REFERENCES stocks (id)
            )
        """
        )

        # Lisää sample osakkeet
        stocks = [
            ("AAPL", "Apple Inc.", "Technology"),
            ("MSFT", "Microsoft Corp.", "Technology"),
            ("GOOGL", "Alphabet Inc.", "Technology"),
            ("TSLA", "Tesla Inc.", "Automotive"),
            ("NVDA", "NVIDIA Corp.", "Technology"),
        ]

        for symbol, name, sector in stocks:
            cursor.execute(
                "INSERT INTO stocks (symbol, name, sector) VALUES (?, ?, ?)",
                (symbol, name, sector),
            )

        # Generoi hintadataa
        base_date = datetime.now() - timedelta(days=num_days)

        for stock_id in range(1, len(stocks) + 1):
            base_price = random.uniform(50, 300)

            for day in range(num_days):
                date = base_date + timedelta(days=day)

                # Simuloi hintaliikettä
                change = random.uniform(-0.05, 0.05)  # ±5% päivässä
                base_price *= 1 + change

                # OHLC hinnat
                open_price = base_price * random.uniform(0.98, 1.02)
                close_price = base_price * random.uniform(0.98, 1.02)
                high_price = max(open_price, close_price) * random.uniform(1.0, 1.03)
                low_price = min(open_price, close_price) * random.uniform(0.97, 1.0)

                volume = random.randint(100000, 5000000)

                cursor.execute(
                    """
                    INSERT INTO price_data 
                    (stock_id, date, open_price, high_price, low_price, close_price, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        stock_id,
                        date.strftime("%Y-%m-%d"),
                        round(open_price, 2),
                        round(high_price, 2),
                        round(low_price, 2),
                        round(close_price, 2),
                        volume,
                    ),
                )

        conn.commit()
        conn.close()

    @staticmethod
    def create_sample_analysis_findings(db_path: str) -> List[Dict]:
        """
        Luo sample analysis-löydökset.

        Args:
            db_path: Analysis tietokantapolku

        Returns:
            Lista löydöksistä
        """
        findings = [
            {
                "symbol": "AAPL",
                "date": "2024-01-15",
                "pattern": "Doji",
                "signal_strength": 0.85,
                "price": 185.50,
                "volume": 2500000,
                "description": "Strong doji pattern indicating potential reversal",
                "analysis_date": datetime.now().isoformat(),
            },
            {
                "symbol": "MSFT",
                "date": "2024-01-16",
                "pattern": "Hammer",
                "signal_strength": 0.72,
                "price": 415.25,
                "volume": 1800000,
                "description": "Hammer pattern suggesting bullish reversal",
                "analysis_date": datetime.now().isoformat(),
            },
            {
                "symbol": "GOOGL",
                "date": "2024-01-17",
                "pattern": "Shooting Star",
                "signal_strength": 0.68,
                "price": 155.80,
                "volume": 3200000,
                "description": "Shooting star indicating potential bearish reversal",
                "analysis_date": datetime.now().isoformat(),
            },
            {
                "symbol": "TSLA",
                "date": "2024-01-18",
                "pattern": "Engulfing",
                "signal_strength": 0.91,
                "price": 220.15,
                "volume": 4500000,
                "description": "Strong bullish engulfing pattern",
                "analysis_date": datetime.now().isoformat(),
            },
        ]

        # Tallenna analysis-tietokantaan jos se on olemassa
        if os.path.exists(db_path):
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            for finding in findings:
                cursor.execute(
                    """
                    INSERT INTO analysis_findings 
                    (symbol, date, pattern, signal_strength, price, volume, description, analysis_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                    (
                        finding["symbol"],
                        finding["date"],
                        finding["pattern"],
                        finding["signal_strength"],
                        finding["price"],
                        finding["volume"],
                        finding["description"],
                        finding["analysis_date"],
                    ),
                )

            conn.commit()
            conn.close()

        return findings

    @staticmethod
    def create_pattern_test_data() -> List[Tuple]:
        """
        Luo OHLC dataa kynttiläkuvioiden testaamiseen.

        Returns:
            Lista (open, high, low, close) tupleja
        """
        patterns = []

        # Doji pattern (open ≈ close)
        patterns.extend(
            [
                (100.0, 105.0, 98.0, 100.1),  # Doji
                (200.0, 202.0, 198.0, 199.9),  # Doji
            ]
        )

        # Hammer pattern (long lower shadow, small body)
        patterns.extend(
            [
                (100.0, 101.0, 95.0, 100.5),  # Hammer
                (150.0, 151.0, 145.0, 150.8),  # Hammer
            ]
        )

        # Shooting Star pattern (long upper shadow, small body)
        patterns.extend(
            [
                (100.0, 108.0, 99.0, 100.5),  # Shooting Star
                (200.0, 210.0, 199.0, 201.0),  # Shooting Star
            ]
        )

        # Engulfing patterns (kaksi kynttilää)
        patterns.extend(
            [
                # Bullish engulfing
                [
                    (100.0, 102.0, 99.0, 101.0),  # Ensimmäinen (bearish)
                    (100.5, 105.0, 98.0, 104.0),
                ],  # Toinen (bullish, engulfing)
                # Bearish engulfing
                [
                    (100.0, 103.0, 99.0, 102.0),  # Ensimmäinen (bullish)
                    (101.5, 102.0, 95.0, 96.0),
                ],  # Toinen (bearish, engulfing)
            ]
        )

        # Normaalit kynttilät (ei kuviota)
        patterns.extend(
            [
                (100.0, 103.0, 99.0, 102.0),  # Normaali bullish
                (100.0, 101.0, 97.0, 98.0),  # Normaali bearish
                (100.0, 105.0, 100.0, 103.0),  # Normaali bullish
            ]
        )

        return patterns

    @staticmethod
    def create_performance_test_data(size: int = 1000) -> List[Dict]:
        """
        Luo suorituskykytesteille isoa datamäärää.

        Args:
            size: Datarivien määrä

        Returns:
            Lista hintadataa
        """
        data = []
        base_price = 100.0

        for i in range(size):
            # Simuloi hintaliikettä
            change = random.uniform(-0.02, 0.02)
            base_price *= 1 + change

            open_price = base_price * random.uniform(0.99, 1.01)
            close_price = base_price * random.uniform(0.99, 1.01)
            high_price = max(open_price, close_price) * random.uniform(1.0, 1.02)
            low_price = min(open_price, close_price) * random.uniform(0.98, 1.0)

            data.append(
                {
                    "symbol": f"TEST{i % 10}",  # 10 erilaista symbolia
                    "date": (datetime.now() - timedelta(days=size - i)).strftime(
                        "%Y-%m-%d"
                    ),
                    "open": round(open_price, 2),
                    "high": round(high_price, 2),
                    "low": round(low_price, 2),
                    "close": round(close_price, 2),
                    "volume": random.randint(50000, 2000000),
                }
            )

        return data

    @staticmethod
    def create_stress_test_scenario() -> Dict:
        """
        Luo stressitestiskenaario.

        Returns:
            Skenaariodata
        """
        return {
            "concurrent_users": 10,
            "operations_per_user": 100,
            "large_dataset_size": 50000,
            "memory_limit_mb": 500,
            "max_response_time_ms": 5000,
            "patterns_to_detect": ["Doji", "Hammer", "Shooting Star", "Engulfing"],
            "symbols": [f"STRESS{i:03d}" for i in range(100)],
        }


if __name__ == "__main__":
    """Luo testidataa kun ajetaan suoraan."""
    generator = TestDataGenerator()

    # Luo osakedata
    print("Luodaan sample osakedata...")
    generator.create_sample_osakedata("test_osakedata.db", 200)
    print("✅ Osakedata luotu")

    # Luo testitiedot
    print("Luodaan pattern test data...")
    patterns = generator.create_pattern_test_data()
    print(f"✅ {len(patterns)} pattern testiä luotu")

    # Luo performance data
    print("Luodaan performance test data...")
    perf_data = generator.create_performance_test_data(5000)
    print(f"✅ {len(perf_data)} performance testiä luotu")

    print("\n🎯 Testidatat valmiit käytettäväksi!")
