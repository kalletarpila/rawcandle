"""Two public SEC contexts; approvals and generations are synthetic and temporary."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import shutil
import sqlite3

import pytest

from rawcandle.fundamentals.admin import approved_publication_evidence as approved
from rawcandle.fundamentals.admin import policy_reviewed_publication_plan as policy
from rawcandle.fundamentals.admin import reviewed_publication_plan as legacy
from rawcandle.fundamentals.admin.publication_observation_approval import prepare_candidate, select_cases, make_approval
from rawcandle.fundamentals.generations import prepare_generation_from_candidates, activate_generation, resolve_active_generation
from rawcandle.fundamentals.publication_event_policy import fingerprint
from rawcandle.fundamentals.schema.result_publication import ensure_result_publication_schema

FIXTURE = Path(__file__).parent / 'fixtures/approved_publication_context_v1.json'


def seal(value, field):
    value[field] = fingerprint({k: v for k, v in value.items() if k != field})
    return value


def insert(db, table, row):
    db.execute(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join('?' for _ in row)})", tuple(row.values()))


def build_handoff(fixture):
    from hashlib import sha256
    fixture=deepcopy(fixture)
    companies=[]
    for company in fixture['companies']:
        raw=json.dumps(dict(company_id=company['company_id'],complete=True,filings=company['filings']),sort_keys=True)
        for snap in fixture['snapshots']:
            if snap['canonical']['company'][0]['company_id']==company['company_id']:
                snap['company_capture_sha256']=sha256(raw.encode()).hexdigest()
        companies.append(dict(company_id=company['company_id'],capture_raw_json=raw,
                              additional_document_texts=company['additional_document_texts']))
    proposal = dict(status='PROPOSED', approved=False, runtime_use_permitted=False,
                    baseline_authority_fingerprint=fingerprint([s['canonical']['authority'] for s in fixture['snapshots']]),
                    proposal_bindings=fixture['bindings'], holds=[],
                    input_fingerprints={'source_files':fixture['snapshots'][0]['reviewed_input_hashes']},
                    proposed_policy_evidence=dict(policy_version=policy.V1,cases=fixture['cases']))
    seal(proposal, 'artifact_fingerprint')
    states = {tuple(b['natural_key']): s for b, s in zip(fixture['bindings'], fixture['snapshots'])}
    candidate = prepare_candidate(proposal, proposal_path='synthetic-review-proposal.json',
        expected_proposal_fingerprint=proposal['artifact_fingerprint'], baseline_states=states,
        current_states=states, current_global_state={'generation': 'synthetic_source'})
    selection = select_cases(candidate, approve_all=True)
    receipt = make_approval(candidate,candidate,selection,confirmed=True,
        confirmed_selection_fingerprint=selection['artifact_fingerprint'], operator='SYNTHETIC TEST ONLY',
        note='Synthetic test confirmation, never real operator approval', timestamp='2026-10-09T00:00:00Z')
    return seal(dict(schema_version=1,input_mode=approved.MODE,proposal=proposal,approval=receipt,
        review_candidate=candidate,approved_snapshots=[dict(natural_key=list(k),snapshot=s) for k,s in states.items()],
        companies=companies,semantic_input_references={k:v for k,v in fixture['snapshots'][0]['reviewed_input_hashes'].items() if Path(k).name!='identity.json'}),
        'handoff_fingerprint')


@pytest.fixture
def setup(tmp_path):
    fixture=json.loads(FIXTURE.read_text());root=tmp_path/'source';root.mkdir();roles={}
    for role in ['provider','canonical','analysis']:
        path=tmp_path/(role+'.db');roles[role]=path
        with sqlite3.connect(path) as db:
            for table, field, pk in [('company','company','company_id'),('company_cik','ciks',None),
                                     ('security','security','security_id'),('v4_quarter','quarter','quarter_id')]:
                rows=[r for s in fixture['snapshots'] for r in s['canonical'][field]]
                columns=list(rows[0])
                def definition(k):
                    t='INTEGER' if isinstance(rows[0][k],int) else 'TEXT'
                    return k+' '+t+(' PRIMARY KEY' if k==pk else '')
                db.execute(f"CREATE TABLE {table} ({','.join(map(definition,columns))})")
                seen=set()
                for row in rows:
                    digest=fingerprint(row)
                    if digest not in seen:insert(db,table,row);seen.add(digest)
            ensure_result_publication_schema(db)
            for s in fixture['snapshots']:
                for row in s['canonical']['authority']:insert(db,'v4_result_publication_authority',row)
            for table in fixture['snapshots'][0]['identity_tables']:
                db.execute('CREATE TABLE '+table+(' (security_id INTEGER)' if table=='provider_security_identity' else ' (company_id INTEGER)'))
            db.execute('CREATE TABLE financial_sentinel(value REAL)');db.execute('INSERT INTO financial_sentinel VALUES(1234.5)')
    manifest=prepare_generation_from_candidates(roles,generation_id='synthetic_source',project_root=root,source='TEST')
    activate_generation(manifest['manifest'],project_root=root)
    handoff=build_handoff(fixture);input_path=tmp_path/'approved_handoff.json';input_path.write_text(json.dumps(handoff))
    allow=tmp_path/'keys.csv'
    with allow.open('w') as f:
        w=csv.writer(f);w.writerow(['company_id','fiscal_year','fiscal_quarter']);w.writerows(b['natural_key'] for b in fixture['bindings'])
    return dict(root=root,handoff=handoff,input=input_path,allow=allow,fixture=fixture,tmp=tmp_path)


def prepare(s, name='plan.json', **kwargs):
    path=s['tmp']/name
    policy.prepare_policy_plan(project_root=s['root'],allowlist_path=s['allow'],output_plan=path,
        policy_evidence_path=None,as_of_date='2026-10-09',retry_days=60,approved_handoff_path=s['input'],
        expected_approval_fingerprint=s['handoff']['approval']['artifact_fingerprint'],**kwargs)
    return json.loads(path.read_text())


def canonical(s):
    return resolve_active_generation(s['root']).role_paths()['canonical']


def revalidate(s, plan):
    return legacy.revalidate_plan_state(plan,resolve_active_generation(s['root']),as_of_date='2026-10-09')


def test_copy_only_production_shaped_smoke(setup, monkeypatch):
    s=setup;before={k:p.read_bytes() for k,p in resolve_active_generation(s['root']).role_paths().items()}
    monkeypatch.setattr(policy,'apply_resolution',lambda *a,**k:pytest.fail('authority writer invoked during prepare'))
    plan=prepare(s)
    assert plan['schema_version']==3 and plan['prepared_key_count']==2
    assert policy.validate_policy_plan(plan)==plan
    revalidate(s,plan)
    assert all(plan[k] is False for k in ['publication_authorized','production_apply_authorized','executed'])
    assert plan['candidate_evidence_provenance']==approved.MODE
    assert before=={k:p.read_bytes() for k,p in resolve_active_generation(s['root']).role_paths().items()}
    with sqlite3.connect(canonical(s)) as db:assert db.execute('SELECT COUNT(*) FROM v4_result_publication_evidence').fetchone()[0]==0
    for case in plan['policy_cases']:
        obs=next(iter(case['observations'].values()));record=plan['frozen_inputs'][case['frozen_input_reference']]
        filing=next(f for f in record['filings'] if f['accession_number']==case['parent_accession'])
        assert fingerprint(filing)==obs['resolver_context_sha256']


def test_matching_stored_evidence_allowed(setup):
    s=setup;plan=prepare(s)
    with sqlite3.connect(canonical(s)) as db:
        for c in s['fixture']['cases']:insert(db,'v4_result_publication_evidence',{**c['events'][0]['evidence'],'disposition':'ACCEPTED','created_at_utc':'2026-10-09T00:00:00Z'})
    revalidate(s,plan)
    assert prepare(s,'matching.json')['prepared_key_count']==2


@pytest.mark.parametrize('mutation', ['conflicting_evidence','quarter','authority','identity','perimeter','provider_identity','fiscal_context'])
def test_live_state_drift_rejects(setup, mutation):
    s=setup;plan=prepare(s)
    with sqlite3.connect(canonical(s)) as db:
        if mutation=='conflicting_evidence':
            row=deepcopy(s['fixture']['cases'][0]['events'][0]['evidence']);row['source_timestamp_utc']='2025-05-07T01:00:00Z';row.update(disposition='ACCEPTED',created_at_utc='2026-10-09T00:00:00Z');insert(db,'v4_result_publication_evidence',row)
        elif mutation=='quarter':db.execute("UPDATE v4_quarter SET period_end='2025-04-01'")
        elif mutation=='authority':
            from rawcandle.fundamentals.result_publication import apply_resolution
            db.row_factory=sqlite3.Row;c=s['fixture']['cases'][0];apply_resolution(db,c['quarter'],[c['events'][0]['evidence']])
        elif mutation=='identity':db.execute("UPDATE company_cik SET status='INACTIVE'")
        elif mutation=='perimeter':db.execute('INSERT INTO fundamentals_economic_structural_event VALUES(22)')
        elif mutation=='provider_identity':db.execute('INSERT INTO provider_security_identity VALUES(?)',(s['fixture']['snapshots'][0]['canonical']['security'][0]['security_id'],))
        else:db.execute("UPDATE v4_quarter SET identity_status='REVIEW'")
    with pytest.raises((ValueError,RuntimeError)):revalidate(s,plan)


def test_generation_drift_rejects(setup):
    s=setup;plan=prepare(s);binding=resolve_active_generation(s['root'])
    copies={role:s['tmp']/('new_'+role+'.db') for role in binding.role_paths()}
    for role,path in copies.items():shutil.copyfile(binding.role_paths()[role],path)
    new=prepare_generation_from_candidates(copies,generation_id='changed_generation',project_root=s['root'],source='TEST');activate_generation(new['manifest'],project_root=s['root'])
    with pytest.raises(RuntimeError,match='GENERATION_DRIFT'):revalidate(s,plan)


@pytest.mark.parametrize('mutation', ['no_receipt','wrong_receipt','unapproved_key','evidence_hash','context','observation','excerpt','schema','policy_input'])
def test_handoff_fail_closed(setup, mutation):
    s=setup;h=deepcopy(s['handoff'])
    if mutation=='no_receipt':h.pop('approval')
    elif mutation=='wrong_receipt':h['approval']['operator_note']='changed'
    elif mutation=='unapproved_key':h['approved_snapshots'][0]['natural_key'][0]=99999
    elif mutation=='evidence_hash':h['proposal']['proposed_policy_evidence']['cases'][0]['events'][0]['evidence']['evidence_hash']='0'*64
    elif mutation=='context':h['companies'][0]['capture_raw_json']+='changed'
    elif mutation=='observation':h['proposal']['proposed_policy_evidence']['cases'][0]['events'][0]['observation']['entity_confidence']='UNPROVEN'
    elif mutation=='excerpt':h['companies'][0]['additional_document_texts'][approved.company_filings(h['companies'][0])[0]['source_reference']]='changed'
    elif mutation=='schema':h['schema_version']=999
    else:h['semantic_input_references']={'unreviewed.json':'0'*64}
    seal(h,'handoff_fingerprint')
    with pytest.raises(ValueError):approved.validate_handoff(h,s['handoff']['approval']['artifact_fingerprint'])


@pytest.mark.parametrize('action',['hold','reject','omit'])
def test_unapproved_hold_reject_membership_cannot_enter(setup,action):
    s=setup;h=deepcopy(s['handoff']);candidate=h['review_candidate'];keys=[b['natural_key'] for b in candidate['stable_cases']]
    selection=select_cases(candidate,approve=keys[:1],**({'hold' if action=='hold' else 'reject':keys[1:]} if action!='omit' else {}))
    h['approval']=make_approval(candidate,candidate,selection,confirmed=True,
        confirmed_selection_fingerprint=selection['artifact_fingerprint'],operator='SYNTHETIC',note='test',timestamp='2026-10-09T00:00:00Z')
    h['approved_snapshots']=h['approved_snapshots'][:1];seal(h,'handoff_fingerprint');s['input'].write_text(json.dumps(h));s['handoff']=h
    with pytest.raises(ValueError,match='UNAPPROVED_KEY'):prepare(s)


def test_explicit_receipt_fingerprint_pin_required(setup):
    s=setup
    with pytest.raises(ValueError,match='RECEIPT_FINGERPRINT_INVALID'):
        approved.validate_handoff(s['handoff'],'0'*64)


def test_normal_preparer_still_requires_stored_evidence(setup):
    s=setup;evidence=s['tmp']/'legacy.json';evidence.write_text(json.dumps(s['handoff']['proposal']['proposed_policy_evidence']))
    with pytest.raises(ValueError,match='PUBLICATION_POLICY_STORED_EVIDENCE_DRIFT'):
        policy.prepare_policy_plan(project_root=s['root'],allowlist_path=s['allow'],output_plan=s['tmp']/'legacy_plan.json',policy_evidence_path=evidence,as_of_date='2026-10-09',retry_days=60)


def test_plan_tampering_even_with_resealed_plan_rejects(setup):
    plan=prepare(setup);plan['policy_cases'][0]['observations'].clear();seal(plan,'plan_fingerprint')
    with pytest.raises(ValueError):policy.validate_policy_plan(plan)


def test_live_semantic_input_drift_rejects(tmp_path):
    path=tmp_path/'reviewed.json';path.write_text('original')
    from hashlib import sha256
    h=dict(semantic_input_references={'logical-input':sha256(path.read_bytes()).hexdigest()},semantic_input_paths={'logical-input':str(path)})
    approved.check_live_inputs(h);path.write_text('changed')
    with pytest.raises(ValueError,match='POLICY_INPUT_CHANGED'):approved.check_live_inputs(h)


def test_future_candidate_execution_uses_frozen_evidence_on_copy_only(setup):
    s=setup;plan=prepare(s);copy=s['tmp']/'candidate.db';shutil.copyfile(canonical(s),copy);before=canonical(s).read_bytes()
    result=policy.run_policy_candidate(copy,plan,as_of_date='2026-10-09')
    assert result['new_verified']==2
    assert canonical(s).read_bytes()==before
    with sqlite3.connect(copy) as db:
        assert db.execute("SELECT COUNT(*) FROM v4_result_publication_authority WHERE status='VERIFIED'").fetchone()[0]==2
        assert db.execute('SELECT value FROM financial_sentinel').fetchone()[0]==1234.5


def test_deterministic_plan_with_frozen_metadata(setup,monkeypatch):
    class StableUUID:hex='synthetic_fixed_id'
    monkeypatch.setattr(policy,'uuid4',lambda:StableUUID())
    monkeypatch.setattr(legacy,'utc_now',lambda:'2026-10-09T00:00:00Z')
    a=prepare(setup,'first.json');b=prepare(setup,'second.json')
    assert a==b
    assert (setup['tmp']/'first.json').read_bytes()==(setup['tmp']/'second.json').read_bytes()


def test_new_competing_filing_rejects(setup):
    s=setup;fixture=deepcopy(s['fixture']);extra=deepcopy(fixture['companies'][0]['filings'][0])
    old=extra['accession_number'].replace('-','');extra['accession_number']='0001739445-25-999999'
    extra['source_reference']=extra['source_reference'].replace(old,extra['accession_number'].replace('-',''))
    extra['acceptance_timestamp_utc']='2025-05-06T21:20:08Z'
    for exhibit in extra['result_exhibits']:
        exhibit['source_reference']=exhibit['source_reference'].replace(old,extra['accession_number'].replace('-',''))
    fixture['companies'][0]['filings'].append(extra);h=build_handoff(fixture)
    with pytest.raises(ValueError,match='COMPETING_OR_INELIGIBLE_CONTEXT'):
        approved.validate_handoff(h,h['approval']['artifact_fingerprint'])


def test_v3_cannot_be_downgraded_to_bypass_mode_checks(setup):
    plan=prepare(setup);plan['schema_version']=2;seal(plan,'plan_fingerprint')
    with pytest.raises(ValueError,match='APPROVED_MODE_VERSION_REQUIRED'):policy.validate_policy_plan(plan)


def test_reviewed_plan_entry_point_forwards_explicit_mode(setup):
    s=setup;path=s['tmp']/'wrapper.json'
    result=legacy.prepare_reviewed_plan(project_root=s['root'],allowlist_path=s['allow'],output_plan=path,
        publication_event_policy=policy.V1,approved_handoff_path=s['input'],
        expected_approval_fingerprint=s['handoff']['approval']['artifact_fingerprint'],as_of_date='2026-10-09')
    assert result['prepared_key_count']==2
    with pytest.raises(ValueError,match='APPROVED_MODE_REQUIRED'):
        legacy.prepare_reviewed_plan(project_root=s['root'],allowlist_path=s['allow'],output_plan=s['tmp']/'bad.json',
                                     approved_handoff_path=s['input'])


def test_extra_stored_candidate_rejects(setup):
    s=setup;plan=prepare(s)
    with sqlite3.connect(canonical(s)) as db:
        e=s['fixture']['cases'][0]['events'][0]['evidence']
        for suffix in ['', '_extra']:
            insert(db,'v4_result_publication_evidence',{**e,'evidence_id':e['evidence_id']+suffix,'evidence_hash':('f'*64 if suffix else e['evidence_hash']),
                'disposition':'ACCEPTED','created_at_utc':'2026-10-09T00:00:00Z'})
    with pytest.raises(ValueError,match='CONFLICTING_STORED_EVIDENCE'):revalidate(s,plan)


def test_exact_identity_capture_is_bound_to_review_and_security_ids(setup):
    from hashlib import sha256
    fixture=deepcopy(setup['fixture']);sid=fixture['snapshots'][0]['canonical']['security'][0]['security_id']
    raw=json.dumps({'provider_security_identity':[{'security_id':sid,'provider':'SHARADAR'},
                                                {'security_id':99999,'provider':'unrelated'}],
                    'structural_events':[]})
    digest=sha256(raw.encode()).hexdigest()
    for snap in fixture['snapshots']:snap['reviewed_input_hashes']={'logical/identity.json':digest}
    handoff=build_handoff(fixture);handoff['identity_input']=dict(source_reference='logical/identity.json',raw_json=raw)
    seal(handoff,'handoff_fingerprint');approved.validate_handoff(handoff,handoff['approval']['artifact_fingerprint'])
    first=handoff['approved_snapshots'][0]
    tables=approved.identity_tables_for_case(handoff,tuple(first['natural_key']),first['snapshot'])
    assert tables['provider_security_identity']==[{'security_id':sid,'provider':'SHARADAR'}]
    handoff['identity_input']['raw_json']+=' ';seal(handoff,'handoff_fingerprint')
    with pytest.raises(ValueError,match='IDENTITY_PROOF_CHANGED'):
        approved.validate_handoff(handoff,handoff['approval']['artifact_fingerprint'])


def test_context_only_quarter_preserved_without_entering_apply_membership(setup):
    s=setup;fixture=deepcopy(s['fixture']);q=deepcopy(fixture['cases'][0]['quarter'])
    q.update(quarter_id=99998,fiscal_quarter='Q3',period_end='2025-09-30',
             first_public_result_date='2025-10-31',source_availability_date='2025-10-31')
    authority=deepcopy(fixture['snapshots'][0]['canonical']['authority'][0])
    authority.update(quarter_id=q['quarter_id'],fiscal_quarter='Q3',status='NOT_FOUND')
    scope=deepcopy(fixture['snapshots'][0]['company_open_scope'][0])
    scope.update(authority);scope.update(period_end=q['period_end'],identity_status='ACCEPTED',
        first_public_result_date='2025-10-31',source_availability_date='2025-10-31',
        context_date='2025-10-31',canonical_quarter_id=q['quarter_id'])
    for snap in fixture['snapshots']:snap['company_open_scope'].append(scope)
    from dataclasses import asdict
    from rawcandle.fundamentals.result_publication import SecFiling
    filing=SecFiling('0001739445-25-999998','8-K','2.02','2025-10-31T20:00:00Z','third.htm',
        'https://www.sec.gov/Archives/edgar/data/1739445/000173944525999998/third.htm',
        'Item 2.02 Results of Operations and Financial Condition. The company announced results for the quarter ended September 30, 2025.')
    fixture['companies'][0]['filings'].append(json.loads(json.dumps(asdict(filing))))
    with sqlite3.connect(canonical(s)) as db:
        insert(db,'v4_quarter',q);insert(db,'v4_result_publication_authority',authority)
    h=build_handoff(fixture);s['handoff']=h;s['input'].write_text(json.dumps(h))
    plan=prepare(s,'full_scope.json');assert plan['prepared_key_count']==2
    context_only=[22,2025,'Q3'];assert context_only not in plan['prepared_keys']
    assert context_only not in plan['source_allowlist_keys']
    revalidate(s,plan)
    case=next(c for c in plan['policy_cases'] if c['fiscal_quarter']=='Q2')
    record=plan['frozen_inputs'][case['frozen_input_reference']]
    assert len(record['quarters'])==3
    narrowed={**record,'quarters':[v for v in record['quarters'] if v['fiscal_quarter']!='Q3']}
    assert policy.reproduce(case,narrowed)['final_result']=='REVIEW'
    assert policy.reproduce(case,record)['final_result']=='UNIQUE'
    candidate=s['tmp']/'full_scope_candidate.db';shutil.copyfile(canonical(s),candidate)
    assert policy.run_policy_candidate(candidate,plan,as_of_date='2026-10-09')['new_verified']==2
    with sqlite3.connect(candidate) as db:
        assert db.execute("SELECT status FROM v4_result_publication_authority WHERE fiscal_quarter='Q3'").fetchone()[0]=='NOT_FOUND'
