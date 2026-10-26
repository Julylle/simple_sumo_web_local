"""Parameterized MySQL writes; each time-step/batch commits atomically."""
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from pathlib import Path


def utcnow():
    return datetime.now(timezone.utc)


def dbtime(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def json_value(value):
    # Preserve nonnumeric values, arrays and non-finite source values losslessly as strings.
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return {'bytes_hex': value.hex()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def encode(value):
    return json.dumps(json_value(value), ensure_ascii=False, allow_nan=False)


def numeric(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


class Store:
    def __init__(self):
        self.connection = None

    def connect(self, create=False, database=None):
        import pymysql
        name = database if database is not None else os.getenv('MYSQL_DATABASE', 'sumo_timeseries')
        if not re.fullmatch(r'[A-Za-z0-9_]+', name):
            raise ValueError('MYSQL_DATABASE must contain only letters, digits and underscores.')
        kwargs = dict(host=os.getenv('MYSQL_HOST', '127.0.0.1'), port=int(os.getenv('MYSQL_PORT', '3306')),
                      user=os.getenv('MYSQL_USER', 'sumo'), password=os.environ['MYSQL_PASSWORD'],
                      charset='utf8mb4', connect_timeout=10, read_timeout=30, write_timeout=30,
                      autocommit=False)
        if create:
            with pymysql.connect(**kwargs) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_bin')
        self.connection = pymysql.connect(database=name, **kwargs)
        with self.connection.cursor() as cursor:
            cursor.execute("SET time_zone = '+00:00'")
        return self

    def close(self):
        if self.connection:
            self.connection.close()
            self.connection = None

    def _rollback_after_error(self):
        """Best-effort cleanup; a lost connection must not hide the write error."""
        try:
            self.connection.rollback()
        except Exception:
            logging.warning('MySQL rollback failed; preserving the original database error.',
                            exc_info=True)

    def initialize(self, display_timezone=None):
        with self.connection.cursor() as cursor:
            for statement in Path(__file__).with_name('schema.sql').read_text().split(';'):
                if statement.strip() and not statement.strip().startswith('CREATE OR REPLACE VIEW'):
                    cursor.execute(statement)
        self.connection.commit()
        from database.local_time import install_local_views
        install_local_views(self.connection, display_timezone)

    def register_mapping(self, digest, content, rows):
        try:
            with self.connection.cursor() as c:
                c.execute('INSERT IGNORE INTO mapping_versions VALUES (%s,%s,%s,%s)',
                          (digest, 'cx_opcua1124.csv', dbtime(utcnow()), content))
                c.executemany('INSERT IGNORE INTO raw_variables (mapping_sha,`row_number`,sumo_name,opc_tag,metadata) VALUES (%s,%s,%s,%s,%s)',
                              [(digest, i, r['SumoName'], r['OpcTag'], encode(r)) for i, r in enumerate(rows, 1)])
                c.execute('SELECT `row_number`,id FROM raw_variables WHERE mapping_sha=%s', (digest,))
                ids = dict(c.fetchall())
            self.connection.commit()
            return [ids[i] for i in range(1, len(rows)+1)]
        except Exception:
            self._rollback_after_error()
            raise

    def write_raw(self, batch_id, ids, samples):
        try:
            with self.connection.cursor() as c:
                c.executemany('''INSERT INTO raw_data
                    (batch_id,variable_id,acquired_at,source_timestamp,server_timestamp,status_code,quality,raw_value,numeric_value,scaled_value,error)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE batch_id=VALUES(batch_id)''',
                    [(batch_id, vid, dbtime(s['acquired_at']), dbtime(s.get('source_timestamp')),
                      dbtime(s.get('server_timestamp')), s.get('status_code'), s['quality'],
                      encode(s.get('raw_value')), s.get('numeric_value'), s.get('scaled_value'), s.get('error'))
                     for vid, s in zip(ids, samples, strict=True)])
            self.connection.commit()
        except Exception:
            self._rollback_after_error()
            raise

    def register_run(self, run_id, digest, model_name, catalog, mode, configuration):
        try:
            with self.connection.cursor() as c:
                c.execute('INSERT IGNORE INTO sumo_models VALUES (%s,%s,%s)', (digest, model_name, dbtime(utcnow())))
                for start in range(0, len(catalog), 500):
                    c.executemany('''INSERT IGNORE INTO sumo_variables
                        (model_sha,variable_name,variable_type,category,unit,metadata) VALUES (%s,%s,%s,%s,%s,%s)''',
                        [(digest, v['name'], v['type'], v['category'], v['unit'], encode(v)) for v in catalog[start:start+500]])
                c.execute('INSERT IGNORE INTO sumo_runs VALUES (%s,%s,%s,%s,%s)',
                          (run_id, digest, dbtime(utcnow()), mode, encode(configuration)))
                c.execute('SELECT model_sha,configuration FROM sumo_runs WHERE run_id=%s', (run_id,))
                existing_sha, existing_config = c.fetchone()
                if json.loads(existing_config).get('variable_catalog_sha') != configuration.get('variable_catalog_sha'):
                    raise ValueError('Recording scope changed. Restore the previous settings to resume, or start a new run.')
                if existing_sha != digest:
                    raise ValueError('Run ID belongs to a different model.')
                c.execute('SELECT variable_name,id FROM sumo_variables WHERE model_sha=%s', (digest,))
                ids = dict(c.fetchall())
            self.connection.commit()
            return {v['name']: ids[v['name']] for v in catalog}
        except Exception:
            self._rollback_after_error()
            raise

    def write_simulation(self, run_id, ids, simulated_ms, data, sensor_time=None, *, replace_previous=False):
        try:
            with self.connection.cursor() as c:
                c.execute('''INSERT INTO sumo_samples (run_id,simulated_ms,acquired_at,sensor_read_at)
                    VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id),
                    acquired_at=VALUES(acquired_at),sensor_read_at=VALUES(sensor_read_at)''',
                          (run_id, int(simulated_ms), dbtime(utcnow()), dbtime(sensor_time)))
                sample_id = c.lastrowid
                values = []
                for name, vid in ids.items():
                    value = data.get(name)
                    quality = 'missing' if name not in data else 'good'
                    if isinstance(value, float) and not math.isfinite(value):
                        quality = 'nonfinite'
                    values.append((sample_id, vid, encode(value), numeric(value), quality))
                for start in range(0, len(values), 500):
                    c.executemany('''INSERT INTO sumo_values VALUES (%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE value_json=VALUES(value_json),numeric_value=VALUES(numeric_value),quality=VALUES(quality)''', values[start:start+500])
                if replace_previous:
                    # Explicit child-first cleanup also supports older databases
                    # whose existing foreign key does not use ON DELETE CASCADE.
                    # Raw sensor tables and shared model catalogs are untouched.
                    c.execute('''DELETE v FROM sumo_values v
                        JOIN sumo_samples s ON s.id=v.sample_id WHERE s.run_id <> %s''', (run_id,))
                    c.execute('DELETE FROM sumo_samples WHERE run_id <> %s', (run_id,))
                    c.execute('DELETE FROM sumo_runs WHERE run_id <> %s', (run_id,))
            self.connection.commit()
        except Exception:
            self._rollback_after_error()
            raise
