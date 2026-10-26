"""Bounded MySQL writer, separate from native Scheduler callbacks."""
import copy
import hashlib
import os
import logging
from queue import Queue, Full
from threading import Thread, Event

from database.catalog import model_catalog
from database.store import Store


def write_error_detail(error):
    """Show actionable database errors without returning SQL or credentials."""
    code = error.args[0] if error.args and isinstance(error.args[0], int) else None
    reasons = {
        0: 'MySQL connection is unavailable. Check the backend traceback for the original connection or write failure.',
        1142: 'Database account lacks permission for the requested write or deletion.',
        1146: 'Required simulation tables are missing.',
        1451: 'Foreign key constraints prevent deletion of old simulation results.',
        1452: 'A referenced simulation run, sample or variable is missing.',
        1205: 'Database lock wait timed out.',
        1213: 'Database deadlock interrupted the transaction.',
        2006: 'MySQL connection closed during the write.',
        2013: 'MySQL connection was lost or the write query timed out.',
        1114: 'Database table or storage is full.',
        1290: 'MySQL is read-only or restricts this write.',
        1366: 'A simulation value is incompatible with the database column type.',
        1406: 'A simulation value exceeds the database column size.',
    }
    prefix = f'MySQL {code}: ' if code is not None else ''
    return prefix + reasons.get(code, 'Check the backend log for the original database error.')


class SimulationRecorder:
    def __init__(self, project, run_id, mode, configuration, extra_names=(), *, database=None):
        digest, catalog = model_catalog(project, extra_names)
        configuration = {**configuration, 'recording_database': database or os.getenv('MYSQL_DATABASE', 'sumo_timeseries'),
                         'variable_catalog_sha': hashlib.sha256(
            '\n'.join(sorted(v['name'] for v in catalog)).encode()).hexdigest()}
        self.store = Store()
        try:
            self.store.connect(database=database) if database is not None else self.store.connect()
            self.ids = self.store.register_run(run_id, digest, project.name, catalog, mode, configuration)
        except Exception:
            self.store.close()
            raise
        self.names = list(self.ids)
        self.run_id = run_id
        # Only an explicitly new historical run replaces prior results.
        # Resume must never infer replacement from a zero simulation time.
        self.replace_pending = mode == 'history_then_live' and configuration.get('replace_existing_results') is True
        self.error = None
        self.queue = Queue(maxsize=8)
        self.thread = Thread(target=self._write, daemon=True, name='sumo-mysql')
        self.thread.start()

    def _write(self):
        try:
            while True:
                item = self.queue.get()
                try:
                    if item is None:
                        return
                    if isinstance(item, Event):
                        item.set()
                    elif self.error is None:
                        ms, data, sensor_time = item
                        if self.replace_pending:
                            self.store.write_simulation(self.run_id, self.ids, ms, data, sensor_time,
                                                        replace_previous=True)
                            self.replace_pending = False
                        else:
                            self.store.write_simulation(self.run_id, self.ids, ms, data, sensor_time)
                except Exception as exc:
                    self.error = exc
                    logging.exception('SUMO database write failed for run %s (replacement pending: %s)',
                                      self.run_id, self.replace_pending)
                finally:
                    self.queue.task_done()
        finally:
            self.store.close()

    def check(self):
        if self.error:
            operation = 'first sample and replacement' if self.replace_pending else 'sample write'
            raise RuntimeError(f'SUMO MySQL write failed ({operation}). {write_error_detail(self.error)} '
                               'Simulation stopped to avoid silent history loss.') from self.error

    def submit(self, ms, data, sensor_time=None):
        self.check()
        try:
            self.queue.put_nowait((ms, {k: copy.deepcopy(data[k]) for k in self.names if k in data}, sensor_time))
        except Full as exc:
            raise RuntimeError('SUMO MySQL writer is behind; simulation stopped because its bounded queue is full.') from exc

    def flush(self):
        barrier = Event()
        self.queue.put(barrier, timeout=60)
        if not barrier.wait(60):
            raise RuntimeError('SUMO MySQL write timed out.')
        self.check()

    def close(self):
        try:
            self.flush()
        finally:
            self.queue.put(None, timeout=60)
            self.thread.join(timeout=60)


def open_recorder(project, run_id, mode, configuration, extra_names=()):
    if mode == 'history_then_live':
        # This mode already requires the history database. Always store its model
        # outputs there too, including after catching up and on checkpoint resume.
        history = configuration.get('history') or {}
        database = history.get('database') or os.getenv('SUMO_HISTORY_DATABASE', 'sumo_web_database')
        return SimulationRecorder(project, run_id, mode, configuration, extra_names, database=database)
    if os.getenv('SUMO_MYSQL_ENABLED', '0') != '1':
        return None
    return SimulationRecorder(project, run_id, mode, configuration, extra_names)
