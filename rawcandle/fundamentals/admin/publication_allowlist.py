"""Exact operator scope; never a publication authority or a retry policy."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Collection, Sequence


QuarterKey = tuple[int, int, str]
EXACT_SCOPE_MODE = "EXACT_NATURAL_KEY_ALLOWLIST"


def _integer(value: Any, maximum: int) -> int:
    if type(value) is int:
        number = value
    elif isinstance(value, str) and re.fullmatch(r"[0-9]+", value.strip()):
        number = int(value.strip())
    else:
        raise ValueError("PUBLICATION_ALLOWLIST_INVALID_INTEGER")
    if not 1 <= number <= maximum:
        raise ValueError("PUBLICATION_ALLOWLIST_INTEGER_OUT_OF_RANGE")
    return number


def normalize_allowlist(items: Collection[Sequence[Any]]) -> tuple[QuarterKey, ...]:
    normalized: set[QuarterKey] = set()
    for item in items:
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            raise ValueError("PUBLICATION_ALLOWLIST_INVALID_KEY_SHAPE")
        company = _integer(item[0], 2**63 - 1)
        year = _integer(item[1], 9999)
        if not isinstance(item[2], str) or item[2].strip().upper() not in {"Q1", "Q2", "Q3", "Q4"}:
            raise ValueError("PUBLICATION_ALLOWLIST_INVALID_FISCAL_QUARTER")
        key = (company, year, item[2].strip().upper())
        if key in normalized:
            raise ValueError("PUBLICATION_ALLOWLIST_DUPLICATE_KEY")
        normalized.add(key)
    return tuple(sorted(normalized))


def read_allowlist_csv(path: Path) -> tuple[QuarterKey, ...]:
    with path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        columns = ("company_id", "fiscal_year", "fiscal_quarter")
        if not reader.fieldnames or any(reader.fieldnames.count(name) != 1 for name in columns):
            raise ValueError("PUBLICATION_ALLOWLIST_CSV_IDENTITY_COLUMNS_REQUIRED")
        keys = []
        for row in reader:
            if None in row:
                raise ValueError("PUBLICATION_ALLOWLIST_CSV_MALFORMED_ROW")
            keys.append(tuple(row[name] for name in columns))
    return normalize_allowlist(keys)


def allowlist_evidence(keys: Sequence[QuarterKey]) -> dict[str, Any]:
    canonical = json.dumps(sorted(keys), separators=(",", ":"), ensure_ascii=True)
    return {"scope_mode": EXACT_SCOPE_MODE, "allowlist_count": len(keys),
            "allowlist_fingerprint": hashlib.sha256(canonical.encode("ascii")).hexdigest(),
            "allowlist_natural_keys": list(keys)}


def select_exact_scope(
    candidate_db: Path, keys: Sequence[QuarterKey], *, as_of_date: str, retry_days: int = 60,
) -> dict[str, Any]:
    if retry_days < 0:
        raise ValueError("PUBLICATION_RETRY_CONFIGURATION_INVALID")
    today = date.fromisoformat(as_of_date)
    cutoff = (today - timedelta(days=retry_days)).isoformat()
    classifications, selected = [], []
    with closing(sqlite3.connect(candidate_db.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        for key in keys:
            row = connection.execute(
                "SELECT q.quarter_id,c.company_id,a.status,"
                "max(coalesce(q.first_public_result_date,''),coalesce(q.source_availability_date,'')) AS context_date,"
                "(SELECT count(DISTINCT cik_normalized) FROM company_cik WHERE company_id=q.company_id AND status='ACTIVE') AS cik_count "
                "FROM v4_quarter q LEFT JOIN company c USING(company_id) "
                "LEFT JOIN v4_result_publication_authority a USING(company_id,fiscal_year,fiscal_quarter) "
                "WHERE q.company_id=? AND q.fiscal_year=? AND q.fiscal_quarter=?", key,
            ).fetchone()
            status = row["status"] if row else None
            reason = None
            if row is None or row["company_id"] is None:
                classification = "IDENTITY_MISSING"
            elif status == "VERIFIED":
                classification = "CURRENTLY_VERIFIED"
            elif status == "AMBIGUOUS":
                classification = "CURRENTLY_AMBIGUOUS"
            elif status not in {None, "UNRESOLVED", "NOT_FOUND"}:
                classification = "NO_LONGER_OPEN"
            elif not cutoff <= row["context_date"] <= today.isoformat():
                classification = "NOT_IN_CURRENT_SCOPE"
            elif row["cik_count"] != 1:
                classification, reason = "ERROR", "UNIQUE_ACTIVE_CIK_REQUIRED"
            else:
                classification = "SELECTED_OPEN"
                priority = {None: 0, "UNRESOLVED": 1, "NOT_FOUND": 2}[status]
                selected.append((key, priority, row["context_date"], status or "MISSING"))
            classifications.append({"natural_key": key, "classification": classification,
                                    "current_status": status or "MISSING", "reason": reason})
    # Same priority/date/natural-key ordering as ordinary retries, without a cap.
    selected.sort(key=lambda item: item[0])
    selected.sort(key=lambda item: item[2], reverse=True)
    selected.sort(key=lambda item: item[1])
    quarter_keys = [item[0] for item in selected]
    return {**allowlist_evidence(keys), "new_quarters": [], "retry_quarters": quarter_keys,
            "quarter_keys": quarter_keys, "selected_natural_keys": quarter_keys,
            "selected_count": len(quarter_keys), "classifications": classifications,
            "skipped_counts": dict(Counter(row["classification"] for row in classifications
                                            if row["classification"] != "SELECTED_OPEN")),
            "applied_count": 0, "recent_open_total": len(selected), "retry_eligible_total": len(selected),
            "retry_selected": len(selected), "retry_backlog_remaining": 0,
            "retry_days": retry_days, "retry_max_quarters": None,
            "recent_status_counts": dict(Counter(item[3] for item in selected)),
            "recent_context": "max(first_public_result_date,source_availability_date); scope only, never authority"}


def assert_scope_subset(keys: Sequence[QuarterKey], allowed: Sequence[QuarterKey]) -> None:
    if len(keys) != len(set(keys)) or not set(keys) <= set(allowed):
        raise RuntimeError("PUBLICATION_EXACT_ALLOWLIST_SCOPE_EXPANDED")
