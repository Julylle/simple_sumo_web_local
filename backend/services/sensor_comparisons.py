"""Read measured nitrate independently of model inputs and simulation progress."""
from datetime import timedelta
import math
import os

from database.store import Store, dbtime
from services.historical_inputs import parse_time

LIVE_EXTRA_OUTPUTS = tuple(f'Sumo__Plant__CSTR{lane}_4__{name}'
                          for lane in (3, 4) for name in ('SNOx', 'SNHx'))
# Only mappings confirmed in the existing collector CSV; no shared NHx assumed.
COMPARISON_SENSORS = {
    'sensor:Sumo__Plant__CSTR3_4__SNOx': (
        'Sumo__Plant__CSTR3_4__param__Nitrate_sensor', 'SiemensEth.PLC200.II_anoxic_nitrate'),
    'sensor:Sumo__Plant__CSTR3_10__SNOx': (
        'Sumo__Plant__CSTR3_10__param__Nitrate_sensor', 'SiemensEth.PLC200.II_aerobic_nitrate'),
}


def comparison_database():
    # Measurement source is independent of the model's checkpoint/history DB.
    return os.getenv('SUMO_COMPARISON_DATABASE', 'sumo_web_database')


def read_comparisons(snapshot):
    stamps = (snapshot.get('result') or {}).get('sensor_timestamps') or []
    times = [parse_time(value) for value in stamps if value]
    result = {'run_id': snapshot.get('id'), 'series': {}, 'aggregation_seconds': None, 'database': comparison_database()}
    if not times:
        return result
    interval = snapshot.get('interval_minutes', 1) * 60
    first_is_initial = ((snapshot.get('result') or {}).get('time_h') or [None])[0] == 0
    begin = min(times) if first_is_initial else min(times) - timedelta(seconds=interval)
    end = max(times)
    if end <= begin:
        return result
    span = (end - begin).total_seconds()
    # Bound response size for long-running simulations; keep the interval means
    # explicitly labelled and never include observations after model progress.
    aggregation = interval * max(1, math.ceil(span / (5000 * interval)))
    count = math.ceil(span / aggregation)
    filters = ' OR '.join('(v.sumo_name=%s AND v.opc_tag=%s)' for _ in COMPARISON_SENSORS)
    params = [dbtime(begin), aggregation * 1000000, dbtime(begin), dbtime(end)]
    params.extend(value for pair in COMPARISON_SENSORS.values() for value in pair)
    sql = '''SELECT FLOOR(TIMESTAMPDIFF(MICROSECOND,%s,r.acquired_at)/%s) AS bucket,
        v.sumo_name, AVG(r.numeric_value)
        FROM raw_data r JOIN raw_variables v ON v.id=r.variable_id
        WHERE r.acquired_at >= %s AND r.acquired_at < %s
          AND r.quality='good' AND r.numeric_value IS NOT NULL
          AND (''' + filters + ') GROUP BY bucket,v.sumo_name ORDER BY bucket,v.sumo_name'
    store = Store()
    try:
        store.connect(database=result['database'])
        with store.connection.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()
    finally:
        store.close()
    timestamps = [min(begin + timedelta(seconds=(i + 1) * aggregation), end).isoformat()
                  for i in range(count)]
    names = {pair[0]: key for key, pair in COMPARISON_SENSORS.items()}
    series = {key: {'timestamps': timestamps, 'values': [None] * count} for key in COMPARISON_SENSORS}
    for bucket, name, value in rows:
        if name in names and 0 <= int(bucket) < count and value is not None and math.isfinite(float(value)):
            series[names[name]]['values'][int(bucket)] = float(value)
    return {**result, 'series': series, 'aggregation_seconds': aggregation}
