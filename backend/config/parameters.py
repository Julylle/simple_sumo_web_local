initial_values = {
    'S1N20': 0,      'S1N2O0': 0,     'S1NH0': 13.575,    'S1NH2OH0': 0, 'S1NO0': 0,
    'S1NO20': 0.750,      'S1NO30': 0.425,    'S1O0': 0,     'S1S0': 100,
    'S2N20': 0,      'S2N2O0': 0,     'S2NH0':13.190,     'S2NH2OH0': 0, 'S2NO0': 0,
    'S2NO20': 0.120,      'S2NO30': 0.025,    'S2O0': 0,     'S2S0': 100,
    'S3N20': 0,      'S3N2O0': 0,     'S3NH0': 6.622,    'S3NH2OH0': 0, 'S3NO0': 0,
    'S3NO20': 0.642,      'S3NO30': 3.565,    'S3O0': 1.6,     'S3S0': 100,
    'S4N20': 0,      'S4N2O0': 0,     'S4NH0': 2.060,    'S4NH2OH0': 0, 'S4NO0': 0,
    'S4NO20': 0.843,      'S4NO30': 10.495,    'S4O0': 1.0,     'S4S0': 100,
    'S5N20': 0,      'S5N2O0': 0,     'S5NH0': 0.043,    'S5NH2OH0':0,  'S5NO0': 0,
    'S5NO20': 0.225,      'S5NO30': 13.287,    'S5O0': 2.2,   'S5S0': 100,
    'X1AOB0': 148,     'X1H0': 1000,     'X1I0': 100,     'X1NOB0': 40.68,
    'X2AOB0': 148,     'X2H0': 1000,     'X2I0': 100,     'X2NOB0': 40.68,
    'X3AOB0': 148,     'X3H0': 1000,     'X3I0': 100,    'X3NOB0': 40.99,
    'X4AOB0': 148,     'X4H0': 1000,     'X4I0': 100,    'X4NOB0': 40.99,
    'X5AOB0': 148,     'X5H0': 1000,     'X5I0': 100,    'X5NOB0': 40.32,
}

# 2026-01-12 calibration based on profiling data and corresponding monitoring data 
model_parameters = {
    'SOsat': 9.28, # shuting: 8.46
    # 'SRT': 13.5, # degine SRT
    'qwas': 1.6, # WAS flow rate, L/s
    'dynamicSwitch': 1, 'constantKLa':0, 'DOSetpoint': 0,
    'S1DOsetpoint': 0, 'S2DOsetpoint': 0, 'S3DOsetpoint': 1.6, 'S4DOsetpoint': 2.0, 'S5DOsetpoint': 2.2,
    'SN2inlet': 0,  'SN2Oinlet': 0, 'SNHinlet': 63.595, 
    'SNH2OHinlet': 0, 'SNOinlet': 0,
    'SNO2inlet': 0, 'SNO3inlet': 0.01,
    'SOinlet': 0,
    'SSinlet': 412.8, # The current value is TCOD*0.8, 228, sCOD # 516, # TCOD influent
    'XAOBinlet': 0, 'XHinlet': 0,  'XIinlet': 0, #257, # TSS influent
    'XSinlet': 0,     'XNOBinlet': 0,
    'qinlet': 59,   # average flow rate, L/s
    'qras' : 59, # average flow rate, L/s
    'depth1': 3.32, 'depth2': 3.32, 'depth3': 3.3, 'depth4': 3.3, 'depth5': 3.3, 
    'Rdiff' : 0.9640, # average flow rate, L/s
}

# Public simulation inputs used by the browser, mapped to the ASM model's
# internal names and units.  The model uses L/s for hydraulic flows.
PROCESS_VOLUME_L = 2 * 233727.29 + 3 * 467454.51


def frontend_parameter_overrides(parameters):
    """Translate API simulation inputs into ASM parameter overrides."""
    return {
        'qinlet': float(parameters.flow_m3_d) / 86.4,
        'SSinlet': float(parameters.influent_cod_mg_l) * 0.8,
        'SNHinlet': float(parameters.influent_nh4_mg_l),
        'DOSetpoint': 1,
        'S1DOsetpoint': 0,
        'S2DOsetpoint': 0,
        'S3DOsetpoint': float(parameters.do_mg_l),
        'S4DOsetpoint': float(parameters.do_mg_l),
        'S5DOsetpoint': float(parameters.do_mg_l),
        'qwas': PROCESS_VOLUME_L / (float(parameters.srt_d) * 86400),
        'frontend_inputs': True,
    }

# # Calibration parameters for steady state
# default_calibration_params = {
#     # AOB kinetic parameters
#     'uAOB': 1.96,
#     'bAOB': 0.068,
#     'KAOB1O': 1.0,
#     'KAOB2O': 0.6,
#     'KAOBNO2': 20.2,
#     'KAOBNH': 25,
#     # NOB kinetic parameters
#     'uNOB': 0.79,
#     'bNOB': 0.04,
#     'KNOBNO2': 0.51,
#     'KNOBO': 1.1,
#     # Heterotroph kinetic parameters
#     'uH': 6.0,
#     'bH': 0.5,
#     'KHO': 0.1,
#     'KHS1': 20,
#     'KHS2': 20,
#     'KHS3': 20,
#     'KHS4': 20,
#     'KHS5': 40,
#     # Oxygen transfer coefficients
#     'kla1O2': 110,
#     'kla2O2': 90,
#     'kla3O2': 80,
#     'etag2': 0.28,
#     'etag3': 0.16,
#     'etag4': 0.35,
#     'etag5': 0.35, 
# }

# Calibration parameters for steady state
calibration_params_initial = {
    # AOB kinetic parameters
    'bAOB': 0.068,
    'uAOB': 0.9, # 1.96,
    'KAOB1O': 0.5, # 1.0,
    'KAOBNH': 0.8, # 5, 25,
    'KAOBNO2': 1.0, # 20.2,
    # NOB kinetic parameters
    'bNOB': 0.04,
    'uNOB': 1.4, # 0.79,
    'KNOBO': 0.6, # 1.1,
    'KNOBNH': 0.02, # 0.02, 
    'KNOBNO2': 0.5, # 0.51,
    'KAOB2O': 2, # 0.6,
    # Heterotroph kinetic parameters
    'bH': 0.24,
    'uH': 5.5,
    'etag2': 0.6, # 0.28,
    'KHS2': 10,
    'KHNO3': 0.2, # 0.2,
    'KHNH': 0.01, # 0.02,
    'KHO': 0.1, # 0.1,
    'etag3': 0.6, # 0.16,
    'KHS3': 20,
    'KHNO2': 0.2, # 0.2,
    'KHS1': 20,
    'KHS4': 20,
    'KHS5': 40,
    'etag4': 0.5, # 0.35,
    'etag5': 0.9, # 0.35, 
    # Oxygen transfer coefficients
    'kla1O2': 260, # 285,
    'kla2O2': 120, # 75,
    'kla3O2': 60, # 53,
    'qmlr_ratio': 2.5,
}

# Extract lists for backward compatibility
# unknowns = list(calibration_params.keys())
# initial_guess = list(calibration_params.values())

AllVariables = [
            'S1N2', 'S1N2O', 'S1NH', 'S1NH2OH', 'S1NO', 'S1NO2', 'S1NO3', 'S1O', 'S1S',
            'S2N2', 'S2N2O', 'S2NH', 'S2NH2OH', 'S2NO', 'S2NO2', 'S2NO3', 'S2O', 'S2S',
            'S3N2', 'S3N2O', 'S3NH', 'S3NH2OH', 'S3NO', 'S3NO2', 'S3NO3', 'S3O', 'S3S',
            'S4N2', 'S4N2O', 'S4NH', 'S4NH2OH', 'S4NO', 'S4NO2', 'S4NO3', 'S4O', 'S4S',
            'S5N2', 'S5N2O', 'S5NH', 'S5NH2OH', 'S5NO', 'S5NO2', 'S5NO3', 'S5O', 'S5S',
            'X1AOB', 'X1H', 'X1I', 'X1NOB', 'X2AOB', 'X2H', 'X2I', 'X2NOB',
            'X3AOB', 'X3H', 'X3I', 'X3NOB', 'X4AOB', 'X4H', 'X4I', 'X4NOB',
            'X5AOB', 'X5H', 'X5I', 'X5NOB',
            ]