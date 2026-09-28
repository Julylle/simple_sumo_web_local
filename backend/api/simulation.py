import io
import pandas as pd
from fastapi import APIRouter, HTTPException, Request, Response
from services.input_series import SERIES, default_profiles, metadata, save_upload
from schemas.simulation import SimulationInput
from services.simulation_service import simulate
from config.parameters import calibration_params_initial

router = APIRouter()


@router.get("/calibration-parameters", response_model=dict[str, float])
def get_calibration_parameters():
    """Expose the initial calibration values displayed by the client."""
    return calibration_params_initial.copy()

@router.post("/simulation")
def run_simulation(parameters: SimulationInput):
    try:
        return {"result": simulate(parameters)}
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/input-series/defaults')
def get_default_series():
    return {key: metadata(key, value) for key, value in default_profiles().items()}


@router.get('/input-series/template/{key}')
def get_series_template(key: str):
    if key not in SERIES:
        raise HTTPException(status_code=404, detail='Unknown input series')
    profile = default_profiles()[key]
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame({'time_h': profile['time_h'], 'value': profile['values']}).to_excel(writer, index=False, sheet_name='series')
        pd.DataFrame({'unit': [SERIES[key][1]], 'basis': ['Single lane'],
                      'interpolation': ['Previous value held; final value held after end']}).to_excel(writer, index=False, sheet_name='instructions')
    return Response(output.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': f'attachment; filename="{key}_template.xlsx"'})


@router.post('/input-series/{key}')
async def upload_series(key: str, request: Request, filename: str = 'series.xlsx'):
    content = await request.body()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail='Excel file must be under 5 MB')
    try:
        return save_upload(key, content, filename)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f'Cannot import Excel: {exc}') from exc
