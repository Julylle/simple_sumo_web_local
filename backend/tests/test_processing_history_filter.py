import json
import zipfile

import pytest
from services.processing_history import should_record_input
from services.input_provenance import process_readings, input_provenance, record_treatments
from services import live_checkpoint as cp

PREFIX = 'Sumo__Plant__'


@pytest.mark.parametrize('name', [
    'CSTR1__param__SO2', 'CSTR2_10__param__SO2', 'CSTR1_5__SO2',
    'MLR1__param__Qpumped_target', 'MLR2_1__param__Qpumped_target',
    'MLR1_2__param__Qpumped_target', 'MLR2_2__Q',
])
def test_excluded_input_names(name):
    assert not should_record_input(PREFIX + name)


@pytest.mark.parametrize('name', [
    'CSTR3_5__param__SO2', 'CSTR4_10__param__SO2', 'CSTR1_5__param__SNOx',
    'CSTR10_5__param__SO2', 'MLR10__param__Qpumped_target',
    'Sideflowdivider3__param__Qpumped_target', 'WAS_1__param__Qpumped_target',
])
def test_other_inputs_still_logged(name):
    assert should_record_input(PREFIX + name)


def test_live_processing_unchanged_but_excluded_logs_removed_and_not_appended():
    excluded = PREFIX + 'CSTR1_5__param__SO2'
    kept = PREFIX + 'CSTR3_5__param__SO2'
    mapping = {excluded:'ns=2;s=a', kept:'ns=2;s=b'}
    values = process_readings(mapping, [dict(column=k, value=-2) for k in mapping])
    assert values == {excluded:0, kept:0}
    session = {'input_processing_records': [
        dict(column=excluded, sequence=1), dict(column=kept, sequence=7)]}
    record_treatments(session, input_provenance(mapping, values, 0, 60000))
    assert [r['column'] for r in session['input_processing_records']] == [kept, kept]
    assert [r['sequence'] for r in session['input_processing_records']] == [7,8]
    held = process_readings(mapping, [dict(column=k,error='TimeoutError') for k in mapping], values)
    record_treatments(session, input_provenance(mapping, held, 60000, 60000))
    assert held == values
    assert all(r['column'] == kept for r in session['input_processing_records'])


def test_old_checkpoint_read_and_persist_removes_excluded_rows_without_touching_state(tmp_path, monkeypatch):
    monkeypatch.setenv('SUMO_LIVE_STATE_DIR', str(tmp_path))
    records = [dict(column=PREFIX+'MLR2_1__param__Qpumped_target', sequence=1),
               dict(column=PREFIX+'CSTR3_5__param__SO2', sequence=2, model_value=0.001)]
    target = cp.checkpoint_path()
    with zipfile.ZipFile(target, 'w') as archive:
        archive.writestr('metadata.json', json.dumps({'run_id':'test','simulated_ms':60000}))
        archive.writestr('input_processing_records.json', json.dumps(records))
        archive.writestr('state.xml', b'unchanged state')
    with zipfile.ZipFile(target) as archive:
        assert cp._read_processing_records(archive) == records[1:]
    cp.persist_processing_records({'id':'test', 'input_processing_records':records})
    with zipfile.ZipFile(target) as archive:
        assert json.loads(archive.read('input_processing_records.json')) == records[1:]
        assert archive.read('state.xml') == b'unchanged state'
        assert json.loads(archive.read('metadata.json'))['simulated_ms'] == 60000
    assert json.loads((tmp_path/'input_processing_test.json').read_text()) == records[1:]
    assert len(records) == 2  # no in-place modification of the original list
