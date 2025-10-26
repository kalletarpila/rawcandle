from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from typing import Iterable, List, Optional

from . import config
from .db import AnalysisRepository, PriceRepository, PriceSeries
from .indicators import compute_rsi, compute_volume_growth
from .results import SimulationResult
from .signals import SelectedSignal, canonicalise_selection, resolve_signals
from .utils import ensure_upper_ticker


@dataclass(frozen=True)
class SimulationSettings:
    start_date: _dt.date
    end_date: _dt.date
    capital_thousands: int
    invest_percent: float
    drop_percent: float
    rise_percent: float
    min_strength: float
    max_rsi: float
    min_volume_growth: float
    selected_patterns: List[str] = field(default_factory=list)

    @property
    def starting_capital(self) -> float:
        return float(self.capital_thousands) * 1000.0

    @property
    def invest_fraction(self) -> float:
        return max(0.0, min(self.invest_percent, 100.0)) / 100.0

    def canonical_patterns(self) -> List[str]:
        return canonicalise_selection(self.selected_patterns)


@dataclass
class SimulationRequest:
    ticker: str
    settings: SimulationSettings


@dataclass
class PendingBuy:
    date: _dt.date
    t0_date: _dt.date


@dataclass
class PendingSale:
    date: _dt.date
    trigger_date: _dt.date


class SimulationEngine:
    def __init__(
        self,
        analysis_repo: AnalysisRepository,
        price_repo: PriceRepository,
    ) -> None:
        self.analysis_repo = analysis_repo
        self.price_repo = price_repo

    def run(self, request: SimulationRequest) -> SimulationResult:
        ticker = ensure_upper_ticker(request.ticker)
        settings = request.settings

        price_series = self.price_repo.fetch_price_series(ticker)
        if len(price_series) == 0:
            start_capital = settings.starting_capital
            return SimulationResult(
                ticker=ticker,
                start_capital=start_capital,
                end_capital=start_capital,
                growth_pct=0.0,
                buy_trades=0,
            )

        canonical_patterns = settings.canonical_patterns()
        signals_map = resolve_signals(
            self.analysis_repo,
            ticker,
            settings.start_date,
            settings.end_date,
            canonical_patterns,
            settings.min_strength,
        )

        price_rows_all = price_series.rows()
        rsi_map = compute_rsi(price_rows_all, period=config.RSI_PERIOD)
        volume_growth_map = compute_volume_growth(price_rows_all, window=config.VOLUME_SMA_WINDOW)

        trading_dates = price_series.dates_between(settings.start_date, settings.end_date)
        if not trading_dates:
            start_capital = settings.starting_capital
            final_row = price_series.previous_on_or_before(settings.end_date)
            end_capital = start_capital
            if final_row:
                end_capital = start_capital  # no trades, but close price defined
            return SimulationResult(
                ticker=ticker,
                start_capital=start_capital,
                end_capital=start_capital,
                growth_pct=0.0,
                buy_trades=0,
            )

        cash = settings.starting_capital
        shares = 0
        avg_cost = 0.0
        buy_trades = 0

        pending_buys: List[PendingBuy] = []
        pending_sale: Optional[PendingSale] = None

        invest_fraction = settings.invest_fraction
        drop_multiplier = 1.0 - (settings.drop_percent / 100.0)
        rise_multiplier = 1.0 + (settings.rise_percent / 100.0)

        end_date = settings.end_date

        for current_date in trading_dates:
            row = price_series.get(current_date)
            if row is None:
                continue

            # Execute pending sale at the day's open before new buys.
            if pending_sale and pending_sale.date == current_date and shares > 0:
                sale_price = row.open
                cash += shares * sale_price
                shares = 0
                avg_cost = 0.0
                pending_sale = None

            # Execute any pending buys scheduled for today.
            executable_buys = [p for p in pending_buys if p.date == current_date]
            pending_buys = [p for p in pending_buys if p.date != current_date]
            for pending_buy in executable_buys:
                if invest_fraction <= 0:
                    continue
                buy_price = row.open
                budget = cash * invest_fraction
                max_shares = int(budget // buy_price)
                if max_shares < 1:
                    # Skip silently if funds insufficient for at least one share
                    continue
                total_cost = max_shares * buy_price
                cash -= total_cost
                if shares == 0:
                    avg_cost = buy_price
                else:
                    avg_cost = ((avg_cost * shares) + total_cost) / (shares + max_shares)
                shares += max_shares
                buy_trades += 1

            # Evaluate t0 signal for current day.
            signal = signals_map.get(current_date)
            if signal:
                rsi_value = rsi_map.get(current_date)
                if rsi_value is not None and rsi_value <= settings.max_rsi:
                    volume_growth = volume_growth_map.get(current_date)
                    if volume_growth is not None and volume_growth >= settings.min_volume_growth:
                        next_date = price_series.next_date_within(current_date, end_date)
                        if next_date:
                            pending_buys.append(PendingBuy(date=next_date, t0_date=current_date))

            # Evaluate stop-loss / take-profit triggers at close.
            if shares > 0 and pending_sale is None:
                stop_price = avg_cost * drop_multiplier
                take_price = avg_cost * rise_multiplier
                close_price = row.close
                should_sell = False
                if close_price <= stop_price:
                    should_sell = True
                elif close_price >= take_price:
                    should_sell = True
                if should_sell:
                    next_date = price_series.next_date_within(current_date, end_date)
                    if next_date:
                        pending_sale = PendingSale(date=next_date, trigger_date=current_date)

        # Final valuation at the last available close on/before end_date.
        final_row = price_series.previous_on_or_before(end_date)
        end_capital = cash
        if shares > 0 and final_row:
            end_capital += shares * final_row.close

        start_capital = settings.starting_capital
        growth_pct = 0.0
        if start_capital > 0:
            growth_pct = ((end_capital / start_capital) - 1.0) * 100.0

        return SimulationResult(
            ticker=ticker,
            start_capital=start_capital,
            end_capital=end_capital,
            growth_pct=growth_pct,
            buy_trades=buy_trades,
        )

