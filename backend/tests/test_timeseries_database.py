import asyncio
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from database.catalog import load_mapping, model_catalog, COLUMNS
from database.collector import acquire
from database.store import numeric, json_value, dbtime
from database.simulation import SimulationRecorder, open_recorder


def test_complete_csv_retains_all_rows_columns_and_tag_spaces():
    sha, content, rows = load_mapping()
    assert len(rows) == 73
    assert len(sha) == 64
    assert all(set(COLUMNS).issubset(row) for row in rows)
    assert any('MLR _Flow' in row['OpcTag'] for row in rows)
    assert any(row['OpcType'] == 'STRING' for row in rows)
    assert len({r['OpcTag'] for r in rows}) < len(rows)
    assert load_mapping()[0] == sha


def test_collector_reads_unique_tags_but_persists_every_mapping_and_quality():
    _, _, rows = load_mapping()
    calls = []
    timestamp = datetime(2026, 10, 25, tzinfo=timezone.utc)
    class Node:
        def __init__(self, tag): self.tag = tag
        async def read_data_value(self, **kwargs):
            calls.append(self.tag)
            if 'pH' in self.tag:
                raise RuntimeError('bad node')
            bad = 'Temperature' in self.tag
            return SimpleNamespace(Value=SimpleNamespace(Value='41.7'), SourceTimestamp=timestamp,
                ServerTimestamp=timestamp, StatusCode=SimpleNamespace(value=0x80000000 if bad else 0,
                                                                     is_good=lambda: not bad))
    class Client:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get_node(self, node): return Node(node)
    samples = asyncio.run(acquire(rows, Client))
    assert len(samples) == 73
    assert len(calls) == len({r['OpcTag'] for r in rows})
    assert samples[0]['raw_value'] == '41.7'
    assert samples[0]['scaled_value'] == pytest.approx(1000)
    assert samples[0]['source_timestamp'] == timestamp
    assert samples[1]['quality'] == 'read_error'
    assert samples[1]['scaled_value'] is None
    assert samples[2]['quality'] == 'bad'
    assert samples[2]['scaled_value'] is None
    assert any('MLR _Flow' in tag for tag in calls)


def test_connection_failure_still_records_every_variable():
    _, _, rows = load_mapping()
    class Offline:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): raise ConnectionError('offline')
        async def __aexit__(self, *args): pass
    samples = asyncio.run(acquire(rows, Offline))
    assert len(samples) == len(rows)
    assert all(s['quality'] == 'connection_error' and s['numeric_value'] is None for s in samples)


@pytest.fixture
def project(tmp_path):
    path = tmp_path/'model.sumo'
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('variables.var', '\n'.join([
            '1\tstate\t0\tREALARRAY\tStateVariable\tPlant\tmg/L',
            '2\taccum\t0\tREAL\tAccumulatedStateVariable\tPlant\tkg',
            '3\tderived\t0\tREAL\tSystemState\tPlant\tmg/L',
            '4\tparam\t0\tREAL\tParameter\tPlant\tmg/L']))
    return path


def test_state_catalog_automatic_and_array_metadata_preserved(project, monkeypatch):
    monkeypatch.delenv('SUMO_DB_INCLUDE_SYSTEM_STATE', raising=False)
    sha, rows = model_catalog(project)
    assert {r['name'] for r in rows} == {'state', 'accum'}
    assert rows[0]['type'] == 'REALARRAY'
    assert len(model_catalog(project, ['derived'])[1]) == 3
    monkeypatch.setenv('SUMO_DB_INCLUDE_SYSTEM_STATE', '1')
    assert len(model_catalog(project)[1]) == 3
    assert sha == model_catalog(project)[0]


def test_serialization_preserves_strings_arrays_nonfinite_and_utc():
    assert json_value(['2', 3, float('nan')]) == ['2', 3, 'nan']
    assert numeric('2.5') == 2.5
    assert numeric('not available') is None
    assert numeric([1, 2]) is None
    assert numeric(float('inf')) is None
    assert dbtime('2026-10-25T11:00:00+10:00') == datetime(2026, 10, 25, 1)


def test_background_writer_flushes_arrays_and_propagates_errors(project):
    class FakeStore:
        def connect(self): return self
        def register_run(self, *args): return {'state': 1, 'accum': 2}
        def write_simulation(self, *args):
            self.writes.append(args)
            if args[2] == 120000: raise RuntimeError('disk full')
        def close(self): self.closed = True
        def __init__(self): self.writes = []; self.closed = False
    fake = FakeStore()
    with patch('database.simulation.Store', return_value=fake):
        recorder = SimulationRecorder(project, 'run', 'live', {})
    data = {'state': [1, 2], 'accum': 3}
    recorder.submit(60000, data, '2026-10-25T01:00:00+00:00')
    data['state'][0] = 9
    recorder.flush()
    assert fake.writes[0][3]['state'] == [1, 2]
    recorder.submit(120000, data)
    with pytest.raises(RuntimeError, match='MySQL write failed'): recorder.flush()
    with pytest.raises(RuntimeError, match='MySQL write failed'): recorder.close()
    assert fake.closed


def test_disabled_recorder_does_not_require_mysql(project, monkeypatch):
    monkeypatch.delenv('SUMO_MYSQL_ENABLED', raising=False)
    assert open_recorder(project, 'run', 'live', {}) is None


def test_only_one_collector_can_own_spool(tmp_path):
    from database.collector import lock_collector
    lock = lock_collector(tmp_path)
    try:
        with pytest.raises(RuntimeError, match='already owns'):
            lock_collector(tmp_path)
    finally:
        lock.close()
    lock_collector(tmp_path).close()


@pytest.mark.parametrize('flag', [None, '0', '1'])
def test_history_recording_is_required_and_uses_checkpoint_database(project, monkeypatch, flag):
    if flag is None: monkeypatch.delenv('SUMO_MYSQL_ENABLED', raising=False)
    else: monkeypatch.setenv('SUMO_MYSQL_ENABLED', flag)
    monkeypatch.setenv('MYSQL_DATABASE', 'different_live_database')
    monkeypatch.setenv('SUMO_HISTORY_DATABASE', 'different_history_setting')
    config = {'history': {'database': 'sumo_web_database'}}
    with patch('database.simulation.SimulationRecorder') as recorder:
        result = open_recorder(project, 'run', 'history_then_live', config, ['derived'])
        recorder.assert_called_once_with(project, 'run', 'history_then_live', config, ['derived'], database='sumo_web_database')
        assert result is recorder.return_value


def test_history_default_destination_and_write_connection_failure(project, monkeypatch):
    monkeypatch.delenv('SUMO_MYSQL_ENABLED', raising=False)
    monkeypatch.delenv('SUMO_HISTORY_DATABASE', raising=False)
    with patch('database.simulation.Store') as factory:
        store = factory.return_value
        store.connect.side_effect = ConnectionError('write connection unavailable')
        with pytest.raises(ConnectionError):
            open_recorder(project, 'run', 'history_then_live', {})
        store.connect.assert_called_once_with(database='sumo_web_database')
        store.close.assert_called_once()
