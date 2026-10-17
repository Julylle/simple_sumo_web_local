"""Validated per-upload SUMO inputs; original model data remains unchanged."""
import csv
import io
import math
from threading import Lock
from uuid import uuid4

COLUMNS = ('sim_time_ms', 'Sumo__Plant__Influent__param__TKN', 'Sumo__Plant__Influent__param__TCOD')
MAX_BYTES = 1024 * 1024
_uploads = {}
_lock = Lock()


def save_input(content, filename):
    if len(content) > MAX_BYTES:
        raise ValueError('CSV must be no larger than 1 MB.')
    try:
        text = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text), strict=True)
        if reader.fieldnames != list(COLUMNS):
            raise ValueError('CSV columns must be: ' + ', '.join(COLUMNS))
        rows = []
        previous = -1
        for line, row in enumerate(reader, 2):
            if None in row or any(row.get(key) is None for key in COLUMNS):
                raise ValueError(f'CSV line {line}: incorrect number of columns.')
            values = [float(row[key]) for key in COLUMNS]
            timestamp = values[0]
            if any(not math.isfinite(v) or v < 0 for v in values):
                raise ValueError(f'CSV line {line}: values must be finite and non-negative.')
            if timestamp % 300000 or timestamp <= previous or (not rows and timestamp != 0):
                raise ValueError(f'CSV line {line}: times must start at 0, increase strictly, and align to 300000 ms.')
            previous = timestamp
            rows.append([int(timestamp), *values[1:]])
        if not rows:
            raise ValueError('CSV must contain at least one data row.')
    except (UnicodeError, csv.Error) as exc:
        raise ValueError('Upload a valid UTF-8 CSV file.') from exc
    except (TypeError, OverflowError) as exc:
        raise ValueError('CSV contains invalid numeric values.') from exc
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(COLUMNS)
    writer.writerows(rows)
    identifier = str(uuid4())
    with _lock:
        while len(_uploads) >= 20:
            del _uploads[next(iter(_uploads))]
        _uploads[identifier] = output.getvalue()
    return {'id': identifier, 'filename': filename.replace('\\', '/').split('/')[-1],
            'count': len(rows), 'end_h': rows[-1][0] / 3600000}


def get_input(identifier):
    with _lock:
        if identifier not in _uploads:
            raise ValueError('Uploaded input has expired. Please upload the CSV again.')
        return _uploads[identifier]
