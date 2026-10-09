"""Synthetic operator confirmations only; no real approval is recorded."""
from copy import deepcopy
import ast
import json
from pathlib import Path

import pytest

from rawcandle.fundamentals.admin import publication_observation_approval as review
from rawcandle.fundamentals.admin.policy_reviewed_publication_plan import validate_policy_plan
from rawcandle.fundamentals.publication_event_policy import fingerprint


@pytest.fixture
def prepared():
    states = {(1, 2025, 'Q1'): dict(quarter_id=10, evidence='original', policy_result='UNIQUE',
                                  competing_context=False, source_proofs_valid=True),
              (2, 2025, 'Q1'): dict(quarter_id=20, evidence='other', policy_result='UNIQUE',
                                  competing_context=False, source_proofs_valid=True)}
    proposal = dict(status='PROPOSED', approved=False, runtime_use_permitted=False,
                    baseline_authority_fingerprint='baseline', holds=[{'out_of_scope': True}],
                    proposal_bindings=[dict(natural_key=list(k), observation_fingerprint=str(k),
                                            complete_evidence_fingerprint=v['evidence'],
                                            source_hashes={'source': 'hash'}, source_context_sha256='context')
                                       for k, v in states.items()])
    proposal['artifact_fingerprint'] = fingerprint(proposal)
    def prepare(current=None, supplied=None, generation='synthetic'):
        return review.prepare_candidate(supplied or proposal, proposal_path='synthetic-proposal.json',
                    expected_proposal_fingerprint=proposal['artifact_fingerprint'],
                    baseline_states=states, current_states=states if current is None else current,
                    current_global_state={'generation': generation})
    return proposal, states, prepare


def receipt(candidate, selection, **overrides):
    kwargs = dict(confirmed=True, confirmed_selection_fingerprint=selection['artifact_fingerprint'],
                  operator='SYNTHETIC TEST OPERATOR', note='Synthetic test only', timestamp='2026-10-09T00:00:00Z')
    kwargs.update(overrides)
    return review.make_approval(candidate, candidate, selection, **kwargs)


def test_approve_all_deterministic_and_proposal_is_not_approval(prepared):
    _, _, prepare = prepared
    candidate = prepare()
    assert candidate == prepare()
    assert candidate['status'] == 'AWAITING_OPERATOR_CONFIRMATION'
    assert candidate['approved'] is False
    selection = review.select_cases(candidate, approve_all=True)
    assert selection == review.select_cases(candidate, approve=reversed(selection['approved_keys']))
    assert len(receipt(candidate, selection)['approved_cases']) == 2


def test_partial_exact_selection_omitted_stays_unapproved(prepared):
    candidate = prepared[2]()
    selection = review.select_cases(candidate, approve=[(1, 2025, 'Q1')])
    approval = receipt(candidate, selection)
    assert len(approval['approved_cases']) == 1
    assert selection['unreviewed_keys'] == [[2, 2025, 'Q1']]
    assert approval['approved_cases'][0]['source_hashes'] == {'source': 'hash'}


@pytest.mark.parametrize('action', ['hold', 'reject'])
def test_hold_reject_are_not_approved(prepared, action):
    candidate = prepared[2]()
    selection = review.select_cases(candidate, approve=[(1, 2025, 'Q1')], **{action: [(2, 2025, 'Q1')]})
    assert len(receipt(candidate, selection)['approved_cases']) == 1
    assert selection[('rejected_keys' if action == 'reject' else 'held_keys')] == [[2, 2025, 'Q1']]


@pytest.mark.parametrize('kwargs', [dict(approve=[(3,2025,'Q1')]),
    dict(approve=[(1,2025,'Q1')], hold=[(1,2025,'Q1')]),
    dict(approve_all=True, reject=[(1,2025,'Q1')]),
    dict(approve=[(1,2025,'Q1'),(1,2025,'Q1')])])
def test_invalid_selections_fail(prepared, kwargs):
    with pytest.raises(ValueError):
        review.select_cases(prepared[2](), **kwargs)


def test_changed_proposal_blocks(prepared):
    proposal = deepcopy(prepared[0]);proposal['holds'].append({})
    with pytest.raises(ValueError, match='PROPOSAL_FINGERPRINT_CHANGED'):
        prepared[2](supplied=proposal)


@pytest.mark.parametrize('field,value', [('evidence','changed'), ('quarter_id',999),
    ('competing_context',True), ('source_proofs_valid',False), ('policy_result','REVIEW')])
def test_changed_binding_removed_and_cannot_be_selected(prepared, field, value):
    states = deepcopy(prepared[1]);states[(1,2025,'Q1')][field] = value
    candidate = prepared[2](current=states)
    assert len(candidate['stable_cases']) == len(candidate['stale_cases']) == 1
    assert candidate['stale_cases'][0]['state'] == 'STALE_PROPOSAL_REVIEW_REQUIRED'
    with pytest.raises(ValueError):
        review.select_cases(candidate, approve=[(1,2025,'Q1')])


def test_state_change_during_pause_blocks(prepared):
    before = prepared[2]();after = prepared[2](generation='advanced')
    selection = review.select_cases(before, approve_all=True)
    with pytest.raises(ValueError, match='CURRENT_STATE_CHANGED'):
        review.make_approval(before, after, selection, confirmed=True,
            confirmed_selection_fingerprint=selection['artifact_fingerprint'],
            operator='test', note='test', timestamp='now')


@pytest.mark.parametrize('kwargs', [dict(confirmed=False),dict(confirmed=1),dict(operator=''),
    dict(note=''),dict(confirmed_selection_fingerprint='wrong')])
def test_explicit_exact_confirmation_required(prepared, kwargs):
    candidate = prepared[2]()
    with pytest.raises(ValueError, match='CONFIRMATION_REQUIRED'):
        receipt(candidate, review.select_cases(candidate, approve_all=True), **kwargs)


def test_selection_cannot_be_rebound_after_confirmation(prepared):
    candidate = prepared[2]();all_cases = review.select_cases(candidate, approve_all=True)
    partial = review.select_cases(candidate, approve=[(1,2025,'Q1')])
    with pytest.raises(ValueError, match='CONFIRMATION_REQUIRED'):
        receipt(candidate, partial, confirmed_selection_fingerprint=all_cases['artifact_fingerprint'])


def test_receipt_immutable_non_executing_and_not_a_publication_plan(prepared, tmp_path):
    candidate = prepared[2]();selection = review.select_cases(candidate, approve_all=True)
    approval = receipt(candidate, selection)
    path = review.write_approval(tmp_path, approval)
    assert path.parent == tmp_path / review.APPROVAL_DIRECTORY
    assert json.loads(path.read_text()) == approval
    with pytest.raises(FileExistsError):
        review.write_approval(tmp_path, approval)
    for flag in ['runtime_use_permitted','publication_authorized',
                 'production_apply_authorized','authority_mutation_authorized']:
        assert approval[flag] is False
    with pytest.raises(ValueError):
        validate_policy_plan(approval)
    with pytest.raises(ValueError):
        validate_policy_plan(prepared[0])


def test_docs_destination_cannot_redirect_into_runtime(prepared, tmp_path):
    candidate = prepared[2]();approval = receipt(candidate,review.select_cases(candidate,approve_all=True))
    runtime = tmp_path / 'data';runtime.mkdir()
    (tmp_path / 'docs').symlink_to(runtime, target_is_directory=True)
    with pytest.raises(ValueError, match='DIRECTORY_REDIRECTED'):
        review.write_approval(tmp_path, approval)
    assert not list(runtime.iterdir())


def test_module_has_no_execution_dependencies_or_consumers():
    path = Path(review.__file__);tree = ast.parse(path.read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node,ast.ImportFrom)]
    assert all(not module or not module.startswith('rawcandle.') or
               module == 'rawcandle.fundamentals.publication_event_policy' for module in imports)
    # Inspect only the scheduler/refresh/publication consumers relevant to this boundary.
    consumers = [Path('rawcandle/fundamentals/result_publication.py')]
    consumers += [Path('rawcandle/fundamentals/admin') / name for name in (
        'refresh_scheduler.py', 'refresh_fundamentals.py', 'refresh_production.py',
        'publication_backlog_drain.py', 'policy_reviewed_publication_plan.py',
        'reviewed_publication_plan.py')]
    for source in consumers:
        assert 'publication_observation_approval' not in source.read_text()
        assert 'docs/fundamentals_v4/review_approvals' not in source.read_text()



def test_review_render_preserves_exact_excerpts_hashes_and_grouping():
    bundle = next(Path('docs/fundamentals_v4/review_proposals').glob('historical_publication_review_proposal_v1.ea28*.json'))
    proposal = json.loads(bundle.read_text());case = proposal['proposed_policy_evidence']['cases'][0]
    rendered = review.render_case(case, proposal['proposal_bindings'][0],company_name='Issuer <test>',ticker='TEST')
    assert '<details' in rendered and '<summary>' in rendered
    assert 'Issuer &lt;test&gt;' in rendered
    assert 'FULL_PERIOD_RESULTS' in rendered and 'GAAP_TOTAL' in rendered
    for proof in case['events'][0]['observation']['documents']:
        assert proof['excerpt_sha256'] in rendered
        assert proof['source_sha256'] in rendered
        assert str(proof['locator']['unicode_start']) in rendered
    assert 'proposal pending operator review' in rendered
