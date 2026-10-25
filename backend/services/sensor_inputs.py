"""Supported live inputs: 12 influent parameters and 24 reactor DO setpoints."""
from services.sumo_data import ALLOWED_COLUMNS

DO_COLUMNS = tuple(
    f"Sumo__Plant__CSTR{lane}_{tank}__param__SO2"
    for lane in range(1, 5) for tank in range(5, 11)
)
SENSOR_COLUMNS = (*ALLOWED_COLUMNS, *DO_COLUMNS)
