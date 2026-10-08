import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

from services import calibration_data as service


class CalibrationDataTests(unittest.TestCase):
    def setUp(self):
        self.measured = pd.DataFrame({'t (min)': [0, 60], **{name: [1.0, 2.0] for name in service.REQUIRED}})
        self.inputs = pd.DataFrame({'t (min)': [0, 60], **{name: [10.0, 20.0] for name in service.INPUT_COLUMNS}})

    def workbook(self):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            self.measured.to_excel(writer, sheet_name='validation', index=False)
            self.inputs.to_excel(writer, sheet_name='dyinput', index=False)
        return output.getvalue()

    def test_upload_preserves_missing_values_and_uses_uploaded_inputs(self):
        self.measured.loc[1, 'S1NO3'] = np.nan
        self.measured['S1N2O'] = [0.1, np.nan]
        with tempfile.TemporaryDirectory() as folder, patch.object(service, 'STORE_DIR', Path(folder)):
            info = service.save_measurements(self.workbook(), '../example.xlsx')
            data = service.read_measurements(info['id'])
        self.assertEqual(info['filename'], 'example.xlsx')
        self.assertEqual(info['variables']['S1NO3'], [1.0, None])
        self.assertEqual(info['time_h'], [0, 1])
        self.assertNotIn('inputs', info)
        json.dumps(data, allow_nan=False)
        measured, overrides = service.optimization_inputs(data)
        self.assertTrue(np.isnan(measured['NO3'].loc[60, 'S1NO3']))
        self.assertEqual(overrides['time_series']['nh4']['values'], [10, 20])
        self.assertEqual(overrides['dynamic_inputs']['SNH'], [10, 20])
        self.assertAlmostEqual(overrides['time_series']['inflow']['values'][0], 20 * 86.4 / 11)

    def test_bad_workbooks_are_rejected(self):
        cases = [
            ('measured', 'S1NH', None),
            ('measured', 't (min)', [0, 0]),
            ('measured', 'S1NO3', [None, None]),
            ('measured', 'S1O', ['invalid', 1]),
            ('measured', 'S1NH', [-1, 1]),
            ('inputs', 'RAS (L/s)', [0, 1]),
            ('inputs', 't (min)', [0, 30]),
            ('inputs', 'SNH', [None, 1]),
        ]
        for target, column, values in cases:
            self.setUp()
            frame = getattr(self, target)
            if values is None:
                frame.drop(columns=column, inplace=True)
            else:
                frame[column] = values
            with self.subTest(target=target, column=column), self.assertRaises(ValueError):
                service.parse_workbook(self.workbook())
        with self.assertRaises(ValueError):
            service.parse_workbook(b'not an Excel file')
        with self.assertRaises(ValueError):
            service.read_measurements('../file')

    def test_comparison_matches_times_and_skips_missing_measurements(self):
        data = {'time_h': [0, 1], 'variables': {'S1NH': [1, None]}}
        before = pd.DataFrame({'S1NH': [3, 99]}, index=[0, 60])
        after = pd.DataFrame({'S1NH': [1.0, 50.0]}, index=[0, 60])
        result = service.comparison_result(data, before, after)
        self.assertEqual(result['metrics']['S1NH'], {'before': 2, 'after': 0})
        self.assertEqual(result['after']['S1NH'], [1, 50])
        json.dumps(result, allow_nan=False)
        with self.assertRaises(ValueError):
            service.comparison_result(data, before.iloc[:1], after)
        after.iloc[0, 0] = np.inf
        with self.assertRaises(ValueError):
            service.comparison_result(data, before, after)

    def test_template_contains_required_headers_without_private_data(self):
        with pd.ExcelFile(io.BytesIO(service.template_workbook())) as workbook:
            self.assertIn('instructions', workbook.sheet_names)
            validation = pd.read_excel(workbook, sheet_name='validation')
            self.assertEqual(len(validation), 0)
            self.assertTrue(set(service.REQUIRED).issubset(validation.columns))

    def test_simulation_accepts_partial_validation_without_operating_inputs(self):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            pd.DataFrame({'t (min)': [0, 60], 'S5NH': [1.2, None], 'S3NO3': [2.5, 3.0]}).to_excel(
                writer, sheet_name='validation', index=False)
        data = service.simulation_measurements(output.getvalue(), '../measurements.xlsx')
        self.assertEqual(data['time_h'], [0, 1])
        self.assertEqual(data['variables']['S5NH'], [1.2, None])
        self.assertEqual(data['filename'], 'measurements.xlsx')
        self.assertEqual(set(data['variables']), {'S5NH', 'S3NO3'})
        json.dumps(data, allow_nan=False)

    def test_simulation_rejects_empty_invalid_or_unrecognized_measurements(self):
        for columns in [
            {'t (min)': [0, 60], 'S5NH': [None, None]},
            {'t (min)': [0, 60], 'other': [1, 2]},
            {'t (min)': [0, 0], 'S5NH': [1, 2]},
            {'t (min)': [0, 60], 'S5NH': [-1, 2]},
            {'t (min)': [0, 60], 'S5NH': ['bad', 2]},
        ]:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                pd.DataFrame(columns).to_excel(writer, sheet_name='validation', index=False)
            with self.subTest(columns=columns), self.assertRaises(ValueError):
                service.simulation_measurements(output.getvalue(), 'measurements.xlsx')


if __name__ == '__main__':
    unittest.main()
