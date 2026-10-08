import math
from uuid import UUID
from typing import Annotated, Literal
from pydantic import BaseModel, Field, field_validator
from config.parameters import calibration_params_initial

class CalibrationInput(BaseModel):
    calibration_parameters: dict[str, float] = Field(default_factory=dict)

    @field_validator('calibration_parameters')
    @classmethod
    def validate_calibration(cls, values):
        for name, value in values.items():
            if name not in calibration_params_initial:
                raise ValueError(f'Unknown calibration parameter: {name}')
            if not math.isfinite(value) or value < 0 or (name.startswith('K') and value == 0):
                raise ValueError(f'{name} must be finite and {"positive" if name.startswith("K") else "non-negative"}')
        return values


class AutoCalibrationInput(CalibrationInput):
    measurement_id: UUID
    oxygen_mode: Literal['do_setpoint', 'constant_kla', 'calculated_kla'] = 'calculated_kla'
    do_setpoints: list[Annotated[float, Field(ge=0, le=8, allow_inf_nan=False)]] = Field(
        default_factory=lambda: [0, 0, 1.6, 2.0, 2.2], min_length=5, max_length=5)


class SimulationInput(CalibrationInput):
    use_do_setpoint: bool = False
    input_series: dict[str, str] = Field(default_factory=dict)
    flow_m3_d: float = Field(50000, ge=100, le=1_000_000)
    influent_cod_mg_l: float = Field(450, ge=10, le=3000)
    influent_nh4_mg_l: float = Field(40, ge=0.1, le=300)
    do_mg_l: float = Field(2.0, ge=0.2, le=8)
    srt_d: float = Field(15, ge=1, le=80)
    duration_h: float = Field(24, ge=1, allow_inf_nan=False)
    tank1_volume_m3: float = Field(233.72729, gt=0, allow_inf_nan=False)
    tank1_do_mg_l: float | None = Field(None, ge=0, le=8, allow_inf_nan=False)
    tank2_volume_m3: float = Field(233.72729, gt=0, allow_inf_nan=False)
    tank2_do_mg_l: float | None = Field(None, ge=0, le=8, allow_inf_nan=False)
    tank3_volume_m3: float = Field(467.45451, gt=0, allow_inf_nan=False)
    tank3_do_mg_l: float | None = Field(None, ge=0, le=8, allow_inf_nan=False)
    tank4_volume_m3: float = Field(467.45451, gt=0, allow_inf_nan=False)
    tank4_do_mg_l: float | None = Field(None, ge=0, le=8, allow_inf_nan=False)
    tank5_volume_m3: float = Field(467.45451, gt=0, allow_inf_nan=False)
    tank5_do_mg_l: float | None = Field(None, ge=0, le=8, allow_inf_nan=False)
    mlr_ratio: float = Field(2.5, ge=0, allow_inf_nan=False)
    ras_ratio: float = Field(1, gt=0, allow_inf_nan=False)
