"""Phase 1 acceptance through native HTTP/capture, with disposable OLD/runs."""

from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tracemalloc
from urllib.parse import parse_qs, urlsplit

import pytest

from rawcandle.fundamentals import source_capture as capture
from rawcandle.fundamentals.admin import acquisition_snapshot as fetch
from rawcandle.fundamentals.admin.artifacts import sha256_file
from rawcandle.fundamentals.admin.refresh_fundamentals import REFRESH_REQUEST_FIELDS
from rawcandle.fundamentals.generations import ROLE_FILENAMES, migrate_flat_layout
from rawcandle.fundamentals.providers.sharadar import SharadarClient
from rawcandle.fundamentals.providers.sharadar_limiter import CredentialRequestLimiter
from tests.provider_capture_fixtures import full_row

NOW = datetime(2026, 11, 11, 12, tzinfo=timezone.utc)
OP = "fetch_" + "a" * 32
SECRET = "never-persist-this-credential"


class Response(io.BytesIO):
    status = 200

    def __init__(self, payload, *, status=200, headers=None):
        self.status = status
        self.headers = headers or {"Content-Type": "application/json"}
        super().__init__(
            payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        )

    def getcode(self):
        return self.status


def row(ticker="AAA", dimension="ARQ", **overrides):
    return full_row(
        dict(
            ticker=ticker,
            dimension=dimension,
            date="2026-08-01",
            reportperiod="2026-06-30",
            calendardate="2026-06-30",
            fiscalperiod="2026-Q2",
            lastupdated="2026-11-10",
            revenue=100,
            equity=80,
            **overrides,
        )
    )


@pytest.fixture
def old(tmp_path):
    for name in ROLE_FILENAMES.values():
        path = tmp_path / "project/data" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(path) as db:
            db.execute(
                "CREATE TABLE sharadar_fundamental_observation(ticker,dimension,date,reportperiod)"
            )
    migrate_flat_layout(project_root=tmp_path / "project", generation_id="old")
    return tmp_path / "project"


class Transport:
    def __init__(self, *, fail_at=None, change=None, now=lambda: NOW):
        self.calls, self.fail_at, self.change, self.now = [], fail_at, change, now

    def __call__(self, request, timeout):
        params = {
            k: v[0] for k, v in parse_qs(urlsplit(request.full_url).query).items()
        }
        if "/schema/" in request.full_url:
            self.calls.append(("schema", params))
            return Response(list(REFRESH_REQUEST_FIELDS))
        identity = params["ticker"], params["dimension"]
        self.calls.append(identity)
        if identity == self.fail_at:
            raise KeyboardInterrupt()
        payload = [row(*identity)]
        if self.change:
            payload = self.change(identity, payload)
        return payload if isinstance(payload, Response) else Response(payload)

    def client(self, **kwargs):
        return SharadarClient(
            api_key=SECRET,
            opener=self,
            wall_clock=lambda: self.now().timestamp(),
            **kwargs,
        )


def start(old, tmp_path, transport=None, **kwargs):
    transport = transport or Transport()
    return fetch.start_fetch(
        ["AAA", "BBB"],
        project_root=old,
        root=tmp_path / "runs",
        operation_id=OP,
        source_day=NOW.date().isoformat(),
        client=transport.client(),
        now=lambda: NOW,
        **kwargs,
    )


def checkpoint(tmp_path, number=0):
    path = tmp_path / "runs" / OP / f"fetch/checkpoints/{number:06d}.json"
    return path, json.loads(path.read_text())


def test_sequential_persistence_native_capture_and_offline_open(old, tmp_path):
    transport = Transport()
    before = {str(p): sha256_file(p) for p in old.rglob("*") if p.is_file()}
    result = start(old, tmp_path, transport)
    assert transport.calls[1:] == [
        ("AAA", "ARQ"),
        ("AAA", "MRQ"),
        ("BBB", "ARQ"),
        ("BBB", "MRQ"),
    ]
    assert result["status"] == "FETCH_SEALED" and result["actual_http_attempts"] == 5
    snap = fetch.open_snapshot(
        OP, root=tmp_path / "runs", expected_reference=result["snapshot_reference"]
    )
    value = snap.read_slot(0)
    envelope = capture.envelope(value["records"][0])
    path, receipt = checkpoint(tmp_path)
    body = tmp_path / "runs" / OP / receipt["body"]["relative_path"]
    assert body.read_bytes() == json.dumps([row()]).encode()
    assert (
        envelope["acquisition_source"]["response_sha256"]
        == hashlib.sha256(body.read_bytes()).hexdigest()
    )
    assert envelope["acquired_at_utc"] == NOW.isoformat()
    assert value["incoming_financial_input_eligible"]
    assert value["receipt"]["parameters"] == {
        "ticker": "AAA",
        "dimension": "ARQ",
        "limit": "10000",
        "from": "2016-07-01",
        "to": "2026-11-11",
        "format": "json",
        "sort": "date.asc",
    }
    assert value["receipt"]["coverage"]["old_outside_window_action"] == "PRESERVE_OLD"
    assert not snap.validate_preflight(
        old_authority=fetch.pin_old_authority(old), now=NOW
    )["publication_authorized"]
    assert before == {str(p): sha256_file(p) for p in old.rglob("*") if p.is_file()}
    assert SECRET not in "\n".join(
        p.read_text() for p in (tmp_path / "runs").rglob("*") if p.is_file()
    )


@pytest.mark.parametrize(
    "failure,complete", [(("AAA", "MRQ"), 1), (("BBB", "ARQ"), 2), (("BBB", "MRQ"), 3)]
)
def test_interrupt_resume_only_missing_slots(old, tmp_path, failure, complete):
    first = Transport(fail_at=failure)
    with pytest.raises(KeyboardInterrupt):
        start(old, tmp_path, first)
    refs = [checkpoint(tmp_path, n)[1] for n in range(complete)]
    second = Transport()
    result = fetch.resume_fetch(
        OP,
        project_root=old,
        root=tmp_path / "runs",
        client=second.client(),
        now=lambda: NOW,
    )
    expected = [("AAA", "ARQ"), ("AAA", "MRQ"), ("BBB", "ARQ"), ("BBB", "MRQ")][
        complete:
    ]
    assert second.calls == expected
    assert result["status"] == "FETCH_SEALED"
    assert [checkpoint(tmp_path, n)[1] for n in range(complete)] == refs
    assert result["actual_http_attempts"] == 6  # includes interrupted dispatch


@pytest.mark.parametrize(
    "artifact", ["body", "captures", "receipt", "index", "plan", "schema", "request"]
)
def test_tamper_prevents_resume_without_http(old, tmp_path, artifact):
    with pytest.raises(KeyboardInterrupt):
        start(old, tmp_path, Transport(fail_at=("AAA", "MRQ")))
    receipt_path, receipt = checkpoint(tmp_path)
    directory = tmp_path / "runs" / OP
    target = (
        directory / receipt[artifact]["relative_path"]
        if artifact in ("body", "captures")
        else {
            "receipt": receipt_path,
            "index": directory / "fetch/checkpoint_index.jsonl",
            "plan": directory / "fetch/acquisition_plan.jsonl",
            "schema": directory / "fetch/schema_receipt.json",
            "request": directory / "request.json",
        }[artifact]
    )
    target.write_bytes(target.read_bytes() + b"corrupt\n")
    transport = Transport()
    with pytest.raises((fetch.SnapshotError, ValueError)):
        fetch.resume_fetch(
            OP,
            project_root=old,
            root=tmp_path / "runs",
            client=transport.client(),
            now=lambda: NOW,
        )
    assert not transport.calls


@pytest.mark.parametrize("kind", ["body", "receipt", "schema"])
def test_declared_missing_is_integrity_failure(old, tmp_path, kind):
    with pytest.raises(KeyboardInterrupt):
        start(old, tmp_path, Transport(fail_at=("AAA", "MRQ")))
    path, receipt = checkpoint(tmp_path)
    target = (
        tmp_path / "runs" / OP / receipt["body"]["relative_path"]
        if kind == "body"
        else (
            path
            if kind == "receipt"
            else tmp_path / "runs" / OP / "fetch/schema_receipt.json"
        )
    )
    target.unlink()
    transport = Transport()
    with pytest.raises((fetch.SnapshotError, FileNotFoundError)):
        fetch.resume_fetch(
            OP,
            project_root=old,
            root=tmp_path / "runs",
            client=transport.client(),
            now=lambda: NOW,
        )
    assert not transport.calls


@pytest.mark.parametrize(
    "kind", ["symlink", "traversal", "wrong_operation", "wrong_type"]
)
def test_reference_rejects_unsafe_paths_identity_and_types(old, tmp_path, kind):
    start(old, tmp_path)
    run = fetch._Run(tmp_path / "runs", OP)
    _, receipt = checkpoint(tmp_path)
    ref = dict(receipt["body"])
    if kind == "symlink":
        path = run.path(ref["relative_path"])
        data = path.read_bytes()
        path.unlink()
        other = tmp_path / "outside"
        other.write_bytes(data)
        path.symlink_to(other)
    elif kind == "traversal":
        ref["relative_path"] = "../outside"
    elif kind == "wrong_operation":
        ref["operation_id"] = "fetch_" + "b" * 32
    else:
        ref["kind"] = "CAPTURES"
    with pytest.raises(fetch.SnapshotError):
        run.verify(ref, "BODY")


@pytest.mark.parametrize(
    "defect",
    [
        "empty",
        "wrong_dimension",
        "wrong_ticker",
        "duplicate",
        "limit",
        "pagination",
        "truncated",
        "out_of_window",
        "nonobject",
    ],
)
def test_unproven_history_is_not_checkpointed(old, tmp_path, defect, monkeypatch):
    if defect == "limit":
        monkeypatch.setattr(fetch, "LIMIT", 1)

    def change(identity, rows):
        if defect == "empty":
            return []
        if defect == "wrong_dimension":
            rows[0]["dimension"] = "MRQ"
        if defect == "wrong_ticker":
            rows[0]["ticker"] = "FOREIGN"
        if defect == "duplicate":
            return rows + rows
        if defect == "pagination":
            return {"data": rows, "next": "unverified"}
        if defect == "truncated":
            return Response(
                json.dumps(rows).encode(), headers={"Content-Length": "999999"}
            )
        if defect == "out_of_window":
            rows[0]["date"] = "2010-01-01"
        if defect == "nonobject":
            return [rows[0], None]
        return rows

    transport = Transport(change=change)
    try:
        result = start(old, tmp_path, transport)
        assert result["status"] == "FETCH_BLOCKED"
    except fetch.SnapshotError:
        pass
    assert not (tmp_path / "runs" / OP / "fetch/checkpoints/000000.json").exists()
    assert not (tmp_path / "runs" / OP / "fetch/seal.json").exists()
    assert len(transport.calls) == 2


@pytest.mark.parametrize("defect", ["projected", "absent", "null", "value"])
def test_absent_null_value_and_diagnostic_only_source(old, tmp_path, defect):
    def change(identity, rows):
        raw = rows[0]
        if defect == "projected":
            rows[0] = {k: raw[k] for k in REFRESH_REQUEST_FIELDS}
        if defect == "absent":
            del raw["revenue"]
        if defect == "null":
            raw["revenue"] = None
        if defect == "value":
            raw["revenue"] = 123
        return rows

    result = start(old, tmp_path, Transport(change=change))
    snap = fetch.open_snapshot(OP, root=tmp_path / "runs")
    record = snap.read_slot(0)
    assert record["incoming_financial_input_eligible"] == (defect in ("null", "value"))
    expected = {
        "absent": "ABSENT",
        "null": "EXPLICIT_NULL",
        "value": "VALUE",
        "projected": "VALUE",
    }[defect]
    assert (
        capture.field_state(capture.raw_payload(record["records"][0]), "revenue")
        == expected
    )
    assert result["diagnostic_slots"] == (4 if defect in ("absent", "projected") else 0)


@pytest.mark.parametrize(
    "seconds,eligible",
    [
        (fetch.MAX_AGE_SECONDS - 0.000001, True),
        (fetch.MAX_AGE_SECONDS, True),
        (fetch.MAX_AGE_SECONDS + 0.000001, False),
    ],
)
def test_seven_day_exact_preflight_and_audit(old, tmp_path, seconds, eligible):
    start(old, tmp_path)
    snap = fetch.open_snapshot(OP, root=tmp_path / "runs")
    current = NOW + timedelta(seconds=seconds)
    if eligible:
        assert (
            snap.validate_preflight(
                old_authority=fetch.pin_old_authority(old), now=current
            )["source_age_seconds"]
            == seconds
        )
    else:
        with pytest.raises(fetch.SnapshotError, match="EXPIRED"):
            snap.validate_preflight(
                old_authority=fetch.pin_old_authority(old), now=current
            )
    assert (
        fetch.open_snapshot(OP, root=tmp_path / "runs").read_slot(0)["receipt"][
            "acquired_at_utc"
        ]
        == NOW.isoformat()
    )


@pytest.mark.parametrize("days,eligible", [(6, True), (7, True), (8, False)])
def test_resume_preserves_original_age_and_does_not_impose_same_day(
    old, tmp_path, days, eligible
):
    with pytest.raises(KeyboardInterrupt):
        start(old, tmp_path, Transport(fail_at=("AAA", "MRQ")))
    current = NOW + timedelta(days=days)
    second = Transport(now=lambda: current)
    if eligible:
        fetch.resume_fetch(
            OP,
            project_root=old,
            root=tmp_path / "runs",
            client=second.client(),
            now=lambda: current,
        )
        assert second.calls == [("AAA", "MRQ"), ("BBB", "ARQ"), ("BBB", "MRQ")]
        snap = fetch.open_snapshot(OP, root=tmp_path / "runs")
        assert snap.manifest["oldest_acquired_at_utc"] == NOW.isoformat()
    else:
        with pytest.raises(fetch.SnapshotError, match="EXPIRED"):
            fetch.resume_fetch(
                OP,
                project_root=old,
                root=tmp_path / "runs",
                client=second.client(),
                now=lambda: current,
            )
        assert not second.calls


def test_old_drift_and_cross_operation_cannot_reuse(old, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        start(old, tmp_path, Transport(fail_at=("AAA", "MRQ")))
    transport = Transport()
    manifest = old / "data/fundamentals_active_generation.json"
    manifest.write_text(manifest.read_text() + "\n")
    with pytest.raises(fetch.SnapshotError, match="OLD_AUTHORITY_DRIFT"):
        fetch.resume_fetch(
            OP,
            project_root=old,
            root=tmp_path / "runs",
            client=transport.client(),
            now=lambda: NOW,
        )
    assert not transport.calls
    other = "fetch_" + "b" * 32
    (tmp_path / "runs" / OP).rename(tmp_path / "runs" / other)
    with pytest.raises(fetch.SnapshotError, match="OPERATION"):
        fetch.open_snapshot(other, root=tmp_path / "runs")


def test_old_anchor_absence_is_explicit_and_requires_local_comparison(old, tmp_path):
    from rawcandle.fundamentals.generations import resolve_active_generation

    provider = resolve_active_generation(old).role_paths()["provider"]
    # Fixture amendment occurs before pinning, never during acquisition.
    with sqlite3.connect(provider) as db:
        db.execute(
            "INSERT INTO sharadar_fundamental_observation VALUES('AAA','ARQ','2017-08-01','2017-06-30')"
        )
    manifest = old / "data/fundamentals_active_generation.json"
    value = json.loads(manifest.read_text())
    value["role_verification"]["provider"]["sha256"] = sha256_file(provider)
    manifest.write_text(json.dumps(value))
    result = start(old, tmp_path)
    assert result["status"] == "FETCH_SEALED"
    slot = fetch.open_snapshot(OP, root=tmp_path / "runs").read_slot(0)
    assert slot["receipt"]["coverage"]["missing_old_source_key_count"] == 1
    assert slot["source_history_comparison_required"]
    assert not slot["incoming_financial_input_eligible"]
    assert slot["receipt"]["coverage"]["absence_authorizes_deletion"] is False


def test_429_pauses_promptly_retains_arq_and_counts_actual_attempts(old, tmp_path):
    class Clock:
        value = NOW.timestamp()

        def clock(self):
            return self.value

        def sleep(self, n):
            self.value += n

    clock = Clock()
    limiter = CredentialRequestLimiter(
        SECRET, root=tmp_path / "limiter", clock=clock.clock, sleeper=clock.sleep
    )

    def change(identity, rows):
        return (
            Response(b"rate limit", status=429, headers={"Retry-After": "120"})
            if identity == ("AAA", "MRQ")
            else rows
        )

    transport = Transport(
        change=change, now=lambda: datetime.fromtimestamp(clock.value, timezone.utc)
    )
    result = fetch.start_fetch(
        ["AAA", "BBB"],
        project_root=old,
        root=tmp_path / "runs",
        operation_id=OP,
        source_day="2026-11-11",
        client=transport.client(credential_limiter=limiter),
        now=lambda: datetime.fromtimestamp(clock.value, timezone.utc),
    )
    assert result["status"] == "FETCH_PAUSED" and result["complete_verified_slots"] == 1
    assert transport.calls[1:] == [("AAA", "ARQ"), ("AAA", "MRQ")]
    events = list(fetch._lines(tmp_path / "runs" / OP / "fetch/attempts.jsonl"))
    assert sum(e["event"] == "STARTED" for e in events) == 3
    second = Transport(now=lambda: datetime.fromtimestamp(clock.value, timezone.utc))
    result = fetch.resume_fetch(
        OP,
        project_root=old,
        root=tmp_path / "runs",
        client=second.client(credential_limiter=limiter, wait_budget_seconds=0),
        now=lambda: datetime.fromtimestamp(clock.value, timezone.utc),
    )
    assert result["status"] == "FETCH_PAUSED" and not second.calls
    clock.value += 120
    result = fetch.resume_fetch(
        OP,
        project_root=old,
        root=tmp_path / "runs",
        client=second.client(credential_limiter=limiter),
        now=lambda: datetime.fromtimestamp(clock.value, timezone.utc),
    )
    assert result["status"] == "FETCH_SEALED" and result["actual_http_attempts"] == 6
    assert second.calls == [("AAA", "MRQ"), ("BBB", "ARQ"), ("BBB", "MRQ")]


def test_checkpoint_commit_survives_crash_before_index(old, tmp_path, monkeypatch):
    original = fetch._append

    def interrupted(path, value):
        if path.name == "checkpoint_index.jsonl":
            raise KeyboardInterrupt()
        return original(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(fetch, "_append", interrupted)
        with pytest.raises(KeyboardInterrupt):
            start(old, tmp_path)
    assert checkpoint(tmp_path)[1]["state"] == "COMPLETE_VERIFIED"
    transport = Transport()
    result = fetch.resume_fetch(
        OP,
        project_root=old,
        root=tmp_path / "runs",
        client=transport.client(),
        now=lambda: NOW,
    )
    assert result["status"] == "FETCH_SEALED" and transport.calls[0] == ("AAA", "MRQ")


def test_two_gib_child_is_stream_hashed_and_oversized_replay_rejected(
    old, tmp_path, monkeypatch
):
    start(old, tmp_path)
    run = fetch._Run(tmp_path / "runs", OP)
    relative = "fetch/responses/" + "f" * 32 + ".body"
    path = run.path(relative)
    with path.open("wb") as stream:
        stream.truncate(2 * 1024**3)
    # Exercise real chunked native hashing without loading a giant child.
    tracemalloc.start()
    ref = run.ref(relative, "BODY")
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < 8 * 1024**2
    assert ref["size_bytes"] == 2 * 1024**3
    assert len(json.dumps(ref)) < 400
    _, receipt = checkpoint(tmp_path)
    receipt["body"] = ref
    original = Path.read_text
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda self, *a, **k: (
            pytest.fail("eager body read") if self == path else original(self, *a, **k)
        ),
    )
    # Verification order is body, captures, then explicit singleton decode bound.
    with pytest.raises(fetch.SnapshotError, match="BUDGET"):
        fetch._validate_checkpoint(
            run,
            next(iter(fetch._lines(run.path("fetch/acquisition_plan.jsonl")))),
            receipt,
        )
    for name in ("result.json", "fetch/control.json", "fetch/snapshot_manifest.json"):
        assert run.path(name).stat().st_size < fetch.MAX_CONTROL


@pytest.mark.parametrize("boundary", ["index_control", "manifest_seal"])
def test_interrupt_at_durable_commit_boundaries_resumes_without_refetch(
    old, tmp_path, monkeypatch, boundary
):
    original = fetch._write

    def interrupted(path, value):
        if (
            boundary == "index_control"
            and path.name == "control.json"
            and value.get("committed_slots") == 1
            or boundary == "manifest_seal"
            and path.name == "seal.json"
        ):
            raise KeyboardInterrupt()
        return original(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(fetch, "_write", interrupted)
        with pytest.raises(KeyboardInterrupt):
            start(old, tmp_path)
    transport = Transport()
    result = fetch.resume_fetch(
        OP,
        project_root=old,
        root=tmp_path / "runs",
        client=transport.client(),
        now=lambda: NOW,
    )
    assert result["status"] == "FETCH_SEALED"
    assert transport.calls == (
        [("AAA", "MRQ"), ("BBB", "ARQ"), ("BBB", "MRQ")]
        if boundary == "index_control"
        else []
    )


def test_no_new_operation_can_import_other_sealed_evidence(old, tmp_path):
    first = start(old, tmp_path)
    second = "fetch_" + "b" * 32
    transport = Transport()
    result = fetch.start_fetch(
        ["AAA"],
        project_root=old,
        root=tmp_path / "runs",
        operation_id=second,
        source_day="2026-11-11",
        client=transport.client(),
        now=lambda: NOW,
    )
    assert transport.calls[1:] == [("AAA", "ARQ"), ("AAA", "MRQ")]
    with pytest.raises(fetch.SnapshotError, match="REFERENCE"):
        fetch.open_snapshot(
            second,
            root=tmp_path / "runs",
            expected_reference=first["snapshot_reference"],
        )


@pytest.mark.parametrize("change", ["attempt", "capture", "horizon", "coverage"])
def test_receipt_semantic_tamper_rejected_even_with_rehashed_unsealed_index(
    old, tmp_path, change
):
    with pytest.raises(KeyboardInterrupt):
        start(old, tmp_path, Transport(fail_at=("AAA", "MRQ")))
    path, receipt = checkpoint(tmp_path)
    if change == "attempt":
        receipt["transport_attempt_id"] = "0" * 32
    elif change == "horizon":
        receipt["parameters"]["from"] = "2025-11-11"
    elif change == "coverage":
        receipt["coverage"]["row_count"] = 999
    else:
        cap_path = tmp_path / "runs" / OP / receipt["captures"]["relative_path"]
        value = json.loads(cap_path.read_text())
        value["envelope"]["acquired_at_utc"] = "2026-11-10T12:00:00+00:00"
        cap_path.write_text(json.dumps(value) + "\n")
        receipt["captures"]["sha256"] = sha256_file(cap_path)
        receipt["captures"]["size_bytes"] = cap_path.stat().st_size
    path.write_text(json.dumps(receipt) + "\n")
    run = fetch._Run(tmp_path / "runs", OP)
    fetch._write_index(run, {0: receipt})
    transport = Transport()
    with pytest.raises(fetch.SnapshotError):
        fetch.resume_fetch(
            OP,
            project_root=old,
            root=tmp_path / "runs",
            client=transport.client(),
            now=lambda: NOW,
        )
    assert not transport.calls


def test_expiry_is_enforced_at_seal_not_only_resume_entry(old, tmp_path, monkeypatch):
    original = fetch._seal
    monkeypatch.setattr(
        fetch,
        "_seal",
        lambda run, control, checkpoints, times, now: original(
            run,
            control,
            checkpoints,
            times,
            now + timedelta(seconds=fetch.MAX_AGE_SECONDS + 1),
        ),
    )
    with pytest.raises(fetch.SnapshotError, match="EXPIRED"):
        start(old, tmp_path)
    assert not (tmp_path / "runs" / OP / "fetch/seal.json").exists()
    assert checkpoint(tmp_path, 3)[1]["state"] == "COMPLETE_VERIFIED"


@pytest.mark.parametrize(
    "case", ["wrong_schema", "secret_echo", "invalid_utf8", "oversize"]
)
def test_native_transport_refuses_untrusted_or_unbounded_capture(
    old, tmp_path, monkeypatch, case
):
    if case == "oversize":
        monkeypatch.setattr(fetch, "MAX_RESPONSE_BYTES", 1024)

    def change(identity, rows):
        if case == "secret_echo":
            rows[0]["extra"] = SECRET
        if case == "invalid_utf8":
            return Response(b"\xff")
        if case == "oversize":
            return Response(b" " * 1025)
        return rows

    transport = Transport(change=change)
    if case == "wrong_schema":
        original = transport.__class__.__call__

        class BadSchema(Transport):
            def __call__(self, request, timeout):
                if "/schema/" in request.full_url:
                    return Response(["ticker"])
                return original(self, request, timeout)

        transport = BadSchema()
    try:
        result = start(old, tmp_path, transport)
        assert result["status"] == "FETCH_BLOCKED"
    except (fetch.SnapshotError, ValueError):
        pass
    assert not (tmp_path / "runs" / OP / "fetch/checkpoints/000000.json").exists()
    assert SECRET not in "\n".join(
        p.read_text() for p in (tmp_path / "runs").rglob("*") if p.is_file()
    )


def test_native_root_manifest_binds_snapshot_reference_without_raw_inline(
    old, tmp_path
):
    result = start(old, tmp_path)
    directory = tmp_path / "runs" / OP
    manifest = json.loads((directory / "artifact_manifest.json").read_text())
    entries = {entry["name"]: entry for entry in manifest["artifacts"]}
    reference = json.loads(
        (directory / "acquisition_snapshot_reference.json").read_text()
    )
    assert reference["manifest"] == result["snapshot_reference"]
    assert reference["publication_authorized"] is False
    assert entries["acquisition_snapshot_reference.json"]["sha256"] == sha256_file(
        directory / "acquisition_snapshot_reference.json"
    )
    assert (directory / "artifact_manifest.json").stat().st_size < fetch.MAX_CONTROL
    assert all("raw" not in item for item in entries.values())


def test_killed_dispatch_uncertainty_is_reported_separately(old, tmp_path):
    with pytest.raises(KeyboardInterrupt):
        start(old, tmp_path, Transport(fail_at=("AAA", "MRQ")))
    ledger = tmp_path / "runs" / OP / "fetch/attempts.jsonl"
    events = list(fetch._lines(ledger))
    assert events[-1]["event"] == "INTERRUPTED"
    # Model SIGKILL before a terminal event can be written. No receipt exists
    # for this attempt; its STARTED remains indeterminate after explicit resume.
    ledger.write_text("".join(json.dumps(e) + "\n" for e in events[:-1]))
    transport = Transport()
    result = fetch.resume_fetch(
        OP,
        project_root=old,
        root=tmp_path / "runs",
        client=transport.client(),
        now=lambda: NOW,
    )
    assert result["actual_http_attempts"] == 5
    assert result["dispatch_intents"] == 6
    assert result["indeterminate_http_attempts"] == 1
