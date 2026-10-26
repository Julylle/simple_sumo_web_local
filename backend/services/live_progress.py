"""Read-only progress diagnostics; never change simulation timestamps or cadence."""
from datetime import datetime, timezone


def live_progress(session, now=None):
    now = now or datetime.now(timezone.utc)
    history = session.get('history') or {}
    frontier = history.get('input_frontier') or {}
    timestamps = session.get('sensor_timestamps') or []
    model_at = timestamps[-1] if timestamps else None
    def lag(value):
        if not value:
            return None
        try:
            timestamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if timestamp.tzinfo is None:
                return None
            return max(0, (now - timestamp).total_seconds())
        except (ValueError, TypeError, AttributeError):
            return None
    model_lag = lag(model_at)
    complete_lag = lag(frontier.get('complete_until'))
    return {
        'observed_at': now.isoformat(), 'model_at': model_at,
        'model_lag_seconds': model_lag,
        'input_frontier': dict(frontier),
        'input_lag_seconds': lag(frontier.get('latest_collection_at')),
        'held_inputs': list(history.get('held_inputs', [])),
        'held_at': history.get('held_at'),
        'held_intervals': history.get('held_intervals', 0),
        'backlog_seconds': (max(0, model_lag - complete_lag)
                            if model_lag is not None and complete_lag is not None else None),
        'timings': dict(session.get('timings', {})),
    }
