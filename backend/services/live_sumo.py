"""Single persistent live SUMO session. Scheduler callbacks never block on OPC I/O."""
import asyncio
import csv
import io
import math
import logging
import os
import tempfile
import shutil
import sys
import threading
import time
import zipfile
from pathlib import Path
from uuid import uuid4

from services.kepserver import read_snapshot
from services.sumo_data import ALLOWED_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
_lock = threading.RLock()
_session = None

def snapshot():
    with _lock:
        if _session is None:
            return {"status": "idle"}
        s = _session
        return {"id": s["id"], "status": s["status"], "error": s.get("error"),
                "phase": s["phase"], "simulated_h": s["sim_ms"] / 3600000,
                "samples": len(s["times"]), "result": {
                    "time_h": list(s["times"]), "variables": {k: list(v) for k, v in s["variables"].items()}}}

def start(mapping, interval_minutes):
    global _session
    if not mapping or any(k not in ALLOWED_COLUMNS or not isinstance(v, str) or not v.strip() for k,v in mapping.items()):
        raise ValueError("Provide valid OPC UA node IDs for supported SUMO inputs.")
    if not isinstance(interval_minutes, int) or not 1 <= interval_minutes <= 60:
        raise ValueError("Limit time must be 1–60 whole minutes.")
    with _lock:
        if _session is not None and _session["status"] in ("starting", "running", "stopping"):
            raise RuntimeError("A live SUMO session is already active.")
        s = {"id": str(uuid4()), "status": "starting", "phase": "initializing",
             "error": None, "sim_ms": 0, "times": [], "variables": {},
             "mapping": dict(mapping), "interval": interval_minutes * 60,
             "stop": threading.Event()}
        _session = s
    threading.Thread(target=_worker, args=(s,), daemon=True, name="sumo-live").start()
    return snapshot()

def stop():
    with _lock:
        if _session is None or _session["status"] not in ("starting", "running"):
            raise RuntimeError("No active live SUMO session.")
        _session["status"] = "stopping"
        _session["phase"] = "saving"
        _session["stop"].set()
    return snapshot()

def export_csv():
    with _lock:
        s = _session
        if s is None or not s["times"]:
            raise ValueError("No live SUMO samples available.")
        names = list(s["variables"])
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["time_h", *names])
        for i, t in enumerate(s["times"]):
            writer.writerow([t, *(s["variables"][k][i] for k in names)])
        return out.getvalue()

def _worker(s):
    model_dir = ROOT / 'real_sim_1202'
    # DTool Python modules are shipped with the SUMO project, not pip-installed.
    if str(model_dir) not in sys.path:
        sys.path.insert(0, str(model_dir))
    try:
        import dynamita.tool as dtool
        import dynamita.scheduler as ds
        from real_sim_1202.fixed_dynamic_run import OUTPUT_VARIABLES, validate_state_file
    except Exception as exc:
        logging.exception("Live SUMO import failed")
        with _lock:
            s["status"] = "failed"
            s["phase"] = "import_failed"
            s["error"] = f"SUMO import failed: {exc}"
        return

    step_ms = s["interval"] * dtool.sec
    # StopTime is an upper bound, not the requested operating duration.
    # Long-running sessions should be restarted from saved state before this limit.
    max_ms = 365 * dtool.day
    done = threading.Event()
    boundary = threading.Event()
    errors = []
    state_loaded = False
    save_requested = False
    saved = False
    job = None
    try:
        logging.info("Live SUMO %s validating model files", s["id"])
        with _lock:
            s["phase"] = "validating_model"
        initial = model_dir / "sumo_steady_state.xml"
        project = model_dir / "Cixi Eastern WWTP_20260920.sumo"
        validate_state_file(initial)
        with zipfile.ZipFile(project) as archive:
            fields = [line.split("\t") for line in archive.read("variables.var").decode("utf-8-sig").splitlines()]
        for column in s["mapping"]:
            meta = next((row for row in fields if len(row)>4 and row[1]==column), None)
            if meta is None or meta[4] not in ("Parameter","SystemParameter","Dimension"):
                raise ValueError("SUMO input not writable: "+column)
        # First read must succeed before creating a SUMO job.
        with _lock:
            s["phase"] = "reading_initial_sensors"
        values = {r["column"]: r["value"] for r in asyncio.run(read_snapshot(s["mapping"]))}
        with tempfile.TemporaryDirectory(prefix="sumo_live_") as directory:
            folder = Path(directory)
            shutil.copytree(model_dir / "dynamita", folder / "dynamita")
            with _lock:
                s["phase"] = "prepared_dynamita_runtime"
            dll = (folder / "dynamic_headless.dll").as_posix()
            output_state = (folder / "final_state.xml").as_posix()
            with _lock:
                s["phase"] = "extracting_model_dll"
            dtool.extract_dll_from_project(str(project), dll)
            ds.sumo.setParallelJobs(1)
            def message(job_id, msg):
                nonlocal state_loaded, saved
                if msg.startswith("530041"):
                    state_loaded = True
                if msg.startswith(("230046","230008")):
                    errors.append("SUMO rejected assignment: "+msg)
                    done.set()
                if msg.startswith("530045") and save_requested:
                    saved = True
                    done.set()
                if ds.sumo.isSimFinishedMsg(msg) and not save_requested:
                    errors.append("SUMO finished unexpectedly.")
                    done.set()
            def sample(job_id, data):
                try:
                    ms = data.get("Sumo__Time")
                    if ms is None or not math.isfinite(float(ms)):
                        raise ValueError("Missing SUMO simulation time.")
                    with _lock:
                        s["sim_ms"] = int(ms)
                        s["times"].append(float(ms)/3600000)
                        for name in [*s["mapping"], *OUTPUT_VARIABLES]:
                            s["variables"].setdefault(name, []).append(float(data.get(name, float("nan"))))
                        # Keep arrays aligned and finite for the plot.
                        if any(not math.isfinite(s["variables"][k][-1]) for k in s["variables"]):
                            raise ValueError("Non-finite SUMO output.")
                    boundary.set()
                except Exception as exc:
                    errors.append(str(exc))
                    done.set()
            ds.sumo.message_callback = message
            ds.sumo.datacomm_callback = sample
            commands = [f'load "{initial.as_posix()}";', "maptoic;", "set Sumo__Time 0;",
                        f"set Sumo__StopTime {max_ms};", f"set Sumo__DataComm {step_ms};",
                        "mode dynamic;", *(f"set {k} {v};" for k,v in values.items()),
                        f"set Sumo__LimitTime {step_ms};", "start;"]
            with _lock:
                s["phase"] = "scheduling_job"
            job = ds.sumo.schedule(dll, commands=commands,
                variables=list(dict.fromkeys(["Sumo__Time", *s["mapping"], *OUTPUT_VARIABLES])),
                jobData={getattr(ds.sumo, "persistent", "persistent"): True})
            with _lock:
                s["status"] = "running"
                s["phase"] = "waiting_for_boundary"
            started = time.monotonic()
            next_index = 1
            while not done.is_set():
                if s["stop"].is_set():
                    break
                if not boundary.wait(0.25):
                    continue
                boundary.clear()
                if not state_loaded:
                    raise RuntimeError("SUMO initial state was not confirmed loaded.")
                with _lock:
                    current_ms = s["sim_ms"]
                if current_ms < next_index * step_ms:
                    continue
                if current_ms > next_index * step_ms:
                    raise RuntimeError("SUMO advanced beyond its input boundary.")
                # Do not advance before real time catches up with simulated time.
                due = started + next_index * s["interval"]
                while time.monotonic() < due and not s["stop"].is_set():
                    s["stop"].wait(min(0.25, due - time.monotonic()))
                if s["stop"].is_set():
                    break
                try:
                    new_values = {r["column"]: r["value"] for r in asyncio.run(read_snapshot(s["mapping"]))}
                except Exception as exc:
                    # Fail closed: do not advance with stale values.
                    raise RuntimeError("OPC UA unavailable; live simulation stopped: "+str(exc)) from exc
                for key, value in new_values.items():
                    ds.sumo.sendCommand(job, f"set {key} {value};")
                values = new_values
                next_index += 1
                ds.sumo.sendCommand(job, f"set Sumo__LimitTime {next_index * step_ms};")
                with _lock:
                    s["phase"] = "simulating"
            if errors:
                raise RuntimeError(errors[0])
            # Save state while the persistent job is paused at its limit.
            save_requested = True
            ds.sumo.sendCommand(job, f'save "{output_state}";')
            if not done.wait(60) or not saved:
                raise RuntimeError("SUMO state-save acknowledgement timed out.")
            validate_state_file(output_state)
            # Keep state available after the temporary directory closes.
            state_path = Path(os.getenv("SUMO_LIVE_STATE_DIR", str(ROOT / "live_states")))
            state_path.mkdir(parents=True, exist_ok=True)
            import shutil
            shutil.copy2(output_state, state_path / (s["id"] + ".xml"))
            with _lock:
                s["status"] = "stopped"
                s["phase"] = "saved"
    except Exception as exc:
        logging.exception("Live SUMO worker failed")
        with _lock:
            s["status"] = "failed"
            s["phase"] = "failed"
            s["error"] = str(exc)
    finally:
        if job is not None:
            try:
                ds.sumo.finish(job)
            except Exception:
                pass
        try:
            ds.sumo.cleanup()
        except Exception:
            pass
        ds.sumo.message_callback = None
        ds.sumo.datacomm_callback = None
