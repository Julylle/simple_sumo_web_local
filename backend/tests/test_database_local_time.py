from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from database.local_time import display_timezone, install_local_views
from database.store import dbtime
from services.historical_inputs import history_request, parse_time


@pytest.mark.parametrize('value', ['+08:00','-05:30','Asia/Shanghai','America/New_York'])
def test_supported_display_zones(value):
    assert display_timezone(value)==value


@pytest.mark.parametrize('value', ["+08:00'; DROP TABLE raw_data;--", '+15:00','+08:99','SYSTEM','bad zone'])
def test_invalid_or_unsafe_zones_are_rejected(value):
    with pytest.raises(ValueError):display_timezone(value)


def test_view_update_only_changes_views_and_keeps_utc_aliases():
    connection=MagicMock()
    cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value=(datetime(2026,1,1,8),)
    assert install_local_views(connection,'+08:00')=='+08:00'
    statements=[call.args[0] for call in cursor.execute.call_args_list]
    assert len(statements)==3
    assert cursor.execute.call_args_list[0].args[1]==('+08:00',)
    assert all('CREATE OR REPLACE VIEW' in sql for sql in statements[1:])
    assert all('AS plot_time' in sql and 'AS display_timezone' in sql for sql in statements[1:])
    assert 's.sensor_read_at AS sensor_read_at_utc' in statements[2]
    assert "CONVERT_TZ(s.sensor_read_at,'+00:00','+08:00')" in statements[2]
    assert 'r.acquired_at AS acquired_at_utc' in statements[1]
    assert not any('UPDATE raw_data' in sql or 'UPDATE sumo_samples' in sql for sql in statements)
    connection.commit.assert_called_once()


def test_unavailable_named_zone_fails_before_replacing_views():
    connection=MagicMock()
    cursor=connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value=(None,)
    with pytest.raises(ValueError,match='timezone tables'):
        install_local_views(connection,'Asia/Shanghai')
    assert cursor.execute.call_count==1


def test_local_range_is_converted_once_and_matches_plot_instants():
    plan=history_request('2026-01-01T08:00:00+08:00',None,5)
    assert plan['start']=='2026-01-01T00:00:00+00:00'
    assert dbtime(plan['start'])==datetime(2026,1,1,0,0)
    assert parse_time('2026-01-01T08:05:00+08:00')==datetime(2026,1,1,0,5,tzinfo=timezone.utc)
