#!/usr/bin/env python
"""
Auto-Calibration using PyGMO
This script optimizes the shared calibration parameter list using the PyGMO archipelago algorithm.
"""

import numpy as np
import pandas as pd
import pickle
import os
from config.parameters import initial_values, model_parameters, AllVariables, calibration_params_initial
from steady_simulation import run_steady_simulation
from dynamic_simulation import run_dynamic_simulation

import pygmo as pg
from pygmo import problem

from config.paths import STEADY_DATA_FILE, DYNAMIC_DATA_FILE, BACKEND_DIR


def load_measured_data(dynamic_switch=None):
    """Load steady or dynamic measurements according to ``dynamicSwitch``."""
    if dynamic_switch is None:
        dynamic_switch = model_parameters.get('dynamicSwitch', 0)
    dynamic_switch = bool(dynamic_switch)
    data_file = DYNAMIC_DATA_FILE if dynamic_switch else STEADY_DATA_FILE

    try:
        # Open the workbook once. Besides being faster, this avoids repeatedly
        # acquiring a OneDrive-hosted file while Excel may be syncing it.
        with pd.ExcelFile(data_file) as workbook:
            if dynamic_switch:
                validation = pd.read_excel(workbook, sheet_name='validation', header=0)
                validation.set_index('t (min)', inplace=True)
                # Excel stores these nominal whole-minute values with small
                # floating-point offsets (for example 419.999999986).
                validation.index = np.rint(validation.index).astype(float)
                return {
                    'O2': validation[[f'S{i}O' for i in range(1, 6)]],
                    'NO3': validation[[f'S{i}NO3' for i in range(1, 6)]],
                    'NO2': validation[[f'S{i}NO2' for i in range(1, 6)]],
                    'NH4': validation[[f'S{i}NH' for i in range(1, 6)]],
                }

            dfO2 = pd.read_excel(workbook, sheet_name='O2', header=0, index_col=0).iloc[0]
            dfNO3 = pd.read_excel(workbook, sheet_name='NO3', header=0, index_col=0).iloc[0]
            dfNO2 = pd.read_excel(workbook, sheet_name='NO2', header=0, index_col=0).iloc[0]
            dfNH4 = pd.read_excel(workbook, sheet_name='NH4', header=0, index_col=0).iloc[0]
            # dfN2O = pd.read_excel(workbook, sheet_name='N2O', header=0, index_col=0).iloc[0]
            return {
                'O2': dfO2, 
                'NO3': dfNO3, 
                'NO2': dfNO2, 
                'NH4': dfNH4, 
                # 'N2O': dfN2O
                }
    except PermissionError as e:
        raise PermissionError(
            f"Cannot read calibration workbook '{data_file}'. "
            "Close it in Excel and ensure it is available offline in OneDrive, then retry."
        ) from e
    except Exception as e:
        print(f"Error loading measured data: {e}")
        raise


class ASMOptimization:
    """Objective function for PyGMO optimization."""
    
    def __init__(self, measured_data, dynamic_switch=None, calibration_parameters=None, parameter_overrides=None):
        self.parameter_overrides = dict(parameter_overrides or {})
        self.measured_data = measured_data
        if dynamic_switch is None:
            dynamic_switch = model_parameters.get('dynamicSwitch', 0)
        self.dynamic_switch = bool(dynamic_switch)
        
        self.initial_parameters = calibration_params_initial.copy()
        self.initial_parameters.update(calibration_parameters or {})

        # Optimization bounds; the parameter order is shared with the UI.
        # These search bounds are separate from the UI literature references.
        # Calibration bounds
        bounds = {
            'bAOB': (0.01, 0.15), 'uAOB': (0.45, 2.208),
            'KAOB1O': (0.043, 1.45), 'KAOB2O': (0.058, 2.0),
            'KAOBNH': (0.1, 35), 'KAOBNO2': (0.1, 150),
            'bNOB': (0.01, 0.22), 'uNOB': (0.1, 1.5),
            'KNOBO': (0.1, 2.2), 'KNOBNH': (0.005, 0.03),
            'KNOBNO2': (0.05, 5.5), 'bH': (0.1, 1),
            'uH': (2, 7), 'KHNH': (0.009, 60), 'KHNO3': (0.01, 15),
            'KHO': (0.05, 4), 'KHNO2': (0.05, 0.81),
            'KHS1': (1, 45), 'KHS2': (1, 60), 'KHS3': (1.5, 20),
            'KHS4': (1.5, 20), 'KHS5': (2, 40),
            'etag2': (0.02, 0.85), 'etag3': (0.02, 0.6),
            'etag4': (0.02, 0.8), 'etag5': (0.02, 0.9),
            'kla1O2': (20, 500), 'kla2O2': (20, 500), 'kla3O2': (20, 500),
        }
        if bounds.keys() != calibration_params_initial.keys():
            raise ValueError('Auto-calibration bounds must match the shared parameter list')
        self.calibration_bounds = {name: bounds[name] for name in calibration_params_initial}
        if self.parameter_overrides.get('DOSetpoint'):
            # Oxygen transfer coefficients do not affect fixed-DO simulations.
            self.calibration_bounds = {name: bounds for name, bounds in self.calibration_bounds.items()
                                       if not name.startswith('kla')}
        self.calibration_unknowns = list(self.calibration_bounds)

        # Precompute state indices once (avoid expensive DataFrame building in every fitness call)
        # self.idx_o2 = np.array([AllVariables.index(v) for v in ['S3O', 'S4O', 'S5O']])
        measured_tanks = range(1, 6) if self.dynamic_switch else range(1, 3)
        no3_columns = [f'S{i}NO3' for i in measured_tanks]
        nh4_columns = [f'S{i}NH' for i in measured_tanks]
        self.idx_no3 = np.array([AllVariables.index(v) for v in no3_columns])
        # self.idx_no2 = np.array([AllVariables.index(v) for v in ['S1NO2', 'S2NO2']])
        self.idx_nh4 = np.array([AllVariables.index(v) for v in nh4_columns])
        # self.idx_n2o = np.array([i for i, v in enumerate(AllVariables) if v in ['S2N2O', 'S4N2O', 'S6N2O', 'S8N2O']])

        # Cache measured vectors once
        # self.meas_O2 = self.measured_data['O2'][['S3O', 'S4O', 'S5O']].values
        self.meas_NO3 = self.measured_data['NO3'][no3_columns].values
        # self.meas_NO2 = self.measured_data['NO2'][['S1NO2', 'S2NO2']].values
        self.meas_NH4 = self.measured_data['NH4'][nh4_columns].values
        # self.meas_N2O = self.measured_data['N2O'].values
        self.measurement_times = (
            self.measured_data['NO3'].index.to_numpy(dtype=float)
            if self.dynamic_switch else None
        )

    def simulate_parameters(self, calibration_parameters):
        """Use identical inputs and initialization for fitness and comparisons."""
        params = {**model_parameters, **self.initial_parameters,
                  **self.parameter_overrides, **calibration_parameters,
                  'dynamicSwitch': int(self.dynamic_switch)}
        params.setdefault('qmlr_ratio', 2.5)
        if self.dynamic_switch:
            state = initial_values.copy()
            if params.get('DOSetpoint'):
                for tank in range(1, 6):
                    state[f'S{tank}O0'] = params[f'S{tank}DOsetpoint']
            record, _ = run_dynamic_simulation(
                parameter_overrides=params,
                initial_state=list(state.values()),
                output_times=self.measurement_times, paraName=None)
        else:
            final_time = 60 * 24 * 60
            record, _, _ = run_steady_simulation(
                parameter_overrides=params, tfinal=final_time,
                output_times=[final_time], save_state=False, paraName=None)
        return record

    def fitness(self, x):
        """Calculate objective function (normalized MSE)."""
        try:
            calibration_params = dict(zip(self.calibration_unknowns, x))
            simulation_record = self.simulate_parameters(calibration_params)

            if self.dynamic_switch:
                if len(simulation_record) != len(self.measurement_times) or not np.allclose(
                    simulation_record.index.to_numpy(dtype=float),
                    self.measurement_times,
                ):
                    raise ValueError(
                        "Dynamic simulation did not return all requested measurement times"
                    )
                simu_NO3 = simulation_record.iloc[:, self.idx_no3].to_numpy()
                simu_NH4 = simulation_record.iloc[:, self.idx_nh4].to_numpy()
            else:
                y_last = simulation_record.iloc[-1, :].to_numpy()
                simu_NO3 = y_last[self.idx_no3]
                simu_NH4 = y_last[self.idx_nh4]

            if not np.all(np.isfinite(simu_NO3)) or not np.all(np.isfinite(simu_NH4)):
                raise ValueError("simulation returned non-finite state values")

            mask_no3 = np.isfinite(self.meas_NO3)
            mask_nh4 = np.isfinite(self.meas_NH4)
            if not mask_no3.any() or not mask_nh4.any():
                raise ValueError('NH4 and NO3 measurements are required')
            mse_NO3 = np.mean((simu_NO3[mask_no3] - self.meas_NO3[mask_no3])**2) / (
                np.mean(self.meas_NO3[mask_no3])**2 + 1e-6)
            mse_NH4 = np.mean((simu_NH4[mask_nh4] - self.meas_NH4[mask_nh4])**2) / (
                np.mean(self.meas_NH4[mask_nh4])**2 + 1e-6)
            total_mse = mse_NO3 + mse_NH4
            if not np.isfinite(total_mse):
                raise ValueError("objective value is not finite")
            return [total_mse]
        
        except Exception as e:
            print(f"Error in fitness calculation: {e}")
            return [1e10]
    
    def get_bounds(self):
        """Get parameter bounds."""
        lb = [self.calibration_bounds[param][0] for param in self.calibration_unknowns]
        ub = [self.calibration_bounds[param][1] for param in self.calibration_unknowns]
        return (lb, ub)


def run_auto_calibration(calibration_parameters=None, *, save_results=True,
                         measured_data=None, dynamic_switch=None, parameter_overrides=None):
    """Run PyGMO auto-calibration."""
    
    print("\n" + "="*70)
    print("PHASE 2: AUTO-CALIBRATION (PyGMO)")
    print("="*70 + "\n")
    
    # Load measured data
    print("Loading measured data...")
    if dynamic_switch is None:
        dynamic_switch = int(bool(model_parameters.get('dynamicSwitch', 0)))
    selected_file = DYNAMIC_DATA_FILE if dynamic_switch else STEADY_DATA_FILE
    print(f"Calibration mode: {'dynamic' if dynamic_switch else 'steady'}")
    print(f"Measurement workbook: {selected_file.name}")
    if measured_data is None:
        measured_data = load_measured_data(dynamic_switch)
    
    # Create optimization problem
    print("Setting up PyGMO optimization...")
    opt = ASMOptimization(measured_data, dynamic_switch=dynamic_switch,
                          calibration_parameters=calibration_parameters,
                          parameter_overrides=parameter_overrides)
    prob = problem(opt)

    # Match PyGMO concurrency to the execution environment.
    if "SLURM_CPUS_PER_TASK" in os.environ:
        execution_mode = "Slurm/HPC"
        available_cpus = int(os.environ["SLURM_CPUS_PER_TASK"])
    else:
        execution_mode = "local computer"
        available_cpus = os.cpu_count() or 1

    n_islands = min(available_cpus, 12)
    pop_size = 8  # Keep near minimum for saDE to reduce RAM footprint
    n_evolutions = 3
    
    # Create algorithm (use gradient-free method since we don't provide gradients)
    # sade is a very robust gradient-free method (Self-Adaptive Differential Evolution)
    algo = pg.algorithm(pg.sade(gen=8))
    
    # Create population for each island with random starting points
    # Build an initial guess vector from `initial_values` ordered by calibration_unknowns.
    init_x = []
    for param in opt.calibration_unknowns:
        if param in opt.initial_parameters:
            lb, ub = opt.calibration_bounds[param]
            init_x.append(float(np.clip(opt.initial_parameters[param], lb, ub)))
        else:
            lb, ub = opt.calibration_bounds[param]
            init_x.append(0.5 * (lb + ub))

    # Create population for each island with random starting points and include the initial guess
    print("Initializing populations...")
    print(f"Population size: {pop_size} (includes initial guess)")
    print(f"Problem dimension: {prob.get_nx()}")
    print(f"Execution mode: {execution_mode}")
    print(f"Available CPU cores: {available_cpus}")
    print(f"PyGMO islands: {n_islands}")
    
    # Create archipelago
    try:
        # Connect neighboring islands so their best individual can migrate.
        # One best candidate is sent per migration, and it replaces an existing
        # individual only when it is better.
        archi = pg.archipelago(t=pg.topology(pg.ring()))
        migration_selection = pg.s_policy(pg.select_best(rate=1))
        migration_replacement = pg.r_policy(pg.fair_replace(rate=1))
        for i in range(n_islands):
            # create island population and include the initial guess to seed the search
            island_pop = pg.population(prob, size=max(1, pop_size - 1))
            island_pop.push_back(init_x)
            archi.push_back(
                # FastAPI invokes this function in a worker thread. PyGMO's
                # global pool installs signal handlers during initialization,
                # which is only legal on the interpreter's main thread.
                udi=pg.mp_island(use_pool=False),
                algo=algo,
                pop=island_pop,
                s_pol=migration_selection,
                r_pol=migration_replacement,
            )
        print(f"Archipelago created with {len(archi)} islands in a ring topology")
        print("Migration policy: send 1 best candidate; replace only if better")
    except Exception as e:
        print(f"Error creating archipelago: {e}")
        raise
    
    # Evolution
    print(f"\nRunning optimization ({n_islands} islands, {n_evolutions} evolution cycles)...\n")
    for i in range(n_evolutions):
        print(f"Evolution {i+1}/{n_evolutions} starting...")
        try:
            archi.evolve()
            archi.wait_check()
        except Exception as e:
            print(f"Error during evolution {i+1}: {e}")
            raise
        
        # Get best from each island
        best_per_island = []
        best_x_per_island = []
        for isl_idx, isl in enumerate(archi):
            pop = isl.get_population()
            if len(pop) > 0:
                champ_f = pop.champion_f[0]
                best_per_island.append(champ_f)
                best_x_per_island.append(pop.champion_x)
                print(f"  Island {isl_idx}: best = {champ_f:.6f}")
        
        if best_per_island:
            best_value = min(best_per_island)
            print(f"Evolution {i+1}/{n_evolutions} - Best objective: {best_value:.6f}\n")
        else:
            print(f"Evolution {i+1}/{n_evolutions} - No solutions found\n")
    
    # Get best solution from all islands
    print("\nOptimization completed!")
    all_champions_f = []
    all_champions_x = []
    for isl in archi:
        pop = isl.get_population()
        if len(pop) > 0:
            all_champions_f.append(pop.champion_f[0])
            all_champions_x.append(pop.champion_x)
    
    if not all_champions_f:
        print("Warning: No solutions found")
        raise RuntimeError("Optimization failed to produce any solutions")
    
    best_idx = np.argmin(all_champions_f)
    best_params = all_champions_x[best_idx]
    best_fitness = all_champions_f[best_idx]
    if not np.isfinite(best_fitness) or best_fitness >= 1e10:
        raise RuntimeError("All calibration candidates failed to simulate")
    
    print(f"Best objective value: {best_fitness:.6f}\n")
    
    # Map back to parameter names
    calibration_params = opt.initial_parameters.copy()
    for i, param_name in enumerate(opt.calibration_unknowns):
        calibration_params[param_name] = best_params[i]
    
    print("Calibrated Parameters:")
    print("-" * 70)
    for param_name, param_value in sorted(calibration_params.items()):
        print(f"  {param_name:15s} = {param_value:10.6f}")
    print("-" * 70)
    
    # API runs return results without changing shared defaults or disk state.
    if save_results:
        with open(BACKEND_DIR / 'calibrated_parameters.pkl', 'wb') as f:
            pickle.dump(calibration_params, f)
    calibrated_model = model_parameters.copy()
    calibrated_model.update(calibration_params)

    print("\n" + "="*70)
    print("Auto-calibration completed successfully!")
    print("="*70 + "\n")
    
    return calibration_params, calibrated_model


if __name__ == '__main__':
    run_auto_calibration()
