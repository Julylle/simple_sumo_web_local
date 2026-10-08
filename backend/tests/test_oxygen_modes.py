import unittest
from uuid import uuid4

import numpy as np
from pydantic import ValidationError

from config.parameters import calibration_params_initial, model_parameters
from models.asm_model import GrowthCoupledProduction
from schemas.simulation import AutoCalibrationInput


class OxygenModeTests(unittest.TestCase):
    def test_api_modes_and_setpoints_are_validated(self):
        for mode in ['do_setpoint', 'constant_kla', 'calculated_kla']:
            self.assertEqual(AutoCalibrationInput(measurement_id=uuid4(), oxygen_mode=mode).oxygen_mode, mode)
        for values in [{'oxygen_mode': 'invalid'}, {'do_setpoints': [1]},
                       {'do_setpoints': [0, 0, -1, 2, 3]}, {'do_setpoints': [0, 0, float('nan'), 2, 3]}]:
            with self.subTest(values=values), self.assertRaises(ValidationError):
                AutoCalibrationInput(measurement_id=uuid4(), **values)

    def test_constant_kla_ignores_airflow_changes_but_calculated_kla_tracks_them(self):
        profiles = {key: {'time_h': [0, 1], 'values': [10, 20]}
                    for key in ['inflow', 'ras', 'was', 'nh4', 'bcod', 'airflow1', 'airflow2', 'airflow3']}
        params = {**model_parameters, **calibration_params_initial, 'dynamicSwitch': 1, 'qmlr_ratio': 2.5,
                  'dynamic_inputs': {'t (min)': [0, 60], 'SNO2': [0, 0], 'SNO3': [0, 0], 'XI': [0, 0]},
                  'time_series': profiles, 'airflow_reference': [10, 10, 10]}
        base = np.array([params[f'kla{i}O2'] / 1440 for i in (1, 2, 3)])
        for constant in (0, 1):
            model = GrowthCoupledProduction({**params, 'constantKLa': constant})
            np.testing.assert_allclose(model.get_dynamic_inputs(0)[-3:], base)
            np.testing.assert_allclose(model.get_dynamic_inputs(60)[-3:], base if constant else base * 2 ** 0.86)


if __name__ == '__main__':
    unittest.main()
