"""Visibility of completed review evidence; no retention or review-state policy."""
from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime, timezone
from typing import Any, Mapping

RECENT_HISTORY_NOTE = ('Showing completed cases from the last 2 calendar months; '
                       'undated or uncertain terminal records remain visible. Full audit evidence is retained.')


def history_cutoff(today: date) -> date:
    """Subtract two calendar months, clamping the day to the target month's end."""
    year, month = divmod(today.year * 12 + today.month - 3, 12)
    return date(year, month + 1, min(today.day, monthrange(year, month + 1)[1]))


def _day(value: Any) -> date | None:
    if not isinstance(value, str):
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if stamp.tzinfo is None:
            return None  # An unspecified timezone is not a safe hiding basis.
        return stamp.astimezone(timezone.utc).date()
    except (ValueError, OverflowError):
        return None


def terminal_history_date(item: Mapping[str, Any], *, kind: str) -> date | None:
    """The same authoritative terminal date for filtering and compact display."""
    status = item.get('status')
    if kind == 'provider':
        if status != 'RESOLVED':
            return None
        evidence = item.get('resolution_evidence') or {}
        primary = (item.get('resolution_at_utc'), item.get('approval_published_at_utc'),
                   evidence.get('published_at_utc') if isinstance(evidence, Mapping) else None)
    elif kind == 'ownership':
        if status not in ('PUBLISHED', 'SUPERSEDED'):
            return None
        result = item.get('result') or {}
        publication = result.get('publication') if isinstance(result, Mapping) else None
        primary = (publication.get('published_at'),) if status == 'PUBLISHED' and isinstance(publication, Mapping) else ()
    else:
        raise ValueError('Unknown review history kind')
    timestamps = [value for value in primary if value not in (None, '')]
    if not timestamps and item.get('history_terminal_event') == status:
        timestamps = [item.get('history_terminal_at_utc')]
    days = [_day(value) for value in timestamps]
    if not days or any(day is None for day in days):
        return None
    return max(days)


def recent_history_visible(item: Mapping[str, Any], *, kind: str, today: date | None = None) -> bool:
    """Only hide a known terminal case with an unambiguous old terminal date.

    First/last observation, fiscal period and approval-preparation dates are
    deliberately not fallbacks for a resolution/publication/supersession date.
    """
    terminal_date = terminal_history_date(item,kind=kind)
    if terminal_date is None:
        return True  # Nonterminal or uncertain completion evidence fails open.
    current_day = today if today is not None else datetime.now(timezone.utc).date()
    return terminal_date >= history_cutoff(current_day)
