"""Independent KEPServer acquisition: python -m database.collector."""
import asyncio
import logging
import os
import time
from pathlib import Path
from uuid import uuid4

from asyncua import Client
from database.catalog import CSV_PATH, load_mapping
from database.store import Store, utcnow, encode, numeric


async def acquire(rows, client_factory=Client):
    endpoint = os.getenv('KEPSERVER_OPC_URL', 'opc.tcp://127.0.0.1:49320')
    observations = {}
    try:
        async with client_factory(endpoint, timeout=15) as client:
            uri = os.getenv('KEPSERVER_NAMESPACE_URI')
            namespace = await client.get_namespace_index(uri) if uri else int(os.getenv('KEPSERVER_NAMESPACE_INDEX', '2'))
            for tag in dict.fromkeys(row['OpcTag'] for row in rows):
                try:
                    # Preserve tag spaces and punctuation exactly as supplied by the CSV.
                    node = client.get_node(f'ns={namespace};s={tag}')
                    dv = await node.read_data_value(raise_on_bad_status=False)
                    observations[tag] = {'acquired_at': utcnow().isoformat(),
                        'source_timestamp': dv.SourceTimestamp, 'server_timestamp': dv.ServerTimestamp,
                        'status_code': dv.StatusCode.value,
                        'quality': 'good' if dv.StatusCode.is_good() else 'bad',
                        'raw_value': dv.Value.Value if dv.Value else None}
                except Exception as exc:
                    observations[tag] = {'acquired_at': utcnow().isoformat(), 'quality': 'read_error', 'error': str(exc)}
    except Exception as exc:
        for row in rows:
            observations.setdefault(row['OpcTag'], {'acquired_at': utcnow().isoformat(),
                                                   'quality': 'connection_error', 'error': str(exc)})
    samples = []
    for row in rows:
        sample = dict(observations[row['OpcTag']])
        value = numeric(sample.get('raw_value'))
        sample['numeric_value'] = value
        # Match the project's existing input convention. Never overwrite the raw value.
        scaled = (value - float(row['Offset'])) / float(row['Scaling']) if value is not None and sample['quality'] == 'good' else None
        sample['scaled_value'] = numeric(scaled)
        samples.append(sample)
    return samples


def lock_collector(spool):
    """OS lock is released on exit/crash; one writer owns a spool directory."""
    stream = (spool / 'collector.lock').open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            if stream.tell() == 0:
                stream.write(b'0'); stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return stream
    except OSError as exc:
        stream.close()
        raise RuntimeError('A collector already owns this raw spool directory.') from exc


def main():
    import json
    logging.basicConfig(level=logging.INFO)
    period = float(os.getenv('RAW_SAMPLE_SECONDS', '60'))
    if period < 1:
        raise ValueError('RAW_SAMPLE_SECONDS must be at least 1.')
    digest, content, rows = load_mapping(os.getenv('RAW_MAPPING_CSV', str(CSV_PATH)))
    spool = Path(os.getenv('RAW_SPOOL_DIR', str(Path(__file__).resolve().parents[1] / 'raw_spool')))
    spool.mkdir(parents=True, exist_ok=True)
    collector_lock = lock_collector(spool)
    pending = spool / 'pending.json'
    store = None
    try:
        while True:
            started = time.monotonic()
            try:
                if pending.exists():
                    batch = json.loads(pending.read_text(encoding='utf-8'))
                    if batch['mapping_sha'] != digest:
                        raise RuntimeError('Pending batch uses a different CSV. Restore the original CSV before restarting.')
                else:
                    batch = {'id': str(uuid4()), 'mapping_sha': digest, 'samples': asyncio.run(acquire(rows))}
                    temporary = pending.with_suffix('.tmp')
                    with temporary.open('w', encoding='utf-8') as stream:
                        stream.write(encode(batch)); stream.flush(); os.fsync(stream.fileno())
                    os.replace(temporary, pending)
                if store is None:
                    store = Store().connect()
                    ids = store.register_mapping(digest, content, rows)
                store.write_raw(batch['id'], ids, batch['samples'])
                pending.unlink()
                logging.info('raw data: stored %s mapped readings in batch %s', len(rows), batch['id'])
                time.sleep(max(0, period-(time.monotonic()-started)))
            except Exception:
                logging.exception('Acquisition paused; pending batch retained. Retrying in 5 seconds.')
                if store:
                    store.close(); store = None
                time.sleep(5)
    finally:
        collector_lock.close()
        if store:
            store.close()


if __name__ == '__main__':
    main()
