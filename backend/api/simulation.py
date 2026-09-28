from fastapi import APIRouter
from schemas.simulation import SimulationInput
from services.simulation_service import simulate

router = APIRouter()

@router.post("/simulation")
def run_simulation(parameters: SimulationInput):
    return {"result": simulate(parameters)}
