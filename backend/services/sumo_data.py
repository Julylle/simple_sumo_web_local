"""Validated per-upload SUMO inputs; original model data remains unchanged."""
import csv
import io
import math
from threading import Lock
from uuid import uuid4

PREFIX = 'Sumo__Plant__Influent__param__'
PARAMETERS = {
    'Q': 'm3/d', 'pH': 'pH', 'T': 'deg C',
    'Ammonia_sensor_Horiba': 'mg/L', 'COD_lab': 'mg/L', 'TKN_lab': 'mg/L',
    'Ammonia_lab': 'mg/L', 'TSS_sensor': 'mg/L', 'Ammonia_analyzer': 'mg/L',
    'TCOD': 'mg COD/L', 'TKN': 'mg N/L', 'TP': 'mg P/L',
}
ALLOWED_COLUMNS = tuple(PREFIX + name for name in PARAMETERS)
COLUMNS = ('sim_time_ms', PREFIX + 'TKN', PREFIX + 'TCOD')


def validate_columns(columns):
    if not columns or len(columns) != len(set(columns)) or any(c not in ALLOWED_COLUMNS for c in columns):
        raise ValueError('Select one or more distinct supported influent parameters.')
    return list(columns)


def input_options():
    return [{'name': PREFIX + name, 'label': name, 'unit': unit} for name, unit in PARAMETERS.items()]


def template_csv(columns):
    columns = validate_columns(columns)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['sim_time_ms', *columns])
    for timestamp in (0, 300000, 600000):
        writer.writerow([timestamp, *['' for _ in columns]])
    return output.getvalue()


MAX_BYTES = 1024 * 1024
_uploads = {}
_lock = Lock()


def parse_input(content, selected_columns=None):
    if len(content) > MAX_BYTES:
        raise ValueError('CSV must be no larger than 1 MB.')
    try:
        text = content.decode('utf-8-sig')
        reader = csv.DictReader(io.StringIO(text), strict=True)
        fields = reader.fieldnames or []
        if not fields or fields[0] != 'sim_time_ms':
            raise ValueError('The first CSV column must be sim_time_ms.')
        columns = validate_columns(fields[1:])
        if selected_columns is not None and columns != validate_columns(selected_columns):
            raise ValueError('CSV columns must match the selected parameters and their template order.')
        fields = ['sim_time_ms', *columns]
        rows = []
        previous = -1
        for line, row in enumerate(reader, 2):
            if None in row or any(row.get(key) is None for key in fields):
                raise ValueError(f'CSV line {line}: incorrect number of columns.')
            values = [float(row[key]) for key in fields]
            timestamp = values[0]
            if any(not math.isfinite(v) or v < 0 for v in values):
                raise ValueError(f'CSV line {line}: values must be finite and non-negative.')
            if timestamp % 300000 or timestamp <= previous or (not rows and timestamp != 0):
                raise ValueError(f'CSV line {line}: times must start at 0, increase strictly, and align to 300000 ms.')
            for column, value in zip(columns, values[1:]):
                if column == PREFIX + 'pH' and value > 14:
                    raise ValueError(f'CSV line {line}: pH must be between 0 and 14.')
                if column == PREFIX + 'T' and value > 100:
                    raise ValueError(f'CSV line {line}: temperature must be between 0 and 100 deg C.')
                if column == PREFIX + 'Q' and value <= 0:
                    raise ValueError(f'CSV line {line}: flow Q must be positive.')
            previous = timestamp
            rows.append([int(timestamp), *values[1:]])
        if not rows:
            raise ValueError('CSV must contain at least one data row.')
    except (UnicodeError, csv.Error) as exc:
        raise ValueError('Upload a valid UTF-8 CSV file.') from exc
    except (TypeError, OverflowError) as exc:
        raise ValueError('CSV contains invalid numeric values.') from exc
    return columns, rows


def save_input(content, filename, selected_columns=None):
    columns, rows = parse_input(content, selected_columns)
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['sim_time_ms', *columns])
    writer.writerows(rows)
    identifier = str(uuid4())
    with _lock:
        while len(_uploads) >= 20:
            del _uploads[next(iter(_uploads))]
        _uploads[identifier] = output.getvalue()
    return {'id': identifier, 'filename': filename.replace('\\', '/').split('/')[-1],
            'count': len(rows), 'end_h': rows[-1][0] / 3600000, 'columns': columns}


def get_input(identifier):
    with _lock:
        if identifier not in _uploads:
            raise ValueError('Uploaded input has expired. Please upload the CSV again.')
        return _uploads[identifier]
