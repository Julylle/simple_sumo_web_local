"""Bounded MySQL writer, separate from native Scheduler callbacks."""
import copy
import hashlib
import os
from queue import Queue, Full
from threading import Thread, Event

from database.catalog import model_catalog
from database.store import Store


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
                        self.store.write_simulation(self.run_id, self.ids, ms, data, sensor_time)
                except Exception as exc:
                    self.error = exc
                finally:
                    self.queue.task_done()
        finally:
            self.store.close()

    def check(self):
        if self.error:
            raise RuntimeError('SUMO MySQL write failed; simulation stopped to avoid silent history loss.') from self.error

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
