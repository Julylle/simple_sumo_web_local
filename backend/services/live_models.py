"""Uploaded projects and asynchronously generated states, scoped to this server session."""
import io
import asyncio
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

BUILTIN_DIR = Path(__file__).resolve().parents[1] / 'real_sim_1202'
from services.kepserver import read_snapshot
from services.model_inputs import scale_model_inputs
from services.sensor_inputs import SENSOR_COLUMNS

MAX_STATE_BYTES = 20 * 1024 * 1024
MAX_MODEL_BYTES = 50 * 1024 * 1024
STEADY_SECONDS = 3.5 * 60 * 60
_solver_lock = threading.Lock()
_store = tempfile.TemporaryDirectory(prefix='sumo_uploaded_models_')
_models = {}
_lock = threading.Lock()



def validate_state(content):
    if not content or len(content) > MAX_STATE_BYTES:
        raise ValueError('Choose a non-empty steady-state XML no larger than 20 MB.')
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError('Invalid steady-state XML.') from exc
    if root.tag != 'systemstate' or len(root) == 0:
        raise ValueError('Choose a non-empty SUMO systemstate XML.')


def register_model(project_bytes, project_name, *, state_bytes=None, mapping=None,
                   state_mode='calculate', tolerance=1e-6):
    if state_mode not in ('upload', 'calculate'):
        raise ValueError('Choose upload or calculate for the steady state.')
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Convergence tolerance must be positive and finite.')
    if state_mode == 'upload':
        validate_state(state_bytes)
    elif (not isinstance(mapping, dict) or not 1 <= len(mapping) <= len(SENSOR_COLUMNS) or
          any(k not in SENSOR_COLUMNS or not isinstance(v, str) or not v.strip()
              for k, v in mapping.items())):
        raise ValueError('Configure sensor mappings before calculating the steady state.')

    project_name = (project_name or '').replace('\\', '/').split('/')[-1]
    if not project_name.lower().endswith('.sumo'):
        raise ValueError('Choose a compiled .sumo project.')
    if not project_bytes or len(project_bytes) > MAX_MODEL_BYTES:
        raise ValueError('SUMO project must be non-empty and no larger than 50 MB.')
    try:
        with zipfile.ZipFile(io.BytesIO(project_bytes)) as archive:
            for name, limit in [('variables.var', 20 * 1024 * 1024), ('sumoproject.dll', 200 * 1024 * 1024)]:
                info = archive.getinfo(name)
                if not 0 < info.file_size <= limit:
                    raise ValueError(f'Invalid or oversized model member: {name}')
            fields = [line.split('\t') for line in archive.read('variables.var').decode('utf-8-sig').splitlines()]
            if not any(len(row) > 4 for row in fields):
                raise ValueError('SUMO project has no valid variable metadata.')
    except (zipfile.BadZipFile, KeyError, UnicodeError, RuntimeError) as exc:
        raise ValueError('Invalid .sumo project: compiled sumoproject.dll and variables.var are required.') from exc
    if state_mode == 'calculate':
        writable = {row[1] for row in fields if len(row)>4 and row[4] in
                    ('Parameter', 'SystemParameter', 'Dimension')}
        missing = set(mapping) - writable
        if missing:
            raise ValueError('SUMO inputs not writable: ' + ', '.join(sorted(missing)))
    identifier = str(uuid4())
    with _lock:
        if len(_models) >= 20:
            raise ValueError('Upload limit reached for this server session. Restart the backend to clear unused uploads.')
        folder = Path(_store.name) / identifier
        folder.mkdir()
        project = folder / 'model.sumo'
        state = folder / 'sumo_steady_state.xml'
        project.write_bytes(project_bytes)
        if state_mode == 'upload':
            state.write_bytes(state_bytes)
        _models[identifier] = {'project': project, 'state': state, 'name': project_name,
                               'state_name': state.name, 'status': 'ready' if state_mode == 'upload' else 'queued',
                               'error': None, 'mapping': dict(mapping or {}), 'tolerance': tolerance,
                               'state_mode': state_mode, 'sensor_read_at': None}
    if state_mode == 'calculate':
        threading.Thread(target=_prepare_model, args=(identifier,), daemon=True,
                         name='sumo-steady').start()
    return model_status(identifier)


def model_status(identifier):
    with _lock:
        model = _models.get(identifier)
        if model is None:
            raise ValueError('Uploaded model is unavailable. Upload the project again.')
        return {'id': identifier, **{key: model[key] for key in
                ('name', 'state_name', 'status', 'error', 'sensor_read_at', 'tolerance', 'state_mode')}}


def _run_steady(model):
    # A separate process isolates Scheduler callbacks and cleanup from live runs.
    # Copy the solver script so its CSV and DLL stay in this job folder.
    folder = model['project'].parent
    shutil.copy2(BUILTIN_DIR / 'steady_run.py', folder / 'steady_run.py')
    env = dict(os.environ)
    env['PYTHONPATH'] = str(BUILTIN_DIR) + os.pathsep + env.get('PYTHONPATH', '')
    command = [
        sys.executable, '-u', '-c',
        'from steady_run import prepare_steady_state; import sys,json; '
        'prepare_steady_state(sys.argv[1], sys.argv[2], wall_run_seconds=float(sys.argv[3]), '
        'inputs=json.load(open(sys.argv[4]))["values"], tolerance=float(sys.argv[5]))',
        str(model['project']), str(model['state']), str(STEADY_SECONDS),
        str(folder / 'sensor_inputs.json'), str(model['tolerance']),
    ]
    with (folder / 'steady_process.log').open('w', encoding='utf-8') as output:
        result = subprocess.run(command, cwd=folder, env=env, stdout=output,
                                stderr=subprocess.STDOUT, timeout=STEADY_SECONDS + 180)
    if result.returncode:
        tail = (folder / 'steady_process.log').read_text(encoding='utf-8', errors='replace')[-3000:]
        raise RuntimeError('Steady-state generation failed: ' + tail)


def _prepare_model(identifier):
    try:
        # Serialize steady jobs to avoid starting many licensed solver processes.
        with _solver_lock:
            with _lock:
                model = dict(_models[identifier])
                _models[identifier]['status'] = 'preparing'
            async def fresh_snapshot():
                return await asyncio.wait_for(read_snapshot(model['mapping']), timeout=30)
            readings = asyncio.run(fresh_snapshot())
            values = scale_model_inputs(readings)
            if set(values) != set(model['mapping']):
                raise ValueError('Incomplete sensor snapshot; steady-state calculation was not started.')
            (model['project'].parent / 'sensor_inputs.json').write_text(
                json.dumps({'readings': readings, 'values': values}), encoding='utf-8')
            with _lock:
                _models[identifier]['sensor_read_at'] = max(r['timestamp'] for r in readings)
            _run_steady(model)
            root = ET.parse(model['state']).getroot()
            if root.tag != 'systemstate' or len(root) == 0:
                raise ValueError('Generated state is not a non-empty SUMO systemstate.')
            with _lock:
                _models[identifier]['status'] = 'ready'
    except Exception as exc:
        with _lock:
            _models[identifier].update(status='failed', error=str(exc))



def resolve_model(model_id='builtin'):
    if model_id == 'builtin':
        return {'project': BUILTIN_DIR / 'Cixi Eastern WWTP_20260920.sumo',
                'state': BUILTIN_DIR / 'sumo_steady_state.xml',
                'name': 'Cixi Eastern WWTP_20260920.sumo', 'state_name': 'sumo_steady_state.xml'}
    with _lock:
        model = _models.get(model_id)
        if model is None:
            raise ValueError('Uploaded model is unavailable. Upload the project again.')
        if model['status'] != 'ready':
            raise ValueError(model.get('error') or 'The model initial state is still being generated.')
        return dict(model)
