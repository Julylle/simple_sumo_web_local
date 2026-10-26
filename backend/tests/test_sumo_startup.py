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
