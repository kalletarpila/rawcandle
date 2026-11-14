"""One exact candidate confirmation and retained OLD pointer recovery."""
import json
from copy import deepcopy
from pathlib import Path
import shutil
import pytest
from tests import test_fundamentals_universe_reconciliation as f
from rawcandle.fundamentals.admin import universe_reconciliation as r
from rawcandle.fundamentals.admin import publication_journal as j
from rawcandle.fundamentals.generations import resolve_active_generation,prepare_generation_from_candidates,activate_generation

@pytest.mark.parametrize('defect',['missing','wrong_B','wrong_A','review_drift','config_drift'])
def test_confirmation_is_exact_and_fresh(tmp_path,monkeypatch,defect):
 w,d,args=f.setup(tmp_path,monkeypatch);old=resolve_active_generation(w.env.project)
 def confirm(binding):
  if defect=='wrong_B':binding['candidate']['generation_id']='other'
  if defect=='wrong_A':binding['old']['generation_id']='other'
  if defect=='review_drift':monkeypatch.setattr(r.core,'_queue_binding',lambda env:'changed review authority')
  if defect=='config_drift':monkeypatch.setattr(w.env,'config',lambda:dict(route='CHANGED',mode='FULL_WORKFLOW',ownership=False))
  return binding
 args['confirm_candidate']=None if defect=='missing' else confirm
 result=r.run_reconciliation(w.env,d,**args,stop_after='publish')
 assert result['outcome']=='BLOCKED',result
 assert resolve_active_generation(w.env.project).generation_id==old.generation_id


def test_retained_old_has_no_duplicate_files_and_completion_does_not_recover(tmp_path,monkeypatch):
 w,d,args=f.setup(tmp_path,monkeypatch);old=resolve_active_generation(w.env.project)
 result=r.run_reconciliation(w.env,d,**args,stop_after='publish')
 assert result['outcome']=='COMPLETED',result
 journal=j.load_journal(w.env.journal)
 for role,record in journal['roles'].items():
  assert Path(record['backup_path'])==old.role_paths()[role]
 assert not list((w.env.root/'backups').rglob('*.db'))
 before=resolve_active_generation(w.env.project).generation_id
 assert j.recover_if_required(w.env.journal)['recovered'] is False
 assert resolve_active_generation(w.env.project).generation_id==before
 assert all(p.exists() for p in old.role_paths().values())

@pytest.mark.parametrize('defect',['missing','corrupt'])
def test_invalid_old_is_not_a_no_copy_fallback(tmp_path,monkeypatch,defect):
 w,d,args=f.setup(tmp_path,monkeypatch);old=resolve_active_generation(w.env.project)
 p=old.role_paths()['provider']
 if defect=='missing':p.unlink()
 else:p.write_bytes(b'corrupt')
 if defect=='missing':
  from rawcandle.fundamentals.generations import FundamentalsGenerationError
  with pytest.raises(FundamentalsGenerationError):r.run_reconciliation(w.env,d,**args,stop_after='publish')
 else:
  result=r.run_reconciliation(w.env,d,**args,stop_after='publish')
  assert result['outcome']=='BLOCKED',result
 assert json.loads((w.env.project/'data/fundamentals_active_generation.json').read_text())['generation_id']==old.generation_id


def test_recovery_never_overwrites_unexpected_newer_generation(tmp_path,monkeypatch):
 w,d,args=f.setup(tmp_path,monkeypatch)
 with pytest.raises(r.native.SimulatedPublicationCrash):
  r.run_reconciliation(w.env,d,**args,stop_after='publish',inject_crash='AFTER_ACTIVATION')
 b=resolve_active_generation(w.env.project);lane=w.env.root/'newer';lane.mkdir()
 candidates={}
 for role,p in b.role_paths().items():
  dest=lane/(role+'.db');shutil.copyfile(p,dest);candidates[role]=dest
 prepared=prepare_generation_from_candidates(candidates,generation_id='newer_C',project_root=w.env.project,source='fixture')
 activate_generation(prepared['manifest'],project_root=w.env.project,expected_active_generation_id=b.generation_id)
 with pytest.raises(j.PublicationRecoveryError):
  with w.env.writer_lock():j.recover_if_required(w.env.journal)
 assert resolve_active_generation(w.env.project).generation_id=='newer_C'

@pytest.mark.parametrize('kind',['hash','bytes'])
def test_confirmation_cannot_substitute_candidate_content(tmp_path,monkeypatch,kind):
 w,d,args=f.setup(tmp_path,monkeypatch)
 def confirm(binding):
  if kind=='hash':binding['candidate']['role_verification']['provider']['sha256']='0'*64
  else:
   p=w.env.project/'data/fundamentals_generations'/binding['candidate']['generation_id']/binding['candidate']['roles']['provider']
   p.write_bytes(b'changed after verification')
  return binding
 args['confirm_candidate']=confirm
 result=r.run_reconciliation(w.env,d,**args,stop_after='publish')
 assert result['outcome']=='BLOCKED',result
 assert resolve_active_generation(w.env.project).generation_id=='old'


def test_legacy_role_replacement_restores_verified_physical_copies(tmp_path):
 from tests.test_fundamentals_generations import _flat_fixture,_database,_value
 from rawcandle.fundamentals.admin.batch_add_tickers import BatchAddTickerPaths
 from rawcandle.fundamentals.generations import legacy_role_paths
 _flat_fixture(tmp_path);old=legacy_role_paths(tmp_path)
 paths=BatchAddTickerPaths(old['provider'],old['canonical'],old['analysis'],tmp_path/'market.db',tmp_path/'tax.db')
 backups=r.native._verified_backups(paths,tmp_path/'backups')
 candidates={}
 for role in old:
  p=tmp_path/'temp/legacy-run'/ (role+'.db');_database(p,'new');candidates[role]=p
 records=r.native._candidate_manifest(candidates,backups)
 journal_path=tmp_path/'legacy-journal.json'
 journal=j.prepare_journal(path=journal_path,operation_type='fixture',run_id='legacy-run',preview_run_id=None,test_run_id=None,refresh_set_fingerprint='f'*64,old_source_watermark=None,new_source_watermark='',source_schema_fingerprint='fixture',roles=records)
 for role,p in old.items():
  assert Path(backups[role]['backup'])!=p
  p.unlink();_database(p,'changed')
 recovered=j.restore_old_generation(journal,journal_path=journal_path)
 assert recovered['status']=='RECOVERED'
 assert all(_value(p)=='old' for p in old.values())
 assert all(Path(v['backup']).exists() for v in backups.values())
