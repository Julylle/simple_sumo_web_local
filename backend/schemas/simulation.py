from pydantic import BaseModel, Field

class SimulationInput(BaseModel):
    flow_m3_d: float = Field(50000, ge=100, le=1_000_000)
    influent_cod_mg_l: float = Field(450, ge=10, le=3000)
    influent_nh4_mg_l: float = Field(40, ge=0.1, le=300)
    do_mg_l: float = Field(2.0, ge=0.2, le=8)
    srt_d: float = Field(15, ge=1, le=80)
    duration_h: float = Field(24, ge=1, le=240)
