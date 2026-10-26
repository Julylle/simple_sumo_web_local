from pathlib import Path

import pytest
from services.sumo_startup import write_startup_script
from database.catalog import model_catalog


def test_entire_bundled_catalog_is_followed_before_start(tmp_path):
    project = Path(__file__).resolve().parents[1] / 'real_sim_1202' / 'Cixi Eastern WWTP_20260920.sumo'
    _, catalog = model_catalog(project)
    names = [v['name'] for v in catalog]
    assert len(names) > 3000
    extra = 'Sumo__Plant__Influent__param__Q'
    commands = ['load "C:/a folder/state.xml";', 'maptoic;', 'set Sumo__Time 0;',
                'set Sumo__LimitTime 60000;', 'start;']
    script = write_startup_script(tmp_path, commands, ['Sumo__Time', extra, *names, extra])
    lines = script.read_text().splitlines()
    assert lines[:4] == commands[:4]
    assert lines[-1] == 'start;'
    follows = lines[4:-1]
    assert follows == [f'follow {name};' for name in [extra, *names]]
    assert all(len(line.encode()) < 1024 for line in follows)
    # Native schedule gets one short execute command, not the >100 KB catalog.
    assert script.stat().st_size > 100000
    assert len(f'execute "{script.as_posix()}"'.encode()) < 1024
    assert commands[-1] == 'start;'


@pytest.mark.parametrize('name', ['bad;start', 'bad\nstart', 'bad|name', 'bad\x00name', ''])
def test_invalid_follow_name_is_rejected(tmp_path, name):
    with pytest.raises(ValueError, match='subscription name'):
        write_startup_script(tmp_path, ['start;'], [name])


def test_bundled_project_restores_calibrated_values_not_dll_defaults():
    from services.sumo_startup import project_parameter_commands
    project = Path(__file__).resolve().parents[1] / 'real_sim_1202' / 'Cixi Eastern WWTP_20260920.sumo'
    commands = project_parameter_commands(project)
    assert 'set Sumo__Plant__CSTR3_5__param__L_Vtrain 1548;' in commands
    assert 'set Sumo__Plant__MLR2_1__param__Qpumped_target 57600;' in commands
    assert 'set Sumo__Plant__param__Sumo1__muNITO 0.5;' in commands
    assert 'set Sumo__Plant__Influent__param__frSNHx_TKN 0.749;' in commands


def test_project_constants_do_not_enable_competing_dynamic_input(tmp_path):
    import zipfile
    from services.sumo_startup import project_parameter_commands
    project = tmp_path / 'model.sumo'
    with zipfile.ZipFile(project, 'w') as archive:
        archive.writestr('parameters.txt', '\ufeff[CONSTANT INPUT]\nFull Symbol\tValue\tScenario\nSumo__Plant__p\t2\t3\n[DYNAMIC INPUT]\ninputs.tsv\tLinear\tN/A\n')
    assert project_parameter_commands(project) == ['set Sumo__Plant__p 2;']


def test_missing_project_parameters_fails_instead_of_silent_defaults(tmp_path):
    import zipfile
    from services.sumo_startup import project_parameter_commands
    project = tmp_path / 'model.sumo'
    with zipfile.ZipFile(project, 'w'):
        pass
    with pytest.raises(ValueError, match='missing parameters.txt'):
        project_parameter_commands(project)
