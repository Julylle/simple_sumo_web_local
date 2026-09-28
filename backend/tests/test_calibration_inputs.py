import unittest
from unittest.mock import patch

import pandas as pd
from pydantic import ValidationError

from config.parameters import calibration_params_initial
from models.python_engine import PythonEngine
from schemas.simulation import SimulationInput


class CalibrationInputTests(unittest.TestCase):
    def test_values_reach_simulation_without_mutating_defaults(self):
        original = calibration_params_initial.copy()
        record = pd.DataFrame({'S5NH': [1.], 'S5S': [2.], 'S5N2O': [0.1]}, index=[0.])
        with patch('models.python_engine.run_dynamic_simulation', return_value=(record, {})) as run:
            PythonEngine().run(SimulationInput(calibration_parameters={'uAOB': 0.45}, mlr_ratio=4))
            overrides = run.call_args.kwargs['parameter_overrides']
            self.assertEqual(overrides['uAOB'], 0.45)
            self.assertEqual(overrides['qmlr_ratio'], 4)
            self.assertEqual(run.call_args.kwargs['initialization_mode'], 'steady')
        self.assertEqual(calibration_params_initial, original)

    def test_invalid_values_are_rejected(self):
        for values in ({'unknown': 1}, {'uAOB': -1}, {'uAOB': float('nan')},
                       {'uAOB': float('inf')}, {'KHO': 0}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SimulationInput(calibration_parameters=values)

    def test_defaults_remain_optional_for_api_clients(self):
        self.assertEqual(SimulationInput().calibration_parameters, {})
        self.assertEqual(SimulationInput(calibration_parameters=calibration_params_initial).calibration_parameters,
                         calibration_params_initial)
