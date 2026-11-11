"""Inert singleton FETCH foundation. No financial route calls this module.

COMPLETE_VERIFIED means a native, bounded *request window*, never lifetime
history or publication permission. OLD outside that window remains authoritative.
"""

from __future__ import annotations

from contextlib import contextmanager
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
from .refresh_fundamentals import (
    REFRESH_REQUEST_FIELDS,
    SOURCE_PRIMARY_KEY,
    source_key,
    validate_complete_history,
)
from .workflow_evidence import trusted_path

FORMAT = "FUNDAMENTALS_ACQUISITION_SNAPSHOT_V1"
POLICY = "SINGLETON_ARQ_MRQ_WINDOW_V1"
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
            or self.request.get("mode") != "ACQUISITION_ONLY"
            or self.request.get("format") != FORMAT
            or self.request.get("policy") != POLICY
            or self.request.get("max_age_seconds") != MAX_AGE_SECONDS
            or self.request.get("capture_version") != capture.VERSION
            or self.request.get("normalization_version") != NORMALIZATION
        ):
            raise SnapshotError("OPERATION_OR_POLICY_MISMATCH")

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
            "mode": "ACQUISITION_ONLY",
            "status": status,
            "complete_verified_slots": complete,
            "diagnostic_slots": diagnostic,
            "total_slots": total,
            "publication_authorized": False,
            "future_test_authorized": False,
            "future_production_authorized": False,
            **extra,
        }
        _write(self.path("result.json"), value)
        if status != "FETCHING":
            # Native top-level artifact manifest covers the bounded reference;
            # that reference recursively binds the large source children.
            if extra.get("snapshot_reference"):
                _write(
                    self.path("acquisition_snapshot_reference.json"),
                    {
                        "operation_id": self.operation_id,
                        "mode": "ACQUISITION_ONLY",
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
            report = capture.profile_report(row, profile)
            if not report["eligible_authoritative_full_source"]:
                # An original projected/defective native response is diagnostic,
                # never safe finance. Identity/coverage failures above are global.
                diagnostics.add(report["reason"])
    expected = {
        tuple(item) for item in _lines(run.verify(slot["old_window_keys"], "ANCHORS"))
    }
    if not expected.issubset(keys):
        raise SnapshotError("OLD_WINDOW_COVERAGE_MISSING")
    trust = validate_complete_history(
        records, ticker=slot["ticker"], dimension=slot["dimension"]
    )
    if trust.status != "COMPLETE":
        diagnostics.add("NATIVE_HISTORY_VALIDATION_FAILED")
    return {
        "coverage_contract": POLICY,
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
        and (not isinstance(payload, dict) or len(payload) == 1)
    )


def _checkpoints(run, control):
    """Atomic receipt is the commit point; index is a rebuildable compact view.

    A deletion remains detectable via control/index commitments. A receipt that
    survived interruption before its index update is verified and adopted locally.
    """
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
    times = []
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
            if slot["slot"] in indexed or slot["slot"] < control.get(
                "committed_slots", 0
            ):
                raise SnapshotError("DECLARED_CHECKPOINT_MISSING")
            continue
        receipt = _read(path)
        _validate_checkpoint(run, slot, receipt, events)
        result[slot["slot"]] = receipt
        times.append(_time(receipt["acquired_at_utc"]))
    if (
        planned != run.request["total_slots"]
        or planned % 2
        or (control.get("index_reference") and set(indexed) != set(result))
        or set(indexed) - set(result)
        or sorted(result) != list(range(len(result)))
    ):
        raise SnapshotError("CHECKPOINT_SEQUENCE_INVALID")
    return result, times


def start_fetch(
    tickers,
    *,
    project_root,
    source_day,
    root=ADMIN_RUN_ROOT,
    operation_id=None,
    client=None,
    now=_now,
):
    """Explicit acquisition-only API; never called by scheduler/Refresh routes.

    Scope is caller-supplied, not financial classification or discovery approval.
    Live use requires separate operator authorization; this API grants none.
    """
    tickers = list(tickers)
    if not tickers or len(tickers) > 10000 or len(set(tickers)) != len(tickers):
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
        "mode": "ACQUISITION_ONLY",
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
    writer.write_json("request.json", request)
    _sync(writer.run_dir)
    run = _Run(root, operation_id)
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
        operation_id, project_root=project_root, root=root, client=client, now=now
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
    operation_id, *, project_root, root=ADMIN_RUN_ROOT, client=None, now=_now
):
    run = _Run(root, operation_id)
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
                    else type(exc).__name__
                ),
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
    checkpoints, times = _checkpoints(run, control)
    _age(times, now())
    total = control["total_slots"]
    counts = lambda: (
        sum(r["state"] == "COMPLETE_VERIFIED" for r in checkpoints.values()),
        sum(
            r["state"] == "DOCUMENTED_LOCAL_SOURCE_DEFECT" for r in checkpoints.values()
        ),
    )
    # Repair only a non-authoritative interrupted index tail/orphan entry,
    # after every committed receipt and child has passed verification.
    _write_index(run, checkpoints)
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
        for slot in _lines(run.verify(control["plan_reference"], "PLAN")):
            if slot["slot"] in checkpoints:
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
                    **attempts,
                )
            # fundamentals() filters its public records; full payload and
            # original captures must agree before any checkpoint can commit.
            if (
                response.response_body is None
                or response.parameters != params
                or not _payload_shape(response.payload)
                or payload_records(response.payload)
                != [capture.raw_payload(r) for r in response.records]
            ):
                raise SnapshotError("UNFILTERED_RESPONSE_OR_CAPTURE_MISMATCH")
            digest = hashlib.sha256(response.response_body).hexdigest()
            coverage = _coverage(
                run, slot, response.records, digest, response.acquired_at_utc
            )
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
            _write(run.path("fetch/control.json"), control)
            run.progress("FETCHING", *counts(), total, **attempts)
            del response  # release this singleton before the next HTTP request
    return _seal(run, control, checkpoints, times, now())


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


def _seal(run, control, checkpoints, times, now):
    _age(times, now)
    if len(checkpoints) != control["total_slots"]:
        raise SnapshotError("SNAPSHOT_COVERAGE_INCOMPLETE")
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
        "mode": "ACQUISITION_ONLY",
        "publication_authorized": False,
        "max_age_seconds": MAX_AGE_SECONDS,
        "old_authority": run.request["old_authority"],
        "policy": POLICY,
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

    def iter_slots(self):
        for slot in _lines(self._run.verify(self.manifest["plan"], "PLAN")):
            yield dict(slot)

    def read_slot(self, number):
        for slot in self.iter_slots():
            if slot["slot"] == number:
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
                    "incoming_financial_input_eligible": receipt["state"]
                    == "COMPLETE_VERIFIED",
                }
        raise SnapshotError("SLOT_NOT_IN_PLAN")

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
        or manifest.get("mode") != "ACQUISITION_ONLY"
        or manifest.get("publication_authorized") is not False
        or manifest.get("max_age_seconds") != MAX_AGE_SECONDS
        or manifest.get("policy") != POLICY
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
    checkpoints, times = _checkpoints(run, control)
    if (
        len(checkpoints) != manifest["total_slots"]
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
