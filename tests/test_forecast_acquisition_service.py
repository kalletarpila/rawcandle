from __future__ import annotations

import json
from pathlib import Path

from rawcandle.forecasts.contracts import (
    FAMILY_EARNINGS_HISTORY_REFERENCE,
    FAMILY_FISCAL_ESTIMATE,
    FAMILY_PRICE_TARGET,
    STATUS_SUCCESS_CHANGED,
    STATUS_SUCCESS_WITH_DATA,
)
from rawcandle.forecasts.repository import ForecastRepository
from rawcandle.forecasts.schema import connect_forecasts_db, migrate_forecasts_db
from rawcandle.forecasts.service import ForecastAcquisitionService
from rawcandle.forecasts.transport import YahooRawResult


FIXTURES = Path(__file__).parent / "fixtures" / "forecasts" / "yahoo"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_collect_symbol_persists_selected_families_without_scheduler(
    tmp_path: Path,
) -> None:
    path = tmp_path / "forecasts.db"
    migrate_forecasts_db(path)
    repository = ForecastRepository(path, adapter_version="0.2.66")
    run_id = repository.start_run(run_id="service-run")
    payloads = {
        FAMILY_FISCAL_ESTIMATE: _fixture("success_with_data_aapl.real_compact.json"),
        FAMILY_PRICE_TARGET: _fixture("price_targets_aapl.real_compact.json"),
        FAMILY_EARNINGS_HISTORY_REFERENCE: _fixture(
            "earnings_history_aapl.real_compact.json"
        ),
    }

    class FakeTransport:
        def fetch(self, provider_symbol: str, family: str) -> YahooRawResult:
            payload = payloads[family]
            return YahooRawResult(
                requested_at_utc="2026-09-27T10:00:00Z",
                fetched_at_utc="2026-09-27T10:00:01Z",
                provider_symbol=provider_symbol,
                forecast_family=family,
                http_status=200,
                status=STATUS_SUCCESS_WITH_DATA,
                success=True,
                error_class=None,
                error_code=None,
                error_message=None,
                raw_payload=payload,
                raw_body=json.dumps(payload, separators=(",", ":")),
                raw_hash=f"raw-{family}",
                attempt_count=1,
            )

    service = ForecastAcquisitionService(FakeTransport(), repository)
    persisted = service.collect_symbol(
        run_id=run_id,
        provider_symbol="AAPL",
        company_id=7,
        security_id=7,
    )

    assert [item.status for item in persisted] == [STATUS_SUCCESS_CHANGED] * 3
    with connect_forecasts_db(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forecast_fetch").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM forecast_snapshot").fetchone()[0] == 3
