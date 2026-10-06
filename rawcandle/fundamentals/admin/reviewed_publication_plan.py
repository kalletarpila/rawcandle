"""Reviewed operator scope and frozen resolver inputs, never publication authority."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import tempfile
from collections import Counter, defaultdict
from contextlib import closing
from dataclasses import asdict, fields
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from rawcandle.fundamentals.admin.contracts import utc_now
from rawcandle.fundamentals.admin.publication_allowlist import (
    allowlist_evidence, normalize_allowlist, read_allowlist_csv, select_exact_scope,
)
from rawcandle.fundamentals.admin.publication_journal import load_journal, is_incomplete, sha256_file
from rawcandle.fundamentals.generations import resolve_active_generation, active_manifest_path
from rawcandle.fundamentals.result_publication import (
    SecClient, SecFiling, SecResultExhibit, scoped_quarters, resolve_sec_filings_detailed,
    normalize_utc_timestamp,
)
from rawcandle.fundamentals.sec_result_context import same_accession_document

SCHEMA_VERSION = 1
SCOPE_MODE = "REVIEWED_APPLY_PLAN"


def fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def _key(row) -> tuple[int, int, str]:
    return (row["company_id"], row["fiscal_year"], row["fiscal_quarter"])


def _rows(connection, sql, parameters=()):
    return [dict(row) for row in connection.execute(sql, parameters)]


def state_for_key(connection, key):
    """Bind complete quarter, authority and company/CIK/security identity rows."""
    return {
        "quarter": _rows(connection, "SELECT * FROM v4_quarter WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?", key),
        "authority": _rows(connection, "SELECT * FROM v4_result_publication_authority WHERE company_id=? AND fiscal_year=? AND fiscal_quarter=?", key),
        "company": _rows(connection, "SELECT * FROM company WHERE company_id=?", key[:1]),
        "ciks": sorted(_rows(connection, "SELECT * FROM company_cik WHERE company_id=?", key[:1]), key=fingerprint),
        "securities": sorted(_rows(connection, "SELECT * FROM security WHERE company_id=?", key[:1]), key=fingerprint),
    }


def _request(quarters):
    return {"cik": str(quarters[0]["cik_normalized"]),
            "from_calendar_year": min(int(q["period_end"][:4]) for q in quarters),
            "from_calendar_date": min(q["period_end"] for q in quarters),
            "to_calendar_date": (datetime.fromisoformat(max(q["period_end"] for q in quarters))
                                 + timedelta(days=180)).date().isoformat()}


def _request_key(request):
    return (request["cik"], request["from_calendar_year"], request["from_calendar_date"], request["to_calendar_date"])


def _require_clean_journal(root):
    journal = load_journal(root / "data/.fundamentals_admin_publication_journal.json")
    if is_incomplete(journal) or (journal and journal["state"] == "RECOVERED"):
        raise RuntimeError("PUBLICATION_PLAN_JOURNAL_NOT_CLEAN")


def _decode_filing(value):
    if not isinstance(value, dict) or set(value) != {field.name for field in fields(SecFiling)}:
        raise ValueError("PUBLICATION_PLAN_FILING_SHAPE_INVALID")
    string_fields = ("accession_number", "form", "items", "acceptance_timestamp_utc", "primary_document", "source_reference", "text")
    if any(not isinstance(value[name], str) for name in string_fields):
        raise ValueError("PUBLICATION_PLAN_FILING_SHAPE_INVALID")
    if (not re.fullmatch(r"[0-9]{10}-[0-9]{2}-[0-9]{6}", value["accession_number"])
            or value["form"].upper() != "8-K" or "2.02" not in {s.strip() for s in value["items"].split(",")}
            or normalize_utc_timestamp(value["acceptance_timestamp_utc"]) != value["acceptance_timestamp_utc"]
            or type(value["legacy_primary"]) is not bool
            or not isinstance(value["result_sections"], list)
            or any(not isinstance(s, str) for s in value["result_sections"])
            or not isinstance(value["result_exhibits"], list) or len(value["result_exhibits"]) > 2):
        raise ValueError("PUBLICATION_PLAN_FILING_INVALID")
    exhibits = []
    for exhibit in value["result_exhibits"]:
        if (not isinstance(exhibit, dict) or set(exhibit) != {f.name for f in fields(SecResultExhibit)}
                or any(not isinstance(v, str) for v in exhibit.values())
                or not re.fullmatch(r"[0-9a-f]{64}", exhibit["sha256"])
                or not same_accession_document(value["source_reference"], exhibit["source_reference"])):
            raise ValueError("PUBLICATION_PLAN_EXHIBIT_INVALID")
        exhibits.append(SecResultExhibit(**exhibit))
    return SecFiling(**{**value, "result_sections": tuple(value["result_sections"]), "result_exhibits": tuple(exhibits)})


def _resolve(quarters, input_record):
    return resolve_sec_filings_detailed(quarters, [_decode_filing(f) for f in input_record["filings"]])[0]


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    try:
        if type(plan["schema_version"]) is not int or plan["schema_version"] != SCHEMA_VERSION:
            raise ValueError("PUBLICATION_PLAN_SCHEMA_UNSUPPORTED")
        if fingerprint({k: v for k, v in plan.items() if k != "plan_fingerprint"}) != plan["plan_fingerprint"]:
            raise ValueError("PUBLICATION_PLAN_TAMPERED")
        datetime.fromisoformat(normalize_utc_timestamp(plan["created_at_utc"]).replace("Z", "+00:00"))
        date.fromisoformat(plan["as_of_date"])
        if not isinstance(plan["plan_id"], str) or not plan["plan_id"]:
            raise ValueError("PUBLICATION_PLAN_ID_INVALID")
        keys = normalize_allowlist(plan["prepared_keys"])
        if [list(k) for k in keys] != plan["prepared_keys"]:
            raise ValueError("PUBLICATION_PLAN_KEY_ORDER_INVALID")
        source = normalize_allowlist(plan["source_allowlist_keys"])
        if (type(plan["prepared_key_count"]) is not int or type(plan["source_allowlist_count"]) is not int
                or [list(k) for k in source] != plan["source_allowlist_keys"]
                or plan["prepared_key_count"] != len(keys) or plan["prepared_keys_fingerprint"] != fingerprint(plan["prepared_keys"])
                or plan["source_allowlist_count"] != len(source)
                or plan["source_allowlist_fingerprint"] != allowlist_evidence(source)["allowlist_fingerprint"]
                or not set(keys) <= set(source) or [_key(c) for c in plan["per_case"]] != list(keys)):
            raise ValueError("PUBLICATION_PLAN_SCOPE_INVALID")
        cases = plan["per_case"]
        if plan["canonical_authority_fingerprint"] != fingerprint([c["state"] for c in cases]):
            raise ValueError("PUBLICATION_PLAN_STATE_FINGERPRINT_INVALID")
        inputs = plan["frozen_inputs"]
        for input_id, record in inputs.items():
            if input_id != fingerprint(record):
                raise ValueError("PUBLICATION_PLAN_INPUT_FINGERPRINT_INVALID")
            if _request(record["quarters"]) != record["request"]:
                raise ValueError("PUBLICATION_PLAN_REQUEST_BINDING_INVALID")
            context_keys = normalize_allowlist([list(_key(q)) for q in record["quarters"]])
            if (not set(context_keys) <= set(source)
                    or len({q["company_id"] for q in record["quarters"]}) != 1
                    or any(str(q["cik_normalized"]) != record["request"]["cik"] for q in record["quarters"])
                    or not re.fullmatch(r"[0-9]{1,10}", record["request"]["cik"])):
                raise ValueError("PUBLICATION_PLAN_CONTEXT_SCOPE_INVALID")
            # Validate every filing, including negative/ranking context retained in the plan.
            for payload in record["filings"]:
                filing = _decode_filing(payload)
                expected = (f"https://www.sec.gov/Archives/edgar/data/{int(record['request']['cik'])}/"
                            f"{filing.accession_number.replace('-', '')}/{filing.primary_document}")
                if filing.source_reference != expected:
                    raise ValueError("PUBLICATION_PLAN_ACCESSION_CONTEXT_INVALID")
        if set(inputs) != {c["frozen_input_reference"] for c in cases}:
            raise ValueError("PUBLICATION_PLAN_INPUT_SCOPE_INVALID")
        for case in cases:
            key = _key(case)
            normalize_allowlist([list(key)])
            record = inputs[case["frozen_input_reference"]]
            candidates = _resolve(record["quarters"], record).get(key, [])
            state = case["state"]
            prior = state["authority"][0]["status"] if state["authority"] else "MISSING"
            expected_quarter = state["quarter"][0]
            frozen_quarter = next(q for q in record["quarters"] if _key(q) == key)
            active_ciks = {str(row["cik_normalized"]) for row in state["ciks"] if row["status"] == "ACTIVE"}
            if (case["resolver_outcome"] != "FRESH_UNIQUE" or type(case["candidate_count"]) is not int or case["candidate_count"] != 1
                    or case["current_scope_state"] != "SELECTED_OPEN"
                    or prior != case["prior_status"] or prior not in {"MISSING", "UNRESOLVED", "NOT_FOUND"}
                    or len(candidates) != 1 or candidates[0] != case["evidence"]
                    or fingerprint({"input": record, "evidence": case["evidence"]}) != case["evidence_fingerprint"]
                    or _key(expected_quarter) != key
                    or active_ciks != {case["parent_cik"]}
                    or any(frozen_quarter[name] != expected_quarter[name] for name in
                           ("quarter_id", "company_id", "fiscal_year", "fiscal_quarter", "period_end", "first_public_result_date", "source_availability_date"))
                    or str(record["request"]["cik"]) != case["parent_cik"]):
                raise ValueError("PUBLICATION_PLAN_UNIQUE_REPRODUCTION_FAILED")
            evidence = candidates[0]
            for case_field, evidence_field in (("parent_accession", "accession_number"), ("parent_form", "filing_form"),
                                               ("parent_acceptance_timestamp", "source_timestamp_utc"), ("matching_method", "matching_method")):
                if case[case_field] != evidence[evidence_field]:
                    raise ValueError("PUBLICATION_PLAN_PARENT_BINDING_INVALID")
            linked = json.loads(evidence["matching_method"].split(":", 1)[1]) if evidence["matching_method"].startswith("SEC_LINKED_EXHIBIT:") else None
            if case["linked_exhibit_context"] != linked:
                raise ValueError("PUBLICATION_PLAN_EXHIBIT_BINDING_INVALID")
        # APPLY resolves only prepared keys; prove narrowed/chunked context reproduces PREPARE.
        for group in _apply_groups(plan):
            record = inputs[group[0]["frozen_input_reference"]]
            quarters = _case_quarters(group, record)
            matches = _resolve(quarters, record)
            if any(matches.get(_key(c)) != [c["evidence"]] for c in group):
                raise ValueError("PUBLICATION_PLAN_APPLY_CONTEXT_NOT_REPRODUCIBLE")
    except (KeyError, TypeError, IndexError, AttributeError, StopIteration) as exc:
        raise ValueError("PUBLICATION_PLAN_SHAPE_INVALID") from exc
    return plan


def _apply_groups(plan):
    cases = _ordered_cases(plan)
    for offset in range(0, len(cases), 200):
        groups = defaultdict(list)
        for case in cases[offset:offset + 200]:
            groups[case["company_id"]].append(case)
        yield from groups.values()


def _ordered_cases(plan):
    cases = sorted(plan["per_case"], key=_key)
    cases.sort(key=lambda c: max(c["state"]["quarter"][0].get("first_public_result_date") or "",
                                 c["state"]["quarter"][0].get("source_availability_date") or ""), reverse=True)
    cases.sort(key=lambda c: {"MISSING": 0, "UNRESOLVED": 1, "NOT_FOUND": 2}[c["prior_status"]])
    return cases


def _case_quarters(cases, record):
    lookup = {_key(q): q for q in record["quarters"]}
    return [lookup[_key(c)] for c in cases]


def load_plan(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("PUBLICATION_PLAN_PATH_INVALID")
    def unique_fields(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("PUBLICATION_PLAN_DUPLICATE_JSON_FIELD")
            result[key] = value
        return result
    return validate_plan(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_fields))


def prepare_reviewed_plan(*, project_root: Path, allowlist_path: Path, output_plan: Path,
                          client: SecClient | None = None, as_of_date: str | None = None,
                          retry_days: int = 60, network_budget_seconds: float = 1800) -> dict[str, Any]:
    root = project_root.resolve()
    if not math.isfinite(network_budget_seconds) or network_budget_seconds <= 0:
        raise ValueError("PUBLICATION_NETWORK_BUDGET_INVALID")
    day = as_of_date or utc_now()[:10]
    destination = output_plan.resolve()
    if any(base == destination or base in destination.parents for base in (root / "data", root / "backups")):
        raise ValueError("PUBLICATION_PLAN_OUTPUT_PATH_UNSAFE")
    allowed = read_allowlist_csv(allowlist_path)
    provenance = allowlist_evidence(allowed)
    binding = resolve_active_generation(root, require_generation=True)
    _require_clean_journal(root)
    if output_plan.exists() or output_plan.is_symlink():
        raise FileExistsError("PUBLICATION_PLAN_IMMUTABLE_OUTPUT_EXISTS")
    canonical = binding.role_paths()["canonical"]
    scope = select_exact_scope(canonical, allowed, as_of_date=day, retry_days=retry_days)
    client = client or SecClient(maximum_runtime_seconds=network_budget_seconds)
    cases, classifications, inputs = [], [], {}
    with closing(sqlite3.connect(canonical.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        keys = scope["quarter_keys"]
        quarters = []
        for offset in range(0, len(keys), 200):
            quarters.extend(scoped_quarters(connection, 1, (), quarter_keys=keys[offset:offset + 200]))
        groups = defaultdict(list)
        for q in quarters:
            groups[q["company_id"]].append(q)
        for item in scope["classifications"]:
            if item["classification"] != "SELECTED_OPEN":
                outcome = "NO_LONGER_OPEN" if item["classification"] in {"CURRENTLY_VERIFIED", "CURRENTLY_AMBIGUOUS", "NO_LONGER_OPEN"} else "IDENTITY_OR_SCOPE_DRIFT"
                classifications.append({**item, "fresh_outcome": outcome})
        for company_quarters in groups.values():
            request = _request(company_quarters)
            try:
                filings = client.item_2_02_filings(request["cik"], **{k: v for k, v in request.items() if k != "cik"})
            except (OSError, TimeoutError, ValueError, KeyError, IndexError, TypeError) as exc:
                classifications.extend({"natural_key": _key(q), "fresh_outcome": "FETCH_ERROR", "error": str(exc)} for q in company_quarters)
                continue
            record = json.loads(json.dumps({"request": request, "quarters": company_quarters, "filings": [asdict(f) for f in filings]}))
            input_id = fingerprint(record)
            matches, _, diagnostics = resolve_sec_filings_detailed(company_quarters, filings)
            for quarter in company_quarters:
                key = _key(quarter)
                candidates = matches.get(key, [])
                outcome = "FRESH_UNIQUE" if len(candidates) == 1 else "AMBIGUOUS" if candidates else "NO_CANDIDATE"
                classifications.append({"natural_key": key, "fresh_outcome": outcome, "candidate_count": len(candidates), **diagnostics[key]})
                if outcome != "FRESH_UNIQUE":
                    continue
                evidence = candidates[0]
                state = state_for_key(connection, key)
                method = evidence["matching_method"]
                cases.append({"company_id": key[0], "fiscal_year": key[1], "fiscal_quarter": key[2],
                              "prior_status": state["authority"][0]["status"] if state["authority"] else "MISSING",
                              "current_scope_state": "SELECTED_OPEN", "resolver_outcome": outcome, "candidate_count": 1,
                              "state": state, "parent_cik": request["cik"],
                              "parent_accession": evidence["accession_number"], "parent_form": evidence["filing_form"],
                              "parent_acceptance_timestamp": evidence["source_timestamp_utc"], "matching_method": method,
                              "linked_exhibit_context": json.loads(method.split(":", 1)[1]) if method.startswith("SEC_LINKED_EXHIBIT:") else None,
                              "evidence": evidence, "evidence_fingerprint": fingerprint({"input": record, "evidence": evidence}),
                              "frozen_input_reference": input_id})
                inputs[input_id] = record
        cases.sort(key=_key)
        prepared_keys = [list(_key(c)) for c in cases]
        plan = {"schema_version": SCHEMA_VERSION, "plan_id": "publication_plan_" + uuid4().hex,
                "created_at_utc": utc_now(), "as_of_date": day, "retry_days": retry_days,
                "source_allowlist_path": str(allowlist_path.resolve()), "source_allowlist_keys": list(allowed),
                "source_allowlist_count": len(allowed), "source_allowlist_fingerprint": provenance["allowlist_fingerprint"],
                "active_generation_id": binding.generation_id, "active_generation_manifest_fingerprint": fingerprint(binding.manifest),
                "canonical_authority_fingerprint": fingerprint([c["state"] for c in cases]),
                "prepared_key_count": len(cases), "prepared_keys": prepared_keys,
                "prepared_keys_fingerprint": fingerprint(prepared_keys), "per_case": cases,
                "frozen_inputs": inputs, "classifications": sorted(classifications, key=lambda r: r["natural_key"]),
                "prepare_network": dict(client.stats)}
        plan = json.loads(json.dumps(plan))
        plan["plan_fingerprint"] = fingerprint(plan)
        validate_plan(plan)
    revalidate_plan_state(plan, binding, as_of_date=day)
    if fingerprint(resolve_active_generation(root, require_generation=True).manifest) != fingerprint(binding.manifest):
        raise RuntimeError("PUBLICATION_PLAN_GENERATION_DRIFT")
    _require_clean_journal(root)
    output_plan.parent.mkdir(parents=True, exist_ok=True)
    # Publish a complete, exclusive artifact; never overwrite an existing review.
    with tempfile.NamedTemporaryFile(dir=output_plan.parent, mode="w", encoding="utf-8", delete=False) as target:
        temporary = Path(target.name)
        try:
            json.dump(plan, target, indent=2, sort_keys=True, allow_nan=False)
            target.write("\n")
            target.flush()
            os.fsync(target.fileno())
            os.fchmod(target.fileno(), 0o444)
            os.fsync(target.fileno())
            os.link(temporary, output_plan)
        finally:
            temporary.unlink(missing_ok=True)
    descriptor = os.open(output_plan.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return {"status": "PREPARED" if cases else "SKIPPED", "plan_path": str(output_plan.resolve()),
            "plan_id": plan["plan_id"], "plan_fingerprint": plan["plan_fingerprint"],
            "source_allowlist_count": len(allowed), "source_allowlist_fingerprint": provenance["allowlist_fingerprint"],
            "prepared_key_count": len(cases), "classification_counts": dict(Counter(r["fresh_outcome"] for r in classifications))}


def revalidate_plan_state(plan, binding, *, as_of_date):
    validate_plan(plan)
    if (binding.generation_id != plan["active_generation_id"]
            or fingerprint(binding.manifest) != plan["active_generation_manifest_fingerprint"]):
        raise RuntimeError("PUBLICATION_PLAN_GENERATION_DRIFT")
    canonical = binding.role_paths()["canonical"]
    keys = normalize_allowlist(plan["prepared_keys"])
    scope = select_exact_scope(canonical, keys, as_of_date=as_of_date, retry_days=plan["retry_days"])
    if set(scope["quarter_keys"]) != set(keys):
        raise RuntimeError("PUBLICATION_PLAN_OPEN_SCOPE_DRIFT")
    with closing(sqlite3.connect(canonical.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        if any(state_for_key(connection, _key(c)) != c["state"] for c in plan["per_case"]):
            raise RuntimeError("PUBLICATION_PLAN_AUTHORITY_IDENTITY_DRIFT")
    scope["scope_mode"] = SCOPE_MODE
    return scope


class PlanSecClient(SecClient):
    """Only precomputed request windows are valid; all network entry points reject."""
    def __init__(self, plan):
        super().__init__(fetch_json=self._deny, fetch_text=self._deny)
        self.inputs = {}
        for group in _apply_groups(plan):
            record = plan["frozen_inputs"][group[0]["frozen_input_reference"]]
            self.inputs[_request_key(_request(_case_quarters(group, record)))] = tuple(_decode_filing(f) for f in record["filings"])

    @staticmethod
    def _deny(*args, **kwargs):
        raise sqlite3.DatabaseError("PUBLICATION_PLAN_NETWORK_FORBIDDEN")

    _request = _deny

    def item_2_02_filings(self, cik, *, from_calendar_year=2024, from_calendar_date=None, to_calendar_date=None):
        key = (cik, from_calendar_year, from_calendar_date, to_calendar_date)
        if key not in self.inputs:
            raise sqlite3.DatabaseError("PUBLICATION_PLAN_FROZEN_REQUEST_DRIFT")
        self.stats["frozen_input_reads"] += 1
        return list(self.inputs[key])


def run_plan_candidate(candidate_db, plan, *, as_of_date):
    from rawcandle.fundamentals.admin.candidate_publication import run_candidate_publication
    with closing(sqlite3.connect(candidate_db.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        if any(state_for_key(connection, _key(c)) != c["state"] for c in plan["per_case"]):
            raise RuntimeError("PUBLICATION_PLAN_CANDIDATE_STATE_DRIFT")
    # Existing resolver/apply remains authoritative, with only reviewed inputs supplied.
    result = run_candidate_publication(candidate_db, [], as_of_date=as_of_date, retry_days=plan["retry_days"],
                                       client=PlanSecClient(plan), exact_quarter_allowlist=plan["prepared_keys"])
    expected = {tuple(k) for k in plan["prepared_keys"]}
    if (set(result.get("applied_natural_keys", ())) != expected or result["status"] != "SUCCESS"
            or result.get("new_verified") != len(expected)):
        raise RuntimeError("PUBLICATION_PLAN_APPLY_RESULT_DRIFT")
    with closing(sqlite3.connect(candidate_db.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        for case in plan["per_case"]:
            authority = state_for_key(connection, _key(case))["authority"][0]
            evidence = case["evidence"]
            if (authority["status"] != "VERIFIED" or authority["result_publication_timestamp_utc"] != case["parent_acceptance_timestamp"]
                    or authority["selected_evidence_id"] != evidence["evidence_id"]
                    or authority["result_publication_source"] != "SEC_8K_ITEM_2_02"):
                raise RuntimeError("PUBLICATION_PLAN_AUTHORITY_RESULT_DRIFT")
    result["scope_mode"] = SCOPE_MODE
    return result


def plan_scope_evidence(plan):
    return {"scope_mode": SCOPE_MODE, "plan_id": plan["plan_id"], "plan_fingerprint": plan["plan_fingerprint"],
            "prepared_keys_fingerprint": plan["prepared_keys_fingerprint"], "prepared_key_count": plan["prepared_key_count"],
            "source_allowlist_count": plan["source_allowlist_count"], "source_allowlist_fingerprint": plan["source_allowlist_fingerprint"]}


def _canonical_digest(path, *, excluded_keys=(), publication_only=False):
    """Deterministic semantic comparison, excluding only authorized publication keys."""
    keys = set(excluded_keys)
    result = {}
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
            name = row["name"]
            publication = name in {"v4_result_publication_authority", "v4_result_publication_evidence"}
            if publication != publication_only:
                continue
            quoted = '"' + name.replace('"', '""') + '"'
            columns = [r[1] for r in connection.execute(f"PRAGMA table_info({quoted})")]
            order = ",".join('"' + c.replace('"', '""') + '"' for c in columns)
            digest = hashlib.sha256()
            count = 0
            for item in connection.execute(f"SELECT * FROM {quoted} ORDER BY {order}"):
                values = dict(item)
                if publication and _key(values) in keys:
                    continue
                encoded = [v.hex() if isinstance(v, bytes) else v for v in item]
                digest.update(json.dumps(encoded, separators=(",", ":"), ensure_ascii=True).encode() + b"\n")
                count += 1
            result[name] = {"sha256": digest.hexdigest(), "rows": count}
    return result


def rehearse_reviewed_plan(*, project_root: Path, plan_path: Path, rehearsal_root: Path | None = None,
                          as_of_date: str | None = None):
    from rawcandle.fundamentals.admin.publication_backlog_drain import run_backlog_drain
    root = project_root.resolve()
    plan = load_plan(plan_path)
    _require_clean_journal(root)
    binding = resolve_active_generation(root, require_generation=True)
    day = as_of_date or utc_now()[:10]
    revalidate_plan_state(plan, binding, as_of_date=day)
    target = rehearsal_root.resolve() if rehearsal_root else Path(tempfile.mkdtemp(prefix="rawcandle_publication_plan_"))
    if target == root or target in root.parents or root in target.parents:
        raise ValueError("PUBLICATION_PLAN_REHEARSAL_ROOT_UNSAFE")
    if target.exists() and any(target.iterdir()):
        raise ValueError("PUBLICATION_PLAN_REHEARSAL_ROOT_NOT_EMPTY")
    target.mkdir(parents=True, exist_ok=True)
    copied_dir = target / "data/fundamentals_generations" / binding.generation_id
    source_hashes = {role: sha256_file(path) for role, path in binding.role_paths().items()}
    shutil.copytree(binding.generation_dir, copied_dir)
    shutil.copyfile(binding.generation_dir / "generation_manifest.json", active_manifest_path(target))
    keys = normalize_allowlist(plan["prepared_keys"])
    before = {"financial": _canonical_digest(binding.role_paths()["canonical"]),
              "unrelated_publication": _canonical_digest(binding.role_paths()["canonical"], excluded_keys=keys, publication_only=True)}
    result = run_backlog_drain(project_root=target, apply=True, confirm_production=True,
                               reviewed_apply_plan=plan_path, as_of_date=day)
    active = resolve_active_generation(target, require_generation=True)
    after = {"financial": _canonical_digest(active.role_paths()["canonical"]),
             "unrelated_publication": _canonical_digest(active.role_paths()["canonical"], excluded_keys=keys, publication_only=True)}
    if before != after:
        raise RuntimeError("PUBLICATION_PLAN_REHEARSAL_UNRELATED_MUTATION")
    if any(sha256_file(binding.role_paths()[role]) != digest for role, digest in source_hashes.items()):
        raise RuntimeError("PUBLICATION_PLAN_REHEARSAL_SOURCE_CHANGED")
    if any(sha256_file(active.role_paths()[role]) != source_hashes[role] for role in ("provider", "analysis")):
        raise RuntimeError("PUBLICATION_PLAN_REHEARSAL_FINANCIAL_ROLE_CHANGED")
    evidence = {"status": "PASS", "plan_id": plan["plan_id"], "plan_fingerprint": plan["plan_fingerprint"],
                "rehearsal_root": str(target), "before": before, "after": after,
                "unrelated_changes": 0, "writer_result": result, "source_role_hashes": source_hashes}
    report = target / "fundamental_reports/publication_plan_rehearsal.json"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    return evidence
