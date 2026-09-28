import numpy as np

from models.base import SimulationEngine
from dynamic_simulation import run_dynamic_simulation
from config.paths import BACKEND_DIR as PROJECT_DIR
from config.parameters import frontend_parameter_overrides
from schemas.simulation import SimulationInput


class PythonEngine(SimulationEngine):
    """Adapt ASM dynamic results to the public simulation output contract.
    Browser inputs are translated into ASM hydraulic, influent, oxygen and
    sludge-retention parameters before the dynamic model is executed.
    """

    def run(self, p: SimulationInput) -> dict:
        parameter_overrides = frontend_parameter_overrides(p)
        record, _ = run_dynamic_simulation(
            parameter_overrides=parameter_overrides,
            output_times=np.linspace(0.0, p.duration_h * 60.0, 481),
            paraName=None,
            initialization_mode='steady', # three options: 'config', 'steady'， 'measured'
        )
        return {
            "time_h": record.index.to_numpy(dtype=float) / 60.0,
            "variables": {
                name: record[name].to_numpy(dtype=float) for name in record.columns
            },
            "nh4_mg_l": record["S5NH"].to_numpy(dtype=float),
            "cod_mg_l": record["S5S"].to_numpy(dtype=float),
            # Keep the existing API key; this is dissolved N2O (mg N/L).
            "n2o_index": record["S5N2O"].to_numpy(dtype=float),
        }
