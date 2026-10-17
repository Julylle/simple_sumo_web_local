import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from models.sumo_worker import OUTPUTS, read_result
from models import sumo_engine


class SumoIntegrationTests(unittest.TestCase):
    def make_csv(self, directory, end=3600, value='2.5'):
        path = Path(directory) / 'result.csv'
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.DictWriter(stream, fieldnames=['sim_time_seconds', *OUTPUTS.values()])
            writer.writeheader()
            for timestamp in [0, end]:
                writer.writerow({'sim_time_seconds': timestamp, **{name: value for name in OUTPUTS.values()}})
        return path

    def test_result_units_and_variable_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            result = read_result(self.make_csv(directory), 1)
        self.assertEqual(result['time_h'], [0, 1])
        self.assertEqual(result['variables']['effluent_nh4'], [2.5, 2.5])
        self.assertEqual(set(result['variables']), set(OUTPUTS))

    def test_reject_partial_and_nonfinite_results(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                read_result(self.make_csv(directory, end=300), 1)
            with self.assertRaises(ValueError):
                read_result(self.make_csv(directory, value='nan'), 1)

    def test_worker_isolated_and_result_read(self):
        def fake_run(args, **kwargs):
            self.assertEqual(args[-1], '1')
            self.assertEqual(kwargs['timeout'], 3600)
            Path(kwargs['cwd'], 'result.json').write_text(json.dumps({'time_h': [0, 1]}))
            return type('Completed', (), {'returncode': 0})()
        with patch.object(sumo_engine.subprocess, 'run', side_effect=fake_run):
            self.assertEqual(sumo_engine.execute(1), {'time_h': [0, 1]})

    def test_duplicate_run_rejected(self):
        with patch.object(sumo_engine, '_jobs', {}), patch.object(sumo_engine._pool, 'submit'):
            job = sumo_engine.start_run(1)
            self.assertEqual(sumo_engine.get_run(job['id'])['status'], 'running')
            with self.assertRaises(RuntimeError):
                sumo_engine.start_run(1)

    def test_progress_is_monotonic_and_completion_waits_for_results(self):
        observed = []
        def fake_execute(duration_h, report):
            for value in [0.5, 0.25, 1, 2]:
                report(value)
                observed.append(sumo_engine.get_run('test'))
            return {'time_h': [0, 1]}
        with patch.object(sumo_engine, '_jobs', {'test': {'status': 'running'}}), patch.object(sumo_engine, 'execute', side_effect=fake_execute):
            sumo_engine._run('test', 1)
            self.assertEqual([job['progress_pct'] for job in observed], [50, 50, 99, 99])
            self.assertEqual(observed[-1]['phase'], 'finalizing')
            self.assertEqual(sumo_engine.get_run('test')['progress_pct'], 100)
            self.assertEqual(sumo_engine.get_run('test')['status'], 'completed')

    def test_progress_reader_rejects_invalid_values(self):
        from unittest.mock import Mock
        for value in [float('nan'), -1, 'bad', 0.5]:
            with tempfile.TemporaryDirectory() as directory:
                Path(directory, 'progress.json').write_text(json.dumps({'simulated_h': value}))
                stop = Mock()
                stop.wait.side_effect = [False, True]
                report = Mock()
                sumo_engine._watch_progress(directory, stop, report)
                if value == 0.5:
                    report.assert_called_once_with(0.5)
                else:
                    report.assert_not_called()

    def test_uploaded_input_validation_and_snapshot(self):
        from services.sumo_data import COLUMNS, save_input, get_input
        header = ','.join(COLUMNS) + '\n'
        uploaded = save_input(('\ufeff' + header + '0,30,300\n300000,40,400\n').encode('utf-8'), 'inputs.csv')
        self.assertEqual(uploaded['count'], 2)
        self.assertIn('300000,40.0,400.0', get_input(uploaded['id']))
        for rows in ['0,nan,300\n', '1,30,300\n', '0,30,300\n0,40,400\n', '0,-1,300\n', '']:
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                save_input((header + rows).encode(), 'inputs.csv')
        with self.assertRaises(ValueError):
            get_input('missing')

    def test_upload_size_and_header_validation(self):
        from services.sumo_data import MAX_BYTES, save_input
        for content in [b'x' * (MAX_BYTES + 1), b'time,tkn,cod\n0,30,300\n', b'\xff']:
            with self.assertRaises(ValueError):
                save_input(content, 'inputs.csv')

    def test_uploaded_csv_reaches_worker_and_full_csv_is_preserved(self):
        def fake_run(args, **kwargs):
            directory = Path(kwargs['cwd'])
            self.assertEqual((directory / 'input.csv').read_text(), 'uploaded input')
            (directory / 'result.json').write_text('{"time_h": [0, 1]}')
            (directory / 'dynamic_results_test.csv').write_text('all samples\n', encoding='utf-8')
            return type('Completed', (), {'returncode': 0})()
        with patch.object(sumo_engine.subprocess, 'run', side_effect=fake_run):
            result = sumo_engine.execute(1, input_csv='uploaded input')
            self.assertEqual(result['_csv'], 'all samples\n')

    def test_export_only_available_after_success_and_not_in_status(self):
        with patch.object(sumo_engine, '_jobs', {'test': {'status': 'running'}}), patch.object(sumo_engine, '_exports', {}), patch.object(sumo_engine, 'execute', return_value={'time_h': [0, 1], '_csv': 'full csv'}):
            self.assertIsNone(sumo_engine.get_export('test'))
            sumo_engine._run('test', 1)
            self.assertEqual(sumo_engine.get_export('test'), 'full csv')
            self.assertNotIn('_csv', sumo_engine.get_run('test')['result'])

    def test_template_subset_and_uploaded_columns_match(self):
        from services.sumo_data import PREFIX, template_csv, parse_input, save_input
        selected = [PREFIX + 'Q', PREFIX + 'pH', PREFIX + 'T']
        template = list(csv.reader(template_csv(selected).splitlines()))
        self.assertEqual(template[0], ['sim_time_ms', *selected])
        self.assertEqual(template[1], ['0', '', '', ''])
        content = (','.join(template[0]) + '\n0,50000,7.2,20\n300000,51000,7.3,21\n').encode()
        info = save_input(content, 'inputs.csv', selected)
        self.assertEqual(info['columns'], selected)
        self.assertEqual(parse_input(content)[1][-1], [300000, 51000, 7.3, 21])
        with self.assertRaises(ValueError):
            parse_input(content, selected[::-1])
        with self.assertRaises(ValueError):
            parse_input(template_csv(selected).encode())

    def test_all_supported_parameters_and_invalid_columns(self):
        from services.sumo_data import ALLOWED_COLUMNS, PREFIX, parse_input, template_csv
        self.assertEqual(len(ALLOWED_COLUMNS), 12)
        valid_values = [50000, 7, 20, 30, 300, 40, 30, 200, 30, 300, 40, 5]
        content = (','.join(['sim_time_ms', *ALLOWED_COLUMNS]) + '\n0,' + ','.join(map(str, valid_values)) + '\n').encode()
        self.assertEqual(parse_input(content)[0], list(ALLOWED_COLUMNS))
        for selected in [[], [PREFIX + 'Q'] * 2, ['Sumo__StopTime']]:
            with self.assertRaises(ValueError):
                template_csv(selected)
        for name, value in [('pH', 15), ('T', 101), ('Q', 0)]:
            with self.assertRaises(ValueError):
                parse_input(f'sim_time_ms,{PREFIX}{name}\n0,{value}\n'.encode())

    def test_failures_visible_to_client(self):
        with patch.object(sumo_engine, '_jobs', {'test': {'status': 'running'}}), patch.object(sumo_engine, 'execute', side_effect=RuntimeError('License unavailable')):
            with self.assertLogs(level='ERROR'):
                sumo_engine._run('test', 1)
            self.assertEqual(sumo_engine.get_run('test')['status'], 'failed')
            self.assertEqual(sumo_engine.get_run('test')['error'], 'License unavailable')


if __name__ == '__main__':
    unittest.main()
