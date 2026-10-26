"""Bulk indexed history reads. Raw values use the same conversion as live OPC inputs."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import os
import re

from database.store import Store, dbtime
from services.model_inputs import scale_model_inputs


def parse_time(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except (ValueError, AttributeError) as exc:
        raise ValueError('History timestamps must be ISO dates with a timezone.') from exc
    if parsed.tzinfo is None:
        raise ValueError('History timestamps must include a timezone.')
    return parsed.astimezone(timezone.utc)


def history_request(start, end, interval_minutes):
    begin, finish = parse_time(start), parse_time(end)
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
    start, end = parse_time(history['start']), parse_time(history['end'])
    completed = history['completed']
    begin = start + timedelta(seconds=completed * interval_seconds)
    if begin >= end:
        return []
    filters, params = [], []
    for column, node in mapping.items():
        match = re.fullmatch(r'ns=\d+;s=(.+)', node)
        if not match:
            raise ValueError('History requires string OPC node IDs: ' + node)
        filters.append('(v.sumo_name=%s AND v.opc_tag=%s)')
        params.extend([column, match.group(1)])
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
