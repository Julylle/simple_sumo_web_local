"""Versioned CSV mappings and model-derived state-variable catalogs."""
import csv
import hashlib
import io
import math
import os
import zipfile
from pathlib import Path

CSV_PATH = Path(__file__).with_name('cx_opcua1124.csv')
COLUMNS = 'IO IOType SumoName SumoType SumoUnit OpcTag OpcType OpcUnit IsArray Scaling Offset Comment'.split()


def load_mapping(path=CSV_PATH):
    content = Path(path).read_text(encoding='utf-8-sig')
    reader = csv.DictReader(io.StringIO(content))
    if not set(COLUMNS).issubset(reader.fieldnames or []):
        raise ValueError('Mapping CSV is missing required columns.')
    rows = list(reader)
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('Malformed mapping CSV row.')
        if not row['SumoName'] or not row['OpcTag']:
            raise ValueError('Every row requires SumoName and OpcTag.')
        scaling, offset = float(row['Scaling']), float(row['Offset'])
        if not math.isfinite(scaling) or not scaling or not math.isfinite(offset):
            raise ValueError('Scaling must be finite and nonzero; Offset must be finite.')
    if not rows:
        raise ValueError('Mapping CSV is empty.')
    return hashlib.sha256(content.encode()).hexdigest(), content, rows


def model_catalog(project, extra_names=()):
    """True state variables plus explicitly requested plot outputs.

    SystemState is SUMO's much larger derived/internal catalog; opt in separately.
    """
    kinds = {'StateVariable', 'AccumulatedStateVariable'}
    if os.getenv('SUMO_DB_INCLUDE_SYSTEM_STATE', '0') == '1':
        kinds.add('SystemState')
    extra = set(extra_names)
    project = Path(project)
    with project.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    with zipfile.ZipFile(project) as archive:
        rows = [line.split('\t') for line in archive.read('variables.var').decode('utf-8-sig').splitlines() if line.strip()]
    result = {}
    for row in rows:
        if len(row) >= 7 and (row[4] in kinds or row[1] in extra):
            result[row[1]] = {'name': row[1], 'type': row[3], 'category': row[4],
                              'unit': row[6], 'fields': row}
    if not result:
        raise ValueError('No SUMO state variables found in variables.var.')
    return digest, list(result.values())
