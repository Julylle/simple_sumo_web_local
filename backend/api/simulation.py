import io
import pandas as pd
from fastapi import APIRouter, HTTPException, Request, Response
from services.input_series import SERIES, default_profiles, metadata, save_upload
from schemas.simulation import AutoCalibrationInput, SimulationInput
from services.calibration_data import save_measurements, template_workbook, run_uploaded_calibration, simulation_measurements
from services.simulation_service import simulate
from config.parameters import calibration_params_initial

router = APIRouter()


@router.get("/calibration-parameters", response_model=dict[str, float])
def get_calibration_parameters():
    """Expose the initial calibration values displayed by the client."""
    return calibration_params_initial.copy()


@router.post("/auto-calibration")
def auto_calibrate(parameters: AutoCalibrationInput):
    try:
        return run_uploaded_calibration(parameters.calibration_parameters, parameters.measurement_id,
                                        parameters.oxygen_mode, parameters.do_setpoints)
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Auto-calibration requires PyGMO and Assimulo on the server.") from exc
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail="Auto-calibration failed to produce a valid solution. Check server logs.") from exc


@router.post('/calibration-measurements')
async def upload_calibration_measurements(request: Request, filename: str = 'measurements.xlsx'):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail='Excel file must be under 5 MB')
    if not filename.lower().endswith('.xlsx'):
        raise HTTPException(status_code=422, detail='Upload an .xlsx workbook')
    try:
        return save_measurements(bytes(content), filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get('/calibration-measurements/template')
def calibration_template():
    return Response(template_workbook(),
                    media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition': 'attachment; filename="calibration_template.xlsx"'})


@router.post('/simulation-measurements')
async def upload_simulation_measurements(request: Request, filename: str = 'measurements.xlsx'):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(status_code=413, detail='Excel file must be under 5 MB')
    if not filename.lower().endswith('.xlsx'):
        raise HTTPException(status_code=422, detail='Upload an .xlsx workbook')
    try:
        return simulation_measurements(bytes(content), filename)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
