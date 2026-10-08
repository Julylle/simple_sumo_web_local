"""Check the optimizer contract without requiring native solver installations."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from config.parameters import AllVariables, calibration_params_initial, model_parameters


class AutoCalibrationTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            'auto_calibration_under_test', Path(__file__).resolve().parents[1] / 'auto_calibration.py')
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {
            'pygmo': MagicMock(), 'steady_simulation': MagicMock(),
            'dynamic_simulation': MagicMock(),
        }):
            spec.loader.exec_module(self.module)
        self.measured = {
            'NO3': pd.Series({f'S{i}NO3': 1.0 for i in range(1, 6)}),
            'NH4': pd.Series({f'S{i}NH': 1.0 for i in range(1, 6)}),
        }

    def test_optimizer_covers_table_parameters_in_same_order(self):
        opt = self.module.ASMOptimization(self.measured)
        self.assertEqual(opt.calibration_unknowns, list(calibration_params_initial))
        for name, (low, high) in opt.calibration_bounds.items():
            self.assertLess(low, high)
            self.assertLessEqual(low, calibration_params_initial[name])
            self.assertGreaterEqual(high, calibration_params_initial[name])

    def test_steady_fitness_passes_all_values_without_shared_pickle(self):
        defaults = calibration_params_initial.copy()
        opt = self.module.ASMOptimization(self.measured, calibration_parameters={'uH': 6.5})
        self.assertEqual(opt.initial_parameters['uH'], 6.5)
        values = list(opt.initial_parameters.values())
        record = pd.DataFrame(np.ones((1, len(AllVariables))), columns=AllVariables)
        self.module.run_steady_simulation.return_value = (record, {}, {})
        self.assertEqual(opt.fitness(values), [0.0])
        kwargs = self.module.run_steady_simulation.call_args.kwargs
        for name, value in zip(opt.calibration_unknowns, values):
            self.assertEqual(kwargs['parameter_overrides'][name], value)
        self.assertIsNone(kwargs['paraName'])
        self.assertFalse(kwargs['save_state'])
        self.assertNotIn('plot', kwargs)
        self.assertEqual(calibration_params_initial, defaults)

    def test_dynamic_fitness_matches_measurement_times(self):
        measured = {key: pd.DataFrame([series, series], index=[0.0, 60.0])
                    for key, series in self.measured.items()}
        opt = self.module.ASMOptimization(measured, dynamic_switch=True)
        record = pd.DataFrame(np.ones((2, len(AllVariables))), columns=AllVariables, index=[0.0, 60.0])
        self.module.run_dynamic_simulation.return_value = (record, {})
        self.assertEqual(opt.fitness(list(opt.initial_parameters.values())), [0.0])
        self.assertIsNone(self.module.run_dynamic_simulation.call_args.kwargs['paraName'])
        self.module.run_dynamic_simulation.return_value = (record.iloc[:1], {})
        self.assertEqual(opt.fitness(list(opt.initial_parameters.values())), [1e10])

    def test_api_run_returns_all_values_without_writing_or_mutating_defaults(self):
        original = model_parameters.copy()
        self.module.load_measured_data = MagicMock(return_value=self.measured)
        champion = MagicMock()
        champion.__len__.return_value = 8
        champion.champion_f = [0.1]
        champion.champion_x = list(calibration_params_initial.values())
        island = MagicMock()
        island.get_population.return_value = champion
        archipelago = self.module.pg.archipelago.return_value
        archipelago.__iter__.side_effect = lambda: iter([island])
        with patch('builtins.open') as write, patch('builtins.print'):
            values, _ = self.module.run_auto_calibration({'uH': 100}, save_results=False)
        write.assert_not_called()

        self.module.pg.mp_island.assert_called_with(use_pool=False)
        self.assertIs(archipelago.push_back.call_args.kwargs['udi'], self.module.pg.mp_island.return_value)
        self.assertEqual(list(values), list(calibration_params_initial))
        self.assertEqual(model_parameters, original)
        seed = self.module.pg.population.return_value.push_back.call_args.args[0]
        self.assertEqual(seed[list(calibration_params_initial).index('uH')], 7)
        champion.champion_f = [1e10]
        with patch('builtins.open') as write, patch('builtins.print'), self.assertRaises(RuntimeError):
            self.module.run_auto_calibration(save_results=False)
        write.assert_not_called()

    def test_missing_measurements_are_excluded_from_objective(self):
        measured = {key: pd.DataFrame([series, series], index=[0.0, 60.0])
                    for key, series in self.measured.items()}
        measured['NO3'].loc[60, 'S1NO3'] = np.nan
        opt = self.module.ASMOptimization(measured, dynamic_switch=True,
                                          parameter_overrides={'dynamic_inputs': {'SNH': [10, 20]}})
        record = pd.DataFrame(np.ones((2, len(AllVariables))), columns=AllVariables, index=[0, 60])
        record.loc[60, 'S1NO3'] = 999
        self.module.run_dynamic_simulation.return_value = (record, {})
        self.assertEqual(opt.fitness(list(opt.initial_parameters.values())), [0.0])
        self.assertEqual(self.module.run_dynamic_simulation.call_args.kwargs['parameter_overrides']['dynamic_inputs'], {'SNH': [10, 20]})

    def test_fixed_do_initializes_each_tank_and_does_not_optimize_kla(self):
        measured = {key: pd.DataFrame([series, series], index=[0, 60]) for key, series in self.measured.items()}
        setpoints = [0.1, 0.2, 1.2, 2.3, 3.4]
        overrides = {'DOSetpoint': 1, **{f'S{i}DOsetpoint': value for i, value in enumerate(setpoints, 1)}}
        opt = self.module.ASMOptimization(measured, dynamic_switch=True, parameter_overrides=overrides)
        self.assertEqual(len(opt.calibration_unknowns), len(calibration_params_initial) - 3)
        self.assertFalse(any(name.startswith('kla') for name in opt.calibration_unknowns))
        self.module.run_dynamic_simulation.return_value = (pd.DataFrame(), {})
        opt.simulate_parameters({})
        state = self.module.run_dynamic_simulation.call_args.kwargs['initial_state']
        for tank, value in enumerate(setpoints, 1):
            self.assertEqual(state[AllVariables.index(f'S{tank}O')], value)


if __name__ == '__main__':
    unittest.main()
