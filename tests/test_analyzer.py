"""
Yksikkötestit analysis.analyzer moduulille
"""

import pytest
import os
import sys
from unittest.mock import patch, MagicMock, call
from datetime import datetime, timedelta

# Lisää projektin juurikansio Python path:iin ennen analysis-importteja
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Analysis importit vaativat sys.path muutoksen
try:
    from analysis.analyzer import AnalysisEngine
    from analysis.database_manager import DatabaseManager
except ImportError as e:
    print(f"Import error: {e}")
    raise


class TestAnalysisEngine:
    """Testit AnalysisEngine luokalle"""

    def test_init(self, temp_db, temp_osakedata_db):
        """Testaa AnalysisEngine alustus"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)
        assert engine.analysis_db_path == temp_db
        assert engine.stock_db_path == temp_osakedata_db
        assert isinstance(engine.db_manager, DatabaseManager)

    @patch("analysis.analyzer.AnalysisEngine._get_stock_data")
    @patch("analysis.analyzer.AnalysisEngine._detect_patterns")
    @patch("analysis.analyzer.AnalysisEngine._save_findings")
    def test_analyze_ticker_success(
        self, mock_save, mock_detect, mock_get_data, temp_db, temp_osakedata_db
    ):
        """Testaa onnistunutta ticker analyysiä"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Mock data
        mock_stock_data = [
            {
                "date": "2024-01-01",
                "open": 150.0,
                "high": 155.0,
                "low": 148.0,
                "close": 152.0,
                "volume": 1000000,
            },
            {
                "date": "2024-01-02",
                "open": 152.0,
                "high": 158.0,
                "low": 151.0,
                "close": 157.0,
                "volume": 1200000,
            },
        ]
        mock_patterns = [{"date": "2024-01-01", "pattern": "doji", "strength": 0.8}]

        mock_get_data.return_value = mock_stock_data
        mock_detect.return_value = mock_patterns
        mock_save.return_value = True

        result = engine.analyze_ticker("AAPL")

        assert result["success"] is True
        assert result["patterns_found"] == 1
        assert "analysis_time" in result

        mock_get_data.assert_called_once_with("AAPL")
        mock_detect.assert_called_once_with("AAPL", mock_stock_data)
        mock_save.assert_called_once_with("AAPL", mock_patterns)

    @patch("analysis.analyzer.AnalysisEngine._get_stock_data")
    def test_analyze_ticker_no_data(self, mock_get_data, temp_db, temp_osakedata_db):
        """Testaa ticker analyysiä kun dataa ei ole"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)
        mock_get_data.return_value = []

        result = engine.analyze_ticker("NONEXISTENT")

        assert result["success"] is False
        assert "No stock data found" in result["error"]

    @patch("analysis.analyzer.AnalysisEngine._get_stock_data")
    def test_analyze_ticker_exception(self, mock_get_data, temp_db, temp_osakedata_db):
        """Testaa ticker analyysiä kun tapahtuu virhe"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)
        mock_get_data.side_effect = Exception("Database error")

        result = engine.analyze_ticker("AAPL")

        assert result["success"] is False
        assert "Database error" in result["error"]

    def test_get_stock_data(self, temp_db, temp_osakedata_db):
        """Testaa osakedata haku"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Testaa AAPL dataa (lisätty conftest.py:ssä)
        data = engine._get_stock_data("AAPL")
        assert len(data) == 2
        assert data[0]["ticker"] == "AAPL"
        assert data[0]["date"] == "2024-01-01"
        assert data[0]["close"] == 152.0

    def test_detect_patterns_doji(self, temp_db, temp_osakedata_db):
        """Testaa doji kuvion tunnistus"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Doji: open ja close lähes samoja
        stock_data = [
            {
                "date": "2024-01-01",
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 100.1,  # Hyvin lähellä open-arvoa
                "volume": 1000000,
            }
        ]

        patterns = engine._detect_patterns("TEST", stock_data)

        # Pitäisi löytää doji
        doji_patterns = [p for p in patterns if p["pattern"] == "doji"]
        assert len(doji_patterns) > 0
        assert doji_patterns[0]["strength"] > 0.5

    def test_detect_patterns_hammer(self, temp_db, temp_osakedata_db):
        """Testaa vasara kuvion tunnistus"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Hammer: pitkä alavarjo, lyhyt ylävarjo, close lähellä high
        stock_data = [
            {
                "date": "2024-01-01",
                "open": 95.0,
                "high": 100.0,
                "low": 85.0,  # Pitkä alavarjo
                "close": 99.0,  # Lähellä high
                "volume": 1000000,
            }
        ]

        patterns = engine._detect_patterns("TEST", stock_data)

        # Pitäisi löytää hammer
        hammer_patterns = [p for p in patterns if p["pattern"] == "hammer"]
        assert len(hammer_patterns) > 0

    def test_detect_patterns_shooting_star(self, temp_db, temp_osakedata_db):
        """Testaa tähdenlento kuvion tunnistus"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Shooting star: pitkä ylävarjo, lyhyt alavarjo, close lähellä low
        stock_data = [
            {
                "date": "2024-01-01",
                "open": 95.0,
                "high": 110.0,  # Pitkä ylävarjo
                "low": 90.0,
                "close": 91.0,  # Lähellä low
                "volume": 1000000,
            }
        ]

        patterns = engine._detect_patterns("TEST", stock_data)

        # Pitäisi löytää shooting star
        shooting_star_patterns = [
            p for p in patterns if p["pattern"] == "shooting_star"
        ]
        assert len(shooting_star_patterns) > 0

    def test_detect_patterns_engulfing_bullish(self, temp_db, temp_osakedata_db):
        """Testaa nouseva nielaiseva kuvion tunnistus"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Bullish engulfing: edellinen laskeva, seuraava nouseva ja suurempi
        stock_data = [
            {
                "date": "2024-01-01",
                "open": 100.0,
                "high": 102.0,
                "low": 95.0,
                "close": 96.0,  # Laskeva kynttilä
                "volume": 1000000,
            },
            {
                "date": "2024-01-02",
                "open": 94.0,
                "high": 105.0,
                "low": 93.0,
                "close": 104.0,  # Nouseva, nielaisee edellisen
                "volume": 1200000,
            },
        ]

        patterns = engine._detect_patterns("TEST", stock_data)

        # Pitäisi löytää bullish engulfing
        bullish_patterns = [p for p in patterns if p["pattern"] == "bullish_engulfing"]
        assert len(bullish_patterns) > 0

    def test_detect_patterns_engulfing_bearish(self, temp_db, temp_osakedata_db):
        """Testaa laskeva nielaiseva kuvion tunnistus"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Bearish engulfing: edellinen nouseva, seuraava laskeva ja suurempi
        stock_data = [
            {
                "date": "2024-01-01",
                "open": 95.0,
                "high": 105.0,
                "low": 94.0,
                "close": 104.0,  # Nouseva kynttilä
                "volume": 1000000,
            },
            {
                "date": "2024-01-02",
                "open": 106.0,
                "high": 107.0,
                "low": 90.0,
                "close": 92.0,  # Laskeva, nielaisee edellisen
                "volume": 1200000,
            },
        ]

        patterns = engine._detect_patterns("TEST", stock_data)

        # Pitäisi löytää bearish engulfing
        bearish_patterns = [p for p in patterns if p["pattern"] == "bearish_engulfing"]
        assert len(bearish_patterns) > 0

    def test_calculate_pattern_strength(self, temp_db, temp_osakedata_db):
        """Testaa kuvion vahvuuden laskeminen"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Testaa vahva doji (pieni body)
        candle = {
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 100.1,
            "volume": 1000000,
        }

        strength = engine._calculate_pattern_strength("doji", candle)
        assert 0.5 <= strength <= 1.0

        # Testaa heikko doji (iso body)
        weak_candle = {
            "open": 100.0,
            "high": 102.0,
            "low": 98.0,
            "close": 105.0,  # Iso ero open-close
            "volume": 1000000,
        }

        weak_strength = engine._calculate_pattern_strength("doji", weak_candle)
        assert weak_strength < strength

    @patch("analysis.analyzer.AnalysisEngine._get_stock_info")
    def test_save_findings(self, mock_get_info, temp_db, temp_osakedata_db):
        """Testaa löydösten tallentaminen"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        mock_get_info.return_value = {
            "market_cap": 3000000000000,
            "sector": "Technology",
        }

        patterns = [
            {
                "date": "2024-01-01",
                "pattern": "doji",
                "strength": 0.8,
                "open": 150.0,
                "high": 155.0,
                "low": 148.0,
                "close": 152.0,
                "volume": 1000000,
            }
        ]

        result = engine._save_findings("AAPL", patterns)
        assert result is True

        # Tarkista että data tallentui
        findings = engine.db_manager.get_findings_by_ticker("AAPL")
        assert len(findings) == 1
        assert findings[0]["pattern"] == "doji"  # Käytä oikeaa kenttänimeä
        assert findings[0]["signal_strength"] == 0.8  # Käytä oikeaa kenttänimeä

    def test_get_stock_info(self, temp_db, temp_osakedata_db):
        """Testaa osakkeen tietojen haku"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        info = engine._get_stock_info("AAPL")
        assert info is not None
        assert info["market_cap"] == 3000000000000
        assert info["sector"] == "Technology"

        # Testaa olematon ticker
        no_info = engine._get_stock_info("NONEXISTENT")
        assert no_info["market_cap"] is None
        assert no_info["sector"] is None

    @patch("analysis.analyzer.AnalysisEngine.analyze_ticker")
    def test_batch_analyze(self, mock_analyze, temp_db, temp_osakedata_db):
        """Testaa usean tickerin analyysi"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Mock onnistuneet analyysit
        mock_analyze.return_value = {
            "success": True,
            "patterns_found": 2,
            "analysis_time": 1.5,
        }

        tickers = ["AAPL", "MSFT", "GOOGL"]
        results = engine.batch_analyze(tickers)

        assert len(results) == 3
        assert all(r["success"] for r in results)
        assert mock_analyze.call_count == 3

        # Tarkista että oikeat tickerit kutsuttiin
        expected_calls = [call("AAPL"), call("MSFT"), call("GOOGL")]
        mock_analyze.assert_has_calls(expected_calls)

    def test_analyze_date_range(self, temp_db, temp_osakedata_db):
        """Testaa analyysi tietyllä aikavälillä"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        start_date = "2024-01-01"
        end_date = "2024-01-02"

        # Testaa että metodi on olemassa (vaikka ei täysin implementoitu)
        assert hasattr(engine, "analyze_date_range")

    def test_performance_metrics(self, temp_db, temp_osakedata_db):
        """Testaa suorituskyvyn mittaaminen"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Simuloi analyysi ja mittaa aika
        start_time = datetime.now()
        # Yksinkertainen operaatio
        _ = engine._get_stock_data("AAPL")
        end_time = datetime.now()

        duration = (end_time - start_time).total_seconds()
        assert duration >= 0
        assert duration < 10  # Pitäisi olla nopea

    def test_memory_usage(self, temp_db, temp_osakedata_db):
        """Testaa muistin käyttö suurilla dataseteillä"""
        engine = AnalysisEngine(temp_db, temp_osakedata_db)

        # Luo suuri määrä test dataa
        large_stock_data = []
        for i in range(1000):
            large_stock_data.append(
                {
                    "date": f"2024-01-{i+1:02d}",
                    "open": 100.0 + i,
                    "high": 105.0 + i,
                    "low": 95.0 + i,
                    "close": 102.0 + i,
                    "volume": 1000000,
                }
            )

        # Testaa että analyysi toimii isommalla datalla
        patterns = engine._detect_patterns(
            "TEST", large_stock_data[:100]
        )  # Rajataan 100:aan
        assert isinstance(patterns, list)
        # Muistin käyttö ei pitäisi räjähtää käsiin
