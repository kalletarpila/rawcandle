from rawcandle.research.forecast_revision_research import ordered_observations, summarize_forecast_revision_research
from rawcandle.research.forecast_revision_research import analyze_event, classify_fetch, numeric, revision, reconstruct_fetch
from rawcandle.forecasts.fiscal_linker import LINK_RULE_VERSION
from rawcandle.forecasts.identity import IDENTITY_RULE_VERSION
import sqlite3
import pytest


def event(status="EXACT"):
    return {"company_id": "1", "ticker": "TEST", "fiscal_year": "2026", "fiscal_quarter": "Q3",
            "research_status": status, "canonical_timestamp_utc": "2026-09-29T20:00:00Z",
            "research_publication_date": "2026-09-29", "first_full_post_result_trading_date": "2026-09-30"}


def observation(order, stamp, horizon, target, value=1.0):
    return {"company_id": 1, "fetch_order": order, "fetch_id": str(order), "snapshot_id": "snapshot",
            "link_id": str(order), "resolution_id": str(order), "fetched_at_utc": stamp,
            "horizon": horizon, "target": (1,2026,target), "states": {
                "EPS_ESTIMATE:AVG": {"state": "NUMERIC_VALUE", "numeric": value},
                "EPS_ANALYST_COUNT:VALUE": {"state": "NUMERIC_VALUE", "numeric": order}}}


@pytest.mark.parametrize("stamp,expected", [("2026-09-29T19:59:59Z","PRE_RESULT"),
                                           ("2026-09-29T20:00:00Z","POST_RESULT")])
def test_exact_pre_post(stamp, expected):
    assert classify_fetch(event(),stamp)==expected


def test_daily_boundary_does_not_invent_hour():
    e=event("HEURISTIC_HIGH")
    assert classify_fetch(e,"2026-09-28T12:00:00Z")=="PRE_RESULT"
    assert classify_fetch(e,"2026-09-29T12:00:00Z")=="BOUNDARY_UNCERTAIN"
    assert classify_fetch(e,"2026-09-30T12:00:00Z")=="POST_RESULT"


def test_transition_same_target_and_determinism():
    rows=[observation(1,"2026-09-29T12:00:00Z","0q","Q3",99),
          observation(2,"2026-09-29T12:00:00Z","+1q","Q4",1),
          observation(3,"2026-09-30T12:00:00Z","0q","Q4",2)]
    actual=analyze_event(event(),rows,(1,2026,"Q4"),["2026-09-29","2026-09-30"])
    assert actual==analyze_event(event(),list(reversed(rows)),(1,2026,"Q4"),["2026-09-29","2026-09-30"])
    assert actual["transition_status"]=="OBSERVED"
    assert actual["transition_interval_hours"]==24
    assert actual["eps_revision_abs"]==1
    assert actual["eps_analyst_count_change"]==1
    assert actual["pre_eps_avg"]!=99
    assert actual["transition_trading_day_class"]=="NEXT_TRADING_DAY"


def test_cross_quarter_not_a_revision():
    rows=[observation(1,"2026-09-29T12:00:00Z","0q","Q3",99),
          observation(2,"2026-09-30T12:00:00Z","0q","Q4",2)]
    actual=analyze_event(event(),rows,(1,2026,"Q4"),[])
    assert not actual["comparable"]
    assert actual["eps_revision_abs"] is None


def test_checkpoints_on_or_after_and_heuristic_hour_null():
    import json
    rows=[observation(1,"2026-09-28T12:00:00Z","+1q","Q4"),
          observation(2,"2026-09-30T12:00:00Z","0q","Q4"),
          observation(3,"2026-10-02T12:00:00Z","0q","Q4")]
    result=analyze_event(event("HEURISTIC_HIGH"),rows,(1,2026,"Q4"),
                         ["2026-09-30","2026-10-01","2026-10-02"])
    checkpoints=json.loads(result["checkpoints_json"])
    assert checkpoints["1"]["fetch_id"]=="3"
    assert checkpoints["2"]["fetch_id"]=="3"
    assert checkpoints["5"] is None
    assert result.get("hours_publication_to_new_0q_first_seen") is None


@pytest.mark.parametrize("rows,status", [([],"NO_USABLE_0Q"),
    ([observation(1,"2026-09-30T12:00:00Z","0q","Q4")],"INSUFFICIENT_PRE_HISTORY"),
    ([observation(1,"2026-09-29T12:00:00Z","0q","Q3")],"INSUFFICIENT_POST_HISTORY"),
    ([observation(1,"2026-09-29T12:00:00Z","0q","Q3"),observation(2,"2026-09-30T12:00:00Z","0q","Q3")],"NOT_YET_OBSERVED")])
def test_transition_censoring(rows,status):
    assert analyze_event(event(),rows,(1,2026,"Q4"),[])["transition_status"]==status


def test_null_absent_empty_zero_and_percent_guard():
    assert numeric(None,"EPS_ESTIMATE","AVG") is None
    for state in ("EXPLICIT_NULL","EMPTY_OBJECT","ABSENT"):
        assert numeric({"states":{"EPS_ESTIMATE:AVG":{"state":state,"numeric":None}}},"EPS_ESTIMATE","AVG") is None
    assert numeric({"states":{"EPS_ESTIMATE:AVG":{"state":"NUMERIC_ZERO","numeric":"0"}}},"EPS_ESTIMATE","AVG")==0
    for pre,post in ((0,1),(1e-10,1),(-1,1),(-2,-1)):
        absolute,pct,flag=revision(pre,post)
        assert absolute==post-pre and pct is None and flag


def test_fetch_specific_as_known_unchanged_snapshot():
    c=sqlite3.connect(":memory:")
    c.row_factory=sqlite3.Row
    c.executescript("""
      CREATE TABLE forecast_snapshot(snapshot_id,forecast_family);
      CREATE TABLE forecast_fiscal_link(fetch_id,knowledge_mode,link_rule_version,linked_at_utc,
        fundamentals_as_of_utc,occurrence_index,link_status,snapshot_id,resolution_id,company_id,
        security_id,provider_horizon,expected_fiscal_year,expected_fiscal_quarter,canonical_quarter_id,link_id);
      CREATE TABLE forecast_identity_resolution(resolution_id,fetch_id,identity_rule_version,
        identity_status,company_id,security_id,acquisition_timestamp_utc);
      CREATE TABLE forecast_estimate(snapshot_id,occurrence_index,estimate_id,metric,statistic,value_state,value_numeric,value_text);
    """)
    stamp="2026-09-29T12:00:00Z"
    c.execute("INSERT INTO forecast_snapshot VALUES(?,?)",("old_snapshot","FISCAL_ESTIMATE"))
    c.execute("INSERT INTO forecast_identity_resolution VALUES(?,?,?,?,?,?,?)",("r","unchanged",IDENTITY_RULE_VERSION,"RESOLVED",1,10,stamp))
    for mode,asof,quarter,identifier in (("AS_KNOWN",stamp,"Q3","valid"),("CURRENT_RECONCILED",stamp,"Q4","reconciled"),("AS_KNOWN","2026-10-01T12:00:00Z","Q4","future")):
        c.execute("INSERT INTO forecast_fiscal_link VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("unchanged",mode,LINK_RULE_VERSION,"2026-10-02T12:00:00Z",asof,0,"LINKED","old_snapshot","r",1,10,"0q",2026,quarter,"q",identifier))
    c.execute("INSERT INTO forecast_estimate VALUES(?,?,?,?,?,?,?,?)",("old_snapshot",0,"e","EPS_ESTIMATE","AVG","NUMERIC_ZERO","0",None))
    fetch={"fetch_id":"unchanged","snapshot_id":"old_snapshot","fetched_at_utc":stamp,"status":"SUCCESS_UNCHANGED"}
    result=reconstruct_fetch(c,fetch)
    assert len(result)==1 and result[0]["target"]==(1,2026,"Q3")
    assert result[0]["link_id"]=="valid"
    assert numeric(result[0],"EPS_ESTIMATE","AVG")==0
    for status in ("TRANSIENT_FAILURE","VALID_NO_DATA"):
        assert reconstruct_fetch(c,{**fetch,"status":status})==[]
    c.close()


def test_fetch_order_keeps_unchanged_and_no_data_excludes_failures():
    rows = [
        {"fetch_order": i, "fetched_at_utc": "2026-09-28T12:00:00Z", "status": status}
        for i, status in [(4, "TRANSIENT_FAILURE"), (3, "VALID_NO_DATA"),
                          (2, "SUCCESS_UNCHANGED"), (1, "SUCCESS_CHANGED")]
    ]
    assert [row["fetch_order"] for row in ordered_observations(rows)] == [1, 2, 3]


def test_frozen_boundaries_before_history_produce_empty_cohort():
    publications = [{"company_id": "1", "fiscal_year": "2026", "fiscal_quarter": "Q3",
                     "research_status": "HEURISTIC_HIGH", "first_full_post_result_trading_date": "2026-09-25"}]
    fetches = [{"company_id": 1, "fetched_at_utc": "2026-09-27T12:00:00Z", "status": "SUCCESS_UNCHANGED"}]
    summary = summarize_forecast_revision_research(publications, fetches)
    assert summary["events_inside_history_window"] == 0
    assert summary["successful_fiscal_fetches"] == 1


def test_exact_timestamp_takes_precedence_over_daily_boundary():
    publications = [{"company_id": "1", "fiscal_year": "2026", "fiscal_quarter": "Q3",
                     "research_status": "EXACT", "canonical_timestamp_utc": "2026-09-28T20:00:00Z",
                     "first_full_post_result_trading_date": "2026-09-29"}]
    fetches = [{"company_id": 1, "fetched_at_utc": stamp, "status": "SUCCESS_CHANGED"}
               for stamp in ["2026-09-28T12:00:00Z", "2026-09-28T21:00:00Z"]]
    assert summarize_forecast_revision_research(publications, fetches)["events_inside_history_window"] == 1


def test_empty_history_has_no_fabricated_window():
    assert summarize_forecast_revision_research([], []) == {
        "history_start": None, "history_end": None, "events_inside_history_window": 0}
