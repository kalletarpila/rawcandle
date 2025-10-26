from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SimulationResult:
    ticker: str
    start_capital: float
    end_capital: float
    growth_pct: float
    buy_trades: int

    def as_dict(self) -> dict[str, float | str]:
        return {
            "ticker": self.ticker,
            "start_capital": self.start_capital,
            "end_capital": self.end_capital,
            "growth_pct": self.growth_pct,
            "buy_trades": self.buy_trades,
        }

