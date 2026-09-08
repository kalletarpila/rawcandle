from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any, Mapping

from rawcandle.fundamentals.operating_income_v2 import snapshot_eight
from rawcandle.fundamentals.snapshot import v2_assembler
from rawcandle.fundamentals.snapshot.assembler import SnapshotPaths

from .contract import CANDIDATE_REPORT_CONTRACT
from .engine import MODEL_FINGERPRINT, MODEL_VERSION, RelativeValuationSnapshot


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
