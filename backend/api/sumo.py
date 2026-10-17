from uuid import UUID
from fastapi import APIRouter, HTTPException, Request, Response, Query
from pydantic import BaseModel, Field
from models.sumo_engine import start_run, get_run, get_export
from services.sumo_data import MAX_BYTES, save_input, get_input, input_options, template_csv, parse_input

router = APIRouter()


class SumoInput(BaseModel):
    input_id: UUID | None = None
    input_columns: list[str] | None = None
    duration_h: float = Field(168, ge=1, le=168, allow_inf_nan=False)


@router.post('/sumo/runs', status_code=202)
def start(parameters: SumoInput):
    try:
        content = get_input(str(parameters.input_id)) if parameters.input_id else None
        if parameters.input_columns is not None:
            if content is None:
                raise ValueError('Upload the CSV for the selected parameters before running.')
            parse_input(content.encode('utf-8'), parameters.input_columns)
        return start_run(parameters.duration_h, content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get('/sumo/runs/{job_id}')
def status(job_id: UUID):
    result = get_run(str(job_id))
    if result is None:
        raise HTTPException(status_code=404, detail='SUMO run not found or expired.')
    return result


@router.post('/sumo/input')
async def upload_input(request: Request, filename: str = 'Sumo__Plant__Influent__param.csv',
                       columns: list[str] | None = Query(default=None)):
    if not filename.lower().endswith('.csv'):
        raise HTTPException(status_code=422, detail='Choose a .csv file.')
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_BYTES:
            raise HTTPException(status_code=413, detail='CSV must be no larger than 1 MB.')
    try:
        return save_input(bytes(content), filename, columns)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/sumo/runs/{job_id}/download')
def download(job_id: UUID):
    job = get_run(str(job_id))
    if job is None:
        raise HTTPException(status_code=404, detail='SUMO run not found or expired.')
    content = get_export(str(job_id))
    if content is None:
        raise HTTPException(status_code=409, detail='Result download is available after a successful simulation.')
    return Response(content=('\ufeff' + content).encode('utf-8'), media_type='text/csv',
                    headers={'Content-Disposition': f'attachment; filename="sumo_results_{job_id}.csv"'})


class TemplateInput(BaseModel):
    columns: list[str] = Field(min_length=1, max_length=12)


@router.get('/sumo/input-options')
def options():
    return input_options()


@router.post('/sumo/input-template')
def template(parameters: TemplateInput):
    try:
        content = template_csv(parameters.columns)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(content=('\ufeff' + content).encode('utf-8'), media_type='text/csv',
                    headers={'Content-Disposition': 'attachment; filename="Sumo__Plant__Influent__param.csv"'})
