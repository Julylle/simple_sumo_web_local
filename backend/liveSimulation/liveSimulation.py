"""Single persistent live SUMO session. Scheduler callbacks never block on OPC I/O."""
import asyncio
import csv
from datetime import datetime, timedelta, timezone
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

from database.simulation import open_recorder
from services.historical_inputs import history_request, load_history, load_available_history, parse_time, history_time
from services.kepserver import read_snapshot
from services.input_provenance import input_provenance, process_readings, record_treatments
from services.sensor_inputs import SENSOR_COLUMNS
from services.processing_history import filter_processing_records
from services.sumo_startup import write_startup_script, project_parameter_commands
from services.live_progress import live_progress
from services.resume_history import resume_history
from services.sensor_comparisons import LIVE_EXTRA_OUTPUTS
from services.live_models import resolve_model
from services.live_checkpoint import save_checkpoint, checkpoint_info, restore_checkpoint, saved_snapshot, persist_processing_records

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
                "checkpoint": checkpoint_info(), "mode": s.get("mode", "live"),
                "history": dict(s["history"]) if s.get("history") else None,
                "last_sumo_message": s.get("last_sumo_message"),
                "sumo_commands": list(s.get("sumo_commands", [])),
                "diagnostics": live_progress(s),
                "input_provenance": s.get("input_provenance"),
                "input_processing_records": filter_processing_records(s.get("input_processing_records", [])),
                "phase": s["phase"], "simulated_h": s["sim_ms"] / 3600000,
                "samples": len(s["times"]), "result": {
                    "sensor_timestamps": list(s.get("sensor_timestamps", [None] * len(s["times"]))),
                    "time_h": list(s["times"]), "variables": {k: list(v) for k, v in s["variables"].items()}}}

def start(mapping, interval_minutes=1, model_id="builtin", mode="live", history_start=None, history_end=None):
    global _session
    if not mapping or any(k not in SENSOR_COLUMNS or not isinstance(v, str) or not v.strip() for k,v in mapping.items()):
        raise ValueError("Provide valid OPC UA node IDs for supported SUMO inputs.")
    if not isinstance(interval_minutes, int) or not 1 <= interval_minutes <= 60:
        raise ValueError("Limit time must be 1–60 whole minutes.")
    if mode not in ('live', 'history_then_live'):
        raise ValueError('Unknown simulation mode.')
    history = history_request(history_start, history_end, interval_minutes) if mode == 'history_then_live' else None
    selected_model = resolve_model(model_id)
    return _launch(mapping, interval_minutes, model_id, selected_model, history=history)

def _launch(mapping, interval_minutes, model_id, selected_model, resume_ms=0, resume_folder=None, result=None, run_id=None, history=None, input_processing_records=None):
    global _session
    if history is not None:
        history = dict(history)
        # Old checkpoints predate last_inputs; recover actual model-unit inputs
        # from their saved series, without applying flow scaling a second time.
        if resume_ms and not history.get('last_inputs'):
            history['last_inputs'] = {key: values[-1] for key, values in (result or {}).get('variables', {}).items()
                                     if key in mapping and values and isinstance(values[-1], (int, float))
                                     and math.isfinite(values[-1]) and values[-1] >= 0}
    with _lock:
        if _session is not None and _session["status"] in ("starting", "running", "stopping"):
            raise RuntimeError("A live SUMO session is already active.")
        s = {"id": run_id or str(uuid4()), "status": "starting", "phase": "initializing",
             "input_processing_records": filter_processing_records(input_processing_records or []),
             "error": None, "sim_ms": resume_ms, "resume_ms": resume_ms,
             "resume_folder": resume_folder, "times": list((result or {}).get("time_h", [])),
             "variables": {k: list(v) for k, v in (result or {}).get("variables", {}).items()},
             "sensor_timestamps": list((result or {}).get("sensor_timestamps", [None] * len((result or {}).get("time_h", [])))),
             "mapping": dict(mapping), "interval": interval_minutes * 60,
             "model": selected_model, "model_id": model_id,
             "history": dict(history) if history else None,
             "mode": "history" if history and (not history.get("caught_up") if history.get("follow") else history["completed"] < history["total"]) else "live",
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
                           metadata['simulated_ms'], folder, metadata.get('result'), metadata['run_id'], resume_history(metadata),
                           metadata.get('input_processing_records', []))
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
        writer.writerow(["time_h", "sensor_read_at_utc", *names])
        for i, t in enumerate(s["times"]):
            writer.writerow([t, result.get("sensor_timestamps", [None] * len(s["times"]))[i], *(s["variables"][k][i] for k in names)])
        return out.getvalue()

def _read_model_inputs(mapping, previous=None):
    readings = asyncio.run(read_snapshot(mapping, tolerate_errors=True))
    return process_readings(mapping, readings, previous)


def _wait_for_collected_windows(s, done=None):
    """Read ahead immediately; only sleep after catching up to acquisition."""
    while not s['stop'].is_set():
        if done is not None and done.is_set():
            raise RuntimeError('SUMO stopped while waiting for sensor collection.')
        if s['history'].get('caught_up'):
            with _lock:
                s['phase'] = 'waiting_for_sensor_collection'
            delay = s.get('_history_next_read_at', 0) - time.monotonic()
            if delay > 0:
                # Wake for stop/error handling, without querying the database.
                s['stop'].wait(min(1, delay))
                continue
        read_started = time.monotonic()
        query_started = time.perf_counter()
        windows = load_available_history(s['mapping'], s['interval'], s['history'])
        with _lock:
            s.setdefault('timings', {})['history_read_seconds'] = time.perf_counter() - query_started
        s['_history_next_read_at'] = read_started + max(60, s['interval'])
        if s['stop'].is_set():
            return []
        if done is not None and done.is_set():
            raise RuntimeError('SUMO stopped while reading collected data.')
        with _lock:
            if windows:
                s['history']['total'] = s['history']['completed'] + len(windows)
                s['mode'] = 'live' if s['history'].get('caught_up') else 'history'
                return windows
            s['history']['caught_up'] = True
            s['mode'] = 'live'
            s['phase'] = 'waiting_for_sensor_collection'
        # A halted collector leaves the model paused at its last saved boundary.
        # The next iteration waits until the selected LimitTime has elapsed.
    return []


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
    paused = threading.Event()
    paused_at = 0.0
    native_time_ms = None
    callback_count = 0
    resumed_boundary = False
    errors = []
    state_loaded = False
    save_requested = False
    save_done = threading.Event()
    job = None
    workspace = None
    recorder = None
    interrupted_before_boundary = False
    try:
        boundary_timeout = float(os.environ.get("SUMO_BOUNDARY_TIMEOUT_SECONDS", "300"))
        if not math.isfinite(boundary_timeout) or boundary_timeout <= 0:
            raise ValueError("SUMO_BOUNDARY_TIMEOUT_SECONDS must be a positive finite number.")
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
        output_variables = list(dict.fromkeys(name for name in [*OUTPUT_VARIABLES, *LIVE_EXTRA_OUTPUTS] if name in available_names))
        history = s.get('history')
        with _lock:
            s['phase'] = 'loading_history' if history else 'reading_initial_sensors'
        following = bool(history and history.get('follow'))
        windows = (_wait_for_collected_windows(s) if following else
                   load_history(s['mapping'], s['interval'], history) if history else [])
        if s['stop'].is_set():
            s.update(status='stopped', phase='cancelled')
            return
        history_index = 0
        replaying = bool(windows)
        if not following:
            s['mode'] = 'history' if replaying else 'live'
        if replaying:
            step_ms = windows[0].duration_ms
            max_ms += sum(window.duration_ms for window in windows)
        target_ms = resume_ms + step_ms
        recorder = open_recorder(project, s['id'], 'history_then_live' if history else 'live',
                                 {'mapping': s['mapping'], 'interval_seconds': s['interval'], 'history': history}, output_variables)
        database_variables = recorder.names if recorder else []
        # First read must succeed before creating a SUMO job.
        values = windows[0].values if replaying else _read_model_inputs(s["mapping"], (history or {}).get("last_inputs"))
        s["input_read_at"] = windows[0].timestamp if replaying else datetime.now(timezone.utc).isoformat()
        with _lock:
            s['input_provenance'] = input_provenance(s['mapping'], values, resume_ms, step_ms, windows[0] if replaying else None)
            record_treatments(s, s['input_provenance'])
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
            nonlocal state_loaded, paused_at
            logging.info("Live SUMO %s job %s: %s", s["id"], job_id, msg)
            with _lock:
                s["last_sumo_message"] = msg
            if msg.startswith("530003"):
                paused_at = time.monotonic()
                paused.set()
            elif msg.startswith(("530002", "530008")):
                paused.clear()
            if msg.startswith("530041"):
                state_loaded = True
            if msg.startswith(("230013", "230046", "230008")):
                # Unknown commands must fail immediately, not wait for DataComm.
                errors.append("SUMO rejected command: " + msg)
                logging.error("Live SUMO %s rejected command; recent commands: %r",
                              s["id"], s.get("sumo_commands", []))
                done.set()
            if msg.startswith("530045") and save_requested:
                save_done.set()
            if ds.sumo.isSimFinishedMsg(msg):
                errors.append("SUMO finished unexpectedly.")
                done.set()
        def sample(job_id, data):
            nonlocal native_time_ms, callback_count
            try:
                ms = data.get("Sumo__Time")
                if ms is None or not math.isfinite(float(ms)):
                    raise ValueError("Missing SUMO simulation time.")
                previous_native_ms = native_time_ms
                native_time_ms = float(ms)
                callback_count += 1
                if native_time_ms < 0 or (previous_native_ms is not None and native_time_ms < previous_native_ms):
                    raise RuntimeError(f"Invalid SUMO local clock: {native_time_ms} ms after {previous_native_ms} ms")
                # Each new native job starts at zero. Only application-facing
                # times include the checkpoint offset, exactly once.
                ms = resume_ms + native_time_ms
                logging.info("Live SUMO %s data callback #%s: native_ms=%s cumulative_ms=%s target_ms=%s offset_ms=%s",
                             s['id'], callback_count, native_time_ms, ms, target_ms, resume_ms)
                if ms > target_ms:
                    raise RuntimeError("SUMO advanced beyond its input boundary.")
                data = {**data, "Sumo__Time": ms}
                with _lock:
                    # Some schedulers emit the loaded checkpoint at start; do not duplicate it.
                    if s["times"] and float(ms)/3600000 <= s["times"][-1]:
                        return
                    s["sim_ms"] = int(ms)
                    sample_time = (history_time(history, ms).isoformat()
                                   if replaying else s["input_read_at"])
                    s.setdefault("sensor_timestamps", [None] * len(s["times"])).append(sample_time)
                    s["times"].append(float(ms)/3600000)
                    for name in dict.fromkeys([*s["mapping"], *output_variables]):
                        s["variables"].setdefault(name, [None] * (len(s["times"]) - 1)).append(float(data.get(name, float("nan"))))
                    # Keep arrays aligned and finite for the plot.
                    if any(not math.isfinite(s["variables"][k][-1]) for k in s["variables"]):
                        raise ValueError("Non-finite SUMO output.")
                if recorder:
                    recorder.submit(int(ms), data, sample_time)
                boundary.set()
            except Exception as exc:
                errors.append(str(exc))
                done.set()
        ds.sumo.message_callback = message
        ds.sumo.datacomm_callback = sample
        commands = [*project_parameter_commands(project),
                    f'load "{initial.as_posix()}";', "maptoic;", "set Sumo__Time 0;",
                    f"set Sumo__StopTime {max_ms - resume_ms};", f"set Sumo__DataComm {step_ms};",
                    "mode dynamic;", *(f"set {k} {v};" for k,v in values.items()),
                    f"set Sumo__LimitTime {target_ms - resume_ms};", "start;"]
        def record_commands(items):
            for command in items:
                logging.info("Live SUMO %s command: %r", s["id"], command)
            with _lock:
                s["sumo_commands"] = (s.get("sumo_commands", []) + list(items))[-80:]

        def send_command(job_id, command):
            if errors:
                raise RuntimeError(errors[0])
            record_commands([command])
            ds.sumo.sendCommand(job_id, command)
            if errors:
                raise RuntimeError(errors[0])

        subscriptions = list(dict.fromkeys(["Sumo__Time", *s["mapping"], *output_variables, *database_variables]))
        startup_script = write_startup_script(folder, commands, subscriptions)
        logging.info("Live SUMO %s: %s subscriptions in %s (%s bytes)",
                     s["id"], len(subscriptions), startup_script, startup_script.stat().st_size)
        schedule_commands = [f'execute "{startup_script.as_posix()}"']
        record_commands([*schedule_commands, *commands])
        with _lock:
            s["phase"] = "scheduling_job"
        # Avoid expanding thousands of follow commands into one native IPC message.
        # Keep all database variables; load their subscriptions from disk instead.
        interval_started = time.perf_counter()
        job = ds.sumo.schedule(dll, commands=schedule_commands,
            variables=["Sumo__Time"],
            jobData={getattr(ds.sumo, "persistent", "persistent"): True})
        if not isinstance(job, int) or job < 0:
            rejected_job, job = job, None
            raise RuntimeError(f"SUMO scheduler rejected the job: {rejected_job}. Last message: {s.get('last_sumo_message', 'none')}")
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
                send_command(job, f'save "{output_state}";')
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

        due = time.monotonic() + s["interval"]
        boundary_started = time.monotonic()
        while not done.is_set():
            if not boundary.wait(0.25):
                if done.is_set():
                    break
                if s["stop"].is_set():
                    # Do not label an unfinished interval as a saved checkpoint.
                    interrupted_before_boundary = True
                    break
                # A paused engine cannot advance merely by waiting longer. Allow
                # one explicit continuation per boundary, after a grace period
                # for an in-flight boundary callback. Never infer completion.
                if (paused.is_set() and state_loaded and not resumed_boundary
                        and native_time_ms is not None and native_time_ms < target_ms - resume_ms
                        and time.monotonic() - paused_at >= 1):
                    resumed_boundary = True
                    paused.clear()
                    logging.warning("Live SUMO %s paused at %s ms before %s ms; continuing once",
                                    s['id'], native_time_ms, target_ms - resume_ms)
                    send_command(job, "continue;")
                    continue
                if time.monotonic() - boundary_started >= boundary_timeout:
                    raise RuntimeError(
                        f"SUMO did not reach LimitTime {(target_ms - resume_ms) / 1000:g} s "
                        f"(cumulative target {target_ms / 1000:g} s) within "
                        f"{boundary_timeout:g} seconds of wall time. Last model time: "
                        f"{s['sim_ms'] / 1000:g} s; initial state loaded: {state_loaded}. "
                        f"Last SUMO message: {s.get('last_sumo_message', 'none received')}. "
                        f"Native callbacks: {callback_count}; last native time (ms): {native_time_ms}; "
                        f"paused: {paused.is_set()}; continuation attempted: {resumed_boundary}. "
                        "Previous completed checkpoint retained. Inspect backend SUMO logs; "
                        "for a known slow model, increase SUMO_BOUNDARY_TIMEOUT_SECONDS.")
                continue
            boundary.clear()
            if not state_loaded:
                raise RuntimeError("SUMO initial state was not confirmed loaded.")
            with _lock:
                current_ms = s["sim_ms"]
            if current_ms < target_ms:
                continue
            if current_ms > target_ms:
                raise RuntimeError("SUMO advanced beyond its input boundary.")
            reached_at = time.perf_counter()
            with _lock:
                s['phase'] = 'writing_simulation_results'
            if recorder:
                recorder.flush()
            flushed_at = time.perf_counter()
            if replaying:
                with _lock:
                    history['completed'] += 1
                    window = windows[history_index]
                    history['last_inputs'] = dict(window.values)
                    history['last_input_provenance'] = dict(window.provenance)
                    history['held_inputs'] = list(window.held_inputs)
                    history['held_at'] = window.timestamp
                    history['held_intervals'] = history.get('held_intervals', 0) + bool(window.held_inputs)
            checkpoint(current_ms)
            saved_at = time.perf_counter()
            with _lock:
                s.setdefault('timings', {}).update(
                    model_seconds=reached_at - interval_started,
                    database_wait_seconds=flushed_at - reached_at,
                    checkpoint_seconds=saved_at - flushed_at,
                    interval_work_seconds=saved_at - interval_started,
                    interval_simulated_seconds=step_ms / 1000)
            logging.info('Live SUMO %s interval %s ms timings: %s', s['id'], current_ms, s['timings'])
            # Replay runs without wall-clock pacing. Live mode waits once per interval.
            if not replaying:
                with _lock:
                    s['phase'] = 'waiting_for_live_clock'
                while time.monotonic() < due and not s["stop"].is_set():
                    s["stop"].wait(max(0, min(0.25, due - time.monotonic())))
            if s["stop"].is_set():
                break
            history_index += 1
            if following and history_index >= len(windows):
                windows = _wait_for_collected_windows(s, done)
                history_index = 0
                if not windows:
                    break
            if replaying and history_index < len(windows):
                window = windows[history_index]
                new_values, step_ms = window.values, window.duration_ms
                s['input_read_at'] = window.timestamp
            else:
                if replaying:
                    # Preserve the same native job/state; start a fresh live clock.
                    replaying = False
                    s['mode'] = 'live'
                    due = time.monotonic() + s['interval']
                    windows = []
                else:
                    due += s['interval']
                step_ms = s['interval'] * dtool.sec
                try:
                    new_values = _read_model_inputs(s["mapping"], values)
                    s["input_read_at"] = datetime.now(timezone.utc).isoformat()
                except Exception as exc:
                    raise RuntimeError("OPC UA unavailable; live simulation stopped: " + str(exc)) from exc
            with _lock:
                s['input_provenance'] = input_provenance(s['mapping'], new_values, current_ms, step_ms,
                                                        windows[history_index] if replaying else None)
                record_treatments(s, s['input_provenance'])
            values = new_values
            interval_started = time.perf_counter()
            for key, value in new_values.items():
                send_command(job, f"set {key} {value};")
            target_ms = current_ms + step_ms
            if following and target_ms >= max_ms:
                max_ms = target_ms + 365 * dtool.day
                send_command(job, f'set Sumo__StopTime {max_ms - resume_ms};')
            send_command(job, f"set Sumo__DataComm {step_ms};")
            boundary_started = time.monotonic()
            resumed_boundary = False
            send_command(job, f"set Sumo__LimitTime {target_ms - resume_ms};")
            with _lock:
                s["phase"] = "replaying_history" if s.get("mode") == "history" else "simulating_live"
        if errors:
            raise RuntimeError(errors[0])
        with _lock:
            s["status"] = "stopped"
            s["phase"] = "stopped_before_boundary" if interrupted_before_boundary else "saved"
    except Exception as exc:
        logging.exception("Live SUMO worker failed")
        with _lock:
            s["status"] = "failed"
            s["phase"] = "failed"
            s["error"] = str(exc)
    finally:
        try:
            persist_processing_records(s)
        except Exception as exc:
            logging.exception('Failed to save sensor processing records')
            with _lock:
                s.update(status='failed', error='Failed to save sensor processing records: ' + str(exc))
        if recorder:
            try:
                recorder.close()
            except Exception as exc:
                logging.exception('SUMO database writer failed')
                with _lock:
                    s.update(status='failed', phase='database_failed', error=str(exc))
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
