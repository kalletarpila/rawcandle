import datetime as dt

from simu.engine import SimulationEngine, SimulationRequest, SimulationSettings
from simu.db import AnalysisEvent, PriceRow, PriceSeries


class StubAnalysisRepo:
    def __init__(self, candle_events, divergence_events):
        self._candles = candle_events
        self._divergences = divergence_events

    def fetch_events(self, ticker, start_date, end_date):
        return [
            event
            for event in self._candles
            if event.ticker == ticker and start_date <= event.date <= end_date
        ]

    def fetch_divergences(self, ticker, start_date, end_date):
        return [
            event
            for event in self._divergences
            if event.ticker == ticker and start_date <= event.date <= end_date
        ]


class StubPriceRepo:
    def __init__(self, rows):
        self._series = PriceSeries(rows)

    def fetch_price_series(self, ticker):
        return self._series


def _build_price_rows():
    rows = []
    date = dt.date(2024, 1, 1)
    for i in range(40):
        base = 20 + i * 0.1
        rows.append(
            PriceRow(
                date=date + dt.timedelta(days=i),
                open=base,
                high=base + 0.2,
                low=base - 0.2,
                close=base,
                volume=1_000_000 + (i * 1000),
            )
        )
    return rows


def _settings(require_combo: bool) -> SimulationSettings:
    return SimulationSettings(
        start_date=dt.date(2024, 1, 1),
        end_date=dt.date(2024, 3, 31),
        capital_thousands=10,
        invest_percent=50,
        drop_percent=5,
        drop_average_days=5,
        rise_percent=10,
        min_strength=0.1,
        max_rsi=100,
        min_volume_growth=-100,
        selected_patterns=["hammer", "bullish_divergence"],
        require_divergence_combo=require_combo,
    )


def test_engine_executes_trade_when_combo_matches():
    t0 = dt.date(2024, 2, 1)
    candle_event = AnalysisEvent(
        ticker="AAA",
        date=t0,
        pattern_key="hammer",
        raw_pattern="Hammer",
        strength=0.9,
    )
    divergence_event = AnalysisEvent(
        ticker="AAA",
        date=t0 - dt.timedelta(days=1),
        pattern_key="bullish_divergence",
        raw_pattern="Bullish Divergence",
        strength=1.2,
    )

    engine = SimulationEngine(
        analysis_repo=StubAnalysisRepo([candle_event], [divergence_event]),
        price_repo=StubPriceRepo(_build_price_rows()),
    )

    request = SimulationRequest(ticker="AAA", settings=_settings(require_combo=True))
    result = engine.run(request)

    assert result.buy_trades == 1
    assert result.end_capital != result.start_capital


def test_engine_skips_trade_without_divergence():
    t0 = dt.date(2024, 2, 1)
    candle_event = AnalysisEvent(
        ticker="AAA",
        date=t0,
        pattern_key="hammer",
        raw_pattern="Hammer",
        strength=0.9,
    )
    divergence_event = AnalysisEvent(
        ticker="AAA",
        date=t0 - dt.timedelta(days=10),
        pattern_key="bullish_divergence",
        raw_pattern="Bullish Divergence",
        strength=1.0,
    )

    engine = SimulationEngine(
        analysis_repo=StubAnalysisRepo([candle_event], [divergence_event]),
        price_repo=StubPriceRepo(_build_price_rows()),
    )

    request = SimulationRequest(ticker="AAA", settings=_settings(require_combo=True))
    result = engine.run(request)

    assert result.buy_trades == 0
