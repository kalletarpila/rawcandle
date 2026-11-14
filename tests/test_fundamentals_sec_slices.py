"""Offline SEC slices on the same UPDATE, bytes and native parser/retry policy."""
from datetime import datetime, timedelta, timezone
import json
from urllib.error import HTTPError, URLError

import pytest

from rawcandle.fundamentals.admin import sec_snapshot as sec
from rawcandle.fundamentals.admin.contracts import fingerprint

NOW = datetime(2026, 11, 14, 12, tzinfo=timezone.utc)
REFERENCE = {"operation_id": "same-fetch", "sha256": "immutable-source"}


class Clock:
    seconds = 0.0
    def monotonic(self):
        return self.seconds + 1
    def sleep(self, seconds):
        self.seconds += seconds
    def now(self):
        return NOW + timedelta(seconds=self.seconds)


def plan(count=3):
    return [dict(company_id=i, cik=str(i), from_calendar_year=2026,
                 from_calendar_date="2026-01-01", to_calendar_date="2026-12-31")
            for i in range(1, count + 1)]


def body(url):
    if "submissions" in url:
        return json.dumps({"filings": {"recent": {
            "form": ["8-K"], "items": ["2.02"],
            "accessionNumber": ["0000000001-26-000001"],
            "acceptanceDateTime": ["2026-11-04T20:00:00Z"],
            "primaryDocument": ["result.htm"],
        }}}).encode()
    return b"Item 2.02 Results of Operations and Financial Condition. Third quarter ended September 30, 2026."


@pytest.fixture
def clock(monkeypatch):
    value = Clock()
    monkeypatch.setattr(sec.time, "monotonic", value.monotonic)
    monkeypatch.setattr(sec.time, "sleep", value.sleep)
    return value


def capture(path, clock, fetch, count=3):
    return sec.capture(path, operation_id="same-update", snapshot_reference=REFERENCE,
                       plan=plan(count), fetch_bytes=fetch, now=clock.now)


def test_three_fresh_300_second_slices_skip_completed_scopes(tmp_path, clock):
    calls, results = [], []
    def fetch(url):
        calls.append(url)
        clock.sleep(150)
        return body(url)
    first = capture(tmp_path, clock, fetch)
    assert sec.capture_progress(first)["pending_scopes"] == 2
    assert first["slice"]["request_count"] == 2
    assert not (tmp_path / "manifest.json").exists()
    preserved = {u: dict(r) for u, r in first["requests"].items() if "sha256" in r}
    hashes = {p.name: p.read_bytes() for p in (tmp_path / "bytes").iterdir()}
    results.append(first)
    second = capture(tmp_path, clock, fetch)
    assert sec.capture_progress(second)["resolved_scopes"] == 2
    assert second["slice"]["request_count"] == 2
    final = capture(tmp_path, clock, fetch)
    results += [second, final]
    assert sec.capture_progress(final)["can_advance_to_validate"]
    assert len(calls) == len(set(calls)) == 6
    assert final["slice_count"] == 3 and final["request_attempts"] == 6
    assert all(final["requests"][u] == r for u, r in preserved.items())
    assert all((tmp_path / "bytes" / name).read_bytes() == data for name, data in hashes.items())
    assert {r["budget_started_at_utc"] for r in results} == {NOW.isoformat()}
    assert sec.capture_progress(final)["newly_completed_scopes"] == 1
    before = (tmp_path / "manifest.json").read_bytes()
    capture(tmp_path, clock, lambda _: pytest.fail("sealed capture refetched"))
    assert (tmp_path / "manifest.json").read_bytes() == before


def test_partial_scope_reuses_successful_url_and_original_hash(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(sec, "MAX_REQUESTS_PER_SLICE", 1)
    calls = []
    def fetch(url):
        calls.append(url)
        return body(url)
    first = capture(tmp_path, clock, fetch, 1)
    original = dict(next(iter(first["requests"].values())))
    assert sec.capture_progress(first)["pending_scopes"] == 1
    final = capture(tmp_path, clock, fetch, 1)
    assert len(calls) == 2
    assert final["requests"][calls[0]] == original


def test_native_pacing_is_retained_at_slice_boundary(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(sec, "MAX_REQUESTS_PER_SLICE", 2)
    intervals = []
    def fetch(url):
        begin = clock.seconds
        clock.sleep(10)
        intervals.append((begin, clock.seconds))
        return body(url)
    capture(tmp_path, clock, fetch, 2)
    capture(tmp_path, clock, fetch, 2)
    assert len(intervals) == 4
    assert intervals[2][0] - intervals[1][1] >= 0.119


def test_crash_after_durable_response_never_refetches_it(tmp_path, clock, monkeypatch):
    write = sec._write
    def interrupted(path, value):
        write(path, value)
        if path.name == "pending.json" and any("sha256" in r for r in value["requests"].values()):
            raise KeyboardInterrupt("after durable response")
    calls = []
    def fetch(url):
        calls.append(url)
        return body(url)
    with monkeypatch.context() as patch:
        patch.setattr(sec, "_write", interrupted)
        with pytest.raises(KeyboardInterrupt):
            capture(tmp_path, clock, fetch, 1)
    final = capture(tmp_path, clock, fetch, 1)
    assert len(calls) == len(set(calls)) == 2
    assert final["request_attempts"] == 2


def test_concurrent_capture_cannot_repeat_requests(tmp_path, clock):
    import fcntl
    with (tmp_path / "capture.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(ValueError, match="ALREADY_RUNNING"):
            capture(tmp_path, clock, lambda _: pytest.fail("concurrent request"), 1)


def test_retry_wait_and_attempts_survive_crash_and_later_slice(tmp_path, clock, monkeypatch):
    write = sec._write
    calls = []
    def fetch(url):
        calls.append(url)
        if "CIK0000000001" in url and calls.count(url) == 1:
            raise URLError("transient")
        return body(url)
    def interrupted(path, value):
        write(path, value)
        if path.name == "pending.json" and any(r.get("error") for r in value["requests"].values()):
            raise KeyboardInterrupt("after retry checkpoint")
    with monkeypatch.context() as patch:
        patch.setattr(sec, "_write", interrupted)
        with pytest.raises(KeyboardInterrupt):
            capture(tmp_path, clock, fetch, 2)
    waiting = capture(tmp_path, clock, fetch, 2)
    assert sec.capture_progress(waiting, now=clock.now())["retry_wait_scopes"] == 1
    assert sec.capture_progress(waiting, now=clock.now())["resolved_scopes"] == 1
    assert calls.count(calls[0]) == 1
    clock.sleep(1)
    final = capture(tmp_path, clock, fetch, 2)
    assert final["requests"][calls[0]]["attempt_count"] == 2
    assert len(final["requests"][calls[0]]["failures"]) == 1
    assert sec.capture_progress(final)["resolved_scopes"] == 2


def test_native_three_attempt_limit_does_not_reset_between_slices(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(sec, "MAX_REQUESTS_PER_SLICE", 1)
    calls = []
    def fetch(url):
        calls.append(url)
        raise HTTPError(url, 503, "temporary outage", {}, None)
    for _ in range(3):
        result = capture(tmp_path, clock, fetch, 1)
        clock.sleep(2)
    if not (tmp_path / "manifest.json").exists():
        result = capture(tmp_path, clock, fetch, 1)
    assert len(calls) == 3
    assert next(iter(result["requests"].values()))["attempt_count"] == 3
    assert sec.capture_progress(result)["locally_unresolved_scopes"] == 1


def test_local_missing_source_does_not_block_safe_peer(tmp_path, clock):
    def fetch(url):
        if "CIK0000000001" in url:
            raise HTTPError(url, 404, "not found", {}, None)
        return body(url)
    value = capture(tmp_path, clock, fetch, 2)
    progress = sec.capture_progress(value)
    assert progress["resolved_scopes"] == progress["locally_unresolved_scopes"] == 1
    assert progress["can_advance_to_validate"]
    _, client = sec.open_bundle(tmp_path, operation_id="same-update", snapshot_reference=REFERENCE)
    with pytest.raises(URLError):
        client.item_2_02_filings("1", from_calendar_year=2026)


def test_mapping_issue_is_local_and_durable_storage_error_is_shared(tmp_path, clock, monkeypatch):
    scopes = plan(2)
    scopes[0]["cik"] = None
    value = sec.capture(tmp_path / "mapping", operation_id="same-update", snapshot_reference=REFERENCE,
                        plan=scopes, fetch_bytes=body, now=clock.now)
    assert sec.capture_progress(value)["locally_unresolved_scopes"] == 1
    assert sec.capture_progress(value)["resolved_scopes"] == 1
    from pathlib import Path
    original = Path.open
    def broken(path, *args, **kwargs):
        if path.parent.name == "bytes" and args and args[0] == "xb":
            raise OSError("durable storage unavailable")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "open", broken)
    with pytest.raises(sec.SharedCaptureError, match="DURABLE_CAPTURE_FAILED"):
        capture(tmp_path / "storage", clock, body, 2)
    assert not (tmp_path / "storage/manifest.json").exists()


@pytest.mark.parametrize("failure", ["forbidden", "invalid_json", "nonbytes", "unexpected"])
def test_shared_source_failure_stops_and_cannot_auto_retry(tmp_path, clock, failure):
    calls = []
    def fetch(url):
        calls.append(url)
        if failure == "forbidden":
            raise HTTPError(url, 403, "common configuration", {}, None)
        if failure == "unexpected":
            raise RuntimeError()
        return b"not json" if failure == "invalid_json" else None
    with pytest.raises(sec.SharedCaptureError):
        capture(tmp_path, clock, fetch, 2)
    assert len(calls) == 1 and not (tmp_path / "manifest.json").exists()
    with pytest.raises(sec.SharedCaptureError):
        capture(tmp_path, clock, fetch, 2)
    assert len(calls) == 1


def test_capture_expiry_not_reset_by_new_slice(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(sec, "MAX_REQUESTS_PER_SLICE", 1)
    capture(tmp_path, clock, body, 1)
    before = (tmp_path / "pending.json").read_bytes()
    clock.sleep(169 * 3600)
    with pytest.raises(ValueError):
        capture(tmp_path, clock, lambda _: pytest.fail("expired fetch"), 1)
    assert (tmp_path / "pending.json").read_bytes() == before


def test_completed_evidence_tampering_stops_final_seal(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(sec, "MAX_REQUESTS_PER_SLICE", 2)
    first = capture(tmp_path, clock, body, 2)
    digest = next(iter(first["requests"].values()))["sha256"]
    (tmp_path / "bytes" / digest).write_bytes(b"tampered")
    with pytest.raises(sec.SharedCaptureError, match="TAMPERED"):
        capture(tmp_path, clock, body, 2)
    assert not (tmp_path / "manifest.json").exists()


@pytest.mark.parametrize("status", ["PENDING", "RETRY_WAIT", "UNKNOWN"])
def test_unfinished_scope_cannot_be_consumed_as_sealed_bundle(tmp_path, clock, status):
    value = capture(tmp_path, clock, body, 1)
    value["outcomes"][0]["status"] = status
    value.pop("fingerprint")
    sec._write(tmp_path / "manifest.json", value | {"fingerprint": fingerprint(value)})
    with pytest.raises(ValueError, match="INCOMPLETE"):
        sec.open_bundle(tmp_path, operation_id="same-update", snapshot_reference=REFERENCE)


def test_legacy_pending_budget_and_successful_record_are_preserved(tmp_path, clock):
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "bytes").mkdir()
    import hashlib
    url = "https://data.sec.gov/submissions/CIK0000000001.json"
    payload = body(url)
    digest = hashlib.sha256(payload).hexdigest()
    (tmp_path / "bytes" / digest).write_bytes(payload)
    original = dict(sha256=digest, size=len(payload), acquired_at_utc=NOW.isoformat())
    old = dict(operation_id="same-update", snapshot_reference=REFERENCE, plan=plan(1),
               budget_started_at_utc=NOW.isoformat(), requests={url: original})
    old["fingerprint"] = fingerprint(old)
    sec._write(tmp_path / "pending.json", old)
    clock.sleep(301)
    value = capture(tmp_path, clock, body, 1)
    assert sec.capture_progress(value)["resolved_scopes"] == 1
    assert value["budget_started_at_utc"] == NOW.isoformat()
    assert value["requests"][url] == original
    assert value["legacy_request_attempts_unknown"]


def test_legacy_pending_budget_error_is_retained_as_observation(tmp_path, clock):
    url = "https://data.sec.gov/submissions/CIK0000000001.json"
    error = dict(error="TimeoutError", reason="SEC_CANDIDATE_TIME_BUDGET_EXHAUSTED",
                 acquired_at_utc=NOW.isoformat())
    old = dict(operation_id="same-update", snapshot_reference=REFERENCE, plan=plan(1),
               budget_started_at_utc=NOW.isoformat(), requests={url: error})
    sec._write(tmp_path / "pending.json", old | {"fingerprint": fingerprint(old)})
    clock.sleep(301)
    value = capture(tmp_path, clock, body, 1)
    assert value["requests"][url]["failures"] == [error]
    assert value["requests"][url]["attempt_count"] == 1


def test_corrupt_or_foreign_pending_state_stops_before_request(tmp_path, clock, monkeypatch):
    monkeypatch.setattr(sec, "MAX_REQUESTS_PER_SLICE", 1)
    capture(tmp_path, clock, body, 1)
    path = tmp_path / "pending.json"
    original = path.read_bytes()
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        sec.capture(tmp_path, operation_id="foreign", snapshot_reference=REFERENCE,
                    plan=plan(1), fetch_bytes=lambda _: pytest.fail("foreign fetch"), now=clock.now)
    assert path.read_bytes() == original
    path.write_bytes(original.replace(b"same-update", b"same-UPDATE"))
    corrupt = path.read_bytes()
    with pytest.raises(ValueError, match="BINDING_MISMATCH"):
        capture(tmp_path, clock, lambda _: pytest.fail("corrupt fetch"), 1)
    assert path.read_bytes() == corrupt


def test_legacy_sealed_budget_errors_remain_readable_and_unresolved(tmp_path, clock):
    old = dict(contract=sec.CONTRACT, operation_id="same-update", snapshot_reference=REFERENCE,
               plan=plan(1), requests={}, budget_started_at_utc=NOW.isoformat(),
               outcomes=[{"company_id": 1, "error": "TimeoutError", "reason": "SEC_CANDIDATE_TIME_BUDGET_EXHAUSTED"}])
    sec._write(tmp_path / "manifest.json", old | {"fingerprint": fingerprint(old)})
    before = (tmp_path / "manifest.json").read_bytes()
    value = capture(tmp_path, clock, lambda _: pytest.fail("legacy refetch"), 1)
    assert sec.capture_progress(value)["locally_unresolved_scopes"] == 1
    assert (tmp_path / "manifest.json").read_bytes() == before


def test_same_update_waits_for_sec_slices_before_validate(tmp_path, monkeypatch):
    import sqlite3
    from tests import test_fundamentals_snapshot_workflow as fixtures
    from tests import test_fundamentals_snapshot_integration as integration
    original = fixtures.native._migrate_refresh_fixture_to_generation_layout
    def prepare(fixture, patch):
        with sqlite3.connect(fixture.paths.canonical_db) as db:
            db.execute("""INSERT INTO company_cik(company_id,cik_normalized,cik_display,source,status,created_at_utc,
                         source_type,source_name,source_field,source_value,derivation,confidence)
                         VALUES(1,'0000000001','1','TEST','ACTIVE',?,'TEST','SEC','CIK','1','DIRECT','HIGH')""",
                       (fixtures.native.NOW,))
        original(fixture, patch)
    monkeypatch.setattr(fixtures.native, "_migrate_refresh_fixture_to_generation_layout", prepare)
    workflow, _, histories, sharadar_calls = integration.setup(tmp_path, monkeypatch)
    for dimension in ("ARQ", "MRQ"):
        histories["AAA"][dimension].append(fixtures.native._source_row("AAA", dimension, 2026, 3, lastupdated="2026-11-04"))
    requests = []
    def fetch(url):
        requests.append(url)
        return body(url)
    workflow.sec_fetch_bytes = fetch
    monkeypatch.setattr(sec, "MAX_REQUESTS_PER_SLICE", 0)
    first = workflow.start(publication_intent=False, ownership_intent=False, stop_after="validate")
    assert first["outcome"] == "FETCH_PAUSED", first
    assert not first.get("validation_id") and not requests
    update, snapshot, previous_calls = first["run_id"], first["fetch_operation_id"], list(sharadar_calls)
    clock = Clock()
    clock.now = lambda: fixtures.NOW + timedelta(seconds=clock.seconds)
    monkeypatch.setattr(sec.time, "monotonic", clock.monotonic)
    monkeypatch.setattr(sec.time, "sleep", clock.sleep)
    monkeypatch.setattr(sec, "MAX_REQUESTS_PER_SLICE", 1)
    workflow.now = clock.now
    workflow.env.clock = clock.now
    second = workflow.advance(update, stop_after="validate")
    assert second["outcome"] == "FETCH_PAUSED" and not second.get("validation_id"), second
    assert not (workflow.env.directory() / "update_sources.json").exists()
    third = workflow.advance(update, stop_after="validate")
    assert third["outcome"] == "VALIDATED", third
    assert third["run_id"] == update and third["fetch_operation_id"] == snapshot
    assert sharadar_calls == previous_calls
    assert len(requests) == len(set(requests)) == 2
    assert third["sec_acquisition"]["can_advance_to_validate"]
