"""User-uploaded dynamic calibration data and aligned comparison output."""
import io
import json
from pathlib import Path
from uuid import UUID, uuid4

import numpy as np
import pandas as pd

from services.input_series import STORE_DIR, profiles_from_frame

COMPONENTS = {'O2': 'O', 'NH4': 'NH', 'NO2': 'NO2', 'NO3': 'NO3', 'N2O': 'N2O'}
REQUIRED = [f'S{i}{suffix}' for suffix in ('O', 'NH', 'NO2', 'NO3') for i in range(1, 6)]
INPUT_COLUMNS = ['SNH', 'SNO2', 'SNO3', 'bCOD', 'XI', 'Effluent rate (L/s)',
                 'WAS (L/s)', 'RAS (L/s)', 'Aeration Tank 4_m3/h']


def numeric_frame(frame, columns, sheet, allow_missing=False, nonempty_columns=None):
    missing = set(['t (min)', *columns]) - set(frame.columns)
    if missing:
        raise ValueError(f'{sheet}: missing columns: {", ".join(sorted(missing))}')
    frame = frame[['t (min)', *columns]].dropna(how='all').copy()
    if not 2 <= len(frame) <= 5000:
        raise ValueError(f'{sheet}: provide between 2 and 5000 rows')
    for column in frame:
        try:
            frame[column] = pd.to_numeric(frame[column], errors='raise')
        except (ValueError, TypeError) as exc:
            raise ValueError(f'{sheet}: {column} must contain numbers or blank measurement cells') from exc
    times = frame['t (min)'].to_numpy(dtype=float)
    # Remove Excel timestamp floating point noise without rounding to minutes.
    times = np.round(times, 6)
    if not np.isfinite(times).all() or times[0] != 0 or not (np.diff(times) > 0).all():
        raise ValueError(f'{sheet}: t (min) must start at 0 and increase strictly')
    frame['t (min)'] = times
    values = frame[columns].to_numpy(dtype=float)
    if np.isinf(values).any() or (values < 0).any():
        raise ValueError(f'{sheet}: values must be finite and non-negative')
    if not allow_missing and np.isnan(values).any():
        raise ValueError(f'{sheet}: input values cannot be blank')
    required = REQUIRED if nonempty_columns is None else nonempty_columns
    if allow_missing and any(frame[column].notna().sum() == 0 for column in required):
        raise ValueError('validation: each required measurement column needs at least one value')
    return frame


def simulation_measurements(content, filename):
    """Read comparison-only measurements; operating inputs are not required."""
    from config.parameters import AllVariables
    try:
        frame = pd.read_excel(io.BytesIO(content), sheet_name='validation', engine='openpyxl')
    except Exception as exc:
        raise ValueError('Upload an .xlsx workbook containing a validation sheet') from exc
    frame.columns = frame.columns.astype(str).str.strip()
    columns = [name for name in AllVariables if name in frame]
    if not columns:
        raise ValueError('validation: include at least one model variable column, for example S5NH')
    frame = numeric_frame(frame, columns, 'validation', allow_missing=True, nonempty_columns=[])
    if not frame[columns].notna().any().any():
        raise ValueError('validation: provide at least one measured value')
    return {
        'id': uuid4().hex, 'filename': Path(filename.replace('\\', '/')).name[:200],
        'time_h': (frame['t (min)'] / 60).tolist(),
        'variables': {name: [None if pd.isna(value) else float(value) for value in frame[name]] for name in columns},
    }


def parse_workbook(content):
    try:
        with pd.ExcelFile(io.BytesIO(content), engine='openpyxl') as book:
            measured = pd.read_excel(book, sheet_name='validation')
            inputs = pd.read_excel(book, sheet_name='dyinput')
    except Exception as exc:
        raise ValueError('Upload an .xlsx workbook containing validation and dyinput sheets') from exc
    measured.columns = measured.columns.astype(str).str.strip()
    inputs.columns = inputs.columns.astype(str).str.strip()
    optional = [f'S{i}N2O' for i in range(1, 6) if f'S{i}N2O' in measured]
    measured = numeric_frame(measured, REQUIRED + optional, 'validation', allow_missing=True)
    inputs = numeric_frame(inputs, INPUT_COLUMNS, 'dyinput')
    if inputs['t (min)'].iloc[-1] < measured['t (min)'].iloc[-1]:
        raise ValueError('dyinput must cover the full validation time range')
    if (inputs['RAS (L/s)'] <= 0).any() or inputs['Aeration Tank 4_m3/h'].iloc[:8].mean() <= 0:
        raise ValueError('RAS must be positive and the initial airflow average must be positive')
    return measured, inputs


def save_measurements(content, filename):
    measured, inputs = parse_workbook(content)
    identifier = uuid4().hex
    data = {
        'id': identifier, 'filename': Path(filename.replace('\\', '/')).name[:200],
        'time_h': (measured['t (min)'] / 60).tolist(),
        'variables': {name: [None if pd.isna(x) else float(x) for x in measured[name]]
                      for name in measured if name != 't (min)'},
        'inputs': inputs.to_dict(orient='list'),
    }
    folder = STORE_DIR / 'calibration'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f'{identifier}.json').write_text(json.dumps(data, allow_nan=False), encoding='utf-8')
    return {key: value for key, value in data.items() if key != 'inputs'}


def read_measurements(identifier):
    path = STORE_DIR / 'calibration' / f'{UUID(str(identifier)).hex}.json'
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError as exc:
        raise ValueError('Uploaded measurements are no longer available. Upload the workbook again.') from exc


def optimization_inputs(data):
    frame = pd.DataFrame(data['variables'], index=np.asarray(data['time_h']) * 60)
    measured = {key: frame[[f'S{i}{suffix}' for i in range(1, 6) if f'S{i}{suffix}' in frame]]
                for key, suffix in COMPONENTS.items()}
    profiles = profiles_from_frame(pd.DataFrame(data['inputs']))
    overrides = {
        'dynamic_inputs': data['inputs'], 'time_series': profiles,
        'airflow_reference': [float(np.mean(profiles[f'airflow{i}']['values'][:8])) for i in (1, 2, 3)],
    }
    return measured, overrides


def comparison_result(data, before, after):
    times = np.asarray(data['time_h']) * 60
    result = {'time_h': data['time_h'], 'measured': data['variables'], 'before': {}, 'after': {}, 'metrics': {}}
    for label, record in [('before', before), ('after', after)]:
        if len(record) != len(times) or not np.allclose(record.index.to_numpy(dtype=float), times):
            raise ValueError('Simulation did not return the measurement timestamps')
        for name, measurements in data['variables'].items():
            predicted = record[name].to_numpy(dtype=float)
            if not np.isfinite(predicted).all():
                raise ValueError('Simulation returned non-finite concentrations')
            result[label][name] = predicted.tolist()
            observed = np.asarray(measurements, dtype=float)
            mask = np.isfinite(observed)
            result['metrics'].setdefault(name, {})[label] = (
                float(np.sqrt(np.mean((predicted[mask] - observed[mask]) ** 2))) if mask.any() else None)
    return result


def run_uploaded_calibration(parameters, identifier, oxygen_mode='calculated_kla', do_setpoints=None):
    from auto_calibration import ASMOptimization, run_auto_calibration
    data = read_measurements(identifier)
    measured, overrides = optimization_inputs(data)
    overrides.update(DOSetpoint=int(oxygen_mode == 'do_setpoint'),
                     constantKLa=int(oxygen_mode == 'constant_kla'))
    for tank, value in enumerate(do_setpoints if do_setpoints is not None else [0, 0, 1.6, 2.0, 2.2], 1):
        overrides[f'S{tank}DOsetpoint'] = value
    opt = ASMOptimization(measured, dynamic_switch=True,
                          calibration_parameters=parameters, parameter_overrides=overrides)
    before = opt.simulate_parameters(parameters)
    values, _ = run_auto_calibration(parameters, save_results=False, measured_data=measured,
                                    dynamic_switch=True, parameter_overrides=overrides)
    after = opt.simulate_parameters(values)
    return {'calibration_parameters': values, 'comparison': comparison_result(data, before, after)}


def template_workbook():
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(columns=['t (min)', *REQUIRED, *[f'S{i}N2O' for i in range(1, 6)]]).to_excel(
            writer, sheet_name='validation', index=False)
        pd.DataFrame(columns=['t (min)', *INPUT_COLUMNS]).to_excel(writer, sheet_name='dyinput', index=False)
        pd.DataFrame({'Instructions': [
            'Fill both sheets with at least two rows. t (min) starts at 0 and increases strictly.',
            'validation: tank 1–5 concentrations in mg/L. Blank measurements are skipped. N2O is optional.',
            'dyinput: SNH, SNO2, SNO3, bCOD, XI in mg/L; plant-wide flows in L/s; tank airflow in m3/h.',
            'dyinput must cover the measurement period. All input cells are required.',
            'The objective uses NH4 and NO3; all uploaded measured components appear in comparisons.',
        ]}).to_excel(writer, sheet_name='instructions', index=False)
    return output.getvalue()
