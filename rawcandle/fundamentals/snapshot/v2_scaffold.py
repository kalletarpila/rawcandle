"""Source-only scaffold for the active V2 company snapshot."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence

from rawcandle.fundamentals.operating_income_v2.score_math import fiscal_ordinal
from rawcandle.fundamentals.ttm.engine import MODEL_VERSION as TTM_MODEL_VERSION


CURRENT_PRICE_LABEL = "INDICATIVE_CURRENT_PRICE_VALUATION"
PRICE_MAX_AGE_DAYS = 7
FILING_PRICE_MAX_AGE_DAYS = 3
HISTORY_MODE_NOTICE = "Currently revised history \u2014 not original point-in-time history"


@dataclass(frozen=True)
class SnapshotPaths:
    canonical_db: Path
    analysis_db: Path
    market_db: Path
    taxonomy_db: Path
    provider_db: Path


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def four_observation_average(values: Sequence[float | None]) -> float | None:
    if len(values) != 4 or any(value is None for value in values):
        return None
    numbers = [float(value) for value in values if value is not None]
    if not all(math.isfinite(value) for value in numbers):
        return None
    return sum(numbers) / 4.0


def assert_source_unchanged(before: Mapping[str, Any], after: Mapping[str, Any]) -> None:
    if before != after:
        raise RuntimeError("SNAPSHOT_SOURCE_CHANGED_DURING_GENERATION")


def _readonly(path: Path) -> sqlite3.Connection:
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"SNAPSHOT_SOURCE_NOT_REGULAR_FILE:{path}")
    # SQLite's read-only mode includes committed WAL frames without checkpointing
    # or treating the main database file as an immutable standalone snapshot.
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    connection.execute("BEGIN")
    return connection


def _validate_paths(paths: SnapshotPaths) -> None:
    resolved = [path.resolve() for path in asdict(paths).values()]
    if len(set(resolved)) != len(resolved):
        raise ValueError("SNAPSHOT_SOURCE_PATHS_MUST_BE_DISTINCT")
    for path in asdict(paths).values():
        if not path.is_absolute():
            raise ValueError(f"SNAPSHOT_SOURCE_PATH_MUST_BE_ABSOLUTE:{path}")
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"SNAPSHOT_SOURCE_NOT_REGULAR_FILE:{path}")


def strict_fiscal_slots(
    rows: Sequence[Mapping[str, Any]],
    *,
    anchor_year: int,
    anchor_quarter: str,
    count: int,
) -> list[dict[str, Any]]:
    anchor = fiscal_ordinal(anchor_year, anchor_quarter)
    by_ordinal = {
        fiscal_ordinal(row["fiscal_year"], row["fiscal_quarter"]): dict(row)
        for row in rows
    }
    result = []
    for ordinal in range(anchor - count + 1, anchor + 1):
        year, quarter_index = divmod(ordinal, 4)
        result.append({
            "fiscal_year": year,
            "fiscal_quarter": f"Q{quarter_index + 1}",
            "fiscal_sequence": ordinal,
            "row": by_ordinal.get(ordinal),
        })
    return result


def lifecycle_transition_status(
    row: Mapping[str, Any] | None,
    previous: Mapping[str, Any] | None,
) -> str:
    if row is None:
        return "NO_LIFECYCLE_OBSERVATION"
    if row.get("lifecycle_status") == "LIFECYCLE_NOT_READY":
        if row.get("raw_state") == "UNCLASSIFIED" and previous and previous.get("candidate_count") == 1:
            return "CANDIDATE_CLEARED_BY_UNCLASSIFIED"
        return "LIFECYCLE_NOT_READY"
    candidate = row.get("candidate_state")
    if row.get("candidate_count") == 1 and candidate:
        replaced = previous.get("candidate_state") if previous and previous.get("candidate_count") == 1 else None
        suffix = f"; REPLACED_{replaced}" if replaced and replaced != candidate else ""
        return f"PENDING_{candidate}_1_OF_2{suffix}"
    final_state = row.get("final_state")
    raw_state = row.get("raw_state")
    previous_final = previous.get("final_state") if previous else None
    if final_state == "DISTRESSED" and raw_state == "DISTRESSED" and previous_final != "DISTRESSED":
        return "IMMEDIATE_DISTRESSED_ENTRY"
    if (
        final_state
        and raw_state == final_state
        and previous
        and previous.get("candidate_state") == final_state
        and previous.get("candidate_count") == 1
    ):
        return f"CONFIRMED_{final_state}_2_OF_2"
    return "NO_PENDING_TRANSITION"


def lifecycle_presentation(
    rows: Sequence[Mapping[str, Any]],
    *,
    anchor_year: int,
    anchor_quarter: str,
) -> dict[str, Any]:
    anchor_ordinal = fiscal_ordinal(anchor_year, anchor_quarter)
    by_ordinal = {
        fiscal_ordinal(row["fiscal_year"], row["fiscal_quarter"]): dict(row)
        for row in rows
    }
    display = []
    for ordinal in range(anchor_ordinal - 3, anchor_ordinal + 1):
        year, quarter_index = divmod(ordinal, 4)
        row = by_ordinal.get(ordinal)
        display.append({
            "fiscal_year": year,
            "fiscal_quarter": f"Q{quarter_index + 1}",
            "row": row,
            "transition_status": lifecycle_transition_status(row, by_ordinal.get(ordinal - 1)),
        })

    current = by_ordinal.get(anchor_ordinal)
    tenure = 0
    active_since = None
    if current and current.get("lifecycle_status") == "LIFECYCLE_READY" and current.get("final_state"):
        expected = current["final_state"]
        ordinal = anchor_ordinal
        while (
            (row := by_ordinal.get(ordinal)) is not None
            and row.get("lifecycle_status") == "LIFECYCLE_READY"
            and row.get("final_state") == expected
        ):
            tenure += 1
            active_since = row
            ordinal -= 1
    lifecycle_ready = bool(
        current and current.get("lifecycle_status") == "LIFECYCLE_READY"
    )
    return {
        "history": display,
        "current_status": current.get("lifecycle_status") if current else None,
        "confirmed_state": current.get("final_state") if lifecycle_ready else None,
        "tenure_quarters": tenure or None,
        "active_since_fiscal_year": active_since.get("fiscal_year") if active_since else None,
        "active_since_fiscal_quarter": active_since.get("fiscal_quarter") if active_since else None,
        "active_since_available_date": active_since.get("source_available_date") if active_since else None,
        "candidate_state": current.get("candidate_state") if lifecycle_ready and current.get("candidate_count") == 1 else None,
        "candidate_count": int(current.get("candidate_count") or 0) if current else 0,
    }


def _resolve_ticker(
    canonical: sqlite3.Connection, supplied: str
) -> dict[str, Any]:
    normalized = supplied.strip().upper()
    if not normalized:
        raise ValueError("TICKER_REQUIRED")
    rows = canonical.execute(
        """SELECT s.security_id,s.company_id,s.current_ticker,1 AS direct
             FROM security s
            WHERE s.active=1 AND UPPER(s.current_ticker)=?
            UNION ALL
           SELECT s.security_id,s.company_id,s.current_ticker,0 AS direct
             FROM ticker_alias a JOIN security s USING(security_id)
            WHERE UPPER(a.ticker)=?""",
        (normalized, normalized),
    ).fetchall()
    companies = {int(row["company_id"]) for row in rows}
    if not rows:
        raise LookupError(f"UNKNOWN_TICKER:{normalized}")
    if len(companies) != 1:
        raise LookupError(f"AMBIGUOUS_TICKER:{normalized}")
    direct = [row for row in rows if int(row["direct"]) == 1]
    candidates = direct or rows
    securities = {int(row["security_id"]) for row in candidates}
    if len(securities) != 1:
        raise LookupError(f"AMBIGUOUS_SECURITY:{normalized}")
    selected = candidates[0]
    canonical_ticker = str(selected["current_ticker"]).upper()
    if (
        not canonical_ticker
        or canonical_ticker.startswith(".")
        or ".." in canonical_ticker
        or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-" for character in canonical_ticker)
    ):
        raise ValueError(f"UNSAFE_CANONICAL_TICKER:{canonical_ticker}")
    return {
        "company_id": int(selected["company_id"]),
        "security_id": int(selected["security_id"]),
        "ticker": canonical_ticker,
        "resolution": "CURRENT_TICKER" if direct else "TICKER_ALIAS",
    }


def _source_state(connections: Mapping[str, sqlite3.Connection], ticker: str) -> dict[str, Any]:
    canonical = connections["canonical"]
    market = connections["market"]
    taxonomy = connections["taxonomy"]
    provider = connections["provider"]

    def one(conn: sqlite3.Connection, query: str, params: Sequence[Any] = ()) -> list[Any]:
        row = conn.execute(query, params).fetchone()
        return list(row) if row is not None else []

    return {
        "canonical_ttm": one(
            canonical,
            "SELECT COUNT(*),MAX(updated_at_utc),MAX(run_id) FROM v4_ttm_values WHERE model_version=?",
            (TTM_MODEL_VERSION,),
        ),
        "price": one(
            market,
            "SELECT COUNT(*),MAX(pvm),MAX(id) FROM osakedata WHERE UPPER(osake)=?",
            (ticker,),
        ),
        "classification": one(
            market,
            "SELECT ticker,sector,industry FROM ticker_meta WHERE UPPER(ticker)=?",
            (ticker,),
        ),
        "taxonomy": one(
            taxonomy,
            """SELECT COUNT(*),MAX(tv.taxonomy_version_id),MAX(tv.source_hash)
                 FROM ec_taxonomy_version tv JOIN ec_ecosystem e USING(ecosystem_id)
                WHERE tv.status='ACTIVE' AND tv.is_active=1 AND e.status='ACTIVE'""",
        ),
        "provider_identity": one(
            provider,
            """SELECT name,permaticker,lastupdated,fetched_at_utc
                 FROM sharadar_ticker_metadata
                WHERE table_name='fundamentals' AND UPPER(ticker)=?
                ORDER BY fetched_at_utc DESC LIMIT 1""",
            (ticker,),
        ),
    }


def _report_source_state(source_state: Mapping[str, Any]) -> dict[str, Any]:
    state: dict[str, Any] = {}
    delta = list(source_state.get("delta") or [])
    if delta:
        state["delta"] = delta[:8]
    diagnostic = list(source_state.get("diagnostic") or [])
    if diagnostic:
        state["diagnostic"] = diagnostic[:3]
    relative = list(source_state.get("relative") or [])
    if relative:
        relative[0] = None
        state["relative"] = relative
    return state


def read_source_state(paths: SnapshotPaths, ticker: str) -> dict[str, Any]:
    _validate_paths(paths)
    with ExitStack() as stack:
        connections = {
            name.removesuffix("_db"): stack.enter_context(_readonly(path))
            for name, path in asdict(paths).items()
        }
        return _source_state(connections, ticker)


def _company_name(provider: sqlite3.Connection, canonical: sqlite3.Connection, company_id: int, ticker: str) -> str:
    row = provider.execute(
        """SELECT name FROM sharadar_ticker_metadata
            WHERE table_name='fundamentals' AND UPPER(ticker)=?
            ORDER BY fetched_at_utc DESC LIMIT 1""",
        (ticker,),
    ).fetchone()
    if row and row[0]:
        return str(row[0])
    fallback = canonical.execute(
        "SELECT company_name FROM company WHERE company_id=?", (company_id,)
    ).fetchone()
    return str(fallback[0]) if fallback and fallback[0] else ticker


def _classification(market: sqlite3.Connection, ticker: str) -> dict[str, Any]:
    row = market.execute(
        "SELECT sector,industry FROM ticker_meta WHERE UPPER(ticker)=?", (ticker,)
    ).fetchone()
    return {
        "sector": row[0] if row and row[0] else None,
        "industry": row[1] if row and row[1] else None,
    }


def _taxonomy_memberships(taxonomy: sqlite3.Connection, ticker: str) -> list[dict[str, Any]]:
    return [dict(row) for row in taxonomy.execute(
        """SELECT e.ecosystem_code,e.ecosystem_name,m.membership_role,m.is_primary,
                  child.entity_level AS membership_level,parent.entity_code AS peer_group_code,
                  parent.entity_name AS peer_group_name
             FROM ec_membership m
             JOIN ec_taxonomy_version tv ON tv.taxonomy_version_id=m.taxonomy_version_id
             JOIN ec_ecosystem e ON e.ecosystem_id=m.ecosystem_id
             JOIN ec_entity child ON child.entity_id=m.child_entity_id
             JOIN ec_entity parent ON parent.entity_id=m.parent_entity_id
            WHERE tv.status='ACTIVE' AND tv.is_active=1 AND e.status='ACTIVE'
              AND m.status='ACTIVE' AND child.status='ACTIVE'
              AND child.entity_type='TICKER' AND UPPER(child.ticker)=?
            ORDER BY e.ecosystem_code,m.is_primary DESC,parent.entity_code,m.membership_id""",
        (ticker,),
    )]


def _canonical_history(
    canonical: sqlite3.Connection, company_id: int, report_date: str
) -> list[dict[str, Any]]:
    return [dict(row) for row in canonical.execute(
        """SELECT t.*,q.source_availability_date,
                  f.accounts_receivable,f.inventory,f.accounts_payable,
                  f.deferred_revenue,f.total_assets
             FROM v4_ttm_values t
             JOIN v4_quarter q ON q.quarter_id=t.endpoint_quarter_id
             LEFT JOIN v4_quarter_financials f ON f.quarter_id=t.endpoint_quarter_id
            WHERE t.company_id=? AND t.model_version=?
              AND t.ttm_source_available_date IS NOT NULL
              AND t.ttm_source_available_date<=?
            ORDER BY t.endpoint_fiscal_year,
                     CASE t.endpoint_fiscal_quarter
                       WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END""",
        (company_id, TTM_MODEL_VERSION, report_date),
    )]


def assemble_company_snapshot(
    paths: SnapshotPaths, *, ticker: str, report_date: str,
) -> dict[str, Any]:
    _validate_paths(paths)
    report_day = date.fromisoformat(report_date)
    with ExitStack() as stack:
        connections = {
            name.removesuffix("_db"): stack.enter_context(_readonly(path))
            for name, path in asdict(paths).items()
        }
        canonical = connections["canonical"]
        identity = _resolve_ticker(canonical, ticker)
        identity["company_name"] = _company_name(
            connections["provider"], canonical, identity["company_id"], identity["ticker"]
        )
        identity.update(_classification(connections["market"], identity["ticker"]))
        identity["taxonomy_memberships"] = _taxonomy_memberships(
            connections["taxonomy"], identity["ticker"]
        )
        source_state_audit = _source_state(connections, identity["ticker"])
        canonical_rows = _canonical_history(canonical, identity["company_id"], report_date)
        if not canonical_rows:
            raise LookupError(
                f"NO_FUNDAMENTAL_ENDPOINT_ON_OR_BEFORE_REPORT_DATE:{identity['ticker']}:{report_date}"
            )
        anchor = canonical_rows[-1]
        anchor_year = int(anchor["endpoint_fiscal_year"])
        anchor_quarter = str(anchor["endpoint_fiscal_quarter"])
        normalized = [
            {**row, "fiscal_year": row["endpoint_fiscal_year"],
             "fiscal_quarter": row["endpoint_fiscal_quarter"]}
            for row in canonical_rows
        ]
        slots = strict_fiscal_slots(
            normalized, anchor_year=anchor_year, anchor_quarter=anchor_quarter, count=5
        )
        labels = ("YoY base", "t\u22123", "t\u22122", "t\u22121", "Nykyinen")
        history = []
        for label, slot in zip(labels, slots):
            ttm = slot["row"]
            history.append({
                **slot,
                "label": label,
                "ttm": ttm,
                "quarter_id": int(ttm["endpoint_quarter_id"]) if ttm else None,
                "availability_date": ttm.get("ttm_source_available_date") if ttm else None,
                "score": None,
                "score_raw": None,
                "valuation": None,
            })
        anchor_ordinal = fiscal_ordinal(anchor_year, anchor_quarter)
        base = {
            "report_date": report_date,
            "history_notice": HISTORY_MODE_NOTICE,
            "identity": identity,
            "anchor": {
                "company_id": identity["company_id"],
                "security_id": identity["security_id"],
                "quarter_id": int(anchor["endpoint_quarter_id"]),
                "fiscal_year": anchor_year,
                "fiscal_quarter": anchor_quarter,
                "fiscal_sequence": anchor_ordinal,
                "period_end": anchor["period_end"],
                "source_availability_date": anchor["ttm_source_available_date"],
                "ttm_readiness": anchor["readiness_status"],
                "fundamental_age_days": (
                    report_day - date.fromisoformat(anchor["ttm_source_available_date"])
                ).days,
            },
            "history": history,
            "lifecycle": None,
            "delta": None,
            "current_price_valuation": {},
            "valuation_multiples": {},
            "relative_position": None,
            "diagnostic": None,
            "diagnostic_counts": {},
            "absolute_values": {"yoy_base": {}, "previous": {}, "current": {}},
            "source_state": source_state_audit,
            "source_state_audit": source_state_audit,
            "source_state_audit_fingerprint": _fingerprint(source_state_audit),
            "reconciliation": [],
        }
    assert_source_unchanged(source_state_audit, read_source_state(paths, identity["ticker"]))
    return base
