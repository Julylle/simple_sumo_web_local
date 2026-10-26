import json
import re
import zipfile
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from real_sim_1202 import steady_run
from services import kepserver
from services.sensor_inputs import SENSOR_COLUMNS
from database.catalog import load_mapping

Q = 'Sumo__Plant__Influent__param__Q'


def test_default_mapping_matches_all_web_presets():
    frontend = Path(__file__).resolve().parents[2] / 'frontend/src'
    text = (frontend/'components/RealTimeSumo.tsx').read_text()
    text += (frontend/'config/doSensors.ts').read_text()
    text += (frontend/'config/additionalControls.ts').read_text()
    pairs = dict(re.findall(r'["\']?(Sumo__Plant__[A-Za-z0-9_]+)["\']?\s*:\s*["\'](ns=2;s=[^"\']+)["\']', text))
    _, _, rows = load_mapping()
    defaults = {r['SumoName']: 'ns=2;s='+r['OpcTag'] for r in rows if r['SumoName'] in SENSOR_COLUMNS}
    assert defaults == pairs
    assert len(defaults) == 53


@pytest.mark.parametrize('source_mode', ['mapping', 'live-url'])
@pytest.mark.parametrize('failure', [None, 'sensor', 'incomplete', 'solver', 'invalid_state'])
def test_cli_reads_once_applies_web_scaling_and_only_replaces_success(tmp_path, monkeypatch, failure, source_mode):
    project = tmp_path/'test.sumo'
    output = tmp_path/'state.xml'
    output.write_text('<systemstate><old/></systemstate>')
    mapping = tmp_path/'mapping.json'
    mapping.write_text(json.dumps({Q:'ns=2;s=flow'}))
    with zipfile.ZipFile(project, 'w') as archive:
        archive.writestr('variables.var', f'0\t{Q}\t0\tREAL\tParameter')
    readings = [{'column':Q,'value':41.7,'timestamp':'2026-10-26T00:00:00Z'}]
    read = AsyncMock(return_value=[] if failure == 'incomplete' else readings,
                     side_effect=ConnectionError('offline') if failure == 'sensor' else None)
    monkeypatch.setattr(kepserver, 'read_snapshot', read)
    calls = []
    def solve(project_path, output_path, **kwargs):
        calls.append(kwargs)
        assert kwargs['inputs'][Q] == pytest.approx(1000)
        assert kwargs['tolerance'] == 100
        assert kwargs['wall_run_seconds'] == 5*3600
        assert Path(kwargs['work_dir']).exists()
        recovery = Path(kwargs['timeout_state_path'])
        assert recovery.parent == output.parent
        assert recovery.name.startswith('state_unconverged_')
        if failure == 'solver':
            recovery.write_text('<systemstate><partial/></systemstate>')
            raise TimeoutError('not converged')
        Path(output_path).write_text('<wrong/>' if failure == 'invalid_state' else '<systemstate><new/></systemstate>')
    monkeypatch.setattr(steady_run, 'prepare_steady_state', solve)
    monkeypatch.chdir(tmp_path)
    args = ['--project', str(project), '--output', str(output)]
    if source_mode == 'mapping':
        args += ['--mapping', str(mapping)]
    else:
        import io
        import urllib.request
        def get_status(url, timeout):
            assert url == 'http://localhost:8000/api/sumo/live/status'
            return io.BytesIO(json.dumps({'mapping': {Q:'ns=2;s=flow'}}).encode())
        monkeypatch.setattr(urllib.request, 'urlopen', get_status)
        args += ['--live-url', 'http://localhost:8000']
    if failure:
        with pytest.raises((ValueError, TimeoutError, ConnectionError)):
            steady_run.main(args)
        assert '<old/>' in output.read_text()
        if failure == 'solver':
            assert '<partial/>' in next(tmp_path.glob('state_unconverged_*.xml')).read_text()
    else:
        steady_run.main(args)
        assert '<new/>' in output.read_text()
        snapshot = json.loads(next(tmp_path.glob('steady_sensor_inputs_*.json')).read_text())
        assert snapshot['readings'][0]['value'] == 41.7
        assert snapshot['values'][Q] == pytest.approx(1000)
    read.assert_awaited_once_with({Q:'ns=2;s=flow'})
    assert bool(calls) == (failure not in ('sensor', 'incomplete'))
    assert not list(tmp_path.glob('*.pending.xml'))


def test_default_project_location_does_not_depend_on_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert Path(steady_run.SUMO_PROJECT).parent == Path(steady_run.__file__).resolve().parent
