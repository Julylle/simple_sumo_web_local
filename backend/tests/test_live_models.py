import io
import zipfile
from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from services import live_models
from api.live_sumo import router, LiveStart
from liveSimulation import liveSimulation

Q = 'Sumo__Plant__Influent__param__Q'
STATE = b'<systemstate><state name="test"/></systemstate>'


def project_bytes():
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        archive.writestr('variables.var', f'0\t{Q}\tREAL\tm3/d\tParameter\n')
        archive.writestr('sumoproject.dll', b'test-placeholder-not-executed')
    return output.getvalue()


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(live_models, '_store', SimpleNamespace(name=str(tmp_path)))
    monkeypatch.setattr(live_models, '_models', {})
    monkeypatch.setattr(live_models, 'read_snapshot', AsyncMock(return_value=[
        {'column': Q, 'value': 41.7, 'timestamp': '2026-10-25T00:00:00Z'}]))
    monkeypatch.setattr(live_models.threading, 'Thread', lambda **kwargs: SimpleNamespace(start=lambda: None))


def test_builtin_is_default_and_original_paths_are_preserved():
    assert LiveStart(mapping={Q: 'tag'}).model_id == 'builtin'
    model = live_models.resolve_model()
    assert model['project'] == live_models.BUILTIN_DIR / 'Cixi Eastern WWTP_20260920.sumo'
    assert model['state'] == live_models.BUILTIN_DIR / 'sumo_steady_state.xml'


def test_upload_and_start_use_selected_project_and_state():
    app = FastAPI()
    app.include_router(router, prefix='/api')
    with TestClient(app) as client:
        content = project_bytes()
        response = client.post('/api/sumo/live/models', data={'state_mode':'calculate', 'mapping':'{"'+Q+'":"tag"}'}, files={
            'project': ('other.sumo', content)})
        assert response.status_code == 202, response.text
        model_id = response.json()['id']
        assert client.get('/api/sumo/live/models/'+model_id).json()['status'] == 'queued'
        with pytest.raises(ValueError, match='still being generated'):
            live_models.resolve_model(model_id)
        with patch.object(live_models, '_run_steady', lambda model: model['state'].write_bytes(STATE)):
            live_models._prepare_model(model_id)
        assert client.get('/api/sumo/live/models/'+model_id).json()['status'] == 'ready'
        model = live_models.resolve_model(model_id)
        assert model['project'].read_bytes() == content
        assert model['state'].read_bytes() == STATE
        with patch.object(liveSimulation, '_session', None), patch.object(liveSimulation.threading, 'Thread'):
            started = client.post('/api/sumo/live/start', json={'mapping': {Q:'tag'}, 'model_id': model_id})
            assert started.status_code == 202
            assert started.json()['model_name'] == 'other.sumo'
            assert liveSimulation._session['model'] == model


def test_invalid_files_never_registered():
    with pytest.raises(ValueError):
        live_models.register_model(b'not zip', 'model.sumo', mapping={Q:'tag'})
    assert not live_models._models


@pytest.mark.parametrize('output', [b'<wrong/>', b'<broken', None])
def test_generation_failure_cannot_start(output):
    model = live_models.register_model(project_bytes(), 'model.sumo', mapping={Q:'tag'})
    def generate(record):
        if output is None:
            raise RuntimeError('Solver failed')
        record['state'].write_bytes(output)
    with patch.object(live_models, '_run_steady', generate):
        live_models._prepare_model(model['id'])
    assert live_models.model_status(model['id'])['status'] == 'failed'
    with pytest.raises(ValueError):
        live_models.resolve_model(model['id'])


def test_unknown_id_cannot_be_used_as_a_file_path():
    with pytest.raises(ValueError, match='unavailable'):
        live_models.resolve_model('../../model.sumo')


def test_upload_limits_are_checked(monkeypatch):
    monkeypatch.setattr(live_models, 'MAX_MODEL_BYTES', 1)
    with pytest.raises(ValueError, match='50 MB'):
        live_models.register_model(project_bytes(), 'model.sumo', mapping={Q:'tag'})


def test_solver_runs_in_isolated_directory_with_uploaded_paths():
    model = live_models.register_model(project_bytes(), 'model.sumo', mapping={Q:'tag'})
    record = live_models._models[model['id']]
    with patch.object(live_models.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as run:
        live_models._run_steady(record)
    args, kwargs = run.call_args
    assert args[0][-5:-2] == [str(record['project']), str(record['state']), str(live_models.STEADY_SECONDS)]
    assert kwargs['cwd'] == record['project'].parent
    assert kwargs['timeout'] > live_models.STEADY_SECONDS
    assert (kwargs['cwd'] / 'steady_run.py').read_bytes() == (live_models.BUILTIN_DIR / 'steady_run.py').read_bytes()


def test_upload_xml_ready_without_sensor_read_or_solver():
    app = FastAPI()
    app.include_router(router, prefix='/api')
    with TestClient(app) as client, patch.object(live_models, '_run_steady') as solver:
        result = client.post('/api/sumo/live/models', data={'state_mode':'upload'},
                             files={'project':('model.sumo',project_bytes()),
                                    'initial_state':('state.xml',STATE)})
        assert result.status_code == 202, result.text
        assert result.json()['status'] == 'ready'
        assert live_models.resolve_model(result.json()['id'])['state'].read_bytes() == STATE
        solver.assert_not_called()
        live_models.read_snapshot.assert_not_called()


def test_steady_uses_fresh_scaled_snapshot_and_records_it():
    import json
    model = live_models.register_model(project_bytes(), 'model.sumo', mapping={Q:'tag'})
    def generate(record):
        inputs = json.loads((record['project'].parent / 'sensor_inputs.json').read_text())
        assert inputs['values'][Q] == pytest.approx(1000)
        assert inputs['readings'][0]['value'] == 41.7
        record['state'].write_bytes(STATE)
    with patch.object(live_models, '_run_steady', generate):
        live_models._prepare_model(model['id'])
    assert live_models.model_status(model['id'])['status'] == 'ready'
    live_models.read_snapshot.assert_awaited_once_with({Q:'tag'})


@pytest.mark.parametrize('state', [b'<wrong/>', b'<broken', b''])
def test_invalid_uploaded_state_rejected(state):
    with pytest.raises(ValueError):
        live_models.register_model(project_bytes(), 'model.sumo', state_mode='upload', state_bytes=state)


def test_sensor_failure_never_runs_solver():
    model = live_models.register_model(project_bytes(), 'model.sumo', mapping={Q:'tag'})
    with patch.object(live_models, 'read_snapshot', AsyncMock(side_effect=RuntimeError('Disconnected'))), patch.object(live_models, '_run_steady') as solver:
        live_models._prepare_model(model['id'])
    assert live_models.model_status(model['id'])['status'] == 'failed'
    solver.assert_not_called()
