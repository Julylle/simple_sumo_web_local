"""Visibility and retention policy for sensor treatment logs, not model inputs."""
import re

_EXCLUDED = re.compile(
    r'Sumo__Plant__(?:CSTR[12](?:_\d+)?__(?:param__)?SO2|MLR[12](?:_\d+)?__.+)'
)


def should_record_input(column):
    return not _EXCLUDED.fullmatch(column or '')


def filter_processing_records(records):
    # Keep original IDs and diagnostic values for all retained records.
    return [row for row in records if should_record_input(row.get('column'))]
