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


def test_local_views_match_shanghai_plot_and_keep_canonical_utc():
    from datetime import datetime, timezone
    from database.local_time import install_local_views
    store=Store().connect()
    try:
        store.initialize(display_timezone='+08:00')
        digest,content,rows=load_mapping()
        ids=store.register_mapping(digest,content,rows)
        stamp=datetime(2026,1,1,0,5,0,123456,tzinfo=timezone.utc)
        batch=str(uuid4())
        store.write_raw(batch,ids,[{'acquired_at':stamp,'quality':'good','numeric_value':1,'raw_value':1} for _ in rows])
        run=str(uuid4())
        catalog=store.register_run(run,'e'*64,'timezone-test',[{'name':'local_time_test','type':'REAL','category':'StateVariable','unit':'mg/L'}],'test',{})
        store.write_simulation(run,catalog,300000,{'local_time_test':1},stamp)
        with store.connection.cursor() as c:
            c.execute('SELECT sensor_read_at,sensor_read_at_utc,plot_time FROM `sumo simulation` WHERE run_id=%s',(run,))
            local,utc,plot=c.fetchone()
            assert local==datetime(2026,1,1,8,5,0,123456)
            assert utc==stamp.replace(tzinfo=None)
            assert plot=='2026-01-01 08:05:00.123'
            c.execute('SELECT acquired_at,acquired_at_utc,plot_time FROM `raw data` WHERE batch_id=%s LIMIT 1',(batch,))
            assert c.fetchone()==(local,utc,plot)
            c.execute('SELECT sensor_read_at FROM sumo_samples WHERE run_id=%s',(run,))
            assert c.fetchone()[0]==utc
    finally:store.close()
