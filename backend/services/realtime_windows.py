"""Time-window coordinator shared by live and historical SUMO modes.

The SUMO scheduler must remain persistent. This module only controls when
the next 300-second input window may be released; it never restarts SUMO.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
import math
from services.sensor_policy import normalize_reading
import time


class Mode(str, Enum):
    LIVE = "live"
    REPLAY = "replay"


@dataclass(frozen=True)
class Window:
    index: int
    start_ms: int
    end_ms: int
    inputs: dict[str, float]


def make_windows(samples, step_seconds=300):
    """Aggregate timestamped samples into windows (mean of valid samples).

    samples: iterable of (elapsed_seconds, {SUMO_column: value}).
    Reject missing windows instead of silently substituting zero.
    """
    if step_seconds <= 0:
        raise ValueError("step_seconds must be positive")
    grouped = {}
    for elapsed, values in samples:
        if not isinstance(elapsed, (int, float)) or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("Invalid sample timestamp")
        if not isinstance(values, dict) or not values:
            raise ValueError("Missing sensor values")
        index = int(elapsed // step_seconds)
        bucket = grouped.setdefault(index, {})
        for column, value in values.items():
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"Invalid sensor value for {column}")
            bucket.setdefault(column, []).append(normalize_reading(column, float(value)))
    if not grouped:
        raise ValueError("No samples")
    columns = set(next(iter(grouped.values())))
    windows = []
    for index in range(max(grouped) + 1):
        bucket = grouped.get(index)
        if bucket is None or set(bucket) != columns:
            raise ValueError(f"Missing data in window {index}")
        windows.append(Window(index, index * step_seconds * 1000,
                              (index + 1) * step_seconds * 1000,
                              {key: sum(vals) / len(vals) for key, vals in bucket.items()}))
    return windows


class ClockGate:
    """Wait until a live wall-clock window ends; replay never waits.

    Use monotonic time so changes to system time do not shift simulation.
    """
    def __init__(self, mode: Mode, step_seconds=300, clock=time.monotonic, sleeper=time.sleep):
        self.mode = Mode(mode)
        self.step_seconds = step_seconds
        self.clock = clock
        self.sleeper = sleeper
        self.started_at = clock()

    def await_window(self, index):
        if index < 0:
            raise ValueError("Window index must be nonnegative")
        if self.mode == Mode.LIVE:
            delay = self.started_at + (index + 1) * self.step_seconds - self.clock()
            if delay > 0:
                self.sleeper(delay)
