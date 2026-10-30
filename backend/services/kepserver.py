"""Read a single OPC UA snapshot; no background polling or simulation."""
import asyncio
import math
from services.sensor_policy import normalize_reading
import os
from datetime import datetime, timezone

from asyncua import Client, ua
from services.sensor_inputs import SENSOR_COLUMNS

DEFAULT_NODE = "ns=2;s=GEeth.PLC128.Influent_ammonia_sensor"

async def read_snapshot(mapping: dict[str, str], *, progress=None, skip_bad=False, skipped=None, tolerate_errors=False):
    if not mapping:
        raise ValueError("Configure at least one sensor mapping.")
    if any(key not in SENSOR_COLUMNS for key in mapping):
        raise ValueError("Unsupported SUMO input parameter.")
    if any(not isinstance(node, str) or not node.strip() for node in mapping.values()):
        raise ValueError("Every mapped parameter requires an OPC UA node ID.")
    if tolerate_errors:
        return await _read_tolerant_snapshot(mapping)
    url = os.getenv("KEPSERVER_OPC_URL", "opc.tcp://127.0.0.1:49320")
    if progress:
        progress("Connecting to KEPServer")
    async with Client(url=url, timeout=15) as client:
        readings = []
        for index, (column, node_id) in enumerate(mapping.items(), 1):
            context = f"{column} ({node_id})"
            if progress:
                progress(f"Reading {index}/{len(mapping)}: {context}")
            try:
                node = client.get_node(node_id)
                # Keep asyncua's quality check: Bad values must not enter SUMO.
                value = float(await node.read_value())
            except ua.UaStatusCodeError as exc:
                if not skip_bad or not ua.StatusCode(exc.code).is_bad():
                    raise RuntimeError(
                        f"OPC UA read failed: {context}; {type(exc).__name__}: {exc}"
                    ) from exc
                reason = f"{type(exc).__name__}: {exc}"
                if skipped is not None:
                    skipped.append({"column": column, "node_id": node_id, "reason": reason})
                if progress:
                    progress(f"Skipping Bad sensor: {context}; {reason}; retaining project parameter")
                continue
            except asyncio.TimeoutError as exc:
                raise TimeoutError(f"OPC UA read timed out: {context}") from exc
            except Exception as exc:
                raise RuntimeError(
                    f"OPC UA read failed: {context}; {type(exc).__name__}: {exc}"
                ) from exc
            if not math.isfinite(value):
                raise ValueError(f"Invalid reading for {context}: {value!r}")
            value = normalize_reading(column, value)
            readings.append({"column": column, "node_id": node_id, "value": value,
                             "timestamp": datetime.now(timezone.utc).isoformat()})
        if progress:
            progress(f"Read {len(readings)}/{len(mapping)} inputs; closing OPC UA session")
        return readings


async def _read_tolerant_snapshot(mapping):
    """Return failures as observations; the model boundary decides which value to hold."""
    readings = []
    def observation(column, node_id, **fields):
        return dict(column=column, node_id=node_id,
                    timestamp=datetime.now(timezone.utc).isoformat(), **fields)
    try:
        async with Client(url=os.getenv("KEPSERVER_OPC_URL", "opc.tcp://127.0.0.1:49320"), timeout=15) as client:
            for column, node_id in mapping.items():
                try:
                    value = float(await client.get_node(node_id).read_value())
                    readings.append(observation(column, node_id, value=value))
                except Exception as exc:
                    readings.append(observation(column, node_id, error=f"{type(exc).__name__}: {exc}"))
    except Exception as exc:
        # Keep successful observations if only session teardown failed.
        seen = {r['column'] for r in readings}
        readings.extend(observation(column, node, error=f"{type(exc).__name__}: {exc}")
                        for column, node in mapping.items() if column not in seen)
    return readings
