"""Operation-owned SEC bytes; native parsing/resolution, no offline fallback."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import time
from pathlib import Path
from urllib.error import URLError

from rawcandle.fundamentals.result_publication import SecClient
from .artifacts import sha256_file
from .contracts import fingerprint
from . import publication_journal as journal

CONTRACT = "FUNDAMENTALS_UPDATE_SEC_INPUTS_V1"
NETWORK_BUDGET_SECONDS = 300


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
        or sha256_file(path) != name
    ):
        raise ValueError("SEC_BUNDLE_CONTENT_TAMPERED")
    return path.read_bytes()


def capture(
    directory: Path,
    *,
    operation_id,
    snapshot_reference,
    plan,
    fetch_bytes=None,
    now=lambda: datetime.now(timezone.utc),
):
    """Run the native bounded reader once, preserving every requested raw body.

    Planning is an identity/period superset, never financial acceptance. The
    native client's existing deadline, throttle and retry semantics are retained.
    Failed documents remain explicit errors, including optional exhibit errors.
    """
    directory = Path(directory)
    if (directory / "manifest.json").exists():
        return open_bundle(
            directory, operation_id=operation_id, snapshot_reference=snapshot_reference
        )[0]
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "bytes").mkdir(exist_ok=True)
    if any(
        p.is_symlink() for p in (directory, directory / "bytes", *directory.parents)
    ):
        raise ValueError("SEC_BUNDLE_UNTRUSTED_PATH")
    requests = {}
    budget_started_at = now()
    pending = directory / "pending.json"
    if pending.exists():
        previous = json.loads(pending.read_text())
        if (
            previous.get("operation_id") != operation_id
            or previous.get("snapshot_reference") != snapshot_reference
            or previous.get("plan") != plan
            or previous.get("fingerprint")
            != fingerprint({k: v for k, v in previous.items() if k != "fingerprint"})
        ):
            raise ValueError("SEC_PENDING_CAPTURE_BINDING_MISMATCH")
        requests = previous["requests"]
        budget_started_at = datetime.fromisoformat(previous["budget_started_at_utc"])
        if budget_started_at > now():
            raise ValueError("SEC_CAPTURE_BUDGET_CLOCK_IN_FUTURE")

    def checkpoint():
        value = {
            "operation_id": operation_id,
            "snapshot_reference": snapshot_reference,
            "plan": plan,
            "requests": requests,
            "budget_started_at_utc": budget_started_at.isoformat(),
        }
        value["fingerprint"] = fingerprint(value)
        _write(pending, value)

    checkpoint()

    class RecordingClient(SecClient):
        def _request(self, url):
            if url in requests:
                if "error" in requests[url]:
                    raise URLError("SEC_CAPTURED_REQUEST_FAILED:" + url)
                self.stats["resumed_capture_hits"] += 1
                return _content(directory, requests[url])
            try:
                if time.monotonic() >= self._deadline:
                    self.stats["budget_exhausted"] += 1
                    raise TimeoutError("SEC_CANDIDATE_TIME_BUDGET_EXHAUSTED")
                body = fetch_bytes(url) if fetch_bytes else super()._request(url)
                if not isinstance(body, bytes):
                    raise TypeError("SEC_CAPTURE_REQUIRES_RAW_BYTES")
                digest = hashlib.sha256(body).hexdigest()
                path = directory / "bytes" / digest
                if not path.exists():
                    with path.open("xb") as f:
                        f.write(body)
                        f.flush()
                        import os

                        os.fsync(f.fileno())
                requests[url] = {
                    "sha256": digest,
                    "size": len(body),
                    "acquired_at_utc": now().isoformat(),
                }
                checkpoint()
                return body
            except Exception as error:
                requests[url] = {
                    "error": type(error).__name__,
                    "reason": str(error),
                    "acquired_at_utc": now().isoformat(),
                }
                checkpoint()
                raise

    remaining = max(
        0, NETWORK_BUDGET_SECONDS - (now() - budget_started_at).total_seconds()
    )
    client = RecordingClient(maximum_runtime_seconds=remaining)
    outcomes = []
    for scope in plan:
        try:
            filings = client.item_2_02_filings(
                scope["cik"],
                from_calendar_year=scope["from_calendar_year"],
                from_calendar_date=scope["from_calendar_date"],
                to_calendar_date=scope["to_calendar_date"],
            )
            outcomes.append(
                {"company_id": scope["company_id"], "filings": len(filings)}
            )
        except Exception as error:
            outcomes.append(
                {
                    "company_id": scope["company_id"],
                    "error": type(error).__name__,
                    "reason": str(error),
                }
            )
    value = {
        "contract": CONTRACT,
        "operation_id": operation_id,
        "snapshot_reference": snapshot_reference,
        "plan": plan,
        "requests": requests,
        "outcomes": outcomes,
        "network_budget_seconds": NETWORK_BUDGET_SECONDS,
        "budget_started_at_utc": budget_started_at.isoformat(),
        "sealed_at_utc": now().isoformat(),
        "network": dict(client.stats),
    }
    value["fingerprint"] = fingerprint(value)
    _write(directory / "manifest.json", value)
    if pending.exists():
        pending.unlink()
    journal.fsync_directory(directory / "bytes")
    journal.fsync_directory(directory)
    return value


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
