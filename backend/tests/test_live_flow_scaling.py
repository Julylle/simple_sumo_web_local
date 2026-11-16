from unittest.mock import AsyncMock, patch

import pytest

from liveSimulation.liveSimulation import _read_model_inputs

Q = 'Sumo__Plant__Influent__param__Q'
TKN = 'Sumo__Plant__Influent__param__TKN'
DO = 'Sumo__Plant__CSTR1_5__param__SO2'


def test_fresh_flow_is_divided_once_and_other_readings_unchanged():
    initial = [{'timestamp': '2026-10-30T01:47:00+00:00', 'column': Q, 'value': 41.7}, {'timestamp': '2026-10-30T01:47:00+00:00', 'column': TKN, 'value': 40},
               {'timestamp': '2026-10-30T01:47:00+00:00', 'column': DO, 'value': 2.5}]
    updated = [{'timestamp': '2026-10-30T01:47:00+00:00', 'column': Q, 'value': 83.4}, {'timestamp': '2026-10-30T01:47:00+00:00', 'column': TKN, 'value': 42},
               {'timestamp': '2026-10-30T01:47:00+00:00', 'column': DO, 'value': 3}]
    mapping = {Q: 'flow-tag', TKN: 'tkn-tag', DO: 'do-tag'}
    with patch('liveSimulation.liveSimulation.read_snapshot',
               new=AsyncMock(side_effect=[initial, updated])) as read:
        assert _read_model_inputs(mapping) == {Q: pytest.approx(1000), TKN: 40, DO: 2.5}
        assert _read_model_inputs(mapping) == {Q: pytest.approx(2000), TKN: 42, DO: 3}
        assert read.await_count == 2
        read.assert_awaited_with(mapping, tolerate_errors=True)
    assert initial[0]['value'] == 41.7
    assert updated[0]['value'] == 83.4


def test_mapping_without_flow_is_unchanged():
    with patch('liveSimulation.liveSimulation.read_snapshot',
               new=AsyncMock(return_value=[{'timestamp': '2026-10-30T01:47:00+00:00', 'column': DO, 'value': 2}])):
        assert _read_model_inputs({DO: 'do-tag'}) == {DO: 2}


@pytest.mark.parametrize('column,raw,expected', [
    ('Sumo__Plant__Sideflowdivider3__param__Qpumped_target', 41.7, 1000),
    ('Sumo__Plant__Carbon1__param__Q', 83.34, 2),
    ('Sumo__Plant__Carbon2__param__Q', 125.01, 3),
    ('Sumo__Plant__Metal1__param__Q', 166.68, 4),
])
def test_additional_control_conversions_on_every_fresh_read(column, raw, expected):
    readings = [{'timestamp': '2026-10-30T01:47:00+00:00', 'column': column, 'value': raw}, {'timestamp': '2026-10-30T01:47:00+00:00', 'column': DO, 'value': 2.5}]
    with patch('liveSimulation.liveSimulation.read_snapshot',
               new=AsyncMock(return_value=readings)):
        for _ in range(2):
            assert _read_model_inputs({column: 'tag', DO: 'do-tag'}) == {
                column: pytest.approx(expected), DO: 2.5}
    assert readings[0]['value'] == raw


def test_negative_sensor_values_clamped_before_model_conversion():
    from services.model_inputs import scale_model_inputs
    key = 'Sumo__Plant__Sideflowdivider3__param__Qpumped_target'
    readings = [{'timestamp': '2026-10-30T01:47:00+00:00', 'column': key, 'value': -334.88330078125}, {'timestamp': '2026-10-30T01:47:00+00:00', 'column': DO, 'value': -1}]
    assert scale_model_inputs(readings) == {key: pytest.approx(0.001 / 0.0417), DO: 0}
    assert readings[0]['value'] == -334.88330078125
    for value in [float('nan'), float('inf'), float('-inf')]:
        with pytest.raises(ValueError, match='Non-finite'):
            scale_model_inputs([{'timestamp': '2026-10-30T01:47:00+00:00', 'column': key, 'value': value}])
