"""Step 1: fresh OPC values, then exact/as-of UTC database observations (raw units)."""
import asyncio
import math
from services.sensor_policy import normalize_reading
import logging
import time
from uuid import uuid4
import os
from datetime import datetime, timezone

from asyncua import Client
from database.store import Store, dbtime
from services.historical_inputs import mapping_filters
from services.sensor_inputs import SENSOR_COLUMNS


def database_readings(mapping, at):
    store = Store()
    result = []
    try:
        store.connect(database=os.getenv('SUMO_HISTORY_DATABASE', 'sumo_web_database'))
        with store.connection.cursor() as cursor:
            for column, node in mapping.items():
                filters, params = mapping_filters({column: node})
                # Exact timestamp wins; otherwise latest earlier good observation.
                # Never use future observations, averages, or already scaled values.
                cursor.execute('''SELECT r.numeric_value,r.acquired_at
                    FROM raw_data r JOIN raw_variables v ON v.id=r.variable_id
                    WHERE ''' + filters[0] + ''' AND r.acquired_at <= %s
                    AND r.quality='good' AND r.numeric_value IS NOT NULL
                    AND r.numeric_value >= -1.7976931348623157e308
                    AND r.numeric_value <= 1.7976931348623157e308
                    ORDER BY r.acquired_at DESC,r.id DESC LIMIT 1''', [*params, dbtime(at)])
                row = cursor.fetchone()
                if row is None:
                    continue
                value, timestamp = float(row[0]), row[1].replace(tzinfo=timezone.utc)
                if not math.isfinite(value) or timestamp > at:
                    continue
                result.append(dict(column=column, node_id=node, value=normalize_reading(column, value),
                    timestamp=timestamp.isoformat(),
                    source='database_current' if dbtime(timestamp) == dbtime(at) else 'database_previous',
                    age_seconds=(at-timestamp).total_seconds()))
    finally:
        store.close()
    return result


async def read_resilient_snapshot(mapping, *, opc_timeout=60):
    if not mapping or any(k not in SENSOR_COLUMNS for k in mapping):
        raise ValueError('Configure supported sensor mappings.')
    if any(not isinstance(v, str) or not v.strip() for v in mapping.values()):
        raise ValueError('Every mapped parameter requires an OPC UA node ID.')
    snapshot_id = uuid4().hex[:8]
    started = time.monotonic()
    logging.info("Step1 snapshot %s started: %s mapped sensors", snapshot_id, len(mapping))
    at = datetime.now(timezone.utc)
    readings, errors = {}, {}

    async def opc():
        client = Client(url=os.getenv('KEPSERVER_OPC_URL', 'opc.tcp://127.0.0.1:49320'), timeout=15)
        # Match the 60-second session lifetime granted by the site KEPServer.
        # This is separate from request and overall snapshot timeouts.
        client.session_timeout = 60000
        async with client as client:
            for column, node in mapping.items():
                try:
                    value = float(await client.get_node(node).read_value())
                    if not math.isfinite(value):
                        raise ValueError('Non-finite sensor value')
                    readings[column] = dict(column=column, node_id=node, value=normalize_reading(column, value),
                        timestamp=datetime.now(timezone.utc).isoformat(), source='opcua', age_seconds=0)
                except Exception as exc:
                    errors[column] = f'{type(exc).__name__}: {exc}'
                    logging.warning("Step1 snapshot %s OPC input unavailable: %s (%s): %s; trying database",
                                    snapshot_id, column, node, errors[column])
    try:
        await asyncio.wait_for(opc(), timeout=opc_timeout)
    except Exception as exc:
        logging.warning("Step1 snapshot %s OPC session/read failed: %s: %s; trying database for missing inputs",
                        snapshot_id, type(exc).__name__, exc)
        for column in mapping:
            if column not in readings:
                errors.setdefault(column, f'{type(exc).__name__}: {exc}')
    missing = {k: v for k, v in mapping.items() if k not in readings}
    db_error = None
    if missing:
        try:
            for reading in await asyncio.to_thread(database_readings, missing, at):
                reading['opc_error'] = errors.get(reading['column'], 'No OPC reading')
                readings[reading['column']] = reading
        except Exception as exc:
            db_error = f'{type(exc).__name__}: {exc}'
    unresolved = [k for k in mapping if k not in readings]
    logging.log(logging.WARNING if unresolved else logging.INFO,
                "Step1 snapshot %s completed in %.2fs: opcua=%s database=%s unavailable=%s",
                snapshot_id, time.monotonic()-started,
                sum(r['source']=='opcua' for r in readings.values()),
                sum(r['source'].startswith('database') for r in readings.values()), len(unresolved))
    if unresolved:
        logging.error("Step1 snapshot %s unresolved inputs: %s; database: %s",
                      snapshot_id, ', '.join(unresolved), db_error or 'No earlier good observations')
    return dict(readings=[readings[k] for k in mapping if k in readings], checked_at=at.isoformat(),
                unavailable=[dict(column=k, node_id=v, reason=errors.get(k, 'No OPC reading'),
                    database_error=db_error or 'No good database observation at or before requested time')
                    for k, v in mapping.items() if k not in readings])
