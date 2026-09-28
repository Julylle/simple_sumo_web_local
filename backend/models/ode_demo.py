"""Small ODE model used to test the secure simulation pipeline.

States
------
S_cod : biodegradable COD concentration [mg/L]
S_nh4 : ammonium-N concentration [mg/L]

The equations are deliberately simple; this is an integration test model, not a
calibrated wastewater process model.  A fixed-step RK4 solver is implemented
locally so the demo does not depend on SciPy.
"""
from __future__ import annotations

import numpy as np
from config.paths import STEADY_DATA_FILE


def rhs(_t: float, y: np.ndarray, *, do_mg_l: float, srt_d: float) -> np.ndarray:
    cod, nh4 = np.maximum(y, 0.0)

    # Simple oxygen-limited first-order kinetics.
    oxygen_factor = do_mg_l / (0.5 + do_mg_l)
    srt_factor = srt_d / (5.0 + srt_d)
    k_cod = 0.16 * oxygen_factor                 # 1/h
    k_nh4 = 0.10 * oxygen_factor * srt_factor   # 1/h

    d_cod_dt = -k_cod * cod
    d_nh4_dt = -k_nh4 * nh4
    return np.array([d_cod_dt, d_nh4_dt], dtype=float)


def solve_ode(*, cod0: float, nh40: float, do_mg_l: float, srt_d: float,
              duration_h: float, n_steps: int = 480) -> tuple[np.ndarray, np.ndarray]:
    """Solve the two-state ODE with classical fourth-order Runge-Kutta (RK4)."""
    n_steps = max(10, int(n_steps))
    t = np.linspace(0.0, float(duration_h), n_steps + 1)
    y = np.empty((n_steps + 1, 2), dtype=float)
    y[0] = [cod0, nh40]

    for i in range(n_steps):
        dt = t[i + 1] - t[i]
        kwargs = {"do_mg_l": do_mg_l, "srt_d": srt_d}
        k1 = rhs(t[i], y[i], **kwargs)
        k2 = rhs(t[i] + dt / 2, y[i] + dt * k1 / 2, **kwargs)
        k3 = rhs(t[i] + dt / 2, y[i] + dt * k2 / 2, **kwargs)
        k4 = rhs(t[i] + dt, y[i] + dt * k3, **kwargs)
        y[i + 1] = np.maximum(y[i] + dt * (k1 + 2*k2 + 2*k3 + k4) / 6, 0.0)

    return t, y


# def run_demo(*, flow_m3_d: float, influent_cod_mg_l: float,
#              influent_nh4_mg_l: float, do_mg_l: float, srt_d: float,
#              duration_h: float) -> dict[str, np.ndarray]:
#     """Return full private model output. The API layer decides what may leave the server."""
#     t, y = solve_ode(
#         cod0=influent_cod_mg_l,
#         nh40=influent_nh4_mg_l,
#         do_mg_l=do_mg_l,
#         srt_d=srt_d,
#         duration_h=duration_h,
#     )
#     cod, nh4 = y[:, 0], y[:, 1]

#     # Synthetic N2O indicator for UI testing only; not a mechanistic N2O model.
#     removal_rate = np.maximum(-np.gradient(nh4, t), 0.0)
#     low_do_factor = 1.0 + 1.5 / max(do_mg_l, 0.2)
#     n2o_index = flow_m3_d * removal_rate * low_do_factor / 1000.0

#     return {
#         "time_h": t,
#         "cod_mg_l": cod,
#         "nh4_mg_l": nh4,
#         "n2o_index": n2o_index,
#         # Example private state: intentionally not included in ALLOWED_OUTPUTS.
#         "private_total_state": cod + nh4,
#     }


import numpy as np
import pandas as pd
import pickle
import time
from pathlib import Path

from config.parameters import initial_values, model_parameters, AllVariables
from models.asm_model import GrowthCoupledProduction
from visualization.plotting import CompareDynamicCombine
try:
    from visualization.plotting import CompareSteady
    PLOTTING_AVAILABLE = True
except ImportError:
    print("Warning: matplotlib not available, skipping plots")
    PLOTTING_AVAILABLE = False
from assimulo.problem import Explicit_Problem
from assimulo.solvers import CVode

STEADY_STATE_FILE = 'steady_state_initial_values.pkl'


def update_calibration_params(calibration_params, filename='calibrated_parameters.pkl'):
    """Return parameters updated from a pickled parameter dictionary.

    ``filename=None`` disables pickle loading.  Values already present in
    ``calibration_params`` are replaced by values from the pickle.
    """
    if filename is None:
        return calibration_params

    filename = Path(filename)
    try:
        with open(filename, 'rb') as f:
            calibrated_params = pickle.load(f)
    except FileNotFoundError:
        print(f"Warning: {filename} not found; using initial calibration parameters.")
        return calibration_params

    if not isinstance(calibrated_params, dict):
        raise TypeError(f"{filename} must contain a parameter dictionary.")
    invalid_names = [name for name in calibrated_params if not isinstance(name, str)]
    if invalid_names:
        raise TypeError(f"{filename} must contain string parameter names.")

    calibration_params.update(calibrated_params)
    print(f"Loaded {len(calibrated_params)} parameters from {filename}.")
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
    
    print("\n" + "="*70)
    print("PHASE 1: STEADY-STATE SIMULATION")
    print("="*70 + "\n")
    
    # Calibration parameters for steady state

    from config.parameters import calibration_params_initial

    params = model_parameters.copy()
    params.update(calibration_params_initial)
    params = update_calibration_params(params, paraName)
    if parameter_overrides is not None:
        params.update(parameter_overrides)
    params['dynamicSwitch'] = 0
    
    initial_numbers = [value for value in initial_values.values()]
    
    # Run simulation
    print("Running steady-state simulation for 180 days...")
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
    
    elapsed_time = time.time() - start_time
    print(f"Simulation completed in {elapsed_time:.2f} seconds\n")
    
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
        print(f"Saved steady-state initial values to {STEADY_STATE_FILE}.")

    if not compare:
        return simuRecord, params, steady_state_initial_values
    
    # Load measured data
    print("Loading measured data...")
    dfO2 = pd.read_excel(STEADY_DATA_FILE, sheet_name='O2', header=0, index_col=0).iloc[0]
    dfNO3 = pd.read_excel(STEADY_DATA_FILE, sheet_name='NO3', header=0, index_col=0).iloc[0]
    dfNO2 = pd.read_excel(STEADY_DATA_FILE, sheet_name='NO2', header=0, index_col=0).iloc[0]
    dfNH4 = pd.read_excel(STEADY_DATA_FILE, sheet_name='NH4', header=0, index_col=0).iloc[0]
    dfN2O = pd.read_excel(STEADY_DATA_FILE, sheet_name='N2O', header=0, index_col=0).iloc[0]
    
    # Extract simulated values at steady state
    simu_NO3 = simuRecord.filter(regex=r'S.*NO3').iloc[-1, :]
    simu_NO2 = simuRecord.filter(regex=r'S.*NO2').iloc[-1, :]
    simu_NH4 = simuRecord.filter(regex=r'S.*NH$').iloc[-1, :]
    simu_N2O = simuRecord[['S1N2O', 'S2N2O', 'S3N2O', 'S4N2O', 'S5N2O']].iloc[-1, :]
    simu_O2 = simuRecord[['S3O', 'S4O', 'S5O']].iloc[-1, :]
    
    # Compare with measured data
    print("\nComparison of Simulation vs. Measured Data:")
    print("-" * 70)
    mlss5 = simuRecord[['X5AOB', 'X5NOB', 'X5I', 'X5H']].iloc[-1, :].sum()
    mlss1 = simuRecord[['X1AOB', 'X1NOB', 'X1I', 'X1H']].iloc[-1, :].sum()
    # Sum biomass components across the four states for Zone 1 at each time
    # to produce a time-indexed DataFrame with column name 'X_MLSS'.
    MLSS_simu = simuRecord[['X1AOB', 'X1NOB', 'X1I', 'X1H']].sum(axis=1).to_frame('X_MLSS')

    unit1 = 'Concentration (mg/L)'
    unit2 = 'MLSS (mg/L)'
    if plot and PLOTTING_AVAILABLE:
        CompareSteady(simu_O2, dfO2, unit1)
        CompareSteady(simu_NO3, dfNO3, unit1)
        CompareSteady(simu_NO2, dfNO2, unit1)
        CompareSteady(simu_NH4, dfNH4, unit1)
        CompareSteady(simu_N2O, dfN2O, unit1)
        CompareDynamicCombine(MLSS_simu, None, unit2, 'SteadyResults')
        
        # CompareSteady(simu_N2O, dfN2O, unit1)
    else:
        print("Plots skipped (matplotlib not available)")
    
    print("-" * 70)
    print("Steady-state simulation completed successfully!")
    print(f'MLSS is {mlss1:.2f} mg/L in Zone 1 and {mlss5:.2f} mg/L in Zone 5')
    print(f'AOB, NOB, I, H are {list(simuRecord[["X5AOB", "X5NOB", "X5I", "X5H"]].iloc[-1, :])} mg/L in Zone 5')
    
    print("="*70 + "\n")
    
    return simuRecord, params, steady_state_initial_values