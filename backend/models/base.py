from abc import ABC, abstractmethod
from schemas.simulation import SimulationInput

class SimulationEngine(ABC):
    @abstractmethod
    def run(self, parameters: SimulationInput) -> dict:
        raise NotImplementedError
