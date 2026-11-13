"""Ticker exclusion receipts for UPDATE_FETCH; never financial/source approval."""

from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
from uuid import uuid4

from . import acquisition_snapshot as a
from .refresh_fundamentals import resolve_identity
from rawcandle.fundamentals.generations import resolve_active_generation
from rawcandle.fundamentals.providers.sharadar import SharadarResult, parse_payload, payload_records

CONTRACT = "FUNDAMENTALS_TICKER_ACQUISITION_QUARANTINE_V1"
STATE = "LOCAL_ACQUISITION_QUARANTINE"


def reason(response, run, slot):
    try:
        _, coverage = a._history_response_coverage(run, slot, response)
    except a.SnapshotError as error:
        return str(error).removeprefix("UNFILTERED_RESPONSE_OR_CAPTURE_MISMATCH:")
    return "SOURCE_PROFILE_UNTRUSTWORTHY" if coverage["diagnostic_reasons"] else None


def classify(run, slot, response, project_root, plan, *, identity=None):
    """Positive request/body/OLD isolation; unknown/shared contract errors STOP."""
    if run.request["mode"] != "UPDATE_FETCH" or not response.ok:
        return None
    if (not isinstance(response.response_body, bytes)
        or response.parameters != a._parameters(run.request, slot)):
        return None
    event = a._transport_events(run).get(response.attempt_id, {})
    digest = hashlib.sha256(response.response_body).hexdigest()
    if (event.get("event") != "FINISHED" or event.get("http_status") != 200
        or event.get("endpoint") != a.ENDPOINT or event.get("parameters") != response.parameters
        or event.get("response_sha256") != digest
        or event.get("response_bytes") != len(response.response_body)
        or event.get("at_utc") != response.acquired_at_utc):
        return None
    failure = reason(response, run, slot)
    allowed = {
        "EMPTY_OR_LIMIT_COVERAGE_UNPROVEN", "SOURCE_IDENTITY_MISMATCH",
        "SOURCE_WINDOW_MISMATCH", "SOURCE_KEY_INVALID", "DUPLICATE_SOURCE_PRIMARY_KEY",
        "PAYLOAD_SHAPE_VALID", "PAYLOAD_CAPTURE_EQUAL", "SOURCE_PROFILE_UNTRUSTWORTHY",
    }
    if failure not in allowed:
        return None
    raw = payload_records(response.payload)
    # Preserve the native client's exact public filtering and original envelopes.
    # Other response/capture disagreement is a shared client-integrity failure.
    if [a.capture.raw_payload(r) for r in response.records] != [r for r in raw if r.get("dimension") == slot["dimension"]]:
        return None
    for row in response.records:
        source = a.capture.raw_payload(row)
        envelope = a.capture.envelope(row) or {}
        origin = envelope.get("acquisition_source") or {}
        if (envelope.get("policy") != a.capture.VERSION or envelope.get("authoritative_acquisition") is not True
            or envelope.get("capture_fingerprint") != a.capture.digest({k: v for k, v in envelope.items() if k != "capture_fingerprint"})
            or envelope.get("raw_payload_fingerprint") != a.capture.digest(source)
            or envelope.get("raw_key_set_fingerprint") != a.capture.digest(sorted(source))
            or envelope.get("raw_key_state_fingerprint") != a.capture.digest({k: a.capture.field_state(source, k) for k in sorted(source)})
            or origin.get("provider") != "SHARADAR" or origin.get("kind") != "FULL_HTTP_RESPONSE"
            or origin.get("endpoint") != a.ENDPOINT or origin.get("status") != "SUCCESS"
            or origin.get("source_path") != "https://api.sharadar.com/v1.0" + a.ENDPOINT
            or origin.get("response_sha256") != digest
            or origin.get("request_fingerprint") != a.capture.digest(response.parameters)
            or envelope.get("acquired_at_utc") != response.acquired_at_utc):
            return None
        profile = a.capture.profile_report(source, a.capture.BASE, capture=envelope)
        if not profile["capture_verified"]:
            # A reduced source projection is a real source defect. An invalid
            # envelope over a full payload is instead a shared client failure.
            projected = set(source) <= set(a.REFRESH_REQUEST_FIELDS) | {"permaticker", "observation_id"}
            if not projected or envelope.get("full_capture_shape_verified") is not False:
                return None
    tickers = {r.get("ticker") for r in raw}
    dimensions = {r.get("dimension") for r in raw}
    planned_tickers = {p["ticker"] for p in plan}
    # A response that mixes or impersonates another planned peer is shared risk.
    if len(tickers) > 1 or (tickers - {slot["ticker"]}) & planned_tickers:
        return None
    if failure == "PAYLOAD_SHAPE_VALID":
        payload = response.payload
        rows = payload if isinstance(payload, list) else payload.get("data") if isinstance(payload, dict) and set(payload) == {"count", "data"} else None
        if (not isinstance(rows, list) or not raw or tickers != {slot["ticker"]}
            or all(isinstance(r, dict) for r in rows)
            or (isinstance(payload, dict) and (type(payload["count"]) is not int or payload["count"] != len(rows)))):
            return None  # Unknown wrappers/pagination are shared source-contract errors.
    if failure == "PAYLOAD_CAPTURE_EQUAL":
        # Only the native client's documented dimension filtering is localizable.
        if (tickers != {slot["ticker"]} or not dimensions <= {"ARQ", "MRQ"}
            or dimensions == {slot["dimension"]}
            or [a.capture.raw_payload(r) for r in response.records]
            != [r for r in raw if r.get("dimension") == slot["dimension"]]):
            return None
    if project_root is not None:
        binding = resolve_active_generation(Path(project_root), require_generation=True)
        if (binding.generation_id != run.request["old_authority"]["generation_id"]
            or a.sha256_file(binding.manifest_path) != run.request["old_authority"]["manifest_sha256"]):
            raise a.SnapshotError("OLD_AUTHORITY_DRIFT")
        roles = binding.role_paths()
        identity = resolve_identity(SimpleNamespace(provider_db=roles["provider"], canonical_db=roles["canonical"]), slot["ticker"])
    identity = identity or {}
    if (identity.get("status") != "KNOWN"
        or not all(identity.get(k) for k in ("company_id", "security_id", "provider_security_id"))
        or any(identity.get(k) != slot["ticker"] for k in ("ticker", "current_ticker", "provider_ticker"))):
        return None
    # Foreign security IDs attached to the requested ticker cannot be isolated.
    if tickers == {slot["ticker"]} and any(
        str(row[key]) != str(identity["provider_security_id"])
        for row in raw for key in ("permaticker", "provider_security_id") if row.get(key) is not None
    ):
        return None
    if project_root is not None:
        with a.sqlite3.connect(f"file:{roles['canonical']}?mode=ro", uri=True) as db:
            peers = db.execute("SELECT current_ticker FROM security WHERE company_id=? AND current_ticker<>?", (identity["company_id"], slot["ticker"])).fetchall()
        if any(r[0] in planned_tickers for r in peers):
            return None
    # Empty history alone is not a schema signature. Repeated nonempty contract
    # contradictions across distinct requested tickers are shared-failure evidence.
    signature = None
    if failure in {"SOURCE_IDENTITY_MISMATCH", "PAYLOAD_CAPTURE_EQUAL", "PAYLOAD_SHAPE_VALID"}:
        signature = a.capture.digest({"reason": failure, "expected_dimension": slot["dimension"], "dimensions": sorted(str(d) for d in dimensions),
            "foreign_tickers": sorted(str(t) for t in tickers - {slot["ticker"]}),
            "key_sets": sorted({a.capture.digest(sorted(r)) for r in raw})})
    if failure == "SOURCE_PROFILE_UNTRUSTWORTHY" and raw:
        missing = sorted(set(a.capture.definitions(a.capture.BASE)[0]) - set.intersection(*(set(r) for r in raw)))
        if missing:
            signature = a.capture.digest({"shared_missing_source_fields": missing})
        elif any((a.capture.envelope(r) or {}).get("full_capture_shape_verified") is False for r in response.records):
            signature = a.capture.digest({"shared_reduced_projection": sorted({a.capture.digest(sorted(r)) for r in raw})})
    if failure == "SOURCE_WINDOW_MISMATCH":
        signature = a.capture.digest({"source_window_filter_failed": [run.request["horizon_from"], run.request["source_day"]]})
    return {"reason": failure, "identity": identity, "shared_failure_signature": signature}


def persist(run, slot, response, proof, diagnostic):
    """Atomic quarantine receipt is a disposition, not a successful checkpoint."""
    path = run.path(f"fetch/quarantines/{slot['slot']:06d}.json")
    if path.exists():
        raise a.SnapshotError("QUARANTINE_SLOT_ALREADY_COMMITTED")
    key = uuid4().hex
    body = f"fetch/quarantines/responses/{key}.body"
    captures = f"fetch/quarantines/captures/{key}.jsonl"
    a._atomic(run.path(body), response.response_body)
    a._atomic(run.path(captures), (a._json({"raw": a.capture.raw_payload(r), "envelope": a.capture.envelope(r)}).encode() for r in response.records))
    record = {"format": CONTRACT, "operation_id": run.operation_id,
        **{k: slot[k] for k in ("slot", "ticker", "dimension")}, "state": STATE,
        "affected_slots": [slot["slot"] // 2 * 2, slot["slot"] // 2 * 2 + 1],
        "old_authority": run.request["old_authority"], "request": run.ref("request.json", "REQUEST"),
        "parameters": response.parameters, "transport_attempt_id": response.attempt_id,
        "acquired_at_utc": response.acquired_at_utc, "content_type": (response.response_headers or {}).get("content-type", ""),
        "body": run.ref(body, "QUARANTINE_BODY"), "captures": run.ref(captures, "QUARANTINE_CAPTURES"),
        "captured_row_count": len(response.records),
        "diagnostic": {"relative_path": diagnostic, "sha256": a.sha256_file(run.path(diagnostic))},
        "history_complete": False, "incoming_financial_input_eligible": False,
        "absence_authorizes_deletion": False, "publication_authorized": False, **proof}
    a._write(path, record)
    a._append(run.path("fetch/quarantine_index.jsonl"), {"slot": slot["slot"], "receipt": run.ref(str(path.relative_to(run.directory)), "QUARANTINE")})
    return record


def load(run, control, project_root):
    """Replay real retained bytes/envelopes; never regenerate an attestation."""
    directory = run.path("fetch/quarantines")
    indexed = {}
    path = run.path("fetch/quarantine_index.jsonl")
    if path.exists():
        for item in a._lines(path, interrupted_tail=not bool(control.get("quarantine_index_reference"))):
            if item["slot"] in indexed:
                raise a.SnapshotError("DUPLICATE_QUARANTINE_INDEX")
            if a._read(run.verify(item["receipt"], "QUARANTINE"))["slot"] != item["slot"]:
                raise a.SnapshotError("QUARANTINE_INDEX_IDENTITY_MISMATCH")
            indexed[item["slot"]] = item["receipt"]
    if control.get("quarantine_index_reference"):
        run.verify(control["quarantine_index_reference"], "QUARANTINE_INDEX")
    plan = list(a._lines(run.verify(control["plan_reference"], "PLAN")))
    result = {}
    for path in sorted(directory.glob("*.json")) if directory.exists() else []:
        record = a._read(path)
        number = record.get("slot")
        if type(number) is not int or not 0 <= number < len(plan) or path.name != f"{number:06d}.json":
            raise a.SnapshotError("QUARANTINE_SLOT_IDENTITY_INVALID")
        slot = plan[number]
        if (record.get("format") != CONTRACT or record.get("state") != STATE
            or record.get("operation_id") != run.operation_id
            or any(record.get(k) != slot[k] for k in ("ticker", "dimension"))
            or record.get("old_authority") != run.request["old_authority"]
            or record.get("affected_slots") != [number // 2 * 2, number // 2 * 2 + 1]
            or any(record.get(k) is not False for k in ("history_complete", "incoming_financial_input_eligible", "absence_authorizes_deletion", "publication_authorized"))):
            raise a.SnapshotError("QUARANTINE_BINDING_INVALID")
        run.verify(record["request"], "REQUEST")
        body = run.verify(record["body"], "QUARANTINE_BODY")
        if body.stat().st_size > a.MAX_RESPONSE_BYTES:
            raise a.SnapshotError("QUARANTINE_RESPONSE_TOO_LARGE")
        a._bind_transport(run, record, a.ENDPOINT, a._parameters(run.request, slot))
        diagnostic = record["diagnostic"]
        if a.sha256_file(run.path(diagnostic["relative_path"])) != diagnostic["sha256"]:
            raise a.SnapshotError("QUARANTINE_DIAGNOSTIC_CHANGED")
        details = a._read(run.path(diagnostic["relative_path"]))
        if (details.get("operation_id") != run.operation_id or details.get("slot") != number
            or details.get("failed_predicate") != record["reason"]
            or details.get("accepted_snapshot_slot") is not False or details.get("publication_authorized") is not False
            or details.get("response_sha256") != record["body"]["sha256"]):
            raise a.SnapshotError("QUARANTINE_DIAGNOSTIC_BINDING_INVALID")
        payload = parse_payload(body.read_text(), record["content_type"])
        records = [{**x["raw"], "_acquisition_payload": x["raw"], "_capture_envelope": x["envelope"], "_capture_transport": a.capture.VERSION}
                   for x in a._lines(run.verify(record["captures"], "QUARANTINE_CAPTURES"))]
        if record.get("captured_row_count") != len(records):
            raise a.SnapshotError("QUARANTINE_CAPTURE_COUNT_MISMATCH")
        response = SharadarResult("SUCCESS", "AUTH_OK", 200, a.ENDPOINT, "", 0, records,
            payload=payload, response_body=body.read_bytes(), parameters=record["parameters"],
            response_headers={"content-type": record["content_type"]}, acquired_at_utc=record["acquired_at_utc"], attempt_id=record["transport_attempt_id"])
        proof = classify(run, slot, response, project_root, plan, identity=record.get("identity"))
        if proof is None or any(record.get(k) != v for k, v in proof.items()):
            raise a.SnapshotError("QUARANTINE_LOCALITY_UNPROVEN")
        result[number] = record
    if (set(indexed) - set(result) or len(result) < control.get("committed_quarantine_slots", 0)
        or (control.get("quarantine_index_reference") and set(indexed) != set(result))):
        raise a.SnapshotError("DECLARED_QUARANTINE_MISSING")
    check_shared(result)
    return result


def check_shared(records):
    owners = {}
    for record in records.values():
        signature = record.get("shared_failure_signature")
        if signature:
            owners.setdefault(signature, set()).add(record["ticker"])
    if any(len(tickers) > 1 for tickers in owners.values()):
        raise a.SnapshotError("SHARED_ACQUISITION_SOURCE_CONTRACT_FAILURE")


def require_peer_control(checkpoints, records):
    check_shared(records)
    quarantined = {r["ticker"] for r in records.values()}
    paired = {}
    for receipt in checkpoints.values():
        if receipt["state"] == "COMPLETE_VERIFIED" and receipt["ticker"] not in quarantined:
            paired.setdefault(receipt["ticker"], set()).add(receipt["dimension"])
    if not any(dimensions == {"ARQ", "MRQ"} for dimensions in paired.values()):
        raise a.SnapshotError("ACQUISITION_LOCALITY_WITHOUT_VALID_PEER_CONTROL")


def write_index(run, records):
    a._atomic(run.path("fetch/quarantine_index.jsonl"), b"".join(a._json({"slot": n, "receipt": run.ref(f"fetch/quarantines/{n:06d}.json", "QUARANTINE")}).encode() for n in sorted(records)))


def statistics(checkpoints, records, total):
    tickers = {r["ticker"] for r in records.values()}
    return {"quarantined_tickers": len(tickers), "quarantined_slots": len(tickers) * 2,
        "accounted_quarantine_slots": len(records), "accounted_slots": len(checkpoints) + len(records),
        "pending_slots": total - len(checkpoints) - len(records),
        "nonquarantined_verified_slots": sum(r["ticker"] not in tickers and r["state"] == "COMPLETE_VERIFIED" for r in checkpoints.values())}
