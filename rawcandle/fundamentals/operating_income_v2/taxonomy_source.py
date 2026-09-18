from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sqlite3
from typing import Any

from .relative_position import EcosystemMembership


def load_active_dc_memberships(
    taxonomy_db: Path, canonical_db: Path,
) -> tuple[dict[int, tuple[EcosystemMembership, ...]], dict[str, Any]]:
    # The admin contract owns the active DC sidecar interpretation and semantic hash.
    from rawcandle.fundamentals.admin.taxonomy import TaxonomyPaths, _active_state

    state = _active_state(TaxonomyPaths(taxonomy_db=taxonomy_db), "dc_ecosystem")
    ticker_to_companies: dict[str, set[int]] = defaultdict(set)
    with sqlite3.connect(f"file:{canonical_db.resolve()}?mode=ro", uri=True) as connection:
        connection.execute("PRAGMA query_only=ON")
        for company_id, ticker in connection.execute(
            "SELECT company_id,current_ticker FROM security WHERE active=1"
        ):
            ticker_to_companies[str(ticker).upper()].add(int(company_id))

    memberships: dict[int, list[EcosystemMembership]] = defaultdict(list)
    unmapped: set[str] = set()
    ambiguous: set[str] = set()
    for row in state["rows"]:
        ticker = str(row["ticker"]).upper()
        companies = ticker_to_companies.get(ticker, set())
        if not companies:
            unmapped.add(ticker)
            continue
        if len(companies) != 1:
            ambiguous.add(ticker)
            continue
        memberships[next(iter(companies))].append(EcosystemMembership(
            "DATACENTER", str(row["report_group_status"]),
            str(row["entity_id"]),
        ))
    if ambiguous:
        raise ValueError(f"AMBIGUOUS_DC_TAXONOMY_TICKERS:{','.join(sorted(ambiguous))}")
    active = state["active_version"]
    dependency = {
        "domain": "dc_ecosystem",
        "version": active["taxonomy_version_code"],
        "semantic_fingerprint": state["semantic_fingerprint"],
        "membership_rows": len(state["rows"]),
        "mapped_companies": len(memberships),
        "unmapped_tickers": sorted(unmapped),
    }
    return {key: tuple(value) for key, value in sorted(memberships.items())}, dependency
