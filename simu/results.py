from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationResult:
    ticker: str
    start_capital: float
    end_capital: float
    end_cash: float
    end_position_value: float
    growth_pct: float
    buy_trades: int
    signals_found: int
    eligible_signals: int
    cash_blocked_signals: int = 0

    def as_dict(self) -> dict[str, float | str]:
        return {
            "ticker": self.ticker,
            "start_capital": self.start_capital,
            "end_capital": self.end_capital,
            "end_cash": self.end_cash,
            "end_position_value": self.end_position_value,
            "growth_pct": self.growth_pct,
            "buy_trades": self.buy_trades,
            "signals_found": self.signals_found,
            "eligible_signals": self.eligible_signals,
            "cash_blocked_signals": self.cash_blocked_signals,
        }
