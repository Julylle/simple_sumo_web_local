import numpy as np

from models.base import SimulationEngine
from dynamic_simulation import run_dynamic_simulation
from schemas.simulation import SimulationInput


class PythonEngine(SimulationEngine):
    """Adapt ASM dynamic results to the public simulation output contract.

    Flow, influent concentrations and sludge wasting come from the dynamic
    workbook; the demo's flow/COD/NH4/SRT inputs are not mapped to this model.
    """

    def run(self, p: SimulationInput) -> dict:
        record, _ = run_dynamic_simulation(
            parameter_overrides={
                "DOSetpoint": 1,
                "S3DOsetpoint": p.do_mg_l,
                "S4DOsetpoint": p.do_mg_l,
                "S5DOsetpoint": p.do_mg_l,
            },
            output_times=np.linspace(0.0, p.duration_h * 60.0, 481),
            plot=False,
            compare=False,
            paraName=None,
        )
        return {
            "time_h": record.index.to_numpy(dtype=float) / 60.0,
            "nh4_mg_l": record["S5NH"].to_numpy(dtype=float),
            "cod_mg_l": record["S5S"].to_numpy(dtype=float),
            # Keep the existing API key; this is dissolved N2O (mg N/L).
            "n2o_index": record["S5N2O"].to_numpy(dtype=float),
        }
