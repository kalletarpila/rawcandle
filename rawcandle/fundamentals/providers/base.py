from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Protocol


@dataclass(frozen=True)
class ProviderObservation:
    provider: str
    provider_record_id: str
    native_table: str
    ticker: str
    provider_security_id: str | None
    observed_period_end: str | None
    provider_fiscal_label: str | None
    source_timestamp: str | None
    source_reference: str | None
    observed_at_utc: str | None
    content_hash: str
    provider_status: str
    fields: Mapping[str, Any]


class ProviderClient(Protocol):
    @property
    def provider_name(self) -> str:
        ...

    def raw_observations(self, native_table: str, records: Iterable[Mapping[str, Any]]) -> list[ProviderObservation]:
        ...
