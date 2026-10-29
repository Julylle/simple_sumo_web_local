"""Anchor database replay to the model state saved at the checkpoint boundary."""
from datetime import timedelta
import os
import math

from services.historical_inputs import parse_time, history_time


def checkpoint_boundary(metadata):
    if metadata.get('sensor_boundary_at'):
        return parse_time(metadata['sensor_boundary_at']), metadata.get('boundary_source', 'recorded_boundary')
    history = metadata.get('history')
    if history:
        boundary = history_time(history, metadata['simulated_ms'])
        # Legacy fixed-range runs could already have switched to direct OPC.
        # Their later states belong to the fresh input clock, not the old range.
        if history.get('follow') or not history.get('end') or boundary <= parse_time(history['end']):
            return boundary, 'historical_boundary'
    # Direct-live readings were taken at the beginning of the interval; the
    # saved model state is at its end. Do not replay that interval twice.
    read_at = metadata.get('input_read_at')
    if not read_at:
        timestamps = (metadata.get('result') or {}).get('sensor_timestamps') or []
        read_at = timestamps[-1] if timestamps else None
    if read_at:
        return (parse_time(read_at) + timedelta(minutes=metadata['interval_minutes']),
                'direct_live_input_plus_interval')
    # Very old bundles have no sensor timestamp. Preserve the model and use
    # their save time as an explicitly labelled approximate replay boundary.
    return parse_time(metadata['saved_at']), 'legacy_save_time_estimate'


def resume_history(metadata):
    boundary, source = checkpoint_boundary(metadata)
    previous = metadata.get('history') or {}
    last_inputs = dict(previous.get('last_inputs') or {})
    # A legacy fixed-history run may have later used fresh direct-live inputs.
    # Its final saved parameter samples supersede older history input values.
    for key, values in (metadata.get('result') or {}).get('variables', {}).items():
        if key in metadata.get('mapping', {}) and values and isinstance(values[-1], (int, float)):
            if math.isfinite(values[-1]) and values[-1] >= 0:
                last_inputs[key] = values[-1]
    return {
        'start': boundary.isoformat(), 'end': None, 'completed': 0, 'total': 0,
        'follow': True, 'caught_up': False,
        # Application time continues from the checkpoint; native job time restarts
        # at zero. The replay cursor counts only intervals after this boundary.
        'model_time_offset_ms': metadata['simulated_ms'],
        'database': previous.get('database') or os.getenv('SUMO_HISTORY_DATABASE', 'sumo_web_database'),
        'resume_boundary_source': source,
        'last_inputs': last_inputs,
        'last_input_provenance': dict(previous.get('last_input_provenance') or {}),
        'held_intervals': previous.get('held_intervals', 0),
    }
