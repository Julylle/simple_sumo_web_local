"""Live SUMO lifecycle endpoints. One active Scheduler job per backend process."""
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from liveSimulation import liveSimulation as live_sumo

router = APIRouter()

class LiveStart(BaseModel):
    mapping: dict[str, str] = Field(min_length=1, max_length=12)
    interval_minutes: int = Field(default=5, ge=1, le=60)

@router.post("/sumo/live/start", status_code=202)
def start(body: LiveStart):
    try:
        return live_sumo.start(body.mapping, body.interval_minutes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/sumo/live/status")
def status():
    return live_sumo.snapshot()

@router.post("/sumo/live/stop")
def stop():
    try:
        return live_sumo.stop()
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/sumo/live/download")
def download():
    try:
        content = live_sumo.export_csv()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(content=("\ufeff"+content).encode("utf-8"), media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="sumo_live_results.csv"'})
