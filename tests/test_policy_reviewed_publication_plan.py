from collections import Counter
from copy import deepcopy
import csv
import json
from pathlib import Path
import sqlite3
import shutil

import pytest

from tests.test_candidate_publication import database
from rawcandle.fundamentals.admin import reviewed_publication_plan as plans
from rawcandle.fundamentals.admin import policy_reviewed_publication_plan as policy
from rawcandle.fundamentals.admin import publication_backlog_drain as drain
from rawcandle.fundamentals.admin.publication_journal import (
    load_journal,
    sha256_file,
    PublicationRecoveredRetryRequired,
)
from rawcandle.fundamentals.admin.production_transaction import (
    SimulatedTransactionCrash,
)
from rawcandle.fundamentals.generations import (
    prepare_generation_from_candidates,
    activate_generation,
    resolve_active_generation,
)
from rawcandle.fundamentals.publication_event_policy import (
    PUBLICATION_EVENT_POLICY_V1 as V1,
    fingerprint,
)
from rawcandle.fundamentals.result_publication import SecClient, apply_resolution


DAY = "2026-10-06"
FIXTURE = Path(__file__).parent / "fixtures/publication_event_policy_v1.json"
COHORT = json.loads(FIXTURE.read_text())


def insert(db, table, row):
    db.execute(
        f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})",
        tuple(row.values()),
    )


def seeded_policy_root(root, supplied=COHORT):
    root.mkdir(parents=True, exist_ok=True)
    roles = {
        role: database(root / (role + ".db"), count=0)
        for role in ("canonical", "provider", "analysis")
    }
    with sqlite3.connect(roles["canonical"]) as db:
        for c in supplied["cases"]:
            q = c["quarter"]
            db.execute("INSERT OR IGNORE INTO company VALUES(?)", (q["company_id"],))
            cik = (
                c["events"][0]["evidence"]["source_reference"]
                .split("/data/")[1]
                .split("/")[0]
                .zfill(10)
            )
            if not db.execute(
                "SELECT 1 FROM company_cik WHERE company_id=?", (q["company_id"],)
            ).fetchone():
                db.execute(
                    "INSERT INTO company_cik VALUES(?,?,'ACTIVE')",
                    (q["company_id"], cik),
                )
                db.execute(
                    "INSERT INTO security VALUES(?,?,1)", (q["company_id"], c["ticker"])
                )
            columns = (
                "quarter_id",
                "company_id",
                "fiscal_year",
                "fiscal_quarter",
                "period_end",
                "first_public_result_date",
                "source_availability_date",
            )
            insert(db, "v4_quarter", {k: q[k] for k in columns})
            insert(db, "v4_result_publication_authority", c["authority"])
            for e in c["events"]:
                insert(db, "v4_result_publication_evidence", e["evidence"])
        # Unrelated VERIFIED, UNRESOLVED and NOT_FOUND rows must be preserved.
        first = supplied["cases"][0]
        for i, status in enumerate(
            ("VERIFIED", "UNRESOLVED", "NOT_FOUND"), start=900001
        ):
            q = {
                **first["quarter"],
                "quarter_id": i,
                "fiscal_year": 2025,
                "fiscal_quarter": f"Q{i-900000}",
                "period_end": "2025-06-30",
            }
            insert(db, "v4_quarter", {k: q[k] for k in columns})
            e = {
                **first["events"][0]["evidence"],
                "quarter_id": i,
                "fiscal_year": 2025,
                "fiscal_quarter": q["fiscal_quarter"],
                "evidence_id": f"outside_{i}",
                "evidence_hash": str(i) * 10,
            }
            apply_resolution(
                db,
                q,
                [e] if status == "VERIFIED" else [],
                unresolved=status == "UNRESOLVED",
            )
        db.execute("CREATE TABLE financial_sentinel(value REAL)")
        db.execute("INSERT INTO financial_sentinel VALUES(123456.78)")
    manifest = prepare_generation_from_candidates(
        roles, generation_id="policy_source", project_root=root, source="TEST"
    )
    activate_generation(manifest["manifest"], project_root=root)
    return root


def prepare(tmp_path, supplied=COHORT):
    root = seeded_policy_root(tmp_path / "source", supplied)
    evidence = tmp_path / "reviewed_evidence.json"
    evidence.write_text(json.dumps(supplied))
    allowlist = tmp_path / "keys.csv"
    with allowlist.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("company_id", "fiscal_year", "fiscal_quarter"))
        writer.writerows(
            tuple(
                c["quarter"][k] for k in ("company_id", "fiscal_year", "fiscal_quarter")
            )
            for c in supplied["cases"]
        )
    path = tmp_path / "plan.json"
    report = plans.prepare_reviewed_plan(
        project_root=root,
        allowlist_path=allowlist,
        output_plan=path,
        policy_evidence_path=evidence,
        publication_event_policy=V1,
        as_of_date=DAY,
    )
    return root, path, plans.load_plan(path), report


def reseal(plan):
    plan["per_case"] = deepcopy(
        [c for c in plan["policy_cases"] if c["policy_result"] == "POLICY_V1_UNIQUE"]
    )
    plan["plan_fingerprint"] = plans.fingerprint(
        {k: v for k, v in plan.items() if k != "plan_fingerprint"}
    )


def forbid_network(monkeypatch):
    def fail(*a, **kw):
        raise AssertionError("POLICY_PLAN_NETWORK_FORBIDDEN")

    monkeypatch.setattr(SecClient, "_get_json", fail)
    monkeypatch.setattr(SecClient, "_get_text", fail)
    monkeypatch.setattr(SecClient, "_request", fail)


def test_exact_policy_plan_23_3_and_52_retained(tmp_path, monkeypatch):
    forbid_network(monkeypatch)
    root, path, plan, report = prepare(tmp_path)
    assert plan["policy_mode"] == plan["policy_version"] == V1
    assert plan["schema_version"] == 2
    assert report["prepared_key_count"] == 23
    assert report["classification_counts"] == {
        "POLICY_V1_REVIEW": 3,
        "POLICY_V1_UNIQUE": 23,
    }
    assert (
        sum(len(c["original_candidate_evidence"]) for c in plan["policy_cases"]) == 52
    )
    assert Counter(
        c["policy_decision"]["filtering_result"] for c in plan["policy_cases"]
    ) == {"UNIQUE": 19, "AMBIGUOUS": 4, "REVIEW": 3}
    holdouts = {
        c["company_id"]
        for c in plan["policy_cases"]
        if c["policy_result"] == "POLICY_V1_REVIEW"
    }
    assert holdouts == {
        c["quarter"]["company_id"]
        for c in COHORT["cases"]
        if c["ticker"] in {"ABAT", "OPTT", "AMR"}
    }
    assert all(
        c["evidence"] is None
        for c in plan["policy_cases"]
        if c["company_id"] in holdouts
    )
    assert (
        sum(
            e["index_review"] is not None
            for c in plan["policy_cases"]
            for e in c["acceptance_observations"].values()
        )
        == 10
    )
    assert path.stat().st_mode & 0o222 == 0
    assert not (root / "data/.fundamentals_admin_publication_journal.json").exists()


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "candidate",
        "excerpt",
        "context",
        "class",
        "relation",
        "accession",
        "timestamp",
        "acceptance",
        "acceptance_missing",
        "source",
    ],
)
def test_tampered_policy_inputs_or_decisions_fail_even_with_outer_resealed(
    tmp_path, change
):
    _, _, plan, _ = prepare(tmp_path)
    c = next(
        c
        for c in plan["policy_cases"]
        if c["relations"]
        and any(e["index_review"] for e in c["acceptance_observations"].values())
    )
    event_id = next(iter(c["observations"]))
    if change == "version":
        plan["policy_version"] = "LEGACY"
    elif change == "candidate":
        c["original_candidate_evidence"].pop()
    elif change == "excerpt":
        c["observations"][event_id]["documents"][0]["excerpt"] += " changed"
    elif change == "context":
        record = plan["frozen_inputs"][c["frozen_input_reference"]]
        record["filings"][0]["text"] += " changed"
    elif change == "class":
        c["observations"][event_id]["event_class"] = "NON_RESULT_EVENT"
    elif change == "relation":
        c["relations"] = []
    elif change == "accession":
        c["parent_accession"] = "0001326380-26-000051"
    elif change == "timestamp":
        c["parent_acceptance_timestamp"] = "2026-10-01T00:00:00Z"
    elif change.startswith("acceptance"):
        e = next(e for e in c["acceptance_observations"].values() if e["index_review"])
        if change == "acceptance_missing":
            e["index_review"] = None
        else:
            e["index_review"]["index_sha256"] = "a" * 64
    elif change == "source":
        c["original_candidate_evidence"][0]["source_type"] = "ISSUER_EARNINGS_RELEASE"
    reseal(plan)
    with pytest.raises(ValueError):
        plans.validate_plan(plan)


def test_exact_rehearsal_activates_only_23_no_network_unrelated_or_financial_changes(
    tmp_path, monkeypatch
):
    root, path, plan, _ = prepare(tmp_path)
    forbid_network(monkeypatch)
    binding = resolve_active_generation(root)
    hashes = {role: sha256_file(p) for role, p in binding.role_paths().items()}
    result = plans.rehearse_reviewed_plan(
        project_root=root,
        plan_path=path,
        rehearsal_root=tmp_path / "rehearsal",
        as_of_date=DAY,
    )
    assert result["status"] == "PASS" and result["unrelated_changes"] == 0
    writer = result["writer_result"]
    assert writer["status"] == "SUCCESS" and writer["journal_state"] == "COMPLETED"
    assert writer["publication"]["applied_count"] == 23
    assert writer["publication"]["network"]["network_requests"] == 0
    assert set(map(tuple, writer["publication"]["applied_natural_keys"])) == set(
        map(tuple, plan["prepared_keys"])
    )
    journal = load_journal(
        tmp_path / "rehearsal/data/.fundamentals_admin_publication_journal.json"
    )
    assert journal["postflight_state"] == "PASSED"
    assert journal["scope_evidence"]["policy_mode"] == V1
    assert (
        journal["scope_evidence"]["policy_decisions_fingerprint"]
        == plan["policy_decisions_fingerprint"]
    )
    assert all(
        sha256_file(binding.role_paths()[role]) == value
        for role, value in hashes.items()
    )
    active = resolve_active_generation(tmp_path / "rehearsal")
    with sqlite3.connect(active.role_paths()["canonical"]) as db:
        db.row_factory = sqlite3.Row
        for c in plan["policy_cases"]:
            assert (
                policy._evidence_rows(db, plans._key(c))
                == c["original_candidate_evidence"]
            )
            row = plans.state_for_key(db, plans._key(c))["authority"][0]
            if c["policy_result"] == "POLICY_V1_REVIEW":
                assert row == c["state"]["authority"][0]
            else:
                assert (
                    row["result_publication_timestamp_utc"]
                    == c["parent_acceptance_timestamp"]
                )


@pytest.mark.parametrize(
    "stage",
    ["AFTER_PREPARED", "AFTER_NEW_GENERATION_READY", "AFTER_GENERATION_ACTIVATION"],
)
def test_crash_recovery_requires_exact_same_policy_plan(tmp_path, stage):
    root, path, plan, _ = prepare(tmp_path)

    def run(**kwargs):
        return drain.run_backlog_drain(
            project_root=root,
            apply=True,
            confirm_production=True,
            as_of_date=DAY,
            **kwargs,
        )

    with pytest.raises(SimulatedTransactionCrash):
        run(reviewed_apply_plan=path, inject_crash_at=stage)
    with pytest.raises(PublicationRecoveredRetryRequired):
        run(reviewed_apply_plan=path)
    with pytest.raises(RuntimeError, match="SAME_PLAN_REQUIRED"):
        run()
    altered = deepcopy(plan)
    altered["plan_id"] += "_other_review"
    reseal(altered)
    other = tmp_path / "different.json"
    other.write_text(json.dumps(altered))
    with pytest.raises(RuntimeError, match="SAME_PLAN_REQUIRED"):
        run(reviewed_apply_plan=other)
    assert run(reviewed_apply_plan=path)["status"] == "SUCCESS"


def test_zero_key_policy_plan_never_falls_back(tmp_path):
    supplied = deepcopy(COHORT)
    supplied["cases"] = [
        c for c in supplied["cases"] if c["ticker"] in {"ABAT", "OPTT", "AMR"}
    ]
    root, path, plan, report = prepare(tmp_path, supplied)
    before = resolve_active_generation(root)
    result = drain.run_backlog_drain(
        project_root=root,
        apply=True,
        confirm_production=True,
        reviewed_apply_plan=path,
        as_of_date=DAY,
    )
    assert result["status"] == "SKIPPED" and report["prepared_key_count"] == 0
    assert resolve_active_generation(root).generation_id == before.generation_id
    assert not (root / "data/.fundamentals_admin_publication_journal.json").exists()


def test_policy_prepare_requires_explicit_reviewed_input_and_cli_gating(
    tmp_path, monkeypatch
):
    from rawcandle.cli import result_publication_backlog_drain as cli

    with pytest.raises(ValueError, match="REVIEWED_EVIDENCE_REQUIRED"):
        plans.prepare_reviewed_plan(
            project_root=tmp_path,
            allowlist_path=tmp_path / "missing.csv",
            output_plan=tmp_path / "plan.json",
            publication_event_policy=V1,
        )
    with pytest.raises(SystemExit):
        cli.main(["--publication-event-policy", V1])
    with pytest.raises(SystemExit):
        cli.main(["--prepare-reviewed-plan", "--publication-event-policy", V1])
    root, path, plan, _ = prepare(tmp_path / "cli")
    monkeypatch.setattr(cli, "ROOT", root)
    assert (
        cli.main(["--reviewed-apply-plan", str(path), "--publication-event-policy", V1])
        == 0
    )


@pytest.mark.parametrize(
    "kind",
    [
        "INITIAL_RESULT_TO_CORRECTION_OR_REVISION",
        "RESULT_TO_SAME_RESULT_REPEAT",
        "NONQUALIFYING_INITIAL",
    ],
)
def test_revision_repeat_and_nonqualifying_timestamp_semantics_survive_plan_handoff(
    tmp_path, kind
):
    supplied = deepcopy(COHORT)
    supplied["cases"] = [next(c for c in supplied["cases"] if c["ticker"] == "GME")]
    c = supplied["cases"][0]
    a, b = c["events"]
    if kind == "RESULT_TO_SAME_RESULT_REPEAT":
        b["observation"]["event_class"] = "DUPLICATE_OR_REPEAT_PUBLICATION"
    else:
        b["observation"]["event_class"] = "REVISED_OR_CORRECTED_RESULTS"
    c["relations"][0]["relation_type"] = (
        "INITIAL_RESULT_TO_CORRECTION_OR_REVISION"
        if kind == "NONQUALIFYING_INITIAL"
        else kind
    )
    if kind == "NONQUALIFYING_INITIAL":
        a["observation"]["net_result_scope"] = "ABSENT"
    for side, event in (("from", a), ("to", b)):
        c["relations"][0][side + "_observation_fingerprint"] = fingerprint(
            event["observation"]
        )
    root, path, plan, _ = prepare(tmp_path, supplied)
    expected = b if kind == "NONQUALIFYING_INITIAL" else a
    assert (
        plan["per_case"][0]["parent_acceptance_timestamp"]
        == expected["evidence"]["source_timestamp_utc"]
    )
    result = plans.rehearse_reviewed_plan(
        project_root=root,
        plan_path=path,
        rehearsal_root=tmp_path / "rehearsal",
        as_of_date=DAY,
    )
    assert result["status"] == "PASS"


def test_holdout_evidence_drift_blocks_before_any_selected_authority_write(tmp_path):
    root, _, plan, _ = prepare(tmp_path)
    candidate = tmp_path / "inactive.db"
    shutil.copyfile(
        resolve_active_generation(root).role_paths()["canonical"], candidate
    )
    holdout = next(
        c for c in plan["policy_cases"] if c["policy_result"] == "POLICY_V1_REVIEW"
    )
    with sqlite3.connect(candidate) as db:
        db.execute(
            "UPDATE v4_result_publication_evidence SET observed_at_utc='2026-10-06T00:00:00Z' WHERE evidence_id=?",
            (holdout["original_candidate_evidence"][0]["evidence_id"],),
        )
    before = sha256_file(candidate)
    with pytest.raises(RuntimeError, match="CANDIDATE_STATE_DRIFT"):
        plans.run_plan_candidate(candidate, plan, as_of_date=DAY)
    assert sha256_file(candidate) == before


def test_recovery_rejects_missing_policy_journal_binding(tmp_path):
    root, path, _, _ = prepare(tmp_path)
    kwargs = dict(
        project_root=root,
        apply=True,
        confirm_production=True,
        reviewed_apply_plan=path,
        as_of_date=DAY,
    )
    with pytest.raises(SimulatedTransactionCrash):
        drain.run_backlog_drain(**kwargs, inject_crash_at="AFTER_PREPARED")
    with pytest.raises(PublicationRecoveredRetryRequired):
        drain.run_backlog_drain(**kwargs)
    journal_path = root / "data/.fundamentals_admin_publication_journal.json"
    journal = load_journal(journal_path)
    del journal["scope_evidence"]["policy_version"]
    journal_path.write_text(json.dumps(journal))
    with pytest.raises(RuntimeError, match="SAME_POLICY_PLAN_REQUIRED"):
        drain.run_backlog_drain(**kwargs)


def test_legacy_plan_without_policy_field_and_explicit_legacy_are_unchanged(tmp_path):
    from tests.test_reviewed_publication_plan import prepare as prepare_legacy

    _, _, plan, _ = prepare_legacy(tmp_path)
    assert "policy_mode" not in plan and plan["schema_version"] == 1
    assert plans.validate_plan(plan) == plan
    explicit = deepcopy(plan)
    explicit["policy_mode"] = "LEGACY"
    explicit["plan_fingerprint"] = plans.fingerprint(
        {k: v for k, v in explicit.items() if k != "plan_fingerprint"}
    )
    assert plans.validate_plan(explicit)["prepared_keys"] == plan["prepared_keys"]


def test_non_object_plan_is_rejected_without_default_policy_fallback():
    with pytest.raises(ValueError, match="SHAPE_INVALID"):
        plans.validate_plan([])
