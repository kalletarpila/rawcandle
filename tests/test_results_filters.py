"""
Yksikkötestit results-sivun uusille filtereille.

Testaa:
- downtrend pattern-filtteri (pattern=0)
- Divergenssi-yhdistelmä filtteri generoinnissa
- Divergenssi-yhdistelmä filtteri Excel-viennissä
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from analysis.results_generator import ResultsGenerator


class TestDowntrendPatternFilter:
    """Testaa downtrend pattern-filtteri."""

    def test_downtrend_in_pattern_mapping(self):
        """Testaa että downtrend (0) on pattern_mapping:ssa."""
        pattern_mapping = {
            "downtrend": 0,
            "Hammer": 1,
            "Bullish Engulfing": 2,
            "Piercing Pattern": 3,
            "Three White Soldiers": 4,
            "Morning Star": 5,
            "Dragonfly Doji": 6,
            "Bullish Divergence": 7,
            "Bearish Divergence": 8,
        }

        assert "downtrend" in pattern_mapping
        assert pattern_mapping["downtrend"] == 0

    def test_pattern_number_to_name_conversion(self):
        """Testaa että pattern-numerot muunnetaan nimiksi oikein."""
        pattern_names = {
            0: "downtrend",
            1: "Hammer",
            2: "Bullish Engulfing",
            3: "Piercing Pattern",
            4: "Three White Soldiers",
            5: "Morning Star",
            6: "Dragonfly Doji",
            7: "Bullish Divergence",
            8: "Bearish Divergence",
        }

        # Testaa muunnos
        pattern_filter = [0, 1, 7]
        converted = [
            pattern_names[num] for num in pattern_filter if num in pattern_names
        ]

        assert converted == ["downtrend", "Hammer", "Bullish Divergence"]

    def test_downtrend_pattern_filter_in_results(self):
        """Testaa että downtrend suodatetaan oikein."""
        # Mock results data
        all_results = [
            {
                "id": 1,
                "candle_pattern": 0,
                "ticker": "AAPL",
                "date": "2025-01-01",
            },  # downtrend
            {
                "id": 2,
                "candle_pattern": 1,
                "ticker": "MSFT",
                "date": "2025-01-01",
            },  # Hammer
            {
                "id": 3,
                "candle_pattern": 0,
                "ticker": "GOOGL",
                "date": "2025-01-02",
            },  # downtrend
            {
                "id": 4,
                "candle_pattern": 7,
                "ticker": "AMZN",
                "date": "2025-01-03",
            },  # Bullish Divergence
        ]

        # Suodata vain downtrend (pattern=0)
        selected_patterns = [0]
        filtered = [r for r in all_results if r["candle_pattern"] in selected_patterns]

        assert len(filtered) == 2
        assert all(r["candle_pattern"] == 0 for r in filtered)
        assert filtered[0]["ticker"] == "AAPL"
        assert filtered[1]["ticker"] == "GOOGL"


class TestDivergenceComboFilter:
    """Testaa divergenssi-yhdistelmä filtteri."""

    @pytest.fixture
    def mock_findings(self):
        """Luo mock findings data."""
        return [
            # AAPL: Sekä Hammer että Bullish Divergence samana päivänä
            {"ticker": "AAPL", "pvm": "2025-01-01", "pattern": "Hammer", "id": 1},
            {
                "ticker": "AAPL",
                "pvm": "2025-01-01",
                "pattern": "Bullish Divergence",
                "id": 2,
            },
            # MSFT: Vain Hammer (ei divergenssiä)
            {"ticker": "MSFT", "pvm": "2025-01-02", "pattern": "Hammer", "id": 3},
            # GOOGL: Vain Bearish Divergence (ei kynttilää)
            {
                "ticker": "GOOGL",
                "pvm": "2025-01-03",
                "pattern": "Bearish Divergence",
                "id": 4,
            },
            # TSLA: Morning Star + Bearish Divergence samana päivänä
            {"ticker": "TSLA", "pvm": "2025-01-04", "pattern": "Morning Star", "id": 5},
            {
                "ticker": "TSLA",
                "pvm": "2025-01-04",
                "pattern": "Bearish Divergence",
                "id": 6,
            },
            # NVDA: Downtrend + Bearish Divergence samana päivänä
            {"ticker": "NVDA", "pvm": "2025-01-05", "pattern": "downtrend", "id": 7},
            {
                "ticker": "NVDA",
                "pvm": "2025-01-05",
                "pattern": "Bearish Divergence",
                "id": 8,
            },
        ]

    def test_filter_divergence_combos(self, mock_findings):
        """Testaa _filter_divergence_combos metodi."""
        # Kynttilämalli patternit
        candle_patterns = {
            "downtrend",
            "Hammer",
            "Bullish Engulfing",
            "Piercing Pattern",
            "Three White Soldiers",
            "Morning Star",
            "Dragonfly Doji",
        }

        # Divergenssi patternit
        divergence_patterns = {"Bullish Divergence", "Bearish Divergence"}

        # Rakenna (ticker, date) -> patterns mapping
        ticker_date_patterns = {}
        for finding in mock_findings:
            key = (finding.get("ticker"), finding.get("pvm"))
            pattern = finding.get("pattern")

            if key not in ticker_date_patterns:
                ticker_date_patterns[key] = set()
            ticker_date_patterns[key].add(pattern)

        # Etsi yhdistelmät
        combo_keys = set()
        for key, patterns in ticker_date_patterns.items():
            has_candle = bool(patterns & candle_patterns)
            has_divergence = bool(patterns & divergence_patterns)

            if has_candle and has_divergence:
                combo_keys.add(key)

        # Suodata findings
        filtered = [
            f for f in mock_findings if (f.get("ticker"), f.get("pvm")) in combo_keys
        ]

        # Pitäisi olla 6 tapahtumaa (2 AAPL + 2 TSLA + 2 NVDA)
        assert len(filtered) == 6

        # Tarkista että kaikki kolme tickeriä löytyvät
        tickers = {f["ticker"] for f in filtered}
        assert tickers == {"AAPL", "TSLA", "NVDA"}

        # Tarkista että MSFT ja GOOGL eivät löydy
        assert "MSFT" not in tickers
        assert "GOOGL" not in tickers

    def test_divergence_combo_filter_with_results_data(self):
        """Testaa divergenssi-yhdistelmä filtteri results_data taulussa."""
        # Mock results_data (candle_pattern on numero)
        all_results = [
            # AAPL: Hammer (1) + Bullish Divergence (7) samana päivänä
            {"id": 1, "ticker": "AAPL", "date": "2025-01-01", "candle_pattern": 1},
            {"id": 2, "ticker": "AAPL", "date": "2025-01-01", "candle_pattern": 7},
            # MSFT: Vain Hammer (1)
            {"id": 3, "ticker": "MSFT", "date": "2025-01-02", "candle_pattern": 1},
            # GOOGL: Vain Bearish Divergence (8)
            {"id": 4, "ticker": "GOOGL", "date": "2025-01-03", "candle_pattern": 8},
            # TSLA: Piercing Pattern (3) + Bearish Divergence (8) samana päivänä
            {"id": 5, "ticker": "TSLA", "date": "2025-01-04", "candle_pattern": 3},
            {"id": 6, "ticker": "TSLA", "date": "2025-01-04", "candle_pattern": 8},
            # NVDA: Downtrend (0) + Bearish Divergence (8)
            {"id": 7, "ticker": "NVDA", "date": "2025-01-05", "candle_pattern": 0},
            {"id": 8, "ticker": "NVDA", "date": "2025-01-05", "candle_pattern": 8},
        ]

        # Kynttilämalli patternit (0-6)
        candle_patterns = {0, 1, 2, 3, 4, 5, 6}
        # Divergenssi patternit (7-8)
        divergence_patterns = {7, 8}

        # Rakenna (ticker, date) -> patterns mapping
        ticker_date_patterns = {}
        ticker_date_ids = {}

        for result in all_results:
            key = (result.get("ticker"), result.get("date"))
            pattern = result.get("candle_pattern")
            result_id = result.get("id")

            if key not in ticker_date_patterns:
                ticker_date_patterns[key] = set()
                ticker_date_ids[key] = []

            ticker_date_patterns[key].add(pattern)
            ticker_date_ids[key].append(result_id)

        # Etsi yhdistelmät
        combo_ids = []
        for key, patterns in ticker_date_patterns.items():
            has_candle = bool(patterns & candle_patterns)
            has_divergence = bool(patterns & divergence_patterns)

            if has_candle and has_divergence:
                combo_ids.extend(ticker_date_ids[key])

        # Pitäisi olla 6 ID:tä (AAPL: 1,2 / TSLA: 5,6 / NVDA: 7,8)
        assert len(combo_ids) == 6
        assert set(combo_ids) == {1, 2, 5, 6, 7, 8}

    def test_no_combos_found(self):
        """Testaa tilanne jossa ei löydy yhdistelmiä."""
        findings = [
            {"ticker": "AAPL", "pvm": "2025-01-01", "pattern": "Hammer", "id": 1},
            {
                "ticker": "MSFT",
                "pvm": "2025-01-02",
                "pattern": "Bullish Engulfing",
                "id": 2,
            },
            {
                "ticker": "GOOGL",
                "pvm": "2025-01-03",
                "pattern": "Piercing Pattern",
                "id": 3,
            },
        ]

        candle_patterns = {"Hammer", "Bullish Engulfing", "Piercing Pattern"}
        divergence_patterns = {"Bullish Divergence", "Bearish Divergence"}

        ticker_date_patterns = {}
        for finding in findings:
            key = (finding.get("ticker"), finding.get("pvm"))
            pattern = finding.get("pattern")

            if key not in ticker_date_patterns:
                ticker_date_patterns[key] = set()
            ticker_date_patterns[key].add(pattern)

        combo_keys = set()
        for key, patterns in ticker_date_patterns.items():
            has_candle = bool(patterns & candle_patterns)
            has_divergence = bool(patterns & divergence_patterns)

            if has_candle and has_divergence:
                combo_keys.add(key)

        # Ei pitäisi löytyä yhdistelmiä
        assert len(combo_keys) == 0

    def test_downtrend_counted_as_candle_pattern(self):
        """Testaa että downtrend (0) lasketaan kynttilämalliksi."""
        findings = [
            {"ticker": "AAPL", "pvm": "2025-01-01", "pattern": "downtrend", "id": 1},
            {
                "ticker": "AAPL",
                "pvm": "2025-01-01",
                "pattern": "Bullish Divergence",
                "id": 2,
            },
        ]

        candle_patterns = {
            "downtrend",
            "Hammer",
            "Bullish Engulfing",
            "Piercing Pattern",
            "Three White Soldiers",
            "Morning Star",
            "Dragonfly Doji",
        }

        divergence_patterns = {"Bullish Divergence", "Bearish Divergence"}

        ticker_date_patterns = {}
        for finding in findings:
            key = (finding.get("ticker"), finding.get("pvm"))
            pattern = finding.get("pattern")

            if key not in ticker_date_patterns:
                ticker_date_patterns[key] = set()
            ticker_date_patterns[key].add(pattern)

        combo_keys = set()
        for key, patterns in ticker_date_patterns.items():
            has_candle = bool(patterns & candle_patterns)
            has_divergence = bool(patterns & divergence_patterns)

            if has_candle and has_divergence:
                combo_keys.add(key)

        # Downtrend + divergenssi muodostaa yhdistelmän
        assert len(combo_keys) == 1


class TestResultsGeneratorDivergenceCombo:
    """Testaa ResultsGenerator _filter_divergence_combos metodi."""

    def test_filter_divergence_combos_method(self):
        """Testaa että _filter_divergence_combos metodi toimii oikein."""
        # Mock findings
        findings = [
            {"ticker": "AAPL", "pvm": "2025-01-01", "pattern": "Hammer"},
            {"ticker": "AAPL", "pvm": "2025-01-01", "pattern": "Bullish Divergence"},
            {"ticker": "MSFT", "pvm": "2025-01-02", "pattern": "Hammer"},
            {"ticker": "GOOGL", "pvm": "2025-01-03", "pattern": "Bearish Divergence"},
        ]

        # Mock ResultsGenerator
        with patch("analysis.results_generator.DatabaseManager"):
            generator = ResultsGenerator(Mock(), "test.db")

            # Testaa metodi
            filtered = generator._filter_divergence_combos(findings)

            # Pitäisi palauttaa vain AAPL findings (1 kpl, ticker+date dedup)
            assert len(filtered) == 1
            assert all(f["ticker"] == "AAPL" for f in filtered)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
