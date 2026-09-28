import unittest
import numpy as np
from config.parameters import calibration_params_initial, frontend_parameter_overrides, model_parameters
from models.asm_model import GrowthCoupledProduction
from schemas.simulation import SimulationInput


class MeasuredInputTests(unittest.TestCase):
    def test_excel_inputs_override_browser_constants(self):
        params = {**model_parameters, **calibration_params_initial,
                  **frontend_parameter_overrides(SimulationInput(flow_m3_d=5098)),
                  'dynamicSwitch': 1, 'dynamic_input_source': 'measured'}
        model = GrowthCoupledProduction(params)
        for hour in (0, 7, 12, 100):
            row = model.dyInput.iloc[min(hour, len(model.dyInput) - 1)]
            inputs = model.get_dynamic_inputs(hour * 60)
            expected_flow = (row['Effluent rate (L/s)'] + row['WAS (L/s)']) * 60 / 11
            np.testing.assert_allclose(
                [inputs[0], inputs[8], inputs[13], inputs[14], inputs[15], inputs[16]],
                [row.SNH, row.bCOD, expected_flow, expected_flow * params['qmlr_ratio'],
                 row['RAS (L/s)'] * 60 / 11, row['WAS (L/s)'] * 60 / 11],
            )
        self.assertNotEqual(model.get_dynamic_inputs(0)[0], model.get_dynamic_inputs(720)[0])
