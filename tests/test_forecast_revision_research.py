from rawcandle.research.forecast_revision_research import ordered_observations, summarize_forecast_revision_research
from rawcandle.research.forecast_revision_research import analyze_event, classify_fetch, numeric, revision, reconstruct_fetch
from rawcandle.forecasts.fiscal_linker import LINK_RULE_VERSION
from rawcandle.forecasts.identity import IDENTITY_RULE_VERSION
from rawcandle.research.forecast_revision_research import next_fiscal_target
from rawcandle.research.forecast_revision_research import transition_class_counts
import sqlite3
import pytest


def test_mixed_missing_trading_calendar_counts_are_json_serializable():
    import json
    counts = transition_class_counts([
        {"transition_trading_day_class": None},
        {"transition_trading_day_class": "NOT_YET_OBSERVED"},
        {},
    ])
    assert counts == {"UNAVAILABLE": 2, "NOT_YET_OBSERVED": 1}
    assert json.loads(json.dumps(counts, sort_keys=True)) == counts


def test_linked_future_target_without_canonical_row_is_usable():
    key = (1, 2026, "Q3")
    rows = [observation(1, "2026-09-29T12:00:00Z", "+1q", "Q4"),
            observation(2, "2026-09-30T12:00:00Z", "0q", "Q4", 2)]
    target = next_fiscal_target([key], key, rows)
    assert target == (1, 2026, "Q4")
    assert analyze_event(event(), rows, target, [])["eps_revision_abs"] == 1


def test_future_target_requires_exact_linked_identity_and_canonical_result():
    key = (1, 2026, "Q3")
    wrong = [observation(1, "2026-09-29T12:00:00Z", "+1q", "Q1")]
    assert next_fiscal_target([key], key, wrong) is None
    assert next_fiscal_target([], key, wrong) is None
    assert next_fiscal_target([key], key, []) is None


def test_future_target_does_not_skip_canonical_gap_and_handles_rollover():
    key = (1, 2026, "Q3")
    rows = [observation(1, "2026-09-29T12:00:00Z", "+1q", "Q4")]
    assert next_fiscal_target([key, (1, 2027, "Q1")], key, rows) is None
    rollover = dict(rows[0], target=(1, 2027, "Q1"))
    assert next_fiscal_target([(1, 2026, "Q4")], (1, 2026, "Q4"), [rollover]) == (1, 2027, "Q1")


def event(status="EXACT"):
    return {"company_id": "1", "ticker": "TEST", "fiscal_year": "2026", "fiscal_quarter": "Q3",
            "research_status": status, "canonical_timestamp_utc": "2026-09-29T20:00:00Z",
            "research_publication_date": "2026-09-29", "first_full_post_result_trading_date": "2026-09-30"}


def observation(order, stamp, horizon, target, value=1.0):
    return {"company_id": 1, "fetch_order": order, "fetch_id": str(order), "snapshot_id": "snapshot",
            "link_id": str(order), "resolution_id": str(order), "fetched_at_utc": stamp,
            "horizon": horizon, "provider_end_date": {"Q1": "2026-03-31", "Q3": "2026-09-30", "Q4": "2026-12-31"}[target], "target": (1,2026,target), "states": {
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
      CREATE TABLE forecast_estimate(snapshot_id,occurrence_index,estimate_id,metric,statistic,value_state,value_numeric,value_text,provider_end_date TEXT DEFAULT '2026-09-30');
    """)
    stamp="2026-09-29T12:00:00Z"
    c.execute("INSERT INTO forecast_snapshot VALUES(?,?)",("old_snapshot","FISCAL_ESTIMATE"))
    c.execute("INSERT INTO forecast_identity_resolution VALUES(?,?,?,?,?,?,?)",("r","unchanged",IDENTITY_RULE_VERSION,"RESOLVED",1,10,stamp))
    for mode,asof,quarter,identifier in (("AS_KNOWN",stamp,"Q3","valid"),("CURRENT_RECONCILED",stamp,"Q4","reconciled"),("AS_KNOWN","2026-10-01T12:00:00Z","Q4","future")):
        c.execute("INSERT INTO forecast_fiscal_link VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",("unchanged",mode,LINK_RULE_VERSION,"2026-10-02T12:00:00Z",asof,0,"LINKED","old_snapshot","r",1,10,"0q",2026,quarter,"q",identifier))
    c.execute("INSERT INTO forecast_estimate(snapshot_id,occurrence_index,estimate_id,metric,statistic,value_state,value_numeric,value_text) VALUES(?,?,?,?,?,?,?,?)",("old_snapshot",0,"e","EPS_ESTIMATE","AVG","NUMERIC_ZERO","0",None))
    fetch={"fetch_id":"unchanged","snapshot_id":"old_snapshot","fetched_at_utc":stamp,"status":"SUCCESS_UNCHANGED"}
    result=reconstruct_fetch(c,fetch)
    assert len(result)==1 and result[0]["target"]==(1,2026,"Q3")
    assert result[0]["link_id"]=="valid"
    assert result[0]["provider_end_date"] == "2026-09-30"
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


@pytest.mark.parametrize('pre_date,post_date,status', [
    ('2026-12-31', '2026-12-31', 'VALIDATED_PROVIDER_DATE_MATCH'),
    ('2026-12-31', '2026-09-30', 'REJECT_PROVIDER_DATE_MISMATCH'),
    (None, '2026-12-31', 'PROVISIONAL_PROVIDER_DATE_MISSING'),
    ('2026-12-31', None, 'PROVISIONAL_PROVIDER_DATE_MISSING'),
    (None, None, 'PROVISIONAL_PROVIDER_DATE_MISSING'),
])
def test_pair_date_quality_controls_metrics(pre_date, post_date, status):
    rows = [dict(observation(1, '2026-09-29T12:00:00Z', '+1q', 'Q4'), provider_end_date=pre_date),
            dict(observation(2, '2026-09-30T12:00:00Z', '0q', 'Q4', 2), provider_end_date=post_date)]
    actual = analyze_event(event(), rows, (1, 2026, 'Q4'), [])
    approved = status == 'VALIDATED_PROVIDER_DATE_MATCH'
    assert actual['pair_validation_status'] == status
    assert actual['nominal_candidate_pair']
    assert actual['comparable'] == approved
    assert actual['pre_eps_avg'] == 1 and actual['post_eps_avg'] == 2
    assert actual['eps_revision_abs'] == (1 if approved else None)
    assert actual['eps_analyst_count_change'] == (1 if approved else None)
    assert actual['provider_date_match'] is (True if approved else False if 'MISMATCH' in status else None)


def air_fixture():
    e = dict(event(), ticker='AIR', fiscal_year='2027', fiscal_quarter='Q1',
             canonical_timestamp_utc='2026-09-28T20:58:22Z', research_publication_date='2026-09-28')
    def obs(order, time, horizon, quarter, end):
        return dict(observation(order, time, horizon, 'Q3'), target=(1, 2027, quarter),
                    provider_end_date=end, fetch_id=time)
    rows = [obs(1, '2026-09-28T11:02:21.626036Z', '0q', 'Q1', '2026-08-31'),
            obs(1, '2026-09-28T11:02:21.626036Z', '+1q', 'Q2', '2026-11-30'),
            # Provider rolls while AS_KNOWN target is still Q1.
            obs(2, '2026-09-29T11:02:26.051928Z', '0q', 'Q1', '2026-11-30'),
            obs(3, '2026-10-01T11:03:12.935188Z', '0q', 'Q1', '2026-11-30'),
            obs(4, '2026-10-02T11:03:13.828041Z', '0q', 'Q2', '2026-11-30')]
    return e, rows


def test_air_provider_timing_precedes_link_relabel_and_preserves_valid_pair():
    e, rows = air_fixture()
    actual = analyze_event(e, rows, (1, 2027, 'Q2'), [])
    assert actual['pair_validation_status'] == 'VALIDATED_PROVIDER_DATE_MATCH'
    assert actual['comparable']
    assert actual['provider_rollover_status'] == 'FORWARD_MATCHED_PLUS1Q'
    assert actual['provider_plus1q_matches_new0q'] is True
    assert actual['provider_old_0q_end_date'] == '2026-08-31'
    assert actual['provider_new_0q_end_date'] == '2026-11-30'
    assert actual['provider_rollover_last_old_fetch_at'] == '2026-09-28T11:02:21.626036Z'
    assert actual['new_0q_first_seen_at_utc'] == '2026-09-29T11:02:26.051928Z'
    assert actual['linker_transition_at'] == '2026-10-02T11:03:13.828041Z'
    assert actual['timing_basis'] == 'PROVIDER_0Q_ROLLOVER'
    assert actual['hours_publication_to_new_0q_first_seen'] == pytest.approx(14.0677922022)
    assert actual == analyze_event(e, list(reversed(rows)), (1, 2027, 'Q2'), [])


@pytest.mark.parametrize('ticker,quarter', [('MU', 'Q1'), ('NKE', 'Q2')])
def test_mu_nke_rejected_while_earlier_forward_rollover_survives(ticker, quarter):
    import copy
    e, rows = air_fixture()
    e['ticker'] = ticker
    target = (1, 2027, quarter)
    if ticker == 'MU':
        e.update(fiscal_year='2026', fiscal_quarter='Q4')
        for row in rows:
            if row['horizon'] == '0q':
                row['target'] = (1, 2026, 'Q4')
    rows[1]['target'] = target
    rows[-1].update(target=target, provider_end_date='2026-08-31')
    untouched = copy.deepcopy(rows)
    actual = analyze_event(e, rows, target, [])
    assert actual['pair_validation_status'] == 'REJECT_PROVIDER_DATE_MISMATCH'
    assert actual['nominal_candidate_pair'] and not actual['comparable']
    assert actual['eps_revision_abs'] is None
    assert actual['provider_rollover_status'] == 'FORWARD_MATCHED_PLUS1Q'
    assert actual['provider_forward_episode_count'] == 1
    assert actual['provider_backward_episode_count'] == 1
    assert actual['provider_rollover_first_new_fetch_at'] == rows[2]['fetched_at_utc']
    assert rows == untouched


def test_link_identity_change_with_unchanged_provider_date_is_diagnostic_only():
    rows = [dict(observation(1, '2026-09-29T12:00:00Z', '0q', 'Q3'), provider_end_date='2026-12-31'),
            observation(2, '2026-09-29T12:00:00Z', '+1q', 'Q4'),
            observation(3, '2026-09-30T12:00:00Z', '0q', 'Q4')]
    actual = analyze_event(event(), rows, (1, 2026, 'Q4'), [])
    assert actual['provider_rollover_status'] == 'NO_OBSERVED_ROLLOVER'
    assert actual['provider_rollover_first_new_fetch_at'] is None
    assert actual['linker_transition_at'] == '2026-09-30T12:00:00Z'
    assert actual['timing_basis'] == 'LINK_IDENTITY_CHANGE_ONLY'
    assert actual['provider_forward_episode_count'] == 0


def test_backward_provider_date_is_not_forward_rollover():
    from rawcandle.research.forecast_revision_research import provider_rollovers
    rows = [observation(1, '2026-09-29T12:00:00Z', '0q', 'Q4'),
            observation(2, '2026-09-30T12:00:00Z', '0q', 'Q3')]
    assert [x['status'] for x in provider_rollovers(rows)] == ['BACKWARD_DATE_REGRESSION']


def test_rollover_requires_immediately_preceding_plus1q_not_older_match():
    from rawcandle.research.forecast_revision_research import provider_rollovers
    rows = [observation(1, '2026-09-28T12:00:00Z', '0q', 'Q3'),
            dict(observation(1, '2026-09-28T12:00:00Z', '+1q', 'Q4'), fetch_id='1'),
            observation(2, '2026-09-29T12:00:00Z', '0q', 'Q3'),
            observation(3, '2026-09-30T12:00:00Z', '0q', 'Q4')]
    assert [x['status'] for x in provider_rollovers(rows)] == ['FORWARD_NO_PLUS1Q_MATCH']


def test_missing_provider_date_breaks_rollover_continuity():
    from rawcandle.research.forecast_revision_research import provider_rollovers
    rows = [observation(1, '2026-09-28T12:00:00Z', '0q', 'Q3'),
            dict(observation(2, '2026-09-29T12:00:00Z', '0q', 'Q3'), provider_end_date=None),
            observation(3, '2026-09-30T12:00:00Z', '0q', 'Q4')]
    assert provider_rollovers(rows) == []


def test_matching_provider_dates_cannot_replace_fiscal_identity():
    from rawcandle.research.forecast_revision_research import validate_pair
    a = observation(1, '2026-09-29T12:00:00Z', '+1q', 'Q4')
    b = dict(observation(2, '2026-09-30T12:00:00Z', '0q', 'Q3'),
             provider_end_date=a['provider_end_date'])
    assert validate_pair(a, b) == 'NO_PAIR'


def test_research_build_preserves_source_hashes_and_history_bounds(tmp_path, monkeypatch):
    import csv
    from rawcandle.forecasts.schema import migrate_forecasts_db
    from rawcandle.research import forecast_revision_research as research
    forecasts, canonical, ohlc = [tmp_path / (name + '.db') for name in ('forecast', 'canonical', 'ohlc')]
    migrate_forecasts_db(forecasts)
    with sqlite3.connect(forecasts) as c:
        c.execute("INSERT INTO forecast_run(run_id,provider,adapter,adapter_version,started_at_utc,status) "
                  "VALUES('run','YAHOO_FINANCE','test','1','2026-09-28T12:00:00Z','SUCCESS')")
        for day in ('2026-09-28', '2026-09-30', '2026-10-14'):
            c.execute("INSERT INTO forecast_fetch(fetch_id,run_id,provider,adapter,adapter_version,company_id,"
                      "identity_key,provider_symbol,forecast_family,requested_at_utc,fetched_at_utc,status,attempt_count) "
                      "VALUES(?,'run','YAHOO_FINANCE','test','1',1,'company:1','TEST','FISCAL_ESTIMATE',"
                      "?,?,'VALID_NO_DATA',1)", (day, day+'T12:00:00Z', day+'T12:00:00Z'))
    with sqlite3.connect(canonical) as c:
        c.execute('CREATE TABLE v4_quarter(company_id,fiscal_year,fiscal_quarter,period_end)')
        c.execute("INSERT INTO v4_quarter VALUES(1,2026,'Q3','2026-09-30')")
    with sqlite3.connect(ohlc) as c:
        c.execute('CREATE TABLE osakedata(osake,pvm)')
    publication = tmp_path / 'publication.csv'
    with publication.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(event()))
        w.writeheader()
        w.writerow(event())
    monkeypatch.setattr(research, 'validate_publication_input', lambda *a: None)
    before = {str(p): research.sha256(p) for p in (forecasts, canonical, ohlc)}
    result = research.build_forecast_revision_research(publication, tmp_path / 'pub.json', forecasts,
        canonical, ohlc, tmp_path / 'out.csv', tmp_path / 'out.json',
        history_start_utc='2026-09-27T16:27:26.679445Z', history_end_utc='2026-10-13T12:01:55.287946Z')
    assert result['output_rows'] == 1
    assert result['availability']['history_end'] == '2026-09-30T12:00:00Z'
    assert result['availability']['valid_no_data_fiscal_fetches'] == 2
    assert result['observations']['pair_validation_counts'] == {'NO_PAIR': 1}
    assert result['source_sha256_before'] == result['source_sha256_after']
    assert before == {str(p): research.sha256(p) for p in (forecasts, canonical, ohlc)}
    assert result['history_bounds']['end_utc'] == '2026-10-13T12:01:55.287946Z'
    # A real concurrent writer must fail closed, not be hidden by the wrapper.
    real_sha = research.sha256
    calls = {}
    def drifted_sha(path):
        calls[path] = calls.get(path, 0) + 1
        return 'changed' if path == ohlc and calls[path] > 1 else real_sha(path)
    monkeypatch.setattr(research, 'sha256', drifted_sha)
    with pytest.raises(ValueError, match='SOURCE_DATABASE_CHANGED_DURING_RESEARCH'):
        research.build_forecast_revision_research(publication, tmp_path / 'pub.json', forecasts,
            canonical, ohlc, tmp_path / 'rejected.csv', tmp_path / 'rejected.json')
    assert not (tmp_path / 'rejected.csv').exists()
