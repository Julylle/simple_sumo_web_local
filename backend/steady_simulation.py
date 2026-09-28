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
    plot=True,
    compare=True,
    paraName='calibrated_parameters.pkl',
):
    """Run a steady simulation, optionally loading parameters from ``paraName``.

    Merge priority (lowest to highest) is: model defaults, calibration initial
    values, the ``paraName`` pickle, then ``parameter_overrides``.
    """
    
    # print("\n" + "="*70)
    # print("PHASE 1: STEADY-STATE SIMULATION")
    # print("="*70 + "\n")
    
    # Calibration parameters for steady state

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
    
    # elapsed_time = time.time() - start_time
    # print(f"Simulation completed in {elapsed_time:.2f} seconds\n")
    
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
    if save_state:
        with open(STEADY_STATE_FILE, 'wb') as f:
            pickle.dump(steady_state_initial_values, f)
        # print(f"Saved steady-state initial values to {STEADY_STATE_FILE}.")

    # if not compare:
    #     return simuRecord, params, steady_state_initial_values
    
    # Load measured data
    # print("Loading measured data...")
    # dfO2 = pd.read_excel(STEADY_DATA_FILE, sheet_name='O2', header=0, index_col=0).iloc[0]
    # dfNO3 = pd.read_excel(STEADY_DATA_FILE, sheet_name='NO3', header=0, index_col=0).iloc[0]
    # dfNO2 = pd.read_excel(STEADY_DATA_FILE, sheet_name='NO2', header=0, index_col=0).iloc[0]
    # dfNH4 = pd.read_excel(STEADY_DATA_FILE, sheet_name='NH4', header=0, index_col=0).iloc[0]
    # dfN2O = pd.read_excel(STEADY_DATA_FILE, sheet_name='N2O', header=0, index_col=0).iloc[0]
    
    # # Extract simulated values at steady state
    # simu_NO3 = simuRecord.filter(regex=r'S.*NO3').iloc[-1, :]
    # simu_NO2 = simuRecord.filter(regex=r'S.*NO2').iloc[-1, :]
    # simu_NH4 = simuRecord.filter(regex=r'S.*NH$').iloc[-1, :]
    # simu_N2O = simuRecord[['S1N2O', 'S2N2O', 'S3N2O', 'S4N2O', 'S5N2O']].iloc[-1, :]
    # simu_O2 = simuRecord[['S3O', 'S4O', 'S5O']].iloc[-1, :]
    
    # # Compare with measured data
    # print("\nComparison of Simulation vs. Measured Data:")
    # print("-" * 70)
    # mlss5 = simuRecord[['X5AOB', 'X5NOB', 'X5I', 'X5H']].iloc[-1, :].sum()
    # mlss1 = simuRecord[['X1AOB', 'X1NOB', 'X1I', 'X1H']].iloc[-1, :].sum()
    # # Sum biomass components across the four states for Zone 1 at each time
    # # to produce a time-indexed DataFrame with column name 'X_MLSS'.
    # MLSS_simu = simuRecord[['X1AOB', 'X1NOB', 'X1I', 'X1H']].sum(axis=1).to_frame('X_MLSS')

    # unit1 = 'Concentration (mg/L)'
    # unit2 = 'MLSS (mg/L)'
    
    # print("-" * 70)
    # print("Steady-state simulation completed successfully!")
    # print(f'MLSS is {mlss1:.2f} mg/L in Zone 1 and {mlss5:.2f} mg/L in Zone 5')
    # print(f'AOB, NOB, I, H are {list(simuRecord[["X5AOB", "X5NOB", "X5I", "X5H"]].iloc[-1, :])} mg/L in Zone 5')
    
    # print("="*70 + "\n")
    
    return simuRecord, params, steady_state_initial_values


if __name__ == '__main__':
    run_steady_simulation()

# %%
