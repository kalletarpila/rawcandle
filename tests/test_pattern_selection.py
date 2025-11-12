"""Test that only selected patterns are analyzed and saved to database."""

import os
import sqlite3
import tempfile
import pandas as pd
from analysis.run_analysis import run_candlestick_analysis
from analysis.database_manager import DatabaseManager


def test_only_selected_patterns_are_saved():
    """Testi: Vain valitut kuviot analysoidaan ja tallennetaan kantaan."""

    # Luo väliaikainen tietokanta osakkeille
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_stock:
        stock_db_path = tmp_stock.name

    # Luo väliaikainen analysis-kanta
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_analysis:
        analysis_db_path = tmp_analysis.name

    try:
        # Luo testidataa jossa on selkeä hammer-kuvio
        conn = sqlite3.connect(stock_db_path)
        cursor = conn.cursor()
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

        # Lisää dataa: Hammer-kuvio 2024-01-05
        # Hammer: pieni runko, pitkä alavarjo, lyhyt ylävarjo
        # Kriteerit: body < 0.4*range, lower_shadow > 2*body, upper_shadow < body
        test_data = [
            ("TEST", "2024-01-01", 100.0, 105.0, 95.0, 102.0, 10000),
            ("TEST", "2024-01-02", 102.0, 107.0, 97.0, 104.0, 10000),
            ("TEST", "2024-01-03", 104.0, 109.0, 99.0, 106.0, 10000),
            ("TEST", "2024-01-04", 106.0, 111.0, 101.0, 108.0, 10000),
            # Hammer: low=90, close=100.5, open=99.5, high=100.8
            # Runko = 1, alavarjo = 9.5, ylävarjo = 0.3, range = 10.8
            # body < 10.8*0.4=4.32 ✓, lower_shadow > 2*1=2 ✓, upper_shadow < 1 ✓
            ("TEST", "2024-01-05", 99.5, 100.8, 90.0, 100.5, 10000),
            ("TEST", "2024-01-06", 100.0, 105.0, 95.0, 102.0, 10000),
        ]

        cursor.executemany(
            "INSERT INTO osakedata (osake, pvm, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            test_data,
        )
        conn.commit()
        conn.close()

        # 1. Aja analyysi VAIN Hammer-kuviolle
        results_hammer = run_candlestick_analysis(
            db_path=stock_db_path,
            ticker="TEST",
            patterns=["Hammer"],  # Vain Hammer valittu
            start_date="2024-01-01",
            end_date="2024-01-06",
        )

        # Tarkista että löytyi Hammer
        assert len(results_hammer) > 0, "Should find at least one Hammer pattern"

        # Tallenna tulokset kantaan
        db_manager = DatabaseManager(analysis_db_path)
        for key, findings in results_hammer.items():
            ticker, date = key.split("|")
            for finding in findings:
                db_manager.save_finding(
                    ticker=ticker,
                    date=date,
                    pattern=finding["pattern"],
                    signal_strength=finding["strength"],
                )

        # Tarkista että VAIN Hammer on kannassa
        all_findings = db_manager.get_all_findings()
        patterns_in_db = {f["pattern"] for f in all_findings}

        assert "Hammer" in patterns_in_db, "Hammer should be in database"
        assert (
            len(patterns_in_db) == 1
        ), f"Should only have Hammer, but got: {patterns_in_db}"

        db_manager.close()

        # 2. Tyhjennä kanta ja aja analyysi useammalla kuviolla
        os.remove(analysis_db_path)
        db_manager = DatabaseManager(analysis_db_path)

        results_multi = run_candlestick_analysis(
            db_path=stock_db_path,
            ticker="TEST",
            patterns=["Hammer", "Dragonfly Doji"],  # Kaksi kuviota
            start_date="2024-01-01",
            end_date="2024-01-06",
        )

        # Tallenna tulokset
        for key, findings in results_multi.items():
            ticker, date = key.split("|")
            for finding in findings:
                db_manager.save_finding(
                    ticker=ticker,
                    date=date,
                    pattern=finding["pattern"],
                    signal_strength=finding["strength"],
                )

        # Tarkista että VAIN valitut kuviot ovat kannassa
        all_findings = db_manager.get_all_findings()
        patterns_in_db = {f["pattern"] for f in all_findings}

        # Pitäisi olla vain Hammer ja/tai Dragonfly Doji, ei muita
        allowed_patterns = {"Hammer", "Dragonfly Doji"}
        assert patterns_in_db.issubset(
            allowed_patterns
        ), f"Found unexpected patterns: {patterns_in_db - allowed_patterns}"

        # Varmista että Hammer löytyi
        assert "Hammer" in patterns_in_db, "Hammer should still be found"

        db_manager.close()

    finally:
        # Siivoa
        if os.path.exists(stock_db_path):
            os.remove(stock_db_path)
        if os.path.exists(analysis_db_path):
            os.remove(analysis_db_path)


def test_no_patterns_selected_returns_empty():
    """Testi: Jos ei valittuja kuvioita, palauta tyhjä tulos."""

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_stock:
        stock_db_path = tmp_stock.name

    try:
        # Luo testidataa
        conn = sqlite3.connect(stock_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT, pvm TEXT, open REAL, high REAL, 
                low REAL, close REAL, volume INTEGER,
                market TEXT NOT NULL DEFAULT 'usa'
            )
        """
        )
        cursor.execute(
            "INSERT INTO osakedata (osake, pvm, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("TEST", "2024-01-01", 100.0, 105.0, 95.0, 102.0, 10000),
        )
        conn.commit()
        conn.close()

        # Aja analyysi ILMAN valittuja kuvioita
        results = run_candlestick_analysis(
            db_path=stock_db_path,
            ticker="TEST",
            patterns=[],  # Tyhjä lista
            start_date="2024-01-01",
            end_date="2024-01-01",
        )

        # Pitäisi palauttaa tyhjä tulos
        assert results == {}, "Should return empty dict when no patterns selected"

    finally:
        if os.path.exists(stock_db_path):
            os.remove(stock_db_path)


def test_divergence_patterns_require_rsi_calculation():
    """Testi: Divergenssit lasketaan vain kun ne on valittu (RSI lasketaan)."""

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_stock:
        stock_db_path = tmp_stock.name

    try:
        # Luo testidataa (riittävästi RSI-laskentaan)
        conn = sqlite3.connect(stock_db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE osakedata (
                osake TEXT, pvm TEXT, open REAL, high REAL, 
                low REAL, close REAL, volume INTEGER,
                market TEXT NOT NULL DEFAULT 'usa'
            )
        """
        )

        # Lisää 60 päivää dataa
        for i in range(60):
            cursor.execute(
                "INSERT INTO osakedata (osake, pvm, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("TEST", f"2024-01-{i+1:02d}", 100.0, 105.0, 95.0, 100.0, 10000),
            )

        conn.commit()
        conn.close()

        # 1. Aja ILMAN divergenssejä - RSI:tä ei pitäisi laskea
        results_no_div = run_candlestick_analysis(
            db_path=stock_db_path,
            ticker="TEST",
            patterns=["Hammer"],  # Ei divergenssejä
            start_date="2024-01-01",
            end_date="2024-01-30",
        )

        # Tarkista että ei divergenssejä tuloksissa
        all_patterns = []
        for findings in results_no_div.values():
            all_patterns.extend([f["pattern"] for f in findings])

        assert "Bullish Divergence" not in all_patterns
        assert "Bearish Divergence" not in all_patterns

        # 2. Aja divergenssien kanssa - RSI pitäisi laskea
        results_with_div = run_candlestick_analysis(
            db_path=stock_db_path,
            ticker="TEST",
            patterns=["Bullish Divergence", "Bearish Divergence"],
            start_date="2024-01-01",
            end_date="2024-01-30",
        )

        # RSI lasketaan, divergenssit etsitään (vaikka ei löytyisikään testidatasta)
        # Tärkeintä että koodi ei kaadu ja toimii oikein
        assert isinstance(
            results_with_div, dict
        ), "Should return dict even if no divergences found"

    finally:
        if os.path.exists(stock_db_path):
            os.remove(stock_db_path)
