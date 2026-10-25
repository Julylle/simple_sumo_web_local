"""Live SUMO lifecycle endpoints. One active Scheduler job per backend process."""
from fastapi import APIRouter, HTTPException, Response, UploadFile, File, Form
import json
from pydantic import BaseModel, Field
from liveSimulation import liveSimulation as live_sumo
from services.live_models import register_model, model_status, MAX_MODEL_BYTES, MAX_STATE_BYTES, BUILTIN_DIR

router = APIRouter()

class LiveStart(BaseModel):
    mapping: dict[str, str] = Field(min_length=1, max_length=40)
    interval_minutes: int = Field(default=5, ge=1, le=60)
    model_id: str = Field(default="builtin", min_length=1, max_length=64)

@router.post("/sumo/live/start", status_code=202)
def start(body: LiveStart):
    try:
        return live_sumo.start(body.mapping, body.interval_minutes, body.model_id)
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


@router.post("/sumo/live/models", status_code=202)
async def upload_model(project: UploadFile | None = File(None),
                       initial_state: UploadFile | None = File(None),
                       state_mode: str = Form(...), mapping: str = Form('{}'),
                       tolerance: float = Form(1e-6)):

    try:
        model_bytes = await project.read(MAX_MODEL_BYTES + 1) if project else (
            BUILTIN_DIR / 'Cixi Eastern WWTP_20260920.sumo').read_bytes()
        state_bytes = await initial_state.read(MAX_STATE_BYTES + 1) if initial_state else None
        if initial_state and not (initial_state.filename or '').lower().endswith('.xml'):
            raise ValueError('Choose a steady-state .xml file.')
        return register_model(model_bytes, project.filename if project else 'Cixi Eastern WWTP_20260920.sumo',
                              state_bytes=state_bytes, mapping=json.loads(mapping),
                              state_mode=state_mode, tolerance=tolerance)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if project:
            await project.close()
        if initial_state:
            await initial_state.close()



@router.get("/sumo/live/models/{model_id}")
def uploaded_model_status(model_id: str):
    try:
        return model_status(model_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
