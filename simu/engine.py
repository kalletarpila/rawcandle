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
    drop_average_days: int
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

    @property
    def drop_average_window(self) -> int:
        return max(1, self.drop_average_days)

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
        print(
            "[SIMU][INIT]",
            ticker,
            f"capital_thousands={settings.capital_thousands}",
            f"starting_cash={settings.starting_capital:,.2f}",
        )
        signal_count = 0
        eligible_signals = 0

        if len(price_series) == 0:
            start_capital = settings.starting_capital
            return SimulationResult(
                ticker=ticker,
                start_capital=start_capital,
                end_capital=start_capital,
                growth_pct=0.0,
                buy_trades=0,
                signals_found=0,
                eligible_signals=0,
            )

        canonical_patterns = settings.canonical_patterns()
        downtrend_only = set(canonical_patterns) == {"downtrend"}
        price_rows_all = price_series.rows()
        signals_map = resolve_signals(
            self.analysis_repo,
            ticker,
            settings.start_date,
            settings.end_date,
            canonical_patterns,
            settings.min_strength,
        )
        signal_count = len(signals_map)

        rsi_map = compute_rsi(price_rows_all, period=config.RSI_PERIOD)
        volume_growth_map = compute_volume_growth(
            price_rows_all, window=config.VOLUME_SMA_WINDOW
        )

        trading_dates = price_series.dates_between(
            settings.start_date, settings.end_date
        )
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
        winning_trades = 0
        losing_trades = 0

        pending_buys: List[PendingBuy] = []
        pending_sale: Optional[PendingSale] = None

        invest_fraction = settings.invest_fraction
        drop_multiplier = 1.0 - (settings.drop_percent / 100.0)
        rise_multiplier = 1.0 + (settings.rise_percent / 100.0)

        end_date = settings.end_date

        drop_window = settings.drop_average_window

        for current_date in trading_dates:
            row = price_series.get(current_date)
            if row is None:
                continue

            # Execute pending sale at the day's open before new buys.
            if pending_sale and pending_sale.date == current_date and shares > 0:
                sale_price = row.open
                print(
                    "[SIMU][SELL]",
                    ticker,
                    current_date,
                    f"shares={shares}",
                    f"price={sale_price:.2f}",
                    f"cash_before={cash:.2f}",
                )
                # Laske kaupan tulos
                profit_per_share = sale_price - avg_cost
                if profit_per_share > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1

                cash += shares * sale_price
                print(
                    "[SIMU][SELL]",
                    ticker,
                    current_date,
                    "cash_after",
                    f"{cash:.2f}",
                    f"profit_per_share={profit_per_share:.2f}",
                )
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
                print(
                    "[SIMU][BUY]",
                    ticker,
                    current_date,
                    f"shares={max_shares}",
                    f"price={buy_price:.2f}",
                    f"cost={total_cost:.2f}",
                    f"cash_before={cash:.2f}",
                )
                cash -= total_cost
                print(
                    "[SIMU][BUY]",
                    ticker,
                    current_date,
                    "cash_after",
                    f"{cash:.2f}",
                )
                if shares == 0:
                    avg_cost = buy_price
                else:
                    avg_cost = ((avg_cost * shares) + total_cost) / (
                        shares + max_shares
                    )
                shares += max_shares
                buy_trades += 1

            # Evaluate t0 signal for current day.
            signal = signals_map.get(current_date)
            if signal:
                if downtrend_only:
                    rsi_value = rsi_map.get(current_date)
                    volume_growth = volume_growth_map.get(current_date)
                    rsi_ok = True
                    vol_ok = True
                else:
                    rsi_value = rsi_map.get(current_date)
                    volume_growth = volume_growth_map.get(current_date)
                    rsi_ok = rsi_value is not None and rsi_value <= settings.max_rsi
                    vol_ok = (
                        volume_growth is not None
                        and volume_growth >= settings.min_volume_growth
                    )
                next_date = price_series.next_date_within(current_date, end_date)
                print(
                    "[SIMU][SIGNAL]",
                    ticker,
                    current_date,
                    signal.raw_pattern,
                    f"strength={signal.strength:.2f}",
                    f"RSI={rsi_value:.2f}" if rsi_value is not None else "RSI=NA",
                    (
                        f"vol%={volume_growth:.2f}"
                        if volume_growth is not None
                        else "vol%=NA"
                    ),
                    f"RSI_OK={rsi_ok}",
                    f"VOL_OK={vol_ok}",
                    f"next_date={next_date}",
                )
                if rsi_ok and vol_ok and next_date:
                    eligible_signals += 1
                    pending_buys.append(
                        PendingBuy(date=next_date, t0_date=current_date)
                    )

            # Evaluate stop-loss / take-profit triggers at close.
            if shares > 0 and pending_sale is None:
                previous_closes = price_series.previous_closes(
                    current_date, drop_window
                )
                drop_reference = None
                if len(previous_closes) >= drop_window:
                    drop_reference = sum(previous_closes) / len(previous_closes)
                take_price = avg_cost * rise_multiplier
                close_price = row.close
                should_sell = False
                drop_reason = None
                if drop_reference is not None:
                    drop_threshold = drop_reference * drop_multiplier
                    if close_price <= drop_threshold:
                        drop_reason = "avoid loss"
                        should_sell = True
                if close_price >= take_price:
                    drop_reason = "secure profits"
                    should_sell = True
                if should_sell:
                    next_date = price_series.next_date_within(current_date, end_date)
                    if next_date:
                        pending_sale = PendingSale(
                            date=next_date, trigger_date=current_date
                        )
                        print(
                            "[SIMU][SELL-TRIGGER]",
                            ticker,
                            current_date,
                            f"close={close_price:.2f}",
                            (
                                f"avg_ref={drop_reference:.2f}"
                                if drop_reference is not None
                                else "avg_ref=NA"
                            ),
                            f"take_price={take_price:.2f}",
                            f"reason={drop_reason or 'rule'}",
                        )

        # Final valuation at the last available close on/before end_date.
        final_row = price_series.previous_on_or_before(end_date)
        position_value = 0.0
        if shares > 0:
            if final_row:
                position_value = shares * final_row.close
            else:
                print("[SIMU][WARN]", ticker, "open position without final price")
        end_capital = cash + position_value

        start_capital = settings.starting_capital
        growth_pct = 0.0
        if start_capital > 0:
            growth_pct = ((end_capital / start_capital) - 1.0) * 100.0

        print(
            "[SIMU][SUMMARY]",
            ticker,
            f"start={start_capital:.2f}",
            f"end={end_capital:.2f}",
            f"growth={growth_pct:.2f}%",
            f"buy_trades={buy_trades}",
            f"winning_trades={winning_trades}",
            f"losing_trades={losing_trades}",
            f"signals_total={signal_count}",
            f"eligible={eligible_signals}",
        )

        return SimulationResult(
            ticker=ticker,
            start_capital=start_capital,
            end_capital=end_capital,
            end_cash=cash,
            end_position_value=position_value,
            growth_pct=growth_pct,
            buy_trades=buy_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            signals_found=signal_count,
            eligible_signals=eligible_signals,
        )
