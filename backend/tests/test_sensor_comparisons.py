from datetime import datetime
from unittest.mock import MagicMock

from services import sensor_comparisons as comparisons
from database.catalog import load_mapping


def fixture_snapshot():
    return {'id':'run-1','interval_minutes':1,'history':{'database':'sumo_web_database'},
            'result':{'time_h':[1/60,2/60,3/60],
                      'sensor_timestamps':[f'2026-10-26T08:0{i}:00Z' for i in (1,2,3)]}}


def test_confirmed_sensors_match_collector_csv():
    _, _, rows = load_mapping()
    for name, tag in comparisons.COMPARISON_SENSORS.values():
        assert any(row['SumoName']==name and row['OpcTag']==tag and row['Scaling']=='1' for row in rows)
    assert len(comparisons.COMPARISON_SENSORS) == 2
    assert not any('NHx' in key for key in comparisons.COMPARISON_SENSORS)


def test_measured_means_are_time_aligned_and_gaps_are_not_forward_filled(monkeypatch):
    store=MagicMock()
    cursor=store.connection.cursor.return_value.__enter__.return_value
    first, second = list(comparisons.COMPARISON_SENSORS)
    cursor.fetchall.return_value=[(0,comparisons.COMPARISON_SENSORS[first][0],0),
                                 (2,comparisons.COMPARISON_SENSORS[second][0],4.5)]
    monkeypatch.setattr(comparisons,'Store',lambda:store)
    result=comparisons.read_comparisons(fixture_snapshot())
    assert result['series'][first]['values']==[0,None,None]
    assert result['series'][second]['values']==[None,None,4.5]
    assert result['series'][first]['timestamps']==[f'2026-10-26T08:0{i}:00+00:00' for i in (1,2,3)]
    assert result['aggregation_seconds']==60
    store.connect.assert_called_once_with(database='sumo_web_database')
    sql, params=cursor.execute.call_args.args
    assert "r.quality='good'" in sql and 'AVG(r.numeric_value)' in sql
    assert params[2:4]==[datetime(2026,10,26,8),datetime(2026,10,26,8,3)]
    store.close.assert_called_once()


def test_no_samples_or_only_initial_state_needs_no_database(monkeypatch):
    factory=MagicMock(side_effect=AssertionError('must not query'))
    monkeypatch.setattr(comparisons,'Store',factory)
    assert comparisons.read_comparisons({'id':'run-1'})['series']=={}
    assert comparisons.read_comparisons({'result':{'time_h':[0],'sensor_timestamps':['2026-01-01T00:00Z']}})['series']=={}


def test_long_runs_bound_comparison_size_and_never_advance_past_model(monkeypatch):
    store=MagicMock()
    store.connection.cursor.return_value.__enter__.return_value.fetchall.return_value=[]
    monkeypatch.setattr(comparisons,'Store',lambda:store)
    snapshot=fixture_snapshot()
    snapshot['result']={'time_h':[0,24*30], 'sensor_timestamps':['2026-01-01T00:00Z','2026-01-31T00:00Z']}
    result=comparisons.read_comparisons(snapshot)
    assert result['aggregation_seconds']>60
    for series in result['series'].values():
        assert len(series['values'])<=5000
        assert series['timestamps'][-1]=='2026-01-31T00:00:00+00:00'


def test_api_rejects_stale_run_and_measurement_failures_do_not_stop_model(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.live_sumo import router
    from liveSimulation import liveSimulation as live
    app=FastAPI();app.include_router(router,prefix='/api')
    client=TestClient(app)
    snapshot=fixture_snapshot()
    monkeypatch.setattr(live,'snapshot',lambda:snapshot)
    reader=MagicMock(side_effect=RuntimeError('database offline'))
    monkeypatch.setattr(comparisons,'read_comparisons',reader)
    stop=MagicMock()
    monkeypatch.setattr(live,'stop',stop)
    assert client.get('/api/sumo/live/comparisons?run_id=old-run').status_code==409
    reader.assert_not_called()
    response=client.get('/api/sumo/live/comparisons?run_id=run-1')
    assert response.status_code==503
    stop.assert_not_called()
    assert snapshot==fixture_snapshot()
