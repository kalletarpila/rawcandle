from collections import Counter
import sqlite3

import pytest

from rawcandle.fundamentals.admin.candidate_publication import select_candidate_scope, run_candidate_publication
from rawcandle.fundamentals.result_publication import SecClient
from rawcandle.fundamentals.schema.result_publication import ensure_result_publication_schema
from rawcandle.fundamentals.generations import prepare_generation_from_candidates, activate_generation
from rawcandle.fundamentals.admin.publication_journal import sha256_file


def database(path, count=1):
    with sqlite3.connect(path) as c:
        c.executescript("""
        CREATE TABLE company(company_id INTEGER PRIMARY KEY);
        CREATE TABLE company_cik(company_id,cik_normalized,status);
        CREATE TABLE security(company_id,current_ticker,active);
        CREATE TABLE v4_quarter(quarter_id INTEGER PRIMARY KEY,company_id,fiscal_year,fiscal_quarter,
                              period_end,first_public_result_date,source_availability_date);
        """)
        ensure_result_publication_schema(c)
        for i in range(1,count+1):
            c.execute("INSERT INTO company VALUES(?)",(i,))
            c.execute("INSERT INTO company_cik VALUES(?,?,'ACTIVE')",(i,str(i)))
            c.execute("INSERT INTO security VALUES(?,? ,1)",(i,f"T{i}"))
            c.execute("INSERT INTO v4_quarter VALUES(?,?,2026,'Q3','2026-08-31','2026-09-30','2026-09-30')",(i,i))
    return path


def open_status(path, company, status, day="2026-09-30"):
    with sqlite3.connect(path) as c:
        c.execute("UPDATE v4_quarter SET first_public_result_date=?,source_availability_date=? WHERE company_id=?",(day,day,company))
        c.execute("INSERT INTO v4_result_publication_authority(company_id,fiscal_year,fiscal_quarter,quarter_id,status,rule_version,status_reason,updated_at_utc) VALUES(?,2026,'Q3',?,?,'result_publication_v1','TEST','2026-10-04T00:00:00Z')",(company,company,status))


def test_priority_cap_new_uncapped_old_excluded(tmp_path):
    p=database(tmp_path/"c.db",120)
    open_status(p,1,"AMBIGUOUS")
    open_status(p,2,"NOT_FOUND")
    open_status(p,3,"UNRESOLVED")
    open_status(p,4,"NOT_FOUND","2025-01-01")
    new=[(i,2026,"Q3") for i in range(60,121)]
    scope=select_candidate_scope(p,new,as_of_date="2026-10-04")
    assert len(scope["new_quarters"])==61
    assert scope["retry_selected"]==50
    assert scope["retry_backlog_remaining"]==8
    assert scope["retry_quarters"][0]==(5,2026,"Q3")
    assert (4,2026,"Q3") not in scope["quarter_keys"]
    assert scope==select_candidate_scope(p,new,as_of_date="2026-10-04")
    all_scope=select_candidate_scope(p,[],as_of_date="2026-10-04",retry_max_quarters=200)
    assert all_scope["retry_quarters"][-3:]==[(3,2026,"Q3"),(2,2026,"Q3"),(1,2026,"Q3")]


def test_new_old_context_selected_and_no_candidates_skipped(tmp_path):
    p=database(tmp_path/"c.db")
    open_status(p,1,"NOT_FOUND","2025-01-01")
    assert run_candidate_publication(p,[],as_of_date="2026-10-04")["status"]=="SKIPPED"
    assert select_candidate_scope(p,[(1,2026,"Q3")],as_of_date="2026-10-04",retry_max_quarters=0)["new_quarters"]==[(1,2026,"Q3")]


class Offline:
    stats=Counter()
    def item_2_02_filings(self,*args,**kwargs):
        raise TimeoutError("controlled offline fixture")


def test_transient_partial_finalizable_and_manifest_after_enrichment(tmp_path):
    p=database(tmp_path/"c.db")
    before=sha256_file(p)
    result=run_candidate_publication(p,[(1,2026,"Q3")],as_of_date="2026-10-04",client=Offline())
    assert result["status"]=="PARTIAL"
    assert result["status_counts"]["UNRESOLVED"]==1
    assert sha256_file(p)!=before
    roles={"canonical":p,"provider":database(tmp_path/"p.db"),"analysis":database(tmp_path/"a.db")}
    prepared=prepare_generation_from_candidates(roles,generation_id="candidate_test",project_root=tmp_path,source="TEST")
    active=activate_generation(prepared["manifest"],project_root=tmp_path)
    assert prepared["manifest"]["role_verification"]["canonical"]["sha256"]==sha256_file(active.role_paths()["canonical"])
    active_sha=sha256_file(active.role_paths()["canonical"])
    with pytest.raises(ValueError,match="FINALIZED_GENERATION"):
        run_candidate_publication(active.role_paths()["canonical"],[],as_of_date="2026-10-04",retry_max_quarters=0)
    assert active_sha==sha256_file(active.role_paths()["canonical"])


def test_structural_schema_failure_blocks_before_manifest(tmp_path):
    p=database(tmp_path/"c.db")
    with sqlite3.connect(p) as c:
        c.execute("DROP TABLE v4_result_publication_authority")
    with pytest.raises(sqlite3.OperationalError):
        run_candidate_publication(p,[],as_of_date="2026-10-04")


def test_mid_enrichment_crash_leaves_inactive_candidate_only(tmp_path):
    class Crash(BaseException):
        pass
    class Interrupted(Offline):
        def item_2_02_filings(self,*args,**kwargs):
            raise Crash("during candidate enrichment")
    p=database(tmp_path/"c.db")
    with pytest.raises(Crash):
        run_candidate_publication(p,[],as_of_date="2026-10-04",client=Interrupted())
    assert not (tmp_path/"data/fundamentals_active_generation.json").exists()
    with sqlite3.connect(p) as c:
        assert c.execute("PRAGMA quick_check").fetchone()[0]=="ok"


def test_sec_scoped_date_skips_older_documents_and_budget():
    payload={"filings":{"recent":{"form":["8-K","8-K"],"items":["2.02","2.02"],
        "acceptanceDateTime":["2026-01-30T12:00:00Z","2026-09-30T12:00:00Z"],
        "accessionNumber":["1-26-1","1-26-2"],"primaryDocument":["old.htm","new.htm"]}}}
    urls=[]
    client=SecClient(fetch_json=lambda _:payload,fetch_text=lambda url:urls.append(url) or "Item 2.02 Results of Operations",minimum_interval_seconds=0)
    client.item_2_02_filings("1",from_calendar_year=2026,from_calendar_date="2026-08-31")
    assert len(urls)==1 and urls[0].endswith("new.htm")
    client=SecClient(maximum_runtime_seconds=0)
    with pytest.raises(TimeoutError,match="TIME_BUDGET"):
        client._request("https://data.sec.gov/submissions/CIK1.json")
    assert client.stats["network_requests"]==0


def test_verified_skipped_backlog_advances_and_no_duplicate_evidence(tmp_path):
    p=database(tmp_path/"c.db",2)
    payload={"filings":{"recent":{"form":["8-K"],"items":["2.02"],"acceptanceDateTime":["2026-09-30T12:00:00Z"],"accessionNumber":["1-26-1"],"primaryDocument":["a.htm"]}}}
    client=SecClient(fetch_json=lambda _:payload,fetch_text=lambda _:"Item 2.02 Results of Operations. Quarter ended August 31, 2026.",minimum_interval_seconds=0)
    first=run_candidate_publication(p,[],as_of_date="2026-10-04",retry_max_quarters=1,client=client)
    assert first["status"]=="SUCCESS"
    next_scope=select_candidate_scope(p,[(1,2026,"Q3")],as_of_date="2026-10-04",retry_max_quarters=1)
    assert next_scope["new_quarters"]==[]
    assert next_scope["retry_quarters"]==[(2,2026,"Q3")]
    run_candidate_publication(p,[],as_of_date="2026-10-04",retry_max_quarters=1,client=client)
    assert run_candidate_publication(p,[],as_of_date="2026-10-04",client=client)["status"]=="SKIPPED"
    with sqlite3.connect(p) as c:
        assert c.execute("SELECT COUNT(*) FROM v4_result_publication_evidence").fetchone()[0]==2
