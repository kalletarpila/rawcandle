from __future__ import annotations

from pathlib import Path

import pytest

from rawcandle.fundamentals.phase12d import PRODUCTION
from rawcandle.fundamentals.phase13f2_date_aware_policy import (
    ListingInterval,
    classify_interval,
    eligible_on_date,
    resolve_listing_interval,
    run_prewrite_audit,
)


def test_date_aware_rule_includes_listing_boundaries_and_excludes_outside() -> None:
    interval = ListingInterval(1, "OLD", "usa", "2022-02-07", "2026-05-12", "provider", "DELISTED")

    assert eligible_on_date(interval, "2022-02-06") == (False, "PRELISTING")
    assert eligible_on_date(interval, "2022-02-07") == (True, "ELIGIBLE_ON_DATE")
    assert eligible_on_date(interval, "2026-05-12") == (True, "ELIGIBLE_ON_DATE")
    assert eligible_on_date(interval, "2026-05-13") == (False, "POST_DELISTING")


def test_open_ended_active_listing_uses_same_generic_rule() -> None:
    interval = ListingInterval(2, "LIVE", "usa", "2025-01-01", None, "provider", "CURRENTLY_LISTED")

    assert eligible_on_date(interval, "2024-12-31") == (False, "PRELISTING")
    assert eligible_on_date(interval, "2026-09-12") == (True, "ELIGIBLE_ON_DATE")
    assert classify_interval(interval, "2026-09-12") == "CURRENTLY_LISTED"


def test_unresolved_interval_fails_closed_even_with_ohlc() -> None:
    interval = ListingInterval(3, "GAP", "usa", "2018-01-02", None, "canonical_active_plus_local_ohlc", "LISTING_INTERVAL_UNRESOLVED")

    assert eligible_on_date(interval, "2026-09-12") == (False, "LISTING_INTERVAL_UNRESOLVED")


def test_stale_ohlc_alone_does_not_classify_security_as_delisted() -> None:
    security = {"security_id": 4, "current_ticker": "STALE", "exchange": "NASDAQ", "active": 1}
    ohlc = {"first_ohlc_date": "2018-01-02", "last_ohlc_date": "2026-08-01"}

    interval = resolve_listing_interval(security, None, ohlc)

    assert interval.status == "LISTING_INTERVAL_UNRESOLVED"
    assert interval.listing_end is None


def test_ticker_reuse_keeps_separate_security_intervals() -> None:
    old = ListingInterval(10, "SNDK1", "usa", "1995-11-08", "2016-05-11", "provider", "DELISTED")
    new = ListingInterval(20, "SNDK", "usa", "2025-02-24", None, "provider", "CURRENTLY_LISTED")

    assert old.security_id != new.security_id
    assert eligible_on_date(old, "2026-09-12") == (False, "POST_DELISTING")
    assert eligible_on_date(new, "2026-09-12") == (True, "ELIGIBLE_ON_DATE")


def test_areb_follows_generic_date_rule() -> None:
    areb = ListingInterval(192, "AREB", "usa", "2022-02-07", "2026-05-12", "provider", "DELISTED")

    assert eligible_on_date(areb, "2026-03-31") == (True, "ELIGIBLE_ON_DATE")
    assert eligible_on_date(areb, "2026-09-12") == (False, "POST_DELISTING")


def test_protected_production_output_refusal() -> None:
    with pytest.raises(PermissionError):
        run_prewrite_audit(PRODUCTION["analysis"])
