from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from contextlib import ExitStack
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from rawcandle.fundamentals.delta.engine import MODEL_FINGERPRINT as DELTA_FINGERPRINT
from rawcandle.fundamentals.delta.readers import FundamentalDeltaRepository
from rawcandle.fundamentals.diagnostic_flags.engine import (
    MODEL_FINGERPRINT as DIAGNOSTIC_FINGERPRINT,
)
from rawcandle.fundamentals.diagnostic_flags.readers import DiagnosticFlagRepository
from rawcandle.fundamentals.lifecycle.engine import MODEL_FINGERPRINT as LIFECYCLE_FINGERPRINT
from rawcandle.fundamentals.lifecycle.revised_history import RevisedLifecycleRepository
from rawcandle.fundamentals.relative_position.engine import (
    MODEL_FINGERPRINT as RELATIVE_FINGERPRINT,
)
from rawcandle.fundamentals.relative_position.persistence import RelativePositionRepository
from rawcandle.fundamentals.score.engine import (
    COMPONENTS,
    MODEL_CONTRACT as SCORE_CONTRACT,
    MODEL_FINGERPRINT as SCORE_FINGERPRINT,
    TTM_MODEL_VERSION,
)
from rawcandle.fundamentals.score.methodology import fiscal_ordinal
from rawcandle.fundamentals.valuation.engine import (
    MODEL_FINGERPRINT as VALUATION_FINGERPRINT,
    PriceBar,
    ValuationObservation,
    calculate_valuation,
    select_price,
)
from rawcandle.fundamentals.valuation.persistence import ValuationRepository


REPORT_CONTRACT = "CURRENT_REVISED_COMPANY_SNAPSHOT_V1"
CURRENT_PRICE_LABEL = "INDICATIVE_CURRENT_PRICE_VALUATION"
PRICE_MAX_AGE_DAYS = 7
HISTORY_MODE_NOTICE = "Currently revised history — not original point-in-time history"
COMPONENT_LABELS = {
    "REVENUE_GROWTH": "Revenue Growth",
    "EBIT_PROFITABILITY": "EBIT Profitability",
    "EBIT_MARGIN_DIRECTION": "EBIT Margin Direction (YoY)",
    "FCF_MARGIN": "FCF Margin",
    "BALANCE_SHEET_RESILIENCE": "Balance Sheet",
    "DILUTION": "Dilution",
    "FUNDAMENTAL_TRAJECTORY": "Fundamental Trajectory",
}


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
    wal = Path(f"{path}-wal")
    if wal.exists() and wal.stat().st_size:
        raise RuntimeError(f"SNAPSHOT_SOURCE_HAS_NONEMPTY_WAL:{path}")
    connection = sqlite3.connect(
        f"file:{path.resolve()}?mode=ro&immutable=1", uri=True
    )
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


def _source_state(
    connections: Mapping[str, sqlite3.Connection], ticker: str
) -> dict[str, Any]:
    analysis = connections["analysis"]
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
        "score": one(
            analysis,
            "SELECT COUNT(*),MAX(generated_at_utc),MAX(run_id) FROM score_result WHERE model_fingerprint=?",
            (SCORE_FINGERPRINT,),
        ),
        "lifecycle": one(
            analysis,
            "SELECT COUNT(*),MAX(generated_at_utc) FROM lifecycle_revised_result WHERE model_fingerprint=?",
            (LIFECYCLE_FINGERPRINT,),
        ),
        "valuation": one(
            analysis,
            "SELECT COUNT(*),MAX(calculated_at_utc) FROM valuation_revised_result WHERE model_fingerprint=?",
            (VALUATION_FINGERPRINT,),
        ),
        "delta": one(
            analysis,
            """SELECT fundamental_source_fingerprint,fundamental_result_fingerprint,
                      lifecycle_source_fingerprint,lifecycle_result_fingerprint,
                      valuation_source_fingerprint,valuation_result_fingerprint,
                      economic_package_fingerprint,physical_content_fingerprint,
                      total_row_count,component_row_count
                 FROM fundamental_delta_package WHERE model_fingerprint=?""",
            (DELTA_FINGERPRINT,),
        ),
        "relative": one(
            analysis,
            """SELECT s.snapshot_id,s.snapshot_date,s.calculation_source_fingerprint,
                      s.source_content_fingerprint,s.result_fingerprint
                 FROM relative_position_active_snapshot a
                 JOIN relative_position_snapshot s USING(snapshot_id)
                WHERE a.model_fingerprint=?""",
            (RELATIVE_FINGERPRINT,),
        ),
        "diagnostic": one(
            analysis,
            """SELECT source_fingerprint,economic_result_fingerprint,
                      physical_content_fingerprint,endpoint_count,evaluation_count
                 FROM diagnostic_flag_package WHERE model_fingerprint=?""",
            (DIAGNOSTIC_FINGERPRINT,),
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


def _score_history(
    analysis: sqlite3.Connection, company_id: int
) -> dict[int, dict[str, Any]]:
    results = [dict(row) for row in analysis.execute(
        """SELECT * FROM score_result WHERE company_id=? AND model_fingerprint=?
            ORDER BY quarter_id""",
        (company_id, SCORE_FINGERPRINT),
    )]
    output = {int(row["quarter_id"]): {**row, "components": {}} for row in results}
    if not output:
        return output
    placeholders = ",".join("?" for _ in output)
    for row in analysis.execute(
        f"""SELECT c.*,r.quarter_id FROM score_component c
              JOIN score_result r USING(score_result_id)
             WHERE r.score_result_id IN ({placeholders}) ORDER BY r.quarter_id,c.component_name""",
        tuple(int(row["score_result_id"]) for row in results),
    ):
        item = dict(row)
        try:
            item["evidence"] = json.loads(item.pop("evidence_json"))
        except (TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("SCORE_EVIDENCE_INVALID") from exc
        output[int(row["quarter_id"])]["components"][str(row["component_name"])] = item
    return output


def _score_raw(
    score: Mapping[str, Any] | None,
    ttm: Mapping[str, Any] | None,
    yoy_base_ttm: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    components = score.get("components", {}) if score else {}
    def metric(name: str) -> Any:
        return components.get(name, {}).get("evidence", {}).get("metric_value")
    branch = None
    branch_value = None
    if ttm:
        cash, debt, ebit, fcf = (ttm.get(key) for key in ("cash", "total_debt", "ttm_ebit", "ttm_free_cashflow"))
        if all(value is not None for value in (cash, debt, ebit, fcf)):
            net_debt = float(debt) - float(cash)
            if float(ebit) > 0:
                branch = "NET_DEBT_TO_EBIT"
                branch_value = net_debt / float(ebit)
            elif net_debt <= 0 and float(fcf) >= 0:
                branch = "NET_CASH_NONPOSITIVE_EBIT_POSITIVE_FCF"
                branch_value = net_debt
            elif net_debt <= 0:
                branch = "NET_CASH_NONPOSITIVE_EBIT_NEGATIVE_FCF"
                branch_value = net_debt
            else:
                branch = "POSITIVE_NET_DEBT_NONPOSITIVE_EBIT"
                branch_value = net_debt
    return {
        "revenue_growth_yoy_ttm": metric("REVENUE_GROWTH"),
        "ebit_margin_ttm": metric("EBIT_PROFITABILITY"),
        "ebit_margin_direction": metric("EBIT_MARGIN_DIRECTION"),
        "fcf_margin_ttm": metric("FCF_MARGIN"),
        "balance_sheet_branch": branch,
        "balance_sheet_value": branch_value,
        "shares_outstanding_yoy_change": metric("DILUTION"),
        "fundamental_trajectory": metric("FUNDAMENTAL_TRAJECTORY"),
        "revenue_growth_comparison_base": yoy_base_ttm.get("ttm_revenue") if yoy_base_ttm else None,
    }


def _current_price_valuation(
    market: sqlite3.Connection,
    *,
    ticker: str,
    report_date: str,
    anchor: Mapping[str, Any],
    classification: Mapping[str, Any],
) -> dict[str, Any]:
    bars = [PriceBar(str(row["pvm"]), row["open"], row["high"], row["low"], row["close"])
            for row in market.execute(
                """SELECT pvm,open,high,low,close FROM osakedata
                    WHERE UPPER(osake)=? AND pvm<=? ORDER BY pvm DESC LIMIT 32""",
                (ticker, report_date),
            )]
    selected = select_price(bars, report_date)
    if selected.selected_price is None or selected.price_date is None:
        return {"label": CURRENT_PRICE_LABEL, "valuation_status": "VALUATION_NOT_READY", "reason_code": selected.reason_code or "PRICE_MISSING", "price_date": selected.price_date, "price_age_calendar_days": selected.price_age_calendar_days}
    if selected.price_age_calendar_days is None or selected.price_age_calendar_days > PRICE_MAX_AGE_DAYS:
        return {"label": CURRENT_PRICE_LABEL, "valuation_status": "VALUATION_NOT_READY", "reason_code": "CURRENT_PRICE_FALLBACK_TOO_OLD", "price_date": selected.price_date, "price_age_calendar_days": selected.price_age_calendar_days, "selected_price": selected.selected_price}
    selected_bar = next(bar for bar in bars if bar.price_date == selected.price_date)
    observation = ValuationObservation(
        company_id=int(anchor["company_id"]), security_id=anchor.get("security_id"), ticker=ticker,
        fiscal_year=int(anchor["endpoint_fiscal_year"]), fiscal_quarter=str(anchor["endpoint_fiscal_quarter"]),
        quarter_id=int(anchor["endpoint_quarter_id"]), period_end=str(anchor["period_end"]),
        fundamental_available_date=selected.price_date,
        ttm_readiness_status=str(anchor["readiness_status"]),
        ttm_blocker_codes=tuple(json.loads(anchor.get("blocker_codes_json") or "[]")),
        ttm_ebit=anchor.get("ttm_ebit"), ttm_free_cashflow=anchor.get("ttm_free_cashflow"),
        ttm_net_income_common=anchor.get("ttm_net_income_common"),
        net_income_common_4q_ready=bool(anchor.get("net_income_common_4q_ready")),
        shares_outstanding=anchor.get("shares_outstanding"), cash=anchor.get("cash"),
        total_debt=anchor.get("total_debt"), sector=classification.get("sector"),
        industry=classification.get("industry"),
    )
    result = calculate_valuation(observation, (selected_bar,)).to_dict()
    result.update(label=CURRENT_PRICE_LABEL, price_date=selected.price_date,
                  price_age_calendar_days=selected.price_age_calendar_days,
                  fundamental_anchor_available_date=anchor.get("ttm_source_available_date"))
    return result


def _relative_position(
    repository: RelativePositionRepository,
    company_id: int,
    report_date: str,
    anchor_quarter_id: int,
) -> dict[str, Any]:
    metadata = repository.active_metadata(model_fingerprint=RELATIVE_FINGERPRINT)
    if metadata is None or str(metadata["snapshot_date"]) > report_date:
        return {"available": False, "reason": "RELATIVE_SNAPSHOT_AFTER_REPORT_DATE" if metadata else "RELATIVE_SNAPSHOT_MISSING", "metadata": metadata, "rows": []}
    rows = repository.current_company(company_id, model_fingerprint=RELATIVE_FINGERPRINT)
    anchored = [row for row in rows if str(row["source_observation_id"]).endswith(f":{anchor_quarter_id}")]
    if rows and not anchored:
        return {"available": False, "reason": "RELATIVE_SOURCE_NOT_ANCHOR_ENDPOINT", "metadata": metadata, "rows": []}
    coverage = []
    for measure in ("FUNDAMENTAL_SCORE", "ABSOLUTE_VALUATION_SCORE"):
        for scope in ("UNIVERSE", "SECTOR", "INDUSTRY", "ECOSYSTEM"):
            coverage.extend(repository.explain_unavailable(
                company_id, model_fingerprint=RELATIVE_FINGERPRINT,
                measure=measure, peer_scope=scope,
            ))
    return {"available": True, "reason": None, "metadata": metadata, "rows": anchored, "coverage": coverage}


def _reconcile(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    for slot in snapshot["history"]:
        score = slot.get("score")
        if score and score["readiness_status"] == "SCORE_FULL":
            values = [score["components"].get(name, {}).get("component_score") for name in COMPONENTS]
            add(f"score_component_sum:{slot['label']}", all(value is not None for value in values) and math.isclose(sum(values), score["total_score"], abs_tol=1e-9))
        valuation = slot.get("valuation")
        if valuation and valuation["valuation_status"] == "VALUATION_FULL":
            values = [valuation[key] for key in ("ebit_points", "fcf_points", "earnings_points")]
            add(f"valuation_component_sum:{slot['label']}", math.isclose(sum(values), valuation["total_valuation_score"], abs_tol=1e-9))
    delta = snapshot.get("delta")
    if delta:
        for prefix in ("qoq", "two_quarter", "yoy"):
            if delta["total"][f"{prefix}_status"] == "DELTA_READY":
                values = [row[f"{prefix}_delta"] for row in delta["components"]]
                add(f"delta_component_sum:{prefix}", all(value is not None for value in values) and math.isclose(sum(values), delta["total"][f"{prefix}_delta"], abs_tol=1e-9))
    current = snapshot["current_price_valuation"]
    if current.get("valuation_status") == "VALUATION_FULL":
        market_cap = current["selected_price"] * current["shares_outstanding"]
        ev = market_cap + current["total_debt"] - current["cash"]
        add("current_market_cap", math.isclose(market_cap, current["market_cap"], rel_tol=1e-12))
        add("current_enterprise_value", math.isclose(ev, current["enterprise_value"], rel_tol=1e-12))
        add("current_ebit_yield", math.isclose(current["ttm_ebit"] / ev, current["ebit_yield"], rel_tol=1e-12))
        add("current_fcf_yield", math.isclose(current["ttm_free_cashflow"] / market_cap, current["fcf_yield"], rel_tol=1e-12))
        add("current_earnings_yield", math.isclose(current["ttm_net_income_common"] / market_cap, current["earnings_yield"], rel_tol=1e-12))
    values = snapshot["absolute_values"]["current"]
    onwc_parts = [values.get(key) for key in ("accounts_receivable", "inventory", "accounts_payable", "deferred_revenue")]
    if all(value is not None for value in onwc_parts):
        expected = onwc_parts[0] + onwc_parts[1] - onwc_parts[2] - onwc_parts[3]
        add("operating_net_working_capital", math.isclose(expected, values["operating_net_working_capital"], abs_tol=1e-9))
    report_day = snapshot["report_date"]
    dates = [slot["availability_date"] for slot in snapshot["history"] if slot.get("availability_date")]
    add("no_future_fundamentals", all(value <= report_day for value in dates))
    price_date = current.get("price_date")
    add("no_future_price", price_date is None or price_date <= report_day)
    relative_date = snapshot["relative_position"].get("metadata", {}).get("snapshot_date") if snapshot["relative_position"].get("metadata") else None
    add("no_future_relative_snapshot", not snapshot["relative_position"]["available"] or relative_date <= report_day)
    return checks


def assemble_company_snapshot(
    paths: SnapshotPaths,
    *,
    ticker: str,
    report_date: str,
    before_final_verify: Callable[[], None] | None = None,
) -> dict[str, Any]:
    _validate_paths(paths)
    report_day = date.fromisoformat(report_date)
    with ExitStack() as stack:
        connections = {
            name.removesuffix("_db"): stack.enter_context(_readonly(path))
            for name, path in asdict(paths).items()
        }
        canonical, analysis = connections["canonical"], connections["analysis"]
        identity = _resolve_ticker(canonical, ticker)
        identity["company_name"] = _company_name(connections["provider"], canonical, identity["company_id"], identity["ticker"])
        classification = _classification(connections["market"], identity["ticker"])
        identity.update(classification)
        identity["taxonomy_memberships"] = _taxonomy_memberships(connections["taxonomy"], identity["ticker"])
        source_state = _source_state(connections, identity["ticker"])

        canonical_rows = _canonical_history(canonical, identity["company_id"], report_date)
        if not canonical_rows:
            raise LookupError(f"NO_FUNDAMENTAL_ENDPOINT_ON_OR_BEFORE_REPORT_DATE:{identity['ticker']}:{report_date}")
        anchor = canonical_rows[-1]
        anchor_year = int(anchor["endpoint_fiscal_year"])
        anchor_quarter = str(anchor["endpoint_fiscal_quarter"])
        anchor_ordinal = fiscal_ordinal(anchor_year, anchor_quarter)
        normalized_canonical = [
            {**row, "fiscal_year": row["endpoint_fiscal_year"], "fiscal_quarter": row["endpoint_fiscal_quarter"]}
            for row in canonical_rows
        ]
        canonical_by_ordinal = {
            fiscal_ordinal(row["fiscal_year"], row["fiscal_quarter"]): row
            for row in normalized_canonical
        }
        slots = strict_fiscal_slots(normalized_canonical, anchor_year=anchor_year, anchor_quarter=anchor_quarter, count=5)
        score_by_quarter = _score_history(analysis, identity["company_id"])
        valuation_repo = ValuationRepository(analysis)
        valuation_by_quarter = {int(row["quarter_id"]): row for row in valuation_repo.history(identity["company_id"], model_fingerprint=VALUATION_FINGERPRINT)}
        labels = ("YoY base", "t−3", "t−2", "t−1", "Nykyinen")
        history = []
        for label, slot in zip(labels, slots):
            ttm = slot["row"]
            quarter_id = int(ttm["endpoint_quarter_id"]) if ttm else None
            score = score_by_quarter.get(quarter_id) if quarter_id else None
            valuation = valuation_by_quarter.get(quarter_id) if quarter_id else None
            if valuation and valuation.get("fundamental_available_date") and valuation["fundamental_available_date"] > report_date:
                valuation = None
            history.append({
                **slot, "label": label, "ttm": ttm, "quarter_id": quarter_id,
                "availability_date": ttm.get("ttm_source_available_date") if ttm else None,
                "score": score,
                "score_raw": _score_raw(score, ttm, canonical_by_ordinal.get(slot["fiscal_sequence"] - 4)),
                "valuation": valuation,
            })

        delta = FundamentalDeltaRepository(analysis).with_components(
            identity["company_id"], anchor_year, anchor_quarter,
            model_fingerprint=DELTA_FINGERPRINT,
        )
        if delta and int(delta["total"]["current_score_result_id"]) != int(anchor["endpoint_quarter_id"]):
            delta = None
        lifecycle_rows = RevisedLifecycleRepository(analysis).history(
            identity["company_id"], model_fingerprint=LIFECYCLE_FINGERPRINT
        )
        eligible_lifecycle_rows = [
            row for row in lifecycle_rows
            if row.get("source_available_date") is None or row["source_available_date"] <= report_date
        ]
        lifecycle = lifecycle_presentation(
            eligible_lifecycle_rows,
            anchor_year=anchor_year,
            anchor_quarter=anchor_quarter,
        )

        filing_values = [
            slot["valuation"]["total_valuation_score"]
            if slot["valuation"] and slot["valuation"]["valuation_status"] == "VALUATION_FULL"
            else None
            for slot in history[1:]
        ]
        valuation_average = four_observation_average(filing_values)
        current_valuation = _current_price_valuation(
            connections["market"], ticker=identity["ticker"], report_date=report_date,
            anchor=anchor, classification=classification,
        )
        relative = _relative_position(
            RelativePositionRepository(analysis), identity["company_id"], report_date,
            int(anchor["endpoint_quarter_id"]),
        )
        diagnostic = DiagnosticFlagRepository(analysis).endpoint(
            identity["company_id"], anchor_year, anchor_quarter,
            model_fingerprint=DIAGNOSTIC_FINGERPRINT,
        )
        current_financials = {
            key: anchor.get(key) for key in (
                "cash", "total_debt", "total_assets", "accounts_receivable", "inventory",
                "accounts_payable", "deferred_revenue", "shares_outstanding",
            )
        }
        current_financials["net_debt"] = (
            None if anchor.get("cash") is None or anchor.get("total_debt") is None
            else anchor["total_debt"] - anchor["cash"]
        )
        wc = [anchor.get(key) for key in ("accounts_receivable", "inventory", "accounts_payable", "deferred_revenue")]
        current_financials["operating_net_working_capital"] = None if any(value is None for value in wc) else wc[0] + wc[1] - wc[2] - wc[3]
        absolute = {}
        for name, slot in (("yoy_base", history[0]), ("previous", history[3]), ("current", history[4])):
            ttm = slot["ttm"] or {}
            absolute[name] = {
                key: ttm.get(key) for key in (
                    "ttm_revenue", "ttm_ebit", "ttm_operating_cashflow", "ttm_capex",
                    "ttm_free_cashflow", "ttm_net_income_common",
                )
            }
        absolute["current"].update(current_financials)
        diagnostic_counts = {status: 0 for status in ("EVALUATED_FLAGGED", "EVALUATED_CLEAR", "FLAG_NOT_READY", "FLAG_NOT_APPLICABLE")}
        if diagnostic:
            for evaluation in diagnostic["evaluations"]:
                diagnostic_counts[evaluation["status"]] += 1

        snapshot: dict[str, Any] = {
            "report_contract": REPORT_CONTRACT,
            "report_date": report_date,
            "history_notice": HISTORY_MODE_NOTICE,
            "identity": identity,
            "anchor": {
                "company_id": identity["company_id"], "security_id": identity["security_id"],
                "quarter_id": int(anchor["endpoint_quarter_id"]), "fiscal_year": anchor_year,
                "fiscal_quarter": anchor_quarter, "fiscal_sequence": anchor_ordinal,
                "period_end": anchor["period_end"],
                "source_availability_date": anchor["ttm_source_available_date"],
                "ttm_readiness": anchor["readiness_status"],
                "fundamental_age_days": (report_day - date.fromisoformat(anchor["ttm_source_available_date"])).days,
            },
            "history": history,
            "delta": delta,
            "lifecycle": lifecycle,
            "valuation_four_observation_average": valuation_average,
            "valuation_four_observation_count": sum(value is not None for value in filing_values),
            "current_price_valuation": current_valuation,
            "relative_position": relative,
            "diagnostic": diagnostic,
            "diagnostic_counts": diagnostic_counts,
            "absolute_values": absolute,
            "component_contract": {name: SCORE_CONTRACT["components"][name]["maximum"] for name in COMPONENTS},
            "model_fingerprints": {
                "score": SCORE_FINGERPRINT, "lifecycle": LIFECYCLE_FINGERPRINT,
                "valuation": VALUATION_FINGERPRINT, "delta": DELTA_FINGERPRINT,
                "relative_position": RELATIVE_FINGERPRINT,
                "diagnostic_flags": DIAGNOSTIC_FINGERPRINT,
            },
            "source_state": source_state,
            "source_state_fingerprint": _fingerprint(source_state),
        }
        snapshot["reconciliation"] = _reconcile(snapshot)
        failures = [row for row in snapshot["reconciliation"] if not row["ok"]]
        if failures:
            raise RuntimeError(f"SNAPSHOT_RECONCILIATION_FAILED:{_canonical_json(failures)}")

    if before_final_verify is not None:
        before_final_verify()
    final_state = read_source_state(paths, identity["ticker"])
    assert_source_unchanged(source_state, final_state)
    return snapshot


def generate_company_snapshot(
    paths: SnapshotPaths,
    *,
    ticker: str,
    report_date: str,
    output_dir: Path,
    overwrite: bool = False,
) -> dict[str, Any]:
    from rawcandle.fundamentals.snapshot.renderer import render_snapshot
    from rawcandle.fundamentals.snapshot.writer import publish_report

    snapshot = assemble_company_snapshot(paths, ticker=ticker, report_date=report_date)
    rendered = render_snapshot(snapshot)
    final_state = read_source_state(paths, snapshot["identity"]["ticker"])
    try:
        assert_source_unchanged(snapshot["source_state"], final_state)
    except RuntimeError as exc:
        raise RuntimeError("SNAPSHOT_SOURCE_CHANGED_BEFORE_PUBLICATION") from exc
    published = publish_report(
        output_dir=output_dir,
        ticker=snapshot["identity"]["ticker"],
        report_date=report_date,
        markdown=rendered.markdown,
        overwrite=overwrite,
    )
    return {
        "status": published.status,
        "output_path": str(published.path),
        "report_content_fingerprint": rendered.content_fingerprint,
        "snapshot": snapshot,
    }
