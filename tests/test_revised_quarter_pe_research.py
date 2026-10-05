"""Focused pure-function checks; no production DBs or external requests."""

import importlib.util
from pathlib import Path
import sys

import pytest

SCRIPT = Path(__file__).resolve().parents[1]/'analysis/research/pe_return_20251003/revised_analysis.py'
sys.path.insert(0,str(SCRIPT.parent))
spec = importlib.util.spec_from_file_location('revised_pe_research',SCRIPT)
research = importlib.util.module_from_spec(spec)
spec.loader.exec_module(research)


def quarter(qid, period='2025-06-30', status='VERIFIED', publication='2025-08-01T20:00:00Z', hint='2025-08-02'):
    return dict(quarter_id=qid,period_end=period,status=status,publication=publication,
                source_availability_date=hint,first_public_result_date=hint)


def test_publication_not_fiscal_end_controls_selection():
    old = quarter(1)
    later = quarter(2,period='2025-09-30',publication='2025-10-20T20:00:00Z',hint='2025-10-21')
    chosen, reason, _ = research.select_quarter([old,later],{})
    assert chosen == old and reason is None


def test_unverified_newer_quarter_blocks_older_fallback():
    old = quarter(1)
    newer = quarter(2,period='2025-07-31',status='UNRESOLVED',publication=None,hint='2025-09-10')
    chosen, reason, blockers = research.select_quarter([old,newer],{})
    assert chosen is None and reason == 'INCOMPLETE_PUBLICATION_AUTHORITY' and blockers == [2]


def test_unverified_later_event_evidence_blocks_fallback():
    old = quarter(1)
    unresolved = quarter(2,period='2025-03-31',status='AMBIGUOUS',publication=None,hint='2025-04-30')
    assert research.select_quarter([old,unresolved],{2:['2025-09-01T12:00:00Z']})[1] == 'INCOMPLETE_PUBLICATION_AUTHORITY'


def test_same_timestamp_conflict_not_arbitrarily_resolved():
    assert research.select_quarter([quarter(1),quarter(2)],{})[1] == 'INCOMPLETE_PUBLICATION_AUTHORITY'


def test_no_verified_publication_does_not_use_provider_date():
    assert research.select_quarter([quarter(1,status='NOT_FOUND',publication=None)],{})[1] == 'NO_ELIGIBLE_PUBLISHED_QUARTER'


def test_eps_basis_requires_currency_and_known_split_compatibility():
    p = dict(fxusd='1',sharefactor='1',eps='1.2',epsusd='1.2',shareswadil='100')
    metadata = {'category':'Domestic Common Stock'}
    assert research.valid_basis(p,metadata,[],'2025-06-30')[0]
    assert not research.valid_basis(p,metadata,['2026-01-01'],'2025-06-30')[0]
    assert not research.valid_basis({**p,'fxusd':'1.3'},metadata,[],'2025-06-30')[0]
    assert not research.valid_basis(p,{'category':'ADR Common Stock Primary Class'},[],'2025-06-30')[0]


def test_primary_ols_uses_unrounded_unmodified_values():
    rows = [{'pe':x,'return':3+2*x} for x in (1.001,2.002,1000.003)]
    result = research.relationship(rows)
    assert result['alpha'] == pytest.approx(3)
    assert result['beta'] == pytest.approx(2)
    assert result['Pearson'] == pytest.approx(1)
    assert result['R2'] == pytest.approx(1)
    assert research.statistics([1,2,1000])['maximum'] == 1000


def test_nonfinite_values_and_degenerate_sample():
    assert research.number('nan') is None
    assert research.number('inf') is None
    assert research.relationship([{'pe':2,'return':3}])['beta'] is None
