"""Live SUMO lifecycle endpoints. One active Scheduler job per backend process."""
from fastapi import APIRouter, HTTPException, Response, UploadFile, File, Form
import json
from typing import Literal
from pydantic import BaseModel, Field
from liveSimulation import liveSimulation as live_sumo
from services.live_models import register_model, model_status, MAX_MODEL_BYTES, MAX_STATE_BYTES, BUILTIN_DIR

router = APIRouter()

class LiveStart(BaseModel):
    mode: Literal["live", "history_then_live"] = "live"
    history_start: str | None = None
    history_end: str | None = None
    mapping: dict[str, str] = Field(min_length=1, max_length=40)
    interval_minutes: int = Field(default=1, ge=1, le=60)
    model_id: str = Field(default="builtin", min_length=1, max_length=64)

@router.post("/sumo/live/start", status_code=202)
def start(body: LiveStart):
    try:
        return live_sumo.start(body.mapping, body.interval_minutes, body.model_id,
                               mode=body.mode, history_start=body.history_start, history_end=body.history_end)
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


@router.post("/sumo/live/resume", status_code=202)
def resume():
    try:
        return live_sumo.resume()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/sumo/live/comparisons")
def comparisons(run_id: str):
    from services.sensor_comparisons import read_comparisons, comparison_database
    snapshot = live_sumo.snapshot()
    if snapshot.get('id') != run_id:
        raise HTTPException(status_code=409, detail='Simulation changed; refresh sensor comparisons.')
    try:
        return read_comparisons(snapshot)
    except Exception as exc:
        import logging
        logging.exception('Sensor comparison read failed')
        reasons = {1049: 'Database does not exist.', 1045: 'MySQL login denied.',
                   1044: 'MySQL account cannot access this database.',
                   1146: 'Required raw_data/raw_variables tables are missing.',
                   2003: 'Cannot connect to MySQL.', 2013: 'MySQL connection lost or query timed out.'}
        code = exc.args[0] if exc.args and isinstance(exc.args[0], int) else None
        reason = reasons.get(code, 'Check collector/database access and backend logs.')
        if isinstance(exc, KeyError) and exc.args == ('MYSQL_PASSWORD',):
            reason = 'MYSQL_PASSWORD is not configured in the backend environment.'
        raise HTTPException(status_code=503,
                            detail=f'Sensor comparisons from {comparison_database()} unavailable. {reason}') from exc
