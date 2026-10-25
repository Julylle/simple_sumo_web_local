# -*- coding: utf-8 -*-
import os
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

CURRENT_WORKING_DIR = os.getcwd()
print(CURRENT_WORKING_DIR)

SUMO_PROJECT = os.path.join(CURRENT_WORKING_DIR, "Cixi Eastern WWTP_20260920.sumo")
SUMO_STATE = os.path.join(CURRENT_WORKING_DIR, "sumo_steady_state.xml")
OUTPUT_VARIABLES = [
    "Sumo__Plant__Effluent1__SNHx",
    "Sumo__Plant__Effluent1__SNOx",
    "Sumo__Plant__Influent__TCOD",
    "Sumo__Plant__Influent__Q",
    "Sumo__Plant__Effluent1__TCOD",
    "Sumo__Plant__CSTR3_10__XVSS",
    "Sumo__MaxAbsDer",
]

def prepare_steady_state(sumo_project_path, out_state_path, wall_run_seconds=60):
    def norm(p):
        return os.path.abspath(p).replace("\\", "/")

    model = norm(os.path.join(CURRENT_WORKING_DIR, "steady_headless.dll"))
    dtool.extract_dll_from_project(sumo_project_path, model)

    ds.sumo.setParallelJobs(1)
    done_event = threading.Event()
    saved_event = threading.Event()
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
        if ds.sumo.isSimFinishedMsg(msg):
            done_event.set()
        elif msg.startswith("530045"):
            saved_event.set()

    def data_callback(job, data):
        nonlocal sample_index
        # Record exactly the same sample that is printed, including late callbacks.
        with output_lock:
            if output_errors:
                return
            try:
                sample_index += 1
                elapsed = time.monotonic() - started_at
                timestamp = datetime.now().isoformat(timespec="milliseconds")
                values = [data.get(variable) for variable in OUTPUT_VARIABLES]
                writer.writerow([
                    sample_index, timestamp, f"{elapsed:.3f}", job, phase, *values,
                ])
                result_file.flush()
                print(
                    f"Current steady-solver results (job {job}, sample {sample_index}, "
                    f"wall time {elapsed:.3f} s, {phase}):", flush=True,
                )
                for variable, value in zip(OUTPUT_VARIABLES, values):
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
            *OUTPUT_VARIABLES,
        ])
        result_file.flush()
        print("Recording solver output to:", result_path)
        started_at = time.monotonic()
        job = ds.sumo.schedule(
            model,
            commands=[f'execute "{parameter_script}";', "mode steady;", "start;"],
            variables=OUTPUT_VARIABLES,
            jobData=job_data,
        )
        finished = done_event.wait(timeout=wall_run_seconds)
        if output_errors:
            raise RuntimeError(f"Failed to record solver output: {output_errors[0]}") from output_errors[0]
        with output_lock:
            phase = "finalizing"
        logging.info("Steady run wait ended: %s; convergence not verified",
                     "solver_ended" if finished else "time_limit")
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
