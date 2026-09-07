from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from rawcandle.fundamentals.diagnostic_flags import persistence as diagnostic_v1

from . import (
    activation,
    contract,
    diagnostic_flags,
    diagnostic_flags_eight,
    persistence,
    rehearsal,
    snapshot_eight,
    valuation,
)
from .readers import ParallelModelRepository


PERSISTENCE_VERSION = "OPERATING_INCOME_V2_PARALLEL_PERSISTENCE_V2"
MODEL_MAP = {
    **persistence.MODEL_MAP,
    "diagnostic_flags": (
        diagnostic_flags_eight.MODEL_VERSION,
        diagnostic_flags_eight.MODEL_FINGERPRINT,
    ),
    "snapshot": (snapshot_eight.MODEL_VERSION, snapshot_eight.MODEL_FINGERPRINT),
}
PACKAGE_FINGERPRINT = contract.fingerprint({
    "persistence_version": PERSISTENCE_VERSION,
    "family_fingerprint": contract.FAMILY_FINGERPRINT,
    "models": MODEL_MAP,
    "tables": "existing versioned tables; eight-flag diagnostic package; 16-slot evidence layout",
})


@dataclass(frozen=True)
class CandidateApplyReport:
    outcome: str
    economic_result_fingerprint: str
    physical_content_fingerprint: str
    diagnostic_source_fingerprint: str
    diagnostic_economic_fingerprint: str
    diagnostic_physical_fingerprint: str
    rows: dict[str, int]
    logical_changes: int


def _candidate_endpoint(
    source: Mapping[str, Any],
    base: diagnostic_flags.DiagnosticEndpoint,
    *,
    coherent: bool,
) -> diagnostic_flags_eight.DiagnosticEndpoint:
    return diagnostic_flags_eight.DiagnosticEndpoint(
        **asdict(base),
        ebit=source.get("ttm_ebit"),
        ttm_endpoint_coherent=coherent,
    )


def _ttm_input_audit(canonical_path: Path) -> dict[int, dict[str, Any]]:
    connection = sqlite3.connect(f"file:{canonical_path.resolve()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    grouped: dict[int, list[sqlite3.Row]] = {}
    try:
        for row in connection.execute(
            "SELECT i.*,q.company_id FROM v4_ttm_input_quarter i "
            "JOIN v4_quarter q ON q.quarter_id=i.input_quarter_id "
            "ORDER BY i.ttm_id,i.input_position"
        ):
            grouped.setdefault(int(row["ttm_id"]), []).append(row)
    finally:
        connection.close()
    audit = {}
    for ttm_id, items in grouped.items():
        source_sequences = tuple(
            int(item["input_fiscal_year"]) * 4 + int(str(item["input_fiscal_quarter"])[1])
            for item in items
        )
        audit[ttm_id] = {
            "count": len(items),
            "positions": tuple(int(item["input_position"]) for item in items),
            "sequences": source_sequences,
            "companies": tuple(sorted({int(item["company_id"]) for item in items})),
            "max_available": max(
                (str(item["source_availability_date"]) for item in items if item["source_availability_date"]),
                default=None,
            ),
        }
    return audit


def calculate(paths: Mapping[str, Path]) -> dict[str, Any]:
    calculated = rehearsal.calculate(paths)
    input_audit = _ttm_input_audit(paths["canonical"])
    rows = calculated["rows"]
    ttm_by_key = {
        (int(row["company_id"]), int(row["endpoint_quarter_id"])): row
        for row in rows
    }
    valuations = calculated["valuation_v2"]
    valuation_sources = {
        (int(row["company_id"]), int(row["quarter_id"])): row
        for row in calculated["valuation_v1_rows"]
    }
    score_rows = {
        (int(row["company_id"]), int(row["quarter_id"])): row
        for row in calculated["score_v2"]
    }
    sequence_index = {
        (
            int(row["company_id"]),
            int(row["endpoint_fiscal_year"]) * 4
            + int(str(row["endpoint_fiscal_quarter"])[1]),
        ): row
        for row in rows
    }
    source_payload = []
    candidate_results = []
    old_by_key = {}
    for row in calculated["diagnostics_full"]:
        old_by_key[(int(row["company_id"]), int(row["quarter_id"]), str(row["flag_name"]))] = row

    def endpoint(source: Mapping[str, Any]) -> diagnostic_flags_eight.DiagnosticEndpoint:
        key = (int(source["company_id"]), int(source["endpoint_quarter_id"]))
        scored = score_rows[key]
        trajectory = next(
            (item["component_score"] for item in scored["components"] if item["component_name"] == "FUNDAMENTAL_TRAJECTORY"),
            None,
        )
        valuation_source = valuation_sources.get(key, {})
        application = valuation.classify_applicability(
            valuation_source.get("sector"), valuation_source.get("industry")
        )
        classification = (
            "SUPPORTED" if application.supported is True
            else "NOT_APPLICABLE" if application.supported is False
            else "NOT_READY"
        )
        base = rehearsal._diagnostic_endpoint(
            source,
            valuation_result=valuations.get(key),
            trajectory=trajectory,
            applicability_classification=classification,
            applicability_reason=application.reason_code,
        )
        audit = input_audit.get(int(source["ttm_id"]), {})
        endpoint_sequence = int(source["endpoint_fiscal_year"]) * 4 + int(str(source["endpoint_fiscal_quarter"])[1])
        coherent = (
            audit.get("count") == 4
            and audit.get("positions") == (1, 2, 3, 4)
            and audit.get("sequences") == tuple(range(endpoint_sequence - 3, endpoint_sequence + 1))
            and audit.get("companies") == (int(source["company_id"]),)
            and audit.get("max_available") == source.get("ttm_source_available_date")
            and bool(source.get("ebit_4q_ready"))
            and bool(source.get("operating_income_4q_ready"))
            and bool(source.get("revenue_4q_ready"))
            and bool(source.get("ttm_source_available_date"))
        )
        return _candidate_endpoint(source, base, coherent=coherent)

    for row in rows:
        key = (int(row["company_id"]), int(row["endpoint_quarter_id"]))
        sequence = int(row["endpoint_fiscal_year"]) * 4 + int(str(row["endpoint_fiscal_quarter"])[1])
        prior_source = sequence_index.get((key[0], sequence - 1))
        current = endpoint(row)
        prior = endpoint(prior_source) if prior_source else None
        source_payload.append(asdict(current))
        consecutive = bool(
            prior_source
            and str(prior_source["period_end"]) < str(row["period_end"])
            and prior_source.get("ttm_source_available_date")
            and row.get("ttm_source_available_date")
            and str(prior_source["ttm_source_available_date"]) <= str(row["ttm_source_available_date"])
        )
        canonical_consecutive = bool(
            prior_source
            and str(prior_source["period_end"]) < str(row["period_end"])
            and prior_source.get("quarter_source_available_date")
            and row.get("quarter_source_available_date")
            and str(prior_source["quarter_source_available_date"]) <= str(row["quarter_source_available_date"])
        )
        inputs = diagnostic_flags_eight.DiagnosticInput(current, prior, consecutive, canonical_consecutive)
        evaluations = diagnostic_flags_eight.evaluate_diagnostic_flags(inputs)
        if len(evaluations) != 8:
            raise RuntimeError(f"PHASE10B_DIAGNOSTIC_COUNT:{key}")
        for result in evaluations:
            item = {
                "company_id": key[0],
                "quarter_id": key[1],
                "ticker": row["ticker"],
                "flag_name": result.flag_name,
                "status": result.status.value,
                "reason_code": result.reason_code,
                "triggered": result.triggered,
                "comparison_quarter_id": result.comparison_quarter_id,
                "effective_available_date": result.effective_available_date,
                "evidence": {value.name: value.value for value in result.evidence},
                "model_version": result.model_version,
                "model_fingerprint": result.model_fingerprint,
            }
            if result.flag_name in diagnostic_flags.FLAG_NAMES:
                old = old_by_key[(key[0], key[1], result.flag_name)]
                for field in ("flag_name", "status", "reason_code", "triggered", "comparison_quarter_id", "effective_available_date", "evidence"):
                    if item[field] != old[field]:
                        raise RuntimeError(f"PHASE10B_SEVEN_FLAG_REGRESSION:{key}:{result.flag_name}:{field}")
            candidate_results.append(item)

    calculated["diagnostics_full"] = candidate_results
    calculated["diagnostic_source_fingerprint"] = persistence._hash(source_payload)
    fresh_keys = {
        (int(row["company_id"]), int(row["endpoint_quarter_id"]))
        for row in calculated["fresh"]
    }
    calculated["diagnostics"] = [
        row for row in candidate_results
        if (int(row["company_id"]), int(row["quarter_id"])) in fresh_keys
    ]
    calculated["fingerprints"]["diagnostic"] = persistence._hash(candidate_results)
    return calculated


def _candidate_manifest(conn: sqlite3.Connection) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    for table in (persistence.MANIFEST_TABLE, persistence.MANIFEST_HISTORY_TABLE):
        if not conn.execute("SELECT 1 FROM sqlite_schema WHERE type='table' AND name=?", (table,)).fetchone():
            continue
        row = conn.execute(
            f"SELECT * FROM {table} WHERE persistence_fingerprint=?",
            (PACKAGE_FINGERPRINT,),
        ).fetchone()
        if row is not None:
            return row
    return None


def _validate(calculated: Mapping[str, Any]) -> None:
    groups: dict[tuple[int, int], set[str]] = {}
    for row in calculated["diagnostics_full"]:
        key = (int(row["company_id"]), int(row["quarter_id"]))
        groups.setdefault(key, set()).add(str(row["flag_name"]))
        if row["model_fingerprint"] != diagnostic_flags_eight.MODEL_FINGERPRINT:
            raise ValueError(f"PHASE10B_DIAGNOSTIC_MODEL_MISMATCH:{key}")
    expected = set(diagnostic_flags_eight.FLAG_NAMES)
    if any(names != expected for names in groups.values()):
        raise ValueError("PHASE10B_EIGHT_FLAG_ENDPOINT_CONTRACT")
    repository_keys = {
        (int(row["company_id"]), int(row["endpoint_quarter_id"]))
        for row in calculated["rows"]
    }
    if set(groups) != repository_keys:
        raise ValueError("PHASE10B_ENDPOINT_SET_MISMATCH")


def apply_candidate_package(
    conn: sqlite3.Connection,
    calculated: Mapping[str, Any],
    *,
    applied_at: str,
    inject_failure_at: str | None = None,
    stage_callback: Callable[[str, sqlite3.Connection], None] | None = None,
) -> CandidateApplyReport:
    _validate(calculated)
    persistence.ensure_schema(conn)
    target = persistence.economic_fingerprint(calculated)
    existing = _candidate_manifest(conn)
    if existing is not None and existing["economic_result_fingerprint"] == target:
        physical = persistence.physical_fingerprint(conn, diagnostic_model=diagnostic_flags_eight)
        if physical != existing["physical_content_fingerprint"]:
            raise RuntimeError("PHASE10B_PHYSICAL_CONTENT_CHANGED")
        package = conn.execute(
            f"SELECT source_fingerprint,economic_result_fingerprint,physical_content_fingerprint "
            f"FROM {diagnostic_v1.PACKAGE_TABLE} WHERE model_fingerprint=?",
            (diagnostic_flags_eight.MODEL_FINGERPRINT,),
        ).fetchone()
        return CandidateApplyReport(
            "NO_CHANGE", target, physical, package[0], package[1], package[2],
            persistence.row_counts(conn, diagnostic_model=diagnostic_flags_eight), 0,
        )

    conn.execute("BEGIN IMMEDIATE")
    try:
        persistence._archive_current_manifest(conn)
        persistence._apply_diagnostics(
            conn,
            calculated,
            applied_at,
            diagnostic_model=diagnostic_flags_eight,
            persistence_version=PERSISTENCE_VERSION,
        )
        if stage_callback:
            stage_callback("diagnostic", conn)
        if inject_failure_at == "diagnostic":
            raise RuntimeError("INJECTED_PHASE10B_DIAGNOSTIC_FAILURE")
        physical = persistence.physical_fingerprint(conn, diagnostic_model=diagnostic_flags_eight)
        conn.execute(
            f"INSERT OR REPLACE INTO {persistence.MANIFEST_TABLE} VALUES(?,?,?,?,?,?,?,'COMPLETE',?)",
            (
                contract.FAMILY_FINGERPRINT,
                contract.FAMILY_VERSION,
                PERSISTENCE_VERSION,
                PACKAGE_FINGERPRINT,
                json.dumps(MODEL_MAP, sort_keys=True, separators=(",", ":")),
                target,
                physical,
                applied_at,
            ),
        )
        if stage_callback:
            stage_callback("manifest", conn)
        persistence._archive_current_manifest(conn)
        if inject_failure_at == "manifest":
            raise RuntimeError("INJECTED_PHASE10B_MANIFEST_FAILURE")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    package = conn.execute(
        f"SELECT source_fingerprint,economic_result_fingerprint,physical_content_fingerprint "
        f"FROM {diagnostic_v1.PACKAGE_TABLE} WHERE model_fingerprint=?",
        (diagnostic_flags_eight.MODEL_FINGERPRINT,),
    ).fetchone()
    rows = persistence.row_counts(conn, diagnostic_model=diagnostic_flags_eight)
    return CandidateApplyReport(
        "APPLIED", target, physical, package[0], package[1], package[2], rows,
        rows["diagnostic_endpoint"] + rows["diagnostic_evaluation"],
    )


def validate_candidate_package(conn: sqlite3.Connection) -> dict[str, Any]:
    ParallelModelRepository(conn).assert_v2_bundle(
        MODEL_MAP,
        persistence_fingerprint=PACKAGE_FINGERPRINT,
    )
    rows = persistence.row_counts(conn, diagnostic_model=diagnostic_flags_eight)
    expected = 50_585
    if rows["diagnostic_endpoint"] != expected or rows["diagnostic_evaluation"] != expected * 8:
        raise RuntimeError("PHASE10B_PERSISTED_ROW_COUNT_MISMATCH")
    duplicates = conn.execute(
        f"SELECT COUNT(*) FROM (SELECT e.package_id,e.company_id,e.fiscal_sequence,v.flag_id,COUNT(*) n "
        f"FROM {diagnostic_v1.ENDPOINT_TABLE} e JOIN {diagnostic_v1.EVALUATION_TABLE} v USING(endpoint_id) "
        f"WHERE e.package_id=(SELECT package_id FROM {diagnostic_v1.PACKAGE_TABLE} WHERE model_fingerprint=?) "
        "GROUP BY e.package_id,e.company_id,e.fiscal_sequence,v.flag_id HAVING n<>1)",
        (diagnostic_flags_eight.MODEL_FINGERPRINT,),
    ).fetchone()[0]
    orphans = conn.execute(
        f"SELECT COUNT(*) FROM {diagnostic_v1.EVALUATION_TABLE} v LEFT JOIN {diagnostic_v1.ENDPOINT_TABLE} e USING(endpoint_id) WHERE e.endpoint_id IS NULL"
    ).fetchone()[0]
    if duplicates or orphans:
        raise RuntimeError("PHASE10B_PERSISTENCE_RELATIONSHIP_INVALID")
    return {
        "ok": True,
        "counts": rows,
        "duplicates": duplicates,
        "orphans": orphans,
        "quick_check": conn.execute("PRAGMA quick_check").fetchone()[0],
        "foreign_key_violations": list(conn.execute("PRAGMA foreign_key_check")),
        "physical_content_fingerprint": persistence.physical_fingerprint(
            conn, diagnostic_model=diagnostic_flags_eight
        ),
    }


ACTIVE_PACKAGE_FINGERPRINT = persistence.PACKAGE_FINGERPRINT
assert ACTIVE_PACKAGE_FINGERPRINT == "a36d6903c3d640da5e9bd7034faee700b7b064e74ea871880c1bfa2348f4964d"
