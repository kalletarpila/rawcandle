"""Synthetic PRICE-12C identity/finality boundaries; no live providers or stores."""
from datetime import datetime, timezone
import json

import pandas as pd
import pytest

from services import stock_update_service as updater
from tests.test_stockcore_price_provider import data, sql


@pytest.mark.parametrize('listing', ['DELISTED', 'OTC_CONTINUATION', 'RENAMED'])
def test_closed_route_never_redirects_old_security_history(data, listing):
    sql(data.source, "UPDATE routes SET valid_to='2024-01-04',evidence=?",
        (json.dumps({'listing_review': listing}),))
    sql(data.source, "INSERT INTO routes VALUES('successor',1,'yahoo','NEXT','2024-01-04',NULL,1,'{}')")
    before = data.rc.read_bytes()
    assert data.factory('TEST') == ('YAHOO', 'TEST')
    assert data.yahoo_calls == ['TEST']
    assert data.rc.read_bytes() == before


def test_closed_otc_route_with_unit_hold_cannot_use_yahoo(data):
    sql(data.source, "UPDATE routes SET valid_to='2024-01-04'")
    sql(data.source, 'INSERT INTO settings VALUES(?,?)',
        ('source_quality_hold:1', '{"active":true}'))
    obj = data.factory('TEST')
    assert obj.hold == 'SOURCE_UNIT_HOLD'
    assert data.yahoo_calls == []


def test_true_yahoo_no_data_preserves_prices_and_repeat_is_empty(data, monkeypatch):
    sql(data.source, "UPDATE routes SET valid_to='2024-01-04'")
    calls = []

    class NoData:
        def history(self, *, start, end):
            calls.append((start, end))
            return pd.DataFrame()

    data.factory.yahoo_factory = lambda ticker: NoData()
    monkeypatch.setattr(updater, '_sleep_yahoo_after_history_range', lambda: None)
    plan = updater.StockUpdateTickerPlan(
        updater.StockUpdateTickerCandidate('TEST', '2024-01-02', '2024-01-03', 'usa'),
        True, date_ranges=[updater.StockUpdateDateRange('2024-01-04', '2024-01-06')])
    before = data.rc.read_bytes()
    for _ in range(2):
        result = updater.execute_ticker_ohlcv_update_plan(
            osakedata_db_path=str(data.rc), stock=data.factory('TEST'), plan=plan, market='usa')
        assert result.ohlcv_rows_inserted == 0
    assert calls == [('2024-01-04', '2024-01-06')] * 2
    assert data.rc.read_bytes() == before


def test_intraday_source_observation_is_excluded(data):
    data.factory.now = datetime(2024, 1, 4, 15, tzinfo=timezone.utc)
    obj = data.factory('TEST')
    assert obj.hold is None and not obj.rows
    assert data.yahoo_calls == []


def test_missing_completed_source_tail_is_not_fabricated_or_fallen_back(data):
    sql(data.source, "DELETE FROM source_observations WHERE session='2024-01-04'")
    sql(data.source, "UPDATE source_coverage SET status='MISSING' WHERE session='2024-01-04'")
    obj = data.factory('TEST')
    assert not obj.rows
    assert data.factory.counts['stockcore_no_new'] == 1
    assert data.yahoo_calls == []
