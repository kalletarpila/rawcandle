"""Credential-scoped native HTTP coordination; no financial state lives here."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import time

from rawcandle.io_atomic import write_text_atomic


DEFAULT_ROOT = Path(__file__).resolve().parents[3] / "temp" / "sharadar_transport"


def retry_after_seconds(headers, *, now=None):
    """None means invalid/absent; zero is valid. Never clip server guidance."""
    value = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    if value is None:
        return None
    try:
        seconds = float(value)
        return seconds if math.isfinite(seconds) and seconds >= 0 else None
    except (ValueError, TypeError):
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            return max(0.0, date.timestamp() - (time.time() if now is None else now))
        except (ValueError, TypeError, OverflowError):
            return None


class SharadarCooldown(RuntimeError):
    def __init__(self, not_before):
        self.not_before = float(not_before)
        super().__init__("SHARADAR_SHARED_COOLDOWN")


class CredentialRequestLimiter:
    """flock spans opener + body read; every process sees the same cooldown.

    Root is private to this OS user. Only a one-way credential digest is used in
    filenames; keys, URLs, headers and financial payloads are never persisted.
    Coordination failure fails closed, rather than bypassing the limiter.
    """

    def __init__(
        self,
        credential,
        *,
        root=DEFAULT_ROOT,
        minimum_interval=0.5,
        clock=time.time,
        sleeper=time.sleep,
    ):
        self.root = Path(root).absolute()
        self.identity = hashlib.sha256(
            (credential or "UNCONFIGURED").encode()
        ).hexdigest()
        self.minimum_interval = max(0.5, float(minimum_interval))
        self.clock, self.sleeper = clock, sleeper
        self.state_path = self.root / (self.identity + ".json")
        self.lock_path = self.root / (self.identity + ".lock")

    def _check_root(self):
        # Reject symlink ancestors as well as final-component links.
        for path in (self.root, *self.root.parents):
            if path.is_symlink():
                raise ValueError("SHARADAR_LIMITER_PATH_UNTRUSTED")
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        stat = self.root.stat()
        if stat.st_uid != os.getuid() or stat.st_mode & 0o077:
            raise ValueError("SHARADAR_LIMITER_ROOT_NOT_PRIVATE")

    def _state(self):
        if self.state_path.is_symlink():
            raise ValueError("SHARADAR_LIMITER_STATE_UNTRUSTED")
        if not self.state_path.exists():
            return {"next_start": 0.0, "not_before": 0.0}
        if self.state_path.stat().st_size > 4096:
            raise ValueError("SHARADAR_LIMITER_STATE_INVALID")
        value = json.loads(self.state_path.read_text())
        if set(value) != {"next_start", "not_before"} or any(
            not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0
            for v in value.values()
        ):
            raise ValueError("SHARADAR_LIMITER_STATE_INVALID")
        return value

    def _save(self, state):
        write_text_atomic(self.state_path, json.dumps(state, allow_nan=False) + "\n")
        descriptor = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @contextmanager
    def request(self, *, wait_budget=30.0):
        self._check_root()
        fd = os.open(self.lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        deadline = self.clock() + max(0.0, wait_budget)
        try:
            while True:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if self.clock() >= deadline:
                        raise SharadarCooldown(self.clock())
                    self.sleeper(min(0.05, max(0.0, deadline - self.clock())))
            state = self._state()
            eligible = max(state.values())
            remaining = max(0.0, eligible - self.clock())
            if remaining > max(0.0, deadline - self.clock()):
                raise SharadarCooldown(eligible)
            if remaining:
                self.sleeper(remaining)
            state["next_start"] = self.clock() + self.minimum_interval
            self._save(state)  # durable before the actual transport attempt
            try:
                yield self
            finally:
                # Conservatively space from completion as well. Receipt fsyncs
                # between a grant and the actual opener must not shorten the
                # next real HTTP start interval on a slow filesystem.
                state = self._state()
                state["next_start"] = max(
                    state["next_start"], self.clock() + self.minimum_interval
                )
                self._save(state)
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def record_429(self, headers):
        """Caller owns request() lock. Persist before releasing in-flight lock."""
        delay = retry_after_seconds(headers, now=self.clock())
        if delay is None:
            delay = 5.0
        state = self._state()
        state["not_before"] = max(state["not_before"], self.clock() + delay)
        self._save(state)
        return state["not_before"]


def utc_timestamp(value):
    return datetime.fromtimestamp(value, timezone.utc).isoformat()
