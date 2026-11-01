"""Timer controls never stop/mask the oneshot service; commands are mocked."""
import json
from types import SimpleNamespace

import pytest

from dev_tools import stock_update_scheduler_ui as ui


@pytest.mark.parametrize('enabled',[False,True])
def test_timer_only_change_retains_service_and_schedule_settings(tmp_path,enabled):
    timer=tmp_path/'timer';timer.write_text('[Timer]\nOnCalendar=*-*-* 04:30:00\nPersistent=true\n')
    service=tmp_path/'service';service.write_text('[Service]\nType=oneshot\nExecStart=existing-scheduler\n')
    before=(timer.read_bytes(),service.read_bytes());calls=[]
    def run(cmd,**kwargs):
        calls.append(cmd)
        state='enabled\nActiveState=active' if enabled else 'disabled\nActiveState=inactive'
        return SimpleNamespace(returncode=0,stderr='',stdout='LoadState=loaded\nUnitFileState='+state)
    text=ui.set_systemd_timer_enabled(enabled=enabled,command_runner=run,handoff_marker=tmp_path/'absent')
    assert calls[0]==['systemctl','--user','enable' if enabled else 'disable','--now','stock-update-scheduler.timer']
    assert all('stock-update-scheduler.service' not in cmd for cmd in calls)
    assert (timer.read_bytes(),service.read_bytes())==before
    assert ('restored' if enabled else 'disabled') in text


@pytest.mark.parametrize('marker',[{'enabled':True},{'enabled':None},{}])
def test_restore_refuses_enabled_or_unqualified_handoff(tmp_path,marker):
    path=tmp_path/'handoff.json';path.write_text(json.dumps(marker))
    def forbidden(*a,**k):raise AssertionError('NO_TIMER_MUTATION')
    with pytest.raises(ValueError,match='Disable StockCore'):
        ui.set_systemd_timer_enabled(enabled=True,command_runner=forbidden,handoff_marker=path)


def test_failed_state_verification_cannot_claim_timer_disabled(tmp_path):
    def run(*a,**k):return SimpleNamespace(returncode=0,stderr='',stdout='LoadState=loaded\nUnitFileState=enabled\nActiveState=active')
    with pytest.raises(RuntimeError,match='could not be verified'):
        ui.set_systemd_timer_enabled(enabled=False,command_runner=run,handoff_marker=tmp_path/'absent')


def test_ui_buttons_use_existing_timer_authority_without_changing_config(tmp_path,monkeypatch):
    from tests.test_stock_update_scheduler_ui import _FakePage,_write_config
    config=tmp_path/'scheduler.json';_write_config(config);before=config.read_bytes()
    calls=[]
    monkeypatch.setattr(ui,'read_systemd_user_timer_status',lambda:{'installed':True,'status_summary':'fixture'})
    monkeypatch.setattr(ui,'set_systemd_timer_enabled',lambda **kw:calls.append(kw['enabled']) or 'fixture timer verified')
    page=_FakePage();ui.run_app(page,str(config),defer_initial_load=True)
    assert calls==[]
    page.disable_timer_button.on_click(None);page.restore_timer_button.on_click(None)
    assert calls==[False,True] and config.read_bytes()==before
