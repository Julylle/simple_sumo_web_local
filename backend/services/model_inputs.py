"""Shared raw-sensor conversion for live and steady SUMO inputs."""
import math
from database.catalog import load_mapping

INPUT_CONVERSIONS = {row['SumoName']: (float(row['Scaling']), float(row['Offset']))
                     for row in load_mapping()[2]}


def scale_model_inputs(readings):
    values = {r["column"]: r["value"] for r in readings}
    # Raw OPC and historical numeric_value use the same CSV conversion once.
    for column in values:
        if column in INPUT_CONVERSIONS:
            scaling, offset = INPUT_CONVERSIONS[column]
            values[column] = (values[column] - offset) / scaling
    for column, value in values.items():
        if not math.isfinite(value):
            raise ValueError("Non-finite SUMO input after conversion: " + column)
    return values
