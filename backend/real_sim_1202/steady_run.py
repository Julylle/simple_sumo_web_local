# -*- coding: utf-8 -*-
import os
import math
import zipfile
import time
import threading
import logging
import csv
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime

import dynamita.tool as dtool
import dynamita.scheduler as ds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="steady_run.log",
    filemode="a",
)

MODEL_DIR = Path(__file__).resolve().parent
SUMO_PROJECT = str(MODEL_DIR / "real_sim_1202.sumo")
SUMO_STATE = str(MODEL_DIR / "sumo_steady_state.xml")
OUTPUT_VARIABLES = [
    "Sumo__Plant__Effluent1__SNHx",
    "Sumo__Plant__Effluent1__SNOx",
    "Sumo__Plant__Influent__TCOD",
    "Sumo__Plant__Influent__Q",
    "Sumo__Plant__Effluent1__TCOD",
    "Sumo__Plant__CSTR3_10__XVSS",
    "Sumo__MaxAbsDer",
]

def prepare_steady_state(sumo_project_path, out_state_path, wall_run_seconds=3.5*60*60, inputs=None, tolerance=1e-6):
    if not math.isfinite(tolerance) or tolerance <= 0:
        raise ValueError('Convergence tolerance must be positive and finite.')
    inputs = dict(inputs or {})
    with zipfile.ZipFile(sumo_project_path) as archive:
        rows = [line.split('\t') for line in archive.read('variables.var').decode('utf-8-sig').splitlines()]
    available = {row[1] for row in rows if len(row)>1}
    writable = {row[1] for row in rows if len(row)>4 and row[4] in
                ('Parameter', 'SystemParameter', 'Dimension')}
    if set(inputs) - writable or any(not math.isfinite(v) for v in inputs.values()):
        raise ValueError('Invalid sensor inputs for this model.')
    if 'Sumo__MaxAbsDer' not in available:
        raise ValueError('Model does not expose Sumo__MaxAbsDer; convergence cannot be verified.')
    output_variables = [v for v in OUTPUT_VARIABLES if v in available]
    def norm(p):
        return os.path.abspath(p).replace("\\", "/")

    model = norm(os.path.join(CURRENT_WORKING_DIR, "steady_headless.dll"))
    dtool.extract_dll_from_project(sumo_project_path, model)

    ds.sumo.setParallelJobs(1)
    done_event = threading.Event()
    saved_event = threading.Event()
    converged_event = threading.Event()
    last_derivative = None
    consecutive = 0
    solver_errors = []
    result_file = None
    writer = None
    started_at = None
    sample_index = 0
    output_errors = []
    output_lock = threading.Lock()
    phase = "running"
    result_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"steady_results_{datetime.now():%Y%m%d_%H%M}.csv",
    )

    def msg_callback(job, msg):
        logging.info("SUMO job %s: %s", job, msg)
        if msg.startswith(('230046', '230008')) or 'error' in msg.lower():
            solver_errors.append(msg)
            done_event.set()
        if ds.sumo.isSimFinishedMsg(msg):
            done_event.set()
        elif msg.startswith("530045"):
            saved_event.set()

    def data_callback(job, data):
        nonlocal sample_index, last_derivative, consecutive
        # Record exactly the same sample that is printed, including late callbacks.
        with output_lock:
            if output_errors:
                return
            try:
                sample_index += 1
                derivative = data.get('Sumo__MaxAbsDer')
                last_derivative = float(derivative) if derivative is not None else None
                within = last_derivative is not None and math.isfinite(last_derivative) and 0 <= last_derivative <= tolerance
                consecutive = consecutive + 1 if within else 0
                if consecutive >= 3:
                    converged_event.set()
                else:
                    converged_event.clear()
                elapsed = time.monotonic() - started_at
                timestamp = datetime.now().isoformat(timespec="milliseconds")
                values = [data.get(variable) for variable in output_variables]
                writer.writerow([
                    sample_index, timestamp, f"{elapsed:.3f}", job, phase, *values,
                ])
                result_file.flush()
                print(
                    f"Current steady-solver results (job {job}, sample {sample_index}, "
                    f"wall time {elapsed:.3f} s, {phase}):", flush=True,
                )
                for variable, value in zip(output_variables, values):
                    print(f"  {variable}: {value}", flush=True)
            except Exception as exc:
                logging.exception("Failed to record steady-solver output")
                output_errors.append(exc)
                done_event.set()

    ds.sumo.message_callback = msg_callback
    ds.sumo.datacomm_callback = data_callback

    out_state_path = norm(out_state_path)
    job_data = {getattr(ds.sumo, "persistent", "persistent"): True}

    job = None
    parameter_files = None
    try:
        parameter_files = tempfile.TemporaryDirectory(prefix="steady_parameters_", dir=CURRENT_WORKING_DIR)
        parameter_dir = norm(parameter_files.name)
        parameter_script = norm(os.path.join(parameter_dir, "project_parameters.scs"))
        dtool.extract_parameters_from_project(sumo_project_path, parameter_dir, parameter_script)
        result_file = open(result_path, "x", newline="", encoding="utf-8-sig")
        writer = csv.writer(result_file)
        writer.writerow([
            "sample", "recorded_at", "wall_elapsed_seconds", "job", "phase",
            *output_variables,
        ])
        result_file.flush()
        print("Recording solver output to:", result_path)
        started_at = time.monotonic()
        job = ds.sumo.schedule(
            model,
            commands=[f'execute "{parameter_script}";',
                      *[f'set {name} {value:.15g};' for name, value in inputs.items()],
                      "mode steady;", "start;"],
            variables=output_variables,
            jobData=job_data,
        )
        deadline = time.monotonic() + wall_run_seconds
        while not converged_event.is_set() and not done_event.is_set():
            if time.monotonic() >= deadline:
                raise TimeoutError('Steady state did not converge within the time limit; no usable state was saved.')
            converged_event.wait(timeout=min(0.2, max(0, deadline-time.monotonic())))
        if output_errors or solver_errors:
            raise RuntimeError(f'Steady solver failed: {output_errors or solver_errors}')
        # A natural solver finish must also have a finite residual below tolerance.
        if not converged_event.is_set() and not (
            last_derivative is not None and math.isfinite(last_derivative)
            and 0 <= last_derivative <= tolerance
        ):
            raise RuntimeError(f'Solver ended without verified convergence (MaxAbsDer={last_derivative}).')
        if not done_event.is_set():
            ds.sumo.sendCommand(job, "stop;")
            if not done_event.wait(timeout=60):
                raise TimeoutError('SUMO did not confirm stopping after convergence.')
        if output_errors or solver_errors or not (
            last_derivative is not None and math.isfinite(last_derivative)
            and 0 <= last_derivative <= tolerance
        ):
            raise RuntimeError('Final solver state failed convergence validation.')
        with output_lock:
            phase = "converged" 
        logging.info("Convergence verified: MaxAbsDer=%s, tolerance=%s", last_derivative, tolerance)
        # Keep the job alive until SUMO confirms the XML has been written.
        ds.sumo.sendCommand(job, f'save "{out_state_path}";')
        if not saved_event.wait(timeout=60):
            raise TimeoutError("SUMO did not confirm state saving within 60 seconds")
        ET.parse(out_state_path)  # Validate the saved state without exporting another sample.
        if not done_event.is_set():
            ds.sumo.sendCommand(job, "stop;")
            if not done_event.wait(timeout=60):
                raise TimeoutError("SUMO did not confirm stopping within 60 seconds")
        ds.sumo.finish(job)
    finally:
        try:
            ds.sumo.cleanup()
        except Exception:
            logging.exception("cleanup failed")
        ds.sumo.message_callback = None
        ds.sumo.datacomm_callback = None
        if result_file is not None:
            result_file.close()
        if parameter_files is not None:
            parameter_files.cleanup()

    if output_errors:
        raise RuntimeError(f"Failed to record solver output: {output_errors[0]}") from output_errors[0]
    print("Solver output CSV saved:", result_path)
    logging.info("steady state saved at: %s", out_state_path)
    return True


if __name__ == "__main__":
    prepare_steady_state(SUMO_PROJECT, SUMO_STATE, wall_run_seconds=3.5*60*60)

