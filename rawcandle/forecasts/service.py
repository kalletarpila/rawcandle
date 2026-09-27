from __future__ import annotations

from collections.abc import Iterable

from rawcandle.forecasts.contracts import FORECAST_FAMILIES
from rawcandle.forecasts.repository import ForecastRepository, PersistedFetch
from rawcandle.forecasts.transport import YahooForecastTransport


class ForecastAcquisitionService:
    """Collect selected families without owning scheduling or universe scope."""

    def __init__(
        self,
        transport: YahooForecastTransport,
        repository: ForecastRepository,
    ) -> None:
        self.transport = transport
        self.repository = repository

    def collect_symbol(
        self,
        *,
        run_id: str,
        provider_symbol: str,
        families: Iterable[str] = FORECAST_FAMILIES,
        company_id: int | None = None,
        security_id: int | None = None,
    ) -> tuple[PersistedFetch, ...]:
        results = []
        for family in families:
            raw_result = self.transport.fetch(provider_symbol, family)
            results.append(
                self.repository.record_fetch(
                    run_id,
                    raw_result,
                    company_id=company_id,
                    security_id=security_id,
                )
            )
        return tuple(results)
