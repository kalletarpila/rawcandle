from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Mapping

from rawcandle.fundamentals.operating_income_v2 import snapshot_eight
from rawcandle.fundamentals.snapshot import v2_assembler
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths

from .contract import CANDIDATE_REPORT_CONTRACT, PRODUCTION_REPORT_CONTRACT
from .engine import MODEL_FINGERPRINT, MODEL_VERSION, RelativeValuationSnapshot
from .persistence import RelativeValuationRepository


CANDIDATE_SNAPSHOT_MODEL_VERSION = "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_RELATIVE_VALUATION_V1_CANDIDATE"
CANDIDATE_SNAPSHOT_CONTRACT = {
    "model_version": CANDIDATE_SNAPSHOT_MODEL_VERSION,
    "base_snapshot": (snapshot_eight.MODEL_VERSION, snapshot_eight.MODEL_FINGERPRINT),
    "relative_valuation": (MODEL_VERSION, MODEL_FINGERPRINT),
    "production_activation": False,
}
CANDIDATE_SNAPSHOT_FINGERPRINT = hashlib.sha256(
    json.dumps(CANDIDATE_SNAPSHOT_CONTRACT, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()
CANDIDATE_REPORT_SPEC = {
    "version": CANDIDATE_REPORT_CONTRACT,
    "base_presentation": v2_assembler.CANDIDATE_REPORT_PRESENTATION_FINGERPRINT,
    "relative_valuation_model": MODEL_FINGERPRINT,
    "section": "CURRENT_PEERS_AND_OWN_POSITIVE_YIELD_HISTORY",
    "production_default": False,
}
CANDIDATE_REPORT_PRESENTATION_FINGERPRINT = hashlib.sha256(
    json.dumps(CANDIDATE_REPORT_SPEC, sort_keys=True, separators=(",", ":")).encode("ascii")
).hexdigest()

PRODUCTION_SNAPSHOT_MODEL_VERSION = (
    "CURRENT_REVISED_COMPANY_SNAPSHOT_V2_RELATIVE_VALUATION_V1"
)
PRODUCTION_SNAPSHOT_CONTRACT = {
    "model_version": PRODUCTION_SNAPSHOT_MODEL_VERSION,
    "base_snapshot": (snapshot_eight.MODEL_VERSION, snapshot_eight.MODEL_FINGERPRINT),
    "relative_valuation": (MODEL_VERSION, MODEL_FINGERPRINT),
    "production_activation": True,
    "persistence_required": True,
}
PRODUCTION_SNAPSHOT_FINGERPRINT = hashlib.sha256(
    json.dumps(
        PRODUCTION_SNAPSHOT_CONTRACT, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
).hexdigest()
PRODUCTION_REPORT_SPEC = {
    "version": PRODUCTION_REPORT_CONTRACT,
    "base_presentation": v2_assembler.CANDIDATE_REPORT_PRESENTATION_FINGERPRINT,
    "relative_valuation_model": MODEL_FINGERPRINT,
    "section": "CURRENT_PEERS_AND_OWN_POSITIVE_YIELD_HISTORY",
    "production_default": True,
    "unavailable_state": "EXPLICIT_NO_ON_DEMAND_RECALCULATION",
}
PRODUCTION_REPORT_PRESENTATION_FINGERPRINT = hashlib.sha256(
    json.dumps(
        PRODUCTION_REPORT_SPEC, sort_keys=True, separators=(",", ":")
    ).encode("ascii")
).hexdigest()


def attach_relative_valuation_candidate(
    snapshot: Mapping[str, Any],
    relative_valuation: RelativeValuationSnapshot,
) -> dict[str, Any]:
    ticker = str(snapshot["identity"]["ticker"])
    matches = [row for row in relative_valuation.companies if row.ticker == ticker]
    if len(matches) != 1:
        raise ValueError(f"RELATIVE_VALUATION_CANDIDATE_TICKER_MATCH:{ticker}:{len(matches)}")
    output = dict(snapshot)
    output["relative_valuation"] = asdict(matches[0])
    output["relative_valuation_identity"] = {
        "model_version": relative_valuation.model_version,
        "model_fingerprint": relative_valuation.model_fingerprint,
        "source_fingerprint": relative_valuation.source_fingerprint,
        "result_fingerprint": relative_valuation.result_fingerprint,
        "as_of_date": relative_valuation.as_of_date,
    }
    output["report_contract"] = CANDIDATE_REPORT_CONTRACT
    output["report_presentation_fingerprint"] = CANDIDATE_REPORT_PRESENTATION_FINGERPRINT
    output["model_fingerprints"] = dict(output["model_fingerprints"])
    output["model_fingerprints"]["snapshot"] = CANDIDATE_SNAPSHOT_FINGERPRINT
    output["model_fingerprints"]["relative_valuation"] = MODEL_FINGERPRINT
    return output


def assemble_relative_valuation_candidate_snapshot(
    paths: SnapshotPaths,
    *,
    ticker: str,
    report_date: str,
    relative_valuation: RelativeValuationSnapshot,
) -> dict[str, Any]:
    if report_date != relative_valuation.as_of_date:
        raise ValueError("RELATIVE_VALUATION_CANDIDATE_AS_OF_MISMATCH")
    base = v2_assembler.assemble_company_snapshot_v2(paths, ticker=ticker, report_date=report_date)
    return attach_relative_valuation_candidate(base, relative_valuation)


def attach_persisted_relative_valuation_candidate(
    snapshot: Mapping[str, Any], repository: RelativeValuationRepository,
    *, model_fingerprint: str = MODEL_FINGERPRINT,
) -> dict[str, Any]:
    ticker = str(snapshot["identity"]["ticker"])
    persisted = repository.company_by_ticker(ticker, model_fingerprint=model_fingerprint)
    metadata = repository.active_metadata(model_fingerprint=model_fingerprint)
    if persisted is None or metadata is None:
        raise LookupError(f"RELATIVE_VALUATION_PERSISTED_RESULT_NOT_FOUND:{ticker}")
    current = {
        **dict(snapshot.get("current_price_valuation") or {}),
        "quarter_id": persisted["quarter_id"], "fiscal_year": persisted["fiscal_year"],
        "fiscal_quarter": persisted["fiscal_quarter"], "period_end": persisted["period_end"],
        "price_date": persisted["current_price_date"],
        "price_age_calendar_days": persisted["current_price_age_days"],
        "selected_price": persisted["current_price"], "valuation_status": persisted["valuation_status"],
        "reason_code": persisted["valuation_reason"],
        "total_valuation_score": persisted["current_valuation_score"],
        "market_cap": persisted["market_cap"], "enterprise_value": persisted["enterprise_value"],
        "operating_income_yield": persisted["operating_yield"], "fcf_yield": persisted["fcf_yield"],
        "earnings_yield": persisted["reported_earnings_yield"],
    }
    peer_results = []
    peer_coverage = []
    for row in persisted["peer_positions"]:
        coverage = {
            "company_id": persisted["company_id"], "peer_scope": row["scope"],
            "peer_group_id": row["group_id"] or None, "status": row["status"],
            "reason_code": row["reason_code"], "peer_count": row["peer_count"],
            "snapshot_date": metadata["as_of_date"],
        }
        peer_coverage.append(coverage)
        if row["rank_low"] is not None:
            peer_results.append({
                **coverage, "percentile": row["percentile"], "rank_low": row["rank_low"],
                "rank_high": row["rank_high"], "average_rank": row["average_rank"],
                "score": row["source_score"],
            })
    components = [{
        "component": row["component_type"], "current_yield": row["current_yield"],
        "historical_median_positive_yield": row["historical_positive_median"],
        "historical_percentile": row["historical_percentile"],
        "component_observation_count": row["eligible_observation_count"],
        "positive_history_count": row["positive_count"],
        "nonpositive_history_count": row["nonpositive_count"],
        "missing_or_invalid_history_count": row["missing_invalid_count"],
        "component_first_observation_date": row["observation_start_date"],
        "component_last_observation_date": row["observation_end_date"],
        "positive_history_start_date": row["positive_start_date"],
        "positive_history_end_date": row["positive_end_date"],
        "component_history_status": row["status"], "reason_code": row["reason_code"],
    } for row in persisted["components"]]
    own_row = persisted["own_history"]
    own = {
        "status": own_row["status"], "reason_code": own_row["reason_code"],
        "percentile": own_row["percentile"], "window_start_date": own_row["window_start_date"],
        "window_end_date": own_row["window_end_date"],
        "minimum_component_positive_history_count": own_row["minimum_positive_count"],
        "selected_endpoint_count": own_row["selected_endpoint_count"],
        "fiscal_gap_count": own_row["fiscal_gap_count"], "components": components,
    }
    filing = (snapshot.get("history") or [{}])[-1].get("valuation") or {
        "total_valuation_score": persisted["filing_valuation_score"]
    }
    filing_results = [
        row for row in (snapshot.get("relative_position") or {}).get("rows", [])
        if row.get("measure") == "ABSOLUTE_VALUATION_SCORE"
    ]
    output = dict(snapshot)
    output["relative_valuation"] = {
        "company_id": persisted["company_id"], "security_id": persisted["security_id"],
        "ticker": persisted["ticker"], "endpoint_available_date": persisted["endpoint_available_date"],
        "current_fresh": bool(persisted["current_fresh"]), "current_valuation": current,
        "filing_valuation": filing, "score_change_due_to_current_price": persisted["score_change"],
        "current_peer_results": peer_results, "current_peer_coverage": peer_coverage,
        "filing_peer_results": filing_results, "own_history": own,
    }
    output["relative_valuation_identity"] = {
        "model_version": metadata["model_version"], "model_fingerprint": metadata["model_fingerprint"],
        "source_fingerprint": metadata["source_fingerprint"], "result_fingerprint": metadata["result_fingerprint"],
        "as_of_date": metadata["as_of_date"], "snapshot_id": metadata["snapshot_id"],
    }
    output["report_contract"] = CANDIDATE_REPORT_CONTRACT
    output["report_presentation_fingerprint"] = CANDIDATE_REPORT_PRESENTATION_FINGERPRINT
    output["model_fingerprints"] = dict(output["model_fingerprints"])
    output["model_fingerprints"]["snapshot"] = CANDIDATE_SNAPSHOT_FINGERPRINT
    output["model_fingerprints"]["relative_valuation"] = MODEL_FINGERPRINT
    return output


def assemble_persisted_relative_valuation_candidate_snapshot(
    paths: SnapshotPaths, *, ticker: str, report_date: str,
    repository: RelativeValuationRepository,
) -> dict[str, Any]:
    metadata = repository.active_metadata(model_fingerprint=MODEL_FINGERPRINT)
    if metadata is None or metadata["as_of_date"] != report_date:
        raise ValueError("RELATIVE_VALUATION_CANDIDATE_AS_OF_MISMATCH")
    base = v2_assembler.assemble_company_snapshot_v2(paths, ticker=ticker, report_date=report_date)
    return attach_persisted_relative_valuation_candidate(base, repository)


def promote_persisted_relative_valuation_snapshot(
    snapshot: Mapping[str, Any], repository: RelativeValuationRepository,
) -> dict[str, Any]:
    output = attach_persisted_relative_valuation_candidate(snapshot, repository)
    output["report_contract"] = PRODUCTION_REPORT_CONTRACT
    output["report_presentation_fingerprint"] = (
        PRODUCTION_REPORT_PRESENTATION_FINGERPRINT
    )
    output["model_fingerprints"] = dict(output["model_fingerprints"])
    output["model_fingerprints"]["snapshot"] = PRODUCTION_SNAPSHOT_FINGERPRINT
    return output


def attach_relative_valuation_unavailable(
    snapshot: Mapping[str, Any], *, reason_code: str,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    output = dict(snapshot)
    output["relative_valuation_unavailable"] = {
        "reason_code": reason_code,
        "requested_as_of_date": snapshot["report_date"],
        "active_as_of_date": metadata.get("as_of_date") if metadata else None,
        "model_fingerprint": MODEL_FINGERPRINT,
    }
    output["report_contract"] = PRODUCTION_REPORT_CONTRACT
    output["report_presentation_fingerprint"] = (
        PRODUCTION_REPORT_PRESENTATION_FINGERPRINT
    )
    output["model_fingerprints"] = dict(output["model_fingerprints"])
    output["model_fingerprints"]["snapshot"] = PRODUCTION_SNAPSHOT_FINGERPRINT
    output["model_fingerprints"]["relative_valuation"] = MODEL_FINGERPRINT
    return output
