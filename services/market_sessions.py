"""Reviewed Helsinki cash-equity completed sessions, independent of USA clocks.

Nasdaq European Markets Trading Hours and Holiday Schedule, read 2026-11-05:
https://www.nasdaq.com/da/european-market-activity/trading-hours
Years outside the reviewed published calendar fail closed. No provider calls.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

HELSINKI = ZoneInfo('Europe/Helsinki')
CALENDAR_VERSION = 'NASDAQ_HELSINKI_CASH_2024_2027_REVIEWED_20261105'
# Explicit exchange closures, not a national-holiday approximation or USA calendar.
CLOSURES = {
    2024: '01-01 03-29 04-01 05-01 05-09 06-21 12-06 12-24 12-25 12-26 12-31',
    2025: '01-01 01-06 04-18 04-21 05-01 05-29 06-20 12-24 12-25 12-26 12-31',
    2026: '01-01 01-06 04-03 04-06 05-01 05-14 06-19 12-24 12-25 12-31',
    2027: '01-01 01-06 03-26 03-29 05-06 06-25 12-06 12-24 12-31',
}


def is_helsinki_session(day):
    day = date.fromisoformat(day) if isinstance(day, str) else day
    if day.year not in CLOSURES:
        raise ValueError('HELSINKI_CALENDAR_REVIEW_REQUIRED')
    return day.weekday() < 5 and day.strftime('%m-%d') not in CLOSURES[day.year].split()


def last_completed_helsinki_session(now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError('AWARE_MARKET_CLOCK_REQUIRED')
    local = now.astimezone(HELSINKI)
    day = local.date()
    # Closing auction completes at 18:30. A conservative 30-minute publication
    # buffer prevents a close-boundary fetch being certified as a final bar.
    if local.time() < time(19):
        day -= timedelta(days=1)
    for _ in range(15):
        if is_helsinki_session(day):
            return day.isoformat()
        day -= timedelta(days=1)
    raise ValueError('HELSINKI_COMPLETED_SESSION_UNAVAILABLE')


def completed_fetch_until(market, requested, *, now=None):
    date.fromisoformat(requested)
    if (market or '').strip().lower() != 'omxh':
        return requested
    last = date.fromisoformat(last_completed_helsinki_session(now))
    return min(requested, (last + timedelta(days=1)).isoformat())
