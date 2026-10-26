"""Bulk indexed history reads. Raw values use the same conversion as live OPC inputs."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import os
import re

from database.store import Store, dbtime
from services.model_inputs import scale_model_inputs


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


def load_history(mapping, interval_seconds, history):
    """Aggregate in MySQL, not per sensor/per interval network round trips.

    Use acquisition UTC time and [start,end), average only good numeric values.
    All selected inputs must have data in every interval, including the tail.
    Resume queries only the unprocessed part of the original selected range.
    """
    start, end = parse_time(history['start'], 'Saved history start'), parse_time(history['end'], 'Saved history end')
    completed = history['completed']
    begin = start + timedelta(seconds=completed * interval_seconds)
    if begin >= end:
        return []
    filters, params = mapping_filters(mapping)
    sql = '''SELECT FLOOR(TIMESTAMPDIFF(MICROSECOND,%s,r.acquired_at)/%s) AS bucket,
                    v.sumo_name, AVG(r.numeric_value)
             FROM raw_data r JOIN raw_variables v ON v.id=r.variable_id
             WHERE r.acquired_at >= %s AND r.acquired_at < %s
               AND r.quality='good' AND r.numeric_value IS NOT NULL
               AND (''' + ' OR '.join(filters) + ''')
             GROUP BY bucket,v.sumo_name ORDER BY bucket,v.sumo_name'''
    store = Store()
    try:
        store.connect(database=history['database'])
        with store.connection.cursor() as cursor:
            cursor.execute(sql, [dbtime(begin), interval_seconds * 1000000,
                                 dbtime(begin), dbtime(end), *params])
            rows = cursor.fetchall()
    finally:
        store.close()
    grouped = {}
    for index, name, value in rows:
        grouped.setdefault(int(index), {})[name] = float(value)
    windows = []
    count = math.ceil((end - begin).total_seconds() / interval_seconds)
    for index in range(count):
        left = begin + timedelta(seconds=index * interval_seconds)
        right = min(left + timedelta(seconds=interval_seconds), end)
        values = grouped.get(index, {})
        missing = set(mapping) - values.keys()
        if missing:
            raise ValueError(f'History data missing at {left.isoformat()}: ' + ', '.join(sorted(missing)))
        if any(not math.isfinite(value) or value < 0 for value in values.values()):
            raise ValueError(f'Invalid historical input at {left.isoformat()}')
        converted = scale_model_inputs([{'column': name, 'value': value} for name, value in values.items()])
        windows.append(HistoryWindow(round((right-left).total_seconds()*1000), right.isoformat(), converted))
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
    """Find the latest complete interval shared by all inputs, then read a chunk.

    Indexed latest-row lookups avoid repeatedly scanning the complete raw archive.
    A partial newest interval is held back until acquisition crosses its boundary.
    """
    filters, params = mapping_filters(mapping)
    sql = """SELECT v.sumo_name, MAX((
        SELECT r.acquired_at FROM raw_data r
        WHERE r.variable_id=v.id AND r.quality='good' AND r.numeric_value IS NOT NULL
          AND r.acquired_at <= UTC_TIMESTAMP(6)
        ORDER BY r.acquired_at DESC LIMIT 1))
        FROM raw_variables v WHERE """ + ' OR '.join(filters) + ' GROUP BY v.sumo_name'
    store = Store()
    try:
        store.connect(database=history['database'])
        with store.connection.cursor() as cursor:
            cursor.execute(sql, params)
            latest = {name: value.replace(tzinfo=timezone.utc) for name, value in cursor.fetchall() if value is not None}
    finally:
        store.close()
    if set(mapping) - latest.keys():
        return []
    start = parse_time(history['start'])
    available = math.floor((min(latest.values()) - start).total_seconds() / interval_seconds)
    if available <= history['completed']:
        return []
    # Bound memory and query size while repeatedly catching up to a moving frontier.
    count = min(available, history['completed'] + 2000)
    end = start + timedelta(seconds=count * interval_seconds)
    return load_history(mapping, interval_seconds, {**history, 'end': end.isoformat()})
