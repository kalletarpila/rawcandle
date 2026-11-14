"""Operation-owned SEC bytes; native parsing/resolution, no offline fallback."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections import Counter
import fcntl
import os
import hashlib
import json
import time
from pathlib import Path
from urllib.error import HTTPError, URLError

from rawcandle.fundamentals.result_publication import SecClient, SEC_REQUEST_ATTEMPTS
from .artifacts import sha256_file
from .contracts import fingerprint
from . import publication_journal as journal

CONTRACT = "FUNDAMENTALS_UPDATE_SEC_INPUTS_V1"
NETWORK_BUDGET_SECONDS = 300
MAX_REQUESTS_PER_SLICE = 2500


def _write(path, value):
    journal._atomic_json(path, value)


def _content(directory, record):
    name = record.get("sha256", "")
    if len(name) != 64 or any(c not in "0123456789abcdef" for c in name):
        raise ValueError("SEC_BUNDLE_CONTENT_ID_INVALID")
    path = directory / "bytes" / name
    if (
        path.parent.is_symlink()
        or path.is_symlink()
        or path.stat().st_nlink != 1
    ):
        raise ValueError("SEC_BUNDLE_CONTENT_TAMPERED")
    body = path.read_bytes()
    if hashlib.sha256(body).hexdigest() != name or len(body) != record.get("size"):
        raise ValueError("SEC_BUNDLE_CONTENT_TAMPERED")
    return body


class _SlicePaused(RuntimeError):
    pass


class _RetryWait(RuntimeError):
    pass


class SharedCaptureError(RuntimeError):
    def __init__(self, reason, progress=None):
        super().__init__(reason)
        self.progress = progress


def capture_progress(value, *, now=None):
    """Execution coverage, never financial publication/date acceptance."""
    current_time = now or datetime.now(timezone.utc)
    states = [item.get("status", "SOURCE_UNRESOLVED" if "error" in item or not item.get("filings") else "COMPLETED")
              for item in value["outcomes"]]
    counts = Counter(states)
    shared = bool(value.get("shared_failure")) or bool(counts["TERMINAL_FAILURE"])
    remaining = counts["PENDING"] + counts["RETRY_WAIT"]
    return {
        "status": "FAILED" if shared else "FETCH_PAUSED" if remaining else "COMPLETED",
        "total_scopes": len(value["plan"]), "resolved_scopes": counts["COMPLETED"],
        "pending_scopes": counts["PENDING"], "retry_wait_scopes": counts["RETRY_WAIT"],
        "locally_unresolved_scopes": counts["SOURCE_UNRESOLVED"],
        "terminal_failures": max(counts["TERMINAL_FAILURE"], int(shared)),
        "shared_failure": value.get("shared_failure"),
        "remaining_scopes": remaining,
        "can_advance_to_validate": not remaining and not shared,
        "newly_completed_scopes": value.get("slice", {}).get("newly_completed_scopes", 0),
        "elapsed_seconds": value.get("slice", {}).get("elapsed_seconds", 0),
        "request_count": value.get("slice", {}).get("request_count", 0),
        "additional_eligible_work": bool(counts["PENDING"] or any(
            o.get("status") == "RETRY_WAIT" and datetime.fromisoformat(o["retry_after_utc"]) <= current_time
            for o in value["outcomes"])),
        "next_retry_at_utc": min((o["retry_after_utc"] for o in value["outcomes"]
                                  if o.get("status") == "RETRY_WAIT"), default=None),
    }


def capture(
    directory: Path, *, operation_id, snapshot_reference, plan, fetch_bytes=None,
    now=lambda: datetime.now(timezone.utc),
):
    """Use the native nonblocking per-operation lease pattern, never a production lock."""
    directory = Path(directory)
    if (directory / "manifest.json").exists():
        return _capture_slice(directory, operation_id=operation_id,
                              snapshot_reference=snapshot_reference, plan=plan,
                              fetch_bytes=fetch_bytes, now=now)
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("SEC_BUNDLE_UNTRUSTED_PATH")
    directory.mkdir(parents=True, exist_ok=True)
    fd = os.open(directory / "capture.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        if os.fstat(fd).st_nlink != 1:
            raise ValueError("SEC_CAPTURE_LOCK_UNTRUSTED")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("SEC_CAPTURE_ALREADY_RUNNING") from error
        return _capture_slice(directory, operation_id=operation_id,
                              snapshot_reference=snapshot_reference, plan=plan,
                              fetch_bytes=fetch_bytes, now=now)
    finally:
        os.close(fd)


def _capture_slice(
    directory: Path, *, operation_id, snapshot_reference, plan, fetch_bytes=None,
    now=lambda: datetime.now(timezone.utc),
):
    """One bounded slice of the existing pending capture; immutable seal at completion.

    The original capture time remains provenance/freshness authority. Only the
    invocation's monotonic deadline is reset. Native HTTP pacing/retries remain.
    """
    from .acquisition_snapshot import _age, _time

    directory = Path(directory)
    if any(p.is_symlink() for p in (directory, directory / "bytes", *directory.parents)):
        raise ValueError("SEC_BUNDLE_UNTRUSTED_PATH")
    if (directory / "manifest.json").exists():
        sealed = open_bundle(directory, operation_id=operation_id,
                             snapshot_reference=snapshot_reference)[0]
        if sealed["plan"] != plan:
            raise ValueError("SEC_PENDING_CAPTURE_BINDING_MISMATCH")
        _age([_time(sealed["budget_started_at_utc"])], now())
        return sealed  # Legacy sealed observations are never rewritten/retried.
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "bytes").mkdir(exist_ok=True)
    pending = directory / "pending.json"
    previous = {}
    if pending.exists():
        if pending.is_symlink() or pending.stat().st_nlink != 1:
            raise ValueError("SEC_PENDING_UNTRUSTED_PATH")
        previous = json.loads(pending.read_text())
        if (previous.get("contract", CONTRACT) != CONTRACT
                or previous.get("operation_id") != operation_id
                or previous.get("snapshot_reference") != snapshot_reference
                or previous.get("plan") != plan
                or previous.get("fingerprint") != fingerprint(
                    {k: v for k, v in previous.items() if k != "fingerprint"})):
            raise ValueError("SEC_PENDING_CAPTURE_BINDING_MISMATCH")
    started_at = previous.get("budget_started_at_utc", now().isoformat())
    _age([_time(started_at)], now())
    requests = previous.get("requests", {})
    outcomes = previous.get("outcomes", [{"company_id": s["company_id"], "status": "PENDING"} for s in plan])
    if (len(outcomes) != len(plan) or any(
            o.get("company_id") != s["company_id"] or o.get("status") not in {
                "PENDING", "RETRY_WAIT", "COMPLETED", "SOURCE_UNRESOLVED", "TERMINAL_FAILURE"}
            for o, s in zip(outcomes, plan))):
        raise ValueError("SEC_PENDING_SCOPE_BINDING_MISMATCH")
    if previous.get("shared_failure") or any(o["status"] == "TERMINAL_FAILURE" for o in outcomes):
        raise SharedCaptureError(previous.get("shared_failure") or "SEC_CAPTURE_TERMINAL_FAILURE",
                                 capture_progress(previous, now=now()))
    for record in requests.values():
        if "sha256" in record and "error" in record:
            raise ValueError("SEC_PENDING_REQUEST_STATE_INVALID")
        if type(record.get("attempt_count", 0)) is not int or record.get("attempt_count", 0) < 0:
            raise ValueError("SEC_PENDING_ATTEMPTS_INVALID")
    slice_started = time.monotonic()
    slice_started_at = now()
    slice_requests = newly_completed = 0
    local_retry_deadlines = {}
    base_network = Counter(previous.get("network", {}))
    base_attempts = previous.get("request_attempts", 0)
    value = dict(contract=CONTRACT, operation_id=operation_id, snapshot_reference=snapshot_reference,
                 plan=plan, requests=requests, outcomes=outcomes,
                 budget_started_at_utc=started_at,
                 last_slice_started_at_utc=slice_started_at.isoformat(),
                 slice_count=previous.get("slice_count", 0) + 1,
                 legacy_request_attempts_unknown=previous.get("legacy_request_attempts_unknown", False)
                     or any("attempt_count" not in r for r in requests.values()),
                 network_budget_seconds=NETWORK_BUDGET_SECONDS)
    client = None
    scope_urls = set()

    def checkpoint():
        value["slice"] = dict(request_count=slice_requests, request_limit=MAX_REQUESTS_PER_SLICE,
                              elapsed_seconds=time.monotonic() - slice_started,
                              newly_completed_scopes=newly_completed)
        value["network"] = dict(base_network + (client.stats if client else Counter()))
        value["network"]["network_requests"] = base_network["network_requests"] + slice_requests
        value["request_attempts"] = base_attempts + slice_requests
        value["progress"] = capture_progress(value, now=now())
        _write(pending, value | {"fingerprint": fingerprint(value)})

    class RecordingClient(SecClient):
        def _request(self, url):
            scope_urls.add(url)
            if url in self._cache:
                self.stats["cache_hits"] += 1
                return self._cache[url]
            record = requests.get(url, {})
            if "sha256" in record:
                self.stats["resumed_capture_hits"] += 1
                try:
                    body = _content(directory, record)
                    self._cache[url] = body
                    return body
                except (OSError, ValueError) as error:
                    raise SharedCaptureError(str(error)) from error
            if record.get("shared_failure"):
                raise SharedCaptureError(record["reason"])
            if "error" in record:
                # Legacy pending captures cached errors. Budget observations were
                # not real attempts; preserve them as history, never as success.
                legacy_budget = "BUDGET_EXHAUSTED" in record.get("reason", "")
                count = record.get("attempt_count", 0 if legacy_budget else SEC_REQUEST_ATTEMPTS)
                if not record.get("retryable", legacy_budget) or count >= SEC_REQUEST_ATTEMPTS:
                    raise URLError("SEC_CAPTURED_REQUEST_FAILED:" + url)
                retry_at = record.get("retry_after_utc")
                if retry_at and _time(retry_at) > now():
                    raise _RetryWait(retry_at)
            attempts_before = slice_requests
            try:
                return super()._request(url)
            except TimeoutError as error:
                if str(error) == "SEC_CANDIDATE_TIME_BUDGET_EXHAUSTED":
                    raise _SlicePaused(str(error)) from error
                raise
            finally:
                if slice_requests != attempts_before:
                    # SecClient paces from completion, not request start. Keep
                    # that boundary even when a new slice creates a new client.
                    value["last_request_finished_at_utc"] = now().isoformat()
                    checkpoint()

        def _before_request(self, url):
            nonlocal slice_requests
            if time.monotonic() >= self._deadline or slice_requests >= MAX_REQUESTS_PER_SLICE:
                self.stats["budget_exhausted"] += 1
                raise _SlicePaused("SEC_SLICE_BUDGET_EXHAUSTED")
            record = requests.setdefault(url, {})
            legacy_budget = "BUDGET_EXHAUSTED" in record.get("reason", "")
            attempts = record.get("attempt_count", 0 if legacy_budget or not record.get("error") else SEC_REQUEST_ATTEMPTS)
            if attempts >= SEC_REQUEST_ATTEMPTS:
                raise URLError("SEC_CAPTURED_REQUEST_RETRY_EXHAUSTED:" + url)
            if time.monotonic() < local_retry_deadlines.get(url, 0):
                raise _RetryWait(record["retry_after_utc"])
            if legacy_budget:
                record.setdefault("failures", []).append({k: record[k] for k in ("error", "reason", "acquired_at_utc") if k in record})
                record.pop("error", None)
                record.pop("reason", None)
            record.update(attempt_count=attempts + 1, last_attempt_at_utc=now().isoformat(), state="PENDING")
            slice_requests += 1
            checkpoint()  # Crash-safe accounting precedes the actual attempt.

        def _fetch_bytes(self, url, timeout):
            record = requests[url]
            try:
                body = fetch_bytes(url) if fetch_bytes else super()._fetch_bytes(url, timeout)
                if not isinstance(body, bytes):
                    raise TypeError("SEC_CAPTURE_REQUIRES_RAW_BYTES")
            except Exception as error:
                retryable = ((isinstance(error, HTTPError) and error.code in {429, 500, 502, 503, 504})
                             or isinstance(error, (URLError, TimeoutError)) and not isinstance(error, HTTPError))
                retryable = retryable and record["attempt_count"] < SEC_REQUEST_ATTEMPTS
                shared = isinstance(error, (TypeError, SharedCaptureError)) or isinstance(error, HTTPError) and error.code in {401, 403}
                wait = 0.5 * record["attempt_count"]
                record.update(error=type(error).__name__, reason=str(error), acquired_at_utc=now().isoformat(),
                              retryable=retryable, state="RETRY_WAIT" if retryable else "SOURCE_UNRESOLVED")
                record.setdefault("failures", []).append({k: record[k] for k in ("error", "reason", "acquired_at_utc", "attempt_count")})
                if retryable:
                    record["retry_after_utc"] = (now() + timedelta(seconds=wait)).isoformat()
                    local_retry_deadlines[url] = time.monotonic() + wait
                else:
                    record.pop("retry_after_utc", None)
                if shared:
                    record["shared_failure"] = True
                checkpoint()
                if shared:
                    raise SharedCaptureError(str(error)) from error
                raise
            try:
                digest = hashlib.sha256(body).hexdigest()
                path = directory / "bytes" / digest
                if path.exists():
                    _content(directory, {"sha256": digest, "size": len(body)})
                else:
                    with path.open("xb") as handle:
                        handle.write(body)
                        handle.flush()
                        os.fsync(handle.fileno())
                    journal.fsync_directory(path.parent)
            except (OSError, ValueError) as error:
                raise SharedCaptureError("SEC_DURABLE_CAPTURE_FAILED:" + str(error)) from error
            for key in ("error", "reason", "retry_after_utc", "retryable"):
                record.pop(key, None)
            record.update(sha256=digest, size=len(body), acquired_at_utc=now().isoformat(), state="COMPLETED")
            checkpoint()
            return body

    client = RecordingClient(maximum_runtime_seconds=NETWORK_BUDGET_SECONDS)
    timestamps = [r[key] for r in requests.values()
                  for key in ("last_attempt_at_utc", "acquired_at_utc") if r.get(key)]
    if previous.get("last_request_finished_at_utc"):
        timestamps.append(previous["last_request_finished_at_utc"])
        value["last_request_finished_at_utc"] = previous["last_request_finished_at_utc"]
    if timestamps:
        client._last_request = time.monotonic() - max(0, (now() - _time(max(timestamps))).total_seconds())
    checkpoint()
    for index, scope in enumerate(plan):
        if outcomes[index]["status"] in {"COMPLETED", "SOURCE_UNRESOLVED", "TERMINAL_FAILURE"}:
            continue
        if time.monotonic() >= client._deadline or slice_requests >= MAX_REQUESTS_PER_SLICE:
            client.stats["budget_exhausted"] += 1
            break
        scope_urls.clear()
        if not isinstance(scope["cik"], str) or not scope["cik"].isdigit():
            outcomes[index] = dict(company_id=scope["company_id"], status="SOURCE_UNRESOLVED",
                                   reason="SEC_COMPANY_CIK_UNRESOLVED")
            checkpoint()
            continue
        try:
            filings = client.item_2_02_filings(scope["cik"], from_calendar_year=scope["from_calendar_year"],
                         from_calendar_date=scope["from_calendar_date"], to_calendar_date=scope["to_calendar_date"])
            status = "COMPLETED" if filings and not any("error" in requests.get(url, {}) for url in scope_urls) else "SOURCE_UNRESOLVED"
            outcomes[index] = dict(company_id=scope["company_id"], status=status, filings=len(filings))
            newly_completed += status == "COMPLETED"
        except _SlicePaused:
            outcomes[index] = dict(company_id=scope["company_id"], status="PENDING")
            checkpoint()
            break
        except _RetryWait as error:
            outcomes[index] = dict(company_id=scope["company_id"], status="RETRY_WAIT", retry_after_utc=str(error))
        except Exception as error:
            shared = (isinstance(error, (SharedCaptureError, json.JSONDecodeError, KeyError))
                      or not isinstance(error, (HTTPError, URLError, TimeoutError, ValueError)))
            outcomes[index] = dict(company_id=scope["company_id"], status="TERMINAL_FAILURE" if shared else "SOURCE_UNRESOLVED",
                                   error=type(error).__name__, reason=str(error))
            if shared:
                value["shared_failure"] = str(error) or type(error).__name__
                checkpoint()
                raise SharedCaptureError(str(error), capture_progress(value, now=now())) from error
        checkpoint()
    checkpoint()
    if not capture_progress(value, now=now())["can_advance_to_validate"]:
        return value | {"fingerprint": fingerprint(value)}
    # The seal is the next consumption boundary: verify every durable body once.
    # Completed scopes were not reparsed/rehashed on every intermediate slice.
    try:
        for record in requests.values():
            if "sha256" in record:
                _content(directory, record)
    except (OSError, ValueError) as error:
        value["shared_failure"] = str(error) or type(error).__name__
        checkpoint()
        raise SharedCaptureError(str(error), capture_progress(value, now=now())) from error
    value.update(contract=CONTRACT, sealed_at_utc=now().isoformat())
    _write(directory / "manifest.json", value | {"fingerprint": fingerprint(value)})
    pending.unlink()
    journal.fsync_directory(directory)
    return value | {"fingerprint": fingerprint(value)}


def open_bundle(directory: Path, *, operation_id, snapshot_reference, expected=None):
    directory = Path(directory)
    if any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("SEC_BUNDLE_UNTRUSTED_PATH")
    path = directory / "manifest.json"
    if path.is_symlink():
        raise ValueError("SEC_BUNDLE_UNTRUSTED_PATH")
    value = json.loads(path.read_text())
    if (
        value.get("contract") != CONTRACT
        or value.get("operation_id") != operation_id
        or value.get("snapshot_reference") != snapshot_reference
        or value.get("fingerprint")
        != fingerprint({k: v for k, v in value.items() if k != "fingerprint"})
        or expected is not None
        and expected != sha256_file(path)
    ):
        raise ValueError("SEC_BUNDLE_BINDING_MISMATCH")
    if "slice_count" in value and (
        len(value["outcomes"]) != len(value["plan"])
        or any(o.get("company_id") != s["company_id"] for o, s in zip(value["outcomes"], value["plan"]))
        or any(o.get("status") not in {"COMPLETED", "SOURCE_UNRESOLVED", "TERMINAL_FAILURE"}
               for o in value["outcomes"])
        or not capture_progress(value)["can_advance_to_validate"]
    ):
        raise ValueError("SEC_BUNDLE_INCOMPLETE")
    for record in value["requests"].values():
        if "sha256" in record:
            _content(directory, record)
    return value, OfflineClient(directory, value)


class OfflineClient(SecClient):
    """The real SecClient parser with local URL reads, including date filtering."""

    def __init__(self, directory, manifest):
        super().__init__()
        self.directory, self.manifest = directory, manifest

    def _request(self, url):
        record = self.manifest["requests"].get(url)
        if not record or "error" in record:
            self.stats["offline_missing"] += 1
            raise URLError("SEC_INPUT_NOT_CAPTURED:" + url)
        self.stats["offline_hits"] += 1
        return _content(self.directory, record)
