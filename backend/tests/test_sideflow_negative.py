import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from services.sensor_policy import SIDEFLOW_COLUMN as KEY, normalize_reading
from services.model_inputs import INPUT_CONVERSIONS, scale_model_inputs
from services.input_provenance import process_readings, input_provenance, record_treatments
from services.historical_inputs import load_history, history_request
from services.realtime_windows import make_windows
from services.sensor_snapshot import database_readings
from datetime import datetime, timezone

NODE = 'ns=2;s=SiemensEth.PLC204.F_Q2'
OTHER = 'Sumo__Plant__Influent__param__Q'


@pytest.mark.parametrize('raw,expected', [(-334.8833, .001), (0, 0), (.0001, .0001), (4, 4)])
def test_only_negative_values_use_replacement(raw, expected):
    assert normalize_reading(KEY, raw) == expected
    scaling, offset = INPUT_CONVERSIONS[KEY]
    assert scale_model_inputs([dict(column=KEY, value=raw)])[KEY] == pytest.approx((expected-offset)/scaling)
    assert normalize_reading(OTHER, -1) == 0


def test_live_log_and_failure_hold_converted_replacement():
    values = process_readings({KEY:NODE}, [dict(column=KEY, value=-334.8833)])
    expected = scale_model_inputs([dict(column=KEY, value=.001)])[KEY]
    assert values[KEY] == expected
    session = {}
    record_treatments(session, input_provenance({KEY:NODE}, values, 0, 60000))
    record = session['input_processing_records'][0]
    assert record['treatment'] == 'negative_to_minimum'
    assert record['replacement_raw_value'] == .001
    assert record['raw_value'] == -334.8833
    held = process_readings({KEY:NODE}, [dict(column=KEY, error='TimeoutError')], values)
    assert held[KEY] == expected


def test_history_sql_replaces_each_sample_before_mean_and_logs_it():
    store = MagicMock()
    cursor = store.connection.cursor.return_value.__enter__.return_value
    def execute(sql, params):
        # Execute the actual generated aggregate expression against representative raw samples.
        aggregate = sql.split('v.sumo_name, ', 1)[1].split(',\n                    MIN(', 1)[0]
        with sqlite3.connect(':memory:') as db:
            db.create_function('GREATEST', 2, max)
            db.executescript("CREATE TABLE raw_data (numeric_value REAL, quality TEXT);"
                             "CREATE TABLE raw_variables (sumo_name TEXT);")
            db.executemany('INSERT INTO raw_data VALUES (?,?)', [(-2,'good'), (4,'good')])
            db.execute('INSERT INTO raw_variables VALUES (?)', [KEY])
            value = db.execute('SELECT '+aggregate+' FROM raw_data r CROSS JOIN raw_variables v').fetchone()[0]
        assert value == pytest.approx(2.0005)
        cursor.fetchall.return_value = [(0,KEY,value,None,None,2,1,0,None)]
    cursor.execute.side_effect = execute
    plan = history_request('2026-01-01T00:00Z','2026-01-01T00:01Z',1)
    with patch('services.historical_inputs.Store', return_value=store):
        window, = load_history({KEY:NODE},60,plan)
    assert window.values[KEY] == pytest.approx(2.0005 / INPUT_CONVERSIONS[KEY][0])
    assert window.provenance[KEY]['replacement_raw_value'] == .001
    assert window.provenance[KEY]['negative_count'] == 1
    assert window.provenance[KEY]['treatment'] == 'negative_to_minimum'
    assert make_windows([(0,{KEY:-2}),(1,{KEY:4})])[0].inputs[KEY] == pytest.approx(2.0005)


def test_database_preview_uses_raw_replacement():
    store = MagicMock()
    store.connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (-2, datetime(2026,1,1))
    with patch('services.sensor_snapshot.Store', return_value=store):
        result = database_readings({KEY:NODE}, datetime(2026,1,1,tzinfo=timezone.utc))
    assert result[0]['value'] == .001
