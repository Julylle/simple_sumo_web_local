"""Connection snapshots retain strict quality checks and useful timeout errors."""
import asyncio
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from api import kepserver

MAPPING = {"Sumo__Plant__Influent__param__Q": "ns=2;s=flow"}

@pytest.mark.parametrize("configured,expected", [(None, 120), ("240", 240)])
def test_snapshot_timeout_budget_and_success(monkeypatch, configured, expected):
    if configured is None:
        monkeypatch.delenv("KEPSERVER_SNAPSHOT_TIMEOUT_SECONDS", raising=False)
    else:
        monkeypatch.setenv("KEPSERVER_SNAPSHOT_TIMEOUT_SECONDS", configured)
    readings = [{"column": next(iter(MAPPING)), "node_id": "ns=2;s=flow", "value": 10}]
    monkeypatch.setattr(kepserver, "read_resilient_snapshot", AsyncMock(return_value={"readings": readings}))
    async def wait(awaitable, timeout):
        assert timeout == expected
        return await awaitable
    monkeypatch.setattr(kepserver.asyncio, "wait_for", wait)
    assert asyncio.run(kepserver.snapshot(kepserver.SnapshotRequest(mapping=MAPPING))) == {"readings": readings}

@pytest.mark.parametrize("error,status,detail", [
    (TimeoutError(), 504, "snapshot timed out"),
    (RuntimeError("Bad sensor: ns=2;s=flow"), 502, "Bad sensor: ns=2;s=flow"),
])
def test_failed_snapshot_is_not_success(monkeypatch, error, status, detail):
    monkeypatch.setattr(kepserver, "read_resilient_snapshot", AsyncMock(side_effect=error))
    with pytest.raises(HTTPException) as caught:
        asyncio.run(kepserver.snapshot(kepserver.SnapshotRequest(mapping=MAPPING)))
    assert caught.value.status_code == status
    assert detail in caught.value.detail
