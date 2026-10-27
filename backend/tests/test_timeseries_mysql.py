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


def test_history_overwrites_only_matching_absolute_time_atomically():
    from datetime import datetime, timezone, timedelta
    store = Store().connect()
    try:
        store.initialize()
        old, new = str(uuid4()), str(uuid4())
        digest = uuid4().hex * 2
        variables = [{'name':'state','type':'REAL','category':'StateVariable','unit':'mg/L'}]
        ids = store.register_run(old, digest, 'overwrite-test', variables, 'history_then_live', {})
        stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        store.write_simulation(old, ids, 60000, {'state': 1}, stamp)
        store.write_simulation(old, ids, 120000, {'state': 9}, stamp + timedelta(minutes=1))
        store.register_run(new, digest, 'overwrite-test', variables, 'history_then_live', {})
        # Different relative time, identical absolute time: reuse old sample.
        with pytest.raises(Exception):
            store.write_simulation(new, {'state': 18446744073709551615}, 0,
                                   {'state': 2}, stamp, overwrite_history=True)
        with store.connection.cursor() as c:
            c.execute('SELECT COUNT(*) FROM sumo_samples WHERE run_id=%s', (old,))
            assert c.fetchone()[0] == 2
        store.write_simulation(new, ids, 0, {'state': 2}, stamp, overwrite_history=True)
        store.write_simulation(new, ids, 0, {'state': 3}, stamp, overwrite_history=True)
        with store.connection.cursor() as c:
            c.execute('SELECT s.run_id,s.simulated_ms,v.numeric_value FROM sumo_samples s '
                      'JOIN sumo_values v ON v.sample_id=s.id WHERE s.run_id IN (%s,%s) '
                      'ORDER BY s.sensor_read_at', (old, new))
            assert c.fetchall() == ((new, 0, 3.0), (old, 120000, 9.0))
            c.execute('SELECT COUNT(*) FROM sumo_runs WHERE run_id IN (%s,%s)', (old, new))
            assert c.fetchone()[0] == 2
    finally:
        store.close()
