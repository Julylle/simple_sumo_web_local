"""Read a single OPC UA snapshot; no background polling or simulation."""
import math
import os
from datetime import datetime, timezone

from asyncua import Client
from services.sumo_data import ALLOWED_COLUMNS

DEFAULT_NODE = "ns=2;s=GEeth.PLC128.Influent_ammonia_sensor"

async def read_snapshot(mapping: dict[str, str]):
    if not mapping:
        raise ValueError("Configure at least one sensor mapping.")
    if any(key not in ALLOWED_COLUMNS for key in mapping):
        raise ValueError("Unsupported SUMO input parameter.")
    if any(not isinstance(node, str) or not node.strip() for node in mapping.values()):
        raise ValueError("Every mapped parameter requires an OPC UA node ID.")
    url = os.getenv("KEPSERVER_OPC_URL", "opc.tcp://192.168.1.100:49320")
    async with Client(url=url, timeout=10) as client:
        readings = []
        for column, node_id in mapping.items():
            node = client.get_node(node_id)
            value = float(await node.read_value())
            if not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid reading for {column}")
            readings.append({"column": column, "node_id": node_id, "value": value,
                             "timestamp": datetime.now(timezone.utc).isoformat()})
        return readings
