from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from rawcandle.fundamentals.result_publication_daily_research import YahooEvent
from rawcandle.fundamentals.result_publication_daily_research_service import (
    HEURISTIC_RESEARCH_WARNING,
    DailyResearchPublicationService,
    MappingV2CandidateProvider,
    MappingYahooObservationProvider,
    QuarterKey,
    QuarterNotFoundError,
)


DATES = (
    "2026-01-20",
    "2026-01-21",
    "2026-01-22",
    "2026-01-23",
    "2026-01-26",
    "2026-01-27",
)


class TrackingYahooProvider:
    def __init__(self, events: dict[QuarterKey, tuple[YahooEvent, ...]], *, fail: bool = False) -> None:
        self.events = events
        self.fail = fail
        self.calls: list[tuple[QuarterKey, str, str]] = []

    def get_events(self, key: QuarterKey, ticker: str, period_end: str) -> tuple[YahooEvent, ...]:
        self.calls.append((key, ticker, period_end))
        if self.fail:
            raise RuntimeError("offline")
        return self.events.get(key, ())


def _databases(tmp_path: Path) -> tuple[Path, Path]:
    canonical = tmp_path / "canonical.db"
    ohlc = tmp_path / "osakedata.db"
    with sqlite3.connect(canonical) as connection:
        connection.executescript(
            """
            CREATE TABLE v4_quarter(
                quarter_id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                fiscal_year INTEGER NOT NULL,
                fiscal_quarter TEXT NOT NULL,
                period_end TEXT NOT NULL
            );
            CREATE TABLE v4_result_publication_authority(
                company_id INTEGER NOT NULL,
                fiscal_year INTEGER NOT NULL,
                fiscal_quarter TEXT NOT NULL,
                quarter_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                result_publication_timestamp_utc TEXT,
                result_publication_evidence_reference TEXT,
                selected_evidence_id TEXT,
                PRIMARY KEY(company_id,fiscal_year,fiscal_quarter)
            );
            CREATE TABLE v4_result_publication_evidence(
                evidence_id TEXT PRIMARY KEY,
                company_id INTEGER NOT NULL,
                fiscal_year INTEGER NOT NULL,
                fiscal_quarter TEXT NOT NULL,
                source_type TEXT NOT NULL,
                source_timestamp_utc TEXT NOT NULL,
                source_reference TEXT NOT NULL,
                accession_number TEXT,
                disposition TEXT NOT NULL
            );
            CREATE TABLE security(
                security_id INTEGER PRIMARY KEY,
                company_id INTEGER NOT NULL,
                current_ticker TEXT NOT NULL,
                active INTEGER NOT NULL
            );
            """
        )
        rows = [
            (1, "VERIFIED", "2026-01-20T13:00:00Z"),
            (2, "AMBIGUOUS", None),
            (3, "AMBIGUOUS", None),
            (4, "AMBIGUOUS", None),
            (5, "AMBIGUOUS", None),
            (6, "UNRESOLVED", None),
            (7, "NOT_FOUND", None),
            (8, "AMBIGUOUS", None),
            (10, "AMBIGUOUS", None),
        ]
        for company_id, status, timestamp in rows:
            connection.execute(
                "INSERT INTO v4_quarter VALUES(?,?,?,?,?)",
                (company_id, company_id, 2025, "Q4", "2025-12-31"),
            )
            connection.execute(
                "INSERT INTO v4_result_publication_authority VALUES(?,?,?,?,?,?,?,?)",
                (
                    company_id,
                    2025,
                    "Q4",
                    company_id,
                    status,
                    timestamp,
                    f"https://example.test/canonical-{company_id}" if timestamp else None,
                    f"e{company_id}a" if timestamp else None,
                ),
            )
            connection.execute(
                "INSERT INTO security VALUES(?,?,?,?)",
                (company_id, company_id, f"T{company_id}", 1),
            )

        evidence = {
            1: (("a", "2026-01-20T13:00:00Z"),),
            2: (("a", "2026-01-20T22:00:00Z"), ("b", "2026-01-21T13:00:00Z")),
            3: (("a", "2026-01-20T22:00:00Z"), ("b", "2026-01-23T22:00:00Z")),
            4: (("a", "2026-01-20T22:00:00Z"), ("b", "2026-01-23T22:00:00Z")),
            5: (("a", "2026-01-20T22:00:00Z"), ("b", "2026-01-23T22:00:00Z")),
            8: (("a", "2026-01-20T22:00:00Z"), ("b", "2026-01-23T22:00:00Z")),
            10: (("a", "2026-01-21T13:00:00Z"),),
        }
        for company_id, values in evidence.items():
            for suffix, timestamp in values:
                evidence_id = f"e{company_id}{suffix}"
                connection.execute(
                    "INSERT INTO v4_result_publication_evidence VALUES(?,?,?,?,?,?,?,?,?)",
                    (
                        evidence_id,
                        company_id,
                        2025,
                        "Q4",
                        "SEC_8K_ITEM_2_02",
                        timestamp,
                        f"https://example.test/{evidence_id}",
                        f"acc-{company_id}-{suffix}",
                        "ACCEPTED" if company_id == 1 else "CONFLICT",
                    ),
                )
    with sqlite3.connect(ohlc) as connection:
        connection.execute("CREATE TABLE osakedata(osake TEXT,pvm TEXT)")
        for company_id in range(1, 8):
            connection.executemany(
                "INSERT INTO osakedata VALUES(?,?)",
                [(f"T{company_id}", value) for value in DATES],
            )
        connection.executemany(
            "INSERT INTO osakedata VALUES(?,?)",
            [("T10", value) for value in DATES],
        )
        connection.executemany(
            "INSERT INTO osakedata VALUES(?,?)",
            [("T10B", value) for value in DATES if value != "2026-01-21"],
        )
        connection.execute("CREATE UNIQUE INDEX idx_osake_pvm ON osakedata(osake,pvm)")
    with sqlite3.connect(canonical) as connection:
        connection.execute("INSERT INTO security VALUES(?,?,?,?)", (110, 10, "T10B", 1))
    return canonical, ohlc


def _service(
    tmp_path: Path,
    *,
    yahoo_provider: object | None = None,
    v2_provider: object | None = None,
) -> DailyResearchPublicationService:
    canonical, ohlc = _databases(tmp_path)
    return DailyResearchPublicationService(
        canonical,
        ohlc,
        yahoo_provider=yahoo_provider,  # type: ignore[arg-type]
        v2_provider=v2_provider,  # type: ignore[arg-type]
    )


def test_verified_is_exact_without_yahoo_or_v2_call(tmp_path: Path) -> None:
    provider = TrackingYahooProvider({})
    with _service(tmp_path, yahoo_provider=provider) as service:
        result = service.get_daily_research_result(1, 2025, "Q4")
    assert result.result.research_status == "EXACT"
    assert result.is_canonical is True
    assert result.warning is None
    assert result.yahoo_status == "SKIPPED_EXACT"
    assert provider.calls == []


def test_ambiguous_same_effective_day_preserves_unselected_timestamp(tmp_path: Path) -> None:
    with _service(tmp_path) as service:
        result = service.get_daily_research_result(2, 2025, "Q4")
    assert result.result.research_method == "ALL_CANDIDATES_SAME_EFFECTIVE_DAY"
    assert result.result.first_full_post_result_trading_date == "2026-01-21"
    assert result.result.selected_candidate_timestamp_utc is None


def test_yahoo_near_unique_selects_existing_sec_candidate_and_exposes_warning(tmp_path: Path) -> None:
    key = QuarterKey(3, 2025, "Q4")
    yahoo = MappingYahooObservationProvider({key: ["2026-01-20T16:00:00-05:00"]})
    with _service(tmp_path, yahoo_provider=yahoo) as service:
        result = service.get_daily_research_result(3, 2025, "Q4")
    assert result.result.research_method == "YAHOO_NEAR_UNIQUE_SEC"
    assert result.result.selected_candidate_reference == "https://example.test/e3a"
    assert result.warning == HEURISTIC_RESEARCH_WARNING
    assert result.to_dict()["is_canonical"] is False


def test_optional_v2_candidate_precedes_yahoo(tmp_path: Path) -> None:
    key = QuarterKey(4, 2025, "Q4")
    yahoo = MappingYahooObservationProvider({key: ["2026-01-23T16:00:00-05:00"]})
    v2 = MappingV2CandidateProvider({key: "acc-4-a"})
    with _service(tmp_path, yahoo_provider=yahoo, v2_provider=v2) as service:
        result = service.get_daily_research_result(4, 2025, "Q4")
    assert result.result.research_method == "SEC_V2_STRONG_INITIAL"
    assert result.result.selected_candidate_reference == "https://example.test/e4a"
    assert result.v2_candidate_id == "acc-4-a"


def test_yahoo_failure_degrades_to_existing_sec_only_behavior(tmp_path: Path) -> None:
    provider = TrackingYahooProvider({}, fail=True)
    with _service(tmp_path, yahoo_provider=provider) as service:
        result = service.get_daily_research_result(5, 2025, "Q4")
    assert result.result.research_status == "UNUSABLE"
    assert result.result.research_method == "SEC_CANDIDATES_TOO_DISPERSED"
    assert result.yahoo_status == "ERROR:RuntimeError"


@pytest.mark.parametrize("company_id,status", [(6, "UNRESOLVED"), (7, "NOT_FOUND")])
def test_no_sec_candidates_remain_unusable(tmp_path: Path, company_id: int, status: str) -> None:
    provider = TrackingYahooProvider(
        {QuarterKey(company_id, 2025, "Q4"): (YahooEvent("2026-01-20T16:00:00-05:00"),)}
    )
    with _service(tmp_path, yahoo_provider=provider) as service:
        result = service.get_daily_research_result(company_id, 2025, "Q4")
    assert result.result.canonical_authority_status == status
    assert result.result.research_method == "NO_SEC_CANDIDATE"
    assert result.result.research_status == "UNUSABLE"
    assert result.yahoo_status == "SKIPPED_NO_SEC_CANDIDATE"
    assert provider.calls == []


def test_missing_ohlc_calendar_is_explicit_and_ticker_identity_is_preserved(tmp_path: Path) -> None:
    with _service(tmp_path) as service:
        result = service.get_daily_research_result(8, 2025, "Q4")
    assert result.tickers == ("T8",)
    assert result.calendar_status == "UNAVAILABLE"
    assert result.result.research_method == "OHLC_CALENDAR_UNAVAILABLE"


def test_multiple_ticker_calendar_disagreement_never_guesses(tmp_path: Path) -> None:
    with _service(tmp_path) as service:
        result = service.get_daily_research_result(10, 2025, "Q4")
    assert result.tickers == ("T10", "T10B")
    assert result.calendar_status == "DISAGREEMENT"
    assert result.result.research_status == "UNUSABLE"
    assert result.result.research_method == "TICKER_CALENDAR_DISAGREEMENT"
    assert result.result.first_full_post_result_trading_date is None


def test_batch_preserves_request_order_and_reuses_cached_calendars(tmp_path: Path) -> None:
    with _service(tmp_path) as service:
        results = service.get_daily_research_results(
            [QuarterKey(2, 2025, "Q4"), (1, 2025, "Q4"), (6, 2025, "Q4")]
        )
        first_cache = service._calendar_cache.copy()
        repeated = service.get_daily_research_result(2, 2025, "Q4")
    assert [row.result.company_id for row in results] == [2, 1, 6]
    assert repeated.to_dict() == results[0].to_dict()
    assert first_cache


def test_connections_are_read_only_and_service_does_not_mutate_data(tmp_path: Path) -> None:
    canonical, ohlc = _databases(tmp_path)
    before = sqlite3.connect(canonical).execute(
        "SELECT COUNT(*) FROM v4_result_publication_authority"
    ).fetchone()[0]
    with DailyResearchPublicationService(canonical, ohlc) as service:
        service.get_daily_research_result(2, 2025, "Q4")
        assert service._canonical.execute("PRAGMA query_only").fetchone()[0] == 1
        assert service._ohlc.execute("PRAGMA query_only").fetchone()[0] == 1
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            service._canonical.execute("DELETE FROM v4_result_publication_authority")
    after = sqlite3.connect(canonical).execute(
        "SELECT COUNT(*) FROM v4_result_publication_authority"
    ).fetchone()[0]
    assert after == before


def test_missing_and_duplicate_keys_fail_explicitly(tmp_path: Path) -> None:
    with _service(tmp_path) as service:
        with pytest.raises(QuarterNotFoundError, match="9/2025/Q4"):
            service.get_daily_research_result(9, 2025, "Q4")
        with pytest.raises(ValueError, match="DUPLICATE_QUARTER_KEY"):
            service.get_daily_research_results([(1, 2025, "Q4"), (1, 2025, "Q4")])
