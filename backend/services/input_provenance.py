"""Describe actual applied model inputs without consulting preview sensor data."""
from datetime import timedelta
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


