import sys
import threading
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

import pytest
from test_live_checkpoint import session, Q
from liveSimulation import liveSimulation as live
from services import live_checkpoint as cp
from services.historical_inputs import HistoryWindow, history_request


@pytest.mark.parametrize('completed,stop_in_history', [(0,False),(1,False),(0,True)])
def test_history_runs_without_wait_then_same_job_switches_to_live(session, tmp_path, monkeypatch, completed, stop_in_history):
    plan = history_request('2026-01-01T00:00:00Z','2026-01-01T00:01:30Z',1)
    plan['completed'] = completed
    session['history'] = plan
    session['resume_ms'] = completed * 60000
    if completed:
        session['times'] = [1/60]
        session['variables'] = {Q: [1000]}
        session['sensor_timestamps'] = ['2026-01-01T00:01:00+00:00']
    windows = [HistoryWindow(60000,'2026-01-01T00:01:00+00:00',{Q:1000}),
               HistoryWindow(30000,'2026-01-01T00:01:30+00:00',{Q:2000})][completed:]
    loader = Mock(return_value=windows)
    monkeypatch.setattr(live,'load_history',loader)
    monkeypatch.setattr(live,'open_recorder',Mock(return_value=None))
    monkeypatch.setattr(live,'ROOT',tmp_path)
    package, tool, scheduler, fixed = [ModuleType(n) for n in ('dynamita','dynamita.tool','dynamita.scheduler','real_sim_1202.fixed_dynamic_run')]
    tool.sec=1000;tool.day=86400000;tool.extract_dll_from_project=Mock()
    fixed.OUTPUT_VARIABLES=[];fixed.validate_state_file=lambda path:None
    engine=Mock();scheduler.sumo=engine
    engine.persistent='persistent';engine.isSimFinishedMsg=lambda msg:False
    package.tool=tool;package.scheduler=scheduler
    for module in (package,tool,scheduler,fixed):monkeypatch.setitem(sys.modules,module.__name__,module)
    clock=[0.0]; waits=[]; emissions=[];reads=[]
    monkeypatch.setattr(live.time,'monotonic',lambda:clock[0])
    class Stop(threading.Event):
        def wait(self, timeout=None):
            waits.append(timeout);clock[0]+=timeout
            return self.is_set()
    session['stop']=Stop()
    current=[session['resume_ms']]
    def emit(ms):
        current[0]=ms
        emissions.append((ms,clock[0]))
        engine.datacomm_callback(1,{'Sumo__Time':ms,Q:1000})
        if stop_in_history:session['stop'].set()
    def schedule(model,commands,**kwargs):
        engine.message_callback(1,'530041 Loaded')
        emit(int(next(c for c in commands if c.startswith('set Sumo__LimitTime ')).split()[-1].rstrip(';')))
        return 1
    def send(job,command):
        if command.startswith('save '):
            Path(command.split('"')[1]).write_text('<systemstate><value/></systemstate>')
            engine.message_callback(1,'530045 Saved')
        elif command.startswith('set Sumo__LimitTime '):emit(int(command.split()[-1].rstrip(';')))
    def read(mapping):
        reads.append(clock[0])
        assert cp.checkpoint_info()['history']['completed']==2
        if len(reads)==2:raise RuntimeError('test end: OPC offline')
        return {Q:3000}
    engine.schedule.side_effect=schedule;engine.sendCommand.side_effect=send
    monkeypatch.setattr(live,'_read_model_inputs',read)
    live._worker(session)
    engine.schedule.assert_called_once()
    if stop_in_history:
        assert session['status']=='stopped'
        assert not reads and not waits
        assert cp.checkpoint_info()['history']['completed']==1
    else:
        assert session['mode']=='live'
        assert session['history']['completed']==2
        assert reads==[0,60]
        assert all(t==0 for ms,t in emissions)  # no sleeps during replay or calculation
        assert emissions[-1][0]==150000  # final 30-second history tail + 60-second live step
        assert session['sensor_timestamps'][:2]==['2026-01-01T00:01:00+00:00','2026-01-01T00:01:30+00:00']
        assert 'OPC offline' in session['error']
    assert not any(c.args[1].startswith('load ') for c in engine.sendCommand.call_args_list)
    metadata, _, folder = cp.restore_checkpoint()
    try:assert metadata['history']['completed']==(1 if stop_in_history else 2)
    finally:folder.cleanup()


def test_resume_carries_history_cursor(session, monkeypatch):
    session['history']=history_request('2026-01-01T00:00Z','2026-01-01T00:02Z',1)
    session['history']['completed']=1
    cp.save_checkpoint(session,session['model']['state'],60000)
    monkeypatch.setattr(live,'_session',None)
    with patch.object(live.threading,'Thread'):
        result=live.resume()
    try:
        assert result['mode']=='history'
        assert result['history']['completed']==1
        assert live._session['resume_ms']==60000
    finally:live._session['resume_folder'].cleanup()
