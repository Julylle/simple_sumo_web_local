from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from services import historical_inputs as history

Q = 'Sumo__Plant__Influent__param__Q'
NH = 'Sumo__Plant__Influent__param__TKN'
MAPPING = {Q: 'ns=2;s=flow', NH: 'ns=2;s=nitrogen'}


def request():
    return history.history_request('2026-01-01T10:00:00+10:00', '2026-01-01T10:01:30+10:00', 1)


@pytest.mark.parametrize('start,end', [
    ('2026-01-01T00:00', '2026-01-02T00:00Z'),
    ('bad', '2026-01-02T00:00Z'),
    ('2026-01-02T00:00Z', '2026-01-01T00:00Z'),
    ('2026-01-01T00:00Z', '2999-01-01T00:00Z'),
    (None, None),
    ('2026-01-01T00:00:00.000001Z', '2026-01-01T00:01:00Z'),
])
def test_invalid_ranges_rejected(start, end):
    with pytest.raises(ValueError):
        history.history_request(start, end, 1)


def fake_store(monkeypatch, rows):
    store = MagicMock()
    cursor = store.connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = rows
    monkeypatch.setattr(history, 'Store', lambda: store)
    return store, cursor


def test_bulk_read_timezone_partial_tail_and_scaling_once(monkeypatch):
    plan = request()
    assert plan['total'] == 2
    assert plan['database'] == 'sumo_web_database'
    store, cursor = fake_store(monkeypatch, [(0, Q, 41.7), (0, NH, 20), (1, Q, 83.4), (1, NH, 30)])
    windows = history.load_history(MAPPING, 60, plan)
    assert [w.duration_ms for w in windows] == [60000, 30000]
    assert [w.values[Q] for w in windows] == pytest.approx([1000, 2000])
    assert windows[1].timestamp == '2026-01-01T00:01:30+00:00'
    store.connect.assert_called_once_with(database='sumo_web_database')
    store.close.assert_called_once()
    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args.args
    assert 'AVG(GREATEST(r.numeric_value, 0))' in sql and "r.quality='good'" in sql
    assert 'r.acquired_at < %s' in sql and 'flow' not in sql
    assert params[0] == datetime(2026, 1, 1)
    assert params[-4:] == [Q, 'flow', NH, 'nitrogen']


@pytest.mark.parametrize('rows', [[], [(0, Q, 41.7)], [(0,Q,float('nan')),(0,NH,20),(1,Q,41.7),(1,NH,20)]])
def test_empty_missing_partial_and_invalid_input_fail_closed(monkeypatch, rows):
    store, _ = fake_store(monkeypatch, rows)
    with pytest.raises(ValueError):
        history.load_history(MAPPING, 60, request())
    store.close.assert_called_once()


def test_resume_only_reads_remaining_window_and_completed_replay_needs_no_db(monkeypatch):
    plan = request()
    plan['completed'] = 1
    store, cursor = fake_store(monkeypatch, [(0,Q,41.7),(0,NH,20)])
    windows = history.load_history(MAPPING, 60, plan)
    assert len(windows) == 1 and windows[0].duration_ms == 30000
    assert cursor.execute.call_args.args[1][0] == datetime(2026, 1, 1, 0, 1)
    plan['completed'] = 2
    assert history.load_history(MAPPING, 60, plan) == []
    assert store.connect.call_count == 1


def test_db_failure_closes_connection(monkeypatch):
    store, cursor = fake_store(monkeypatch, [])
    cursor.execute.side_effect = RuntimeError('database unavailable')
    with pytest.raises(RuntimeError):
        history.load_history(MAPPING, 60, request())
    store.close.assert_called_once()


def test_api_rejects_missing_history_range_and_unknown_mode(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.live_sumo import router
    from liveSimulation import liveSimulation as live
    app = FastAPI(); app.include_router(router, prefix='/api')
    monkeypatch.setattr(live, '_session', None)
    client = TestClient(app)
    for extra in ({'mode':'history_then_live'}, {'mode':'wrong'}):
        response = client.post('/api/sumo/live/start', json={'mapping':MAPPING, **extra})
        assert response.status_code == 422
    assert live._session is None


def test_open_ended_request_requires_only_start():
    plan = history.history_request('2026-01-01T10:00:00+10:00', None, 1)
    assert plan['follow'] and plan['end'] is None and plan['completed'] == 0
    assert not plan['caught_up']
    with pytest.raises(ValueError, match='future'):
        history.history_request('2999-01-01T00:00Z', None, 1)


def test_follow_uses_collection_frontier_and_holds_missing_inputs(monkeypatch):
    plan = history.history_request('2026-01-01T00:00Z', None, 1)
    store, cursor = fake_store(monkeypatch, [])
    cursor.fetchall.side_effect = [
        [(Q, datetime(2026,1,1,0,2,10)), (NH, datetime(2026,1,1,0,1,30))],
        [(0,Q,41.7),(0,NH,20)],
    ]
    windows = history.load_available_history(MAPPING,60,plan)
    assert len(windows)==2 and windows[0].duration_ms==60000
    assert windows[1].values == windows[0].values
    assert windows[1].held_inputs == tuple(sorted(MAPPING))
    assert windows[0].timestamp=='2026-01-01T00:01:00+00:00'
    assert cursor.execute.call_count==2
    assert cursor.execute.call_args.args[1][3]==datetime(2026,1,1,0,2)


@pytest.mark.parametrize('rows', [[],
    [(Q,datetime(2026,1,1,0,0,59)),(NH,datetime(2026,1,1,0,0,59))]])
def test_follow_waits_for_missing_or_incomplete_newest_data(monkeypatch, rows):
    plan=history.history_request('2026-01-01T00:00Z',None,1)
    store,cursor=fake_store(monkeypatch,rows)
    assert history.load_available_history(MAPPING,60,plan)==[]
    assert cursor.execute.call_count==1
    store.close.assert_called_once()


def test_follow_queries_only_unprocessed_data_and_limits_chunk_size(monkeypatch):
    plan=history.history_request('2026-01-01T00:00Z',None,1)
    plan['completed']=3
    fake_store(monkeypatch,[(Q,datetime(2026,2,1)),(NH,datetime(2026,2,1))])
    from unittest.mock import Mock
    reader=Mock(return_value=['window'])
    monkeypatch.setattr(history,'load_history',reader)
    assert history.load_available_history(MAPPING,60,plan)==['window']
    selection=reader.call_args.args[2]
    assert selection['completed']==3
    assert (history.parse_time(selection['end'])-history.parse_time(plan['start'])).total_seconds()==2003*60


@pytest.mark.parametrize('end', ['', '   ', None])
def test_removed_end_input_is_optional_even_for_older_clients(end):
    plan=history.history_request(' 2026-01-01T08:00:00+08:00 ',end,1)
    assert plan['follow'] and plan['end'] is None
    assert plan['start']=='2026-01-01T00:00:00+00:00'


def test_time_errors_identify_start_and_end_without_guessing_timezone():
    with pytest.raises(ValueError,match='History start is missing'):
        history.history_request('',None,1)
    with pytest.raises(ValueError,match='History start is missing its timezone'):
        history.history_request('2026-01-01T08:00',None,1)
    with pytest.raises(ValueError,match='History end has an invalid format'):
        history.history_request('2026-01-01T08:00+08:00','invalid',1)
    assert history.parse_time(datetime(2026,1,1,tzinfo=timezone.utc))==datetime(2026,1,1,tzinfo=timezone.utc)


def test_internal_empty_and_partial_intervals_hold_model_units_then_recover(monkeypatch):
    plan = history.history_request('2026-01-01T00:00Z', '2026-01-01T00:04Z', 1)
    fake_store(monkeypatch, [(0,Q,41.7),(0,NH,20),(2,NH,30),(3,Q,83.4),(3,NH,40)])
    windows = history.load_history(MAPPING, 60, plan)
    assert [w.values[Q] for w in windows] == pytest.approx([1000,1000,1000,2000])
    assert [w.values[NH] for w in windows] == [20,20,30,40]
    assert [w.held_inputs for w in windows] == [(),tuple(sorted(MAPPING)),(Q,),()]
    assert [w.timestamp for w in windows] == [f'2026-01-01T00:0{i}:00+00:00' for i in range(1,5)]
    assert 'last_inputs' not in plan  # prefetch must not advance the completed cursor


def test_checkpoint_inputs_seed_next_query_without_scaling_again(monkeypatch):
    plan = request()
    plan.update(completed=1, last_inputs={Q:1000,NH:20})
    fake_store(monkeypatch, [])
    window, = history.load_history(MAPPING,60,plan)
    assert window.values == {Q:1000,NH:20}
    assert window.held_inputs == tuple(sorted(MAPPING))


def test_missing_initial_values_cannot_be_filled_from_future(monkeypatch):
    fake_store(monkeypatch, [(1,Q,41.7),(1,NH,20)])
    with pytest.raises(ValueError, match='no previous input'):
        history.load_history(MAPPING,60,request())


def test_follow_missing_sensor_does_not_block_initialized_model(monkeypatch):
    plan = history.history_request('2026-01-01T00:00Z',None,1)
    plan.update(completed=1, last_inputs={Q:1000,NH:20})
    _, cursor = fake_store(monkeypatch, [])
    cursor.fetchall.side_effect = [[(Q,datetime(2026,1,1,0,2,10))], [(0,Q,83.4)]]
    window, = history.load_available_history(MAPPING,60,plan)
    assert window.values[Q] == pytest.approx(2000)
    assert window.values[NH] == 20
    assert window.held_inputs == (NH,)
    assert plan['input_frontier']['missing_inputs'] == [NH]
    assert "r.quality='good'" not in cursor.execute.call_args_list[0].args[0]


def test_negative_history_input_becomes_zero_and_is_not_held(monkeypatch):
    _, cursor = fake_store(monkeypatch, [(0,Q,-334.88330078125),(0,NH,20),(1,Q,41.7),(1,NH,20)])
    windows = history.load_history(MAPPING,60,request())
    assert windows[0].values[Q] == 0
    assert windows[0].held_inputs == ()
    assert windows[1].values[Q] == pytest.approx(1000)
    # Clamp each raw observation before AVG, not the final interval average.
    assert 'AVG(GREATEST(r.numeric_value, 0))' in cursor.execute.call_args.args[0]
