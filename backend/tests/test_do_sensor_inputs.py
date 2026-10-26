"""Live DO support must not expand the offline influent upload schema."""
import asyncio
from unittest.mock import patch

from api.kepserver import SnapshotRequest
from api.live_sumo import LiveStart
from services.sensor_inputs import SENSOR_COLUMNS, DO_COLUMNS
from services.sumo_data import ALLOWED_COLUMNS, validate_columns
from services.kepserver import read_snapshot
from liveSimulation import liveSimulation
import pytest


def test_sensor_allowlist_and_request_capacity():
    assert len(DO_COLUMNS) == 24
    assert len(set(SENSOR_COLUMNS)) == 53
    mapping = {key: f'ns=2;s=sensor{i}' for i, key in enumerate(SENSOR_COLUMNS)}
    assert SnapshotRequest(mapping=mapping).mapping == mapping
    assert LiveStart(mapping=mapping).mapping == mapping
    with pytest.raises(ValueError):
        validate_columns([DO_COLUMNS[0]])
    with patch.object(liveSimulation, '_session', None), patch.object(liveSimulation.threading, 'Thread'):
        liveSimulation.start(mapping, 5)
        assert liveSimulation._session['mapping'] == mapping


def test_all_mappings_return_even_when_tags_are_shared():
    class Node:
        async def read_value(self):
            return 2.5
    class Client:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        def get_node(self, node_id): return Node()
    mapping = {key: 'ns=2;s=shared_tag' for key in SENSOR_COLUMNS}
    with patch('services.kepserver.Client', Client):
        readings = asyncio.run(read_snapshot(mapping))
    assert len(readings) == 53
    assert {r['column'] for r in readings} == set(SENSOR_COLUMNS)
    assert all(r['value'] == 2.5 for r in readings)


def test_unknown_do_input_rejected():
    with pytest.raises(ValueError, match='Unsupported'):
        asyncio.run(read_snapshot({'Sumo__Plant__CSTR9_5__param__SO2': 'ns=2;s=tag'}))


def test_all_supported_inputs_use_csv_scaling_once():
    from database.catalog import load_mapping
    from services.model_inputs import scale_model_inputs
    rows = {r['SumoName']: r for r in load_mapping()[2]}
    raw = [{'column': name, 'value': 41.7} for name in SENSOR_COLUMNS]
    converted = scale_model_inputs(raw)
    for name in SENSOR_COLUMNS:
        row = rows[name]
        assert converted[name] == (41.7-float(row['Offset']))/float(row['Scaling'])
    assert all(r['value'] == 41.7 for r in raw)
