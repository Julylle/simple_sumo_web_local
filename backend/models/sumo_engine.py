"""Run the native scheduler outside the API process and isolate generated files."""
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Event, Lock, Thread
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

BACKEND = Path(__file__).resolve().parents[1]
_pool = ThreadPoolExecutor(max_workers=1)
_lock = Lock()
_jobs = {}


def _watch_progress(directory, stop, on_progress):
    while not stop.wait(0.5):
        try:
            value = json.loads((Path(directory) / 'progress.json').read_text(encoding='utf-8'))['simulated_h']
            if isinstance(value, (int, float)) and math.isfinite(value) and value >= 0:
                on_progress(value)
        except (OSError, ValueError, KeyError, TypeError):
            continue


def execute(duration_h, on_progress=lambda value: None):
    with tempfile.TemporaryDirectory(prefix='sumo_') as directory:
        stop = Event()
        watcher = Thread(target=_watch_progress, args=(directory, stop, on_progress), daemon=True)
        watcher.start()
        with open(Path(directory) / 'worker.log', 'w+', encoding='utf-8') as log:
            try:
                process = subprocess.run(
                    [os.environ.get('SUMO_PYTHON', sys.executable), str(BACKEND / 'models/sumo_worker.py'), str(duration_h)],
                    cwd=directory, stdout=log, stderr=subprocess.STDOUT, timeout=3600, check=False)
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError('SUMO exceeded the one-hour execution limit.') from exc
            finally:
                stop.set()
                watcher.join()
            if process.returncode:
                log.seek(0)
                logging.error('SUMO worker failed: %s', log.read()[-12000:])
                raise RuntimeError('SUMO execution failed. Check the server SUMO installation, license and logs.')
        return json.loads((Path(directory) / 'result.json').read_text(encoding='utf-8'))


def _run(job_id, duration_h):
    try:
        def progress(simulated_h):
            with _lock:
                current = max(_jobs[job_id].get('simulated_h', 0), min(duration_h, simulated_h))
                _jobs[job_id].update(simulated_h=current, progress_pct=min(99, current / duration_h * 100),
                                     phase='finalizing' if current >= duration_h else 'simulating')
        result = execute(duration_h, progress)
        update = {'status': 'completed', 'phase': 'completed', 'progress_pct': 100,
                  'simulated_h': duration_h, 'result': result}
    except Exception as exc:
        logging.exception('SUMO job failed')
        update = {'status': 'failed', 'phase': 'failed', 'error': str(exc) if isinstance(exc, RuntimeError) else 'SUMO could not start. Check server logs.'}
    with _lock:
        _jobs[job_id].update(update)


def start_run(duration_h):
    with _lock:
        if any(job['status'] == 'running' for job in _jobs.values()):
            raise RuntimeError('A SUMO simulation is already running. Try again when it finishes.')
        while len(_jobs) >= 20:
            del _jobs[next(iter(_jobs))]
        job_id = str(uuid4())
        _jobs[job_id] = {'id': job_id, 'status': 'running', 'phase': 'starting', 'progress_pct': 0,
                         'simulated_h': 0, 'duration_h': duration_h}
        _pool.submit(_run, job_id, duration_h)
        return dict(_jobs[job_id])


def get_run(job_id):
    with _lock:
        return dict(_jobs[job_id]) if job_id in _jobs else None
