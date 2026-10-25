"""Opt-in integration against an initialized disposable MySQL 8.4 database."""
import os
from uuid import uuid4
import pytest
from database.catalog import load_mapping
from database.store import Store, utcnow

pytestmark = pytest.mark.skipif(os.getenv('MYSQL_TEST_ENABLED') != '1', reason='Requires disposable MySQL database')


def test_mysql_datasets_metadata_arrays_and_idempotency():
    store = Store().connect()
    try:
        store.initialize()
        digest, content, rows = load_mapping()
        ids = store.register_mapping(digest, content, rows)
        batch = str(uuid4())
        samples = [{'acquired_at': utcnow(), 'quality': 'good', 'raw_value': '41.7',
                    'numeric_value': 41.7, 'scaled_value': 1000} for row in rows]
        store.write_raw(batch, ids, samples)
        store.write_raw(batch, ids, samples)
        with store.connection.cursor() as c:
            c.execute('SELECT COUNT(*) FROM `raw data` WHERE batch_id=%s', (batch,))
            assert c.fetchone()[0] == len(rows)
            c.execute('SELECT OpcTag,Scaling,IOType FROM `raw data` WHERE batch_id=%s AND variable_id=%s', (batch, ids[0]))
            assert c.fetchone() == (rows[0]['OpcTag'], rows[0]['Scaling'], rows[0]['IOType'])
        run = str(uuid4())
        variables = [{'name': 'state_array', 'type': 'REALARRAY', 'category': 'StateVariable', 'unit': 'mg/L'}]
        catalog = store.register_run(run, 'f'*64, 'test-model', variables, 'test', {})
        store.write_simulation(run, catalog, 60000, {'state_array': [1, 2]})
        store.write_simulation(run, catalog, 60000, {'state_array': [9, 9]})
        with store.connection.cursor() as c:
            c.execute('SELECT value_json FROM `sumo simulation` WHERE run_id=%s', (run,))
            import json
            assert [json.loads(row[0]) for row in c.fetchall()] == [[9, 9]]
    finally:
        store.close()
