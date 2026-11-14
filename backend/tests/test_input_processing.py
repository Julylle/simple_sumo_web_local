import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from services.input_provenance import process_readings, input_provenance, record_treatments
from services.historical_inputs import load_history, load_available_history, history_request
from services import live_checkpoint as cp
from services.kepserver import read_snapshot
from liveSimulation import liveSimulation as live

Q = 'Sumo__Plant__Influent__param__Q'
DO = 'Sumo__Plant__CSTR3_5__param__SO2'
MAPPING = {Q: 'ns=2;s=flow'}

@pytest.mark.parametrize('raw', [float('nan'), float('inf'), float('-inf')])
def test_nonfinite_uses_previous_model_units_and_json_safe_log(raw):
    values = process_readings(MAPPING, [{'column': Q, 'value': raw}], {Q: 1000})
    assert values[Q] == 1000  # must not divide a model-unit held value by 0.0417 again
    session = {}
    record_treatments(session, input_provenance(MAPPING, values, 60000, 60000))
    record = session['input_processing_records'][0]
    assert record['start_ms'] == 60000 and record['model_value'] == 1000
    assert 'Non-finite' in record['reason']
    json.dumps(session, allow_nan=False)


def test_negative_then_failure_holds_zero_and_recovers():
    values = process_readings(MAPPING, [{'column': Q, 'value': -334.88}], {Q: 1000})
    assert values[Q] == 0 and values.provenance[Q]['raw_value'] == -334.88
    held = process_readings(MAPPING, [{'column': Q, 'error': 'TimeoutError: PLC offline'}], values)
    assert held[Q] == 0 and held.provenance[Q]['reason'] == 'TimeoutError: PLC offline'
    recovered = process_readings(MAPPING, [{'column': Q, 'value': 83.4}], held)
    assert recovered[Q] == pytest.approx(2000)
    assert 'treatment' not in recovered.provenance[Q]


def test_unseeded_failure_has_actual_reason():
    with pytest.raises(ValueError, match='BadNodeIdUnknown.*no previous'):
        process_readings(MAPPING, [{'column': Q, 'error': 'BadNodeIdUnknown'}])


def plan():
    return dict(history_request('2026-01-01T00:00:00Z', '2026-01-01T00:02:00Z', 1), last_inputs={Q: 1000})


def test_history_nan_and_read_failure_hold_previous():
    store = MagicMock()
    cursor = store.connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [(0, Q, float('nan')), (1, Q, 83.4)]
    with patch('services.historical_inputs.Store', return_value=store):
        windows = load_history(MAPPING, 60, plan())
        assert [w.values[Q] for w in windows] == pytest.approx([1000, 2000])
        assert 'Non-finite' in windows[0].provenance[Q]['reason']
        cursor.execute.side_effect = RuntimeError('Connection lost 2013')
        windows = load_history(MAPPING, 60, plan())
        assert all(w.values[Q] == 1000 for w in windows)
        assert 'Connection lost 2013' in windows[0].provenance[Q]['reason']
        current_plan = plan()
        windows = load_available_history(MAPPING, 60, current_plan)
        assert len(windows) == 1 and windows[0].values[Q] == 1000
        assert current_plan['caught_up']  # failed reads are paced, not a tight retry loop


def test_history_invalid_samples_use_previous_in_average_and_report_collector_error():
    store = MagicMock()
    cursor = store.connection.cursor.return_value.__enter__.return_value
    # Two recorded samples: one valid (2000 model units), one collector failure (hold 1000).
    cursor.fetchall.return_value = [(0, Q, 83.4, None, None, 2, 0, 1, 'PLC timeout'),
                                   (1, Q, None, None, None, 2, 0, 2, 'BadNoCommunication')]
    with patch('services.historical_inputs.Store', return_value=store):
        windows = load_history(MAPPING, 60, plan())
    assert [w.values[Q] for w in windows] == pytest.approx([1500, 1500])
    assert windows[0].provenance[Q]['reason'] == 'PLC timeout'
    assert windows[1].provenance[Q]['reason'] == 'BadNoCommunication'


def test_tolerant_opc_partial_and_connection_failure():
    import asyncio
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    node = MagicMock()
    node.read_value = AsyncMock(side_effect=[41.7, TimeoutError('PLC deadline')])
    client.get_node.return_value = node
    with patch('services.kepserver.Client', return_value=client):
        readings = asyncio.run(read_snapshot({**MAPPING, DO: 'ns=2;s=do'}, tolerate_errors=True))
        assert readings[0]['value'] == 41.7
        assert readings[1]['error'] == 'TimeoutError: PLC deadline'
        client.__aenter__.side_effect = OSError('Endpoint unreachable')
        readings = asyncio.run(read_snapshot(MAPPING, tolerate_errors=True))
        assert readings[0]['error'] == 'OSError: Endpoint unreachable'


def test_checkpoint_restore_stop_append_and_old_compatibility(tmp_path, monkeypatch):
    import zipfile
    monkeypatch.setenv('SUMO_LIVE_STATE_DIR', str(tmp_path))
    state = tmp_path / 'state.xml'
    state.write_text('<systemstate><state/></systemstate>')
    project = tmp_path / 'model.sumo'
    project.write_bytes(b'test model')
    session = dict(id='audit-test', model={'name':'model','project':project}, mapping=MAPPING,
                   interval=60, history=plan(), times=[], variables={})
    values = process_readings(MAPPING, [{'column': Q, 'value': -1}])
    record_treatments(session, input_provenance(MAPPING, values, 0, 60000))
    cp.save_checkpoint(session, state, 60000)
    held = process_readings(MAPPING, [{'column': Q, 'error': 'TimeoutError'}], values)
    record_treatments(session, input_provenance(MAPPING, held, 60000, 60000))
    cp.persist_processing_records(session)
    assert cp.checkpoint_info()['simulated_ms'] == 60000  # final audit save must not advance native state
    assert len(cp.saved_snapshot()['input_processing_records']) == 2
    monkeypatch.setattr(live, '_session', None)
    with patch.object(live.threading, 'Thread'):
        snapshot = live.resume()
    try:
        assert len(snapshot['input_processing_records']) == 2
        record_treatments(live._session, input_provenance(MAPPING, held, 60000, 60000))
        assert live._session['input_processing_records'][-1]['sequence'] == 3
    finally:
        live._session['resume_folder'].cleanup()
    assert len(json.loads((tmp_path/'input_processing_audit-test.json').read_text())) == 2
    legacy = tmp_path / 'legacy.zip'
    with zipfile.ZipFile(legacy, 'w') as archive:
        assert cp._read_processing_records(archive) == []
