"""Exercise convergence and command ordering without a licensed SUMO runtime."""
import importlib.util
import sys
import zipfile
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock

import pytest

Q = 'Sumo__Plant__Influent__param__Q'


@pytest.mark.parametrize('samples,finished,success', [
    ([1, 1e-7, 1e-7, 1e-7], False, True),
    ([1e-7], True, True),
    ([1.0], True, False),
    ([float('nan')], True, False),
    ([], False, False),
    ([1e-7, 1, 1e-7], False, False),
])
def test_only_converged_states_are_saved(tmp_path, monkeypatch, samples, finished, success):
    monkeypatch.chdir(tmp_path)
    package = ModuleType('dynamita')
    tool = ModuleType('dynamita.tool')
    scheduler = ModuleType('dynamita.scheduler')
    tool.extract_dll_from_project = Mock()
    tool.extract_parameters_from_project = Mock()
    engine = Mock()
    engine.persistent = 'persistent'
    engine.isSimFinishedMsg = lambda msg: msg.startswith('530004')
    scheduler.sumo = engine
    package.tool = tool
    package.scheduler = scheduler
    for name, module in [('dynamita',package),('dynamita.tool',tool),('dynamita.scheduler',scheduler)]:
        monkeypatch.setitem(sys.modules, name, module)
    source = Path(__file__).resolve().parents[1] / 'real_sim_1202/steady_run.py'
    spec = importlib.util.spec_from_file_location('test_solver_module', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.__file__ = str(tmp_path / 'steady_run.py')
    project = tmp_path / 'test.sumo'
    state = tmp_path / 'state.xml'
    with zipfile.ZipFile(project, 'w') as archive:
        archive.writestr('variables.var', f'0\t{Q}\tREAL\tm3/d\tParameter\n1\tSumo__MaxAbsDer\tREAL\t-\tVariable')
    def schedule(model, commands, **kwargs):
        assert commands[0].startswith('execute ')
        assert commands[1] == f'set {Q} 1000;'
        assert commands[-2:] == ['mode steady;', 'start;']
        for value in samples:
            engine.datacomm_callback(1, {'Sumo__MaxAbsDer':value})
        if finished:
            engine.message_callback(1, '530004 Simulation ended.')
        return 1
    def send(job, command):
        if command == 'stop;':
            engine.message_callback(1, '530004 Simulation ended.')
        if command.startswith('save '):
            state.write_text('<systemstate><state/></systemstate>')
            engine.message_callback(1, '530045 Saved.')
    engine.schedule.side_effect = schedule
    engine.sendCommand.side_effect = send
    if success:
        assert module.prepare_steady_state(str(project), str(state), wall_run_seconds=0.01, inputs={Q:1000})
        assert state.exists()
    else:
        with pytest.raises((RuntimeError, TimeoutError)):
            module.prepare_steady_state(str(project), str(state), wall_run_seconds=0.01, inputs={Q:1000})
        assert not state.exists()
        assert not any(call.args[1].startswith('save ') for call in engine.sendCommand.call_args_list)
    engine.cleanup.assert_called_once()
