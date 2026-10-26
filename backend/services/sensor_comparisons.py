"""Read measured nitrate independently of model inputs and simulation progress."""
from datetime import timedelta, timezone
import math
import os

from database.store import Store, dbtime
from services.historical_inputs import parse_time

LIVE_EXTRA_OUTPUTS = tuple(f'Sumo__Plant__CSTR{lane}_4__{name}'
                          for lane in (3, 4) for name in ('SNOx', 'SNHx')) + tuple(
    f'Sumo__Plant__CSTR{lane}_10__{name}'
    for lane in (3, 4) for name in ('XTSS', 'XVSS'))
# Only mappings confirmed in the existing collector CSV; no shared NHx assumed.
COMPARISON_SENSORS = {
    'sensor:Sumo__Plant__CSTR3_4__SNOx': (
        'Sumo__Plant__CSTR3_4__param__Nitrate_sensor', 'SiemensEth.PLC200.II_anoxic_nitrate'),
    'sensor:Sumo__Plant__CSTR3_10__SNOx': (
        'Sumo__Plant__CSTR3_10__param__Nitrate_sensor', 'SiemensEth.PLC200.II_aerobic_nitrate'),
    'lab:Sumo__Plant__CSTR3_10__XTSS': ('Sumo__Plant__CSTR3_10__param__MLSS_lab', 'MySQL.SWC3.parm_mlss.parm_mlss__1_'),
    'lab:Sumo__Plant__CSTR3_10__XVSS': ('Sumo__Plant__CSTR3_10__param__MLVSS_lab', 'MySQL.SWC3.parm_mlvss.parm_mlvss__1_'),
    'lab:Sumo__Plant__CSTR4_10__XTSS': ('Sumo__Plant__CSTR4_10__param__MLSS_lab', 'MySQL.SWC4.parm_mlss.parm_mlss__1_'),
    'lab:Sumo__Plant__CSTR4_10__XVSS': ('Sumo__Plant__CSTR4_10__param__MLVSS_lab', 'MySQL.SWC4.parm_mlvss.parm_mlvss__1_'),

}


def comparison_database():
    # Measurement source is independent of the model's checkpoint/history DB.
    return os.getenv('SUMO_COMPARISON_DATABASE', 'sumo_web_database')


STORED_OUTPUT = 'Sumo__Plant__CSTR3_4__SNOx'


def read_stored_output(cursor, snapshot):
    """Restore only this run, never expose results beyond its current progress."""
    hours = (snapshot.get('result') or {}).get('time_h') or []
    if not hours or not snapshot.get('id'):
        return {}
    cursor.execute("""SELECT s.sensor_read_at, d.numeric_value
        FROM sumo_samples s
        JOIN sumo_runs r ON r.run_id=s.run_id
        JOIN sumo_variables v ON v.model_sha=r.model_sha AND v.variable_name=%s
        JOIN sumo_values d ON d.sample_id=s.id AND d.variable_id=v.id
        WHERE s.run_id=%s AND s.simulated_ms<=%s
          AND s.sensor_read_at IS NOT NULL
        ORDER BY s.simulated_ms""", (STORED_OUTPUT, snapshot['id'], round(max(hours)*3600000)))
    points = {}
    for stamp, value in cursor.fetchall():
        # MySQL DATETIME stores UTC; acquisition time is NOT simulation time.
        stamp = stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp
        points[stamp.isoformat()] = float(value) if value is not None and math.isfinite(float(value)) else None
    return {STORED_OUTPUT: {'timestamps': list(points), 'values': list(points.values())}}


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
            stored = read_stored_output(cursor, snapshot)
    finally:
        store.close()
    timestamps = [min(begin + timedelta(seconds=(i + 1) * aggregation), end).isoformat()
                  for i in range(count)]
    names = {pair[0]: key for key, pair in COMPARISON_SENSORS.items()}
    series = {key: {'timestamps': timestamps, 'values': [None] * count} for key in COMPARISON_SENSORS}
    for bucket, name, value in rows:
        if name in names and 0 <= int(bucket) < count and value is not None and math.isfinite(float(value)):
            series[names[name]]['values'][int(bucket)] = float(value)
    return {**result, 'series': series, 'stored_series': stored, 'aggregation_seconds': aggregation}
