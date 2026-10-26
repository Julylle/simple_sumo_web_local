from datetime import datetime, timezone
from unittest.mock import patch

from services.resume_history import checkpoint_boundary, resume_history
from services.historical_inputs import history_time
from services import live_checkpoint as cp
from liveSimulation import liveSimulation as live
from test_live_checkpoint import session, Q


def test_direct_live_uses_end_of_last_applied_interval():
    metadata = {'simulated_ms':3600000,'interval_minutes':1,'saved_at':'2026-10-26T08:00:02Z',
                'result':{'sensor_timestamps':['2026-10-26T08:00:00Z']}}
    history = resume_history(metadata)
    assert history['start'] == '2026-10-26T08:01:00+00:00'
    assert history['model_time_offset_ms'] == 3600000
    assert history['completed'] == 0 and history['follow'] and not history['caught_up']
    assert history_time(history,3660000) == datetime(2026,10,26,8,2,tzinfo=timezone.utc)


def test_fixed_history_partial_tail_and_repeated_resumes_keep_time_continuous():
    metadata = {'simulated_ms':90000,'interval_minutes':1,
        'history':{'start':'2026-01-01T00:00Z','end':'2026-01-01T00:01:30Z',
                   'completed':2,'database':'sumo_web_database','last_inputs':{Q:1000}}}
    first = resume_history(metadata)
    assert first['start'] == '2026-01-01T00:01:30+00:00'
    assert first['end'] is None and first['last_inputs'] == {Q:1000}
    assert history_time(first,150000).isoformat() == '2026-01-01T00:02:30+00:00'
    second = resume_history({**metadata,'simulated_ms':150000,'history':first})
    assert second['start'] == '2026-01-01T00:02:30+00:00'
    assert history_time(second,210000).isoformat() == '2026-01-01T00:03:30+00:00'


def test_explicit_boundary_wins_and_legacy_fallback_is_labelled():
    metadata = {'sensor_boundary_at':'2026-01-01T08:00+08:00','simulated_ms':60000,
        'interval_minutes':1,'saved_at':'2026-01-01T01:00Z'}
    assert resume_history(metadata)['start'] == '2026-01-01T00:00:00+00:00'
    del metadata['sensor_boundary_at']
    assert checkpoint_boundary(metadata)[1] == 'legacy_save_time_estimate'
    assert resume_history(metadata)['start'] == '2026-01-01T01:00:00+00:00'


def test_resuming_direct_live_keeps_saved_bundle_results_and_identity(session,monkeypatch):
    session.update(times=[1/60], variables={Q:[1000]},
        sensor_timestamps=['2026-01-01T00:00:00Z'],input_read_at='2026-01-01T00:00:00Z')
    cp.save_checkpoint(session,session['model']['state'],60000)
    before = cp.checkpoint_path().read_bytes()
    monkeypatch.setattr(live,'_session',None)
    with patch.object(live.threading,'Thread'):
        restored=live.resume()
    try:
        assert cp.checkpoint_path().read_bytes() == before
        assert restored['id'] == session['id']
        assert restored['result']['variables'] == {Q:[1000]}
        assert restored['mode'] == 'history'
        assert restored['history']['database'] == 'sumo_web_database'
        assert restored['history']['start'] == '2026-01-01T00:01:00+00:00'
        assert restored['history']['last_inputs'] == {Q:1000}
        assert live._session['resume_ms'] == 60000
    finally:
        live._session['resume_folder'].cleanup()


def test_legacy_fixed_history_already_in_direct_live_uses_fresh_input_clock():
    metadata = {'simulated_ms':150000,'interval_minutes':1,
        'mapping':{Q:'ns=2;s=Q'},
        'result':{'sensor_timestamps':['2026-01-02T10:00:00Z'],'variables':{Q:[2000]}},
        'history':{'start':'2026-01-01T00:00Z','end':'2026-01-01T00:01:30Z','completed':2,'last_inputs':{Q:1000}}}
    assert resume_history(metadata)['start'] == '2026-01-02T10:01:00+00:00'
    assert resume_history(metadata)['last_inputs'] == {Q:2000}
