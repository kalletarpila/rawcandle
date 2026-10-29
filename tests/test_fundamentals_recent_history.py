"""Terminal-only calendar recency; current reviews and stored evidence survive."""
from copy import deepcopy
from datetime import date, datetime, timezone
import hashlib
import json

import flet as ft
import pytest

from rawcandle.fundamentals.admin.recent_history import history_cutoff, recent_history_visible
from rawcandle.fundamentals.admin.ui_service import FundamentalsAdminUIService
from rawcandle.fundamentals.admin import pb_ownership_review as review
from rawcandle.fundamentals.admin.refresh_review_queue import _connect
from tests.test_fundamentals_review_action_first import provider, ownership, policy, diagnostic, text
from tests.test_fundamentals_operational_presentation import OperationalService, page_for, boundary

TODAY = date(2026,10,29)
OLD = '2026-06-01T12:00:00Z'
RECENT = '2026-09-29T12:00:00Z'


@pytest.fixture(autouse=True)
def fixed_ui_date(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls,tz=None):return datetime(2026,10,29,12,tzinfo=timezone.utc)
    monkeypatch.setattr('rawcandle.fundamentals.admin.recent_history.datetime',Clock)


def published(ticker,when):
    item=ownership(ticker,status='PUBLISHED');item['result']={'publication':{'published_at':when}}
    item['first_seen_at']=OLD
    return item


def superseded(ticker,when):
    item=ownership(ticker,status='SUPERSEDED')
    item.update(history_terminal_event='SUPERSEDED',history_terminal_at_utc=when)
    return item


def resolved(ticker,when):
    item=provider(ticker,status='RESOLVED');item.update(first_seen_at_utc=OLD,resolution_at_utc=when)
    return item


@pytest.mark.parametrize('current,cutoff',[
    (TODAY,date(2026,8,29)),(date(2026,1,31),date(2025,11,30)),
    (date(2025,4,30),date(2025,2,28)),(date(2024,4,30),date(2024,2,29)),
    (date(2026,3,31),date(2026,1,31)),
])
def test_calendar_month_cutoff_clamps_month_end_and_crosses_year(current,cutoff):
    assert history_cutoff(current)==cutoff


@pytest.mark.parametrize('kind,status',[
    ('provider','OPEN'),('provider','REVIEW_REQUIRED'),('provider','WAITING_PROVIDER'),
    ('provider','RETRY_REEVALUATION'),('provider','DEEP_REVIEW'),
    ('ownership','OPEN'),('ownership','HELD'),('ownership','APPROVED'),
    ('ownership','AUTO_CONTINUED'),('ownership','MANUAL_REVIEW'),('ownership','UNKNOWN_CURRENT'),
])
def test_nonterminal_cases_never_disappear_with_old_timestamp(kind,status):
    item=dict(status=status,resolution_at_utc=OLD,result={'publication':{'published_at':OLD}},
              history_terminal_event=status,history_terminal_at_utc=OLD)
    assert recent_history_visible(item,kind=kind,today=TODAY)


@pytest.mark.parametrize('factory,kind',[(published,'ownership'),(superseded,'ownership'),(resolved,'provider')])
@pytest.mark.parametrize('when,visible',[(OLD,False),(RECENT,True),('2026-08-29T00:00:00Z',True),('2026-08-28T23:59:59Z',False)])
def test_terminal_recency_and_inclusive_cutoff(factory,kind,when,visible):
    item=factory('ANY',when);original=deepcopy(item)
    assert recent_history_visible(item,kind=kind,today=TODAY)==visible
    assert item==original


def test_resolution_and_publication_override_observation_or_approval_age():
    item=resolved('ANY',RECENT);item['first_seen_at_utc']='2020-01-01T00:00:00Z'
    assert recent_history_visible(item,kind='provider',today=TODAY)
    item=published('ANY',OLD);item['last_seen_at']=RECENT;item['approval']={'approved_at':RECENT}
    assert not recent_history_visible(item,kind='ownership',today=TODAY)
    item=resolved('ANY',OLD);item['approval_published_at_utc']=RECENT
    assert recent_history_visible(item,kind='provider',today=TODAY)


@pytest.mark.parametrize('when',[None,'','not-a-date','2026-02-30T00:00:00Z','2026-06-01T12:00:00',42])
def test_missing_or_ambiguous_terminal_date_is_not_a_hiding_basis(when):
    assert recent_history_visible(published('ANY',when),kind='ownership',today=TODAY)
    assert recent_history_visible(resolved('ANY',when),kind='provider',today=TODAY)


def test_fallback_must_be_bound_to_the_same_terminal_state():
    item=superseded('ANY',OLD);item['history_terminal_event']='PUBLISHED'
    assert recent_history_visible(item,kind='ownership',today=TODAY)
    item=published('ANY','ambiguous');item.update(history_terminal_event='PUBLISHED',history_terminal_at_utc=OLD)
    assert recent_history_visible(item,kind='ownership',today=TODAY)


def test_timestamp_offsets_use_utc_calendar_days_and_date_only_is_explicit():
    assert not recent_history_visible(published('ANY','2026-08-29T00:30:00+02:00'),kind='ownership',today=TODAY)
    assert recent_history_visible(published('ANY','2026-08-29'),kind='ownership',today=TODAY)


def test_ui_filters_only_terminal_rows_and_keeps_current_counts_deep_and_audit_data():
    open_case=provider('OLD_OPEN');open_case['first_seen_at_utc']=OLD
    review_case=provider('OLD_REVIEW',status='REVIEW_REQUIRED');review_case['first_seen_at_utc']='2026-04-01T00:00:00Z'
    manual=ownership('OLD_MANUAL');manual['first_seen_at']=OLD
    deep=ownership('OLD_DEEP',classification='REVIEW_REQUIRED_IDENTITY_CHANGE');deep['first_seen_at']=OLD
    pending=ownership('OLD_PENDING',status='APPROVED');pending['first_seen_at']=OLD
    diag=diagnostic([policy(manual),policy(deep,'DEEP_REVIEW/BLOCKED')])
    class WithBoundary(OperationalService):
        def list_accounting_boundary_reviews(self):
            item=boundary();item['proposal']['created_at']=OLD;return [item]
    providers=[open_case,review_case,resolved('OLD_DONE',OLD),resolved('RECENT_DONE',RECENT),resolved('UNDATED_DONE',None)]
    owners=[manual,deep,pending,published('OLD_PUB',OLD),published('RECENT_PUB',RECENT),
            superseded('OLD_SUP',OLD),superseded('RECENT_SUP',RECENT),published('UNDATED_PUB',None)]
    original=deepcopy((providers,owners));service=WithBoundary(providers=providers,owners=owners,diag=diag)
    _,c=page_for(service)
    before_counts=c.operational_summary_field.value
    c.review_queue_include_resolved_checkbox.value=True;c.review_queue_include_resolved_checkbox.on_change(None)
    assert c.operational_summary_field.value==before_counts
    assert 'OLD_OPEN' in text(c.review_queue_column) and 'OLD_REVIEW' in text(c.review_queue_column)
    assert 'OLD_MANUAL' in text(c.pb_ownership_column) and 'OLD_PENDING' in text(c.pb_ownership_column)
    assert 'OLD_DEEP' in text(c.deep_review_column) and 'Accounting-boundary review — OPEN' in text(c.deep_review_column)
    for hidden in ('OLD_DONE','OLD_PUB','OLD_SUP'):
        assert hidden not in text(c.content,collapsed=True)
    for kept in ('RECENT_DONE','UNDATED_DONE','RECENT_PUB','RECENT_SUP','UNDATED_PUB'):
        assert kept in text(c.content,collapsed=True)
    provider_history=next(control for control in c.review_queue_column.controls if isinstance(control,ft.ExpansionPanelList)).controls[0]
    owner_history=next(control for control in c.pb_ownership_column.controls if isinstance(control,ft.ExpansionPanelList)).controls[0]
    assert 'visible recent cases (2)' in provider_history.header.title.value
    assert 'visible recent cases (3)' in owner_history.header.title.value
    assert 'last 2 calendar months' in provider_history.header.subtitle.value
    assert not provider_history.expanded and not owner_history.expanded
    assert original==(providers,owners) and not service.actions


def make_queue(tmp_path,events):
    path=tmp_path/'fundamentals_refresh_review_queue.db'
    case=ownership('OLD_SUP',status='SUPERSEDED')
    with _connect(path) as conn:
        conn.executescript(review.SCHEMA)
        conn.execute('INSERT INTO pb_ownership_review VALUES(?,?,?,?,?,?,?,?,?,?,?)',
            (case['case_id'],case['ticker'],1,case['candidate_hash'],json.dumps(case),'SUPERSEDED',OLD,OLD,'run',None,None))
        for event,stamp,evidence in events:
            conn.execute('INSERT INTO refresh_review_queue_audit(ticker,event_type,occurred_at_utc,evidence_json) VALUES(?,?,?,?)',
                (case['ticker'],event,stamp,json.dumps(evidence)))
    return path,case


def test_service_reads_exact_superseded_audit_time_without_queue_writes(tmp_path):
    case_id=ownership('OLD_SUP',status='SUPERSEDED')['case_id']
    path,_=make_queue(tmp_path,[('PB_OWNERSHIP_SUPERSEDED',OLD,{'case_id':case_id}),
        ('PB_OWNERSHIP_CREATED',RECENT,{'case_id':case_id}),('PB_OWNERSHIP_SUPERSEDED',RECENT,{'case_id':'OTHER'})])
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    service=FundamentalsAdminUIService(run_root=tmp_path/'runs',recover_publication_on_startup=False)
    items=service.list_pb_ownership_reviews(include_resolved=True)
    assert items[0]['history_terminal_at_utc']==OLD and items[0]['history_terminal_event']=='SUPERSEDED'
    assert not recent_history_visible(items[0],kind='ownership',today=TODAY)
    assert hashlib.sha256(path.read_bytes()).hexdigest()==before


def test_multiple_distinct_terminal_audit_times_remain_visible(tmp_path):
    case_id=ownership('OLD_SUP',status='SUPERSEDED')['case_id']
    path,_=make_queue(tmp_path,[('PB_OWNERSHIP_SUPERSEDED',stamp,{'case_id':case_id}) for stamp in (OLD,RECENT)])
    service=FundamentalsAdminUIService(run_root=tmp_path/'runs',recover_publication_on_startup=False)
    item=service.list_pb_ownership_reviews(include_resolved=True)[0]
    assert 'history_terminal_at_utc' not in item
    assert recent_history_visible(item,kind='ownership',today=TODAY)
