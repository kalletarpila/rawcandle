import types
from typing import List, Dict

import pytest

from analysis import view as analysis_view_module


class DummyControl:
    """Minimal flet-kontrollin korvike testeille."""

    def __init__(self, value=None):
        self.value = value

    def update(self):
        pass


@pytest.fixture
def sample_findings() -> List[Dict]:
    return [
        {
            "id": 1,
            "ticker": "AAPL",
            "date": "2024-01-02",
            "pattern": "Hammer",
            "signal_strength": 0.82,
            "market": "usa",
            "rsi14": 34.2,
        },
        {
            "id": 2,
            "ticker": "MSFT",
            "date": "2024-01-05",
            "pattern": "Piercing Pattern",
            "signal_strength": 0.71,
            "market": "usa",
            "rsi14": 55.0,
        },
        {
            "id": 3,
            "ticker": "NOKIA.HE",
            "date": "2024-01-07",
            "pattern": "Bullish Engulfing",
            "signal_strength": 0.65,
            "market": "suomi",
            "rsi14": 48.5,
        },
    ]


@pytest.fixture
def analysis_view(monkeypatch, sample_findings):
    """Palauta AnalysisView-instanssi stubatuilla riippuvuuksilla."""

    class DummyDB:
        def __init__(self, *_, **__):
            self._data = sample_findings.copy()

        def get_all_findings(self):
            return self._data.copy()

        def get_divergence_combo_pairs(self):
            return set()

    class DummyEngine:
        def __init__(self, *_, **__):
            pass

        def analyze_ticker(self, ticker: str):
            return {"success": True, "ticker": ticker}

    monkeypatch.setattr(
        analysis_view_module, "DatabaseManager", lambda *args, **kwargs: DummyDB()
    )
    monkeypatch.setattr(analysis_view_module, "AnalysisEngine", DummyEngine)
    monkeypatch.setattr(
        analysis_view_module,
        "list_markets",
        lambda *_args, **_kwargs: [{"name": "USA", "abbreviation": "usa"}],
    )
    monkeypatch.setattr(
        analysis_view_module, "get_market_for_ticker", lambda *_, **__: "usa"
    )

    class MockPage:
        def update(self):
            pass

        def show_snack_bar(self, _snack):
            pass

    view = analysis_view_module.AnalysisView(MockPage())
    # Älä rakenna oikeaa Flet-taulukkoa testeissä
    view.findings_table = types.SimpleNamespace(rows=[], update=lambda: None)
    view.total_findings_text = types.SimpleNamespace(value="0")
    view.avg_strength_text = types.SimpleNamespace(value="0.0")
    view.pattern_counts_text = types.SimpleNamespace(value="")
    view._update_table = lambda: None
    view._update_statistics = lambda: None

    view.all_findings = sample_findings.copy()
    view.filtered_findings = sample_findings.copy()
    return view


def _attach_default_controls(view: analysis_view_module.AnalysisView):
    """Aseta oletusohjaimet jotta _apply_filters toimii ilman Fletiä."""

    view.search_field = DummyControl("")
    view.pattern_filter = DummyControl("")
    view.market_filter = DummyControl(view.ALL_MARKETS_KEY)
    view.date_filter_enabled = DummyControl(False)
    view.start_date_field = DummyControl("")
    view.end_date_field = DummyControl("")
    view.divergence_combo_filter = DummyControl(False)


def test_filter_by_ticker_exact_match(analysis_view):
    _attach_default_controls(analysis_view)
    analysis_view.filter_by_ticker("MSFT")
    assert len(analysis_view.filtered_findings) == 1
    assert analysis_view.filtered_findings[0]["ticker"] == "MSFT"


def test_apply_filters_combines_pattern_and_market(analysis_view):
    _attach_default_controls(analysis_view)
    analysis_view.pattern_filter.value = "Hammer"
    analysis_view.market_filter.value = "usa"

    analysis_view._apply_filters()

    assert len(analysis_view.filtered_findings) == 1
    assert analysis_view.filtered_findings[0]["ticker"] == "AAPL"


def test_search_findings_supports_pattern_lookup(analysis_view):
    results = analysis_view.search_findings("engulf")
    assert len(results) == 1
    assert results[0]["pattern"] == "Bullish Engulfing"


def test_sort_findings_by_pattern_returns_alphabetical(analysis_view):
    analysis_view.filtered_findings = [
        {"pattern": "Piercing Pattern"},
        {"pattern": "Bullish Engulfing"},
        {"pattern": "Hammer"},
    ]

    sorted_rows = analysis_view.sort_findings("pattern")
    assert [row["pattern"] for row in sorted_rows] == [
        "Bullish Engulfing",
        "Hammer",
        "Piercing Pattern",
    ]


def test_clear_filters_resets_ui_fields(analysis_view):
    _attach_default_controls(analysis_view)
    analysis_view.search_field.value = "AAPL"
    analysis_view.pattern_filter.value = "Hammer"
    analysis_view.market_filter.value = "usa"
    analysis_view.date_filter_enabled.value = True
    analysis_view.start_date_field.value = "2024-01-01"
    analysis_view.end_date_field.value = "2024-01-05"
    analysis_view.divergence_combo_filter.value = True
    analysis_view._clear_filters(None)

    assert analysis_view.search_field.value == ""
    assert analysis_view.pattern_filter.value == ""
    assert analysis_view.market_filter.value == analysis_view.ALL_MARKETS_KEY
    assert analysis_view.date_filter_enabled.value is False
    assert analysis_view.start_date_field.value == ""
    assert analysis_view.end_date_field.value == ""
    assert analysis_view.divergence_combo_filter.value is False
    assert analysis_view.filtered_findings == analysis_view.all_findings
