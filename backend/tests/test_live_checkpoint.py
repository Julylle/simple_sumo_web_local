import json
import threading
import zipfile
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch

import pytest

from services import live_checkpoint as cp
from liveSimulation import liveSimulation as live

Q = 'Sumo__Plant__Influent__param__Q'


@pytest.fixture
def session(tmp_path, monkeypatch):
    monkeypatch.setenv('SUMO_LIVE_STATE_DIR', str(tmp_path / 'checkpoints'))
    runtime = tmp_path / 'real_sim_1202'
    (runtime / 'dynamita').mkdir(parents=True)
    project = tmp_path / 'model.sumo'
    state = tmp_path / 'state.xml'
    state.write_text('<systemstate><state/></systemstate>')
    with zipfile.ZipFile(project, 'w') as archive:
        archive.writestr('variables.var', f'0\t{Q}\tREAL\tm3/d\tParameter')
    return {'id':'test-run', 'status':'starting', 'phase':'initializing', 'error':None,
            'sim_ms':0, 'resume_ms':0, 'times':[], 'variables':{},
            'mapping':{Q:'tag'}, 'interval':60, 'stop':threading.Event(),
            'model_id':'uploaded', 'model':{'project':project,'state':state,'name':'custom.sumo'}}


def test_latest_replaces_previous_and_restores_without_original_files(session):
    cp.save_checkpoint(session, session['model']['state'], 60000)
    cp.save_checkpoint(session, session['model']['state'], 120000)
    assert [p.name for p in cp.checkpoint_path().parent.iterdir()] == ['latest_checkpoint.zip']
    session['model']['project'].unlink()
    session['model']['state'].unlink()
    metadata, model, folder = cp.restore_checkpoint()
    try:
        assert metadata['simulated_ms'] == 120000
        assert metadata['mapping'] == {Q:'tag'}
        assert zipfile.is_zipfile(model['project'])
        assert model['state'].read_text() == '<systemstate><state/></systemstate>'
    finally:
        folder.cleanup()


@pytest.mark.parametrize('failure', ['replace', 'invalid_xml'])
def test_failed_save_preserves_last_complete_checkpoint(session, failure):
    cp.save_checkpoint(session, session['model']['state'], 60000)
    previous = cp.checkpoint_path().read_bytes()
    if failure == 'replace':
        with patch.object(cp.os, 'replace', side_effect=OSError('Disk failure')), pytest.raises(OSError):
            cp.save_checkpoint(session, session['model']['state'], 120000)
    else:
        session['model']['state'].write_text('<broken')
        with pytest.raises(Exception):
            cp.save_checkpoint(session, session['model']['state'], 120000)
    assert cp.checkpoint_path().read_bytes() == previous
    assert cp.checkpoint_info()['simulated_ms'] == 60000
    assert not cp.checkpoint_path().with_suffix('.pending').exists()


def test_restart_resume_uses_checkpoint_time_mapping_and_model(session, monkeypatch):
    cp.save_checkpoint(session, session['model']['state'], 120000)
    monkeypatch.setattr(live, '_session', None)
    with patch.object(live.threading, 'Thread'):
        result = live.resume()
    try:
        assert result['model_id'] == 'checkpoint'
        assert live._session['resume_ms'] == 120000
        assert live._session['interval'] == 60
        assert live._session['mapping'] == {Q:'tag'}
        assert live._session['model']['project'].exists()
        with pytest.raises(RuntimeError, match='already active'):
            live.resume()
    finally:
        live._session['resume_folder'].cleanup()


@pytest.mark.parametrize('resume_ms', [0, 120000])
@pytest.mark.parametrize('stop_at_boundary', [False, True])
def test_worker_saves_each_boundary_before_sensor_update_and_preserves_on_failure(session, tmp_path, monkeypatch, resume_ms, stop_at_boundary):
    import sys
    session['resume_ms'] = resume_ms
    monkeypatch.setattr(live, 'ROOT', tmp_path)
    package = ModuleType('dynamita')
    tool = ModuleType('dynamita.tool')
    scheduler = ModuleType('dynamita.scheduler')
    fixed = ModuleType('real_sim_1202.fixed_dynamic_run')
    fixed.OUTPUT_VARIABLES = []
    fixed.validate_state_file = lambda p: None
    tool.sec = 1000
    tool.day = 86400000
    tool.extract_dll_from_project = Mock()
    engine = Mock()
    scheduler.sumo = engine
    engine.persistent = 'persistent'
    engine.isSimFinishedMsg = lambda msg: msg.startswith('530004')
    package.tool = tool
    package.scheduler = scheduler
    for name, module in [('dynamita',package),('dynamita.tool',tool),('dynamita.scheduler',scheduler),
                         ('real_sim_1202.fixed_dynamic_run',fixed)]:
        monkeypatch.setitem(sys.modules, name, module)
    clock = iter(range(0,1000000,1000))
    monkeypatch.setattr(live.time, 'monotonic', lambda: next(clock))
    current = resume_ms
    def emit(ms):
        nonlocal current
        current = ms
        engine.datacomm_callback(1, {'Sumo__Time':ms, Q:1000})
        if stop_at_boundary and ms == resume_ms+120000:
            session['stop'].set()
    def schedule(model, commands, **kwargs):
        assert f'set Sumo__Time {resume_ms};' in commands
        assert f'set Sumo__LimitTime {resume_ms+60000};' in commands
        assert len([c for c in commands if c.startswith('load ')]) == 1
        engine.message_callback(1, '530041 Loaded')
        emit(resume_ms+60000)
        return 1
    def send(job, command):
        if command.startswith('save '):
            path = Path(command.split('"')[1])
            path.write_text(f'<systemstate><time>{current}</time></systemstate>')
            engine.message_callback(1, '530045 Saved')
        elif command.startswith('set Sumo__LimitTime '):
            emit(int(command.split()[-1].rstrip(';')))
    engine.schedule.side_effect = schedule
    engine.sendCommand.side_effect = send
    reads = 0
    def read(mapping):
        nonlocal reads
        reads += 1
        if reads > 1:
            assert cp.checkpoint_info()['simulated_ms'] == resume_ms+(reads-1)*60000
        if reads == 3:
            raise RuntimeError('Sensor disconnected')
        return {Q:1000*reads}
    monkeypatch.setattr(live, '_read_model_inputs', read)
    live._worker(session)
    if stop_at_boundary:
        assert session['status'] == 'stopped'
        assert reads == 2
    else:
        assert session['status'] == 'failed'
        assert 'Sensor disconnected' in session['error']
    assert cp.checkpoint_info()['simulated_ms'] == resume_ms+120000
    assert engine.schedule.call_count == 1
    commands = [c.args[1] for c in engine.sendCommand.call_args_list]
    assert sum(c.startswith('save ') for c in commands) == 2
    assert not any(c.startswith('load ') or c == 'maptoic;' for c in commands)
    engine.cleanup.assert_called_once()
