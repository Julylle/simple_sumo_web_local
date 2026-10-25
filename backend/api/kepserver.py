"""Explicit snapshot and manual-run preparation endpoints."""
import asyncio
import csv
import io
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from services.kepserver import read_snapshot
from services.sumo_data import save_input

router = APIRouter()

class SnapshotRequest(BaseModel):
    mapping: dict[str, str] = Field(min_length=1, max_length=36)

@router.post("/kepserver/snapshot")
async def snapshot(request: SnapshotRequest):
    try:
        return {"readings": await asyncio.wait_for(read_snapshot(request.mapping), timeout=30)}
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
