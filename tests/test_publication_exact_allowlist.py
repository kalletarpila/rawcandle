from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pytest

from tests.test_candidate_publication import database, open_status, Offline
from tests.test_publication_backlog_drain import root_fixture
from rawcandle.fundamentals.admin import publication_backlog_drain as drain
from rawcandle.fundamentals.admin import candidate_publication as candidate
from rawcandle.fundamentals.admin.publication_allowlist import (
    normalize_allowlist, read_allowlist_csv, allowlist_evidence, select_exact_scope, assert_scope_subset,
)
from rawcandle.fundamentals.admin.publication_journal import (
    load_journal, sha256_file, guard_production_writes, PublicationRecoveredRetryRequired,
)
from rawcandle.fundamentals.admin.production_transaction import SimulatedTransactionCrash
from rawcandle.fundamentals.generations import (
    prepare_generation_from_candidates, activate_generation, resolve_active_generation,
)
from rawcandle.fundamentals.result_publication import SecClient, enrich_database


DAY = "2026-10-05"
KEY = (1, 2026, "Q3")


class FixtureSec(SecClient):
    def __init__(self, empty=(), failures=(), ambiguous=()):
        self.inspected = []
        self.empty, self.failures, self.ambiguous = set(empty), set(failures), set(ambiguous)
        super().__init__(fetch_json=self.metadata, fetch_text=lambda _: "Item 2.02 Results of Operations. Quarter ended August 31, 2026.", minimum_interval_seconds=0)

    def metadata(self, url):
        company = int(url.split("CIK", 1)[1].split(".")[0])
        self.inspected.append(company)
        if company in self.failures:
            raise TimeoutError("fixture SEC error")
        count = 0 if company in self.empty else 2 if company in self.ambiguous else 1
        return {"filings": {"recent": {
            "form": ["8-K"] * count, "items": ["2.02"] * count,
            "acceptanceDateTime": [f"2026-09-{29 + i}T12:00:00Z" for i in range(count)],
            "accessionNumber": [f"{company:010d}-26-{i + 1:06d}" for i in range(count)],
            "primaryDocument": [f"filing{i}.htm" for i in range(count)],
        }}}


def seeded_root(root):
    root.mkdir()
    roles = {role: database(root / (role + ".db"), 8) for role in ("provider", "canonical", "analysis")}
    canonical = roles["canonical"]
    open_status(canonical, 1, "UNRESOLVED")
    open_status(canonical, 3, "AMBIGUOUS")
    open_status(canonical, 4, "NOT_FOUND", "2020-01-01")
    open_status(canonical, 5, "NOT_FOUND")
    open_status(canonical, 6, "NOT_FOUND")
    open_status(canonical, 7, "NOT_FOUND")
    enrich_database(canonical, from_fiscal_year=1, quarter_keys=[(2, 2026, "Q3")], client=FixtureSec(), apply=True)
    prepared = prepare_generation_from_candidates(roles, generation_id="old", project_root=root, source="TEST")
    activate_generation(prepared["manifest"], project_root=root)
    return root


def authority_rows(path):
    with sqlite3.connect(path) as connection:
        return {row[0]: row for row in connection.execute("SELECT * FROM v4_result_publication_authority ORDER BY company_id")}


def run(root, keys, **kwargs):
    return drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True,
                                   as_of_date=DAY, exact_quarter_allowlist=keys, **kwargs)


def test_input_normalization_fingerprint_and_duplicate_rejection():
    a = normalize_allowlist([(" 2", "2026", "q3"), KEY])
    b = normalize_allowlist([KEY, (2, 2026, "Q3")])
    assert a == b == (KEY, (2, 2026, "Q3"))
    assert allowlist_evidence(a) == allowlist_evidence(b)
    assert len(allowlist_evidence(a)["allowlist_fingerprint"]) == 64
    with pytest.raises(ValueError, match="DUPLICATE"):
        normalize_allowlist([KEY, ("01", "2026", " q3 ")])


@pytest.mark.parametrize("bad", [
    [(1, 2026)], [(1, 2026, "Q3", 9)], ["T1"], [True],
    [(True, 2026, "Q3")], [(1.0, 2026, "Q3")], [("1.0", 2026, "Q3")],
    [(0, 2026, "Q3")], [(-1, 2026, "Q3")], [(2**63, 2026, "Q3")],
    [(1, -1, "Q3")], [(1, 10000, "Q3")], [(1, 2026, "Q5")], [(1, 2026, 3)],
])
def test_malformed_rejected_before_candidate_creation(tmp_path, bad):
    with pytest.raises(ValueError):
        drain.run_backlog_drain(project_root=tmp_path, exact_quarter_allowlist=bad)
    assert not (tmp_path / "temp").exists()


def test_csv_contract_and_60_reviewed_keys(tmp_path):
    path = Path(__file__).parents[1] / "docs/fundamentals_v4/fundamentals_v4_phase13g3_66_controlled_publication_application.csv"
    keys = read_allowlist_csv(path)
    assert len(keys) == len(set(keys)) == 60
    import csv
    from collections import Counter
    rows = list(csv.DictReader(path.open()))
    assert Counter(row["prior_status"] for row in rows) == {"UNRESOLVED": 28, "NOT_FOUND": 32}
    assert all(row["recognition_cluster"] in {"EXHIBIT_QUARTER_CONTEXT", "ITEM202_HEADING_VARIANTS"} for row in rows)
    empty = tmp_path / "empty.csv"
    empty.write_text("company_id,fiscal_year,fiscal_quarter\n")
    assert read_allowlist_csv(empty) == ()


@pytest.mark.parametrize("contents", [
    "ticker,fiscal_year,fiscal_quarter\nT1,2026,Q3\n",
    "company_id,company_id,fiscal_year,fiscal_quarter\n1,2,2026,Q3\n",
    "company_id,fiscal_year,fiscal_quarter\n1,2026,Q3\n01,2026,q3\n",
    "company_id,fiscal_year,fiscal_quarter\n1,2026,\n",
    "company_id,fiscal_year,fiscal_quarter\n1,2026,Q3,extra\n",
])
def test_malformed_csv_is_rejected(tmp_path, contents):
    path = tmp_path / "bad.csv"
    path.write_text(contents)
    with pytest.raises(ValueError):
        read_allowlist_csv(path)


def test_exact_classification(tmp_path):
    root = seeded_root(tmp_path / "root")
    path = resolve_active_generation(root).role_paths()["canonical"]
    keys = normalize_allowlist([(i, 2026, "Q3") for i in (1, 2, 3, 4, 6, 99)])
    scope = select_exact_scope(path, keys, as_of_date=DAY)
    by_company = {row["natural_key"][0]: row["classification"] for row in scope["classifications"]}
    assert by_company == {1: "SELECTED_OPEN", 2: "CURRENTLY_VERIFIED", 3: "CURRENTLY_AMBIGUOUS",
                          4: "NOT_IN_CURRENT_SCOPE", 6: "SELECTED_OPEN", 99: "IDENTITY_MISSING"}
    assert set(scope["quarter_keys"]) == {KEY, (6, 2026, "Q3")}
    assert_scope_subset(scope["quarter_keys"], keys)


def test_missing_cik_is_report_error_not_enriched(tmp_path):
    path = database(tmp_path / "db")
    with sqlite3.connect(path) as connection:
        connection.execute("DELETE FROM company_cik")
    scope = select_exact_scope(path, (KEY,), as_of_date=DAY)
    assert scope["quarter_keys"] == [] and scope["skipped_counts"] == {"ERROR": 1}


def test_empty_explicit_is_noop_and_none_preserves_default(tmp_path):
    root = root_fixture(tmp_path / "root")
    before = resolve_active_generation(root)
    hashes = {role: sha256_file(path) for role, path in before.role_paths().items()}
    result = run(root, [], client=Offline())
    assert result["status"] == "SKIPPED" and result["skip_reason"] == "NO_ELIGIBLE_ALLOWLIST_ITEMS"
    assert result["scope"]["selected_count"] == 0
    assert not (root / "fundamental_reports").exists()
    assert not (root / "data/.fundamentals_admin_publication_journal.json").exists()
    assert hashes == {role: sha256_file(path) for role, path in before.role_paths().items()}
    default = drain.run_backlog_drain(project_root=root, as_of_date=DAY)
    explicit_none = drain.run_backlog_drain(project_root=root, as_of_date=DAY, exact_quarter_allowlist=None)
    assert default == explicit_none and default["scope"]["retry_selected"] == 3


def test_production_shaped_allowlist_rehearsal(tmp_path):
    root = seeded_root(tmp_path / "root")
    old = resolve_active_generation(root)
    before = authority_rows(old.role_paths()["canonical"])
    hashes = {role: sha256_file(path) for role, path in old.role_paths().items()}
    client = FixtureSec(empty={6})
    allowed = [(i, 2026, "Q3") for i in (1, 2, 3, 4, 6, 99)]
    result = run(root, allowed, client=client)
    assert result["status"] == "PARTIAL"
    assert client.inspected == [1, 6]  # one fetch per selected company, not per preview/apply
    assert result["scope"]["selected_count"] == 2
    assert result["scope_evidence"]["applied_count"] == 2
    assert result["publication"]["new_verified"] == 1
    active = resolve_active_generation(root)
    after = authority_rows(active.role_paths()["canonical"])
    assert {company: row for company, row in before.items() if company not in (1, 6)} == {
        company: row for company, row in after.items() if company not in (1, 6)}
    assert after[1][4] == "VERIFIED" and after[3] == before[3] and after[2] == before[2]
    assert after[6][4] == "NOT_FOUND"
    assert hashes == {role: sha256_file(path) for role, path in old.role_paths().items()}
    for role in ("provider", "analysis"):
        assert hashes[role] == sha256_file(active.role_paths()[role])
    with sqlite3.connect(active.role_paths()["canonical"]) as connection:
        connection.execute("ATTACH DATABASE ? AS old", (str(old.role_paths()["canonical"]),))
        for table in ("v4_quarter", "company", "company_cik", "security"):
            assert not connection.execute(f"SELECT * FROM main.{table} EXCEPT SELECT * FROM old.{table}").fetchall()
            assert not connection.execute(f"SELECT * FROM old.{table} EXCEPT SELECT * FROM main.{table}").fetchall()
        assert connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
        assert not connection.execute("PRAGMA foreign_key_check").fetchall()
    journal = load_journal(root / "data/.fundamentals_admin_publication_journal.json")
    assert journal["state"] == "COMPLETED" and journal["scope_evidence"] == json.loads(json.dumps(result["scope_evidence"]))
    assert journal["scope_evidence"]["allowlist_count"] == 6
    assert journal["scope_evidence"]["allowlist_fingerprint"] == allowlist_evidence(normalize_allowlist(allowed))["allowlist_fingerprint"]
    assert not (root / "temp" / result["run_id"]).exists()


def test_fetch_error_does_not_mutate_selected_authority(tmp_path):
    root = seeded_root(tmp_path / "root")
    old = resolve_active_generation(root)
    before = authority_rows(old.role_paths()["canonical"])
    result = run(root, [KEY, (7, 2026, "Q3")], client=FixtureSec(failures={7}))
    after = authority_rows(resolve_active_generation(root).role_paths()["canonical"])
    assert after[7] == before[7]
    assert result["scope_evidence"]["applied_count"] == 1
    assert result["publication"]["skipped_error_natural_keys"] == [(7, 2026, "Q3")]


def test_frozen_accession_exhibit_and_hash_are_exact_precheck_inputs(tmp_path, monkeypatch):
    from collections import Counter
    from rawcandle.fundamentals.result_publication import apply_resolution
    from rawcandle.fundamentals.admin import candidate_publication as module
    path = database(tmp_path / "db")
    downloads = Counter()
    accession = "0000000001-26-000001"
    def metadata(url):
        downloads[url] += 1
        return {"filings": {"recent": {"form": ["8-K"], "items": ["2.02"],
                "acceptanceDateTime": ["2026-09-30T12:00:00Z"], "accessionNumber": [accession],
                "primaryDocument": ["parent.htm"]}}}
    def document(url):
        downloads[url] += 1
        # A second provider read would supply a different, conflicting payload.
        if downloads[url] > 1:
            return "We reported preliminary results for the quarter ended May 31, 2026."
        if url.endswith("parent.htm"):
            return "<p>Item 2.02 Results of Operations.</p><p>We issued an earnings release attached as <a href='ex99-1.htm'>Exhibit 99.1</a>.</p>"
        return "We reported financial results for the third quarter 2026 ended August 31, 2026."
    client = SecClient(fetch_json=metadata, fetch_text=document, minimum_interval_seconds=0)
    original = module.enrich_database
    frozen = None
    def observe(*args, **kwargs):
        nonlocal frozen
        adapter = kwargs["client"]
        if kwargs["apply"]:
            assert adapter.sealed and adapter.filings == frozen
        report = original(*args, **kwargs)
        if not kwargs["apply"]:
            frozen = dict(adapter.filings)
            filing = next(iter(frozen.values()))[0]
            assert filing.accession_number == accession
            assert len(filing.result_exhibits) == 1
            assert "/000000000126000001/" in filing.result_exhibits[0].source_reference
        return report
    monkeypatch.setattr(module, "enrich_database", observe)
    result = module.run_candidate_publication(path, [], as_of_date=DAY, client=client, exact_quarter_allowlist=[KEY])
    assert result["new_verified"] == 1 and len(downloads) == 3 and set(downloads.values()) == {1}
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        evidence = dict(connection.execute("SELECT * FROM v4_result_publication_evidence").fetchone())
        context = json.loads(evidence["matching_method"].split(":", 1)[1])
        precheck = next(iter(frozen.values()))[0]
        assert evidence["accession_number"] == context["parent_accession"] == precheck.accession_number
        assert evidence["source_timestamp_utc"] == precheck.acceptance_timestamp_utc
        assert context["exhibits"][0]["url"] == precheck.result_exhibits[0].source_reference
        assert context["exhibits"][0]["sha256"] == precheck.result_exhibits[0].sha256
        # Current apply precedence remains authoritative; frozen context is no new tier.
        stronger = {**evidence, "source_type": "ISSUER_EARNINGS_RELEASE", "source_timestamp_utc": "2026-09-30T11:00:00Z",
                    "evidence_hash": "f" * 64, "evidence_id": "issuer_fixture"}
        q = {"quarter_id": 1, "company_id": 1, "fiscal_year": 2026, "fiscal_quarter": "Q3"}
        assert apply_resolution(connection, q, [stronger]) == "VERIFIED"
        assert apply_resolution(connection, q, [evidence]) == "VERIFIED"
        assert connection.execute("SELECT result_publication_source FROM v4_result_publication_authority").fetchone()[0] == "ISSUER_EARNINGS_RELEASE"


def test_new_resolver_conflict_remains_ambiguous(tmp_path):
    root = root_fixture(tmp_path / "root")
    result = run(root, [KEY], client=FixtureSec(ambiguous={1}))
    assert result["publication"]["status_counts"] == {"VERIFIED": 0, "UNRESOLVED": 0, "AMBIGUOUS": 1, "NOT_FOUND": 0}
    assert authority_rows(resolve_active_generation(root).role_paths()["canonical"])[1][4] == "AMBIGUOUS"


def test_authoritative_selection_only_under_writer_lock(tmp_path, monkeypatch):
    root = root_fixture(tmp_path / "root")
    real_lock, real_select = drain.production_lock, drain.select_exact_scope
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
    def select(*args, **kwargs):
        assert held
        return real_select(*args, **kwargs)
    monkeypatch.setattr(drain, "production_lock", lock)
    monkeypatch.setattr(drain, "select_exact_scope", select)
    run(root, [KEY], client=FixtureSec())


def test_subset_checks_fail_closed():
    with pytest.raises(RuntimeError, match="SCOPE_EXPANDED"):
        assert_scope_subset([KEY, (2, 2026, "Q3")], [KEY])
    with pytest.raises(RuntimeError):
        assert_scope_subset([KEY, KEY], [KEY])


def test_exact_key_does_not_expand_to_other_quarter_of_same_company(tmp_path):
    path = database(tmp_path / "db", 2)
    with sqlite3.connect(path) as connection:
        connection.execute("INSERT INTO v4_quarter VALUES(3,1,2026,'Q2','2026-05-31','2026-09-30','2026-09-30')")
        connection.execute("INSERT INTO v4_result_publication_authority(company_id,fiscal_year,fiscal_quarter,quarter_id,status,rule_version,status_reason,updated_at_utc) VALUES(1,2026,'Q2',3,'NOT_FOUND','result_publication_v1','TEST','sentinel')")
        before = connection.execute("SELECT * FROM v4_result_publication_authority WHERE fiscal_quarter='Q2'").fetchall()
    result = candidate.run_candidate_publication(path, [], as_of_date=DAY, client=FixtureSec(), exact_quarter_allowlist=[KEY])
    assert result["applied_natural_keys"] == [KEY]
    with sqlite3.connect(path) as connection:
        assert before == connection.execute("SELECT * FROM v4_result_publication_authority WHERE fiscal_quarter='Q2'").fetchall()


def test_multiple_chunks_exact_scope_and_no_retry_cap_emulation(tmp_path):
    path = database(tmp_path / "db", 205)
    keys = [(i, 2026, "Q3") for i in range(1, 206)]
    result = candidate.run_candidate_publication(path, [], as_of_date=DAY, retry_max_quarters=1,
                                               client=FixtureSec(), exact_quarter_allowlist=keys)
    assert result["selected_count"] == result["applied_count"] == result["new_verified"] == 205
    assert result["new_quarters"] == [] and set(result["applied_natural_keys"]) == set(keys)


def test_empty_allowlist_remains_empty_after_terminal_recovery_check(tmp_path):
    root = root_fixture(tmp_path / "root")
    run(root, [KEY], client=FixtureSec())
    path = root / "data/.fundamentals_admin_publication_journal.json"
    before = sha256_file(path)
    active = resolve_active_generation(root).generation_id
    assert guard_production_writes(path)["status"] == "COMPLETED"
    client = FixtureSec()
    for _ in range(2):
        assert run(root, [], client=client)["status"] == "SKIPPED"
    assert not client.inspected and sha256_file(path) == before
    assert resolve_active_generation(root).generation_id == active


def test_input_without_confirmation_and_new_quarter_overload_rejected(tmp_path):
    root = root_fixture(tmp_path / "root")
    with pytest.raises(PermissionError):
        drain.run_backlog_drain(project_root=root, apply=True, exact_quarter_allowlist=[KEY])
    path = database(tmp_path / "candidate")
    with pytest.raises(ValueError, match="NEW_THIS_REFRESH"):
        candidate.run_candidate_publication(path, [KEY], as_of_date=DAY, exact_quarter_allowlist=[KEY])


@pytest.mark.parametrize("stage", ["AFTER_PREPARED", "AFTER_NEW_GENERATION_READY", "AFTER_GENERATION_ACTIVATION"])
def test_crash_recovery_scope_and_first_retry_abort(tmp_path, stage):
    root = root_fixture(tmp_path / "root")
    with pytest.raises(SimulatedTransactionCrash):
        run(root, [KEY], client=FixtureSec(), inject_crash_at=stage)
    path = root / "data/.fundamentals_admin_publication_journal.json"
    before = load_journal(path)["scope_evidence"]
    with pytest.raises(PublicationRecoveredRetryRequired):
        drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True, as_of_date=DAY, client=FixtureSec())
    assert resolve_active_generation(root).generation_id == "old"
    assert load_journal(path)["scope_evidence"] == before
    with pytest.raises(RuntimeError, match="RECOVERY_SCOPE_REQUIRED"):
        drain.run_backlog_drain(project_root=root, apply=True, confirm_production=True, as_of_date=DAY, client=FixtureSec())
    with pytest.raises(RuntimeError, match="RECOVERY_SCOPE_REQUIRED"):
        run(root, [(2, 2026, "Q3")], client=FixtureSec())
    client = FixtureSec()
    result = run(root, [KEY], client=client)
    assert client.inspected == [1] and result["scope_evidence"]["selected_natural_keys"] == [KEY]


def test_ordinary_post_boundary_failure_restores_scope(tmp_path, monkeypatch):
    root = root_fixture(tmp_path / "root")
    original = drain.activate_prepared_generation
    def fail(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError("fixture post-boundary failure")
    monkeypatch.setattr(drain, "activate_prepared_generation", fail)
    with pytest.raises(RuntimeError, match="post-boundary"):
        run(root, [KEY], client=FixtureSec())
    journal = load_journal(root / "data/.fundamentals_admin_publication_journal.json")
    assert journal["state"] == "RECOVERED" and journal["scope_evidence"]["selected_natural_keys"] == [[1, 2026, "Q3"]]
    assert resolve_active_generation(root).generation_id == "old"


def test_prepublication_failure_and_scope_expansion_never_activate(tmp_path, monkeypatch):
    root = root_fixture(tmp_path / "root")
    original = drain.run_candidate_publication
    def expanded(*args, **kwargs):
        result = original(*args, **kwargs)
        result["enriched_natural_keys"].append((2, 2026, "Q3"))
        return result
    monkeypatch.setattr(drain, "run_candidate_publication", expanded)
    with pytest.raises(RuntimeError, match="SCOPE_EXPANDED"):
        run(root, [KEY], client=FixtureSec())
    assert resolve_active_generation(root).generation_id == "old"
    assert not (root / "data/.fundamentals_admin_publication_journal.json").exists()


def test_cli_reports_fingerprint_before_execution(tmp_path, monkeypatch, capsys):
    import rawcandle.cli.result_publication_backlog_drain as cli
    path = tmp_path / "allow.csv"
    path.write_text("company_id,fiscal_year,fiscal_quarter\n1,2026,Q3\n")
    def writer(**kwargs):
        assert kwargs["exact_quarter_allowlist"] == (KEY,)
        assert kwargs["apply"] is False
        return {"status": "DRY_RUN"}
    monkeypatch.setattr(cli, "run_backlog_drain", writer)
    assert cli.main(["--exact-allowlist", str(path)]) == 0
    out = capsys.readouterr()
    assert json.loads(out.err)["allowlist_count"] == 1
    assert json.loads(out.out)["status"] == "DRY_RUN"
