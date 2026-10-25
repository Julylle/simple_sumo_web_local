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


@pytest.mark.parametrize('database_enabled', [False, True])
@pytest.mark.parametrize('resume_ms', [0, 120000])
@pytest.mark.parametrize('stop_at_boundary', [False, True])
@pytest.mark.parametrize('locked_cleanup', [False, True])
def test_worker_saves_each_boundary_before_sensor_update_and_preserves_on_failure(session, tmp_path, monkeypatch, resume_ms, stop_at_boundary, locked_cleanup, database_enabled):
    import sys
    recorder = Mock()
    recorder.names = ['all_state_test']
    monkeypatch.setattr(live, 'open_recorder', Mock(return_value=recorder if database_enabled else None))
    from datetime import datetime, timezone
    from types import SimpleNamespace
    read_times = iter([datetime(2026, 10, 25, 1, minute, tzinfo=timezone.utc) for minute in (0, 1)])
    monkeypatch.setattr(live, 'datetime', SimpleNamespace(now=lambda tz: next(read_times)))
    session['resume_ms'] = resume_ms
    if resume_ms:
        session['times'] = [resume_ms / 3600000]
        session['variables'] = {Q: [500]}
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
        assert ('all_state_test' in kwargs['variables']) == database_enabled
        engine.message_callback(1, '530041 Loaded')
        if resume_ms:
            emit(resume_ms)
        emit(resume_ms+60000)
        return 1
    def send(job, command):
        if command.startswith('save '):
            path = Path(command.split('"')[1])
            path.write_text(f'<systemstate><time>{current}</time></systemstate>')
            engine.message_callback(1, '530045 Saved')
        elif command.startswith('set Sumo__LimitTime '):
            emit(int(command.split()[-1].rstrip(';')))
    original_temporary_directory = live.tempfile.TemporaryDirectory
    temporary_folders = []
    cleanup_calls = []
    def temporary_directory(**kwargs):
        from types import SimpleNamespace
        directory = original_temporary_directory(**kwargs)
        temporary_folders.append(directory)
        def cleanup():
            engine.finish.assert_called_once_with(1)
            engine.cleanup.assert_called_once()
            cleanup_calls.append(directory.name)
            if locked_cleanup:
                raise PermissionError(5, 'DLL still in use')
            directory.cleanup()
        return SimpleNamespace(name=directory.name, cleanup=cleanup)
    monkeypatch.setattr(live.tempfile, 'TemporaryDirectory', temporary_directory)
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
    try:
        live._worker(session)
    finally:
        for directory in temporary_folders:
            directory.cleanup()
    assert len(cleanup_calls) == 1
    if stop_at_boundary:
        assert session['status'] == 'stopped'
        assert reads == 2
    else:
        assert session['status'] == 'failed'
        assert 'Sensor disconnected' in session['error']
    assert cp.checkpoint_info()['simulated_ms'] == resume_ms+120000
    assert len(session['times']) == (3 if resume_ms else 2)
    if resume_ms:
        assert session['variables'][Q][0] == 500
    assert session['sensor_timestamps'][-2:] == ['2026-10-25T01:00:00+00:00', '2026-10-25T01:01:00+00:00']
    assert len(session['sensor_timestamps']) == len(session['times'])
    assert engine.schedule.call_count == 1
    commands = [c.args[1] for c in engine.sendCommand.call_args_list]
    assert sum(c.startswith('save ') for c in commands) == 2
    assert not any(c.startswith('load ') or c == 'maptoic;' for c in commands)
    engine.cleanup.assert_called_once()
    if database_enabled:
        assert recorder.submit.call_count == 2
        assert recorder.flush.call_count == 2
        recorder.close.assert_called_once()



def test_restart_exposes_history_and_csv_without_starting_worker(session, monkeypatch):
    session['times'] = [0, 1/60, 2/60]
    session['variables'] = {Q: [100, 200, 300]}
    cp.save_checkpoint(session, session['model']['state'], 120000)
    monkeypatch.setattr(live, '_session', None)
    with patch.object(live.threading, 'Thread') as worker:
        result = live.snapshot()
        assert result['status'] == 'interrupted'
        assert result['result']['time_h'] == session['times']
        assert result['mapping'] == session['mapping']
        assert result['interval_minutes'] == 1
        assert '300' in live.export_csv()
        worker.assert_not_called()
        resumed = live.resume()
    try:
        assert resumed['id'] == session['id']
        assert resumed['result'] == result['result']
        assert resumed['samples'] == 3
    finally:
        live._session['resume_folder'].cleanup()


def test_old_checkpoint_without_history_remains_resumable(session, monkeypatch):
    cp.save_checkpoint(session, session['model']['state'], 60000)
    target = cp.checkpoint_path()
    with zipfile.ZipFile(target) as archive:
        members = {name: archive.read(name) for name in archive.namelist() if name != 'results.json'}
    with zipfile.ZipFile(target, 'w') as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    assert cp.saved_snapshot()['result'] == {'time_h': [], 'variables': {}}
    metadata, _, folder = cp.restore_checkpoint()
    folder.cleanup()
    assert metadata['simulated_ms'] == 60000


def test_invalid_history_does_not_replace_last_checkpoint(session):
    cp.save_checkpoint(session, session['model']['state'], 60000)
    previous = cp.checkpoint_path().read_bytes()
    session['times'] = [float('nan')]
    with pytest.raises(ValueError):
        cp.save_checkpoint(session, session['model']['state'], 120000)
    assert cp.checkpoint_path().read_bytes() == previous


def test_sensor_timestamps_survive_checkpoint_resume_and_csv(session, monkeypatch):
    session['times'] = [1/60, 2/60]
    session['variables'] = {Q: [100, 200]}
    session['sensor_timestamps'] = ['2026-10-25T01:00:00+00:00', '2026-10-25T01:01:00+00:00']
    cp.save_checkpoint(session, session['model']['state'], 120000)
    monkeypatch.setattr(live, '_session', None)
    assert live.snapshot()['result']['sensor_timestamps'] == session['sensor_timestamps']
    assert 'sensor_read_at_utc' in live.export_csv()
    assert session['sensor_timestamps'][1] in live.export_csv()
    with patch.object(live.threading, 'Thread'):
        resumed = live.resume()
    try:
        assert resumed['result']['sensor_timestamps'] == session['sensor_timestamps']
    finally:
        live._session['resume_folder'].cleanup()
