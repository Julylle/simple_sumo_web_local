"""One atomically replaced recovery bundle, including the exact SUMO project."""
import json
import math
import os
import tempfile
import threading
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from services.resume_history import checkpoint_boundary

_lock = threading.RLock()


def checkpoint_path():
    root = Path(os.getenv('SUMO_LIVE_STATE_DIR', str(Path(__file__).resolve().parents[1] / 'live_states')))
    root.mkdir(parents=True, exist_ok=True)
    return root / 'latest_checkpoint.zip'


def save_checkpoint(session, state_file, simulated_ms):
    state = Path(state_file).read_bytes()
    root = ET.fromstring(state)
    if root.tag != 'systemstate' or not len(root):
        raise ValueError('Invalid checkpoint systemstate.')
    metadata = {'version': 1, 'run_id': session['id'], 'simulated_ms': simulated_ms,
                'saved_at': datetime.now(timezone.utc).isoformat(),
                'model_name': session['model']['name'], 'mapping': session['mapping'],
                'interval_minutes': session['interval'] // 60,
                'history': session.get('history')}
    boundary, source = checkpoint_boundary({**metadata,
        'input_read_at': session.get('input_read_at'),
        'result': {'sensor_timestamps': session.get('sensor_timestamps', [])}})
    metadata.update(sensor_boundary_at=boundary.isoformat(), boundary_source=source)
    with _lock:
        target = checkpoint_path()
        pending = target.with_suffix('.pending')
        try:
            with pending.open('wb') as stream:
                with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
                    archive.writestr('metadata.json', json.dumps(metadata))
                    archive.writestr('results.json', json.dumps({
                        'time_h': session.get('times', []),
                        'sensor_timestamps': session.get('sensor_timestamps', [None] * len(session.get('times', []))),
                        'variables': session.get('variables', {})}, allow_nan=False))
                    archive.writestr('state.xml', state)
                    archive.write(session['model']['project'], 'model.sumo')
                stream.flush()
                os.fsync(stream.fileno())
            # Readers see either the previous complete bundle or the new complete one.
            os.replace(pending, target)
            if os.name != 'nt':
                descriptor = os.open(target.parent, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
        finally:
            pending.unlink(missing_ok=True)
    return metadata


def checkpoint_info():
    with _lock:
        target = checkpoint_path()
        if not target.exists():
            return None
        try:
            with zipfile.ZipFile(target) as archive:
                metadata = json.loads(archive.read('metadata.json'))
            return {**metadata, 'simulated_h': metadata['simulated_ms'] / 3600000}
        except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
            return {'error': 'Checkpoint cannot be read: ' + str(exc)}


def restore_checkpoint():
    """Extract only known members to a private directory owned by the new session."""
    with _lock:
        target = checkpoint_path()
        if not target.exists():
            raise ValueError('No saved live checkpoint is available.')
        folder = tempfile.TemporaryDirectory(prefix='sumo_resume_')
        try:
            with zipfile.ZipFile(target) as archive:
                if archive.testzip() is not None:
                    raise ValueError('Checkpoint checksum validation failed.')
                metadata = json.loads(archive.read('metadata.json'))
                metadata['result'] = _read_results(archive)
                if metadata.get('version') != 1:
                    raise ValueError('Unsupported checkpoint version.')
                for name in ('model.sumo', 'state.xml'):
                    (Path(folder.name) / name).write_bytes(archive.read(name))
            model = {'project': Path(folder.name) / 'model.sumo',
                     'state': Path(folder.name) / 'state.xml',
                     'name': metadata['model_name'], 'state_name': 'state.xml'}
            return metadata, model, folder
        except Exception as exc:
            folder.cleanup()
            raise ValueError('Cannot restore checkpoint: ' + str(exc)) from exc



def _read_results(archive):
    # Older checkpoints remain usable, but cannot recover unrecorded history.
    if 'results.json' not in archive.namelist():
        return {'time_h': [], 'variables': {}}
    result = json.loads(archive.read('results.json'))
    times, variables = result['time_h'], result['variables']
    if not isinstance(times, list) or not isinstance(variables, dict):
        raise ValueError('Invalid checkpoint results.')
    if any(not isinstance(v, list) or len(v) != len(times) for v in variables.values()):
        raise ValueError('Misaligned checkpoint results.')
    if (any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in times) or
        any(v is not None and (not isinstance(v, (int, float)) or not math.isfinite(v))
            for values in variables.values() for v in values)):
        raise ValueError('Non-finite checkpoint results.')
    timestamps = result.get('sensor_timestamps')
    if timestamps is not None:
        if not isinstance(timestamps, list) or len(timestamps) != len(times):
            raise ValueError('Misaligned sensor timestamps.')
        for value in timestamps:
            if value is not None:
                parsed = datetime.fromisoformat(value)
                if parsed.tzinfo is None:
                    raise ValueError('Sensor timestamp must include a timezone.')
    return result


def saved_snapshot():
    """Read history without loading the native scheduler or starting a simulation."""
    with _lock:
        target = checkpoint_path()
        if not target.exists():
            return None
        with zipfile.ZipFile(target) as archive:
            metadata = json.loads(archive.read('metadata.json'))
            result = _read_results(archive)
        return {'id': metadata['run_id'], 'status': 'interrupted',
                'phase': 'Saved checkpoint — resume to continue',
                'model_id': 'checkpoint', 'model_name': metadata['model_name'],
                'mapping': metadata['mapping'], 'interval_minutes': metadata['interval_minutes'],
                'simulated_h': metadata['simulated_ms'] / 3600000,
                'samples': len(result['time_h']), 'result': result,
                'history': metadata.get('history'),
                'mode': ('history' if (not metadata['history'].get('caught_up') if metadata['history'].get('follow')
                                      else metadata['history']['completed'] < metadata['history']['total']) else 'live')
                        if metadata.get('history') else 'live'}
