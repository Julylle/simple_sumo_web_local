from datetime import datetime, timezone
from services.live_progress import live_progress


def test_progress_separates_collection_lag_from_model_backlog():
    session = {'sensor_timestamps':['2026-10-26T08:30:00Z'],
        'history':{'input_frontier':{'latest_collection_at':'2026-10-26T08:39:30Z',
            'complete_until':'2026-10-26T08:39:00Z'},'held_inputs':['Q'],'held_intervals':2},
        'timings':{'model_seconds':65,'checkpoint_seconds':2}}
    progress = live_progress(session,datetime(2026,10,26,8,40,tzinfo=timezone.utc))
    assert progress['model_lag_seconds'] == 600
    assert progress['input_lag_seconds'] == 30
    assert progress['backlog_seconds'] == 540
    assert progress['held_inputs'] == ['Q']
    assert progress['timings']['checkpoint_seconds'] == 2


def test_no_model_samples_is_not_reported_as_caught_up():
    assert live_progress({})['model_lag_seconds'] is None
    assert live_progress({'sensor_timestamps':[None]})['backlog_seconds'] is None
