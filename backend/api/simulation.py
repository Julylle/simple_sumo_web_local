from fastapi import APIRouter
from schemas.simulation import SimulationInput
from services.simulation_service import simulate
from config.parameters import calibration_params_initial

router = APIRouter()


@router.get("/calibration-parameters", response_model=dict[str, float])
def get_calibration_parameters():
    """Expose the initial calibration values displayed by the client."""
    return calibration_params_initial.copy()

@router.post("/simulation")
def run_simulation(parameters: SimulationInput):
    return {"result": simulate(parameters)}
