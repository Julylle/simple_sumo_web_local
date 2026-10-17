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

    def test_failures_visible_to_client(self):
        with patch.object(sumo_engine, '_jobs', {'test': {'status': 'running'}}), patch.object(sumo_engine, 'execute', side_effect=RuntimeError('License unavailable')):
            with self.assertLogs(level='ERROR'):
                sumo_engine._run('test', 1)
            self.assertEqual(sumo_engine.get_run('test')['status'], 'failed')
            self.assertEqual(sumo_engine.get_run('test')['error'], 'License unavailable')


if __name__ == '__main__':
    unittest.main()
