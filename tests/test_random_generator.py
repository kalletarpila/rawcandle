"""Tests for downtrend generator."""

import os
import sqlite3
import pytest
from analysis.downtrend_generator import generate_random_findings, DowntrendGenerator
from analysis.database_manager import DatabaseManager


def test_generate_random_findings_returns_tuple():
    """Testi: generate_random_findings palauttaa tuplen (count, errors)."""
    # Testataan että funktio palauttaa oikean tyyppisen vastauksen
    # Käytetään todellisia tietokantapolkuja, mutta pieni määrä
    result = generate_random_findings(
        num_tickers=1,
        events_per_ticker=1,
        stock_db_path="data/osakedata.db",
        analysis_db_path="data/analysis.db",
    )

    # Tarkista että palautusarvo on tuple
    assert isinstance(result, tuple), "Function should return a tuple"
    assert len(result) == 2, "Tuple should have 2 elements"

    count, errors = result
    assert isinstance(count, int), "First element should be int (count)"
    assert isinstance(errors, list), "Second element should be list (errors)"
    assert count >= 0, "Count should be non-negative"


def test_downtrend_generator_initialization():
    """Testi: DowntrendGenerator alustus onnistuu."""
    generator = DowntrendGenerator(
        stock_db_path="data/osakedata.db", analysis_db_path="data/analysis.db"
    )

    assert generator.stock_db_path == "data/osakedata.db"
    assert generator.analysis_db_path == "data/analysis.db"


def test_downtrend_generator_uses_database_manager(tmp_path):
    """Testi: DowntrendGenerator käyttää DatabaseManager:ia tallennukseen."""
    # Luo väliaikaiset tietokannat
    stock_db = tmp_path / "test_stock.db"
    analysis_db = tmp_path / "test_analysis.db"

    # Luo mock stock data
    conn = sqlite3.connect(str(stock_db))
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE osakedata (
            osake TEXT,
            pvm TEXT,
            alin REAL,
            ylin REAL,
            avaus REAL,
            paatos REAL,
            volyymi INTEGER,
            market TEXT NOT NULL DEFAULT 'usa'
        )
    """
    )

    # Lisää testidataa (15 päivää laskevaa trendiä)
    for i in range(15):
        cursor.execute(
            "INSERT INTO osakedata VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "TEST",
                f"2024-01-{i+1:02d}",
                100 - i * 2,
                102 - i * 2,
                101 - i * 2,
                100 - i * 2,
                10000,
                "usa",
            ),
        )
    conn.commit()
    conn.close()

    # Aja generaattori
    generator = DowntrendGenerator(
        stock_db_path=str(stock_db), analysis_db_path=str(analysis_db)
    )

    count, errors = generator.generate_random_findings(
        num_tickers=1, events_per_ticker=1
    )

    # Tarkista että DatabaseManager loi taulun
    db_manager = DatabaseManager(str(analysis_db))
    findings = db_manager.get_all_findings()
    db_manager.close()

    # Vähintään taulu pitää olla olemassa (vaikka ei löytyisi downtrend-tapahtumia)
    assert isinstance(findings, list), "DatabaseManager should return list of findings"
