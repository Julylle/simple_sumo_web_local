"""Shared filesystem locations for the standalone ASM simulations."""

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
PRIVATE_DIR = Path(os.environ.get('PRIVATE_DATA_DIR', BACKEND_DIR.parent / 'private'))
DATA_DIR = PRIVATE_DIR / 'DataForModel'
STEADY_DATA_FILE = DATA_DIR / '1_WaterCorp_SteadyCali_20260401.xlsx'
DYNAMIC_DATA_FILE = DATA_DIR / 'TwoDays_Subiaco_DynamicCali_20260401.xlsx'
STEADY_STATE_FILE = BACKEND_DIR / 'steady_state_initial_values.pkl'
