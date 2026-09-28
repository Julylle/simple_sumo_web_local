import unittest

import numpy as np
from pydantic import ValidationError

from config.parameters import (
    AllVariables, calibration_params_initial, frontend_parameter_overrides,
    initial_values, model_parameters,
)
from models.asm_model import GrowthCoupledProduction
from schemas.simulation import SimulationInput


def configured_model(inputs, dynamic=0):
    params = {**model_parameters, **calibration_params_initial,
              **frontend_parameter_overrides(inputs), 'dynamicSwitch': dynamic}
    return GrowthCoupledProduction(params)


class ProcessConfigurationTests(unittest.TestCase):
    def test_each_volume_changes_its_tank_balance(self):
        baseline = SimulationInput()
        state = np.array(list(initial_values.values()), dtype=float)
        expected = configured_model(baseline).rhs(0, state)
        for tank in range(1, 6):
            with self.subTest(tank=tank):
                key = f'tank{tank}_volume_m3'
                changed = baseline.model_copy(update={key: getattr(baseline, key) * 2})
                actual = configured_model(changed).rhs(0, state)
                index = AllVariables.index(f'S{tank}NH')
                self.assertNotAlmostEqual(expected[index], actual[index])

    def test_per_lane_flows_match_in_steady_and_dynamic(self):
        inputs = SimulationInput(flow_m3_d=11000, mlr_ratio=3, ras_ratio=0.8)
        steady = configured_model(inputs).get_dynamic_inputs(0)
        dynamic = configured_model(inputs, dynamic=1).get_dynamic_inputs(0)
        np.testing.assert_allclose(steady[13:17], dynamic[13:17])
        self.assertAlmostEqual(steady[13], 1000 * 1000 / 1440)
        self.assertAlmostEqual(steady[14] / steady[13], 3)
        self.assertAlmostEqual(steady[15] / steady[13], 0.8)

    def test_individual_do_and_volume_conversion(self):
        params = frontend_parameter_overrides(SimulationInput(
            tank3_volume_m3=500, tank3_do_mg_l=1.2, do_mg_l=2.5,
        ))
        self.assertEqual(params['V3'], 500000)
        self.assertEqual(params['S3DOsetpoint'], 1.2)
        self.assertEqual(params['S4DOsetpoint'], 2.5)

    def test_invalid_geometry_is_rejected(self):
        for values in ({'tank1_volume_m3': 0}, {'tank2_volume_m3': -1},
                       {'tank3_do_mg_l': 9}, {'ras_ratio': 0}, {'mlr_ratio': -1}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                SimulationInput(**values)


if __name__ == '__main__':
    unittest.main()
