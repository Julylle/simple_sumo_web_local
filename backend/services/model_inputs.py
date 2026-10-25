"""Shared raw-sensor conversion for live and steady SUMO inputs."""
import math


def scale_model_inputs(readings):
    values = {r["column"]: r["value"] for r in readings}
    # Apply site conversions to fresh raw values, exactly once per update.
    for column in (
        "Sumo__Plant__Influent__param__Q",
        "Sumo__Plant__Sideflowdivider3__param__Qpumped_target",
    ):
        if column in values:
            values[column] /= 0.0417
    for column in (
        "Sumo__Plant__Carbon1__param__Q",
        "Sumo__Plant__Carbon2__param__Q",
        "Sumo__Plant__Metal1__param__Q",
    ):
        if column in values:
            values[column] /= 41.67
    for column, value in values.items():
        if not math.isfinite(value):
            raise ValueError("Non-finite SUMO input after conversion: " + column)
    return values
