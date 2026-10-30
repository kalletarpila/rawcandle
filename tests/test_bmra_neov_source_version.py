"""Current metadata-version drift does not authorize completeness-only repair."""
from copy import deepcopy

import pytest

from rawcandle.fundamentals.admin import legacy_payload_disposition as disposition
from rawcandle.fundamentals.admin import provider_payload as payload
from rawcandle.fundamentals.admin import provider_payload_workflow as workflow
from rawcandle.fundamentals.admin import refresh_fundamentals as refresh
from tests.test_fundamentals_admin_refresh_copy_test import source_row
from tests.test_provider_payload_workflow import setup, base_factory


CASES = (
    ('BMRA','2026-10-15','2026-08-31','2027-Q1','2026-10-16','2026-10-19'),
    ('NEOV','2026-09-23','2026-06-30','2026-Q4','2026-09-23','2026-10-29'),
)


@pytest.mark.parametrize('ticker,day,period,fiscal,stored_stamp,fresh_stamp',CASES)
def test_exact_metadata_cause_remains_unresolved_without_financial_drift(
        ticker,day,period,fiscal,stored_stamp,fresh_stamp):
    raw=source_row(ticker=ticker,date=day,reportperiod=period,fiscalperiod=fiscal,lastupdated=stored_stamp)
    full={**raw,'lastupdated':fresh_stamp,'sharefactor':.5,'equity':120,'equityusd':100}
    old={**refresh.normalize_source_row(raw),'_acquisition_payload':raw}
    new={**refresh.normalize_source_row(full),'_acquisition_payload':full}
    before=deepcopy((old,new))
    result=payload.compare_payload(old,new)
    assert result['reason']=='SOURCE_PAYLOAD_VALUE_REVISION'
    assert result['financial_fields_changed'] is False and result['fields_changed']==[]
    assert set(result['fields_restored'])=={'sharefactor','equity','equityusd'}
    assert {k for k in refresh.REFRESH_REQUEST_FIELDS if old[k]!=new[k]}=={'lastupdated'}
    assert refresh._effective_row(old)==refresh._effective_row(new)
    facts=dict(identity_exact=True,current_source_trusted=True,current_binding_known=True,
        current_incomplete=True,current_healthy=False,exact_repair_available=False,
        native_repair_supported=False,contradictions=[result['reason']],historical_only_count=20,
        historical_no_current_effect_proven=True)
    assert disposition.decide(facts)=='UNRESOLVED'
    assert (old,new)==before


@pytest.mark.parametrize('fresh_stamp',['2026-10-19','2026-10-29'],ids=['BMRA-version-shape','NEOV-version-shape'])
def test_native_proposal_refuses_metadata_plus_completeness_without_any_write(setup,fresh_stamp):
    s=setup;raw={**s.full,'lastupdated':fresh_stamp}
    history=refresh.validate_complete_history([raw],ticker='AAA',dimension='ARQ')
    baseline=workflow.baseline(s.root);queue_before=s.queue.read_bytes()
    with pytest.raises(ValueError,match='PAYLOAD_WORKFLOW_NOT_COMPLETENESS_REPAIR'):
        workflow.proposal(s.root,tuple(s.proposals[0]['source_key']),history,
            fetched_at_utc=s.proposals[0]['source_fetch_timestamp'],source_baseline=baseline)
    assert workflow.baseline(s.root)==baseline and s.queue.read_bytes()==queue_before
