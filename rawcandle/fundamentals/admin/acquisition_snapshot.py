"""Inert singleton FETCH foundation. No financial route calls this module.

COMPLETE_VERIFIED means a native, bounded *request window*, never lifetime
history or publication permission. OLD outside that window remains authoritative.
"""

from __future__ import annotations

from contextlib import contextmanager
from itertools import islice
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from uuid import uuid4

from rawcandle.io_atomic import write_text_atomic
from rawcandle.fundamentals import source_capture as capture
from rawcandle.fundamentals.generations import resolve_active_generation
from rawcandle.fundamentals.providers.sharadar import (
    SharadarClient,
    STATUS_RATE_LIMITED,
    extract_schema_fields,
    payload_records,
)
from .artifacts import ADMIN_RUN_ROOT, AdminRunWriter, sha256_file
from .contracts import AdminOperationType
from .redaction import redact_text
from .refresh_fundamentals import (
    REFRESH_REQUEST_FIELDS,
    SOURCE_PRIMARY_KEY,
    source_key,
    validate_complete_history,
)
from .workflow_evidence import trusted_path
from . import acquisition_quarantine as quarantine

FORMAT = "FUNDAMENTALS_ACQUISITION_SNAPSHOT_V1"
LEGACY_POLICY = "SINGLETON_ARQ_MRQ_WINDOW_V1"
POLICY = "SINGLETON_ARQ_MRQ_WINDOW_V2"
MAX_AGE_SECONDS = 168 * 3600
LIMIT = 10000
MAX_CONTROL = 64 * 1024
MAX_LINE = 64 * 1024
MAX_RESPONSE_BYTES = 64 * 1024 * 1024
ENDPOINT = "/data/fundamentals"
NORMALIZATION = "NATIVE_SHARADAR_FINANCIAL_V1"
KINDS = {
    "REQUEST": r"request\.json",
    "PLAN": r"fetch/acquisition_plan\.jsonl",
    "INDEX": r"fetch/checkpoint_index\.jsonl",
    "ATTEMPTS": r"fetch/attempts\.jsonl",
    "BODY": r"fetch/responses/[a-f0-9]{32}\.body",
    "CAPTURES": r"fetch/captures/[a-f0-9]{32}\.jsonl",
    "CHECKPOINT": r"fetch/checkpoints/[0-9]{6}\.json",
    "ANCHORS": r"fetch/anchors/[0-9]{6}\.jsonl",
    "SCHEMA": r"fetch/schema_receipt\.json",
    "MANIFEST": r"fetch/snapshot_manifest\.json",
    "QUARANTINE": r"fetch/quarantines/[0-9]{6}\.json",
    "QUARANTINE_BODY": r"fetch/quarantines/responses/[a-f0-9]{32}\.body",
    "QUARANTINE_CAPTURES": r"fetch/quarantines/captures/[a-f0-9]{32}\.jsonl",
    "QUARANTINE_INDEX": r"fetch/quarantine_index\.jsonl",
}


class SnapshotError(ValueError):
    pass


def _now():
    return datetime.now(timezone.utc)


def _time(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, AttributeError) as exc:
        raise SnapshotError("ACQUISITION_TIMESTAMP_INVALID") from exc


def _json(value):
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    )


def _sync(directory):
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic(path, data):
    """Native atomic-file pattern, extended for unchanged binary source bytes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".fetch-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            if isinstance(data, bytes):
                stream.write(data)
            else:
                for chunk in data:
                    if len(chunk) > MAX_LINE:
                        raise SnapshotError("CHILD_LINE_BUDGET_EXCEEDED")
                    stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync(path.parent)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _write(path, value):
    text = _json(value)
    if len(text.encode()) > MAX_CONTROL:
        raise SnapshotError("CONTROL_BUDGET_EXCEEDED")
    write_text_atomic(path, text)
    _sync(path.parent)


def _read(path):
    if path.stat().st_size > MAX_CONTROL:
        raise SnapshotError("CONTROL_BUDGET_EXCEEDED")
    try:
        result = json.loads(path.read_text())
        if not isinstance(result, dict):
            raise ValueError()
        return result
    except (ValueError, UnicodeError) as exc:
        raise SnapshotError("CONTROL_INVALID") from exc


def _lines(path, *, interrupted_tail=False):
    with path.open("rb") as stream:
        while line := stream.readline(MAX_LINE + 1):
            if interrupted_tail and not line.endswith(b"\n") and len(line) <= MAX_LINE:
                return  # unsealed index tail is not a committed receipt
            if len(line) > MAX_LINE or not line.endswith(b"\n"):
                raise SnapshotError("INDEX_LINE_INVALID")
            try:
                yield json.loads(line)
            except (ValueError, UnicodeError) as exc:
                raise SnapshotError("INDEX_LINE_INVALID") from exc


def _append(path, value):
    data = _json(value).encode()
    if len(data) > MAX_LINE:
        raise SnapshotError("INDEX_LINE_BUDGET_EXCEEDED")
    with path.open("ab") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    _sync(path.parent)


def pin_old_authority(project_root):
    """Read-only binding to a native immutable generation; never runs recovery."""
    active = resolve_active_generation(Path(project_root), require_generation=True)
    roles = {}
    for role, path in active.role_paths().items():
        digest = sha256_file(path)
        if active.manifest["role_verification"][role]["sha256"] != digest:
            raise SnapshotError("OLD_ROLE_INTEGRITY_MISMATCH")
        roles[role] = {"sha256": digest, "size_bytes": path.stat().st_size}
    return {
        "generation_id": active.generation_id,
        "manifest_sha256": sha256_file(active.manifest_path),
        "roles": roles,
    }


def _age(timestamps, now):
    if not timestamps:
        return None
    oldest, newest = min(timestamps), max(timestamps)
    if newest > now or now - oldest > timedelta(seconds=MAX_AGE_SECONDS):
        raise SnapshotError("SNAPSHOT_EXPIRED_OR_FUTURE_TIMESTAMP")
    return (now - oldest).total_seconds()


class _Run:
    def __init__(self, root, operation_id):
        self.root = Path(root).absolute()
        for part in (self.root, *self.root.parents):
            if part.is_symlink():
                raise SnapshotError("RUN_ROOT_UNTRUSTED")
        # Reuse native run-ID and trusted root-file checks.
        trusted_path(self.root, operation_id, "request.json")
        self.operation_id = operation_id
        self.directory = self.root / operation_id
        self.request = _read(self.directory / "request.json")
        if (
            self.request.get("operation_id") != operation_id
            or self.request.get("mode") not in {"ACQUISITION_ONLY", "UPDATE_FETCH"}
            or self.request.get("format") != FORMAT
            or self.request.get("policy") not in (LEGACY_POLICY, POLICY)
            or self.request.get("max_age_seconds") != MAX_AGE_SECONDS
            or self.request.get("capture_version") != capture.VERSION
            or self.request.get("normalization_version") != NORMALIZATION
        ):
            raise SnapshotError("OPERATION_OR_POLICY_MISMATCH")
        if self.request["mode"] == "UPDATE_FETCH":
            _validate_update_binding(self.request.get("update_binding"))

    def path(self, relative):
        if not isinstance(relative, str) or "\\" in relative:
            raise SnapshotError("ARTIFACT_PATH_INVALID")
        parts = Path(relative).parts
        if (
            not parts
            or Path(relative).is_absolute()
            or any(p in (".", "..") for p in parts)
        ):
            raise SnapshotError("ARTIFACT_PATH_INVALID")
        path = self.directory
        for part in parts:
            path = path / part
            if path.is_symlink():
                raise SnapshotError("ARTIFACT_PATH_UNTRUSTED")
        if self.directory not in path.resolve().parents:
            raise SnapshotError("ARTIFACT_PATH_INVALID")
        return path

    def ref(self, relative, kind):
        if (
            kind not in KINDS
            or not isinstance(relative, str)
            or not re.fullmatch(KINDS[kind], relative)
        ):
            raise SnapshotError("ARTIFACT_TYPE_INVALID")
        path = self.path(relative)
        if not path.is_file():
            raise SnapshotError("ARTIFACT_MISSING")
        return {
            "operation_id": self.operation_id,
            "kind": kind,
            "relative_path": relative,
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }

    def verify(self, ref, kind):
        if not isinstance(ref, dict) or ref.get("operation_id") != self.operation_id:
            raise SnapshotError("REFERENCE_OPERATION_MISMATCH")
        if self.ref(ref.get("relative_path"), kind) != ref:
            raise SnapshotError("ARTIFACT_INTEGRITY_MISMATCH")
        return self.path(ref["relative_path"])

    @contextmanager
    def lock(self):
        path = self.path("fetch/operation.lock")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise SnapshotError("FETCH_ALREADY_RUNNING") from exc
            yield
        finally:
            os.close(fd)

    def control(self):
        control = _read(self.path("fetch/control.json"))
        self.verify(control["request_reference"], "REQUEST")
        self.verify(control["plan_reference"], "PLAN")
        return control

    def progress(self, status, complete, diagnostic, total, **extra):
        value = {
            "format": FORMAT,
            "operation_id": self.operation_id,
            "mode": self.request["mode"],
            "status": status,
            "complete_verified_slots": complete,
            "diagnostic_slots": diagnostic,
            "total_slots": total,
            "publication_authorized": False,
            "future_test_authorized": False,
            "future_production_authorized": False,
            **extra,
        }
        if getattr(self, "quarantine_progress", None):
            value.update(self.quarantine_progress())
        _write(self.path("result.json"), value)
        callback = getattr(self,"progress_callback",None)
        if callback:
            callback({"current_stage_id":"FETCH","stage_state":status,
                      "processed_items":value.get("accounted_slots",complete+diagnostic),"total_items":total,
                      "actual_http_attempts":extra.get("actual_http_attempts",0),
                      **{k:value[k] for k in ("quarantined_tickers", "quarantined_slots", "pending_slots", "nonquarantined_verified_slots") if k in value},
                      "message":extra.get("reason",status)})
        if status != "FETCHING":
            # Native top-level artifact manifest covers the bounded reference;
            # that reference recursively binds the large source children.
            if extra.get("snapshot_reference"):
                _write(
                    self.path("acquisition_snapshot_reference.json"),
                    {
                        "operation_id": self.operation_id,
                        "mode": self.request["mode"],
                        "publication_authorized": False,
                        "manifest": extra["snapshot_reference"],
                    },
                )
            write_text_atomic(
                self.path("operation_report.md"),
                "# Fundamentals acquisition only\n\n"
                f"Operation: {self.operation_id}\n\nStatus: {status}\n\n"
                "No financial publication authorization. Source details are in fetch/.\n",
            )
            AdminRunWriter(
                self.operation_id,
                AdminOperationType.REFRESH_FUNDAMENTALS,
                root=self.root,
            ).write_manifest()
            _sync(self.directory)
        return value


def _parameters(request, slot):
    return {
        "ticker": slot["ticker"],
        "dimension": slot["dimension"],
        "from": request["horizon_from"],
        "to": request["source_day"],
        "limit": str(LIMIT),
        "format": "json",
        "sort": "date.asc",
    }


def _coverage(run, slot, records, body_hash, acquired_at):
    """Verify the entire unfiltered response, not fundamentals()' filtered view."""
    request = run.request
    if not records or len(records) >= LIMIT:
        raise SnapshotError("EMPTY_OR_LIMIT_COVERAGE_UNPROVEN")
    keys = set()
    diagnostics = set()
    for row in records:
        raw, envelope = capture.raw_payload(row), capture.envelope(row)
        if (
            raw.get("ticker") != slot["ticker"]
            or raw.get("dimension") != slot["dimension"]
        ):
            raise SnapshotError("SOURCE_IDENTITY_MISMATCH")
        if not envelope:
            raise SnapshotError("ORIGINAL_CAPTURE_MISSING")
        if (
            envelope.get("capture_fingerprint")
            != capture.digest(
                {k: v for k, v in envelope.items() if k != "capture_fingerprint"}
            )
            or envelope.get("raw_payload_fingerprint") != capture.digest(raw)
            or envelope.get("raw_key_set_fingerprint") != capture.digest(sorted(raw))
            or envelope.get("raw_key_state_fingerprint")
            != capture.digest({k: capture.field_state(raw, k) for k in sorted(raw)})
        ):
            raise SnapshotError("ORIGINAL_CAPTURE_CORRUPT")
        origin = envelope.get("acquisition_source") or {}
        if (
            origin.get("response_sha256") != body_hash
            or origin.get("request_fingerprint")
            != capture.digest(_parameters(request, slot))
            or envelope.get("acquired_at_utc") != acquired_at
        ):
            raise SnapshotError("CAPTURE_RESPONSE_BINDING_MISMATCH")
        # Normalize exact source identity independently of financial eligibility.
        try:
            key = tuple(str(raw[k]) for k in SOURCE_PRIMARY_KEY)
            filing = date.fromisoformat(raw["date"])
            date.fromisoformat(raw["reportperiod"])
        except (KeyError, ValueError, TypeError) as exc:
            raise SnapshotError("SOURCE_KEY_INVALID") from exc
        if key in keys:
            raise SnapshotError("DUPLICATE_SOURCE_PRIMARY_KEY")
        keys.add(key)
        if not request["horizon_from"] <= filing.isoformat() <= request["source_day"]:
            raise SnapshotError("SOURCE_WINDOW_MISMATCH")
        for profile in (capture.BASE, capture.FREEZE):
            # The body/raw equality and original envelope are independently
            # bound above/on replay. Validate that exact pair, including
            # diagnostic rows whose normalized projection is itself invalid.
            # Reconstructing a fresh acquisition envelope is never needed.
            report = capture.profile_report(raw, profile, capture=envelope)
            if not report["eligible_authoritative_full_source"]:
                # An original projected/defective native response is diagnostic,
                # never safe finance. Identity/coverage failures above are global.
                diagnostics.add(report["reason"])
    expected = {
        tuple(item) for item in _lines(run.verify(slot["old_window_keys"], "ANCHORS"))
    }
    missing = expected - keys
    # V1 receipts retain their original verification contract. New V2 work
    # separates response integrity from financial/source-history differences.
    if request["policy"] == LEGACY_POLICY and missing:
        raise SnapshotError("OLD_WINDOW_COVERAGE_MISSING")
    trust = validate_complete_history(
        records, ticker=slot["ticker"], dimension=slot["dimension"]
    )
    if trust.status != "COMPLETE":
        diagnostics.add("NATIVE_HISTORY_VALIDATION_FAILED")
    evidence = {
        "coverage_contract": request["policy"],
        "scope": "BOUNDED_SOURCE_WINDOW_NOT_LIFETIME",
        "from": request["horizon_from"],
        "to": request["source_day"],
        "coverage_basis": "OFFICIAL_NATIVE_FROM_TO_QUERY_AND_OLD_WINDOW_KEYS",
        "server_horizon_live_verified": False,
        "observed_date_min": min(key[2] for key in keys),
        "observed_date_max": max(key[2] for key in keys),
        "row_count": len(records),
        "source_keys_sha256": capture.digest(sorted(keys)),
        "old_window_key_count": len(expected),
        "old_outside_window_action": "PRESERVE_OLD",
        "diagnostic_reasons": sorted(diagnostics),
    }
    if request["policy"] != LEGACY_POLICY:
        evidence.update(
            {
                "coverage_basis": "NATIVE_UNPROJECTED_COMPLETE_BOUNDED_RESPONSE",
                "missing_old_source_key_count": len(missing),
                "missing_old_source_keys_sha256": capture.digest(sorted(missing)),
                "source_history_comparison_required": bool(missing),
                "absence_authorizes_deletion": False,
                "effective_provider_retention_boundary": "NOT_INFERRED_FROM_REQUEST_FROM",
            }
        )
    return evidence


def _transport_events(run):
    path = run.path("fetch/attempts.jsonl")
    started, finished = {}, {}
    if not path.exists():
        return finished
    for event in _lines(path):
        identity = event.get("attempt_id")
        if (
            event.get("operation_id") != run.operation_id
            or not isinstance(identity, str)
            or not re.fullmatch(r"[a-f0-9]{32}", identity)
        ):
            raise SnapshotError("TRANSPORT_EVENT_IDENTITY_INVALID")
        if event.get("event") == "STARTED":
            if identity in started:
                raise SnapshotError("TRANSPORT_ATTEMPT_DUPLICATE")
            started[identity] = event
        elif event.get("event") in ("FINISHED", "FAILED", "INTERRUPTED"):
            first = started.get(identity)
            if (
                not first
                or identity in finished
                or any(
                    first.get(k) != event.get(k)
                    for k in ("endpoint", "parameters", "attempt_number")
                )
            ):
                raise SnapshotError("TRANSPORT_ATTEMPT_BINDING_INVALID")
            finished[identity] = event
        else:
            raise SnapshotError("TRANSPORT_EVENT_INVALID")
    return finished


def _transport_counts(run):
    finished = _transport_events(run)
    path = run.path("fetch/attempts.jsonl")
    dispatched = (
        sum(e["event"] == "STARTED" for e in _lines(path)) if path.exists() else 0
    )
    return {
        "actual_http_attempts": len(finished),
        "dispatch_intents": dispatched,
        "indeterminate_http_attempts": dispatched - len(finished),
    }


def _bind_transport(run, receipt, endpoint, parameters, events=None):
    events = _transport_events(run) if events is None else events
    event = events.get(receipt.get("transport_attempt_id"), {})
    if (
        event.get("event") != "FINISHED"
        or not 200 <= event.get("http_status", 0) < 300
        or event.get("endpoint") != endpoint
        or event.get("parameters") != parameters
        or event.get("at_utc") != receipt.get("acquired_at_utc")
        or event.get("response_sha256") != receipt["body"]["sha256"]
        or event.get("response_bytes") != receipt["body"]["size_bytes"]
    ):
        raise SnapshotError("RECEIPT_TRANSPORT_BINDING_MISMATCH")


def _validate_checkpoint(run, slot, receipt, events=None):
    if (
        receipt.get("operation_id") != run.operation_id
        or receipt.get("slot") != slot["slot"]
        or receipt.get("ticker") != slot["ticker"]
        or receipt.get("dimension") != slot["dimension"]
        or receipt.get("parameters") != _parameters(run.request, slot)
        or receipt.get("state")
        not in ("COMPLETE_VERIFIED", "DOCUMENTED_LOCAL_SOURCE_DEFECT")
    ):
        raise SnapshotError("CHECKPOINT_IDENTITY_MISMATCH")
    body = run.verify(receipt["body"], "BODY")
    captures_path = run.verify(receipt["captures"], "CAPTURES")
    # Only one singleton response is decoded, never the acquisition set.
    from rawcandle.fundamentals.providers.sharadar import parse_payload

    if body.stat().st_size > MAX_RESPONSE_BYTES:
        raise SnapshotError("SINGLE_RESPONSE_BUDGET_EXCEEDED")
    _bind_transport(run, receipt, ENDPOINT, receipt["parameters"], events)
    payload = parse_payload(body.read_text(), receipt["content_type"])
    raw_rows = payload_records(payload)
    records = []
    for item in _lines(captures_path):
        if set(item) != {"raw", "envelope"}:
            raise SnapshotError("CAPTURE_WIRE_INVALID")
        records.append(
            {
                **item["raw"],
                "_acquisition_payload": item["raw"],
                "_capture_envelope": item["envelope"],
                "_capture_transport": capture.VERSION,
            }
        )
    if raw_rows != [capture.raw_payload(row) for row in records] or not _payload_shape(
        payload
    ):
        raise SnapshotError("BODY_CAPTURE_MISMATCH")
    coverage = _coverage(
        run, slot, records, receipt["body"]["sha256"], receipt["acquired_at_utc"]
    )
    if coverage != receipt["coverage"]:
        raise SnapshotError("CHECKPOINT_COVERAGE_MISMATCH")
    state = (
        "DOCUMENTED_LOCAL_SOURCE_DEFECT"
        if coverage["diagnostic_reasons"]
        else "COMPLETE_VERIFIED"
    )
    if receipt["state"] != state:
        raise SnapshotError("CHECKPOINT_STATE_MISMATCH")
    return records


def _payload_shape(payload):
    rows = payload
    if isinstance(payload, dict):
        rows = next(
            (
                payload[k]
                for k in ("data", "rows", "results")
                if isinstance(payload.get(k), list)
            ),
            None,
        )
    return (
        isinstance(rows, list)
        and all(isinstance(row, dict) for row in rows)
        and (
            not isinstance(payload, dict)
            or len(payload) == 1
            # Native Sharadar /data/fundamentals envelope, observed byte-for-
            # byte in Phase 3D. Do not accept pagination or extra metadata.
            or (
                set(payload) == {"count", "data"}
                and type(payload["count"]) is int
                and payload["count"] == len(rows)
            )
        )
    )


def _record_rejected_response(run, slot, response, predicate, checks, secrets=()):
    """Compact, non-authoritative evidence; never retain or accept a raw body."""
    def text(value):
        return redact_text(str(value), configured_secrets=secrets)[:256]

    def identities(rows):
        sample = rows[:32]
        return {
            "row_count": len(rows),
            "sampled_rows": len(sample),
            "tickers": sorted({text(row.get("ticker")) for row in sample}),
            "dimensions": sorted({text(row.get("dimension")) for row in sample}),
        }

    expected = _parameters(run.request, slot)
    parameters = response.parameters or {}
    payload = response.payload
    raw = payload_records(payload)
    captured = [capture.raw_payload(row) for row in response.records]
    body = response.response_body
    origins = [
        (capture.envelope(row) or {}).get("acquisition_source") or {}
        for row in response.records[:32]
    ]
    events = _transport_events(run)
    transport = events.get(response.attempt_id, {})
    if not transport and events:
        latest = next(reversed(events.values()))
        if latest.get("endpoint") == ENDPOINT and latest.get("parameters") == expected:
            transport = latest
    relative = "fetch/rejections/" + uuid4().hex + ".json"
    _write(
        run.path(relative),
        {
            "format": FORMAT + "_REJECTED_RESPONSE_V1",
            "operation_id": run.operation_id,
            "slot": slot["slot"],
            "ticker": slot["ticker"],
            "dimension": slot["dimension"],
            "endpoint": ENDPOINT,
            "transport_attempt_id": response.attempt_id,
            "acquired_at_utc": response.acquired_at_utc,
            "failed_predicate": text(predicate),
            "checks": checks,
            "expected_parameters": expected,
            # Do not copy arbitrary parameters or any sensitive HTTP headers.
            "observed_parameters": {
                key: text(parameters[key]) if key in parameters else None
                for key in expected
            },
            "extra_parameter_keys": [
                text(key) for key in islice(
                    (key for key in parameters if key not in expected), 16
                )
            ],
            "client_status": response.status,
            "http_status": response.http_status,
            "transport_ledger": {
                key: transport.get(key) for key in
                ("attempt_id", "http_status", "response_bytes", "response_sha256")
            },
            "content_type": text((response.response_headers or {}).get("content-type", "")),
            "response_body_type": type(body).__name__,
            "response_bytes": len(body) if isinstance(body, bytes) else None,
            "response_sha256": hashlib.sha256(body).hexdigest() if isinstance(body, bytes) else None,
            "payload_type": type(payload).__name__,
            "payload_top_level_keys": [text(key) for key in islice(payload, 16)] if isinstance(payload, dict) else [],
            "payload_top_level_items": len(payload) if isinstance(payload, (list, dict)) else None,
            "payload_count": text(payload["count"]) if isinstance(payload, dict) and "count" in payload else None,
            "payload_count_type": type(payload["count"]).__name__ if isinstance(payload, dict) and "count" in payload else None,
            "payload_rows": identities(raw),
            "captured_rows": identities(captured),
            "expected_request_fingerprint": capture.digest(expected),
            "captured_request_fingerprints": sorted({text(x.get("request_fingerprint")) for x in origins}),
            "captured_response_sha256s": sorted({text(x.get("response_sha256")) for x in origins}),
            "raw_body_retained": False,
            "accepted_snapshot_slot": False,
            "publication_authorized": False,
        },
    )
    return relative


def _history_response_coverage(run, slot, response):
    # Keep the original four acceptance conditions, but identify each failure.
    checks = {
        "RESPONSE_BODY_PRESENT": response.response_body is not None,
        "REQUEST_PARAMETERS_MATCH": response.parameters == _parameters(run.request, slot),
        "PAYLOAD_SHAPE_VALID": _payload_shape(response.payload),
        "PAYLOAD_CAPTURE_EQUAL": payload_records(response.payload)
        == [capture.raw_payload(row) for row in response.records],
    }
    failed = next((name for name, passed in checks.items() if not passed), None)
    if failed:
        raise SnapshotError("UNFILTERED_RESPONSE_OR_CAPTURE_MISMATCH:" + failed)
    digest = hashlib.sha256(response.response_body).hexdigest()
    return digest, _coverage(run, slot, response.records, digest, response.acquired_at_utc)


def _checked_history_response(run, slot, response, *, secrets=()):
    try:
        return _history_response_coverage(run, slot, response)
    except SnapshotError as error:
        checks = {
            "RESPONSE_BODY_PRESENT": response.response_body is not None,
            "REQUEST_PARAMETERS_MATCH": response.parameters == _parameters(run.request, slot),
            "PAYLOAD_SHAPE_VALID": _payload_shape(response.payload),
            "PAYLOAD_CAPTURE_EQUAL": payload_records(response.payload) == [capture.raw_payload(row) for row in response.records],
        }
        error.rejected_response_diagnostic = _record_rejected_response(
            run, slot, response, str(error).removeprefix("UNFILTERED_RESPONSE_OR_CAPTURE_MISMATCH:"), checks, secrets
        )
        raise


def _checkpoints(run, control, rejected=None):
    """Atomic receipt is the commit point; index is a rebuildable compact view.

    A deletion remains detectable via control/index commitments. A receipt that
    survived interruption before its index update is verified and adopted locally.
    """
    rejected = rejected or {}
    index_path = run.path("fetch/checkpoint_index.jsonl")
    indexed = {}
    # An unsealed, interrupted append tail is not authority. Atomic receipts
    # survive independently; repair the compact view only after verification.
    if index_path.exists():
        for item in _lines(
            index_path, interrupted_tail=not bool(control.get("index_reference"))
        ):
            if item["slot"] in indexed:
                raise SnapshotError("DUPLICATE_CHECKPOINT_INDEX")
            run.verify(item["receipt"], "CHECKPOINT")
            indexed[item["slot"]] = item["receipt"]
    if control.get("index_reference"):
        run.verify(control["index_reference"], "INDEX")
    result = {}
    events = _transport_events(run)
    times = ([_time(run.request["created_at_utc"])]
             if run.request["total_slots"] == 0 and run.request["mode"] == "UPDATE_FETCH" else [])
    planned = 0
    previous_ticker = None
    for slot in _lines(run.verify(control["plan_reference"], "PLAN")):
        if (
            slot.get("slot") != planned
            or slot.get("dimension") != ("ARQ" if planned % 2 == 0 else "MRQ")
            or (planned % 2 and slot.get("ticker") != previous_ticker)
        ):
            raise SnapshotError("PLAN_SEQUENCE_INVALID")
        previous_ticker = slot["ticker"]
        planned += 1
        path = run.path(f"fetch/checkpoints/{slot['slot']:06d}.json")
        if not path.exists():
            if slot["slot"] not in rejected and (slot["slot"] in indexed or slot["slot"] < control.get("accounted_slots", control.get("committed_slots", 0))):
                raise SnapshotError("DECLARED_CHECKPOINT_MISSING")
            continue
        if slot["slot"] in rejected:
            raise SnapshotError("SLOT_BOTH_VERIFIED_AND_REJECTED")
        receipt = _read(path)
        _validate_checkpoint(run, slot, receipt, events)
        result[slot["slot"]] = receipt
        times.append(_time(receipt["acquired_at_utc"]))
    if (
        planned != run.request["total_slots"]
        or planned % 2
        or (control.get("index_reference") and set(indexed) != set(result))
        or set(indexed) - set(result)
        or sorted(set(result) | set(rejected)) != list(range(len(result) + len(rejected)))
    ):
        raise SnapshotError("CHECKPOINT_SEQUENCE_INVALID")
    return result, times


def _validate_update_binding(value):
    from .contracts import fingerprint
    if (not isinstance(value, dict)
            or value.get("contract") != "FUNDAMENTALS_SNAPSHOT_UPDATE_V1"
            or value.get("intent") != "UPDATE"
            or value.get("mode") != "FULL_WORKFLOW"
            or value.get("trigger_source") not in {"MANUAL", "SCHEDULER"}
            or not value.get("update_run_id") or not value.get("old_authority")
            or value.get("fingerprint") != fingerprint({k:v for k,v in value.items() if k != "fingerprint"})):
        raise SnapshotError("UPDATE_FETCH_BINDING_INVALID")


def start_fetch(
    tickers,
    *,
    project_root,
    source_day,
    root=ADMIN_RUN_ROOT,
    operation_id=None,
    client=None,
    now=_now,
    update_binding=None,
    progress_callback=None,
):
    """Explicit acquisition-only API; never called by scheduler/Refresh routes.

    Scope is caller-supplied, not financial classification or discovery approval.
    Live use requires separate operator authorization; this API grants none.
    """
    tickers = list(tickers)
    if (not tickers and update_binding is None) or len(tickers) > 10000 or len(set(tickers)) != len(tickers):
        raise SnapshotError("TICKER_PLAN_INVALID")
    if any(
        not isinstance(t, str) or not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,31}", t)
        for t in tickers
    ):
        raise SnapshotError("TICKER_PLAN_INVALID")
    source_day = date.fromisoformat(source_day)
    if source_day > now().date():
        raise SnapshotError("SOURCE_DAY_IN_FUTURE")
    lookback = date(source_day.year - 10, source_day.month, min(source_day.day, 28))
    quarter = date(lookback.year, ((lookback.month - 1) // 3) * 3 + 1, 1)
    previous = quarter - timedelta(days=1)
    horizon = date(previous.year, ((previous.month - 1) // 3) * 3 + 1, 1)
    operation_id = operation_id or "fetch_" + uuid4().hex
    if not re.fullmatch(r"fetch_[a-f0-9]{32}", operation_id):
        raise SnapshotError("OPERATION_ID_INVALID")
    root = Path(root).absolute()
    if any(part.is_symlink() for part in (root, *root.parents)):
        raise SnapshotError("RUN_ROOT_UNTRUSTED")
    if (root / operation_id).exists() or (root / operation_id).is_symlink():
        raise SnapshotError("OPERATION_ALREADY_EXISTS")
    # Pin before creating a potentially resumable operation. All reads are RO.
    old = pin_old_authority(project_root)
    if update_binding is not None:
        _validate_update_binding(update_binding)
        if update_binding["old_authority"] != old:
            raise SnapshotError("OLD_BINDING_DRIFT")
    root.mkdir(parents=True, exist_ok=True)
    try:
        (root / operation_id).mkdir()  # exclusive ownership even for concurrent starts
    except FileExistsError as exc:
        raise SnapshotError("OPERATION_ALREADY_EXISTS") from exc
    writer = AdminRunWriter(
        operation_id, AdminOperationType.REFRESH_FUNDAMENTALS, root=root
    )
    request = {
        "format": FORMAT,
        "mode": "UPDATE_FETCH" if update_binding is not None else "ACQUISITION_ONLY",
        "operation_id": operation_id,
        "policy": POLICY,
        "max_age_seconds": MAX_AGE_SECONDS,
        "created_at_utc": now().isoformat(),
        "old_authority": old,
        "source_day": source_day.isoformat(),
        "horizon_from": horizon.isoformat(),
        "total_slots": len(tickers) * 2,
        "capture_version": capture.VERSION,
        "normalization_version": NORMALIZATION,
        "transport_mode": "SEQUENTIAL_TICKER_ARQ_THEN_MRQ",
        "publication_authorized": False,
    }
    if update_binding is not None:
        request["update_binding"] = update_binding
    writer.write_json("request.json", request)
    _sync(writer.run_dir)
    run = _Run(root, operation_id)
    run.progress_callback = progress_callback
    for directory in ("responses", "captures", "checkpoints", "anchors"):
        run.path("fetch/" + directory).mkdir(parents=True)
    active = resolve_active_generation(Path(project_root), require_generation=True)
    provider = active.role_paths()["provider"]
    plan = []
    with sqlite3.connect(f"file:{provider.resolve()}?mode=ro", uri=True) as connection:
        for ticker in tickers:
            for dimension in ("ARQ", "MRQ"):
                number = len(plan)
                relative = f"fetch/anchors/{number:06d}.jsonl"
                rows = connection.execute(
                    "SELECT DISTINCT ticker,dimension,date,reportperiod FROM sharadar_fundamental_observation "
                    "WHERE ticker=? AND dimension=? AND date>=? AND date<=? ORDER BY date,reportperiod",
                    (ticker, dimension, horizon.isoformat(), source_day.isoformat()),
                )
                _atomic(
                    run.path(relative),
                    b"".join(_json(list(row)).encode() for row in rows),
                )
                plan.append(
                    {
                        "slot": number,
                        "ticker": ticker,
                        "dimension": dimension,
                        "old_window_keys": run.ref(relative, "ANCHORS"),
                    }
                )
    _atomic(
        run.path("fetch/acquisition_plan.jsonl"),
        b"".join(_json(slot).encode() for slot in plan),
    )
    _write(
        run.path("fetch/control.json"),
        {
            "operation_id": operation_id,
            "request_reference": run.ref("request.json", "REQUEST"),
            "plan_reference": run.ref("fetch/acquisition_plan.jsonl", "PLAN"),
            "total_slots": len(plan),
        },
    )
    return resume_fetch(
        operation_id, project_root=project_root, root=root, client=client, now=now,
        progress_callback=progress_callback
    )


def _schema(run, client):
    path = run.path("fetch/schema_receipt.json")
    if path.exists():
        return _read(path)
    response = client.schema("fundamentals")
    if not response.ok:
        return response
    fields = extract_schema_fields(response.payload)
    if (
        not set(REFRESH_REQUEST_FIELDS).issubset(fields)
        or response.response_body is None
    ):
        raise SnapshotError("SCHEMA_SOURCE_FIELDS_MISSING")
    key = uuid4().hex
    _atomic(run.path(f"fetch/responses/{key}.body"), response.response_body)
    receipt = {
        "operation_id": run.operation_id,
        "schema_fingerprint": capture.digest(sorted(fields)),
        "acquired_at_utc": response.acquired_at_utc,
        "transport_attempt_id": response.attempt_id,
        "body": run.ref(f"fetch/responses/{key}.body", "BODY"),
    }
    _write(path, receipt)
    return receipt


def _verify_schema(run, schema):
    from rawcandle.fundamentals.providers.sharadar import parse_payload

    path = run.verify(schema["body"], "BODY")
    _bind_transport(run, schema, "/schema/fundamentals", {})
    if path.stat().st_size > MAX_RESPONSE_BYTES:
        raise SnapshotError("SCHEMA_BODY_TOO_LARGE")
    fields = extract_schema_fields(parse_payload(path.read_text()))
    if (
        schema.get("operation_id") != run.operation_id
        or not set(REFRESH_REQUEST_FIELDS).issubset(fields)
        or schema.get("schema_fingerprint") != capture.digest(sorted(fields))
    ):
        raise SnapshotError("SCHEMA_BINDING_MISMATCH")


def resume_fetch(
    operation_id, *, project_root, root=ADMIN_RUN_ROOT, client=None, now=_now,
    progress_callback=None,
):
    run = _Run(root, operation_id)
    run.progress_callback = progress_callback
    with run.lock():
        try:
            return _resume(run, project_root=project_root, client=client, now=now)
        except BaseException as exc:
            # Preserve source evidence and record a bounded truthful terminal
            # state. Integrity failures are never converted into cache misses.
            result = run.path("result.json")
            previous = _read(result) if result.exists() else {}
            run.progress(
                (
                    "FETCH_PAUSED"
                    if isinstance(exc, (KeyboardInterrupt, SystemExit))
                    else "FETCH_BLOCKED"
                ),
                previous.get("complete_verified_slots", 0),
                previous.get("diagnostic_slots", 0),
                previous.get("total_slots", run.control()["total_slots"]),
                **{
                    k: previous[k]
                    for k in (
                        "actual_http_attempts",
                        "dispatch_intents",
                        "indeterminate_http_attempts",
                    )
                    if k in previous
                },
                reason=(
                    "INTERRUPTED"
                    if isinstance(exc, (KeyboardInterrupt, SystemExit))
                    else str(exc) if hasattr(exc, "rejected_response_diagnostic")
                    else type(exc).__name__
                ),
                **({"rejected_response_diagnostic": exc.rejected_response_diagnostic}
                   if hasattr(exc, "rejected_response_diagnostic") else {}),
            )
            raise


def _resume(run, *, project_root, client, now):
    operation_id, root = run.operation_id, run.root
    if run.path("fetch/seal.json").exists():
        snapshot = open_snapshot(operation_id, root=root)
        snapshot.validate_preflight(
            old_authority=pin_old_authority(project_root), now=now()
        )
        return run.progress(
            "FETCH_SEALED",
            snapshot.manifest["complete_verified_slots"],
            snapshot.manifest["diagnostic_slots"],
            snapshot.manifest["total_slots"],
            snapshot_reference=snapshot.reference,
            **{
                k: snapshot.manifest[k]
                for k in (
                    "actual_http_attempts",
                    "dispatch_intents",
                    "indeterminate_http_attempts",
                )
            },
        )
    control = run.control()
    if pin_old_authority(project_root) != run.request["old_authority"]:
        raise SnapshotError("OLD_AUTHORITY_DRIFT")
    rejected = quarantine.load(run, control, project_root)
    checkpoints, times = _checkpoints(run, control, rejected)
    times.extend(_time(r["acquired_at_utc"]) for r in rejected.values())
    _age(times, now())
    total = control["total_slots"]
    if run.request["mode"] == "UPDATE_FETCH":
        run.quarantine_progress = lambda: quarantine.statistics(checkpoints, rejected, total)
    counts = lambda: (
        sum(r["state"] == "COMPLETE_VERIFIED" for r in checkpoints.values()),
        sum(
            r["state"] == "DOCUMENTED_LOCAL_SOURCE_DEFECT" for r in checkpoints.values()
        ),
    )
    # Repair only a non-authoritative interrupted index tail/orphan entry,
    # after every committed receipt and child has passed verification.
    _write_index(run, checkpoints)
    if rejected:
        quarantine.write_index(run, rejected)
    client = client or SharadarClient()
    ledger_path = run.path("fetch/attempts.jsonl")
    attempts = _transport_counts(run)

    def observe(event):
        _append(ledger_path, {"operation_id": operation_id, **event})
        if event["event"] == "STARTED":
            attempts["dispatch_intents"] += 1
            attempts["indeterminate_http_attempts"] += 1
        else:
            attempts["actual_http_attempts"] += 1
            attempts["indeterminate_http_attempts"] -= 1
        run.progress("FETCHING", *counts(), total, **attempts)

    if control.get("schema_reference"):
        run.verify(control["schema_reference"], "SCHEMA")
    with client.observe_attempts(observe, response_limit=MAX_RESPONSE_BYTES):
        schema = _schema(run, client)
        if not isinstance(schema, dict):
            return run.progress(
                (
                    "FETCH_PAUSED"
                    if schema.status == STATUS_RATE_LIMITED
                    else "FETCH_BLOCKED"
                ),
                *counts(),
                total,
                reason="SCHEMA_" + schema.status,
                resume_not_before=schema.not_before,
                **attempts,
            )
        if control.get("schema_reference"):
            run.verify(control["schema_reference"], "SCHEMA")
        else:
            control["schema_reference"] = run.ref("fetch/schema_receipt.json", "SCHEMA")
            _write(run.path("fetch/control.json"), control)
        _verify_schema(run, schema)
        plan = list(_lines(run.verify(control["plan_reference"], "PLAN")))
        for slot in plan:
            if slot["slot"] in checkpoints or slot["slot"] in rejected:
                continue
            _age(times, now())
            run.progress(
                "FETCHING",
                *counts(),
                total,
                current_ticker=slot["ticker"],
                current_dimension=slot["dimension"],
            )
            params = _parameters(run.request, slot)
            response = client.fundamentals(
                ticker=slot["ticker"],
                dimension=slot["dimension"],
                limit=LIMIT,
                filters={
                    k: v
                    for k, v in params.items()
                    if k not in {"ticker", "dimension", "limit"}
                },
            )
            if not response.ok:
                diagnostic = {}
                if response.status != STATUS_RATE_LIMITED:
                    diagnostic["rejected_response_diagnostic"] = _record_rejected_response(
                        run, slot, response, "CLIENT_" + response.status,
                        {"CLIENT_RESPONSE_SUCCESS": False},
                        (getattr(client, "_api_key", None),),
                    )
                return run.progress(
                    (
                        "FETCH_PAUSED"
                        if response.status == STATUS_RATE_LIMITED
                        else "FETCH_BLOCKED"
                    ),
                    *counts(),
                    total,
                    reason=response.status,
                    resume_not_before=response.not_before,
                    **diagnostic,
                    **attempts,
                )
            # fundamentals() filters its public records; full payload and
            # original captures must agree before any checkpoint can commit.
            try:
                digest, coverage = _checked_history_response(
                    run, slot, response, secrets=(getattr(client, "_api_key", None),)
                )
                if coverage["diagnostic_reasons"] and run.request["mode"] == "UPDATE_FETCH":
                    raise SnapshotError("SOURCE_PROFILE_UNTRUSTWORTHY")
            except SnapshotError as error:
                proof = quarantine.classify(run, slot, response, project_root, plan)
                if proof is None:
                    raise
                quarantine.check_shared({**rejected, slot["slot"]: {"ticker": slot["ticker"], **proof}})
                _age(times + [_time(response.acquired_at_utc)], now())
                diagnostic = getattr(error, "rejected_response_diagnostic", None)
                if diagnostic is None:
                    diagnostic = _record_rejected_response(run, slot, response, proof["reason"], {"SOURCE_PROFILE_TRUSTWORTHY": False}, (getattr(client, "_api_key", None),))
                rejected[slot["slot"]] = quarantine.persist(run, slot, response, proof, diagnostic)
                times.append(_time(response.acquired_at_utc))
                control.update(committed_quarantine_slots=len(rejected), accounted_slots=len(checkpoints) + len(rejected))
                _write(run.path("fetch/control.json"), control)
                run.progress("FETCHING", *counts(), total, **attempts)
                continue
            _age(times + [_time(response.acquired_at_utc)], now())
            key = uuid4().hex
            body_name, captures_name = (
                f"fetch/responses/{key}.body",
                f"fetch/captures/{key}.jsonl",
            )
            _atomic(run.path(body_name), response.response_body)
            _atomic(
                run.path(captures_name),
                (
                    _json(
                        {"raw": capture.raw_payload(r), "envelope": capture.envelope(r)}
                    ).encode()
                    for r in response.records
                ),
            )
            receipt = {
                "format": FORMAT,
                "operation_id": operation_id,
                **{k: slot[k] for k in ("slot", "ticker", "dimension")},
                "state": (
                    "DOCUMENTED_LOCAL_SOURCE_DEFECT"
                    if coverage["diagnostic_reasons"]
                    else "COMPLETE_VERIFIED"
                ),
                "parameters": params,
                "acquired_at_utc": response.acquired_at_utc,
                "transport_attempt_id": response.attempt_id,
                "content_type": (response.response_headers or {}).get(
                    "content-type", ""
                ),
                "body": run.ref(body_name, "BODY"),
                "captures": run.ref(captures_name, "CAPTURES"),
                "coverage": coverage,
            }
            _write(run.path(f"fetch/checkpoints/{slot['slot']:06d}.json"), receipt)
            checkpoints[slot["slot"]] = receipt
            times.append(_time(response.acquired_at_utc))
            # Receipt is the atomic commit; append-only index is a bounded
            # view, and control remembers every declared complete prefix.
            _append(
                run.path("fetch/checkpoint_index.jsonl"),
                {
                    "slot": slot["slot"],
                    "receipt": run.ref(
                        f"fetch/checkpoints/{slot['slot']:06d}.json", "CHECKPOINT"
                    ),
                },
            )
            control["committed_slots"] = len(checkpoints)
            control["accounted_slots"] = len(checkpoints) + len(rejected)
            _write(run.path("fetch/control.json"), control)
            run.progress("FETCHING", *counts(), total, **attempts)
            del response  # release this singleton before the next HTTP request
    if not rejected:
        return _seal(run, control, checkpoints, times, now())
    return _seal(run, control, checkpoints, times, now(), rejected=rejected, project_root=project_root)


def _write_index(run, checkpoints):
    content = b"".join(
        _json(
            {
                "slot": number,
                "receipt": run.ref(
                    f"fetch/checkpoints/{number:06d}.json", "CHECKPOINT"
                ),
            }
        ).encode()
        for number in sorted(checkpoints)
    )
    _atomic(run.path("fetch/checkpoint_index.jsonl"), content)


def _seal(run, control, checkpoints, times, now, *, rejected=None, project_root=None):
    rejected = rejected or {}
    _age(times, now)
    if len(checkpoints) + len(rejected) != control["total_slots"]:
        raise SnapshotError("SNAPSHOT_COVERAGE_INCOMPLETE")
    if rejected:
        if quarantine.load(run, control, project_root) != rejected:
            raise SnapshotError("QUARANTINE_CHANGED_BEFORE_SEAL")
        quarantine.require_peer_control(checkpoints, rejected)
    _write_index(run, checkpoints)
    if not run.path("fetch/attempts.jsonl").exists():
        raise SnapshotError("TRANSPORT_LEDGER_MISSING")
    # A killed process may leave a dispatch intent with no terminal event.
    # Report that uncertainty separately, never as a known actual/success count.
    attempts = _transport_counts(run)
    manifest = {
        "format": FORMAT,
        "operation_id": run.operation_id,
        "snapshot_id": run.operation_id + "_source",
        "mode": run.request["mode"],
        "publication_authorized": False,
        "max_age_seconds": MAX_AGE_SECONDS,
        "old_authority": run.request["old_authority"],
        "policy": run.request["policy"],
        "capture_version": capture.VERSION,
        "normalization_version": NORMALIZATION,
        "oldest_acquired_at_utc": min(times).isoformat(),
        "newest_acquired_at_utc": max(times).isoformat(),
        "sealed_at_utc": now.isoformat(),
        "total_slots": control["total_slots"],
        "complete_verified_slots": sum(
            r["state"] == "COMPLETE_VERIFIED" for r in checkpoints.values()
        ),
        "diagnostic_slots": sum(
            r["state"] == "DOCUMENTED_LOCAL_SOURCE_DEFECT" for r in checkpoints.values()
        ),
        **attempts,
        "request": run.ref("request.json", "REQUEST"),
        "plan": control["plan_reference"],
        "schema": control["schema_reference"],
        "index": run.ref("fetch/checkpoint_index.jsonl", "INDEX"),
        "attempts": run.ref("fetch/attempts.jsonl", "ATTEMPTS"),
    }
    if rejected:
        quarantine.write_index(run, rejected)
        manifest.update(
            acquisition_quarantine_contract=quarantine.CONTRACT,
            quarantine_index=run.ref("fetch/quarantine_index.jsonl", "QUARANTINE_INDEX"),
            **quarantine.statistics(checkpoints, rejected, control["total_slots"]),
        )
    path = run.path("fetch/snapshot_manifest.json")
    if path.exists():
        # Interrupted after root commit: deterministic source facts must match;
        # original seal timestamp is retained, never silently overwritten.
        previous = _read(path)
        manifest["sealed_at_utc"] = previous["sealed_at_utc"]
        if previous != manifest:
            raise SnapshotError("SEALED_MANIFEST_CONFLICT")
    else:
        _write(path, manifest)
    reference = run.ref("fetch/snapshot_manifest.json", "MANIFEST")
    _write(
        run.path("fetch/seal.json"),
        {"operation_id": run.operation_id, "manifest": reference},
    )
    return run.progress(
        "FETCH_SEALED",
        manifest["complete_verified_slots"],
        manifest["diagnostic_slots"],
        manifest["total_slots"],
        snapshot_reference=reference,
        **attempts,
    )


class AcquisitionSnapshot:
    """Read-only Phase 2 interface; opening never calls any network or writer."""

    def __init__(self, run, manifest, reference):
        self._run, self.manifest, self.reference = run, manifest, reference
        self._quarantined_tickers = frozenset(self.quarantines())

    def quarantines(self):
        """Whole-ticker exclusions, separate from successful source histories."""
        if "quarantine_index" not in self.manifest:
            return {}
        result = {}
        for entry in _lines(self._run.verify(self.manifest["quarantine_index"], "QUARANTINE_INDEX")):
            record = _read(self._run.verify(entry["receipt"], "QUARANTINE"))
            item = result.setdefault(record["ticker"], {"state": quarantine.STATE,
                "identity": record["identity"], "affected_slots": record["affected_slots"],
                "reasons": [], "receipts": [], "incoming_financial_input_eligible": False,
                "absence_authorizes_deletion": False})
            item["reasons"].append(record["reason"])
            item["receipts"].append(entry["receipt"])
        partial = {}
        for entry in _lines(self._run.verify(self.manifest["index"], "INDEX")):
            receipt = _read(self._run.verify(entry["receipt"], "CHECKPOINT"))
            if receipt["ticker"] in result and receipt["state"] == "COMPLETE_VERIFIED":
                partial.setdefault(receipt["ticker"], []).append(entry["receipt"])
        for ticker, item in result.items():
            item["verified_partial_captures"] = partial.get(ticker, [])
            item["valid_partial_capture_obtained"] = bool(item["verified_partial_captures"])
        return result

    def iter_slots(self):
        for slot in _lines(self._run.verify(self.manifest["plan"], "PLAN")):
            yield dict(slot)

    def read_slot(self, number):
        for slot in self.iter_slots():
            if slot["slot"] == number:
                if slot["ticker"] in self._quarantined_tickers:
                    raise SnapshotError("TICKER_ACQUISITION_QUARANTINED")
                receipt = _read(self._run.path(f"fetch/checkpoints/{number:06d}.json"))
                # Bind the receipt to sealed index before returning any rows.
                references = (
                    entry
                    for entry in _lines(
                        self._run.verify(self.manifest["index"], "INDEX")
                    )
                    if entry["slot"] == number
                )
                entry = next(references, None)
                if entry is None:
                    raise SnapshotError("SEALED_SLOT_MISSING")
                self._run.verify(entry["receipt"], "CHECKPOINT")
                records = _validate_checkpoint(self._run, slot, receipt)
                return {
                    "receipt": receipt,
                    "records": records,
                    "source_history_comparison_required": receipt["coverage"].get(
                        "source_history_comparison_required", False
                    ),
                    "incoming_financial_input_eligible": receipt["state"]
                    == "COMPLETE_VERIFIED"
                    and not receipt["coverage"].get(
                        "source_history_comparison_required", False
                    ),
                }
        raise SnapshotError("SLOT_NOT_IN_PLAN")

    def compare_source_history(self, ticker, *, project_root):
        """Local Phase 2 input, never a deletion/financial publication approval.

        Observe actual report-period/fiscal coverage in both captured dimensions;
        request filing-date bounds and canonical freeze dates are different axes.
        Use native retention rules with the unrelated three-year shortcut OFF.
        """
        if ticker in self._quarantined_tickers:
            return {"ticker": ticker, "status": quarantine.STATE,
                "ticker_local_hold_required": True, "incoming_source_for_phase2_eligible": False,
                "automatic_deletion_authorized": False, "publication_authorized": False,
                "old_history_action": "PRESERVE_EXACT_OLD_UNLESS_SEPARATELY_AUTHORIZED"}
        from .refresh_fundamentals import (
            AGED_OUT_OF_SOURCE_WINDOW,
            AMBIGUOUS_SOURCE_REMOVAL,
            MINIMUM_QUARTER_BOUNDARY_SPAN,
            _fiscal_quarter_index,
            build_source_history_merge,
            load_current_history,
        )

        # Phase entry/preflight owns full OLD role hashing. Per-ticker reads pin
        # the native immutable manifest, avoiding a multi-GiB hash for each name.
        binding = resolve_active_generation(Path(project_root), require_generation=True)
        if (
            binding.generation_id != self.manifest["old_authority"]["generation_id"]
            or sha256_file(binding.manifest_path)
            != self.manifest["old_authority"]["manifest_sha256"]
        ):
            raise SnapshotError("OLD_AUTHORITY_DRIFT")
        slots = [slot for slot in self.iter_slots() if slot["ticker"] == ticker]
        if len(slots) != 2 or {s["dimension"] for s in slots} != {"ARQ", "MRQ"}:
            raise SnapshotError("TICKER_DIMENSION_SCOPE_INVALID")
        provider = binding.role_paths()["provider"]
        current = {d: load_current_history(provider, ticker, d) for d in ("ARQ", "MRQ")}
        loaded = {slot["dimension"]: self.read_slot(slot["slot"]) for slot in slots}
        source = {
            d: validate_complete_history(item["records"], ticker=ticker, dimension=d)
            for d, item in loaded.items()
        }
        if (
            sha256_file(binding.manifest_path)
            != self.manifest["old_authority"]["manifest_sha256"]
        ):
            raise SnapshotError("OLD_AUTHORITY_DRIFT")
        result = {
            "ticker": ticker,
            "old_authority": self.manifest["old_authority"],
            "publication_authorized": False,
            "automatic_deletion_authorized": False,
            "old_history_action": "PRESERVE_EXACT_OLD_UNLESS_SEPARATELY_AUTHORIZED",
            "snapshot_reference": self.reference,
        }
        if (
            any(
                item["receipt"]["state"] != "COMPLETE_VERIFIED"
                for item in loaded.values()
            )
            or any(h.status != "COMPLETE" for h in source.values())
            or any(
                c.get("invalid_rows") or c.get("legacy_source_version_ambiguities")
                for c in current.values()
            )
        ):
            return result | {
                "status": "NATIVE_SOURCE_OR_BASELINE_REVIEW_REQUIRED",
                "ticker_local_hold_required": True,
                "incoming_source_for_phase2_eligible": False,
                "financial_locality_authorized": False,
            }
        request = self._run.request
        outside = sum(
            not request["horizon_from"] <= row["date"] <= request["source_day"]
            for c in current.values()
            for row in c["rows"]
        )
        within = {
            d: {
                **c,
                "rows": tuple(
                    r
                    for r in c["rows"]
                    if request["horizon_from"] <= r["date"] <= request["source_day"]
                ),
            }
            for d, c in current.items()
        }
        merge = build_source_history_merge(
            ticker,
            within,
            source,
            as_of_date=date.fromisoformat(request["source_day"]),
            historical_source_window_review_years=0,
        )
        observed = {}
        for d, history in source.items():
            fiscal = [_fiscal_quarter_index(r["fiscalperiod"]) for r in history.rows]
            periods = [date.fromisoformat(r["reportperiod"]) for r in history.rows]
            observed_period_span = (
                (max(periods).year - min(periods).year) * 4
                + (max(periods).month - 1) // 3
                - (min(periods).month - 1) // 3
                + 1
            )
            observed[d] = {
                "min_reportperiod": min(r["reportperiod"] for r in history.rows),
                "max_reportperiod": max(r["reportperiod"] for r in history.rows),
                "observed_fiscal_quarter_span": max(fiscal) - min(fiscal) + 1,
                "observed_reportperiod_quarter_span": observed_period_span,
            }
        # A 41-quarter distance from a missing OLD row to one recent source row
        # does not prove ten years of returned coverage. Require the observed
        # source span too, then retain native prefix/chronology/companion checks.
        broad_window = all(
            min(
                x["observed_fiscal_quarter_span"],
                x["observed_reportperiod_quarter_span"],
            )
            >= MINIMUM_QUARTER_BOUNDARY_SPAN - 1
            for x in observed.values()
        )
        events = []
        for original in merge["events"]:
            event = dict(original)
            if event["event"] == AGED_OUT_OF_SOURCE_WINDOW and not broad_window:
                event.update(
                    event=AMBIGUOUS_SOURCE_REMOVAL,
                    classification_reason="EFFECTIVE_PROVIDER_BOUNDARY_UNPROVEN",
                )
            events.append(event)
        held = any(e["event"] != AGED_OUT_OF_SOURCE_WINDOW for e in events)
        return result | {
            "status": (
                "SOURCE_HISTORY_REVIEW_REQUIRED"
                if held
                else "OLD_RETAINED_SOURCE_READY"
            ),
            "observed_provider_coverage": observed,
            "events": events,
            "outside_request_old_rows_preserved": outside,
            "ticker_local_hold_required": held,
            "incoming_source_for_phase2_eligible": not held,
            "financial_locality_authorized": False,
        }

    def validate_preflight(self, *, old_authority, now, expected_reference=None):
        """Acquisition eligibility only; Phase 2 must still validate finance/intent."""
        if expected_reference is not None and self.reference != expected_reference:
            raise SnapshotError("SNAPSHOT_REFERENCE_MISMATCH")
        if old_authority != self.manifest["old_authority"]:
            raise SnapshotError("OLD_AUTHORITY_DRIFT")
        age = _age(
            [
                _time(self.manifest["oldest_acquired_at_utc"]),
                _time(self.manifest["newest_acquired_at_utc"]),
            ],
            now,
        )
        _verify_snapshot(self._run, self.manifest, self.reference)
        return {
            "snapshot_reference": self.reference,
            "source_age_seconds": age,
            "acquisition_eligible": True,
            "publication_authorized": False,
        }


def _verify_snapshot(run, manifest, reference):
    run.verify(reference, "MANIFEST")
    if (
        manifest.get("format") != FORMAT
        or manifest.get("operation_id") != run.operation_id
        or manifest.get("mode") != run.request["mode"]
        or manifest.get("publication_authorized") is not False
        or manifest.get("max_age_seconds") != MAX_AGE_SECONDS
        or manifest.get("policy") != run.request["policy"]
        or manifest.get("old_authority") != run.request["old_authority"]
    ):
        raise SnapshotError("SNAPSHOT_IDENTITY_OR_POLICY_MISMATCH")
    for key, kind in (
        ("request", "REQUEST"),
        ("plan", "PLAN"),
        ("index", "INDEX"),
        ("schema", "SCHEMA"),
        ("attempts", "ATTEMPTS"),
    ):
        run.verify(manifest[key], kind)
    if any(manifest.get(k) != value for k, value in _transport_counts(run).items()):
        raise SnapshotError("SEALED_ATTEMPT_COUNTS_MISMATCH")
    schema = _read(run.verify(manifest["schema"], "SCHEMA"))
    _verify_schema(run, schema)
    control = {"plan_reference": manifest["plan"], "index_reference": manifest["index"]}
    if "quarantine_index" in manifest:
        if manifest.get("acquisition_quarantine_contract") != quarantine.CONTRACT:
            raise SnapshotError("ACQUISITION_QUARANTINE_CONTRACT_INVALID")
        control["quarantine_index_reference"] = manifest["quarantine_index"]
    elif "acquisition_quarantine_contract" in manifest:
        raise SnapshotError("ACQUISITION_QUARANTINE_INDEX_MISSING")
    rejected = quarantine.load(run, control, None) if "quarantine_index" in manifest else {}
    checkpoints, times = _checkpoints(run, control, rejected)
    times.extend(_time(r["acquired_at_utc"]) for r in rejected.values())
    if "quarantine_index" in manifest:
        stats = quarantine.statistics(checkpoints, rejected, manifest["total_slots"])
        if any(manifest.get(k) != value for k, value in stats.items()):
            raise SnapshotError("SEALED_QUARANTINE_ACCOUNTING_MISMATCH")
        if rejected:
            quarantine.require_peer_control(checkpoints, rejected)
    if (
        len(checkpoints) + len(rejected) != manifest["total_slots"]
        or not times
        or min(times) != _time(manifest["oldest_acquired_at_utc"])
        or max(times) != _time(manifest["newest_acquired_at_utc"])
        or sum(r["state"] == "COMPLETE_VERIFIED" for r in checkpoints.values())
        != manifest["complete_verified_slots"]
        or sum(
            r["state"] == "DOCUMENTED_LOCAL_SOURCE_DEFECT" for r in checkpoints.values()
        )
        != manifest["diagnostic_slots"]
    ):
        raise SnapshotError("SEALED_COVERAGE_MISMATCH")


def open_snapshot(operation_id, *, root=ADMIN_RUN_ROOT, expected_reference=None):
    """Audit reads remain possible after expiry. Use validate_preflight for age."""
    run = _Run(root, operation_id)
    seal = _read(run.path("fetch/seal.json"))
    if seal.get("operation_id") != operation_id:
        raise SnapshotError("SEAL_OPERATION_MISMATCH")
    reference = seal["manifest"]
    if expected_reference is not None and reference != expected_reference:
        raise SnapshotError("SNAPSHOT_REFERENCE_MISMATCH")
    manifest = _read(run.verify(reference, "MANIFEST"))
    _verify_snapshot(run, manifest, reference)
    return AcquisitionSnapshot(run, manifest, reference)
