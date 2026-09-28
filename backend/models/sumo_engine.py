from models.base import SimulationEngine
from schemas.simulation import SimulationInput

class SUMOEngine(SimulationEngine):
    """Integration point for Dynamita SUMO. Kept server-side only."""
    def run(self, parameters: SimulationInput) -> dict:
        raise NotImplementedError("Configure Dynamita SUMO on the server before enabling SUMOEngine.")
