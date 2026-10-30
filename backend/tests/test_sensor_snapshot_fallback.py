import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, AsyncMock

from asyncua import ua
from services import sensor_snapshot as module

Q = 'Sumo__Plant__Influent__param__Q'
T = 'Sumo__Plant__Influent__param__T'
M = {Q: 'ns=2;s=flow', T: 'ns=2;s=temp'}


def client(monkeypatch, values=None, error=None):
    read = AsyncMock(side_effect=values)
    class Session:
        async def __aenter__(self):
            if error:
                raise error
            return SimpleNamespace(get_node=lambda _: SimpleNamespace(read_value=read))
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(module, 'Client', lambda **kwargs: Session())
    return read


def fallback(mapping, at):
    return [dict(column=k, node_id=v, value=17, timestamp=at.isoformat(),
                 source='database_previous', age_seconds=60) for k,v in mapping.items()]


def test_mixed_bad_node_falls_back_then_recovers_next_refresh(monkeypatch):
    client(monkeypatch, [ua.UaStatusCodeError(ua.StatusCodes.Bad), 21, 8, 22])
    db = Mock(side_effect=fallback)
    monkeypatch.setattr(module, 'database_readings', db)
    first = asyncio.run(module.read_resilient_snapshot(M))
    assert [r['source'] for r in first['readings']] == ['database_previous', 'opcua']
    assert db.call_args.args[0] == {Q: M[Q]}
    assert first['unavailable'] == []
    second = asyncio.run(module.read_resilient_snapshot(M))
    assert [r['source'] for r in second['readings']] == ['opcua', 'opcua']
    assert db.call_count == 1


def test_connection_failure_falls_back_for_all(monkeypatch):
    client(monkeypatch, error=ConnectionError('offline'))
    monkeypatch.setattr(module, 'database_readings', fallback)
    result = asyncio.run(module.read_resilient_snapshot(M))
    assert len(result['readings']) == 2
    assert not result['unavailable']


def test_invalid_values_and_no_history_are_explicit(monkeypatch):
    client(monkeypatch, [None, float('nan')])
    monkeypatch.setattr(module, 'database_readings', lambda *args: [])
    result = asyncio.run(module.read_resilient_snapshot(M))
    assert not result['readings']
    assert len(result['unavailable']) == 2


def test_database_error_keeps_valid_opc_result(monkeypatch):
    client(monkeypatch, [1, ValueError('bad')])
    monkeypatch.setattr(module, 'database_readings', Mock(side_effect=ConnectionError('DB offline')))
    result = asyncio.run(module.read_resilient_snapshot(M))
    assert [r['column'] for r in result['readings']] == [Q]
    assert 'DB offline' in result['unavailable'][0]['database_error']


def test_opc_timeout_preserves_completed_readings(monkeypatch):
    class Node:
        async def read_value(self):
            await asyncio.sleep(1)
    class Session:
        async def __aenter__(self):
            return SimpleNamespace(get_node=lambda _: Node())
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(module, 'Client', lambda **kwargs: Session())
    monkeypatch.setattr(module, 'database_readings', fallback)
    result = asyncio.run(module.read_resilient_snapshot(M, opc_timeout=0.001))
    assert len(result['readings']) == 2


def test_database_matching_timestamp_source_and_raw_units(monkeypatch):
    at = datetime(2026,10,28,0,0,tzinfo=timezone.utc)
    cursor = Mock()
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock()
    cursor.fetchone.side_effect = [(41.7, at.replace(tzinfo=None)),
                                 (19, (at-timedelta(hours=1)).replace(tzinfo=None))]
    store = Mock(connection=Mock(cursor=Mock(return_value=cursor)))
    monkeypatch.setattr(module, 'Store', lambda:store)
    monkeypatch.delenv('SUMO_HISTORY_DATABASE', raising=False)
    result = module.database_readings(M, at)
    assert [r['source'] for r in result] == ['database_current','database_previous']
    assert result[0]['value'] == 41.7  # no double scaling
    assert result[1]['age_seconds'] == 3600
    store.connect.assert_called_once_with(database='sumo_web_database')
    sql, params = cursor.execute.call_args_list[0].args
    assert "r.quality='good'" in sql and 'r.acquired_at <= %s' in sql
    assert params == [Q, 'flow', at.replace(tzinfo=None)]
    store.close.assert_called_once()


def test_negative_opc_uses_zero_without_replacing_with_old_database_value(monkeypatch):
    client(monkeypatch, [-334.8833, 21])
    db = Mock(side_effect=AssertionError('negative finite values do not need fallback'))
    monkeypatch.setattr(module, 'database_readings', db)
    result = asyncio.run(module.read_resilient_snapshot(M))
    assert result['readings'][0]['value'] == 0
    assert result['readings'][0]['source'] == 'opcua'
    assert result['unavailable'] == []
    db.assert_not_called()


def test_database_negative_current_value_is_zero_not_skipped(monkeypatch):
    from unittest.mock import MagicMock
    at = datetime(2026,10,30,1,47,tzinfo=timezone.utc)
    store = MagicMock()
    cursor = store.connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (-334.8833, at.replace(tzinfo=None))
    monkeypatch.setattr(module, 'Store', lambda:store)
    result = module.database_readings({Q:M[Q]}, at)
    assert result[0]['value'] == 0
    assert result[0]['source'] == 'database_current'
    assert 'r.numeric_value >= 0' not in cursor.execute.call_args.args[0]
