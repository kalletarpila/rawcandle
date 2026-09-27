from __future__ import annotations

import copy
import json
import sqlite3
from pathlib import Path

import pytest
from yfinance.exceptions import YFRateLimitError

from rawcandle.cli.run_forecast_migrations import main as migration_main
from rawcandle.forecasts.contracts import (
    FAMILY_EARNINGS_HISTORY_REFERENCE,
    FAMILY_FISCAL_ESTIMATE,
    FAMILY_PRICE_TARGET,
    STATUS_MALFORMED,
    STATUS_PROVIDER_SYMBOL_UNAVAILABLE,
    STATUS_RATE_LIMITED,
    STATUS_SUCCESS_CHANGED,
    STATUS_SUCCESS_UNCHANGED,
    STATUS_SUCCESS_WITH_DATA,
    STATUS_TRANSIENT_FAILURE,
    STATUS_VALID_NO_DATA,
    canonicalize_earnings_history,
    canonicalize_earnings_trend,
    canonicalize_price_targets,
    parse_payload,
)
from rawcandle.forecasts.repository import ForecastRepository
from rawcandle.forecasts.schema import SCHEMA_VERSION, connect_forecasts_db, migrate_forecasts_db
from rawcandle.forecasts.transport import (
    YahooForecastTransport,
    YahooRawResult,
    YahooRequestLimiter,
    YahooTransportConfig,
)
from tests.yahoo_forecast_contract import canonicalize as reference_canonicalize
from tests.yahoo_forecast_contract import semantic_hash as reference_hash


FIXTURES = Path(__file__).parent / "fixtures" / "forecasts" / "yahoo"


def fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def raw_result(
    payload: dict | None,
    *,
    family: str = FAMILY_FISCAL_ESTIMATE,
    status: str = STATUS_SUCCESS_WITH_DATA,
    fetched_at: str = "2026-09-27T10:00:00Z",
    raw_hash: str = "raw-1",
) -> YahooRawResult:
    return YahooRawResult(
        requested_at_utc=fetched_at,
        fetched_at_utc=fetched_at,
        provider_symbol="AAPL",
        forecast_family=family,
        http_status=200 if status in {STATUS_SUCCESS_WITH_DATA, STATUS_VALID_NO_DATA} else None,
        status=status,
        success=status in {STATUS_SUCCESS_WITH_DATA, STATUS_VALID_NO_DATA},
        error_class=None if status in {STATUS_SUCCESS_WITH_DATA, STATUS_VALID_NO_DATA} else status,
        error_code=None,
        error_message=None,
        raw_payload=payload,
        raw_body=(
            json.dumps(payload, separators=(",", ":")) if payload is not None else None
        ),
        raw_hash=raw_hash,
        attempt_count=1,
    )


def repository(tmp_path: Path) -> tuple[ForecastRepository, Path]:
    path = tmp_path / "forecasts.db"
    migrate_forecasts_db(path, applied_at_utc="2026-09-27T09:00:00Z")
    return ForecastRepository(path, adapter_version="0.2.66"), path


def test_production_earnings_parser_matches_frozen_reference() -> None:
    payload = fixture("success_with_data_aapl.real_compact.json")
    production = canonicalize_earnings_trend(payload)

    assert production.payload == reference_canonicalize(payload)
    assert production.content_hash == reference_hash(payload)


def test_production_canonicalization_reports_drift_and_preserves_hash_rules() -> None:
    payload = fixture("success_with_data_aapl.real_compact.json")
    formatting_only = copy.deepcopy(payload)
    formatting_only["quoteSummary"]["result"][0]["earningsTrend"]["trend"][0][
        "growth"
    ]["fmt"] = "changed formatting"
    formatting_only["quoteSummary"]["result"][0]["earningsTrend"]["newField"] = 1

    first = canonicalize_earnings_trend(payload)
    second = canonicalize_earnings_trend(formatting_only)

    assert first.content_hash == second.content_hash
    assert second.schema_drift == ("earningsTrend.newField",)


def test_production_family_parsers_cover_no_data_and_secondary_families() -> None:
    no_data = fixture("result_cases.synthetic.json")["cases"][0]["payload"]
    price = canonicalize_price_targets(fixture("price_targets_aapl.real_compact.json"))
    history = canonicalize_earnings_history(
        fixture("earnings_history_aapl.real_compact.json")
    )

    assert parse_payload(FAMILY_FISCAL_ESTIMATE, no_data).status == STATUS_VALID_NO_DATA
    assert price.payload["values"]["median"]["value"] == "340"
    assert history.payload["rows"][0]["providerQuarterDate"] == "2026-06-30"
    assert history.payload["rows"][0]["epsActual"]["value"] == "2.02"


class Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload, separators=(",", ":"))

    def json(self) -> object:
        return self._payload


def transport(requester, *, max_retries: int = 0, sleeper=lambda _: None):
    return YahooForecastTransport(
        config=YahooTransportConfig(
            max_retries=max_retries,
            retry_backoff_seconds=0.01,
            minimum_interval_seconds=0,
        ),
        requester=requester,
        sleeper=sleeper,
        limiter=YahooRequestLimiter(0),
        now=lambda: "2026-09-27T10:00:00Z",
    )


@pytest.mark.parametrize(
    ("case_name", "expected"),
    [
        ("VALID_NO_DATA", STATUS_VALID_NO_DATA),
        ("PROVIDER_SYMBOL_UNAVAILABLE", STATUS_PROVIDER_SYMBOL_UNAVAILABLE),
        ("TRANSIENT_5XX", STATUS_TRANSIENT_FAILURE),
        ("MALFORMED_OR_SCHEMA_MISMATCH", STATUS_MALFORMED),
    ],
)
def test_transport_classifies_raw_results(case_name: str, expected: str) -> None:
    case = next(
        item
        for item in fixture("result_cases.synthetic.json")["cases"]
        if item["name"] == case_name
    )
    status = int(case["transport"]["http_status"])
    payload = case["payload"]
    result = transport(lambda *_: Response(status, payload)).fetch(
        "AAPL", FAMILY_FISCAL_ESTIMATE
    )

    assert result.status == expected
    assert result.http_status == status
    assert result.attempt_count == 1


def test_transport_retries_rate_limit_then_succeeds() -> None:
    calls = []
    sleeps = []
    payload = fixture("success_with_data_aapl.real_compact.json")

    def requester(*_):
        calls.append(1)
        if len(calls) == 1:
            raise YFRateLimitError()
        return Response(200, payload)

    result = transport(requester, max_retries=1, sleeper=sleeps.append).fetch(
        "AAPL", FAMILY_FISCAL_ESTIMATE
    )

    assert result.status == STATUS_SUCCESS_WITH_DATA
    assert result.attempt_count == 2
    assert sleeps == [0.01]


def test_transport_terminal_rate_limit_is_distinct() -> None:
    result = transport(lambda *_: (_ for _ in ()).throw(YFRateLimitError())).fetch(
        "AAPL", FAMILY_FISCAL_ESTIMATE
    )

    assert result.status == STATUS_RATE_LIMITED
    assert result.http_status == 429


def test_non_json_provider_body_survives_into_raw_evidence(tmp_path: Path) -> None:
    class NonJsonResponse:
        status_code = 502
        text = "upstream unavailable"

        def json(self):
            raise ValueError("not json")

    result = transport(lambda *_: NonJsonResponse()).fetch(
        "AAPL", FAMILY_FISCAL_ESTIMATE
    )
    repo, path = repository(tmp_path)
    run = repo.start_run(run_id="raw-error-run")

    persisted = repo.record_fetch(run, result, security_id=7)

    assert persisted.status == STATUS_TRANSIENT_FAILURE
    assert result.raw_body == "upstream unavailable"
    with connect_forecasts_db(path) as connection:
        body = connection.execute(
            "SELECT body_text FROM forecast_raw_evidence"
        ).fetchone()[0]
    assert body == "upstream unavailable"


def test_migration_creates_forecast_schema_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "forecasts.db"
    migrate_forecasts_db(path, applied_at_utc="2026-09-27T09:00:00Z")
    migrate_forecasts_db(path, applied_at_utc="2026-09-27T09:01:00Z")

    with connect_forecasts_db(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        version = connection.execute(
            "SELECT version FROM forecast_schema_version WHERE db_name='forecasts'"
        ).fetchone()[0]

    assert version == SCHEMA_VERSION
    assert {
        "forecast_run", "forecast_fetch", "forecast_snapshot", "forecast_estimate",
        "forecast_price_target", "forecast_earnings_history_reference",
        "forecast_raw_evidence",
    } <= tables


def test_migration_cli_requires_explicit_target(tmp_path: Path) -> None:
    path = tmp_path / "cli-forecasts.db"

    assert migration_main(["--db", str(path)]) == 0
    assert path.exists()


def test_change_only_history_failure_no_data_and_as_of_queries(tmp_path: Path) -> None:
    repo, path = repository(tmp_path)
    payload = fixture("success_with_data_aapl.real_compact.json")
    run = repo.start_run(run_id="run-1", started_at_utc="2026-09-27T09:00:00Z")

    changed = repo.record_fetch(
        run, raw_result(payload, fetched_at="2026-09-27T10:00:00Z", raw_hash="raw-a"),
        company_id=7, security_id=7,
    )
    unchanged = repo.record_fetch(
        run, raw_result(payload, fetched_at="2026-09-27T11:00:00Z", raw_hash="raw-a"),
        company_id=7, security_id=7,
    )
    failure = repo.record_fetch(
        run,
        raw_result(
            None, status=STATUS_TRANSIENT_FAILURE,
            fetched_at="2026-09-27T12:00:00Z", raw_hash="",
        ),
        company_id=7, security_id=7,
    )
    revised = copy.deepcopy(payload)
    revised["quoteSummary"]["result"][0]["earningsTrend"]["trend"][0][
        "earningsEstimate"
    ]["avg"]["raw"] = 2.0
    second_change = repo.record_fetch(
        run, raw_result(revised, fetched_at="2026-09-27T13:00:00Z", raw_hash="raw-b"),
        company_id=7, security_id=7,
    )

    assert changed.status == STATUS_SUCCESS_CHANGED
    assert unchanged.status == STATUS_SUCCESS_UNCHANGED
    assert unchanged.snapshot_id == changed.snapshot_id
    assert failure.status == STATUS_TRANSIENT_FAILURE
    assert second_change.status == STATUS_SUCCESS_CHANGED
    assert second_change.snapshot_id != changed.snapshot_id
    assert repo.as_known_at(
        forecast_family=FAMILY_FISCAL_ESTIMATE,
        timestamp_utc="2026-09-27T09:59:59Z", provider_symbol="AAPL",
        company_id=7, security_id=7,
    ) is None
    between = repo.as_known_at(
        forecast_family=FAMILY_FISCAL_ESTIMATE,
        timestamp_utc="2026-09-27T12:30:00Z", provider_symbol="AAPL",
        company_id=7, security_id=7,
    )
    assert between["snapshot"]["snapshot_id"] == changed.snapshot_id
    after = repo.as_known_at(
        forecast_family=FAMILY_FISCAL_ESTIMATE,
        timestamp_utc="2026-09-27T14:00:00Z", provider_symbol="AAPL",
        company_id=7, security_id=7,
    )
    assert after["snapshot"]["snapshot_id"] == second_change.snapshot_id

    no_data_payload = fixture("result_cases.synthetic.json")["cases"][0]["payload"]
    no_data = repo.record_fetch(
        run,
        raw_result(
            no_data_payload, status=STATUS_VALID_NO_DATA,
            fetched_at="2026-09-27T15:00:00Z", raw_hash="raw-empty",
        ),
        company_id=7, security_id=7,
    )
    known_empty = repo.as_known_at(
        forecast_family=FAMILY_FISCAL_ESTIMATE,
        timestamp_utc="2026-09-27T16:00:00Z", provider_symbol="AAPL",
        company_id=7, security_id=7,
    )
    assert no_data.status == STATUS_VALID_NO_DATA
    assert known_empty["fetch"]["status"] == STATUS_VALID_NO_DATA
    assert known_empty["snapshot"] is None

    with connect_forecasts_db(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forecast_fetch").fetchone()[0] == 5
        assert connection.execute("SELECT COUNT(*) FROM forecast_snapshot").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM forecast_raw_evidence").fetchone()[0] == 3


def test_price_target_change_only_history(tmp_path: Path) -> None:
    repo, path = repository(tmp_path)
    payload = fixture("price_targets_aapl.real_compact.json")
    run = repo.start_run(run_id="price-run")

    first = repo.record_fetch(
        run, raw_result(payload, family=FAMILY_PRICE_TARGET, raw_hash="price-a"),
        security_id=7,
    )
    same = repo.record_fetch(
        run,
        raw_result(
            payload, family=FAMILY_PRICE_TARGET, raw_hash="price-a",
            fetched_at="2026-09-27T11:00:00Z",
        ),
        security_id=7,
    )
    revised = copy.deepcopy(payload)
    revised["quoteSummary"]["result"][0]["financialData"]["targetMeanPrice"] = 330.0
    second = repo.record_fetch(
        run,
        raw_result(
            revised, family=FAMILY_PRICE_TARGET, raw_hash="price-b",
            fetched_at="2026-09-27T12:00:00Z",
        ),
        security_id=7,
    )

    assert (first.status, same.status, second.status) == (
        STATUS_SUCCESS_CHANGED, STATUS_SUCCESS_UNCHANGED, STATUS_SUCCESS_CHANGED,
    )
    with connect_forecasts_db(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forecast_snapshot").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM forecast_price_target").fetchone()[0] == 10


def test_earnings_history_is_persisted_as_provider_reference(tmp_path: Path) -> None:
    repo, path = repository(tmp_path)
    payload = fixture("earnings_history_aapl.real_compact.json")
    run = repo.start_run(run_id="history-run")

    persisted = repo.record_fetch(
        run,
        raw_result(
            payload, family=FAMILY_EARNINGS_HISTORY_REFERENCE,
            raw_hash="history-a",
        ),
        company_id=7,
        security_id=7,
    )

    assert persisted.status == STATUS_SUCCESS_CHANGED
    with connect_forecasts_db(path) as connection:
        row = connection.execute(
            "SELECT * FROM forecast_earnings_history_reference"
        ).fetchone()
    assert row["authority"] == "YAHOO_PROVIDER_REFERENCE"
    assert row["provider_quarter_date"] == "2026-06-30"
    assert row["eps_actual"] == "2.02"


def test_database_constraints_reject_invalid_fetch_status(tmp_path: Path) -> None:
    repo, path = repository(tmp_path)
    repo.start_run(run_id="constraint-run")

    with connect_forecasts_db(path) as connection, pytest.raises(sqlite3.IntegrityError):
        connection.execute(
            """
            INSERT INTO forecast_fetch(
                fetch_id,run_id,provider,adapter,adapter_version,identity_key,
                provider_symbol,forecast_family,requested_at_utc,fetched_at_utc,
                status,attempt_count
            ) VALUES('bad','constraint-run','YAHOO_FINANCE','yfinance','x',
                     'symbol:AAPL','AAPL','PRICE_TARGET','x','x','NOT_A_STATUS',1)
            """
        )
