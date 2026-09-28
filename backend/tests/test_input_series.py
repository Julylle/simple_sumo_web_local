import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from config.parameters import calibration_params_initial, model_parameters
from models.asm_model import GrowthCoupledProduction
from services import input_series as inputs


def workbook(times, values):
    output = io.BytesIO()
    pd.DataFrame({'time_h': times, 'value': values}).to_excel(output, index=False)
    return output.getvalue()


class InputSeriesTests(unittest.TestCase):
    def test_upload_persists_and_resolves(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(inputs, 'STORE_DIR', Path(directory)):
            info = inputs.save_upload('inflow', workbook([0, .5, 2], [1440, 2880, 4320]), 'inflow.xlsx')
            profiles, _ = inputs.resolve_profiles({'inflow': info['id']})
            self.assertEqual(profiles['inflow']['values'], [1440, 2880, 4320])
            self.assertTrue((Path(directory) / f"{info['id']}.xlsx").exists())
            with self.assertRaises(ValueError):
                inputs.read_upload('ras', info['id'])
            with self.assertRaises(ValueError):
                inputs.read_upload('inflow', '../outside')

    def test_invalid_excel_time_and_values(self):
        for times, values in (([0, 0], [1, 2]), ([1, 2], [1, 2]),
                              ([0, 1], [-1, 2]), ([0, 1], [1, float('nan')])):
            with self.subTest(times=times, values=values), self.assertRaises(ValueError):
                inputs.parse_excel(workbook(times, values))

    def test_get_dynamic_inputs_reads_all_eight_profiles(self):
        profiles, references = inputs.resolve_profiles({})
        for key, values in {
            'inflow': [1440, 2880], 'bcod': [100, 200], 'nh4': [30, 60],
            'ras': [720, 1440], 'was': [14.4, 28.8],
            'airflow1': [references[0], references[0] * 2],
            'airflow2': [references[1], references[1] * 3],
            'airflow3': [references[2], 0],
        }.items():
            profiles[key] = inputs.validate_series([0, .5], values)
        params = {**model_parameters, **calibration_params_initial,
                  'qmlr_ratio': 2.5, 'time_series': profiles, 'airflow_reference': references,
                  'dynamicSwitch': 1, 'DOSetpoint': 0}
        model = GrowthCoupledProduction(params)
        before, after = model.get_dynamic_inputs(29), model.get_dynamic_inputs(30)
        np.testing.assert_allclose([before[0], before[8], *before[13:17]], [30, 100, 1000, 2500, 500, 10])
        np.testing.assert_allclose([after[0], after[8], *after[13:17]], [60, 200, 2000, 5000, 1000, 20])
        self.assertAlmostEqual(after[17] / before[17], 2 ** .86)
        self.assertAlmostEqual(after[18] / before[18], 3 ** .86)
        self.assertEqual(after[19], 0)
        np.testing.assert_allclose(model.get_dynamic_inputs(10000)[13:], after[13:])
        # Steady initialization uses the first point, even at large solver times.
        steady = GrowthCoupledProduction({**params, 'dynamicSwitch': 0})
        np.testing.assert_allclose(steady.get_dynamic_inputs(10000)[13:], before[13:])
