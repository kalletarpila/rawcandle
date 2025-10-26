from __future__ import annotations

from typing import Iterable, Iterator, List

from .db import AnalysisRepository, PriceRepository
from .engine import SimulationEngine, SimulationRequest, SimulationSettings
from .results import SimulationResult
from .utils import ensure_upper_ticker


class SimulationService:
    """Facade used by the UI layer to execute simulations."""

    def __init__(self) -> None:
        self.analysis_repo = AnalysisRepository()
        self.price_repo = PriceRepository()
        self.engine = SimulationEngine(self.analysis_repo, self.price_repo)

    def run_for_tickers(
        self,
        tickers: Iterable[str],
        settings: SimulationSettings,
    ) -> Iterator[SimulationResult]:
        canonical_tickers: List[str] = []
        for ticker in tickers:
            cleaned = ensure_upper_ticker(ticker)
            if cleaned:
                canonical_tickers.append(cleaned)

        for ticker in canonical_tickers:
            request = SimulationRequest(ticker=ticker, settings=settings)
            yield self.engine.run(request)

    def close(self) -> None:
        self.analysis_repo.close()
        self.price_repo.close()
