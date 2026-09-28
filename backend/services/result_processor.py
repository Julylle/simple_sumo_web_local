import numpy as np

ALLOWED_OUTPUTS = ("time_h", "nh4_mg_l", "cod_mg_l", "n2o_index")

def public_result(raw: dict, max_points: int = 200) -> dict:
    """Allow-list + downsample. Raw/private model state never crosses the API boundary."""
    n = len(raw["time_h"])
    idx = np.linspace(0, n - 1, min(n, max_points), dtype=int)
    out = {}
    for key in ALLOWED_OUTPUTS:
        arr = np.asarray(raw[key])[idx]
        out[key] = np.round(arr, 5).tolist()
    return out
