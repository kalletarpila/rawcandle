"""Bounded publication enrichment of inactive refresh candidates only."""
from __future__ import annotations

import sqlite3
import math
import time
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Sequence

from rawcandle.fundamentals.result_publication import SecClient, enrich_database
from rawcandle.fundamentals.admin.publication_journal import sqlite_verification
from rawcandle.fundamentals.admin.publication_allowlist import (
    QuarterKey, normalize_allowlist, select_exact_scope, assert_scope_subset,
)


def select_candidate_scope(
    candidate_db: Path, new_quarter_identities: Sequence[Sequence[Any]], *,
    as_of_date: str, retry_days: int = 60, retry_max_quarters: int | None = 100,
) -> dict[str, Any]:
    if retry_days < 0 or (retry_max_quarters is not None and retry_max_quarters < 0):
        raise ValueError("PUBLICATION_RETRY_CONFIGURATION_INVALID")
    today = date.fromisoformat(as_of_date)
    cutoff = (today - timedelta(days=retry_days)).isoformat()
    connection = sqlite3.connect(candidate_db.resolve().as_uri()+"?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        new = []
        for key in sorted({(int(k[0]), int(k[1]), str(k[2])) for k in new_quarter_identities}):
            row = connection.execute(
                "SELECT a.status FROM v4_quarter q LEFT JOIN v4_result_publication_authority a "
                "USING(company_id,fiscal_year,fiscal_quarter) WHERE q.company_id=? AND q.fiscal_year=? AND q.fiscal_quarter=?", key).fetchone()
            if row is None:
                raise ValueError(f"NEW_PUBLICATION_QUARTER_MISSING:{key}")
            if row["status"] != "VERIFIED":
                new.append(key)
        rows = connection.execute(
            "SELECT q.company_id,q.fiscal_year,q.fiscal_quarter,a.status,"
            "max(coalesce(q.first_public_result_date,''),coalesce(q.source_availability_date,'')) AS context_date "
            "FROM v4_quarter q LEFT JOIN v4_result_publication_authority a USING(company_id,fiscal_year,fiscal_quarter) "
            "WHERE (a.status IS NULL OR a.status IN ('UNRESOLVED','NOT_FOUND','AMBIGUOUS')) "
            "AND max(coalesce(q.first_public_result_date,''),coalesce(q.source_availability_date,'')) BETWEEN ? AND ? "
            "ORDER BY CASE a.status WHEN 'UNRESOLVED' THEN 1 WHEN 'NOT_FOUND' THEN 2 WHEN 'AMBIGUOUS' THEN 3 ELSE 0 END,"
            "context_date DESC,q.company_id,q.fiscal_year,q.fiscal_quarter", (cutoff,today.isoformat())).fetchall()
        new_set = set(new)
        retries = [(row["company_id"], row["fiscal_year"], row["fiscal_quarter"]) for row in rows
                   if (row["company_id"],row["fiscal_year"],row["fiscal_quarter"]) not in new_set]
        selected = retries[:retry_max_quarters]
        return {"new_quarters": new, "retry_quarters": selected, "quarter_keys": new+selected,
                "recent_open_total": len(rows), "retry_eligible_total": len(retries),
                "retry_selected": len(selected), "retry_backlog_remaining": len(retries)-len(selected),
                "retry_days": retry_days, "retry_max_quarters": retry_max_quarters,
                "recent_status_counts": dict(Counter(row["status"] or "MISSING" for row in rows)),
                "recent_context": "max(first_public_result_date,source_availability_date); scope only, never authority"}
    finally:
        connection.close()


def run_candidate_publication(
    candidate_db: Path, new_quarter_identities: Sequence[Sequence[Any]], *,
    as_of_date: str, retry_days: int = 60, retry_max_quarters: int | None = 100,
    client: SecClient | None = None,
    network_budget_seconds: float = 300,
    exact_quarter_allowlist: Sequence[Sequence[Any]] | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    if not math.isfinite(network_budget_seconds) or network_budget_seconds <= 0:
        raise ValueError("PUBLICATION_NETWORK_BUDGET_INVALID")
    if (candidate_db.resolve().parent / "generation_manifest.json").exists():
        raise ValueError("PUBLICATION_FINALIZED_GENERATION_WRITE_FORBIDDEN")
    allowed = normalize_allowlist(exact_quarter_allowlist) if exact_quarter_allowlist is not None else None
    if allowed is not None and new_quarter_identities:
        raise ValueError("PUBLICATION_EXACT_ALLOWLIST_CANNOT_USE_NEW_THIS_REFRESH")
    scope = (select_exact_scope(candidate_db, allowed, as_of_date=as_of_date, retry_days=retry_days)
             if allowed is not None else
             select_candidate_scope(candidate_db, new_quarter_identities, as_of_date=as_of_date,
                                    retry_days=retry_days, retry_max_quarters=retry_max_quarters))
    if not scope["quarter_keys"]:
        return {**scope,"status":"SKIPPED","total_processed":0,"status_counts":{},"network":{},
                "runtime_seconds":round(time.perf_counter()-started,3)}
    client = client or SecClient(maximum_runtime_seconds=network_budget_seconds)
    if allowed is not None:
        return _run_exact_publication(candidate_db, scope, allowed, client, as_of_date, retry_days, started)
    counts: Counter = Counter()
    errors, results = [], []
    # Limit SQL parameter/expression size without capping NEW_THIS_REFRESH.
    keys = scope["quarter_keys"]
    for offset in range(0,len(keys),200):
        report = enrich_database(candidate_db, from_fiscal_year=1, quarter_keys=keys[offset:offset+200],
                                 client=client, apply=True, refresh_existing=False)
        counts.update(report["status_counts"])
        errors.extend(report["errors"])
        results.extend(report["results"])
    verification = sqlite_verification(candidate_db)
    return {**scope, "status":"PARTIAL" if errors or any(counts[s] for s in ("UNRESOLVED","NOT_FOUND","AMBIGUOUS")) or len(results)<len(keys) else "SUCCESS",
            "total_processed":len(results),"status_counts":dict(counts),"new_verified":counts["VERIFIED"],
            "errors":errors,"results":results,"network":dict(client.stats),
            "unprocessed_selected":len(keys)-len(results), "verification":verification,
            "runtime_seconds":round(time.perf_counter()-started,3)}


class _FrozenFilingsClient(SecClient):
    """Reuse the exact successful preview inputs; never re-fetch during apply."""
    def __init__(self, delegate: SecClient) -> None:
        super().__init__()
        self.delegate = delegate
        self.stats = getattr(delegate, "stats", Counter())
        self.filings: dict[tuple, tuple] = {}
        self.sealed = False

    def item_2_02_filings(self, cik: str, *, from_calendar_year: int = 2024, **date_scope):
        key = (cik, from_calendar_year, tuple(sorted(date_scope.items())))
        if key not in self.filings:
            if self.sealed:
                raise sqlite3.DatabaseError("PUBLICATION_EXACT_ALLOWLIST_FILING_INPUT_DRIFT")
            kwargs = date_scope if isinstance(self.delegate, SecClient) else {}
            self.filings[key] = tuple(self.delegate.item_2_02_filings(
                cik, from_calendar_year=from_calendar_year, **kwargs,
            ))
        return list(self.filings[key])


def _result_keys(results: Sequence[dict[str, Any]]) -> list[QuarterKey]:
    return [(int(row["company_id"]), int(row["fiscal_year"]), str(row["fiscal_quarter"])) for row in results]


def _run_exact_publication(candidate_db, scope, allowed, client, as_of_date, retry_days, started):
    keys = scope["quarter_keys"]
    assert_scope_subset(keys, allowed)
    frozen = _FrozenFilingsClient(client)
    counts: Counter = Counter()
    errors, results, skipped_errors = [], [], []
    for offset in range(0, len(keys), 200):
        chunk = keys[offset:offset + 200]
        preview = enrich_database(candidate_db, from_fiscal_year=1, quarter_keys=chunk,
                                  client=frozen, apply=False, refresh_existing=False)
        preview_keys = _result_keys(preview["results"])
        assert_scope_subset(preview_keys, chunk)
        error_companies = {int(row["company_id"]) for row in preview["errors"]}
        if not error_companies <= {key[0] for key in chunk}:
            raise RuntimeError("PUBLICATION_EXACT_ALLOWLIST_ERROR_SCOPE_EXPANDED")
        failed = [key for key in chunk if key[0] in error_companies]
        if set(preview_keys) | set(failed) != set(chunk):
            raise RuntimeError("PUBLICATION_EXACT_ALLOWLIST_INCOMPLETE_PREVIEW")
        fresh = select_exact_scope(candidate_db, chunk, as_of_date=as_of_date, retry_days=retry_days)
        if fresh["quarter_keys"] != chunk:
            raise RuntimeError("PUBLICATION_EXACT_ALLOWLIST_CANDIDATE_STATE_DRIFT")
        errors.extend(preview["errors"])
        skipped_errors.extend(failed)
        frozen.sealed = True
        apply_keys = [key for key in chunk if key not in failed]
        if apply_keys:
            report = enrich_database(candidate_db, from_fiscal_year=1, quarter_keys=apply_keys,
                                     client=frozen, apply=True, refresh_existing=False)
            actual = _result_keys(report["results"])
            assert_scope_subset(actual, apply_keys)
            if set(actual) != set(apply_keys) or report["errors"]:
                raise RuntimeError("PUBLICATION_EXACT_ALLOWLIST_INCOMPLETE_APPLY")
            counts.update(report["status_counts"])
            results.extend(report["results"])
        frozen.sealed = False
    applied = _result_keys(results)
    assert_scope_subset(applied, allowed)
    return {**scope, "status": "PARTIAL" if errors or any(counts[s] for s in ("UNRESOLVED", "NOT_FOUND", "AMBIGUOUS")) else "SUCCESS",
            "total_processed": len(applied) + len(skipped_errors), "status_counts": dict(counts),
            "new_verified": counts["VERIFIED"], "errors": errors, "results": results,
            "network": dict(frozen.stats), "unprocessed_selected": 0,
            "enriched_natural_keys": keys, "applied_natural_keys": applied, "applied_count": len(applied),
            "skipped_error_natural_keys": skipped_errors,
            "verification": sqlite_verification(candidate_db),
            "runtime_seconds": round(time.perf_counter() - started, 3)}
