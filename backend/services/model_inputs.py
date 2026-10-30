"""Shared raw-sensor conversion for live and steady SUMO inputs."""
import math
from services.sensor_policy import normalize_reading
from database.catalog import load_mapping

INPUT_CONVERSIONS = {row['SumoName']: (float(row['Scaling']), float(row['Offset']))
                     for row in load_mapping()[2]}


def scale_model_inputs(readings):
    values = {}
    for reading in readings:
        column, value = reading['column'], float(reading['value'])
        if not math.isfinite(value):
            raise ValueError('Non-finite sensor input: ' + column)
        values[column] = normalize_reading(column, value)
    # Raw OPC and historical numeric_value use the same CSV conversion once.
    for column in values:
        if column in INPUT_CONVERSIONS:
            scaling, offset = INPUT_CONVERSIONS[column]
            values[column] = (values[column] - offset) / scaling
    for column, value in values.items():
        if not math.isfinite(value):
            raise ValueError("Non-finite SUMO input after conversion: " + column)
    return values
