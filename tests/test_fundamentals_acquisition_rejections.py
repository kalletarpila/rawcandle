"""Offline native-client boundary diagnostics; no historical live-body fixture."""

from dataclasses import replace
import csv
import hashlib
import io
import json
import socket
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from rawcandle.fundamentals import source_capture as capture
from rawcandle.fundamentals.admin import acquisition_snapshot as fetch
from rawcandle.fundamentals.providers.sharadar import SharadarClient
from tests.test_fundamentals_acquisition_snapshot import (
    NOW, OP, SECRET, Response, Transport, checkpoint, old, row, start,
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Outgoing network access is forbidden")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


def rejection(tmp_path):
    directory = tmp_path / "runs" / OP
    result = json.loads((directory / "result.json").read_text())
    path = directory / result["rejected_response_diagnostic"]
    evidence = json.loads(path.read_text())
    assert path.stat().st_size <= fetch.MAX_CONTROL
    assert evidence["accepted_snapshot_slot"] is False
    assert evidence["publication_authorized"] is False
    assert evidence["raw_body_retained"] is False
    assert not (directory / "fetch/checkpoints/000000.json").exists()
    assert not (directory / "fetch/seal.json").exists()
    with pytest.raises((fetch.SnapshotError, FileNotFoundError)):
        fetch.open_snapshot(OP, root=tmp_path / "runs")
    with pytest.raises(fetch.SnapshotError, match="ARTIFACT_TYPE_INVALID"):
        fetch._Run(tmp_path / "runs", OP).ref(result["rejected_response_diagnostic"], "BODY")
    return result, evidence


@pytest.mark.parametrize("representation", ["list", "data", "rows", "results", "counted_data", "utf8", "csv"])
def test_existing_supported_representations_still_seal(old, tmp_path, representation):
    def change(identity, rows):
        if representation in {"data", "rows", "results"}:
            return {representation: rows}
        if representation == "counted_data":
            return {"count": len(rows), "data": rows}
        if representation == "utf8":
            rows[0]["fixture_note"] = "tutkimus – käypä arvo"
            return Response(json.dumps(rows, ensure_ascii=False).encode("utf-8"))
        if representation == "csv":
            stream = io.StringIO()
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
            return Response(stream.getvalue().encode(), headers={"Content-Type": "text/csv"})
        return rows

    result = start(old, tmp_path, Transport(change=change))
    assert result["status"] == "FETCH_SEALED"
    snap = fetch.open_snapshot(OP, root=tmp_path / "runs")
    snap.validate_preflight(old_authority=fetch.pin_old_authority(old), now=NOW)
    assert len(list(snap.iter_slots())) == 4
    assert not (tmp_path / "runs" / OP / "fetch/rejections").exists()


@pytest.mark.parametrize(
    "defect,predicate",
    [
        ("wrong_ticker", "SOURCE_IDENTITY_MISMATCH"),
        ("wrong_dimension", "PAYLOAD_CAPTURE_EQUAL"),
        ("mixed_dimensions", "PAYLOAD_CAPTURE_EQUAL"),
        ("unfiltered_tickers", "SOURCE_IDENTITY_MISMATCH"),
        ("extra_metadata", "PAYLOAD_SHAPE_VALID"),
        ("pagination", "PAYLOAD_SHAPE_VALID"),
        ("count_mismatch", "PAYLOAD_SHAPE_VALID"),
        ("count_string", "PAYLOAD_SHAPE_VALID"),
        ("count_boolean", "PAYLOAD_SHAPE_VALID"),
        ("count_float", "PAYLOAD_SHAPE_VALID"),
        ("counted_pagination", "PAYLOAD_SHAPE_VALID"),
        ("counted_wrong_container", "PAYLOAD_SHAPE_VALID"),
        ("nonobject", "PAYLOAD_SHAPE_VALID"),
        ("empty", "EMPTY_OR_LIMIT_COVERAGE_UNPROVEN"),
        ("empty_counted", "EMPTY_OR_LIMIT_COVERAGE_UNPROVEN"),
        ("malformed_json", "CLIENT_INVALID_RESPONSE"),
        ("out_of_window", "SOURCE_WINDOW_MISMATCH"),
    ],
)
def test_invalid_history_has_exact_diagnostics_and_no_authority(old, tmp_path, defect, predicate):
    def change(identity, rows):
        if defect == "wrong_ticker":
            rows[0]["ticker"] = "FOREIGN"
        elif defect == "wrong_dimension":
            rows[0]["dimension"] = "MRQ"
        elif defect == "mixed_dimensions":
            return rows + [row(dimension="MRQ")]
        elif defect == "unfiltered_tickers":
            return rows + [row(ticker="FOREIGN")]
        elif defect == "extra_metadata":
            return {"data": rows, "meta": {"count": 1}}
        elif defect == "pagination":
            return {"data": rows, "next": "uncaptured-page"}
        elif defect == "count_mismatch":
            return {"data": rows, "count": len(rows) + 1}
        elif defect == "count_string":
            return {"data": rows, "count": str(len(rows))}
        elif defect == "count_boolean":
            return {"data": rows, "count": True}
        elif defect == "count_float":
            return {"data": rows, "count": float(len(rows))}
        elif defect == "counted_pagination":
            return {"data": rows, "count": len(rows), "next": "uncaptured-page"}
        elif defect == "counted_wrong_container":
            return {"rows": rows, "count": len(rows)}
        elif defect == "nonobject":
            return rows + [None]
        elif defect == "empty":
            return []
        elif defect == "empty_counted":
            return {"count": 0, "data": []}
        elif defect == "malformed_json":
            return Response(b'{"data":[')
        elif defect == "out_of_window":
            rows[0]["date"] = "2010-01-01"
        return rows

    transport = Transport(change=change)
    if defect == "malformed_json":
        assert start(old, tmp_path, transport)["status"] == "FETCH_BLOCKED"
    else:
        with pytest.raises(fetch.SnapshotError, match=predicate):
            start(old, tmp_path, transport)
    result, evidence = rejection(tmp_path)
    assert evidence["failed_predicate"] == predicate
    assert evidence["ticker"] == "AAA" and evidence["dimension"] == "ARQ"
    assert evidence["slot"] == 0 and evidence["http_status"] == 200
    assert evidence["transport_ledger"]["response_bytes"] > 0
    assert len(evidence["transport_ledger"]["response_sha256"]) == 64
    assert result["complete_verified_slots"] == 0
    if defect != "malformed_json":
        assert predicate in result["reason"]
        assert evidence["response_sha256"] == evidence["transport_ledger"]["response_sha256"]
    if defect == "mixed_dimensions":
        assert evidence["payload_rows"]["row_count"] == 2
        assert evidence["captured_rows"]["row_count"] == 1
        assert evidence["payload_rows"]["dimensions"] == ["ARQ", "MRQ"]
    assert len(transport.calls) == 2  # schema + the rejected singleton
    assert SECRET not in "\n".join(p.read_text() for p in (tmp_path / "runs").rglob("*") if p.is_file())


@pytest.mark.parametrize(
    "defect,predicate",
    [
        ("missing_body", "RESPONSE_BODY_PRESENT"),
        ("parameters", "REQUEST_PARAMETERS_MATCH"),
        ("capture_parameters", "CAPTURE_RESPONSE_BINDING_MISMATCH"),
        ("body_bytes", "CAPTURE_RESPONSE_BINDING_MISMATCH"),
        ("capture_row", "PAYLOAD_CAPTURE_EQUAL"),
    ],
)
def test_native_adapter_mismatches_remain_rejected(old, tmp_path, defect, predicate):
    transport = Transport()

    class Adapter(SharadarClient):
        def fundamentals(self, **kwargs):
            response = super().fundamentals(**kwargs)
            if defect == "missing_body":
                return replace(response, response_body=None)
            if defect == "parameters":
                return replace(response, parameters={**response.parameters, "limit": "1"})
            if defect == "body_bytes":
                return replace(response, response_body=response.response_body + b" ")
            if defect == "capture_row":
                return replace(response, records=[])
            raw = [capture.raw_payload(x) for x in response.records]
            records = capture._http_records(
                raw, endpoint=fetch.ENDPOINT,
                parameters={**response.parameters, "limit": "1"},
                acquired_at=response.acquired_at_utc,
                base_url="https://api.sharadar.com/v1.0",
                response_sha256=hashlib.sha256(response.response_body).hexdigest(),
            )
            return replace(response, records=records)

    client = Adapter(api_key=SECRET, opener=transport, wall_clock=lambda: NOW.timestamp())
    with pytest.raises(fetch.SnapshotError, match=predicate):
        fetch.start_fetch(["AAA"], project_root=old, source_day=NOW.date().isoformat(),
                          root=tmp_path / "runs", operation_id=OP, client=client, now=lambda: NOW)
    _, evidence = rejection(tmp_path)
    assert evidence["failed_predicate"] == predicate
    assert evidence["expected_parameters"]["limit"] == "10000"
    if defect == "parameters":
        assert evidence["observed_parameters"]["limit"] == "1"
    if defect == "body_bytes":
        assert evidence["response_sha256"] != evidence["captured_response_sha256s"][0]


def test_diagnostics_are_bounded_and_redact_credentials(old, tmp_path):
    transport = Transport()

    class Adapter(SharadarClient):
        def fundamentals(self, **kwargs):
            result = super().fundamentals(**kwargs)
            return replace(result, parameters={**result.parameters, "ticker": SECRET,
                                              "api_key": SECRET, "unrelated": "x" * 100000})

    client = Adapter(api_key=SECRET, opener=transport, wall_clock=lambda: NOW.timestamp())
    with pytest.raises(fetch.SnapshotError, match="REQUEST_PARAMETERS_MATCH"):
        fetch.start_fetch(["AAA"], project_root=old, source_day=NOW.date().isoformat(),
                          root=tmp_path / "runs", operation_id=OP, client=client, now=lambda: NOW)
    _, evidence = rejection(tmp_path)
    assert evidence["observed_parameters"]["ticker"] == "[REDACTED]"
    assert "unrelated" not in evidence["observed_parameters"]
    assert SECRET not in json.dumps(evidence)


def test_rejected_resume_keeps_committed_checkpoint_and_diagnostics_separate(old, tmp_path):
    def change(identity, rows):
        return {"data": rows, "next": "uncaptured"} if identity == ("AAA", "MRQ") else rows

    with pytest.raises(fetch.SnapshotError, match="PAYLOAD_SHAPE_VALID"):
        start(old, tmp_path, Transport(change=change))
    first_path, _ = checkpoint(tmp_path)
    original = first_path.read_bytes()
    directory = tmp_path / "runs" / OP
    rejected = {str(p): p.read_bytes() for p in (directory / "fetch/rejections").iterdir()}
    transport = Transport()
    result = fetch.resume_fetch(OP, project_root=old, root=tmp_path / "runs",
                                client=transport.client(), now=lambda: NOW)
    assert result["status"] == "FETCH_SEALED"
    assert first_path.read_bytes() == original
    assert transport.calls == [("AAA", "MRQ"), ("BBB", "ARQ"), ("BBB", "MRQ")]
    assert all(Path(name).read_bytes() == body for name, body in rejected.items())
    snap = fetch.open_snapshot(OP, root=tmp_path / "runs")
    assert len(list(snap.iter_slots())) == 4
    assert not snap.validate_preflight(old_authority=fetch.pin_old_authority(old), now=NOW)["publication_authorized"]
    assert "rejections" not in (directory / "fetch/snapshot_manifest.json").read_text()
    assert "rejections" not in (directory / "fetch/checkpoint_index.jsonl").read_text()


def test_failed_update_can_resume_before_code_binding_but_stale_validation_cannot_build(tmp_path, monkeypatch):
    from rawcandle.fundamentals.admin import refresh_update as core
    from tests.test_fundamentals_snapshot_integration import setup

    workflow, _, _, _ = setup(tmp_path, monkeypatch)
    opener = workflow.client._opener

    def reject_history(request, timeout):
        response = opener(request, timeout)
        if "ticker" in parse_qs(urlsplit(request.full_url).query):
            return Response({"data": json.loads(response.read()), "next": "uncaptured"})
        return response

    monkeypatch.setattr(workflow.client, "_opener", reject_history)
    failed = workflow.start(publication_intent=False, ownership_intent=False, stop_after="fetch")
    assert failed["outcome"] == "FAILED"
    assert "PAYLOAD_SHAPE_VALID" in failed["message"]
    run_id = failed["run_id"]
    directory = workflow.env.runs / run_id
    request_bytes = (directory / "update_request.json").read_bytes()
    assert not failed.get("validation_id")
    assert "code" not in json.loads(request_bytes)
    monkeypatch.setattr(workflow.client, "_opener", opener)
    monkeypatch.setattr(core, "_code_binding", lambda: "fixed-code-before-validation")
    resumed = workflow.advance(run_id, stop_after="fetch")
    assert resumed["outcome"] == "FETCH_SEALED", resumed
    assert resumed["fetch_operation_id"] == failed["fetch_operation_id"]
    assert (directory / "update_request.json").read_bytes() == request_bytes
    validated = workflow.advance(run_id, stop_after="validate")
    assert validated["outcome"] == "VALIDATED", validated
    local = workflow.env.runs / validated["validation_id"]
    receipt = json.loads((local / "validation_receipt.json").read_text())
    assert receipt["inputs"]["code"] == "fixed-code-before-validation"
    monkeypatch.setattr(core, "_code_binding", lambda: "another-code-after-validation")
    stale = workflow.advance(run_id, stop_after="build")
    assert stale["outcome"] == "FAILED"
    assert stale["message"] == "PHASE2_LOCAL_AUTHORITY_DRIFT"
    assert not (local / "candidate").exists()
    assert not stale["production_completed"]
