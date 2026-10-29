"""Supported live inputs: 16 influent, 24 reactor DO and 33 additional control parameters."""
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
    'Sumo__Plant__WAS_1__param__Qpumped_target',
    'Sumo__Plant__WAS_2__param__Qpumped_target',
    'Sumo__Plant__Clarifier1__param__Qsludge_target',
    'Sumo__Plant__Clarifier2__param__Qsludge_target',
    'Sumo__Plant__MLR1_1__param__Qpumped_target',
    'Sumo__Plant__MLR1_2__param__Qpumped_target',
    'Sumo__Plant__Switchcontroller2__param__CVtreshold',
    'Sumo__Plant__Switchcontroller3__param__CVtreshold',
    'Sumo__Plant__Sideflowdivider9__param__Qpumped_target',
    'Sumo__Plant__CSTR1_4__param__Ammonia_sensor',
    'Sumo__Plant__CSTR1_4__param__Nitrate_sensor',
    'Sumo__Plant__CSTR23__param__PO4_P_sensor',
    'Sumo__Plant__CSTR1_10__param__MLSS_lab',
    'Sumo__Plant__CSTR1_10__param__MLVSS_lab',
    'Sumo__Plant__CSTR2_10__param__MLSS_lab',
    'Sumo__Plant__CSTR2_10__param__MLVSS_lab',
    'Sumo__Plant__CSTR3_10__param__MLSS_lab',
    'Sumo__Plant__CSTR3_10__param__MLVSS_lab',
    'Sumo__Plant__CSTR4_10__param__MLSS_lab',
    'Sumo__Plant__CSTR4_10__param__MLVSS_lab',
    'Sumo__Plant__CSTR1_10__param__Nitrate_sensor',
    'Sumo__Plant__param__Qair_1_1_sensor',
    'Sumo__Plant__param__Qair_1_2_sensor',
    'Sumo__Plant__CSTR1_6__param__DO_sensor',
    'Sumo__Plant__CSTR1_7__param__DO_sensor',
    'Sumo__Plant__CSTR1_9__param__DO_sensor',
    'Sumo__Plant__CSTR1_10__param__MLSS_sensor',
    'Sumo__Plant__CSTR3_10__param__Nitrate_sensor',
    'Sumo__Plant__CSTR3_4__param__Nitrate_sensor',
)
EXTRA_INFLUENT_COLUMNS = ('Sumo__Plant__Influent__param__COD_analyzer', 'Sumo__Plant__Primary1__param__TSS_sensor', 'Sumo__Plant__Influent__param__frVSS_TSS', 'Sumo__Plant__Primary1__param__TSS_lab')
SENSOR_COLUMNS = (*ALLOWED_COLUMNS, *EXTRA_INFLUENT_COLUMNS, *DO_COLUMNS, *CONTROL_COLUMNS)
