"""Explicit snapshot and manual-run preparation endpoints."""
import asyncio
import csv
import io
import math
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from services.sensor_inputs import SENSOR_COLUMNS
from services.kepserver import read_snapshot
from services.sumo_data import save_input

router = APIRouter()

class SnapshotRequest(BaseModel):
    mapping: dict[str, str] = Field(min_length=1, max_length=len(SENSOR_COLUMNS))

@router.post("/kepserver/snapshot")
async def snapshot(request: SnapshotRequest):
    timeout = 120.0
    try:
        timeout = float(os.getenv("KEPSERVER_SNAPSHOT_TIMEOUT_SECONDS", "120"))
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("KEPSERVER_SNAPSHOT_TIMEOUT_SECONDS must be finite and positive")
        return {"readings": await asyncio.wait_for(read_snapshot(request.mapping), timeout=timeout)}
    except asyncio.TimeoutError as exc:
        raise HTTPException(
            status_code=504,
            detail=f"KEPServer snapshot timed out after up to {timeout:g} seconds: "
                   f"{exc or 'the selected sensor snapshot was not completed'}. "
                   "Check the selected tags or increase KEPSERVER_SNAPSHOT_TIMEOUT_SECONDS.",
        ) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"KEPServer read failed: {exc}") from exc

class PrepareRequest(BaseModel):
    readings: list[dict] = Field(min_length=1, max_length=12)

@router.post("/kepserver/prepare-input")
def prepare_input(request: PrepareRequest):
    # A single snapshot becomes constant boundary conditions for a manually initiated run.
    # This is not historical data and does not start SUMO.
    columns = [r.get("column") for r in request.readings]
    values = [r.get("value") for r in request.readings]
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["sim_time_ms", *columns])
    writer.writerow([0, *values])
    try:
        return save_input(output.getvalue().encode(), "kepserver_snapshot.csv", columns)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
