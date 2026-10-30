import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from services.historical_inputs import load_history, history_request, HistoryWindow
from services.input_provenance import ModelInputs, input_provenance
from services.resume_history import resume_history

Q = 'Sumo__Plant__Influent__param__Q'
MAPPING = {Q:'ns=2;s=flow'}

class InputProvenanceTests(unittest.TestCase):
    def test_real_collection_times_preserved_when_held(self):
        store = MagicMock()
        cursor = store.connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(0,Q,41.7,datetime(2026,1,1,0,0,5),datetime(2026,1,1,0,0,45),3)]
        plan = history_request('2026-01-01T00:00:00Z','2026-01-01T00:02:00Z',1)
        with patch('services.historical_inputs.Store',return_value=store):
            windows = load_history(MAPPING,60,plan)
        self.assertEqual(windows[0].provenance[Q]['source'],'database_interval')
        self.assertEqual(windows[0].provenance[Q]['sample_count'],3)
        self.assertEqual(windows[1].provenance[Q]['source'],'held_previous')
        self.assertEqual(windows[1].provenance[Q]['collected_to'],'2026-01-01T00:00:45+00:00')
        self.assertEqual(windows[1].provenance[Q]['original_source'],'database_interval')
        self.assertAlmostEqual(windows[0].values[Q],1000)

    def test_clamped_history_retains_collection_provenance(self):
        store = MagicMock()
        cursor = store.connection.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(0,Q,0,datetime(2026,10,30,1,47),datetime(2026,10,30,1,47,30),2)]
        plan = history_request('2026-10-30T01:47:00Z','2026-10-30T01:48:00Z',1)
        with patch('services.historical_inputs.Store',return_value=store):
            window = load_history(MAPPING,60,plan)[0]
        self.assertEqual(window.values[Q],0)
        self.assertEqual(window.held_inputs,())
        self.assertEqual(window.provenance[Q]['source'],'database_interval')
        self.assertEqual(window.provenance[Q]['sample_count'],2)
        self.assertEqual(window.provenance[Q]['collected_to'],'2026-10-30T01:47:30+00:00')
        sql = cursor.execute.call_args.args[0]
        self.assertIn('THEN GREATEST(r.numeric_value, 0) END)',sql)
        self.assertIn('MIN(r.acquired_at), MAX(r.acquired_at), COUNT(*)',sql)

    def test_old_checkpoint_time_is_unknown(self):
        store = MagicMock()
        store.connection.cursor.return_value.__enter__.return_value.fetchall.return_value = []
        plan = history_request('2026-01-01T00:00:00Z','2026-01-01T00:01:00Z',1)
        plan['last_inputs'] = {Q:1000}
        with patch('services.historical_inputs.Store',return_value=store):
            window = load_history(MAPPING,60,plan)[0]
        self.assertEqual(window.provenance[Q]['original_source'],'checkpoint_unknown')
        self.assertIsNone(window.provenance[Q].get('collected_to'))

    def test_direct_metadata_and_cumulative_interval(self):
        values = ModelInputs({Q:1000})
        values.provenance = {Q:{'source':'opcua','collected_to':'2026-10-29T00:00:04+00:00'}}
        result = input_provenance(MAPPING,values,167160000,60000)
        self.assertEqual(result['end_ms'],167220000)
        self.assertEqual(result['inputs'][0]['source'],'opcua')
        self.assertEqual(result['inputs'][0]['model_value'],1000)
        self.assertEqual(result['inputs'][0]['collected_to'],'2026-10-29T00:00:04+00:00')

    def test_history_time_distinct_from_collection_time(self):
        window = HistoryWindow(60000,'2026-10-29T00:01:00+00:00',{Q:1000},(),{
            Q:{'source':'database_interval','collected_to':'2026-10-29T00:00:45+00:00'}})
        result = input_provenance(MAPPING,window.values,167160000,60000,window)
        self.assertEqual(result['interval_start'],'2026-10-29T00:00:00+00:00')
        self.assertEqual(result['inputs'][0]['collected_to'],'2026-10-29T00:00:45+00:00')

    def test_resume_keeps_acquisition_metadata(self):
        details = {Q:{'source':'database_interval','collected_to':'2026-10-29T00:00:45+00:00'}}
        plan = resume_history({'sensor_boundary_at':'2026-10-29T00:01:00+00:00',
            'simulated_ms':167220000,'mapping':MAPPING,
            'history':{'last_inputs':{Q:1000},'last_input_provenance':details}})
        self.assertEqual(plan['last_input_provenance'],details)

if __name__ == '__main__':
    unittest.main()
