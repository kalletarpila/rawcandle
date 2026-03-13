"""
Tests for downtrend filtering in analysis phase.

Tämä testi varmistaa, että:
a) Hammer-tapahtuma tallennetaan kantaan kun on laskutrendi
b) Hammer-tapahtuma EI tallennu kantaan kun ei ole laskutrendia

Downtrend-kriteerit (kaikki kolme pakollisia):
1. Porrastava lasku: t-10 > t-5 > t-2 > t0
2. Minimalasku 3%: ((t-10 - t0) / t-10) * 100 >= 3.0
3. Liukuva keskiarvo: t0 < MA10 ja MA5 < MA10
"""

import pytest
import sqlite3
import tempfile
import os
from datetime import datetime, timedelta
from typing import Dict, List

from analysis.analyzer import AnalysisEngine
from analysis.database_manager import DatabaseManager


class TestDowntrendFiltering:
    """Testaa downtrend-filtteröinnin toimivuutta analysis-vaiheessa."""

    @pytest.fixture
    def temp_db(self):
        """Luo väliaikainen tietokanta."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        if os.path.exists(path):
            os.remove(path)

    @pytest.fixture
    def analysis_db(self, temp_db):
        """Luo analysis-tietokanta."""
        return temp_db

    @pytest.fixture
    def stock_db(self):
        """Luo osakedata-tietokanta testidatalla."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        conn = sqlite3.connect(path)
        cursor = conn.cursor()

        # Luo taulut (yksinkertaistettu rakenne)
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS stocks (
                id INTEGER PRIMARY KEY,
                symbol TEXT UNIQUE NOT NULL
            )
        """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS price_data (
                id INTEGER PRIMARY KEY,
                stock_id INTEGER,
                date TEXT NOT NULL,
                open_price REAL,
                high_price REAL,
                low_price REAL,
                close_price REAL,
                volume INTEGER,
                FOREIGN KEY (stock_id) REFERENCES stocks(id)
            )
        """
        )

        # Lisää testiosake
        cursor.execute("INSERT INTO stocks (id, symbol) VALUES (1, 'TEST')")

        conn.commit()
        conn.close()

        yield path

        if os.path.exists(path):
            os.remove(path)

    def _create_downtrend_data(
        self, stock_db: str, base_date: datetime, start_price: float = 100.0
    ):
        """Luo testidataa joka täyttää downtrend-kriteerit.

        Luo 11 päivän hintatiedot:
        - Porrastava lasku: t-10 (100) > t-5 (96) > t-2 (93) > t0 (90)
        - Minimalasku 10%: (100 - 90) / 100 = 10%
        - MA-kriteerit täyttyvät
        - Viimeinen kynttilä on Hammer (pitkä alakaarjo)
        """
        conn = sqlite3.connect(stock_db)
        cursor = conn.cursor()

        # Luo laskeva hintasarja
        prices = []
        for i in range(11):  # t-10 ... t0
            # Tasainen lasku 100 -> 90
            close = start_price - (i * 1.0)
            open_price = close + 0.5
            high = close + 1.0
            low = close - 0.5

            date = (base_date - timedelta(days=10 - i)).strftime("%Y-%m-%d")

            # Viimeinen kynttilä on Hammer
            if i == 10:  # t0
                # Hammer: pitkä alakaarjo, lyhyt ylävarjo, pieni runko
                low = close - 2.0  # Pitkä alakaarjo
                high = close + 0.3  # Lyhyt ylävarjo
                open_price = close + 0.2  # Pieni runko

            prices.append((1, date, open_price, high, low, close, 100000))

        cursor.executemany(
            """
            INSERT INTO price_data 
            (stock_id, date, open_price, high_price, low_price, close_price, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            prices,
        )

        conn.commit()
        conn.close()

    def _create_uptrend_data(
        self, stock_db: str, base_date: datetime, start_price: float = 90.0
    ):
        """Luo testidataa joka EI täytä downtrend-kriteereitä (nousutrendi).

        Luo 11 päivän hintatiedot:
        - Nouseva trendi: t-10 (90) < t-5 (94) < t-2 (97) < t0 (100)
        - EI täytä downtrend-kriteereitä
        - Viimeinen kynttilä on Hammer (pitkä alakaarjo)
        """
        conn = sqlite3.connect(stock_db)
        cursor = conn.cursor()

        # Luo nouseva hintasarja
        prices = []
        for i in range(11):  # t-10 ... t0
            # Tasainen nousu 90 -> 100
            close = start_price + (i * 1.0)
            open_price = close - 0.5
            high = close + 0.5
            low = close - 1.0

            date = (base_date - timedelta(days=10 - i)).strftime("%Y-%m-%d")

            # Viimeinen kynttilä on Hammer
            if i == 10:  # t0
                # Hammer: pitkä alakaarjo, lyhyt ylävarjo, pieni runko
                low = close - 2.0  # Pitkä alakaarjo
                high = close + 0.3  # Lyhyt ylävarjo
                open_price = close + 0.2  # Pieni runko

            prices.append((1, date, open_price, high, low, close, 100000))

        cursor.executemany(
            """
            INSERT INTO price_data 
            (stock_id, date, open_price, high_price, low_price, close_price, volume)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            prices,
        )

        conn.commit()
        conn.close()

    def test_hammer_saved_with_downtrend(self, analysis_db, stock_db):
        """Testi a): Hammer-tapahtuma tallennetaan kantaan kun on laskutrendi."""
        # Luo laskutrendidata
        base_date = datetime.now()
        self._create_downtrend_data(stock_db, base_date)

        # Alusta analyzer ja database manager
        analyzer = AnalysisEngine(analysis_db, stock_db)
        db_manager = DatabaseManager(analysis_db)

        # Aja analyysi downtrend-filtterillä päällä
        # Kriteerit 1, 2, 3 valittu:
        # 1. Porrastava lasku (pakollinen)
        # 2. Minimalasku 3% (pakollinen)
        # 3. MA-suodatin (use_ma_filter=True)
        findings = analyzer.analyze_batch(
            ["TEST"],
            downtrend_filter=True,
            min_decline_percent=3.0,
            use_ma_filter=True,
            use_volume_filter=False,
        )

        # Tarkista että Hammer löytyi
        hammer_findings = [f for f in findings if "hammer" in f["pattern"].lower()]
        assert len(hammer_findings) > 0, "Hammer-kuviota ei löytynyt laskutrendissä"

        # Tallenna löydökset kantaan
        saved_count = 0
        for finding in hammer_findings:
            success = db_manager.insert_finding(
                ticker=finding["symbol"],
                date=finding["date"],
                pattern=finding["pattern"],
                signal_strength=finding["signal_strength"],
            )
            if success:
                saved_count += 1

        # Tarkista että tallentaminen onnistui
        assert saved_count > 0, "Hammer-tapahtumaa ei tallennettu kantaan"

        # Varmista että löydös on kannassa
        all_findings = db_manager.get_all_findings()
        hammer_in_db = [f for f in all_findings if "hammer" in f["pattern"].lower()]
        assert (
            len(hammer_in_db) > 0
        ), "Hammer-tapahtumaa ei löydy kannasta laskutrendin jälkeen"

        print(
            f"✅ Testi a) PASS: Hammer tallennettu kantaan laskutrendissä ({saved_count} löydöstä)"
        )

    def test_hammer_not_saved_without_downtrend(self, analysis_db, stock_db):
        """Testi b): Hammer-tapahtuma EI tallennu kantaan kun ei ole laskutrendia."""
        # Luo nousutrendidata (ei täytä downtrend-kriteereitä)
        base_date = datetime.now()
        self._create_uptrend_data(stock_db, base_date)

        # Alusta analyzer ja database manager
        analyzer = AnalysisEngine(analysis_db, stock_db)
        db_manager = DatabaseManager(analysis_db)

        # Aja analyysi downtrend-filtterillä päällä
        # Kriteerit 1, 2, 3 valittu:
        # 1. Porrastava lasku (pakollinen)
        # 2. Minimalasku 3% (pakollinen)
        # 3. MA-suodatin (use_ma_filter=True)
        findings = analyzer.analyze_batch(
            ["TEST"],
            downtrend_filter=True,
            min_decline_percent=3.0,
            use_ma_filter=True,
            use_volume_filter=False,
        )

        # Tarkista että Hammer EI löytynyt (koska ei laskutrendiä)
        hammer_findings = [f for f in findings if "hammer" in f["pattern"].lower()]
        assert (
            len(hammer_findings) == 0
        ), "Hammer-kuvio löytyi vaikka ei ollut laskutrendiä"

        # Yritä tallentaa (ei pitäisi olla mitään tallennettavaa)
        saved_count = 0
        for finding in hammer_findings:
            success = db_manager.insert_finding(
                ticker=finding["symbol"],
                date=finding["date"],
                pattern=finding["pattern"],
                signal_strength=finding["signal_strength"],
            )
            if success:
                saved_count += 1

        # Tarkista että mitään ei tallennettu
        assert (
            saved_count == 0
        ), "Hammer-tapahtuma tallennettiin vaikka ei ollut laskutrendiä"

        # Varmista että kannassa ei ole Hammer-löydöksiä
        all_findings = db_manager.get_all_findings()
        hammer_in_db = [f for f in all_findings if "hammer" in f["pattern"].lower()]
        assert (
            len(hammer_in_db) == 0
        ), "Hammer-tapahtuma löytyy kannasta vaikka ei ollut laskutrendiä"

        print(
            "✅ Testi b) PASS: Hammer EI tallennettu kantaan ilman laskutrendiä (0 löydöstä)"
        )

    def test_combined_scenario(self, analysis_db, stock_db):
        """Yhdistetty testi: sekä laskutrendi että nousutrendi samassa testissä."""
        base_date = datetime.now()

        # 1. Luo laskutrendidata
        self._create_downtrend_data(stock_db, base_date)

        # Aja analyysi downtrend-filtterillä
        analyzer = AnalysisEngine(analysis_db, stock_db)
        db_manager = DatabaseManager(analysis_db)

        findings_with_downtrend = analyzer.analyze_batch(
            ["TEST"],
            downtrend_filter=True,
            min_decline_percent=3.0,
            use_ma_filter=True,
            use_volume_filter=False,
        )

        # Tallenna laskutrendin löydökset
        downtrend_count = 0
        for finding in findings_with_downtrend:
            success = db_manager.insert_finding(
                ticker=finding["symbol"],
                date=finding["date"],
                pattern=finding["pattern"],
                signal_strength=finding["signal_strength"],
            )
            if success:
                downtrend_count += 1

        # 2. Tyhjennä price_data ja lisää nousutrendidata
        conn = sqlite3.connect(stock_db)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM price_data")
        conn.commit()
        conn.close()

        self._create_uptrend_data(stock_db, base_date + timedelta(days=20))

        # Aja analyysi uudelleen
        findings_without_downtrend = analyzer.analyze_batch(
            ["TEST"],
            downtrend_filter=True,
            min_decline_percent=3.0,
            use_ma_filter=True,
            use_volume_filter=False,
        )

        # Yritä tallentaa nousutrendin löydökset (ei pitäisi olla mitään)
        uptrend_count = 0
        for finding in findings_without_downtrend:
            success = db_manager.insert_finding(
                ticker=finding["symbol"],
                date=finding["date"],
                pattern=finding["pattern"],
                signal_strength=finding["signal_strength"],
            )
            if success:
                uptrend_count += 1

        # Tarkistukset
        assert downtrend_count > 0, "Laskutrendissä pitäisi olla löydöksiä"
        assert uptrend_count == 0, "Nousutrendissä ei pitäisi olla löydöksiä"

        print(
            f"✅ Yhdistetty testi PASS: Laskutrendi={downtrend_count} löydöstä, Nousutrendi={uptrend_count} löydöstä"
        )
