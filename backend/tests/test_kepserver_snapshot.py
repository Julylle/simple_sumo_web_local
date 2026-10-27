"""Snapshot failures must identify the input and preserve OPC UA quality checks."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from asyncua import ua
from services import kepserver

Q = "Sumo__Plant__Influent__param__Q"
NODE = "ns=2;s=test_flow"


def install_client(monkeypatch, read):
    node = SimpleNamespace(read_value=read)
    client = SimpleNamespace(
        get_node=lambda node_id: node,
    )
    class Session:
        async def __aenter__(self):
            return client
        async def __aexit__(self, *args):
            pass
    monkeypatch.setattr(kepserver, "Client", lambda **kwargs: Session())


@pytest.mark.parametrize("error", [
    ua.UaStatusCodeError(ua.StatusCodes.Bad), TimeoutError("request deadline"),
])
def test_node_errors_include_mapping_and_original_cause(monkeypatch, error):
    install_client(monkeypatch, AsyncMock(side_effect=error))
    progress = []
    expected = TimeoutError if isinstance(error, TimeoutError) else RuntimeError
    with pytest.raises(expected) as caught:
        asyncio.run(kepserver.read_snapshot({Q: NODE}, progress=progress.append))
    assert Q in str(caught.value) and NODE in str(caught.value)
    assert caught.value.__cause__ is error
    assert NODE in progress[-1]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_values_rejected_with_node_context(monkeypatch, value):
    install_client(monkeypatch, AsyncMock(return_value=value))
    with pytest.raises(ValueError, match=NODE):
        asyncio.run(kepserver.read_snapshot({Q: NODE}))


def test_success_preserves_raw_value_and_existing_call_signature(monkeypatch):
    install_client(monkeypatch, AsyncMock(return_value=41.7))
    readings = asyncio.run(kepserver.read_snapshot({Q: NODE}))
    assert readings[0]["column"] == Q
    assert readings[0]["node_id"] == NODE
    assert readings[0]["value"] == 41.7


def test_cancellation_is_not_wrapped(monkeypatch):
    install_client(monkeypatch, AsyncMock(side_effect=asyncio.CancelledError()))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(kepserver.read_snapshot({Q: NODE}))
