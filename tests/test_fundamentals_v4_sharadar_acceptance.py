from __future__ import annotations

from pathlib import Path

from rawcandle.fundamentals.providers.sharadar import STATUS_FREE_TIER_LIMIT, STATUS_SUCCESS, SharadarResult
from rawcandle.fundamentals.sharadar_acceptance import (
    classify_reconciliation,
    confirm_paid_entitlement,
    is_within_day_equivalence,
    parse_fiscalperiod,
    validate_arq_vs_mrq,
    validate_debt,
    validate_fcf,
    validate_fiscal_identity,
    validate_q4_coverage,
    validate_quarter_continuity,
    validate_shares,
)


def _result(status: str, records: list[dict]) -> SharadarResult:
    return SharadarResult(
        status=status,
        auth_status="AUTH_OK",
        http_status=200 if status == STATUS_SUCCESS else 403,
        endpoint="/data/fundamentals",
        url="https://api.sharadar.com/v1.0/data/fundamentals?ticker=WDAY",
        request_count=1,
        records=records,
    )


class FakeClient:
    def __init__(self, result: SharadarResult) -> None:
        self.result = result

    def fundamentals(self, **kwargs):
        assert kwargs["ticker"] == "WDAY"
        assert kwargs["dimension"] == "ARQ"
        assert "years" not in kwargs
        assert "fields" not in kwargs
        return self.result


def test_paid_entitlement_success_classification() -> None:
    status, result = confirm_paid_entitlement(FakeClient(_result(STATUS_SUCCESS, [{"ticker": "WDAY"}])))  # type: ignore[arg-type]
    assert status == "PAID_5Y_ENTITLEMENT_CONFIRMED"
    assert result.records


def test_free_tier_403_no_longer_expected_once_paid_access_confirmed() -> None:
    status, _ = confirm_paid_entitlement(FakeClient(_result(STATUS_FREE_TIER_LIMIT, [])))  # type: ignore[arg-type]
    assert status == "PAID_ENTITLEMENT_NOT_ACTIVE_OR_KEY_NOT_REFRESHED"


def test_wday_known_truth() -> None:
    rows, summary = validate_fiscal_identity([{"ticker": "WDAY", "reportperiod": "2026-04-30", "fiscalperiod": "2027-Q1"}])
    assert rows[0]["status"] == "MATCH_OFFICIAL"
    assert summary["match_official"] == 1


def test_asth_known_truth() -> None:
    rows, _ = validate_fiscal_identity([{"ticker": "ASTH", "reportperiod": "2026-03-31", "fiscalperiod": "2026-Q1"}])
    assert rows[0]["status"] == "MATCH_OFFICIAL"


def test_ceco_known_truth() -> None:
    rows, _ = validate_fiscal_identity([{"ticker": "CECO", "reportperiod": "2026-03-31", "fiscalperiod": "2026-Q1"}])
    assert rows[0]["status"] == "MATCH_OFFICIAL"


def test_aapl_known_truth() -> None:
    rows, _ = validate_fiscal_identity([{"ticker": "AAPL", "reportperiod": "2025-12-27", "fiscalperiod": "2026-Q1"}])
    assert rows[0]["status"] == "MATCH_OFFICIAL"


def test_period_equivalence_allows_seven_days() -> None:
    assert is_within_day_equivalence("2026-01-30", "2026-01-31")
    assert is_within_day_equivalence("2026-02-07", "2026-01-31")
    assert not is_within_day_equivalence("2026-02-08", "2026-01-31")


def test_official_period_end_outranks_normalized_provider_date() -> None:
    rows, _ = validate_fiscal_identity([{"ticker": "WDAY", "reportperiod": "2026-04-30", "fiscalperiod": "2026-Q1"}])
    assert rows[0]["expected_fiscalperiod"] == "2027-Q1"
    assert rows[0]["status"] == "MISMATCH_OFFICIAL"


def test_explicit_q4_detection() -> None:
    rows, summary = validate_q4_coverage(
        {"AAPL": [{"ticker": "AAPL", "fiscalperiod": "2025-Q1"}, {"ticker": "AAPL", "fiscalperiod": "2025-Q2"}, {"ticker": "AAPL", "fiscalperiod": "2025-Q3"}, {"ticker": "AAPL", "fiscalperiod": "2025-Q4"}]}
    )
    assert rows[0]["status"] == "FULL_Q1_Q4_SEQUENCE"
    assert summary["explicit_q4_present"] == 1


def test_quarter_continuity() -> None:
    rows, summary = validate_quarter_continuity(
        {"AAPL": [{"fiscalperiod": "2025-Q1"}, {"fiscalperiod": "2025-Q2"}, {"fiscalperiod": "2025-Q3"}, {"fiscalperiod": "2025-Q4"}, {"fiscalperiod": "2026-Q1"}]}
    )
    assert rows[0]["status"] == "CONTINUOUS"
    assert summary["CONTINUOUS"] == 1


def test_duplicate_fiscalperiod_detection() -> None:
    rows, summary = validate_quarter_continuity({"AAPL": [{"fiscalperiod": "2025-Q1"}, {"fiscalperiod": "2025-Q1"}]})
    assert rows[0]["status"] == "DUPLICATE"
    assert summary["DUPLICATE"] == 1


def test_fcf_reconciliation() -> None:
    rows, summary = validate_fcf([{"ticker": "AAPL", "ncfo": 10, "capex": -3, "fcf": 7}])
    assert rows[0]["status"] == "EXACT_RECONCILIATION"
    assert summary["exact_or_rounding"] == 1


def test_debt_reconciliation() -> None:
    rows, summary = validate_debt([{"ticker": "AAPL", "debtc": 3, "debtnc": 7, "debt": 10}])
    assert rows[0]["status"] == "EXACT_RECONCILIATION"
    assert summary["exact_or_rounding"] == 1


def test_sharesbas_stays_period_end_candidate() -> None:
    rows, summary = validate_shares({"AAPL": [{"ticker": "AAPL", "reportperiod": "2025-01-01", "sharesbas": 10}]}, {"AAPL": []})
    assert rows[0]["sharesbas_latest8_pct"] == 100.0
    assert summary["sharesbas_acceptance_status"] == "SHARESBAS_ACCEPT"


def test_weighted_average_shares_not_canonicalized() -> None:
    rows, _ = validate_shares(
        {"AAPL": [{"ticker": "AAPL", "reportperiod": "2025-01-01", "sharesbas": 10, "shareswa": 9, "shareswadil": 8}]},
        {"AAPL": []},
    )
    assert rows[0]["shareswa_latest8_pct"] == 100.0
    assert rows[0]["shareswadil_latest8_pct"] == 100.0


def test_arq_mrq_kept_distinct() -> None:
    rows, summary = validate_arq_vs_mrq(
        {"AAPL": [{"ticker": "AAPL", "reportperiod": "2025-01-01", "fiscalperiod": "2025-Q1", "revenue": 100}]},
        {"AAPL": [{"ticker": "AAPL", "reportperiod": "2025-01-01", "fiscalperiod": "2025-Q1", "revenue": 101}]},
    )
    assert rows[0]["status"] == "RESTATED_OR_UPDATED"
    assert summary["matching_periods"] == 1


def test_permaticker_parseable_fiscalperiod() -> None:
    assert parse_fiscalperiod("2026-Q4") == (2026, 4)
    assert parse_fiscalperiod("bad") is None


def test_no_v4_db_creation(tmp_path: Path) -> None:
    forbidden = ["fundamentals_provider.db", "fundamentals_v4.db", "fundamentals_analysis.db"]
    assert not any((tmp_path / name).exists() for name in forbidden)


def test_no_v3_writes_contract() -> None:
    import rawcandle.fundamentals.sharadar_acceptance as acceptance

    source = Path(acceptance.__file__).read_text()
    assert "rc_fundamentals_v3.db" not in source


def test_no_swingmaster_runtime_dependency() -> None:
    import rawcandle.fundamentals.sharadar_acceptance as acceptance

    source = Path(acceptance.__file__).read_text().lower()
    assert "import swingmaster" not in source
    assert "from swingmaster" not in source
    assert "/home/kalle/projects/swingmaster" not in source


def test_api_key_redaction_not_reimplemented() -> None:
    import rawcandle.fundamentals.sharadar_acceptance as acceptance

    source = Path(acceptance.__file__).read_text()
    assert "SHARADAR_API_KEY" not in source


def test_no_bulk_download_years_parameter() -> None:
    import rawcandle.fundamentals.sharadar_acceptance as acceptance

    source = Path(acceptance.__file__).read_text()
    assert "years=5" not in source
    assert "years=10" not in source
    assert "years=full" not in source
