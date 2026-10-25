"""Supported live inputs: 12 influent, 24 reactor DO and 4 additional control parameters."""
from services.sumo_data import ALLOWED_COLUMNS

DO_COLUMNS = tuple(
    f"Sumo__Plant__CSTR{lane}_{tank}__param__SO2"
    for lane in range(1, 5) for tank in range(5, 11)
)
CONTROL_COLUMNS = (
    'Sumo__Plant__Sideflowdivider3__param__Qpumped_target',
    'Sumo__Plant__Carbon1__param__Q',
    'Sumo__Plant__Carbon2__param__Q',
    'Sumo__Plant__Metal1__param__Q',
)
SENSOR_COLUMNS = (*ALLOWED_COLUMNS, *DO_COLUMNS, *CONTROL_COLUMNS)
