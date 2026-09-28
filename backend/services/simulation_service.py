from models.python_engine import PythonEngine
from services.result_processor import public_result
from schemas.simulation import SimulationInput

_engine = PythonEngine()

def simulate(parameters: SimulationInput) -> dict:
    raw = _engine.run(parameters)
    return public_result(raw)
