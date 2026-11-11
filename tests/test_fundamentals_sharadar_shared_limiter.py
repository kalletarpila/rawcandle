"""Native transport coordination, including separate OS processes."""

from datetime import datetime, timezone
from email.utils import format_datetime
import io
import json
import multiprocessing
import os
from pathlib import Path
import time

import pytest

from rawcandle.fundamentals.providers import sharadar
from rawcandle.fundamentals.providers.sharadar_limiter import (
    CredentialRequestLimiter,
    SharadarCooldown,
    retry_after_seconds,
)


class Clock:
    def __init__(self, value=1000):
        self.value = float(value)

    def now(self):
        return self.value

    def sleep(self, seconds):
        self.value += seconds


class Response(io.BytesIO):
    def __init__(self, status=200, headers=None, body=b"[]"):
        self.status, self.headers = status, headers or {
            "Content-Type": "application/json"
        }
        super().__init__(body)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("120", 120),
        ("0", 0),
        ("0.25", 0.25),
        ("-1", None),
        ("broken", None),
        ("", None),
        ("nan", None),
        ("inf", None),
        (None, None),
    ],
)
def test_numeric_malformed_and_missing_retry_after(value, expected):
    assert (
        retry_after_seconds({} if value is None else {"ReTrY-AfTeR": value}, now=1000)
        == expected
    )


@pytest.mark.parametrize("offset,expected", [(120, 120), (0, 0), (-10, 0)])
def test_http_date_retry_after(offset, expected):
    value = format_datetime(
        datetime.fromtimestamp(1000 + offset, timezone.utc), usegmt=True
    )
    assert retry_after_seconds({"Retry-After": value}, now=1000) == expected


@pytest.mark.parametrize(
    "header,delay", [("120", 120), ("0", 0), ("broken", 5), (None, 5)]
)
def test_durable_cooldown_and_nonblocking_wait_budget(tmp_path, header, delay):
    clock = Clock()
    first = CredentialRequestLimiter(
        "same-secret", root=tmp_path / "coord", clock=clock.now, sleeper=clock.sleep
    )
    with first.request():
        eligible = first.record_429({} if header is None else {"Retry-After": header})
    assert eligible == 1000 + delay
    second = CredentialRequestLimiter(
        "same-secret", root=tmp_path / "coord", clock=clock.now, sleeper=clock.sleep
    )
    with pytest.raises(SharadarCooldown):
        with second.request(wait_budget=0):
            pytest.fail("early dispatch")
    # Even Retry-After:0 retains the conservative 0.5-second start spacing.
    clock.value += max(delay, 0.5)
    with second.request(wait_budget=0):
        pass
    assert "same-secret" not in "\n".join(
        p.name + p.read_text() for p in (tmp_path / "coord").iterdir()
    )


def test_retries_each_have_one_native_attempt_and_close_response(tmp_path):
    clock = Clock()
    limiter = CredentialRequestLimiter(
        "secret", root=tmp_path / "coord", clock=clock.now, sleeper=clock.sleep
    )
    responses = [Response(503), Response()]
    observed = []
    events = []
    used = []

    def opener(request, timeout):
        observed.append(clock.now())
        value = responses.pop(0)
        used.append(value)
        return value

    client = sharadar.SharadarClient(
        api_key="secret",
        opener=opener,
        credential_limiter=limiter,
        retry_sleep_seconds=0.1,
        sleeper=clock.sleep,
        wall_clock=clock.now,
    )
    with client.observe_attempts(events.append):
        result = client.fundamentals(ticker="AAA", dimension="ARQ")
    assert result.ok and result.request_count == 2
    assert observed == [1000, 1000.5]
    assert [e["event"] for e in events] == [
        "STARTED",
        "FINISHED",
        "STARTED",
        "FINISHED",
    ]
    assert len({e["attempt_id"] for e in events}) == 2
    assert all(response.closed for response in used)


def _concurrent_native_worker(root, events, gate):
    limiter = CredentialRequestLimiter("shared-credential", root=Path(root))
    active = Path(events).with_suffix(".active")

    class SlowResponse(Response):
        def read(self, *args):
            time.sleep(0.08)
            return super().read(*args)

        def close(self):
            if not self.closed:
                with open(events, "a") as stream:
                    stream.write(json.dumps(["END", os.getpid(), time.time()]) + "\n")
                active.unlink()
            super().close()

    def opener(request, timeout):
        try:
            fd = os.open(active, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        except FileExistsError:
            with open(events, "a") as stream:
                stream.write(json.dumps(["OVERLAP", os.getpid(), time.time()]) + "\n")
            raise
        with open(events, "a") as stream:
            stream.write(json.dumps(["START", os.getpid(), time.time()]) + "\n")
        return SlowResponse()

    client = sharadar.SharadarClient(
        api_key="shared-credential", opener=opener, credential_limiter=limiter
    )
    gate.wait(5)
    assert client.schema().ok
    assert client.fundamentals(ticker="AAA", dimension="ARQ").ok


def test_cross_process_starts_and_full_response_in_flight_lock(tmp_path):
    context = multiprocessing.get_context("fork")
    gate = context.Event()
    processes = [
        context.Process(
            target=_concurrent_native_worker,
            args=(str(tmp_path / "coord"), str(tmp_path / "events"), gate),
        )
        for _ in range(3)
    ]
    for process in processes:
        process.start()
    gate.set()
    for process in processes:
        process.join(15)
        if process.is_alive():
            process.terminate()
            process.join()
            pytest.fail("coordination deadlock")
        assert process.exitcode == 0
    events = [
        json.loads(line) for line in (tmp_path / "events").read_text().splitlines()
    ]
    assert [event[0] for event in events] == ["START", "END"] * 6
    starts = [e[2] for e in events if e[0] == "START"]
    assert all(b - a >= 0.49 for a, b in zip(starts, starts[1:]))


def _cooldown_worker(root, queue, create):
    limiter = CredentialRequestLimiter("credential", root=Path(root))
    calls = []
    client = sharadar.SharadarClient(
        api_key="credential",
        credential_limiter=limiter,
        wait_budget_seconds=0,
        opener=lambda request, timeout: (
            calls.append(1) or Response(429, {"Retry-After": "120"})
        ),
    )
    result = client.schema() if create else client.fundamentals(ticker="AAA")
    queue.put((result.status, len(calls), result.not_before))


def test_cross_process_schema_cooldown_blocks_other_client_history(tmp_path):
    context = multiprocessing.get_context("fork")
    queue = context.Queue()
    for create in (True, False):
        process = context.Process(
            target=_cooldown_worker, args=(str(tmp_path / "coord"), queue, create)
        )
        process.start()
        process.join(5)
        assert process.exitcode == 0
    first, second = queue.get(timeout=2), queue.get(timeout=2)
    assert first[0] == second[0] == "RATE_LIMITED"
    assert first[1] == 1 and second[1] == 0 and first[2] == second[2]


def test_real_default_transport_cannot_bypass_credential_limiter(tmp_path, monkeypatch):
    actual = CredentialRequestLimiter
    created = []

    def limiter(credential):
        value = actual(credential, root=tmp_path / "coord")
        created.append(value)
        return value

    monkeypatch.setattr(sharadar, "CredentialRequestLimiter", limiter)
    calls = []
    monkeypatch.setattr(
        sharadar.SharadarClient,
        "_default_open",
        staticmethod(
            lambda request, timeout: (
                calls.append(request.full_url) or Response(429, {"Retry-After": "120"})
            )
        ),
    )
    first = sharadar.SharadarClient(api_key="credential")
    second = sharadar.SharadarClient(api_key="credential", wait_budget_seconds=0)
    assert first.schema().status == "RATE_LIMITED"
    assert (
        second.fundamentals(fields=["ticker", "dimension", "lastupdated"]).status
        == "RATE_LIMITED"
    )
    assert (
        len(calls) == 1
        and len(created) == 2
        and created[0].identity == created[1].identity
    )


@pytest.mark.parametrize("kind", ["state_corrupt", "symlink", "public_root"])
def test_limiter_fails_closed_for_untrusted_state(tmp_path, kind):
    root = tmp_path / "coord"
    limiter = CredentialRequestLimiter("credential", root=root)
    with limiter.request():
        pass
    if kind == "state_corrupt":
        limiter.state_path.write_text("{broken")
    elif kind == "symlink":
        data = limiter.state_path.read_bytes()
        limiter.state_path.unlink()
        outside = tmp_path / "outside"
        outside.write_bytes(data)
        limiter.state_path.symlink_to(outside)
    else:
        root.chmod(0o755)
    with pytest.raises(ValueError):
        with limiter.request(wait_budget=0):
            pytest.fail("unsafe coordination accepted")
