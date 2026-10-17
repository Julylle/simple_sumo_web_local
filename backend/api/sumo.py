from uuid import UUID
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from models.sumo_engine import start_run, get_run

router = APIRouter()


class SumoInput(BaseModel):
    duration_h: float = Field(168, ge=1, le=168, allow_inf_nan=False)


@router.post('/sumo/runs', status_code=202)
def start(parameters: SumoInput):
    try:
        return start_run(parameters.duration_h)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get('/sumo/runs/{job_id}')
def status(job_id: UUID):
    result = get_run(str(job_id))
    if result is None:
        raise HTTPException(status_code=404, detail='SUMO run not found or expired.')
    return result
