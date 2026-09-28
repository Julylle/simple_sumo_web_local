"""Small ODE model used to test the secure simulation pipeline.

States
------
S_cod : biodegradable COD concentration [mg/L]
S_nh4 : ammonium-N concentration [mg/L]

The equations are deliberately simple; this is an integration test model, not a
calibrated wastewater process model.  A fixed-step RK4 solver is implemented
locally so the demo does not depend on SciPy.
"""
from __future__ import annotations

import numpy as np
from config.paths import STEADY_DATA_FILE


def rhs(_t: float, y: np.ndarray, *, do_mg_l: float, srt_d: float) -> np.ndarray:
    cod, nh4 = np.maximum(y, 0.0)

    # Simple oxygen-limited first-order kinetics.
    oxygen_factor = do_mg_l / (0.5 + do_mg_l)
    srt_factor = srt_d / (5.0 + srt_d)
    k_cod = 0.16 * oxygen_factor                 # 1/h
    k_nh4 = 0.10 * oxygen_factor * srt_factor   # 1/h

    d_cod_dt = -k_cod * cod
    d_nh4_dt = -k_nh4 * nh4
    return np.array([d_cod_dt, d_nh4_dt], dtype=float)


def solve_ode(*, cod0: float, nh40: float, do_mg_l: float, srt_d: float,
              duration_h: float, n_steps: int = 480) -> tuple[np.ndarray, np.ndarray]:
    """Solve the two-state ODE with classical fourth-order Runge-Kutta (RK4)."""
    n_steps = max(10, int(n_steps))
    t = np.linspace(0.0, float(duration_h), n_steps + 1)
    y = np.empty((n_steps + 1, 2), dtype=float)
    y[0] = [cod0, nh40]

    for i in range(n_steps):
        dt = t[i + 1] - t[i]
        kwargs = {"do_mg_l": do_mg_l, "srt_d": srt_d}
        k1 = rhs(t[i], y[i], **kwargs)
        k2 = rhs(t[i] + dt / 2, y[i] + dt * k1 / 2, **kwargs)
        k3 = rhs(t[i] + dt / 2, y[i] + dt * k2 / 2, **kwargs)
        k4 = rhs(t[i] + dt, y[i] + dt * k3, **kwargs)
        y[i + 1] = np.maximum(y[i] + dt * (k1 + 2*k2 + 2*k3 + k4) / 6, 0.0)

    return t, y


def run_demo(*, flow_m3_d: float, influent_cod_mg_l: float,
             influent_nh4_mg_l: float, do_mg_l: float, srt_d: float,
             duration_h: float) -> dict[str, np.ndarray]:
    """Return full private model output. The API layer decides what may leave the server."""
    t, y = solve_ode(
        cod0=influent_cod_mg_l,
        nh40=influent_nh4_mg_l,
        do_mg_l=do_mg_l,
        srt_d=srt_d,
        duration_h=duration_h,
    )
    cod, nh4 = y[:, 0], y[:, 1]

    # Synthetic N2O indicator for UI testing only; not a mechanistic N2O model.
    removal_rate = np.maximum(-np.gradient(nh4, t), 0.0)
    low_do_factor = 1.0 + 1.5 / max(do_mg_l, 0.2)
    n2o_index = flow_m3_d * removal_rate * low_do_factor / 1000.0

    return {
        "time_h": t,
        "cod_mg_l": cod,
        "nh4_mg_l": nh4,
        "n2o_index": n2o_index,
        # Example private state: intentionally not included in ALLOWED_OUTPUTS.
        "private_total_state": cod + nh4,
    }
