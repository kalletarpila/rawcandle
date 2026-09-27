from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from rawcandle.forecasts.contracts import (
    FAMILY_FISCAL_ESTIMATE,
    FAMILY_PRICE_TARGET,
    STATUS_SUCCESS_WITH_DATA,
)
from rawcandle.forecasts.fiscal_linker import (
    AMBIGUOUS,
    LINKED,
    LINK_RULE_VERSION,
    UNRESOLVED,
    ForecastFiscalLinker,
)
from rawcandle.forecasts.identity import (
    IDENTITY_AMBIGUOUS,
    IDENTITY_RESOLVED,
    IDENTITY_UNRESOLVED,
    ForecastIdentityResolver,
)
from rawcandle.forecasts.linking import (
    AS_KNOWN,
    CURRENT_RECONCILED,
    ForecastLinkService,
)
from rawcandle.forecasts.repository import ForecastRepository
from rawcandle.forecasts.schema import connect_forecasts_db, migrate_forecasts_db
from rawcandle.forecasts.transport import YahooRawResult


FIXTURES = Path(__file__).parent / "fixtures" / "forecasts" / "yahoo"


def _fundamentals_db(tmp_path: Path) -> Path:
    path = tmp_path / "fundamentals.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE company(company_id INTEGER PRIMARY KEY,company_key TEXT);
            CREATE TABLE security(
                security_id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL,
                current_ticker TEXT NOT NULL,active INTEGER NOT NULL,
                valid_from TEXT,valid_to TEXT
            );
            CREATE TABLE ticker_alias(
                alias_id INTEGER PRIMARY KEY,security_id INTEGER NOT NULL,
                ticker TEXT NOT NULL,provider TEXT,valid_from TEXT,valid_to TEXT,
                source TEXT NOT NULL
            );
            CREATE TABLE provider_security_identity(
                provider TEXT NOT NULL,provider_security_id TEXT NOT NULL,
                security_id INTEGER NOT NULL,provider_ticker TEXT,source TEXT NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE company_fiscal_calendar_profile(
                company_id INTEGER PRIMARY KEY,typical_fiscal_year_start TEXT,
                chain_status TEXT,break_reason TEXT,source TEXT,source_type TEXT,
                source_name TEXT,source_field TEXT,source_value TEXT,
                bootstrap_status TEXT,created_at_utc TEXT,updated_at_utc TEXT
            );
            CREATE TABLE company_fiscal_year_anchor(
                company_id INTEGER NOT NULL,fiscal_year INTEGER NOT NULL,
                fiscal_year_start TEXT NOT NULL,source TEXT,source_type TEXT,
                source_name TEXT,source_field TEXT,source_value TEXT,
                confidence TEXT NOT NULL,observed_verified INTEGER NOT NULL,
                created_at_utc TEXT NOT NULL
            );
            CREATE TABLE v4_quarter(
                quarter_id INTEGER PRIMARY KEY,company_id INTEGER NOT NULL,
                fiscal_year INTEGER NOT NULL,fiscal_quarter TEXT NOT NULL,
                period_end TEXT NOT NULL,source_fiscalperiod TEXT NOT NULL,
                source_reportperiod TEXT NOT NULL,identity_provider TEXT NOT NULL,
                identity_status TEXT NOT NULL,source_availability_date TEXT,
                first_public_result_date TEXT,created_at_utc TEXT NOT NULL,
                updated_at_utc TEXT NOT NULL
            );
            """
        )
    return path


def _security(
    path: Path,
    *,
    company_id: int = 1,
    security_id: int = 10,
    ticker: str = "TEST",
    valid_from: str | None = None,
    valid_to: str | None = None,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT OR IGNORE INTO company VALUES(?,?)",
            (company_id, f"company-{company_id}"),
        )
        connection.execute(
            "INSERT INTO security VALUES(?,?,?,?,?,?)",
            (security_id, company_id, ticker, 1, valid_from, valid_to),
        )


def _alias(
    path: Path,
    alias_id: int,
    security_id: int,
    ticker: str,
    valid_from: str | None,
    valid_to: str | None,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO ticker_alias VALUES(?,?,?,?,?,?,?)",
            (alias_id, security_id, ticker, "YAHOO_FINANCE", valid_from, valid_to, "fixture"),
        )


def _quarter(
    path: Path,
    quarter_id: int,
    fiscal_year: int,
    fiscal_quarter: str,
    period_end: str,
    public_date: str,
    *,
    company_id: int = 1,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO v4_quarter VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                quarter_id, company_id, fiscal_year, fiscal_quarter, period_end,
                f"{fiscal_year}-{fiscal_quarter}", period_end, "SHARADAR",
                "ACCEPTED", public_date, public_date,
                "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z",
            ),
        )


def _raw(payload: dict, family: str, fetched_at: str) -> YahooRawResult:
    return YahooRawResult(
        requested_at_utc=fetched_at,
        fetched_at_utc=fetched_at,
        provider_symbol="TEST",
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


def test_identity_resolution_precedence_and_alias_validity_as_of(tmp_path: Path) -> None:
    path = _fundamentals_db(tmp_path)
    _security(path, ticker="NEW", valid_from="2025-01-01")
    _alias(path, 1, 10, "OLD", "2020-01-01", "2024-12-31")
    resolver = ForecastIdentityResolver(path)

    old = resolver.resolve("OLD", "2024-06-01T00:00:00Z")
    expired = resolver.resolve("OLD", "2025-06-01T00:00:00Z")
    current = resolver.resolve("NEW", "2025-06-01T00:00:00Z")

    assert (old.identity_status, old.resolution_method, old.security_id) == (
        IDENTITY_RESOLVED, "TICKER_ALIAS_AS_OF", 10,
    )
    assert expired.identity_status == IDENTITY_UNRESOLVED
    assert (current.identity_status, current.resolution_method) == (
        IDENTITY_RESOLVED, "CURRENT_SECURITY_TICKER_AS_OF",
    )

    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO provider_security_identity VALUES(?,?,?,?,?,?)",
            ("YAHOO_FINANCE", "NEW", 10, "NEW", "fixture", "2025-01-01T00:00:00Z"),
        )
    preferred = resolver.resolve("NEW", "2025-06-01T00:00:00Z")
    assert preferred.resolution_method == "PROVIDER_SECURITY_IDENTITY"


def test_identity_ambiguity_does_not_guess(tmp_path: Path) -> None:
    path = _fundamentals_db(tmp_path)
    _security(path, company_id=1, security_id=10, ticker="ONE")
    _security(path, company_id=2, security_id=20, ticker="TWO")
    _alias(path, 1, 10, "DUP", None, None)
    _alias(path, 2, 20, "DUP", None, None)

    result = ForecastIdentityResolver(path).resolve(
        "DUP", "2026-09-27T00:00:00Z"
    )

    assert result.identity_status == IDENTITY_AMBIGUOUS
    assert result.company_id is None
    assert result.evidence["candidate_count"] == 2


def test_quarterly_annual_rollover_and_end_date_support(tmp_path: Path) -> None:
    path = _fundamentals_db(tmp_path)
    _security(path)
    _quarter(path, 1, 2027, "Q3", "2027-06-30", "2027-08-01")
    linker = ForecastFiscalLinker(path)

    q0 = linker.resolve(
        company_id=1, provider_horizon="0q", provider_end_date="2027-09-30",
        acquisition_timestamp_utc="2027-09-01T00:00:00Z",
    )
    q1 = linker.resolve(
        company_id=1, provider_horizon="+1q", provider_end_date="2027-12-31",
        acquisition_timestamp_utc="2027-09-01T00:00:00Z",
    )
    y0 = linker.resolve(
        company_id=1, provider_horizon="0y", provider_end_date="2027-12-31",
        acquisition_timestamp_utc="2027-09-01T00:00:00Z",
    )
    y1 = linker.resolve(
        company_id=1, provider_horizon="+1y", provider_end_date="2028-12-31",
        acquisition_timestamp_utc="2027-09-01T00:00:00Z",
    )

    assert (q0.expected_fiscal_year, q0.expected_fiscal_quarter) == (2027, "Q4")
    assert (q1.expected_fiscal_year, q1.expected_fiscal_quarter) == (2028, "Q1")
    assert "FISCAL_YEAR_ROLLOVER" in q1.reason_codes
    assert (y0.expected_fiscal_year, y1.expected_fiscal_year) == (2027, 2028)
    assert all(item.link_status == LINKED for item in (q0, q1, y0, y1))


def test_non_calendar_52_week_and_adbe_duplicate_end_date_use_sequence(tmp_path: Path) -> None:
    path = _fundamentals_db(tmp_path)
    _security(path, ticker="ADBE")
    _quarter(path, 1, 2026, "Q3", "2026-08-28", "2026-09-15")
    linker = ForecastFiscalLinker(path)

    q0 = linker.resolve(
        company_id=1, provider_horizon="0q", provider_end_date="2026-11-30",
        acquisition_timestamp_utc="2026-09-27T00:00:00Z",
    )
    q1 = linker.resolve(
        company_id=1, provider_horizon="+1q", provider_end_date="2026-11-30",
        acquisition_timestamp_utc="2026-09-27T00:00:00Z",
    )
    y0 = linker.resolve(
        company_id=1, provider_horizon="0y", provider_end_date="2026-11-30",
        acquisition_timestamp_utc="2026-09-27T00:00:00Z",
    )

    assert (q0.expected_fiscal_year, q0.expected_fiscal_quarter) == (2026, "Q4")
    assert (q1.expected_fiscal_year, q1.expected_fiscal_quarter) == (2027, "Q1")
    assert y0.expected_fiscal_year == 2026
    assert q0.evidence["end_date_difference_days"] <= 4
    assert "END_DATE_OUTSIDE_TOLERANCE" in q1.reason_codes


def test_fiscal_linker_unresolved_unsupported_and_ambiguous_context(tmp_path: Path) -> None:
    path = _fundamentals_db(tmp_path)
    _security(path)
    linker = ForecastFiscalLinker(path)
    missing = linker.resolve(
        company_id=1, provider_horizon="0q", provider_end_date="2026-12-31",
        acquisition_timestamp_utc="2026-09-27T00:00:00Z",
    )
    unsupported = linker.resolve(
        company_id=1, provider_horizon="5q", provider_end_date="2026-12-31",
        acquisition_timestamp_utc="2026-09-27T00:00:00Z",
    )
    _quarter(path, 1, 2026, "Q3", "2026-06-30", "2026-08-01")
    _quarter(path, 2, 2026, "Q3", "2026-06-29", "2026-08-01")
    ambiguous = linker.resolve(
        company_id=1, provider_horizon="0q", provider_end_date="2026-09-30",
        acquisition_timestamp_utc="2026-09-27T00:00:00Z",
    )

    assert missing.link_status == UNRESOLVED
    assert missing.reason_codes == ("INSUFFICIENT_FISCAL_CONTEXT",)
    assert unsupported.reason_codes == ("PROVIDER_HORIZON_UNSUPPORTED",)
    assert ambiguous.link_status == AMBIGUOUS


def _persisted_fetch(tmp_path: Path, fundamentals: Path) -> tuple[Path, str]:
    forecast = tmp_path / "forecasts.db"
    migrate_forecasts_db(forecast, applied_at_utc="2026-09-27T09:00:00Z")
    repository = ForecastRepository(forecast, adapter_version="test")
    run_id = repository.start_run(run_id="link-run")
    payload = json.loads(
        (FIXTURES / "success_with_data_aapl.real_compact.json").read_text()
    )
    persisted = repository.record_fetch(
        run_id,
        _raw(payload, FAMILY_FISCAL_ESTIMATE, "2026-09-27T10:00:00Z"),
        company_id=1,
        security_id=10,
    )
    assert persisted.snapshot_id is not None
    with connect_forecasts_db(forecast) as connection:
        fetch_id = connection.execute("SELECT fetch_id FROM forecast_fetch").fetchone()[0]
    return forecast, str(fetch_id)


def test_fetch_level_link_history_reconciliation_and_linked_as_of(tmp_path: Path) -> None:
    fundamentals = _fundamentals_db(tmp_path)
    _security(fundamentals)
    _alias(fundamentals, 1, 10, "TEST", None, None)
    _quarter(fundamentals, 1, 2026, "Q3", "2026-06-27", "2026-07-31")
    forecast, fetch_id = _persisted_fetch(tmp_path, fundamentals)
    service = ForecastLinkService(forecast, fundamentals)

    links = service.link_fetch(fetch_id, linked_at_utc="2026-09-27T10:01:00Z")
    q4 = next(item for item in links if item["provider_horizon"] == "0q")
    assert len(links) == 2
    assert q4["link_rule_version"] == LINK_RULE_VERSION
    assert q4["expected_fiscal_year"] == 2026
    assert q4["expected_fiscal_quarter"] == "Q4"
    assert q4["canonical_quarter_id"] is None

    repeated = service.link_fetch(
        fetch_id, linked_at_utc="2026-09-27T10:02:00Z"
    )
    assert {item["link_id"] for item in repeated} == {
        item["link_id"] for item in links
    }
    with connect_forecasts_db(forecast) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM forecast_fiscal_link"
        ).fetchone()[0] == 2

    as_known = service.linked_as_known_at(
        company_id=1, fiscal_year=2026, fiscal_quarter="Q4",
        timestamp_utc="2026-10-01T00:00:00Z",
    )
    assert len(as_known["matches"]) == 1
    assert as_known["matches"][0]["link"]["canonical_quarter_id"] is None
    assert as_known["matches"][0]["records"]
    annual = service.linked_as_known_at(
        company_id=1, fiscal_year=2026,
        timestamp_utc="2026-10-01T00:00:00Z",
    )
    assert annual["matches"][0]["link"]["target_type"] == "FISCAL_YEAR"

    original_resolution_id = q4["resolution_id"]
    with connect_forecasts_db(forecast) as connection:
        connection.execute(
            """
            INSERT INTO forecast_identity_resolution(
                resolution_id,resolution_hash,fetch_id,provider,provider_symbol,
                acquisition_timestamp_utc,resolved_at_utc,identity_status,
                company_id,security_id,resolution_method,reason_codes_json,
                identity_rule_version,evidence_json
            ) SELECT 'later-resolution','later-resolution-hash',fetch_id,provider,
                     provider_symbol,acquisition_timestamp_utc,
                     '2026-11-19T00:00:00.000000Z',identity_status,99,99,
                     resolution_method,reason_codes_json,identity_rule_version,
                     evidence_json
              FROM forecast_identity_resolution WHERE resolution_id=?
            """,
            (original_resolution_id,),
        )

    _quarter(fundamentals, 2, 2026, "Q4", "2026-09-26", "2026-11-01")
    reconciled = service.reconcile_fetch(
        fetch_id, reconciled_at_utc="2026-11-20T00:00:00Z"
    )
    reconciled_q4 = next(
        item for item in reconciled if item["provider_horizon"] == "0q"
    )
    assert reconciled_q4["canonical_quarter_id"] == 2
    assert reconciled_q4["knowledge_mode"] == CURRENT_RECONCILED
    assert reconciled_q4["resolution_id"] == original_resolution_id

    still_as_known = service.linked_as_known_at(
        company_id=1, fiscal_year=2026, fiscal_quarter="Q4",
        timestamp_utc="2026-10-01T00:00:00Z", knowledge_mode=AS_KNOWN,
    )
    current = service.linked_as_known_at(
        company_id=1, fiscal_year=2026, fiscal_quarter="Q4",
        timestamp_utc="2026-10-01T00:00:00Z",
        knowledge_mode=CURRENT_RECONCILED,
    )
    assert still_as_known["matches"][0]["link"]["canonical_quarter_id"] is None
    assert current["matches"][0]["link"]["canonical_quarter_id"] == 2


def test_lookahead_guard_and_canonical_correction_are_reconcilable(tmp_path: Path) -> None:
    fundamentals = _fundamentals_db(tmp_path)
    _security(fundamentals)
    _alias(fundamentals, 1, 10, "TEST", None, None)
    _quarter(fundamentals, 1, 2026, "Q3", "2026-06-27", "2026-07-31")
    _quarter(fundamentals, 2, 2026, "Q4", "2026-09-26", "2026-11-01")
    forecast, fetch_id = _persisted_fetch(tmp_path, fundamentals)
    service = ForecastLinkService(forecast, fundamentals)

    links = service.link_fetch(fetch_id, linked_at_utc="2026-09-27T10:01:00Z")
    q4 = next(item for item in links if item["provider_horizon"] == "0q")
    assert q4["canonical_quarter_id"] is None
    assert json.loads(q4["evidence_json"])["latest_known_quarter"]["quarter_id"] == 1

    first = service.reconcile_fetch(fetch_id, reconciled_at_utc="2026-11-20T00:00:00Z")
    assert next(item for item in first if item["provider_horizon"] == "0q")[
        "canonical_quarter_id"
    ] == 2
    with sqlite3.connect(fundamentals) as connection:
        connection.execute(
            "UPDATE v4_quarter SET fiscal_year=2027,fiscal_quarter='Q1' WHERE quarter_id=2"
        )
    corrected = service.reconcile_fetch(
        fetch_id, reconciled_at_utc="2026-11-21T00:00:00Z"
    )
    corrected_q4 = next(
        item for item in corrected if item["provider_horizon"] == "0q"
    )
    assert corrected_q4["canonical_quarter_id"] is None
    assert corrected_q4["supersedes_link_id"] is not None


def test_price_targets_cannot_be_fiscal_linked(tmp_path: Path) -> None:
    fundamentals = _fundamentals_db(tmp_path)
    _security(fundamentals)
    _alias(fundamentals, 1, 10, "TEST", None, None)
    forecast = tmp_path / "forecasts.db"
    migrate_forecasts_db(forecast)
    repository = ForecastRepository(forecast, adapter_version="test")
    run_id = repository.start_run(run_id="price-run")
    payload = json.loads((FIXTURES / "price_targets_aapl.real_compact.json").read_text())
    repository.record_fetch(
        run_id, _raw(payload, FAMILY_PRICE_TARGET, "2026-09-27T10:00:00Z"),
        company_id=1, security_id=10,
    )
    with connect_forecasts_db(forecast) as connection:
        fetch_id = str(connection.execute("SELECT fetch_id FROM forecast_fetch").fetchone()[0])

    with pytest.raises(ValueError, match="only fiscal-estimate"):
        ForecastLinkService(forecast, fundamentals).link_fetch(fetch_id)
    with connect_forecasts_db(forecast) as connection:
        assert connection.execute("SELECT COUNT(*) FROM forecast_fiscal_link").fetchone()[0] == 0
