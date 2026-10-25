"""Uploaded SUMO projects paired with their own initial state, scoped to this server session."""
import io
import tempfile
import threading
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from uuid import uuid4

BUILTIN_DIR = Path(__file__).resolve().parents[1] / 'real_sim_1202'
MAX_MODEL_BYTES = 50 * 1024 * 1024
MAX_STATE_BYTES = 20 * 1024 * 1024
_store = tempfile.TemporaryDirectory(prefix='sumo_uploaded_models_')
_models = {}
_lock = threading.Lock()


def register_model(project_bytes, state_bytes, project_name, state_name):
    project_name = (project_name or '').replace('\\', '/').split('/')[-1]
    state_name = (state_name or '').replace('\\', '/').split('/')[-1]
    if not project_name.lower().endswith('.sumo') or not state_name.lower().endswith('.xml'):
        raise ValueError('Choose a .sumo project and its initial-state .xml file.')
    if not project_bytes or len(project_bytes) > MAX_MODEL_BYTES:
        raise ValueError('SUMO project must be non-empty and no larger than 50 MB.')
    if not state_bytes or len(state_bytes) > MAX_STATE_BYTES:
        raise ValueError('Initial state must be non-empty and no larger than 20 MB.')
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
    try:
        root = ET.fromstring(state_bytes)
        if root.tag != 'systemstate' or len(root) == 0:
            raise ValueError('Choose a SUMO systemstate XML file.')
    except ET.ParseError as exc:
        raise ValueError('Initial state is not valid XML.') from exc
    identifier = str(uuid4())
    with _lock:
        if len(_models) >= 20:
            raise ValueError('Upload limit reached for this server session. Restart the backend to clear unused uploads.')
        folder = Path(_store.name) / identifier
        folder.mkdir()
        project = folder / 'model.sumo'
        state = folder / 'initial_state.xml'
        project.write_bytes(project_bytes)
        state.write_bytes(state_bytes)
        _models[identifier] = {'project': project, 'state': state, 'name': project_name, 'state_name': state_name}
    return {'id': identifier, 'name': project_name, 'state_name': state_name}


def resolve_model(model_id='builtin'):
    if model_id == 'builtin':
        return {'project': BUILTIN_DIR / 'Cixi Eastern WWTP_20260920.sumo',
                'state': BUILTIN_DIR / 'sumo_steady_state.xml',
                'name': 'Cixi Eastern WWTP_20260920.sumo', 'state_name': 'sumo_steady_state.xml'}
    with _lock:
        model = _models.get(model_id)
        if model is None:
            raise ValueError('Uploaded model is unavailable. Upload the project and initial state again.')
        return dict(model)
