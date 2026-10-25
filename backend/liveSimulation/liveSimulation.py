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
from services.model_inputs import scale_model_inputs
from services.sensor_inputs import SENSOR_COLUMNS
from services.live_models import resolve_model
from services.live_checkpoint import save_checkpoint, checkpoint_info, restore_checkpoint, saved_snapshot

ROOT = Path(__file__).resolve().parents[1]
_lock = threading.RLock()
_session = None

def snapshot():
    with _lock:
        if _session is None:
            try:
                saved = saved_snapshot()
            except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                saved = None
            return {**(saved or {"status": "idle"}), "checkpoint": checkpoint_info()}
        s = _session
        return {"id": s["id"], "status": s["status"], "error": s.get("error"),
                "model_id": s["model_id"], "model_name": s["model"]["name"],
                "mapping": dict(s["mapping"]), "interval_minutes": s["interval"] // 60,
                "checkpoint": checkpoint_info(),
                "phase": s["phase"], "simulated_h": s["sim_ms"] / 3600000,
                "samples": len(s["times"]), "result": {
                    "time_h": list(s["times"]), "variables": {k: list(v) for k, v in s["variables"].items()}}}

def start(mapping, interval_minutes, model_id="builtin"):
    global _session
    if not mapping or any(k not in SENSOR_COLUMNS or not isinstance(v, str) or not v.strip() for k,v in mapping.items()):
        raise ValueError("Provide valid OPC UA node IDs for supported SUMO inputs.")
    if not isinstance(interval_minutes, int) or not 1 <= interval_minutes <= 60:
        raise ValueError("Limit time must be 1–60 whole minutes.")
    selected_model = resolve_model(model_id)
    return _launch(mapping, interval_minutes, model_id, selected_model)

def _launch(mapping, interval_minutes, model_id, selected_model, resume_ms=0, resume_folder=None, result=None, run_id=None):
    global _session
    with _lock:
        if _session is not None and _session["status"] in ("starting", "running", "stopping"):
            raise RuntimeError("A live SUMO session is already active.")
        s = {"id": run_id or str(uuid4()), "status": "starting", "phase": "initializing",
             "error": None, "sim_ms": resume_ms, "resume_ms": resume_ms,
             "resume_folder": resume_folder, "times": list((result or {}).get("time_h", [])),
             "variables": {k: list(v) for k, v in (result or {}).get("variables", {}).items()},
             "mapping": dict(mapping), "interval": interval_minutes * 60,
             "model": selected_model, "model_id": model_id,
             "stop": threading.Event()}
        _session = s
    threading.Thread(target=_worker, args=(s,), daemon=True, name="sumo-live").start()
    return snapshot()

def resume():
    with _lock:
        if _session is not None and _session['status'] in ('starting', 'running', 'stopping'):
            raise RuntimeError('A live SUMO session is already active.')
        metadata, model, folder = restore_checkpoint()
        try:
            return _launch(metadata['mapping'], metadata['interval_minutes'], 'checkpoint', model,
                           metadata['simulated_ms'], folder, metadata.get('result'), metadata['run_id'])
        except Exception:
            folder.cleanup()
            raise


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
        current = snapshot()
        result = current.get('result') or {}
        s = {'times': result.get('time_h', []), 'variables': result.get('variables', {})}
        if not s['times']:
            raise ValueError("No live SUMO samples available.")
        names = list(s["variables"])
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["time_h", *names])
        for i, t in enumerate(s["times"]):
            writer.writerow([t, *(s["variables"][k][i] for k in names)])
        return out.getvalue()

def _read_model_inputs(mapping):
    """Read fresh raw sensors and convert flows only at the SUMO input boundary."""
    readings = asyncio.run(read_snapshot(mapping))
    return scale_model_inputs(readings)


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
        if s.get("resume_folder") is not None:
            s["resume_folder"].cleanup()
        return

    step_ms = s["interval"] * dtool.sec
    # StopTime is an upper bound, not the requested operating duration.
    # Long-running sessions should be restarted from saved state before this limit.
    resume_ms = s.get("resume_ms", 0)
    max_ms = resume_ms + 365 * dtool.day
    done = threading.Event()
    boundary = threading.Event()
    errors = []
    state_loaded = False
    save_requested = False
    save_done = threading.Event()
    job = None
    workspace = None
    try:
        logging.info("Live SUMO %s validating model files", s["id"])
        with _lock:
            s["phase"] = "validating_model"
        initial = s["model"]["state"]
        project = s["model"]["project"]
        validate_state_file(initial)
        with zipfile.ZipFile(project) as archive:
            fields = [line.split("\t") for line in archive.read("variables.var").decode("utf-8-sig").splitlines()]
        for column in s["mapping"]:
            meta = next((row for row in fields if len(row)>4 and row[1]==column), None)
            if meta is None or meta[4] not in ("Parameter","SystemParameter","Dimension"):
                raise ValueError("SUMO input not writable: "+column)
        available_names = {row[1] for row in fields if len(row) > 1}
        output_variables = [name for name in OUTPUT_VARIABLES if name in available_names]
        # First read must succeed before creating a SUMO job.
        with _lock:
            s["phase"] = "reading_initial_sensors"
        values = _read_model_inputs(s["mapping"])
        # Release the scheduler before removing a directory containing its loaded DLL.
        workspace = tempfile.TemporaryDirectory(prefix="sumo_live_", ignore_cleanup_errors=True)
        directory = workspace.name
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
            nonlocal state_loaded
            if msg.startswith("530041"):
                state_loaded = True
            if msg.startswith(("230046","230008")):
                errors.append("SUMO rejected assignment: "+msg)
                done.set()
            if msg.startswith("530045") and save_requested:
                save_done.set()
            if ds.sumo.isSimFinishedMsg(msg):
                errors.append("SUMO finished unexpectedly.")
                done.set()
        def sample(job_id, data):
            try:
                ms = data.get("Sumo__Time")
                if ms is None or not math.isfinite(float(ms)):
                    raise ValueError("Missing SUMO simulation time.")
                with _lock:
                    # Some schedulers emit the loaded checkpoint at start; do not duplicate it.
                    if s["times"] and float(ms)/3600000 <= s["times"][-1]:
                        return
                    s["sim_ms"] = int(ms)
                    s["times"].append(float(ms)/3600000)
                    for name in dict.fromkeys([*s["mapping"], *output_variables]):
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
        commands = [f'load "{initial.as_posix()}";', "maptoic;", f"set Sumo__Time {resume_ms};",
                    f"set Sumo__StopTime {max_ms};", f"set Sumo__DataComm {step_ms};",
                    "mode dynamic;", *(f"set {k} {v};" for k,v in values.items()),
                    f"set Sumo__LimitTime {resume_ms + step_ms};", "start;"]
        with _lock:
            s["phase"] = "scheduling_job"
        job = ds.sumo.schedule(dll, commands=commands,
            variables=list(dict.fromkeys(["Sumo__Time", *s["mapping"], *output_variables])),
            jobData={getattr(ds.sumo, "persistent", "persistent"): True})
        with _lock:
            s["status"] = "running"
            s["phase"] = "waiting_for_boundary"
        def checkpoint(simulated_ms):
            nonlocal save_requested
            with _lock:
                s['phase'] = 'saving_checkpoint'
            save_done.clear()
            save_requested = True
            try:
                ds.sumo.sendCommand(job, f'save "{output_state}";')
                deadline = time.monotonic() + 60
                while not save_done.wait(0.1):
                    if done.is_set() or time.monotonic() >= deadline:
                        raise RuntimeError('Checkpoint save failed or timed out; previous checkpoint retained.')
                if errors:
                    raise RuntimeError(errors[0])
                validate_state_file(output_state)
                save_checkpoint(s, output_state, simulated_ms)
            finally:
                save_requested = False

        started = time.monotonic()
        next_index = 1
        while not done.is_set():
            if not boundary.wait(0.25):
                continue
            boundary.clear()
            if not state_loaded:
                raise RuntimeError("SUMO initial state was not confirmed loaded.")
            with _lock:
                current_ms = s["sim_ms"]
            if current_ms < resume_ms + next_index * step_ms:
                continue
            if current_ms > resume_ms + next_index * step_ms:
                raise RuntimeError("SUMO advanced beyond its input boundary.")
            checkpoint(current_ms)
            # Do not advance before real time catches up with simulated time.
            due = started + next_index * s["interval"]
            while time.monotonic() < due and not s["stop"].is_set():
                s["stop"].wait(min(0.25, due - time.monotonic()))
            if s["stop"].is_set():
                break
            try:
                new_values = _read_model_inputs(s["mapping"])
            except Exception as exc:
                # Fail closed: do not advance with stale values.
                raise RuntimeError("OPC UA unavailable; live simulation stopped: "+str(exc)) from exc
            for key, value in new_values.items():
                ds.sumo.sendCommand(job, f"set {key} {value};")
            values = new_values
            next_index += 1
            ds.sumo.sendCommand(job, f"set Sumo__LimitTime {resume_ms + next_index * step_ms};")
            with _lock:
                s["phase"] = "simulating"
        if errors:
            raise RuntimeError(errors[0])
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
        # Windows may retain DLL handles briefly even after Scheduler cleanup.
        # Temporary-file cleanup must not replace the actual simulation outcome.
        for temporary in (workspace, s.get("resume_folder")):
            if temporary is not None:
                try:
                    temporary.cleanup()
                except OSError:
                    logging.warning("Temporary SUMO files remain in %s", temporary.name, exc_info=True)
