#%%
#!/usr/bin/env python
"""
Steady State Simulation and Comparison
This script runs the steady-state ASM model and compares with measured data.
"""

import numpy as np
import pandas as pd
import pickle
import time
from pathlib import Path

from config.parameters import initial_values, model_parameters, AllVariables
from config.paths import BACKEND_DIR, STEADY_DATA_FILE, STEADY_STATE_FILE
from models.asm_model import GrowthCoupledProduction
from assimulo.problem import Explicit_Problem
from assimulo.solvers import CVode


def update_calibration_params(calibration_params, filename='calibrated_parameters.pkl'):
    """Return parameters updated from a pickled parameter dictionary.

    ``filename=None`` disables pickle loading.  Values already present in
    ``calibration_params`` are replaced by values from the pickle.
    """
    if filename is None:
        return calibration_params

    filename = Path(filename)
    if not filename.is_absolute():
        filename = BACKEND_DIR / filename
    try:
        with open(filename, 'rb') as f:
            calibrated_params = pickle.load(f)
    except FileNotFoundError:
        # print(f"Warning: {filename} not found; using initial calibration parameters.")
        return calibration_params

    if not isinstance(calibrated_params, dict):
        raise TypeError(f"{filename} must contain a parameter dictionary.")
    invalid_names = [name for name in calibrated_params if not isinstance(name, str)]
    if invalid_names:
        raise TypeError(f"{filename} must contain string parameter names.")

    calibration_params.update(calibrated_params)
    # print(f"Loaded {len(calibrated_params)} parameters from {filename}.")
    return calibration_params


def run_steady_simulation(
    parameter_overrides=None,
    tfinal=None,
    output_times=None,
    save_state=True,
    paraName='calibrated_parameters.pkl',
):
    """Run a steady simulation, optionally loading parameters from ``paraName``.
    Merge priority (lowest to highest) is: model defaults, calibration initial
    values, the ``paraName`` pickle, then ``parameter_overrides``.
    """
    from config.parameters import calibration_params_initial

    params = model_parameters.copy()
    params.update(calibration_params_initial)
    params = update_calibration_params(params, paraName)
    if parameter_overrides is not None:
        params.update(parameter_overrides)
    params['dynamicSwitch'] = 0
    
    initial_numbers = [value for value in initial_values.values()]
    if params.get('DOSetpoint', 0):
        for tank in range(1, 6):
            initial_numbers[AllVariables.index(f'S{tank}O')] = params[f'S{tank}DOsetpoint']
    
    # Run simulation
    # print("Running steady-state simulation for 180 days...")
    start_time = time.time()
    
    ASM_configuration = GrowthCoupledProduction(params)
    model = Explicit_Problem(ASM_configuration.rhs, initial_numbers, 0.0)
    model.name = 'ASM-N2O steady simulation'
    
    sim = CVode(model)
    if tfinal is None:
        tfinal = 60 * 24 * 180 # 180 days in minutes
    if output_times is None:
        t, y = sim.simulate(tfinal)
    else:
        t, y = sim.simulate(tfinal, ncp_list=list(output_times))
    
    # Build simulation record
    simuRecord = pd.DataFrame()
    for i in range(len(AllVariables)):
        statei = pd.DataFrame({'Time': t, AllVariables[i]: y[:, i]})
        statei.set_index('Time', inplace=True)
        simuRecord = pd.concat([simuRecord, statei], axis=1, ignore_index=False)

    # Persist the final steady-state concentrations for Phase 3.  Retaining
    # the initial_values keys guarantees the state order expected by rhs().
    steady_state_initial_values = {
        name: float(value)
        for name, value in zip(initial_values.keys(), y[-1, :])
    }
    
    return simuRecord, params, steady_state_initial_values

