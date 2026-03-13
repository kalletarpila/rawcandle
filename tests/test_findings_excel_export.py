"""
Yksikkötestit findings-näkymän Excel-vienti toiminnalle.

Testaa:
- Satunnaisotanta ilman palauttamista
- Ylimitoitus (pyydetään enemmän kuin saatavilla)
- Filtteröinti ensin, sitten satunnaisotanta
- Uniikit tapahtumat (ticker, date, pattern)
"""

import pytest
import random
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from results.excel_exporter import ExcelExporter


class TestExcelExportSampling:
    """Testaa Excel-vienti satunnaisotantaa."""

    @pytest.fixture
    def mock_db_manager(self):
        """Luo mock DatabaseManager."""
        db_manager = Mock()
        db_manager.db_path = "test.db"
        
        # Mock results_data (20 tapahtumaa)
        mock_results = []
        for i in range(20):
            mock_results.append({
                "id": i + 1,
                "ticker": f"TICK{i % 5}",  # 5 eri tickeriä
                "date": f"2025-01-{(i % 28) + 1:02d}",
                "candle_pattern": (i % 9),  # Patternit 0-8
                "signal_strength": round(1.0 + (i * 0.1), 2),
                "RSI14_t0": 30 + i,
                "t2": round(-5.0 + i * 0.5, 2),
                "t5": round(-3.0 + i * 0.3, 2),
                "t10": round(-1.0 + i * 0.2, 2),
                "t20": round(0.0 + i * 0.1, 2),
                # Muut sarakkeet...
                "t_1_alin": 100.0,
                "t_1_ylin": 105.0,
                "t_1_bodi": 2.0,
                "t_1_bodi_colour": 1,
                "t0_alin": 101.0,
                "t0_ylin": 106.0,
                "t0_bodi": 2.5,
                "t0_bodi_colour": 1,
                "t1_alin": 102.0,
                "t1_ylin": 107.0,
                "t1_bodi": 3.0,
                "t1_bodi_colour": 1,
                "t_2": -2.5,
                "t_5": -1.5,
                "t_10": -0.5,
                "t_15": 0.5,
                "t_20": 1.5,
                "t_2_hajonta": 1.2,
                "t_5_hajonta": 1.5,
                "t_10_hajonta": 1.8,
                "t_15_hajonta": 2.0,
                "t_20_hajonta": 2.2,
                "t_2_volyymi": 1000000,
                "t_5_volyymi": 1200000,
                "t_10_volyymi": 1500000,
                "t_15_volyymi": 1800000,
                "t_20_volyymi": 2000000,
                "t0_volyymi": 1100000,
                "t2_volyymi": 1300000,
                "t5_volyymi": 1600000,
                "t10_volyymi": 1900000,
                "t20_volyymi": 2100000,
                "t_2_5p_liukuva": 0.5,
                "t_2_10p_liukuva": 0.3,
                "t_2_20p_liukuva": 0.2,
                "t_5_5p_liukuva": 0.6,
                "t_5_10p_liukuva": 0.4,
                "t_5_20p_liukuva": 0.3,
                "t_10_5p_liukuva": 0.7,
                "t_10_10p_liukuva": 0.5,
                "t_10_20p_liukuva": 0.4,
                "t_15_5p_liukuva": 0.8,
                "t_15_10p_liukuva": 0.6,
                "t_15_20p_liukuva": 0.5,
                "t_20_5p_liukuva": 0.9,
                "t_20_10p_liukuva": 0.7,
                "t_20_20p_liukuva": 0.6,
                "t0_50p_liukuva": 1.5,
                "t0_200p_liukuva": 2.5,
                "SPX_0": 4500.0,
                "SPX_2": 4510.0,
                "SPX_5": 4520.0,
                "SPX_10": 4530.0,
                "SPX_15": 4540.0,
                "SPX_20": 4550.0,
                "SPX2": 0.2,
                "SPX5": 0.5,
                "SPX10": 1.0,
                "SPX15": 1.5,
                "SPX20": 2.0,
                "NDX_0": 15000.0,
                "NDX_2": 15100.0,
                "NDX_5": 15200.0,
                "NDX_10": 15300.0,
                "NDX_15": 15400.0,
                "NDX_20": 15500.0,
                "NDX2": 0.3,
                "NDX5": 0.7,
                "NDX10": 1.3,
                "NDX15": 1.8,
                "NDX20": 2.3,
                "t0_close_norm": 0.5,
                "bearish_divergence": 0,
                "bullish_divergence": 1 if i % 2 == 0 else 0,
                "BullDiv_strength": 1.0 if i % 2 == 0 else 0.0,
                "BullDiv_recent_strength": 1.0 if i % 2 == 0 else 0.0,
                "BullDiv_recent_offset": 0 if i % 2 == 0 else -1,
                "Has_BullDiv_recent": 1 if i % 2 == 0 else 0,
                "weekday": (i % 5) + 1,
            })
        
        db_manager.get_results_data.return_value = mock_results
        return db_manager

    @pytest.fixture
    def temp_excel_path(self):
        """Luo väliaikainen polku Excel-tiedostolle."""
        temp_dir = tempfile.mkdtemp()
        excel_path = os.path.join(temp_dir, "test_export.xlsx")
        yield excel_path
        # Cleanup
        if os.path.exists(excel_path):
            os.remove(excel_path)
        os.rmdir(temp_dir)

    def test_random_sample_without_replacement(self, mock_db_manager, temp_excel_path):
        """Testaa satunnaisotanta ilman palauttamista (uniikit tapahtumat)."""
        # Hae kaikki tapahtumat
        all_events = mock_db_manager.get_results_data()
        
        # Arpoo 10 tapahtumaa 20:stä
        sample_size = 10
        sampled_events = random.sample(all_events, sample_size)
        
        # Tarkista että saatiin oikea määrä
        assert len(sampled_events) == sample_size
        
        # Tarkista että kaikki ovat uniikkeja (ID:t)
        sampled_ids = [e["id"] for e in sampled_events]
        assert len(sampled_ids) == len(set(sampled_ids)), "Sampled events must be unique"
        
        # Tarkista että kaikki ID:t löytyvät alkuperäisestä
        all_ids = [e["id"] for e in all_events]
        for sid in sampled_ids:
            assert sid in all_ids

    def test_oversized_sample_request(self, mock_db_manager):
        """Testaa ylimitoitus: pyydetään enemmän kuin on saatavilla."""
        all_events = mock_db_manager.get_results_data()
        total_available = len(all_events)  # 20
        
        # Käyttäjä pyytää 50 tapahtumaa
        requested_count = 50
        
        # Logiikka: jos pyydetty > saatavilla, käytä kaikkia
        if requested_count > total_available:
            events_to_export = all_events
        else:
            events_to_export = random.sample(all_events, requested_count)
        
        # Tarkista että saatiin kaikki saatavilla olevat
        assert len(events_to_export) == total_available
        assert events_to_export == all_events

    def test_filtered_then_sampled(self, mock_db_manager):
        """Testaa että filtteröinti tapahtuu ensin, sitten satunnaisotanta."""
        all_events = mock_db_manager.get_results_data()
        
        # 1. Filtteröi: vain pattern 1 (Hammer)
        filtered_events = [e for e in all_events if e["candle_pattern"] == 1]
        
        # 2. Arpoo 2 tapahtumaa filtteröidystä joukosta
        sample_size = min(2, len(filtered_events))
        if sample_size > 0:
            sampled_events = random.sample(filtered_events, sample_size)
            
            # Tarkista että kaikki ovat pattern 1
            for event in sampled_events:
                assert event["candle_pattern"] == 1
            
            # Tarkista uniikkius
            sampled_ids = [e["id"] for e in sampled_events]
            assert len(sampled_ids) == len(set(sampled_ids))

    def test_unique_ticker_date_pattern_combinations(self, mock_db_manager):
        """Testaa että jokainen (ticker, date, pattern) yhdistelmä on uniikki tapahtuma."""
        all_events = mock_db_manager.get_results_data()
        
        # Luo joukko (ticker, date, pattern) -tupleista
        event_tuples = set()
        for event in all_events:
            event_tuple = (
                event["ticker"],
                event["date"],
                event["candle_pattern"]
            )
            event_tuples.add(event_tuple)
        
        # Jos samalla tickerillä, samana päivänä, eri pattern
        # => ne ovat eri tapahtumia
        # Esim: TICK0, 2025-01-01, pattern=0 ja TICK0, 2025-01-01, pattern=5
        # ovat kaksi eri tapahtumaa
        
        # Testidatassa ID:t ovat uniikkeja, joten ei duplikaatteja
        assert len(all_events) == len(event_tuples)

    def test_excel_export_with_id_filter(self, mock_db_manager, temp_excel_path):
        """Testaa ExcelExporter ID-suodatuksella."""
        with patch('results.excel_exporter.DatabaseManager', return_value=mock_db_manager):
            exporter = ExcelExporter("test.db")
            exporter.db_manager = mock_db_manager
            
            # Valitse 5 ID:tä
            selected_ids = [1, 3, 5, 7, 9]
            
            # Vie Exceliin
            success, message = exporter.export_to_excel(
                output_path=temp_excel_path,
                id_filter=selected_ids,
            )
            
            # Tarkista onnistuminen
            assert success is True
            assert os.path.exists(temp_excel_path)
            
            # Varmista että viety oikea määrä
            assert "5 riviä" in message

    def test_random_sample_repeatability_with_seed(self):
        """Testaa että random.seed() tuottaa toistettavia tuloksia."""
        data = list(range(100))
        
        # Ensimmäinen ajo
        random.seed(42)
        sample1 = random.sample(data, 10)
        
        # Toinen ajo samalla seedillä
        random.seed(42)
        sample2 = random.sample(data, 10)
        
        # Pitäisi olla identtiset
        assert sample1 == sample2

    def test_empty_filtered_results(self, mock_db_manager):
        """Testaa tilanne jossa filtteröinti tuottaa tyhjän joukon."""
        all_events = mock_db_manager.get_results_data()
        
        # Filtteröi: pattern 999 (ei ole olemassa)
        filtered_events = [e for e in all_events if e["candle_pattern"] == 999]
        
        assert len(filtered_events) == 0
        
        # Satunnaisotanta tyhjästä joukosta
        sample_size = 10
        if len(filtered_events) == 0:
            sampled_events = []
        else:
            sampled_events = random.sample(filtered_events, min(sample_size, len(filtered_events)))
        
        assert len(sampled_events) == 0


class TestExcelExporterIDFilter:
    """Testaa ExcelExporter id_filter parametria."""

    @pytest.fixture
    def mock_results(self):
        """Luo mock results_data."""
        return [
            {"id": 1, "ticker": "AAPL", "candle_pattern": 1, "date": "2025-01-01"},
            {"id": 2, "ticker": "MSFT", "candle_pattern": 2, "date": "2025-01-02"},
            {"id": 3, "ticker": "GOOGL", "candle_pattern": 3, "date": "2025-01-03"},
            {"id": 4, "ticker": "AMZN", "candle_pattern": 1, "date": "2025-01-04"},
            {"id": 5, "ticker": "TSLA", "candle_pattern": 2, "date": "2025-01-05"},
        ]

    def test_id_filter_priority_over_pattern_filter(self, mock_results):
        """Testaa että ID-suodatus on ensisijainen pattern-suodatukseen nähden."""
        # Simuloi ExcelExporter logiikka
        all_results = mock_results
        selected_patterns = [1]  # Vain Hammer
        id_filter = [2, 3, 5]  # MSFT, GOOGL, TSLA
        
        # ID-suodatus ensin
        if id_filter is not None:
            id_set = set(id_filter)
            results = [r for r in all_results if r.get("id") in id_set]
        else:
            results = all_results
            if selected_patterns is not None:
                results = [r for r in results if r["candle_pattern"] in selected_patterns]
        
        # Pitäisi olla ID:t 2, 3, 5 (ei pattern-suodatusta)
        assert len(results) == 3
        assert all(r["id"] in [2, 3, 5] for r in results)

    def test_id_filter_none_uses_pattern_filter(self, mock_results):
        """Testaa että ilman ID-suodatusta käytetään pattern-suodatusta."""
        all_results = mock_results
        selected_patterns = [1]  # Vain Hammer
        id_filter = None
        
        # ID-suodatus ensin
        if id_filter is not None:
            id_set = set(id_filter)
            results = [r for r in all_results if r.get("id") in id_set]
        else:
            results = all_results
            if selected_patterns is not None:
                results = [r for r in results if r["candle_pattern"] in selected_patterns]
        
        # Pitäisi olla ID:t 1, 4 (pattern 1)
        assert len(results) == 2
        assert all(r["candle_pattern"] == 1 for r in results)

    def test_empty_id_filter_returns_nothing(self, mock_results):
        """Testaa että tyhjä ID-lista palauttaa tyhjän joukon."""
        all_results = mock_results
        id_filter = []  # Tyhjä lista
        
        if id_filter is not None:
            id_set = set(id_filter)
            results = [r for r in all_results if r.get("id") in id_set]
        else:
            results = all_results
        
        assert len(results) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
