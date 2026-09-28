import numpy as np
from config.parameters import AllVariables

ALLOWED_OUTPUTS = ("time_h", "nh4_mg_l", "cod_mg_l", "n2o_index")

def public_result(raw: dict, max_points: int = 200) -> dict:
    """Publish approved state series using a shared downsampled time axis."""
    n = len(raw["time_h"])
    idx = np.linspace(0, n - 1, min(n, max_points), dtype=int)
    out = {}
    for key in ALLOWED_OUTPUTS:
        arr = np.asarray(raw[key])[idx]
        out[key] = np.round(arr, 5).tolist()
    out["variables"] = {
        name: np.round(np.asarray(raw["variables"][name])[idx], 5).tolist()
        for name in AllVariables
    }
    return out
