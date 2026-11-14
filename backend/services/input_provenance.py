"""Describe actual applied model inputs without consulting preview sensor data."""
from datetime import timedelta
from services.sensor_policy import negative_details
from services.processing_history import filter_processing_records, should_record_input
from services.historical_inputs import parse_time


class ModelInputs(dict):
    """Model-unit values with the exact raw observations used to build them."""
    pass


def input_provenance(mapping, values, start_ms, duration_ms, window=None):
    details = window.provenance if window else getattr(values, 'provenance', {})
    end = parse_time(window.timestamp) if window else None
    return {'start_ms': start_ms, 'end_ms': start_ms + duration_ms,
            'interval_start': (end - timedelta(milliseconds=duration_ms)).isoformat() if end else None,
            'interval_end': end.isoformat() if end else None,
            'inputs': [dict(column=key, node_id=node, model_value=values[key],
                            **details.get(key, {'source': 'unknown'})) for key, node in mapping.items() if key in values]}




def process_readings(mapping, readings, previous=None):
    """Apply sensor policy once, retaining previous values already in model units."""
    import math
    from services.model_inputs import scale_model_inputs
    previous = previous or {}
    indexed = {r['column']: r for r in readings}
    values = ModelInputs()
    values.provenance = {}
    for column, node in mapping.items():
        reading = indexed.get(column, {'error': 'No observation returned'})
        detail = dict(source='opcua', collected_from=reading.get('timestamp'),
                      collected_to=reading.get('timestamp'), sample_count=1)
        reason = reading.get('error')
        raw = None
        if not reason:
            try:
                raw = float(reading['value'])
                if not math.isfinite(raw):
                    reason = 'Non-finite sensor reading: ' + repr(raw)
            except (ValueError, TypeError, KeyError) as exc:
                reason = f'{type(exc).__name__}: {exc}'
        if reason:
            old = previous.get(column)
            if not isinstance(old, (int, float)) or not math.isfinite(old):
                raise ValueError(f'{column} ({node}): {reason}; no previous valid model input to reuse')
            values[column] = old
            detail.update(source='held_previous', treatment='held_previous', reason=reason,
                          raw_value=repr(raw) if raw is not None else None)
        else:
            values[column] = scale_model_inputs([dict(column=column, value=raw)])[column]
            if raw < 0:
                detail.update(**negative_details(column), reason='Negative sensor reading', raw_value=raw)
        values.provenance[column] = detail
    return values


def record_treatments(session, provenance):
    """Append only when a window is selected for the native model, never during prefetch."""
    from datetime import datetime, timezone
    records = filter_processing_records(session.get('input_processing_records', []))
    session['input_processing_records'] = records
    sequence = max((row.get('sequence', 0) for row in records), default=0)
    for row in provenance['inputs']:
        if should_record_input(row.get('column')) and (row.get('treatment') or row.get('source') == 'held_previous'):
            sequence += 1
            records.append(dict(row, sequence=sequence,
                recorded_at=datetime.now(timezone.utc).isoformat(),
                start_ms=provenance['start_ms'], end_ms=provenance['end_ms'],
                interval_start=provenance.get('interval_start'), interval_end=provenance.get('interval_end')))
