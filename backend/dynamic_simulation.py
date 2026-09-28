#%%
#!/usr/bin/env python
"""
Dynamic Simulation
This script runs the dynamic ASM model using calibrated parameters.
"""

import numpy as np
import pandas as pd
import pickle
import time
from pathlib import Path

from config.parameters import initial_values, model_parameters, AllVariables
from config.paths import BACKEND_DIR, DYNAMIC_DATA_FILE, STEADY_STATE_FILE
from models.asm_model import GrowthCoupledProduction
from assimulo.problem import Explicit_Problem
from assimulo.solvers import CVode

from steady_simulation import run_steady_simulation

PROJECT_DIR = BACKEND_DIR


def load_calibrated_parameters(paraName='calibrated_parameters.pkl'):
    """Load and validate a pickled parameter dictionary."""
    if paraName is None:
        return None
    paraName = Path(paraName)
    if not paraName.is_absolute():
        paraName = BACKEND_DIR / paraName
    try:
        with open(paraName, 'rb') as f:
            calibrated_params = pickle.load(f)
    except FileNotFoundError:
        print(f"Warning: {paraName} not found. Using default parameters.")
        return None

    if not isinstance(calibrated_params, dict):
        raise TypeError(f"{paraName} must contain a parameter dictionary.")
    if any(not isinstance(name, str) for name in calibrated_params):
        raise TypeError(f"{paraName} must contain string parameter names.")
    print(f"Loaded {len(calibrated_params)} parameters from {paraName}.")
    print("Parameters loaded from paraName:")
    for name in sorted(calibrated_params):
        value = calibrated_params[name]
        if isinstance(value, (int, float, np.integer, np.floating)):
            print(f"  {name:15s} = {value:.10g}")
        else:
            print(f"  {name:15s} = {value!r}")
    return calibrated_params


def load_steady_state_initial_values(filename=STEADY_STATE_FILE, DOSetpoint=False):
    """Load Phase 1's final concentrations in the model's state order."""
    try:
        with open(filename, 'rb') as f:
            steady_state = pickle.load(f)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"{filename} was not found. Run phase01_steady_simulation.py "
            "before Phase 3."
        ) from exc

    if not isinstance(steady_state, dict):
        raise TypeError(f"{filename} must contain a state dictionary.")
    
    missing_states = [name for name in initial_values if name not in steady_state]
    if missing_states:
        raise ValueError(
            f"{filename} is missing {len(missing_states)} model states: "
            f"{', '.join(missing_states)}"
        )
    steady_state['S1O0'] = model_parameters['S1DOsetpoint'] if DOSetpoint else steady_state['S1O0']
    steady_state['S2O0'] = model_parameters['S2DOsetpoint'] if DOSetpoint else steady_state['S2O0']
    steady_state['S3O0'] = model_parameters['S3DOsetpoint'] if DOSetpoint else steady_state['S3O0']
    steady_state['S4O0'] = model_parameters['S4DOsetpoint'] if DOSetpoint else steady_state['S4O0']
    steady_state['S5O0'] = model_parameters['S5DOsetpoint'] if DOSetpoint else steady_state['S5O0']
    initial_numbers = np.asarray(
        [steady_state[name] for name in initial_values],
        dtype=float,
    )
    if not np.isfinite(initial_numbers).all():
        raise ValueError(f"{filename} contains non-finite concentrations.")

    print(f"Using Phase 1 steady-state concentrations from {filename}")
    return initial_numbers


def build_dynamic_initial_state(
    initialization_mode='measured',
    parameters=None,
    steady_state_file=STEADY_STATE_FILE,
    measurement_file=DYNAMIC_DATA_FILE,
):
    """Build the Phase 3 state while retaining unmeasured steady biomass.

    ``measured`` starts from the saved steady state and replaces NH, NO2, NO3
    and available DO states with the first measured profile. ``steady`` uses
    the Phase 1 state unchanged, and ``config`` uses config.initial_values.
    """
    parameters = parameters or model_parameters
    valid_modes = {'measured', 'steady', 'config'}
    if initialization_mode not in valid_modes:
        raise ValueError(
            f"initialization_mode must be one of {sorted(valid_modes)}, "
            f"not {initialization_mode!r}"
        )

    if initialization_mode == 'config':
        state = {name: float(value) for name, value in initial_values.items()}
        print("Using config.parameters.initial_values for Phase 3 initialization")
    else:
        steady_vector = load_steady_state_initial_values(
            filename=steady_state_file,
            DOSetpoint=False,
        )
        state = dict(zip(initial_values, map(float, steady_vector)))

    if initialization_mode == 'measured':
        validation = pd.read_excel(measurement_file, sheet_name='validation', header=0)
        validation.columns = [str(name).strip() for name in validation.columns]
        replaced = []
        for tank in range(1, 6):
            for component in ('NH', 'NO2', 'NO3'):
                column = f'S{tank}{component}'
                values = pd.to_numeric(validation[column], errors='coerce').dropna()
                if not values.empty:
                    state[f'{column}0'] = float(values.iloc[0])
                    replaced.append(column)
            oxygen_column = f'S{tank}O'
            if oxygen_column in validation:
                oxygen = pd.to_numeric(validation[oxygen_column], errors='coerce').dropna()
                if not oxygen.empty:
                    state[f'{oxygen_column}0'] = float(oxygen.iloc[0])
                    replaced.append(oxygen_column)
        print(
            f"Measured initialization: replaced {len(replaced)} soluble states "
            f"from {Path(measurement_file).name}"
        )

    if parameters.get('DOSetpoint', 0):
        for tank in range(1, 6):
            state[f'S{tank}O0'] = float(parameters[f'S{tank}DOsetpoint'])

    vector = np.asarray([state[name] for name in initial_values], dtype=float)
    if not np.isfinite(vector).all():
        raise ValueError("The constructed Phase 3 initial state contains non-finite values")
    return vector


def apply_biomass_scales(initial_numbers, parameters):
    """Apply optional active-biomass multipliers used by hybrid calibration."""
    scaled = np.asarray(initial_numbers, dtype=float).copy()
    for biomass, parameter_name in (('NOB', 'XNOB_scale'), ('AOB', 'XAOB_scale')):
        scale = float(parameters.get(parameter_name, 1.0))
        if scale <= 0:
            raise ValueError(f"{parameter_name} must be positive")
        for tank in range(1, 6):
            scaled[AllVariables.index(f'X{tank}{biomass}')] *= scale
        if scale != 1.0:
            print(f"Applied {parameter_name} = {scale:.6g} to initial {biomass} states")
    return scaled


def print_dynamic_fit_metrics(simulation, measurement, label):
    """Print time-aligned RMSE and bias for a five-tank concentration group."""
    errors = []
    print(f"{label} fit metrics:")
    for index in range(min(len(simulation.columns), len(measurement.columns))):
        measured = measurement.iloc[:, index].dropna()
        if measured.empty:
            print(f"  {simulation.columns[index]:8s} no measured values")
            continue
        predicted = np.interp(
            measured.index.to_numpy(dtype=float),
            simulation.index.to_numpy(dtype=float),
            simulation.iloc[:, index].to_numpy(dtype=float),
        )
        error = predicted - measured.to_numpy(dtype=float)
        errors.extend(error)
        print(
            f"  {simulation.columns[index]:8s} "
            f"RMSE={np.sqrt(np.mean(error**2)):.4f} mg/L, "
            f"bias={np.mean(error):+.4f} mg/L"
        )
    if errors:
        errors = np.asarray(errors)
        print(
            f"  overall  RMSE={np.sqrt(np.mean(errors**2)):.4f} mg/L, "
            f"bias={np.mean(errors):+.4f} mg/L"
        )


def run_dynamic_simulation(
    parameter_overrides=None,
    initial_state=None,
    output_times=None,
    plot=True,
    compare=True,
    paraName='calibrated_parameters.pkl',
    initialization_mode='steady',
    refresh_steady_state=True,
    measurement_file=DYNAMIC_DATA_FILE,
):
    
    from config.parameters import calibration_params_initial

    params = model_parameters.copy()
    params.update(calibration_params_initial)
    calibrated_params = load_calibrated_parameters(paraName)
    if calibrated_params:
        params.update(calibrated_params)
    if parameter_overrides is not None:
        params.update(parameter_overrides)
    if initial_state is None and refresh_steady_state and initialization_mode in {'measured', 'steady'}:
        _, _, steady_state = run_steady_simulation(
            paraName=paraName,
            parameter_overrides=parameter_overrides,
            save_state=initialization_mode == 'measured',
            plot=plot,
            compare=compare,
        )
        if initialization_mode == 'steady':
            initial_state = [steady_state[name] for name in initial_values]
    # Set dynamic mode
    params['dynamicSwitch'] = 1

    if initial_state is None:
        initial_numbers = build_dynamic_initial_state(
            initialization_mode=initialization_mode,
            parameters=params,
            measurement_file=measurement_file,
        )
    else:
        initial_numbers = np.asarray(initial_state, dtype=float)
    if len(initial_numbers) != len(AllVariables):
        raise ValueError(
            f"initial_state has {len(initial_numbers)} values; expected {len(AllVariables)}"
        )
    initial_numbers = apply_biomass_scales(initial_numbers, params)
    
    ASM_configuration = GrowthCoupledProduction(params)
    model = Explicit_Problem(ASM_configuration.rhs, initial_numbers, 0.0)
    model.name = 'ASM-N2O dynamic simulation'
    
    sim = CVode(model)
    tfinal = float(output_times[-1]) if output_times is not None else 960
    if output_times is None:
        t, y = sim.simulate(tfinal)
    else:
        t, y = sim.simulate(tfinal, ncp_list=list(output_times))
    
    # Build simulation record
    dynaRecord = pd.DataFrame()
    for i in range(len(AllVariables)):
        statei = pd.DataFrame({'Time': t, AllVariables[i]: y[:, i]})
        statei.set_index('Time', inplace=True)
        dynaRecord = pd.concat([dynaRecord, statei], axis=1, ignore_index=False)
    return dynaRecord, params

if __name__ == '__main__':
    hybrid_parameters = PROJECT_DIR / 'calibrated_hybrid_parameters.pkl'
    rate_parameters = PROJECT_DIR / 'calibrated_rate_parameters.pkl'
    selected_parameters = hybrid_parameters if hybrid_parameters.exists() else rate_parameters
    run_dynamic_simulation(
        paraName= None, # selected_parameters,
        initialization_mode='measured', # three options: 'config', 'steady'， 'measured'
    )

# %%
