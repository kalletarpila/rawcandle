from __future__ import annotations

import csv
import json
import sqlite3
import shutil
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from uuid import UUID

import pytest

from tests.test_publication_exact_allowlist import (
    DAY, KEY, FixtureSec, seeded_root, authority_rows,
)
from tests.test_candidate_publication import database
from rawcandle.fundamentals.admin import reviewed_publication_plan as plans
from rawcandle.fundamentals.admin import publication_backlog_drain as drain
from rawcandle.fundamentals.admin.publication_journal import (
    sha256_file, load_journal, PublicationRecoveredRetryRequired,
)
from rawcandle.fundamentals.admin.production_transaction import SimulatedTransactionCrash
from rawcandle.fundamentals.generations import (
    resolve_active_generation, prepare_generation_from_candidates, activate_generation,
)
from rawcandle.fundamentals.result_publication import SecClient, enrich_database


def csv_keys(path, companies):
    with path.open("w", newline="") as target:
        writer = csv.writer(target)
        writer.writerow(("company_id", "fiscal_year", "fiscal_quarter"))
        writer.writerows((company, 2026, "Q3") for company in companies)
    return path


def prepare(tmp_path, *, companies=(1, 2, 3, 4, 6, 7, 8), client=None):
    root = seeded_root(tmp_path / "source")
    allowlist = csv_keys(tmp_path / "review.csv", companies)
    path = tmp_path / "plan.json"
    report = plans.prepare_reviewed_plan(project_root=root, allowlist_path=allowlist, output_plan=path,
                                          as_of_date=DAY, client=client or FixtureSec(empty={6}, failures={7}, ambiguous={8}))
    return root, path, plans.load_plan(path), report


def apply(root, path, **kwargs):
    return drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True,
                                   reviewed_apply_plan=path, as_of_date=DAY, **kwargs)


def forbid_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("network refetch forbidden")
    monkeypatch.setattr(SecClient, "_get_json", fail)
    monkeypatch.setattr(SecClient, "_get_text", fail)


def test_prepare_only_unique_no_production_mutation(tmp_path):
    client = FixtureSec(empty={6}, failures={7}, ambiguous={8})
    root, path, plan, report = prepare(tmp_path, client=client)
    assert plan["prepared_keys"] == [[1, 2026, "Q3"]]
    assert report["classification_counts"] == {"FRESH_UNIQUE": 1, "NO_LONGER_OPEN": 2,
                                               "IDENTITY_OR_SCOPE_DRIFT": 1, "NO_CANDIDATE": 1,
                                               "FETCH_ERROR": 1, "AMBIGUOUS": 1}
    assert client.inspected == [1, 6, 7, 8]
    assert resolve_active_generation(root).generation_id == "old"
    assert not (root / "data/.fundamentals_admin_publication_journal.json").exists()
    assert path.stat().st_mode & 0o222 == 0
    assert plan["source_allowlist_count"] == 7
    assert plan["per_case"][0]["prior_status"] == "UNRESOLVED"
    assert plans.fingerprint(json.loads(json.dumps(plan))) == plans.fingerprint(plan)


def test_deterministic_fingerprint_and_immutable_creation(tmp_path, monkeypatch):
    root = seeded_root(tmp_path / "source")
    allowlist = csv_keys(tmp_path / "review.csv", (1,))
    monkeypatch.setattr(plans, "utc_now", lambda: "2026-10-05T12:00:00Z")
    monkeypatch.setattr(plans, "uuid4", lambda: UUID(int=1))
    files = [tmp_path / "a.json", tmp_path / "b.json"]
    for path in files:
        plans.prepare_reviewed_plan(project_root=root, allowlist_path=allowlist, output_plan=path, client=FixtureSec(), as_of_date=DAY)
    assert plans.load_plan(files[0]) == plans.load_plan(files[1])
    with pytest.raises(FileExistsError):
        plans.prepare_reviewed_plan(project_root=root, allowlist_path=allowlist, output_plan=files[0], client=FixtureSec(), as_of_date=DAY)


@pytest.mark.parametrize("field,value", [("plan_id", "modified"), ("prepared_keys", []), ("prepared_key_count", 0),
                                         ("canonical_authority_fingerprint", "0" * 64), ("frozen_inputs", {})])
def test_tamper_detection(tmp_path, field, value):
    _, _, plan, _ = prepare(tmp_path)
    plan[field] = value
    with pytest.raises(ValueError, match="TAMPERED"):
        plans.validate_plan(plan)


@pytest.mark.parametrize("change", ["schema", "order", "missing_input", "parent_time", "evidence_hash", "scope", "quarter_context"])
def test_malformed_even_with_recomputed_full_fingerprint(tmp_path, change):
    _, _, plan, _ = prepare(tmp_path)
    if change == "schema":
        plan["schema_version"] = 999
    elif change == "order":
        plan["prepared_keys"] = [["1", 2026, "Q3"]]
    elif change == "missing_input":
        plan["frozen_inputs"] = {}
    elif change == "parent_time":
        plan["per_case"][0]["parent_acceptance_timestamp"] = "2026-09-01T12:00:00Z"
    elif change == "evidence_hash":
        plan["per_case"][0]["evidence_fingerprint"] = "f" * 64
    elif change == "quarter_context":
        plan["per_case"][0]["state"]["quarter"][0]["period_end"] = "2026-08-30"
        plan["canonical_authority_fingerprint"] = plans.fingerprint([c["state"] for c in plan["per_case"]])
    else:
        plan["prepared_keys"].append([5, 2026, "Q3"])
    plan["plan_fingerprint"] = plans.fingerprint({k: v for k, v in plan.items() if k != "plan_fingerprint"})
    with pytest.raises(ValueError):
        plans.validate_plan(plan)


def test_production_shaped_rehearsal_and_writer_use_same_frozen_plan(tmp_path, monkeypatch):
    root, path, plan, _ = prepare(tmp_path)
    original = resolve_active_generation(root)
    before = authority_rows(original.role_paths()["canonical"])
    hashes = {role: sha256_file(p) for role, p in original.role_paths().items()}
    forbid_network(monkeypatch)
    rehearsal = plans.rehearse_reviewed_plan(project_root=root, plan_path=path,
                                             rehearsal_root=tmp_path / "rehearsal", as_of_date=DAY)
    assert rehearsal["status"] == "PASS" and rehearsal["unrelated_changes"] == 0
    assert rehearsal["before"] == rehearsal["after"]
    assert rehearsal["plan_fingerprint"] == plan["plan_fingerprint"]
    assert hashes == {role: sha256_file(p) for role, p in original.role_paths().items()}
    assert resolve_active_generation(root).generation_id == "old"
    result = apply(root, path)
    assert result["status"] == "SUCCESS" and result["scope_mode"] == "REVIEWED_APPLY_PLAN"
    assert result["scope_evidence"]["applied_natural_keys"] == [KEY]
    assert result["publication"]["new_verified"] == 1
    after = authority_rows(resolve_active_generation(root).role_paths()["canonical"])
    assert {key: value for key, value in before.items() if key != 1} == {key: value for key, value in after.items() if key != 1}
    assert after[1][4] == "VERIFIED"
    journal = load_journal(root / "data/.fundamentals_admin_publication_journal.json")
    assert journal["state"] == "COMPLETED" and journal["postflight_state"] == "PASSED"
    assert journal["scope_evidence"]["plan_fingerprint"] == plan["plan_fingerprint"]
    assert journal["scope_evidence"]["prepared_keys_fingerprint"] == plan["prepared_keys_fingerprint"]
    assert journal["scope_evidence"]["plan_id"] == plan["plan_id"]
    assert not (root / "temp" / result["run_id"]).exists()
    with sqlite3.connect(resolve_active_generation(root).role_paths()["canonical"]) as c:
        assert c.execute("SELECT result_publication_timestamp_utc FROM v4_result_publication_authority WHERE company_id=1").fetchone()[0] == plan["per_case"][0]["parent_acceptance_timestamp"]


@pytest.mark.parametrize("mutation", ["VERIFIED", "AMBIGUOUS", "authority_metadata", "quarter", "cik", "security", "missing_identity"])
def test_state_drift_fails_before_candidate(tmp_path, mutation):
    root, path, _, _ = prepare(tmp_path)
    canonical = resolve_active_generation(root).role_paths()["canonical"]
    if mutation == "VERIFIED":
        enrich_database(canonical, from_fiscal_year=1, quarter_keys=[KEY], client=FixtureSec(), apply=True)
    with sqlite3.connect(canonical) as c:
        if mutation == "VERIFIED":
            pass
        elif mutation == "AMBIGUOUS":
            c.execute("UPDATE v4_result_publication_authority SET status=? WHERE company_id=1", (mutation,))
        elif mutation == "authority_metadata":
            c.execute("UPDATE v4_result_publication_authority SET updated_at_utc='changed' WHERE company_id=1")
        elif mutation == "quarter":
            c.execute("UPDATE v4_quarter SET period_end='2026-08-30' WHERE company_id=1")
        elif mutation == "cik":
            c.execute("UPDATE company_cik SET cik_normalized='999' WHERE company_id=1")
        elif mutation == "missing_identity":
            c.execute("DELETE FROM company WHERE company_id=1")
        else:
            c.execute("UPDATE security SET current_ticker='RENAMED' WHERE company_id=1")
    with pytest.raises(RuntimeError, match="DRIFT"):
        apply(root, path)
    assert not (root / "fundamental_reports").exists()
    assert not (root / "data/.fundamentals_admin_publication_journal.json").exists()


def test_generation_drift_fails_closed(tmp_path):
    root, path, _, _ = prepare(tmp_path)
    binding = resolve_active_generation(root)
    copies = {}
    for role, source in binding.role_paths().items():
        copies[role] = tmp_path / (role + ".db")
        shutil.copyfile(source, copies[role])
    new = prepare_generation_from_candidates(copies, project_root=root, generation_id="different", source="TEST")
    activate_generation(new["manifest"], project_root=root)
    with pytest.raises(RuntimeError, match="GENERATION_DRIFT"):
        apply(root, path)


def test_zero_key_plan_never_falls_back(tmp_path, monkeypatch):
    root, path, plan, report = prepare(tmp_path, companies=(6,), client=FixtureSec(empty={6}))
    assert plan["prepared_key_count"] == 0 and report["status"] == "SKIPPED"
    forbid_network(monkeypatch)
    result = apply(root, path)
    assert result["status"] == "SKIPPED" and result["skip_reason"] == "NO_PREPARED_PLAN_KEYS"
    assert resolve_active_generation(root).generation_id == "old"
    assert not (root / "fundamental_reports").exists()
    assert not (root / "backups").exists()


@pytest.mark.parametrize("stage", ["AFTER_PREPARED", "AFTER_NEW_GENERATION_READY", "AFTER_GENERATION_ACTIVATION"])
def test_plan_recovery_first_abort_then_same_plan_required(tmp_path, stage):
    root, path, plan, _ = prepare(tmp_path)
    with pytest.raises(SimulatedTransactionCrash):
        apply(root, path, inject_crash_at=stage)
    journal_path = root / "data/.fundamentals_admin_publication_journal.json"
    fence = load_journal(journal_path)["scope_evidence"]
    with pytest.raises(PublicationRecoveredRetryRequired):
        drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True, as_of_date=DAY)
    assert load_journal(journal_path)["scope_evidence"] == fence
    with pytest.raises(RuntimeError, match="SAME_PLAN_REQUIRED"):
        drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True, as_of_date=DAY)
    with pytest.raises(RuntimeError, match="SAME_PLAN_REQUIRED"):
        drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True,
                                exact_quarter_allowlist=[KEY], as_of_date=DAY)
    altered = {**plan, "plan_id": "another_review"}
    altered["plan_fingerprint"] = plans.fingerprint({k: v for k, v in altered.items() if k != "plan_fingerprint"})
    other = tmp_path / "other.json"
    other.write_text(json.dumps(altered))
    with pytest.raises(RuntimeError, match="SAME_PLAN_REQUIRED"):
        apply(root, other)
    assert resolve_active_generation(root).generation_id == "old"
    result = apply(root, path)
    assert result["status"] == "SUCCESS"


def test_post_boundary_rollback_retains_plan_binding(tmp_path, monkeypatch):
    root, path, plan, _ = prepare(tmp_path)
    original = drain.activate_prepared_generation
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("fixture post-boundary failure")
    monkeypatch.setattr(drain, "activate_prepared_generation", fail)
    with pytest.raises(RuntimeError, match="post-boundary"):
        apply(root, path)
    journal = load_journal(root / "data/.fundamentals_admin_publication_journal.json")
    assert journal["state"] == "RECOVERED"
    assert journal["scope_evidence"]["plan_fingerprint"] == plan["plan_fingerprint"]
    assert resolve_active_generation(root).generation_id == "old"


def test_mode_conflicts_and_confirmation(tmp_path):
    root, path, _, _ = prepare(tmp_path)
    with pytest.raises(ValueError, match="INCOMPATIBLE"):
        apply(root, path, exact_quarter_allowlist=[KEY])
    with pytest.raises(ValueError, match="INCOMPATIBLE"):
        apply(root, path, client=FixtureSec())
    with pytest.raises(PermissionError):
        drain.run_backlog_drain(project_root=root, apply=True, reviewed_apply_plan=path)


def test_plan_request_drift_never_fetches(tmp_path):
    _, _, plan, _ = prepare(tmp_path)
    client = plans.PlanSecClient(plan)
    with pytest.raises(sqlite3.DatabaseError, match="FROZEN_REQUEST_DRIFT"):
        client.item_2_02_filings("999", from_calendar_year=2026)
    with pytest.raises(sqlite3.DatabaseError, match="NETWORK_FORBIDDEN"):
        client._request("https://www.sec.gov/")


def test_original_60_row_artifact_valid_prepare_input(tmp_path):
    root = seeded_root(tmp_path / "source")
    original = Path(__file__).parents[1] / "docs/fundamentals_v4/fundamentals_v4_phase13g3_66_controlled_publication_application.csv"
    path = tmp_path / "plan.json"
    report = plans.prepare_reviewed_plan(project_root=root, allowlist_path=original, output_plan=path, client=FixtureSec(), as_of_date=DAY)
    plan = plans.load_plan(path)
    assert plan["source_allowlist_count"] == 60 and report["prepared_key_count"] == 0
    assert plan["source_allowlist_fingerprint"] == "4b69d8500733c1d3e3d5219458bf070dc5c8fb6b99f4082e3241413c9a99ce4e"


def test_cli_prepare_and_plan_modes(tmp_path, monkeypatch, capsys):
    from rawcandle.cli import result_publication_backlog_drain as cli
    root, path, plan, _ = prepare(tmp_path)
    assert cli.main(["--reviewed-apply-plan", str(path), "--rehearsal-root", str(root)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "DRY_RUN"
    with pytest.raises(SystemExit):
        cli.main(["--reviewed-apply-plan", str(path), "--exact-allowlist", "other.csv"])
    with pytest.raises(SystemExit):
        cli.main(["--prepare-reviewed-plan", "--apply"])
    monkeypatch.setattr(cli, "prepare_reviewed_plan", lambda **kwargs: {"status": "PREPARED"})
    assert cli.main(["--prepare-reviewed-plan", "--exact-allowlist", "input.csv", "--output-plan", "output.json"]) == 0


def test_linked_exhibit_roundtrip_keeps_accession_context_and_hash(tmp_path, monkeypatch):
    downloads = Counter()
    def metadata(url):
        downloads[url] += 1
        return {"filings": {"recent": {"form": ["8-K"], "items": ["2.02"],
                "acceptanceDateTime": ["2026-09-30T12:00:00Z"], "accessionNumber": ["0000000001-26-000001"],
                "primaryDocument": ["parent.htm"]}}}
    def document(url):
        downloads[url] += 1
        if url.endswith("parent.htm"):
            return "<p>Item 2.02 Results of Operations.</p><p>We issued an earnings release attached as <a href='ex99-1.htm'>Exhibit 99.1</a>.</p>"
        return "We reported financial results for the third quarter 2026 ended August 31, 2026."
    client = SecClient(fetch_json=metadata, fetch_text=document, minimum_interval_seconds=0)
    root, path, plan, _ = prepare(tmp_path, companies=(1,), client=client)
    case = plan["per_case"][0]
    assert case["linked_exhibit_context"]["parent_accession"] == case["parent_accession"]
    reference = plan["frozen_inputs"][case["frozen_input_reference"]]
    assert case["linked_exhibit_context"]["exhibits"][0]["sha256"] == reference["filings"][0]["result_exhibits"][0]["sha256"]
    assert len(downloads) == 3 and set(downloads.values()) == {1}
    forbid_network(monkeypatch)
    assert apply(root, path)["publication"]["new_verified"] == 1
    assert set(downloads.values()) == {1}


def test_state_revalidation_is_inside_writer_lock(tmp_path, monkeypatch):
    root, path, _, _ = prepare(tmp_path)
    real_lock, real_check = drain.production_lock, drain.revalidate_plan_state
    held = False
    @contextmanager
    def lock(**kwargs):
        nonlocal held
        with real_lock(**kwargs) as owner:
            held = True
            try:
                yield owner
            finally:
                held = False
    def check(*args, **kwargs):
        assert held
        return real_check(*args, **kwargs)
    monkeypatch.setattr(drain, "production_lock", lock)
    monkeypatch.setattr(drain, "revalidate_plan_state", check)
    assert apply(root, path)["status"] == "SUCCESS"


def test_resolver_cannot_be_forced_to_verify_by_plan(tmp_path, monkeypatch):
    root, path, _, _ = prepare(tmp_path)
    real = drain.run_plan_candidate
    def failed_result(*args, **kwargs):
        result = real(*args, **kwargs)
        result["enriched_natural_keys"].append((5, 2026, "Q3"))
        return result
    monkeypatch.setattr(drain, "run_plan_candidate", failed_result)
    with pytest.raises(RuntimeError, match="SCOPE_EXPANDED"):
        apply(root, path)
    assert resolve_active_generation(root).generation_id == "old"
    assert not (root / "data/.fundamentals_admin_publication_journal.json").exists()


def test_parent_corruption_and_duplicate_json_are_rejected(tmp_path):
    _, path, plan, _ = prepare(tmp_path)
    plan["frozen_inputs"][next(iter(plan["frozen_inputs"]))]["filings"][0]["accession_number"] = "0000000001-26-999999"
    plan["plan_fingerprint"] = plans.fingerprint({k: v for k, v in plan.items() if k != "plan_fingerprint"})
    with pytest.raises(ValueError):
        plans.validate_plan(plan)
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ValueError, match="DUPLICATE_JSON"):
        plans.load_plan(duplicate)


def test_plan_reproduction_failures_stop_before_mutation(tmp_path, monkeypatch):
    root, path, plan, _ = prepare(tmp_path)
    from rawcandle.fundamentals.admin import candidate_publication as candidate
    original = candidate.run_candidate_publication
    def nonunique(*args, **kwargs):
        result = original(*args, **kwargs)
        result["new_verified"] = 0
        return result
    monkeypatch.setattr(candidate, "run_candidate_publication", nonunique)
    with pytest.raises(RuntimeError, match="APPLY_RESULT_DRIFT"):
        apply(root, path)
    assert resolve_active_generation(root).generation_id == "old"


def test_cli_rehearsal_uses_copy_not_source(tmp_path, monkeypatch, capsys):
    from rawcandle.cli import result_publication_backlog_drain as cli
    root, path, _, _ = prepare(tmp_path)
    monkeypatch.setattr(cli, "ROOT", root)
    forbid_network(monkeypatch)
    target = tmp_path / "rehearsal"
    assert cli.main(["--reviewed-apply-plan", str(path), "--rehearsal", "--rehearsal-root", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "PASS"
    assert resolve_active_generation(root).generation_id == "old"


def test_same_company_multiple_quarters_keep_original_frozen_window(tmp_path, monkeypatch):
    root = tmp_path / "source"
    root.mkdir()
    roles = {role: database(root / (role + ".db")) for role in ("provider", "canonical", "analysis")}
    with sqlite3.connect(roles["canonical"]) as c:
        c.execute("INSERT INTO v4_quarter VALUES(2,1,2026,'Q2','2026-05-31','2026-09-30','2026-09-30')")
    generation = prepare_generation_from_candidates(roles, project_root=root, generation_id="old", source="TEST")
    activate_generation(generation["manifest"], project_root=root)
    allowlist = tmp_path / "quarters.csv"
    allowlist.write_text("company_id,fiscal_year,fiscal_quarter\n1,2026,Q3\n1,2026,Q2\n")
    def metadata(_):
        return {"filings": {"recent": {"form": ["8-K", "8-K"], "items": ["2.02", "2.02"],
                "acceptanceDateTime": ["2026-06-15T12:00:00Z", "2026-09-30T12:00:00Z"],
                "accessionNumber": ["0000000001-26-000001", "0000000001-26-000002"],
                "primaryDocument": ["q2.htm", "q3.htm"]}}}
    def document(url):
        period = "May 31, 2026" if url.endswith("q2.htm") else "August 31, 2026"
        return "Item 2.02 Results of Operations. Quarter ended " + period + "."
    path = tmp_path / "plan.json"
    plans.prepare_reviewed_plan(project_root=root, allowlist_path=allowlist, output_plan=path, as_of_date=DAY,
                                client=SecClient(fetch_json=metadata, fetch_text=document, minimum_interval_seconds=0))
    plan = plans.load_plan(path)
    assert plan["prepared_key_count"] == 2 and len(plan["frozen_inputs"]) == 1
    assert next(iter(plan["frozen_inputs"].values()))["request"]["from_calendar_date"] == "2026-05-31"
    forbid_network(monkeypatch)
    result = apply(root, path)
    assert result["publication"]["new_verified"] == 2
    assert set(result["scope_evidence"]["applied_natural_keys"]) == {(1, 2026, "Q2"), KEY}
