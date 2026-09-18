from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import asdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .canonical_valuation_source import load_canonical_source as load_valuation_source
from rawcandle.fundamentals import structural_break

from . import delta, diagnostic_flags, lifecycle, relative_position, score, snapshot, valuation
from .contract import FAMILY_FINGERPRINT, TTM_MODEL_VERSION, fingerprint


LEGACY_REHEARSAL_AS_OF = date(2026, 9, 6)
FRESHNESS_DAYS = 180


def resolve_as_of(as_of_date: str | date | None) -> date:
    if as_of_date is None:
        return datetime.now(timezone.utc).date()
    return as_of_date if isinstance(as_of_date, date) else date.fromisoformat(as_of_date)

KEY_TABLES = {
    "canonical": ("v4_quarter_financials", "v4_ttm_values"),
    "analysis": (
        "score_result", "score_component", "lifecycle_revised_result",
        "valuation_revised_result", "fundamental_delta_result",
        "relative_position_result", "diagnostic_flag_evaluation",
    ),
    "market": ("ticker_meta",),
    "provider": ("provider_observation", "sharadar_fundamental_observation"),
    "taxonomy": ("ec_entity", "ec_membership", "ec_ecosystem"),
}


def _ro(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only=ON")
    return connection


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def database_integrity(paths: Mapping[str, Path]) -> dict[str, Any]:
    output = {}
    for name, path in sorted(paths.items()):
        stat = path.stat()
        with _ro(path) as connection:
            schema = [row[0] for row in connection.execute("SELECT sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type,name,tbl_name")]
            tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
            row_counts = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in KEY_TABLES[name]
                if table in tables
            }
            foreign_keys = [list(row) for row in connection.execute("PRAGMA foreign_key_check")]
            quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        output[name] = {
            "path": str(path.resolve()), "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
            "sha256": _sha256(path), "schema_hash": fingerprint(schema), "quick_check": quick,
            "foreign_key_check": foreign_keys, "key_row_counts": row_counts,
            "wal_exists": Path(str(path) + "-wal").exists(),
            "shm_exists": Path(str(path) + "-shm").exists(),
        }
    return output


def _write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    fields = sorted({key for row in rows for key in row})
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=str) + "\n", encoding="utf-8")


def _load_ttm(canonical: Path) -> list[dict[str, Any]]:
    with _ro(canonical) as connection:
        return [dict(row) for row in connection.execute("""
            SELECT t.*,s.current_ticker ticker,q.source_availability_date AS quarter_source_available_date,
              f.accounts_receivable,f.inventory,f.accounts_payable,
              f.deferred_revenue,f.total_assets
            FROM v4_ttm_values t JOIN security s USING(security_id)
            JOIN v4_quarter q ON q.quarter_id=t.endpoint_quarter_id
            LEFT JOIN v4_quarter_financials f ON f.quarter_id=t.endpoint_quarter_id
            WHERE t.model_version='V4_TTM_EBIT_FIRST_V1'
            ORDER BY t.company_id,t.endpoint_fiscal_year,
              CASE t.endpoint_fiscal_quarter WHEN 'Q1' THEN 1 WHEN 'Q2' THEN 2 WHEN 'Q3' THEN 3 ELSE 4 END,t.ttm_id
        """)]


def _load_structural_context(canonical: Path) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    with _ro(canonical) as connection:
        if not structural_break.has_structural_contract(connection):
            return {}, {
                "status": "STRUCTURAL_CONTRACT_ABSENT_LEGACY_ALLOWED",
                "fingerprint": None,
                "ttm_regime_counts": {},
            }
        rows = [
            dict(row)
            for row in connection.execute(
                f"""
                SELECT r.ttm_id,r.event_id,r.company_id,r.endpoint_quarter_id,
                       r.ttm_regime_status,r.regime_reason,r.input_regimes_json,
                       r.same_regime_observation_count,r.regime_fingerprint,
                       e.event_type,e.event_date,e.comparability_status,e.review_status
                  FROM {structural_break.TTM_TABLE} r
                  JOIN {structural_break.EVENT_TABLE} e USING(event_id)
                 ORDER BY r.company_id,r.endpoint_quarter_id,r.ttm_id
                """
            )
        ]
        return {int(row["ttm_id"]): row for row in rows}, {
            "status": "STRUCTURAL_CONTRACT_APPLIED",
            "contract_version": structural_break.CONTRACT_VERSION,
            "fingerprint": structural_break.contract_fingerprint(connection),
            "ttm_regime_counts": dict(sorted(Counter(row["ttm_regime_status"] for row in rows).items())),
        }


def _append_blocker_codes(row: Mapping[str, Any], *codes: str) -> str:
    try:
        existing = list(json.loads(str(row.get("blocker_codes_json") or "[]")))
    except json.JSONDecodeError:
        existing = []
    for code in codes:
        if code and code not in existing:
            existing.append(code)
    return json.dumps(existing, sort_keys=True, separators=(",", ":"))


def _structural_row_ready(context: Mapping[str, Any]) -> bool:
    status = structural_break.normalize_status(str(context.get("comparability_status") or ""))
    regime = str(context.get("ttm_regime_status") or "UNRESOLVED")
    if status in structural_break.CONTINUOUS_STATUSES:
        return True
    return regime in {"PRE_EVENT_COHERENT", "POST_EVENT_COHERENT"}


def _annotate_structural_rows(
    rows: Sequence[Mapping[str, Any]], canonical: Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    context_by_ttm, metadata = _load_structural_context(canonical)
    if not context_by_ttm:
        return [dict(row) for row in rows], metadata
    annotated: list[dict[str, Any]] = []
    readiness_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    for source in rows:
        row = dict(source)
        context = context_by_ttm.get(int(row["ttm_id"]))
        if context is None:
            row.update({
                "structural_contract_version": structural_break.CONTRACT_VERSION,
                "structural_contract_fingerprint": metadata["fingerprint"],
                "structural_readiness_status": "STRUCTURAL_READY",
                "structural_reason_code": "NO_STRUCTURAL_EVENT",
                "structural_regime_status": "NO_STRUCTURAL_EVENT",
                "structural_regime_id": f"NO_EVENT:{row['company_id']}",
            })
        else:
            ready = _structural_row_ready(context)
            regime_status = str(context.get("ttm_regime_status") or "UNRESOLVED")
            reason = "STRUCTURAL_READY" if ready else str(context.get("regime_reason") or regime_status)
            row.update({
                "structural_contract_version": structural_break.CONTRACT_VERSION,
                "structural_contract_fingerprint": metadata["fingerprint"],
                "structural_event_id": context["event_id"],
                "structural_event_type": context["event_type"],
                "structural_event_date": context["event_date"],
                "structural_comparability_status": structural_break.normalize_status(str(context["comparability_status"])),
                "structural_readiness_status": "STRUCTURAL_READY" if ready else "STRUCTURAL_NOT_READY",
                "structural_reason_code": reason,
                "structural_regime_status": regime_status,
                "structural_regime_id": structural_break.stable_hash({
                    "event_id": context["event_id"],
                    "ttm_regime_status": regime_status,
                    "comparability_status": structural_break.normalize_status(str(context["comparability_status"])),
                }),
                "structural_regime_fingerprint": context["regime_fingerprint"],
                "structural_input_regimes_json": context["input_regimes_json"],
            })
            if not ready:
                row["core_ttm_ready"] = 0
                row["readiness_status"] = "STRUCTURAL_NOT_READY"
                row["blocker_codes_json"] = _append_blocker_codes(row, "STRUCTURAL_REGIME_NOT_READY", reason)
        readiness_counts[str(row["structural_readiness_status"])] += 1
        reason_counts[str(row["structural_reason_code"])] += 1
        annotated.append(row)
    return annotated, {
        **metadata,
        "structural_readiness_counts": dict(sorted(readiness_counts.items())),
        "structural_reason_counts": dict(sorted(reason_counts.items())),
    }


def _same_structural_regime(current: Mapping[str, Any], other: Mapping[str, Any] | None) -> bool:
    if other is None:
        return False
    current_regime = current.get("structural_regime_id")
    other_regime = other.get("structural_regime_id")
    if current_regime is None and other_regime is None:
        return True
    return (
        current_regime == other_regime
        and current.get("structural_readiness_status") == "STRUCTURAL_READY"
        and other.get("structural_readiness_status") == "STRUCTURAL_READY"
    )


def _load_quarter_revenues(canonical: Path, rows: Sequence[Mapping[str, Any]]) -> dict[int, tuple[float | None, ...]]:
    with _ro(canonical) as connection:
        values = {int(row[0]): row[1] for row in connection.execute("SELECT quarter_id,revenue FROM v4_quarter_financials")}
    return {int(row["ttm_id"]): tuple(values.get(int(qid)) for qid in json.loads(row["input_quarter_ids_json"])) for row in rows}


def _load_split_events(market: Path) -> dict[str, list[dict[str, Any]]]:
    output = defaultdict(list)
    with _ro(market) as connection:
        for row in connection.execute(
            "SELECT osake AS ticker,split_date,split_ratio,is_price_data_corrected "
            "FROM splits_data ORDER BY osake,split_date"
        ):
            output[str(row["ticker"])].append(dict(row))
    return output


def _diagnostic_endpoint(
    source: Mapping[str, Any],
    *,
    valuation_result: valuation.ValuationResult | None,
    trajectory: float | None,
    applicability_classification: str | None,
    applicability_reason: str | None,
) -> diagnostic_flags.DiagnosticEndpoint:
    company_id = int(source["company_id"])
    quarter_id = int(source["endpoint_quarter_id"])
    fiscal_year = int(source["endpoint_fiscal_year"])
    fiscal_quarter = str(source["endpoint_fiscal_quarter"])
    return diagnostic_flags.DiagnosticEndpoint(
        company_id=company_id,
        quarter_id=quarter_id,
        fiscal_year=fiscal_year,
        fiscal_quarter=fiscal_quarter,
        fiscal_sequence=fiscal_year * 4 + int(fiscal_quarter[1]),
        period_end=str(source["period_end"]),
        source_available_date=source["quarter_source_available_date"],
        ttm_available_date=source["ttm_source_available_date"],
        valuation_available_date=source["ttm_source_available_date"],
        ttm_status=(
            "TTM_READY"
            if source.get("core_ttm_ready")
            else str(source.get("readiness_status") or source.get("structural_reason_code") or "TTM_NOT_READY")
        ),
        revenue=source.get("ttm_revenue"),
        operating_income=source.get("ttm_operating_income"),
        common_earnings=source.get("ttm_net_income_common"),
        operating_cashflow=source.get("ttm_operating_cashflow"),
        capex=source.get("ttm_capex"),
        cash=source.get("cash"),
        total_debt=source.get("total_debt"),
        accounts_receivable=source.get("accounts_receivable"),
        inventory=source.get("inventory"),
        accounts_payable=source.get("accounts_payable"),
        deferred_revenue=source.get("deferred_revenue"),
        total_assets=source.get("total_assets"),
        trajectory=trajectory,
        valuation_status=valuation_result.valuation_status if valuation_result else None,
        valuation_reason=valuation_result.reason_code if valuation_result else None,
        applicability_classification=applicability_classification,
        applicability_reason=applicability_reason,
        operating_income_yield=valuation_result.operating_income_yield if valuation_result else None,
        fcf_yield=valuation_result.fcf_yield if valuation_result else None,
        earnings_yield=valuation_result.earnings_yield if valuation_result else None,
    )


def _fresh(rows: Sequence[Mapping[str, Any]], as_of: date) -> list[Mapping[str, Any]]:
    latest = {}
    for row in rows:
        available = row.get("ttm_source_available_date")
        if not available or str(available) > as_of.isoformat():
            continue
        company_id = int(row["company_id"])
        if company_id not in latest or (str(available), int(row["ttm_id"])) > (str(latest[company_id]["ttm_source_available_date"]), int(latest[company_id]["ttm_id"])):
            latest[company_id] = row
    return [row for row in latest.values() if (as_of - date.fromisoformat(str(row["ttm_source_available_date"]))).days <= FRESHNESS_DAYS]


def _lifecycle(rows: Sequence[Mapping[str, Any]], revenues: Mapping[int, tuple[float | None, ...]]) -> dict[tuple[int, int], lifecycle.StateMachineResult]:
    grouped = defaultdict(dict)
    for row in rows:
        sequence = int(row["endpoint_fiscal_year"]) * 4 + int(str(row["endpoint_fiscal_quarter"])[1])
        grouped[int(row["company_id"])][sequence] = row
    output = {}
    for company_id, history in sorted(grouped.items()):
        state = lifecycle.LifecycleMachineState()
        previous_regime: str | None = None
        for sequence, row in sorted(history.items()):
            lag = history.get(sequence - 4)
            regime = row.get("structural_regime_id")
            if regime is not None and previous_regime is not None and regime != previous_regime:
                state = lifecycle.LifecycleMachineState()
            previous_regime = str(regime) if regime is not None else previous_regime
            chain = (
                lag is not None
                and all(value in history for value in range(sequence - 4, sequence + 1))
                and all(_same_structural_regime(row, history[value]) for value in range(sequence - 4, sequence + 1))
            )
            observation = lifecycle.LifecycleObservation(
                company_id, int(row["endpoint_quarter_id"]), int(row["endpoint_fiscal_year"]),
                str(row["endpoint_fiscal_quarter"]), str(row["period_end"]), row.get("ttm_source_available_date"),
                bool(row.get("core_ttm_ready")), row.get("ttm_revenue"), row.get("ttm_operating_income"),
                row.get("ttm_free_cashflow"), lag.get("ttm_revenue") if chain else None,
                lag.get("ttm_operating_income") if chain else None, chain,
                revenues.get(int(row["ttm_id"]), ()), int(row["security_id"]) if row.get("security_id") else None,
            )
            raw = lifecycle.classify_raw_state(observation)
            state, result = lifecycle.advance_state_machine(state, raw)
            output[(company_id, int(row["endpoint_quarter_id"]))] = result
    return output


def _valuation_from_canonical_source(
    source: Mapping[str, Any], ttm: Mapping[str, Any]
) -> valuation.ValuationResult:
    base = source["observation"]
    observation = valuation.ValuationObservation(
        int(ttm["company_id"]),
        int(ttm["security_id"]) if ttm.get("security_id") else None,
        ttm.get("ticker"),
        int(ttm["endpoint_fiscal_year"]),
        str(ttm["endpoint_fiscal_quarter"]),
        int(ttm["endpoint_quarter_id"]),
        str(ttm["period_end"]),
        ttm.get("ttm_source_available_date"),
        str(ttm["readiness_status"]),
        tuple(json.loads(ttm["blocker_codes_json"])),
        ttm.get("ttm_operating_income"),
        ttm.get("ttm_free_cashflow"),
        ttm.get("ttm_net_income_common"),
        bool(ttm.get("net_income_common_4q_ready")),
        ttm.get("shares_outstanding"),
        ttm.get("cash"),
        ttm.get("total_debt"),
        base.sector,
        base.industry,
    )
    return valuation.calculate_valuation(observation, source["price_bars"])


def _score_delta_observation(row: Mapping[str, Any], ttm: Mapping[str, Any]) -> delta.ScoreObservation:
    sequence = int(ttm["endpoint_fiscal_year"]) * 4 + int(str(ttm["endpoint_fiscal_quarter"])[1])
    fiscal = delta.FiscalObservation(str(ttm["endpoint_quarter_id"]), int(ttm["company_id"]), int(ttm["endpoint_fiscal_year"]), str(ttm["endpoint_fiscal_quarter"]), sequence, str(ttm["period_end"]), str(ttm["ttm_source_available_date"]))
    maxima = dict(zip(score.COMPONENTS, (20.0, 15.0, 15.0, 15.0, 15.0, 10.0, 10.0)))
    components = tuple(delta.ScoreComponentObservation(item["component_name"], item["component_score"], maxima[item["component_name"]], "OBSERVED" if item["component_score"] is not None else "MISSING") for item in row["components"])
    return delta.ScoreObservation(
        fiscal,
        int(ttm["endpoint_quarter_id"]),
        score.MODEL_VERSION,
        score.MODEL_FINGERPRINT,
        row["total_score"],
        row["readiness_status"],
        "TTM_READY" if ttm.get("core_ttm_ready") else str(ttm.get("readiness_status") or "TTM_NOT_READY"),
        components,
    )


def calculate(
    paths: Mapping[str, Path], *,
    as_of_date: str | date | None = None,
) -> dict[str, Any]:
    as_of = resolve_as_of(as_of_date)
    raw_rows = _load_ttm(paths["canonical"])
    rows, structural_metadata = _annotate_structural_rows(raw_rows, paths["canonical"])
    ttm_index = {(int(row["company_id"]), int(row["endpoint_quarter_id"])): row for row in rows}
    fresh = _fresh(rows, as_of); fresh_keys = {(int(row["company_id"]), int(row["endpoint_quarter_id"])) for row in fresh}
    split_events = _load_split_events(paths["market"])
    v2_scores = score.compute_score_rows(rows, split_events, generated_at="REHEARSAL", run_id="PHASE9C")
    score_index = {(int(row["company_id"]), int(row["quarter_id"])): row for row in v2_scores}
    life_v2 = _lifecycle(rows, _load_quarter_revenues(paths["canonical"], rows))
    canonical_valuation = load_valuation_source(paths["canonical"], paths["market"])
    canonical_valuation_index = {
        (int(row["observation"].company_id), int(row["observation"].quarter_id)): row
        for row in canonical_valuation.rows
    }
    valuation_v2 = {}
    valuation_source_rows = []
    for key in sorted(ttm_index):
        source = canonical_valuation_index[key]
        valuation_v2[key] = _valuation_from_canonical_source(source, ttm_index[key])
        base = source["observation"]
        valuation_source_rows.append(
            {
                "company_id": key[0],
                "quarter_id": key[1],
                "security_active": source["security_active"],
                "sector": base.sector,
                "industry": base.industry,
                "source_fingerprint": source["source_fingerprint"],
            }
        )
    valuation_context_index = {
        (int(row["company_id"]), int(row["quarter_id"])): row
        for row in valuation_source_rows
    }

    histories=defaultdict(list); delta_observations={}
    for key,row in score_index.items():
        observation = _score_delta_observation(row,ttm_index[key])
        histories[key[0]].append(observation); delta_observations[key] = observation
    delta_full=[]; delta_results=[]
    for key in sorted(score_index):
        current=delta_observations[key]
        current_ttm = ttm_index[key]
        compatible_history = [
            observation
            for observation in histories[key[0]]
            if int(observation.fiscal.observation_id) == key[1]
            or _same_structural_regime(current_ttm, ttm_index[(key[0], int(observation.fiscal.observation_id))])
        ]
        result=delta.calculate_fundamental_delta(
            current,
            compatible_history,
            source_fingerprint=fingerprint({"phase": "PHASE13F3_4", "structural": structural_metadata}),
        )
        delta_results.append(result)
        delta_full.append({"company_id":key[0],"quarter_id":key[1],"ticker":score_index[key]["ticker"],**{item["horizon"].value:item["delta_points"] for item in result.horizons}})
    delta_current=[row for row in delta_full if (row["company_id"],row["quarter_id"]) in fresh_keys]

    with _ro(paths["market"]) as connection:
        classes={str(row[0]):(row[1],row[2]) for row in connection.execute("SELECT ticker,sector,industry FROM ticker_meta")}
    from .taxonomy_source import load_active_dc_memberships
    memberships, taxonomy_dependency = load_active_dc_memberships(paths["taxonomy"], paths["canonical"])
    relative_score_rows={}
    for row in rows:
        available=row.get("quarter_source_available_date")
        if not available or str(available)>as_of.isoformat(): continue
        company_id=int(row["company_id"]); current=relative_score_rows.get(company_id)
        sequence=int(row["endpoint_fiscal_year"])*4+int(str(row["endpoint_fiscal_quarter"])[1])
        if current is None or sequence>current[0]: relative_score_rows[company_id]=(sequence,row)
    relative_valuation_rows={}
    for key,value in valuation_v2.items():
        available=value.fundamental_available_date
        if not available or str(available)>as_of.isoformat(): continue
        sequence=value.fiscal_year*4+int(value.fiscal_quarter[1]); current=relative_valuation_rows.get(key[0])
        if current is None or sequence>current[0]: relative_valuation_rows[key[0]]=(sequence,key,value)
    relative_observations=[]
    structural_current_eligibility: dict[int, structural_break.StructuralEligibility] = {}
    if structural_metadata["status"] == "STRUCTURAL_CONTRACT_APPLIED":
        with _ro(paths["canonical"]) as connection:
            structural_current_eligibility, _ = structural_break.latest_ttm_eligibility(
                connection, as_of_date=as_of.isoformat()
            )
    for _,row in sorted(relative_score_rows.values(),key=lambda item:int(item[1]["company_id"])):
        eligibility = structural_current_eligibility.get(int(row["company_id"]))
        if eligibility is not None and not eligibility.eligible:
            continue
        key=(int(row["company_id"]),int(row["endpoint_quarter_id"])); ticker=str(row["ticker"]); sector,industry=classes.get(ticker,(None,None)); scored=score_index[key]
        relative_observations.append(relative_position.RelativeObservation(f"S:{key[0]}",key[0],int(row["security_id"]),ticker,relative_position.RelativeMeasure.FUNDAMENTAL_SCORE,scored["total_score"],scored["readiness_status"],scored["readiness_status"]=="SCORE_FULL",scored["readiness_status"],row["quarter_source_available_date"],score.MODEL_VERSION,score.MODEL_FINGERPRINT,f"S:{key}",sector,industry,tuple(memberships.get(key[0], ()))))
    for company_id,(_,key,value) in sorted(relative_valuation_rows.items()):
        eligibility = structural_current_eligibility.get(company_id)
        if eligibility is not None and not eligibility.eligible:
            continue
        source=ttm_index[key]; ticker=str(source["ticker"]); sector,industry=classes.get(ticker,(None,None))
        relative_observations.append(relative_position.RelativeObservation(f"V:{company_id}",company_id,int(source["security_id"]),ticker,relative_position.RelativeMeasure.ABSOLUTE_VALUATION_SCORE,value.total_valuation_score,value.valuation_status,value.valuation_status=="VALUATION_FULL",value.reason_code,value.fundamental_available_date,valuation.MODEL_VERSION,valuation.MODEL_FINGERPRINT,value.result_fingerprint,sector,industry,tuple(memberships.get(company_id, ()))))
    relative=relative_position.calculate_snapshot(relative_observations,snapshot_date=as_of.isoformat(),freshness_days=FRESHNESS_DAYS,classification_fingerprint=fingerprint(classes),taxonomy_fingerprint=taxonomy_dependency["semantic_fingerprint"])

    diagnostics_full=[]
    diagnostic_source_rows=[]
    sequence_index = {
        (int(row["company_id"]), int(row["endpoint_fiscal_year"])*4+int(str(row["endpoint_fiscal_quarter"])[1])): row
        for row in rows
    }
    for row in rows:
        key=(int(row["company_id"]),int(row["endpoint_quarter_id"])); sequence=int(row["endpoint_fiscal_year"])*4+int(str(row["endpoint_fiscal_quarter"])[1]); prior=sequence_index.get((key[0],sequence-1))
        def endpoint(source):
            source_key=(int(source["company_id"]),int(source["endpoint_quarter_id"]))
            val=valuation_v2.get(source_key)
            scored=score_index[source_key]
            traj=next((item["component_score"] for item in scored["components"] if item["component_name"]=="FUNDAMENTAL_TRAJECTORY"),None)
            valuation_source = valuation_context_index.get(source_key, {})
            application=valuation.classify_applicability(valuation_source.get("sector"), valuation_source.get("industry"))
            diagnostic_classification="SUPPORTED" if application.supported is True else "NOT_APPLICABLE" if application.supported is False else "NOT_READY"
            return _diagnostic_endpoint(
                source,
                valuation_result=val,
                trajectory=traj,
                applicability_classification=diagnostic_classification,
                applicability_reason=application.reason_code,
            )
        current_endpoint=endpoint(row); prior_endpoint=endpoint(prior) if prior else None
        diagnostic_source_rows.append(asdict(current_endpoint))
        consecutive=bool(prior and _same_structural_regime(row, prior) and str(prior["period_end"])<str(row["period_end"]) and prior.get("ttm_source_available_date") and row.get("ttm_source_available_date") and str(prior["ttm_source_available_date"])<=str(row["ttm_source_available_date"]))
        canonical_consecutive=bool(prior and _same_structural_regime(row, prior) and str(prior["period_end"])<str(row["period_end"]) and prior.get("quarter_source_available_date") and row.get("quarter_source_available_date") and str(prior["quarter_source_available_date"])<=str(row["quarter_source_available_date"]))
        diagnostic_input=diagnostic_flags.DiagnosticInput(current_endpoint,prior_endpoint,consecutive,canonical_consecutive)
        for result in diagnostic_flags.evaluate_diagnostic_flags(diagnostic_input):
            diagnostics_full.append({"company_id":key[0],"quarter_id":key[1],"ticker":row["ticker"],"flag_name":result.flag_name,"status":result.status.value,"reason_code":result.reason_code,"triggered":result.triggered,"comparison_quarter_id":result.comparison_quarter_id,"effective_available_date":result.effective_available_date,"evidence":{item.name:item.value for item in result.evidence},"model_version":result.model_version,"model_fingerprint":result.model_fingerprint})
    diagnostics=[row for row in diagnostics_full if (row["company_id"],row["quarter_id"]) in fresh_keys]

    snapshot.validate_model_bundle({layer:snapshot.ModelIdentity(*identity) for layer,identity in snapshot.MODEL_CONTRACT["required_models"].items()})
    outputs={"as_of_date":as_of.isoformat(),"taxonomy_dependency":taxonomy_dependency,"rows":rows,"fresh":fresh,"structural_metadata":structural_metadata,"score_v2":v2_scores,"lifecycle_v2":life_v2,"valuation_source_rows":valuation_source_rows,"valuation_v2":valuation_v2,"delta_results":delta_results,"delta_full":delta_full,"delta_current":delta_current,"relative":relative,"diagnostic_source_fingerprint":fingerprint({"structural":structural_metadata,"rows":diagnostic_source_rows}),"diagnostics_full":diagnostics_full,"diagnostics":diagnostics}
    outputs["fingerprints"]={"structural":fingerprint(structural_metadata),"score":fingerprint(v2_scores),"lifecycle":fingerprint([asdict(life_v2[key]) for key in sorted(life_v2)]),"valuation":fingerprint([valuation_v2[key].to_dict() for key in sorted(valuation_v2)]),"delta":fingerprint(delta_full),"relative":relative.result_fingerprint,"diagnostic":fingerprint(diagnostics_full)}
    return outputs
