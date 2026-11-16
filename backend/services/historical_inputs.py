"""Bulk indexed history reads. Raw values use the same conversion as live OPC inputs."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import math
import os
import re

from database.store import Store, dbtime
from services.model_inputs import scale_model_inputs
from services.sensor_policy import SIDEFLOW_COLUMN, SIDEFLOW_NEGATIVE_VALUE, negative_details


def parse_time(value, field='History timestamp'):
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f'{field} is missing. Select a history start time and retry.')
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.strip().replace('Z', '+00:00'))
    except (ValueError, AttributeError, TypeError) as exc:
        raise ValueError(f'{field} has an invalid format. Expected an ISO timestamp such as '
                         '2026-10-26T08:00:00+08:00 or 2026-10-26T00:00:00Z.') from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f'{field} is missing its timezone. Reload the updated web page; '
                         'it converts local dates automatically. API clients must include Z or an offset such as +08:00.')
    return parsed.astimezone(timezone.utc)


def history_time(history, simulated_ms):
    return parse_time(history['start']) + timedelta(
        milliseconds=float(simulated_ms) - history.get('model_time_offset_ms', 0))


def history_request(start, end, interval_minutes):
    begin = parse_time(start, 'History start')
    # Older clients may submit the removed end-time input as an empty string.
    if isinstance(end, str) and not end.strip():
        end = None
    if end is None:
        if begin > datetime.now(timezone.utc):
            raise ValueError('History start cannot be in the future.')
        if begin.microsecond % 1000:
            raise ValueError('History times must have millisecond precision or coarser.')
        return {'start': begin.isoformat(), 'end': None, 'total': 0, 'completed': 0,
                'follow': True, 'caught_up': False,
                'database': os.getenv('SUMO_HISTORY_DATABASE', 'sumo_web_database')}
    # Keep existing fixed-range checkpoints resumable.
    finish = parse_time(end, 'History end')
    if begin.microsecond % 1000 or finish.microsecond % 1000:
        raise ValueError('History times must have millisecond precision or coarser.')
    if finish <= begin:
        raise ValueError('History end must be after start.')
    if finish > datetime.now(timezone.utc):
        raise ValueError('History end cannot be in the future.')
    total = math.ceil((finish - begin).total_seconds() / (interval_minutes * 60))
    if total > 100000:
        raise ValueError('Select at most 100,000 history intervals, or increase LimitTime.')
    return {'start': begin.isoformat(), 'end': finish.isoformat(), 'total': total,
            'completed': 0, 'database': os.getenv('SUMO_HISTORY_DATABASE', 'sumo_web_database')}


@dataclass(frozen=True)
class HistoryWindow:
    duration_ms: int
    timestamp: str
    values: dict[str, float]
    held_inputs: tuple[str, ...] = ()
    provenance: dict = field(default_factory=dict)


def load_history(mapping, interval_seconds, history):
    """Aggregate in MySQL, not per sensor/per interval network round trips.

    Use acquisition UTC time and [start,end), replace negative readings per sensor policy before averaging good numeric values.
    Missing/invalid inputs retain their previous interval value in model units.
    Invalid recorded samples contribute that prior value to the interval mean.
    The first interval needs valid inputs or checkpoint-provided previous values.
    Resume queries only the unprocessed part of the original selected range.
    """
    start, end = parse_time(history['start'], 'Saved history start'), parse_time(history['end'], 'Saved history end')
    completed = history['completed']
    begin = start + timedelta(seconds=completed * interval_seconds)
    if begin >= end:
        return []
    filters, params = mapping_filters(mapping)
    valid = "r.quality='good' AND r.numeric_value IS NOT NULL AND ABS(r.numeric_value) <= 1.7976931348623157e308"
    sql = f'''SELECT FLOOR(TIMESTAMPDIFF(MICROSECOND,%s,r.acquired_at)/%s) AS bucket,
                    v.sumo_name, AVG(CASE WHEN {valid} AND v.sumo_name='{SIDEFLOW_COLUMN}' AND r.numeric_value < 0
                         THEN {SIDEFLOW_NEGATIVE_VALUE}
                         WHEN {valid} THEN GREATEST(r.numeric_value, 0) END),
                    MIN(r.acquired_at), MAX(r.acquired_at), COUNT(*),
                    SUM(CASE WHEN {valid} AND r.numeric_value < 0 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN {valid} THEN 0 ELSE 1 END),
                    MAX(CASE WHEN {valid} THEN NULL ELSE COALESCE(NULLIF(r.error,''), CONCAT('Invalid recorded input; quality=',r.quality)) END)
             FROM raw_data r JOIN raw_variables v ON v.id=r.variable_id
             WHERE r.acquired_at >= %s AND r.acquired_at < %s
               AND (''' + ' OR '.join(filters) + ''')
             GROUP BY bucket,v.sumo_name ORDER BY bucket,v.sumo_name'''
    store = Store()
    read_error = None
    try:
        store.connect(database=history['database'])
        with store.connection.cursor() as cursor:
            cursor.execute(sql, [dbtime(begin), interval_seconds * 1000000,
                                 dbtime(begin), dbtime(end), *params])
            rows = cursor.fetchall()
    except Exception as exc:
        read_error = f'{type(exc).__name__}: {exc}'
        rows = []
    finally:
        store.close()
    grouped = {}
    collected = {}
    for row in rows:
        index, name, value = row[:3]
        grouped.setdefault(int(index), {})[name] = float(value) if value is not None else float('nan')
        collected.setdefault(int(index), {})[name] = {
            'source': 'database_interval',
            'collected_from': row[3].replace(tzinfo=timezone.utc).isoformat() if len(row)>3 and row[3] else None,
            'collected_to': row[4].replace(tzinfo=timezone.utc).isoformat() if len(row)>4 and row[4] else None,
            'sample_count': int(row[5]) if len(row)>5 else None,
            'invalid_count': int(row[7]) if len(row)>7 and row[7] else 0,
            'read_error': row[8] if len(row)>8 else None,
            **({**negative_details(name), 'reason': 'Negative sensor readings replaced before averaging',
                'negative_count': int(row[6])} if len(row)>6 and row[6] else {}),
        }
    windows = []
    previous = {key: float(value) for key, value in history.get('last_inputs', {}).items()
                if key in mapping and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0}
    previous_provenance = dict(history.get('last_input_provenance') or {})
    count = math.ceil((end - begin).total_seconds() / interval_seconds)
    for index in range(count):
        left = begin + timedelta(seconds=index * interval_seconds)
        right = min(left + timedelta(seconds=interval_seconds), end)
        values = grouped.get(index, {})
        invalid = {key: value for key, value in values.items() if not math.isfinite(value)}
        values = {key: value for key, value in values.items() if key not in invalid}
        missing = set(mapping) - values.keys()
        bad_samples = {key for key, detail in collected.get(index, {}).items() if detail.get('invalid_count')}
        unseeded = (missing | bad_samples) - previous.keys()
        if unseeded:
            if read_error:
                raise RuntimeError('Sensor database read failed with no previous input to reuse: ' + read_error)
            raise ValueError(f'History data missing at {left.isoformat()} with no previous input to reuse: ' + ', '.join(sorted(unseeded)))
        converted = scale_model_inputs([{'column': name, 'value': value} for name, value in values.items()])
        converted.update({key: previous[key] for key in missing})
        provenance = dict(collected.get(index, {}))
        for key, value in values.items():
            if value < 0:
                provenance.setdefault(key, {}).update(**negative_details(key), reason='Negative sensor reading', raw_value=value)
        for key in bad_samples - missing:
            detail = provenance[key]
            count_bad, count_all = detail['invalid_count'], detail['sample_count']
            converted[key] = converted[key] * ((count_all - count_bad) / count_all) + previous[key] * (count_bad / count_all)
            detail.update(treatment='held_previous_samples', reason=detail.get('read_error') or 'Invalid recorded samples',
                          previous_model_value=previous[key])
        for key in missing:
            prior = previous_provenance.get(key, {})
            provenance[key] = {**{k: prior[k] for k in ('collected_from', 'collected_to') if k in prior},
                               'source': 'held_previous', 'treatment': 'held_previous',
                               'reason': read_error or collected.get(index, {}).get(key, {}).get('read_error') or ('Non-finite sensor reading: ' + repr(invalid[key]) if key in invalid else 'No valid recorded input in interval'),
                               'original_source': previous_provenance.get(key, {}).get('original_source') or previous_provenance.get(key, {}).get('source', 'checkpoint_unknown')}
        windows.append(HistoryWindow(round((right-left).total_seconds()*1000), right.isoformat(), converted, tuple(sorted(missing | bad_samples)), provenance))
        previous_provenance = provenance
        previous = converted
    return windows


def mapping_filters(mapping):
    filters, params = [], []
    for column, node in mapping.items():
        match = re.fullmatch(r'ns=\d+;s=(.+)', node)
        if not match:
            raise ValueError('History requires string OPC node IDs: ' + node)
        filters.append('(v.sumo_name=%s AND v.opc_tag=%s)')
        params.extend([column, match.group(1)])
    return filters, params


def load_available_history(mapping, interval_seconds, history):
    """Find the latest collected interval, then read a chunk with held inputs.

    Indexed latest-row lookups avoid repeatedly scanning the complete raw archive.
    A partial newest interval is held back until acquisition crosses its boundary.
    """
    filters, params = mapping_filters(mapping)
    sql = """SELECT v.sumo_name, MAX((
        SELECT r.acquired_at FROM raw_data r
        WHERE r.variable_id=v.id AND r.acquired_at <= UTC_TIMESTAMP(6)
        ORDER BY r.acquired_at DESC LIMIT 1))
        FROM raw_variables v WHERE """ + ' OR '.join(filters) + ' GROUP BY v.sumo_name'
    store = Store()
    try:
        store.connect(database=history['database'])
        with store.connection.cursor() as cursor:
            cursor.execute(sql, params)
            latest = {name: value.replace(tzinfo=timezone.utc) for name, value in cursor.fetchall() if value is not None}
    except Exception as exc:
        reason = f'{type(exc).__name__}: {exc}'
        previous = history.get('last_inputs', {})
        if any(key not in previous or not math.isfinite(previous[key]) for key in mapping):
            raise RuntimeError('Sensor database read failed with no previous input to reuse: ' + reason) from exc
        right = parse_time(history['start']) + timedelta(seconds=(history['completed'] + 1) * interval_seconds)
        history['caught_up'] = True  # throttle retries even while the database is unavailable
        if right > datetime.now(timezone.utc):
            return []
        return [HistoryWindow(interval_seconds * 1000, right.isoformat(),
            {key: previous[key] for key in mapping}, tuple(sorted(mapping)),
            {key: {'source': 'held_previous', 'treatment': 'held_previous', 'reason': reason}
             for key in mapping})]
    finally:
        store.close()
    missing = sorted(set(mapping) - latest.keys())
    newest = max(latest.values()) if latest else None
    start = parse_time(history['start'])
    available = (math.floor((newest - start).total_seconds() / interval_seconds)
                 if newest is not None else 0)
    # Reuse this query: no additional database polling for UI diagnostics.
    history['input_frontier'] = {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'latest_collection_at': newest.isoformat() if newest is not None else None,
        'complete_until': (start + timedelta(seconds=available * interval_seconds)).isoformat()
                          if available > 0 else None,
        'missing_inputs': missing,
    }
    if not latest:
        return []
    if available <= history['completed']:
        return []
    # Bound memory and query size while repeatedly catching up to a moving frontier.
    count = min(available, history['completed'] + 2000)
    end = start + timedelta(seconds=count * interval_seconds)
    return load_history(mapping, interval_seconds, {**history, 'end': end.isoformat()})
