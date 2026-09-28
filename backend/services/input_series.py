"""Validated, persisted Excel boundary conditions for one MLE lane."""
import io
import json
import os
from pathlib import Path
from uuid import uuid4, UUID

import numpy as np
import pandas as pd

from config.paths import BACKEND_DIR, DYNAMIC_DATA_FILE

SERIES = {
    "inflow": ("Single lane inflow rate", "m3/d"),
    "bcod": ("Influent biodegradable COD (bCOD)", "mg/L"),
    "nh4": ("Influent NH4-N", "mg/L"),
    "ras": ("Return activated sludge (RAS)", "m3/d per lane"),
    "was": ("Waste activated sludge (WAS)", "m3/d per lane"),
    "airflow1": ("Aerobic 1 airflow rate", "m3/h per lane"),
    "airflow2": ("Aerobic 2 airflow rate", "m3/h per lane"),
    "airflow3": ("Aerobic 3 airflow rate", "m3/h per lane"),
}
STORE_DIR = Path(os.environ.get("SERIES_STORE_DIR", BACKEND_DIR / "runtime" / "input-series"))


def validate_series(time_h, values):
    times = np.asarray(time_h, dtype=float)
    values = np.asarray(values, dtype=float)
    if times.ndim != 1 or values.ndim != 1 or len(times) != len(values) or len(times) < 2:
        raise ValueError("Provide at least two matching time_h and value rows")
    if not np.isfinite(times).all() or not np.isfinite(values).all():
        raise ValueError("Times and values must be finite numbers without blank cells")
    if times[0] != 0 or not (np.diff(times) > 0).all():
        raise ValueError("time_h must start at 0 and be strictly increasing")
    if (values < 0).any():
        raise ValueError("Values must be non-negative")
    return {"time_h": times.tolist(), "values": values.tolist()}


def parse_excel(content):
    frame = pd.read_excel(io.BytesIO(content), sheet_name=0, engine="openpyxl")
    frame.columns = [str(column).strip() for column in frame.columns]
    if not {"time_h", "value"}.issubset(frame.columns):
        raise ValueError("The first worksheet must contain time_h and value columns")
    frame = frame[["time_h", "value"]].dropna(how="all")
    return validate_series(frame.time_h, frame.value)


def default_profiles():
    frame = pd.read_excel(DYNAMIC_DATA_FILE, sheet_name="dyinput")
    times = frame["t (min)"].to_numpy(dtype=float) / 60
    profiles = {
        "inflow": (frame["Effluent rate (L/s)"] + frame["WAS (L/s)"]) * 86.4 / 11,
        "bcod": frame.bCOD, "nh4": frame.SNH,
        "ras": frame["RAS (L/s)"] * 86.4 / 11,
        "was": frame["WAS (L/s)"] * 86.4 / 11,
    }
    for i, share in enumerate((0.55, 0.26, 0.19), 1):
        profiles[f"airflow{i}"] = frame["Aeration Tank 4_m3/h"] * share
    return {key: validate_series(times, values) for key, values in profiles.items()}


def metadata(key, profile, identifier=None, filename="Built-in dyinput workbook"):
    return {"id": identifier, "filename": filename, "key": key, "unit": SERIES[key][1],
            "count": len(profile["time_h"]), "end_h": profile["time_h"][-1],
            "minimum": min(profile["values"]), "maximum": max(profile["values"])}


def save_upload(key, content, filename):
    if key not in SERIES:
        raise ValueError("Unknown input series")
    profile = parse_excel(content)
    identifier = uuid4().hex
    info = metadata(key, profile, identifier, Path(filename.replace("\\", "/")).name[:200])
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    # Unique files preserve previous uploads and prevent concurrent overwrite.
    (STORE_DIR / f"{identifier}.json").write_text(json.dumps({**profile, **info}), encoding="utf-8")
    (STORE_DIR / f"{identifier}.xlsx").write_bytes(content)
    return info


def read_upload(key, identifier):
    identifier = UUID(identifier).hex
    data = json.loads((STORE_DIR / f"{identifier}.json").read_text(encoding="utf-8"))
    if data["key"] != key:
        raise ValueError("Uploaded series does not match the selected input")
    validate_series(data["time_h"], data["values"])
    return data


def resolve_profiles(selections):
    defaults = default_profiles()
    references = [float(np.mean(defaults[f"airflow{i}"]["values"][:8])) for i in (1, 2, 3)]
    for key, identifier in selections.items():
        if key not in SERIES:
            raise ValueError("Unknown input series")
        defaults[key] = read_upload(key, identifier)
    if any(value <= 0 for value in defaults["ras"]["values"]):
        raise ValueError("RAS must remain positive for the current ideal settler model")
    return defaults, references


def sample(profile, t_minutes):
    index = np.searchsorted(profile["time_h"], t_minutes / 60, side="right") - 1
    return float(profile["values"][max(0, min(index, len(profile["values"]) - 1))])
