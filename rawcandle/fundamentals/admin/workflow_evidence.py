"""Bounded presentation metadata and verified references to native run evidence.

These summaries never substitute for the native Preview/Test publication receipt.
Financial stages still receive their original IDs, paths and semantic fingerprints.
"""

from __future__ import annotations

import json
import re
from itertools import islice
from collections.abc import Mapping
from pathlib import Path

from .artifacts import sha256_file

VERSION = "FUNDAMENTALS_WORKFLOW_REFERENCES_V1"
SUMMARY = "workflow_child_summary.json"
MAX_METADATA = 512 * 1024
MAX_ITEMS = 24
MAX_TEXT = 2048
MODES = {
    "PREVIEW",
    "COPY_ONLY_APPLY",
    "PRODUCTION_APPLY",
    "PRODUCTION_NO_CHANGE_APPLY",
    "TRANSACTION_REHEARSAL",
}
OPERATIONS = {"ADD_TICKERS", "REMOVE_TICKERS", "REFRESH_FUNDAMENTALS"}
PREVIEWS = {
    "ADD_TICKERS": "phase13d_preview_payload.json",
    "REMOVE_TICKERS": "remove_tickers_preview.json",
    "REFRESH_FUNDAMENTALS": "refresh_preview.json",
}
SCALARS = {
    "run_id",
    "artifact_dir",
    "operation_type",
    "operation_label",
    "mode",
    "outcome",
    "status",
    "workflow_status",
    "trigger_source",
    "current_stage",
    "started_at_utc",
    "completed_at_utc",
    "final_completed_stage",
    "production_completed",
    "ownership_production_completed",
    "requested_input_count",
    "interrupted",
    "preview_fingerprint",
    "refresh_set_fingerprint",
    "preview_payload_path",
    "payload_path",
    "phase13d_preview_payload_path",
    "test_run_id",
    "message",
    "error",
    "failed_stage",
    "stop_reason",
    "recommended_next_action",
    "user_message",
    "user_failure_reason",
    "outcome_message",
    "write_boundary_crossed",
    "production_writes",
    "manual_test_retry_available",
    "manual_production_available",
    "preview_test_rerun_required",
    "manual_production_retry_available",
    "contract_version",
    "evidence_format",
    "completed_with_review_holds",
}
SMALL = {
    "summary_counts",
    "applyability",
    "retry_authorization",
    "old_refresh_state",
    "refresh_state",
    "terminal_cleanup",
    "rollback",
    "publication_recovery",
    "errors",
    "warnings",
    "source_summary",
    "publication_outcome",
    "git_state",
    "terminal_summary",
    "stages",
    "appendix_source",
    "authoritative_item_evidence",
    "ownership_auto",
    "requested_inputs",
    "request",
    "requested_change",
}
DECISION_KEYS = {
    "schema_version",
    "authoritative_stage",
    "safe_effective_changes",
    "held_item_count",
    "global_blocker_count",
    "test_gate",
    "production_gate",
    "decision_code",
    "decision_text",
    "recommended_action_code",
    "recommended_action_text",
    "local_hold_blocked_safe_changes",
    "safe_peers_published",
    "held_incoming_tickers_published",
    "held_tickers_unchanged",
}


def bounded(value, depth=0, _budget=None):
    budget = [16384] if _budget is None else _budget
    budget[0] -= 1
    if depth > 7 or budget[0] <= 0:
        return None
    if isinstance(value, str):
        result = value[: min(MAX_TEXT, budget[0])]
        budget[0] -= len(result)
        return result
    if isinstance(value, Mapping):
        return {
            str(k)[:128]: bounded(v, depth + 1, budget)
            for k, v in islice(value.items(), 48)
            if budget[0] > 0
        }
    if isinstance(value, (list, tuple)):
        return [
            bounded(v, depth + 1, budget) for v in value[:MAX_ITEMS] if budget[0] > 0
        ]
    return (
        value
        if value is None or isinstance(value, (bool, int, float))
        else str(value)[:MAX_TEXT]
    )


def item_summary(value):
    return bounded(
        {
            k: value[k]
            for k in ("ticker", "review_type", "scope", "reason_codes")
            if k in value
        },
        _budget=[1024],
    )


def compact_decision(value):
    if not isinstance(value, Mapping):
        return None
    result = {k: bounded(v) for k, v in value.items() if k in DECISION_KEYS}
    for key in ("held_items", "global_blockers"):
        result[key] = [
            item_summary(x)
            for x in (value.get(key) or [])[:MAX_ITEMS]
            if isinstance(x, Mapping)
        ]
    result["details_in_child_artifacts"] = True
    return result


def advance_refresh_decision(previous, **kwargs):
    from .refresh_operational_decision import advance_refresh_decision as advance

    result = advance(previous, **kwargs)
    if previous.get("details_in_child_artifacts"):
        result["held_item_count"] = previous["held_item_count"]
        result["global_blocker_count"] = previous["global_blocker_count"]
        # A sample must never be presented as the complete held population.
        if result["held_item_count"]:
            result["decision_text"] = (
                result["decision_text"]
                .split(
                    " "
                    + ", ".join(
                        str(x.get("ticker") or "Unknown ticker")
                        for x in previous["held_items"]
                    ),
                    1,
                )[0]
                .rstrip()
            )
            result[
                "decision_text"
            ] += f" {result['held_item_count']} tickers remain held; see the referenced child evidence."
    return compact_decision(result)


def problem_sample(item):
    # Presentation clipping must never remove fields used to classify a STOP.
    result = bounded(
        {
            k: v
            for k, v in item.items()
            if k
            not in {
                "ticker",
                "classification",
                "reason",
                "action",
                "review_required",
                "reporting_integrity_error",
                "review_scope",
            }
        },
        _budget=[1024],
    )
    for key in ("ticker", "classification", "reason", "action", "review_scope"):
        value = item.get(key)
        result[key] = value[:256] if isinstance(value, str) else value
    for key in ("review_required", "reporting_integrity_error"):
        result[key] = item.get(key)
    return result


def child_summary(payload):
    """Run once while the native child already owns its complete result in memory."""
    from . import full_workflow as fw
    from .operation_report import build_operation_summary
    from .ticker_reporting import analysis_reporting_counts

    result = {k: bounded(v) for k, v in payload.items() if k in SCALARS or k in SMALL}
    decision = compact_decision(payload.get("operational_decision"))
    if decision:
        result["operational_decision"] = decision
    preview = payload.get("refresh_preview") or {}
    result["refresh_preview"] = {
        "future_test_authorized": preview.get("future_test_authorized"),
        "publication_date_state": bounded(preview.get("publication_date_state") or {}),
        "discovery": {
            k: bounded(v)
            for k, v in (preview.get("discovery") or {}).items()
            if isinstance(v, (str, int, float, bool)) or v is None
        },
    }
    for key, fields in (
        ("provider_candidate", ("ticker_count",)),
        ("canonical_candidate", ("impact", "publication_date_bootstrap")),
        ("analysis_candidate", ("status",)),
        ("postflight", ("status",)),
    ):
        item = payload.get(key) or {}
        result[key] = {
            k: bounded(item[k])
            for k in fields
            if isinstance(item, Mapping) and k in item
        }
    if payload.get("postflight") and not result["postflight"].get("status"):
        result["postflight"]["status"] = "PASSED"
    partition = payload.get("review_partition") or {}
    if partition:
        result["review_partition"] = {
            k: bounded(v)
            for k, v in partition.items()
            if isinstance(v, (str, int, float, bool)) or v is None
        }
        result["review_partition"].update(
            safe_tickers=bounded(partition.get("safe_tickers") or []),
            safe_count=len(partition.get("safe_tickers") or []),
            held_count=len(partition.get("held") or []),
            global_count=len(partition.get("global_blockers") or []),
            held=[
                {
                    k: bounded(x[k])
                    for k in ("ticker", "review_type", "scope", "reason_codes")
                    if k in x
                }
                for x in (partition.get("held") or [])[:MAX_ITEMS]
            ],
            global_blockers=[
                {
                    k: bounded(x[k])
                    for k in ("ticker", "review_type", "scope", "reason_codes")
                    if k in x
                }
                for x in (partition.get("global_blockers") or [])[:MAX_ITEMS]
            ],
            details_in_child_artifacts=True,
        )
    problems = fw._problem_items(payload)
    result["_workflow_problem_items"] = [
        problem_sample(x) for x in problems[:MAX_ITEMS]
    ]
    result["_workflow_problem_counts"] = {
        "total": len(problems),
        "review": sum(bool(x.get("review_required")) for x in problems),
        "integrity": sum(bool(x.get("reporting_integrity_error")) for x in problems),
    }
    result["_workflow_batch_outcomes"] = {
        str(p): fw._batch_outcome(payload, production_published=p)
        for p in (False, True)
    }
    result["_workflow_has_structured_items"] = fw._has_structured_items(payload)
    result["_workflow_reporting_integrity"] = analysis_reporting_counts(
        list(payload.get("ticker_reporting") or [])
    )
    result["_workflow_ui_rows"] = bounded(build_operation_summary(payload))
    if len(json.dumps(result).encode()) > MAX_METADATA // 2:
        for key in SMALL:
            if key in result:
                result[key] = bounded(result[key], _budget=[2048])
    if len(json.dumps(result).encode()) > MAX_METADATA:
        raise ValueError("CHILD_SUMMARY_BUDGET_EXCEEDED")
    return result


def trusted_path(root, run_id, filename):
    root = Path(root).resolve()
    if not isinstance(run_id, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id
    ):
        raise ValueError("CHILD_RUN_ID_INVALID")
    if (
        not isinstance(filename, str)
        or Path(filename).name != filename
        or filename in (".", "..")
    ):
        raise ValueError("CHILD_ARTIFACT_TYPE_INVALID")
    directory = root / run_id
    path = directory / filename
    if (
        directory.is_symlink()
        or path.is_symlink()
        or path.resolve().parent != directory
        or not path.is_file()
    ):
        raise ValueError("CHILD_ARTIFACT_MISSING_OR_UNTRUSTED:" + filename)
    return path


def reference(root, run_id, kind, *, operation=None):
    names = {
        "RESULT": "result.json",
        "SUMMARY": SUMMARY,
        "REPORT": "operation_report.md",
        "NOOP_SCOPE": "workflow_noop_scope.json",
        "PREVIEW": PREVIEWS.get(operation),
    }
    filename = names.get(kind)
    if not filename:
        raise ValueError("CHILD_ARTIFACT_TYPE_INVALID")
    path = trusted_path(root, run_id, filename)
    return {
        "format": VERSION,
        "run_id": run_id,
        "kind": kind,
        "operation_type": operation,
        "relative_path": str(Path(run_id) / filename),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def verify_reference(root, ref, *, kind=None, run_id=None):
    if (
        ref.get("format") != VERSION
        or (kind and ref.get("kind") != kind)
        or (run_id and ref.get("run_id") != run_id)
    ):
        raise ValueError("CHILD_REFERENCE_IDENTITY_MISMATCH")
    names = {
        "RESULT": "result.json",
        "SUMMARY": SUMMARY,
        "REPORT": "operation_report.md",
        "NOOP_SCOPE": "workflow_noop_scope.json",
        "PREVIEW": PREVIEWS.get(ref.get("operation_type")),
    }
    filename = names.get(ref.get("kind"))
    if not filename or ref.get("relative_path") != str(Path(ref["run_id"]) / filename):
        raise ValueError("CHILD_REFERENCE_PATH_OR_TYPE_MISMATCH")
    path = trusted_path(root, ref["run_id"], filename)
    if path.stat().st_size != ref["size_bytes"] or sha256_file(path) != ref["sha256"]:
        raise ValueError("CHILD_ARTIFACT_INTEGRITY_MISMATCH")
    return path


def read_summary(path, *, verify=False):
    """UI uses a small presentation receipt; authorization additionally hashes RESULT."""
    path = Path(path)
    root = path.parent.parent
    run_id = path.parent.name
    summary_path = trusted_path(root, run_id, SUMMARY)
    if summary_path.stat().st_size > MAX_METADATA:
        raise ValueError("CHILD_SUMMARY_TOO_LARGE")
    receipt = json.loads(summary_path.read_text())
    if receipt.get("format") != VERSION or receipt.get("run_id") != run_id:
        raise ValueError("CHILD_SUMMARY_IDENTITY_MISMATCH")
    ref = receipt["result_reference"]
    if verify:
        verify_reference(root, ref, kind="RESULT", run_id=run_id)
    else:
        expected = trusted_path(root, run_id, "result.json")
        if (
            ref.get("relative_path") != str(Path(run_id) / "result.json")
            or ref.get("kind") != "RESULT"
            or ref.get("run_id") != run_id
            or expected.stat().st_size != ref["size_bytes"]
        ):
            raise ValueError("CHILD_SUMMARY_REFERENCE_MISMATCH")
    value = receipt["summary"]
    if value.get("run_id") != run_id:
        raise ValueError("CHILD_SUMMARY_RESULT_IDENTITY_MISMATCH")
    manifest = path.parent / "artifact_manifest.json"
    if verify and not manifest.is_file():
        raise ValueError("CHILD_COMPLETION_MANIFEST_MISSING")
    if manifest.exists() or manifest.is_symlink():
        manifest = trusted_path(root, run_id, "artifact_manifest.json")
        if manifest.stat().st_size > MAX_METADATA:
            raise ValueError("CHILD_MANIFEST_TOO_LARGE")
        data = json.loads(manifest.read_text())
        entries = {x["name"]: x for x in data.get("artifacts", [])}
        status = trusted_path(root, run_id, "status.json")
        if (
            status.stat().st_size > MAX_METADATA
            or json.loads(status.read_text()).get("run_id") != run_id
        ):
            raise ValueError("CHILD_STATUS_IDENTITY_MISMATCH")
        for filename, expected, size in (
            (SUMMARY, sha256_file(summary_path), summary_path.stat().st_size),
            ("result.json", ref["sha256"], ref["size_bytes"]),
            ("status.json", sha256_file(status), status.stat().st_size),
        ):
            entry = entries.get(filename, {})
            if (
                data.get("run_id") != run_id
                or entry.get("sha256") != expected
                or entry.get("size_bytes") != size
            ):
                raise ValueError("CHILD_MANIFEST_INTEGRITY_MISMATCH")
    elif not verify:
        value = dict(value, outcome="RUNNING")
    return value, ref


def declares_summary(path):
    manifest = Path(path).parent / "artifact_manifest.json"
    if not (manifest.exists() or manifest.is_symlink()):
        return False
    manifest = trusted_path(
        Path(path).parent.parent, Path(path).parent.name, "artifact_manifest.json"
    )
    if manifest.stat().st_size > MAX_METADATA:
        raise ValueError("CHILD_MANIFEST_TOO_LARGE")
    data = json.loads(manifest.read_text())
    if data.get("run_id") != Path(path).parent.name:
        raise ValueError("CHILD_MANIFEST_IDENTITY_MISMATCH")
    return any(x.get("name") == SUMMARY for x in data.get("artifacts", []))


def load_child(root, child, operation, stage):
    run_id = getattr(child, "run_id", None)
    path = trusted_path(root, run_id, "result.json")
    if (path.parent / SUMMARY).exists():
        payload, ref = read_summary(path, verify=True)
    else:
        if declares_summary(path):
            raise ValueError("CHILD_COMPLETION_SUMMARY_MISSING")
        # Compatibility for small legacy adapters, never decode a giant old result.
        if path.stat().st_size > MAX_METADATA:
            raise ValueError("CHILD_COMPLETED_SUMMARY_REQUIRED")
        raw = json.loads(path.read_text())
        payload = child_summary(raw)
        ref = reference(root, run_id, "RESULT", operation=operation)
    modes = {
        "Preview": {"PREVIEW"},
        "Test on copies": {"COPY_ONLY_APPLY"},
        "Production update": {
            "PRODUCTION_APPLY",
            "PRODUCTION_NO_CHANGE_APPLY",
            "TRANSACTION_REHEARSAL",
        },
    }
    if (
        payload.get("run_id") != run_id
        or payload.get("operation_type") != operation
        or payload.get("mode") not in modes[stage]
        or payload.get("outcome") != getattr(child, "outcome", None)
    ):
        raise ValueError("CHILD_COMPLETION_IDENTITY_MISMATCH")
    if payload.get("outcome") in {"COMPLETED", "NO_CHANGE"}:
        status = path.parent / "status.json"
        if status.exists() or status.is_symlink():
            status = trusted_path(root, run_id, "status.json")
            if (
                status.stat().st_size > MAX_METADATA
                or json.loads(status.read_text()).get("stage") != "COMPLETED"
            ):
                raise ValueError("CHILD_COMPLETION_STATUS_INCOMPLETE")
    ref = {
        **ref,
        "semantic_fingerprint": getattr(child, "preview_fingerprint", None),
        "completion_outcome": payload.get("outcome"),
    }
    payload["evidence_reference"] = ref
    if (path.parent / SUMMARY).exists():
        payload["summary_reference"] = reference(
            root, run_id, "SUMMARY", operation=operation
        )
    return payload


def read_metadata(path):
    """Bounded normal/history view; legacy native pretty JSON is projected in place.

    Old files stay untouched. Only selected metadata lines are assembled; long
    evidence lines and nested financial dictionaries are skipped in fixed chunks.
    Explicit native report downloads remain the legacy details interface.
    """
    path = Path(path)
    if path.is_symlink():
        raise ValueError("SYMLINK_RUN_EVIDENCE")
    if path.name == "result.json" and (path.parent / SUMMARY).exists():
        return read_summary(path)[0]
    if path.name == "result.json" and declares_summary(path):
        raise ValueError("CHILD_COMPLETION_SUMMARY_MISSING")
    if path.stat().st_size <= MAX_METADATA:
        return json.loads(path.read_text())
    keep = SCALARS | SMALL | {"operational_decision", "refresh_preview"}
    result = {}
    stack = []
    skip_indent = None
    new_line = True
    retained = 0
    with path.open() as f:
        while True:
            fragment = f.readline(65536)
            if not fragment:
                break
            starts = new_line
            new_line = fragment.endswith("\n")
            if not starts:
                continue
            if not new_line:
                if skip_indent is None and stack and isinstance(stack[-1][1], dict):
                    match = re.match(
                        r'\s*"(decision_text|headline|reason|message)":', fragment
                    )
                    if match:
                        stack[-1][1][
                            match.group(1)
                        ] = "Large recorded text; see the native report."
                continue
            line = fragment.rstrip()
            indent = len(line) - len(line.lstrip())
            if skip_indent is not None:
                if indent > skip_indent:
                    continue
                skip_indent = None
            while stack and indent <= stack[-1][0]:
                stack.pop()
            parent = stack[-1][1] if stack else result
            if line.strip() == "{" and isinstance(parent, list):
                if len(parent) < MAX_ITEMS:
                    item = {}
                    parent.append(item)
                    stack.append((indent, item))
                else:
                    skip_indent = indent
                continue
            if isinstance(parent, list) and line.strip() not in (
                "[",
                "]",
                "],",
                "}",
                "},",
            ):
                if len(parent) < MAX_ITEMS and retained < MAX_METADATA:
                    try:
                        value = json.loads(line.strip().rstrip(","))
                    except ValueError:
                        pass
                    else:
                        parent.append(bounded(value))
                        retained += min(len(line), MAX_TEXT)
                continue
            match = re.match(r'\s*"([^"\\]+)": (.*)', line)
            if not match:
                continue
            key, raw = match.groups()
            if (
                (indent == 2 and key not in keep)
                or (
                    indent > 2
                    and key
                    in {
                        "held_items",
                        "global_blockers",
                        "ticker_changes",
                        "open_items",
                        "provider_histories",
                        "review_partition",
                    }
                )
                or (indent > 2 and retained > MAX_METADATA)
            ):
                skip_indent = indent
                continue
            if raw in ("{", "["):
                value = {} if raw == "{" else []
                if isinstance(parent, dict):
                    parent[key] = value
                stack.append((indent, value))
                continue
            try:
                value = json.loads(raw.rstrip(","))
            except ValueError:
                continue
            if isinstance(parent, dict):
                parent[key] = bounded(value)
                retained += min(len(raw), MAX_TEXT)
    if not result.get("run_id") or not result.get("mode"):
        raise ValueError("LEGACY_METADATA_UNAVAILABLE")
    return result


def noop_scope(payload):
    """Full minimal scope for the existing P/B safe-no-op gate; no histories."""
    decision = payload.get("operational_decision") or {}
    if (
        payload.get("operation_type") != "REFRESH_FUNDAMENTALS"
        or payload.get("mode") != "PREVIEW"
        or decision.get("decision_code") != "NO_SAFE_CHANGES"
    ):
        return None
    from .full_workflow import _problem_items

    return {
        "held": [
            {"ticker": x.get("ticker"), "scope": x.get("scope")}
            for x in decision.get("held_items") or []
        ],
        "problems": [
            {
                "ticker": x.get("ticker"),
                "review_scope": x.get("review_scope"),
                "reporting_integrity_error": x.get("reporting_integrity_error"),
            }
            for x in _problem_items(payload)
        ],
    }


def ownership_eligibility_view(result, root):
    """Hydrate exact scope only for the unmodified native P/B no-op predicate.

    Display samples cannot stand in for its full-list checks. The scope is pinned
    to the native RESULT and this parent's completed Preview, never reconstructed
    from samples or labels. No authorization or financial input is changed.
    """
    if (
        result.get("evidence_format") != VERSION
        or result.get("outcome") != "STOPPED"
        or (result.get("operational_decision") or {}).get("decision_code")
        != "NO_SAFE_CHANGES"
    ):
        return result
    try:
        stages = result["stages"]
        if len(stages) != 1 or stages[0]["stage"] != "Preview":
            return None
        stage = stages[0]
        ref = stage["evidence_reference"]
        result_path = verify_reference(root, ref, kind="RESULT", run_id=stage["run_id"])
        if stage.get("noop_scope_reference"):
            path = verify_reference(
                root,
                stage["noop_scope_reference"],
                kind="NOOP_SCOPE",
                run_id=stage["run_id"],
            )
            scope = json.loads(path.read_text())
            if scope["format"] != VERSION or scope["run_id"] != stage["run_id"]:
                return None
            if any(
                scope["result_reference"][key] != ref[key]
                for key in ("run_id", "relative_path", "sha256", "size_bytes")
            ):
                return None
        else:
            # Old small adapters have no scope sidecar. Read their exact bound
            # RESULT on this explicit authority path, never a parent sample.
            if (
                stage.get("summary_reference")
                or result_path.stat().st_size > MAX_METADATA
            ):
                return None
            scope = noop_scope(json.loads(result_path.read_text()))
            if scope is None:
                return None
        decision = dict(result["operational_decision"], held_items=scope["held"])
        terminal = dict(
            result["terminal_summary"],
            problem_items=scope["problems"],
            operational_decision=decision,
        )
        return dict(result, operational_decision=decision, terminal_summary=terminal)
    except (OSError, ValueError, TypeError, KeyError):
        return None
