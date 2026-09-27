from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from rawcandle.cli.forecasts import main
from rawcandle.forecasts.contracts import (
    FAMILY_EARNINGS_HISTORY_REFERENCE,
    FAMILY_FISCAL_ESTIMATE,
    FAMILY_PRICE_TARGET,
    STATUS_SUCCESS_WITH_DATA,
    STATUS_TRANSIENT_FAILURE,
)
from rawcandle.forecasts.operator import (
    acquire_run,
    end_date_statistics,
    link_run,
    migrate_database,
    reconcile_run,
    report_run,
)
from rawcandle.forecasts.schema import SCHEMA_VERSION, connect_forecasts_db
from rawcandle.forecasts.transport import YahooRawResult, YahooTransportConfig
from tests.test_forecast_fiscal_linker_v1 import _alias, _fundamentals_db, _quarter, _security


FIXTURES = Path(__file__).parent / "fixtures" / "forecasts" / "yahoo"


class FakeTransport:
    config = YahooTransportConfig(
        max_retries=0, minimum_interval_seconds=0, raw_retention_days=30
    )

    def __init__(self, *, fail: tuple[str, str] | None = None) -> None:
        self.fail = fail
        self.calls: list[tuple[str, str]] = []

    def fetch(self, symbol: str, family: str) -> YahooRawResult:
        self.calls.append((symbol, family))
        failed = self.fail == (symbol, family)
        names = {
            FAMILY_FISCAL_ESTIMATE: "success_with_data_aapl.real_compact.json",
            FAMILY_PRICE_TARGET: "price_targets_aapl.real_compact.json",
            FAMILY_EARNINGS_HISTORY_REFERENCE: "earnings_history_aapl.real_compact.json",
        }
        payload = None if failed else json.loads((FIXTURES / names[family]).read_text())
        status = STATUS_TRANSIENT_FAILURE if failed else STATUS_SUCCESS_WITH_DATA
        return YahooRawResult(
            requested_at_utc="2026-09-27T10:00:00Z",
            fetched_at_utc="2026-09-27T10:00:00Z",
            provider_symbol=symbol,
            forecast_family=family,
            http_status=None if failed else 200,
            status=status,
            success=not failed,
            error_class=STATUS_TRANSIENT_FAILURE if failed else None,
            error_code="FIXTURE_FAILURE" if failed else None,
            error_message="fixture failure" if failed else None,
            raw_payload=payload,
            raw_body=json.dumps(payload, separators=(",", ":")) if payload else None,
            raw_hash=f"raw-{symbol}-{family}" if payload else None,
            attempt_count=2 if failed else 1,
        )


def _fundamentals(tmp_path: Path) -> Path:
    path = _fundamentals_db(tmp_path)
    _security(path, ticker="TEST")
    _alias(path, 1, 10, "TEST", None, None)
    _quarter(path, 1, 2026, "Q3", "2026-06-27", "2026-07-31")
    return path


def test_cli_migration_is_explicit_verified_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "forecasts.db"

    assert main(["migrate", "--db", str(path)]) == 0
    assert main(["migrate", "--db", str(path)]) == 0

    with connect_forecasts_db(path) as connection:
        version = connection.execute(
            "SELECT version FROM forecast_schema_version"
        ).fetchone()[0]
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
    assert version == SCHEMA_VERSION


def test_migration_refuses_unrelated_or_protected_database(tmp_path: Path) -> None:
    unrelated = tmp_path / "other.db"
    with sqlite3.connect(unrelated) as connection:
        connection.execute("CREATE TABLE unrelated(value TEXT)")

    assert main(["migrate", "--db", str(unrelated)]) == 1
    assert main(["migrate", "--db", str(tmp_path / "fundamentals_v4.db")]) == 1


def test_operator_scope_partial_failure_link_reconcile_and_report(tmp_path: Path) -> None:
    forecast = tmp_path / "forecasts.db"
    fundamentals = _fundamentals(tmp_path)
    fundamentals_before = hashlib.sha256(fundamentals.read_bytes()).hexdigest()
    migrate_database(forecast)
    transport = FakeTransport(fail=("BAD", FAMILY_PRICE_TARGET))

    outcome = acquire_run(
        forecast_db=forecast,
        fundamentals_db=fundamentals,
        symbols=["test", "BAD", "TEST"],
        transport=transport,
        run_id="operator-run",
    )

    assert outcome.symbols == ("TEST", "BAD")
    assert len(transport.calls) == 6
    assert outcome.counters == {"SUCCESS_CHANGED": 5, "TRANSIENT_FAILURE": 1}
    link_counts = link_run(
        outcome.run_id, forecast_db=forecast, fundamentals_db=fundamentals
    )
    assert link_counts == {"LINKED": 2, "UNRESOLVED": 2}
    reconcile_counts = reconcile_run(
        outcome.run_id, forecast_db=forecast, fundamentals_db=fundamentals
    )
    assert reconcile_counts["CANONICAL_QUARTER_NOT_YET_AVAILABLE"] == 1
    assert reconcile_counts["ANNUAL_TARGET"] == 1
    assert hashlib.sha256(fundamentals.read_bytes()).hexdigest() == fundamentals_before

    report = report_run(outcome.run_id, forecast_db=forecast)
    assert report["symbols_attempted"] == 2
    assert report["family_fetches_attempted"] == 6
    assert report["acquisition"]["TRANSIENT_FAILURE"] == 1
    assert report["acquisition_by_family"][FAMILY_PRICE_TARGET] == {
        "SUCCESS_CHANGED": 1, "TRANSIENT_FAILURE": 1,
    }
    assert report["identity"] == {"TICKER_ALIAS_AS_OF": 1, "UNRESOLVED": 1}
    assert report["fiscal_link"] == {"LINKED": 2, "UNRESOLVED": 2}
    assert report["provider_quality"]["retry_count"] == 1
    assert report["provider_quality"]["raw_evidence_retained"] == 5
    assert len(report["annual_mappings"]) == 2
    assert report["end_date"]["count"] == 2

    with connect_forecasts_db(forecast) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forecast_price_target").fetchone()[0] == 5
        assert connection.execute(
            "SELECT COUNT(*) FROM forecast_earnings_history_reference"
        ).fetchone()[0] == 2


def test_repeated_unchanged_acquisition_does_not_duplicate_snapshots(tmp_path: Path) -> None:
    forecast = tmp_path / "forecasts.db"
    fundamentals = _fundamentals(tmp_path)
    migrate_database(forecast)

    first = acquire_run(
        forecast_db=forecast, fundamentals_db=fundamentals, symbols=["TEST"],
        transport=FakeTransport(), run_id="first-run",
    )
    second = acquire_run(
        forecast_db=forecast, fundamentals_db=fundamentals, symbols=["TEST"],
        transport=FakeTransport(), run_id="second-run",
    )

    assert first.counters == {"SUCCESS_CHANGED": 3}
    assert second.counters == {"SUCCESS_UNCHANGED": 3}
    with connect_forecasts_db(forecast) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forecast_snapshot").fetchone()[0] == 3
        assert connection.execute("SELECT COUNT(*) FROM forecast_fetch").fetchone()[0] == 6


def test_end_date_distribution_uses_absolute_nearest_rank_statistics() -> None:
    assert end_date_statistics([-1, 10, 46, 90]) == {
        "count": 4,
        "within_45d": 2,
        "outside_45d": 2,
        "median_abs_diff": 10,
        "p90_abs_diff": 90,
        "max_abs_diff": 90,
    }
