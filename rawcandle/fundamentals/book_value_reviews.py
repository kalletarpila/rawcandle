"""Bounded unresolved-basis reviews, bound to immutable accepted evidence.

These are reviewed evidence holds, not rules inferred from EPS-share percentages.
A revised observation, hash or company identity requires a new explicit review.
"""
from __future__ import annotations

from typing import Any, Mapping


REVIEWED_BASIS_HOLDS = (
    {
        'company_id': 902,
        'observation_id': 'be26b0bf9b7eafb3efdfefe71f4266a3e3a3b71857df158f0aed05dac7afb64f',
        'content_hash': '3607c414b271ba0c74ca95f9fc22b570cccd46aca8e7318aed6c15371722ec33',
        'reviewed_as_of': '2026-10-07',
        'reference': 'P/B.4:FTFT:NEEDS_MORE_EVIDENCE',
        'evidence': 'Previously reviewed severe unit discontinuity with no exact-date '
                    'market corroboration; native arithmetic alone does not resolve the basis.',
    },
    {
        'company_id': 1200,
        'observation_id': '3de0925e0a28ebe14cf471ed3a8fc5c9b37a7d274d8410fd7d01e617ff8353fa',
        'content_hash': '098713dc9ec03f48b34c07d0ede28cc975dab84b4226548db421eb57da4cab8b',
        'reviewed_as_of': '2026-10-07',
        'reference': 'P/B.4:KALA:NEEDS_MORE_EVIDENCE',
        'evidence': 'Previously reviewed severe unresolved ownership/unit discontinuity; '
                    'matching native cap and historical price do not independently establish '
                    'the current corporate-action share basis.',
    },
)


def unresolved_basis_review(row: Mapping[str, Any], *, as_of: str) -> dict[str, Any] | None:
    """Never apply a review to another company, source revision or pre-review date."""
    for review in REVIEWED_BASIS_HOLDS:
        if (review['reviewed_as_of'] <= as_of
            and all(row.get(key) == review[key] for key in ('company_id', 'observation_id', 'content_hash'))):
            return dict(review)
    return None
