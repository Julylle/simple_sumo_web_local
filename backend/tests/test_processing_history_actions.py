import json
import zipfile
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.live_sumo import router
from liveSimulation import liveSimulation as live
from services import live_checkpoint as cp
from services.input_provenance import record_treatments

KEY = 'Sumo__Plant__CSTR3_5__param__SO2'


@pytest.fixture
def saved(tmp_path, monkeypatch):
    monkeypatch.setenv('SUMO_LIVE_STATE_DIR', str(tmp_path))
    monkeypatch.setattr(live, '_session', None)
    state = tmp_path/'state.xml'
    state.write_text('<systemstate><state/></systemstate>')
    project = tmp_path/'model.sumo'
    project.write_bytes(b'model')
    session = dict(id='history-actions', model={'name':'model','project':project}, mapping={KEY:'ns=2;s=do'},
                   interval=60, times=[0], variables={KEY:[2]}, sensor_timestamps=['2026-01-01T00:01:00Z'],
                   input_processing_records=[dict(sequence=i+1, column=KEY, reason='测试',model_value=2) for i in range(205)])
    cp.save_checkpoint(session, state, 60000)
    return session, state


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_download_all_pages_and_clear_without_running_model(saved, client):
    session, _ = saved
    result = client.get('/sumo/live/processing-records/download', params={'run_id':session['id']})
    assert result.status_code == 200
    assert 'attachment' in result.headers['content-disposition']
    assert len(result.json()['records']) == 205
    assert result.json()['records'][0]['reason'] == '测试'
    with zipfile.ZipFile(cp.checkpoint_path()) as archive:
        before = {name:archive.read(name) for name in archive.namelist() if name != 'input_processing_records.json'}
    response = client.post('/sumo/live/processing-records/clear', json={'run_id':session['id']})
    assert response.status_code == 200 and response.json()['records'] == []
    assert cp.saved_snapshot()['input_processing_records'] == []
    metadata, _, folder = cp.restore_checkpoint()
    try:
        assert metadata['input_processing_records'] == []
    finally:
        folder.cleanup()
    with zipfile.ZipFile(cp.checkpoint_path()) as archive:
        assert all(archive.read(k) == v for k,v in before.items())
    assert json.loads((cp.checkpoint_path().parent/'input_processing_history-actions.json').read_text()) == []


def test_active_clear_then_new_events_and_checkpoint(saved, monkeypatch):
    session, state = saved
    monkeypatch.setattr(live, '_session', session)
    live.clear_processing_history(session['id'])
    assert session['input_processing_records'] == []
    record_treatments(session, {'start_ms':60000,'end_ms':120000,
                              'inputs':[dict(column=KEY,treatment='held_previous',model_value=2)]})
    cp.save_checkpoint(session,state,120000)
    assert len(cp.saved_snapshot()['input_processing_records']) == 1
    assert cp.saved_snapshot()['input_processing_records'][0]['start_ms'] == 60000


def test_stale_run_id_cannot_clear_or_download_new_run(saved, client):
    assert client.post('/sumo/live/processing-records/clear',json={'run_id':'other-run'}).status_code == 409
    assert client.get('/sumo/live/processing-records/download?run_id=other-run').status_code == 409
    assert len(cp.saved_snapshot()['input_processing_records']) == 205


def test_write_failure_keeps_active_records_and_reports_failure(saved, client, monkeypatch):
    session, _ = saved
    monkeypatch.setattr(live,'_session',session)
    with patch.object(cp, 'persist_processing_records', side_effect=OSError('Disk full')):
        response = client.post('/sumo/live/processing-records/clear',json={'run_id':session['id']})
    assert response.status_code == 500
    assert len(session['input_processing_records']) == 205
    assert len(cp.saved_snapshot()['input_processing_records']) == 205


def test_download_omits_excluded_records_and_does_not_clear(saved, monkeypatch):
    session, _ = saved
    session['input_processing_records'].append(dict(column='Sumo__Plant__MLR1_1__param__Qpumped_target'))
    monkeypatch.setattr(live,'_session',session)
    assert len(live.processing_records(session['id'])['records']) == 205
    assert len(session['input_processing_records']) == 206
