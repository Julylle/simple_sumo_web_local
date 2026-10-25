import io
import zipfile
from types import SimpleNamespace
from unittest.mock import patch

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
        response = client.post('/api/sumo/live/models', files={
            'project': ('other.sumo', content),
            'initial_state': ('other.xml', STATE)})
        assert response.status_code == 201, response.text
        model_id = response.json()['id']
        model = live_models.resolve_model(model_id)
        assert model['project'].read_bytes() == content
        assert model['state'].read_bytes() == STATE
        with patch.object(liveSimulation, '_session', None), patch.object(liveSimulation.threading, 'Thread'):
            started = client.post('/api/sumo/live/start', json={'mapping': {Q:'tag'}, 'model_id': model_id})
            assert started.status_code == 202
            assert started.json()['model_name'] == 'other.sumo'
            assert liveSimulation._session['model'] == model


@pytest.mark.parametrize('project,state', [(b'not zip', STATE), (project_bytes(), b'<wrong/>'), (project_bytes(), b'<broken')])
def test_invalid_files_never_registered(project, state):
    with pytest.raises(ValueError):
        live_models.register_model(project, state, 'model.sumo', 'state.xml')
    assert not live_models._models


def test_unknown_id_cannot_be_used_as_a_file_path():
    with pytest.raises(ValueError, match='unavailable'):
        live_models.resolve_model('../../model.sumo')


def test_upload_limits_are_checked(monkeypatch):
    monkeypatch.setattr(live_models, 'MAX_MODEL_BYTES', 1)
    with pytest.raises(ValueError, match='50 MB'):
        live_models.register_model(project_bytes(), STATE, 'model.sumo', 'state.xml')
