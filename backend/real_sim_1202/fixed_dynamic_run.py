# -*- coding: utf-8 -*-
import os
from pathlib import Path
import time
import threading
import logging
import csv
import math
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

import dynamita.tool as dtool
import dynamita.scheduler as ds

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="dynamic_run.log",
    filemode="a",
)

MODEL_DIR = Path(__file__).resolve().parent

SUMO_PROJECT = os.path.join(MODEL_DIR, "Cixi Eastern WWTP_20260920.sumo")
# Change the initial state of the dynamic simulation 
INITIAL_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sumo_steady_state.xml")
OUTPUT_STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sumo_dynamic_state.xml")
STATE_SAVE_TIMEOUT_SECONDS = 60

SIM_STOPTIME_SECONDS = 7 # in day
DATA_COMM_SECONDS = 300
# CSV column names are also the model input parameter names.
INPUT_COLUMN = [
    "Sumo__Plant__Influent__param__TKN",
    "Sumo__Plant__Influent__param__TCOD",
]
                
INPUT_CSV = str(MODEL_DIR / 'Sumo__Plant__Influent__param.csv')
OUTPUT_VARIABLES = [
    *(f"Sumo__Plant__{tank}__{pollutant}" for tank in ("Effluent1", "CSTR3_10", "CSTR4_10")
      for pollutant in ("SNHx", "SNOx", "TCOD", "TP")),
    *(f"Sumo__Plant__CSTR{line}_{tank}__SO2" for line in (3, 4) for tank in range(5, 11)),
]



def load_input_rows(path, input_columns=None):
    """Read a fixed CSV snapshot; each value takes effect at its timestamp."""
    columns = INPUT_COLUMN if input_columns is None else list(input_columns)
    rows = []
    with open(path, newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if not {"sim_time_ms", *columns}.issubset(reader.fieldnames or []):
            raise ValueError(f"CSV must contain sim_time_ms and {columns}")
        for line, row in enumerate(reader, 2):
            timestamp = float(row["sim_time_ms"])
            value = {column: float(row[column]) for column in columns}
            if not math.isfinite(timestamp) or any(not math.isfinite(v) or v < 0 for v in value.values()):
                raise ValueError(f"Invalid input at CSV line {line}")
            if timestamp < 0 or timestamp % (DATA_COMM_SECONDS * dtool.sec):
                raise ValueError(f"CSV line {line}: time must align with DataComm")
            if rows and timestamp <= rows[-1][0]:
                raise ValueError(f"CSV line {line}: timestamps must strictly increase")
            rows.append((int(timestamp), value))
    if not rows or rows[0][0] != 0:
        raise ValueError("CSV must start at sim_time_ms = 0")
    return rows


def validate_state_file(path):
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise ValueError(f"Cannot read a complete SUMO state file: {path}: {exc}") from exc
    if root.tag != "systemstate" or len(root) == 0:
        raise ValueError(f"Not a SUMO systemstate file: {path}")


def run_dynamic(sumo_project_path, initial_state_path=INITIAL_STATE, output_state_path=OUTPUT_STATE, output_dir=None, on_sample=None, input_columns=None, extra_variables=()):
    input_columns = list(INPUT_COLUMN if input_columns is None else input_columns)
    if not input_columns or len(input_columns) != len(set(input_columns)):
        raise ValueError("Input columns must be non-empty and unique")
    validate_state_file(initial_state_path)
    output_state_path = os.path.abspath(output_state_path)
    if os.path.normcase(os.path.realpath(initial_state_path)) == os.path.normcase(os.path.realpath(output_state_path)):
        raise ValueError("Initial and output state paths must differ")
    with zipfile.ZipFile(sumo_project_path) as project:
        fields = [line.split("\t") for line in project.read("variables.var").decode("utf-8-sig").splitlines()]
    for column in input_columns:
        input_metadata = next((row for row in fields if len(row) > 4 and row[1] == column), None)
        if input_metadata is None or input_metadata[4] not in {"Parameter", "SystemParameter", "Dimension"}:
            raise ValueError(f"Input variable is missing or not writable: {column}")
    for variable in OUTPUT_VARIABLES:
        if not any(len(row) > 1 and row[1] == variable for row in fields):
            raise ValueError(f"Output variable is missing from model: {variable}")
    input_rows = load_input_rows(INPUT_CSV, input_columns)
    stop_time = round(SIM_STOPTIME_SECONDS * dtool.day)
    input_index = 0
    applied_input = input_rows[0][1]
    first_limit = min(input_rows[1][0], stop_time) if len(input_rows) > 1 else stop_time
    def norm(p):
        return os.path.abspath(p).replace("\\", "/")

    model = norm(os.path.join(output_dir or MODEL_DIR, "dynamic_headless.dll"))
    dtool.extract_dll_from_project(sumo_project_path, model)

    ds.sumo.setParallelJobs(1)
    done_event = threading.Event()
    csv_file = None
    csv_writer = None
    csv_errors = []
    state_loaded = False
    save_started_at = None
    csv_path = os.path.join(
        output_dir or os.path.dirname(os.path.abspath(__file__)),
        f"dynamic_results_{datetime.now():%Y%m%d_%H%M}.csv",
    )

    def msg_callback(job, msg):
        nonlocal state_loaded, save_started_at
        logging.info("SUMO job %s: %s", job, msg)
        if msg.startswith("530041"):
            state_loaded = True
        if msg.startswith(("230046", "230008")):
            csv_errors.append(RuntimeError(f"SUMO rejected input assignment: {msg}"))
            done_event.set()
            return
        if ds.sumo.isSimFinishedMsg(msg):
            if csv_errors or save_started_at is not None:
                return
            try:
                save_started_at = time.monotonic()
                ds.sumo.sendCommand(job, f'save "{output_state_path}";')
            except Exception as exc:
                logging.exception("save command failed")
                csv_errors.append(exc)
                done_event.set()
        elif msg.startswith("530045") and save_started_at is not None:
            # The core has finished writing; only now may the job be closed.
            done_event.set()

    ds.sumo.message_callback = msg_callback

    def data_callback(job, data):
        nonlocal input_index, applied_input
        sim_time_ms = data.get("Sumo__Time")
        if sim_time_ms is None:
            logging.warning("SUMO job %s: missing Sumo__Time in data callback", job)
            time_label = "unknown"
        else:
            time_label = f"{sim_time_ms / dtool.sec:g} s ({sim_time_ms / dtool.day:.6f} days)"
        try:
            if csv_errors:
                return
            if not state_loaded:
                raise RuntimeError("SUMO did not confirm loading the initial state; see dynamic_run.log")
            if sim_time_ms is not None and sim_time_ms > 0:
                for column in input_columns:
                    actual_input = data.get(column)
                    if actual_input is None:
                        raise RuntimeError(f"Missing subscribed input variable in SUMO data: {column}")
                    if not math.isclose(actual_input, applied_input[column], rel_tol=1e-7, abs_tol=1e-8):
                        raise RuntimeError(
                            f"{column} input was not applied at {sim_time_ms} ms: "
                            f"requested={applied_input[column]}, model={actual_input}"
                        )
            csv_writer.writerow([
                job,
                sim_time_ms,
                sim_time_ms / dtool.sec if sim_time_ms is not None else None,
                sim_time_ms / dtool.day if sim_time_ms is not None else None,
                *(applied_input[column] for column in input_columns),
                *(data.get(variable) for variable in OUTPUT_VARIABLES),
            ])
            csv_file.flush()
            if on_sample is not None:
                on_sample(sim_time_ms, data)
            if sim_time_ms is None:
                raise ValueError("Missing Sumo__Time; cannot synchronize CSV input")
            if sim_time_ms >= stop_time:
                # Release the final input boundary so SUMO can emit its finish
                # message and process the subsequent state-save command.
                ds.sumo.sendCommand(job, f"set Sumo__LimitTime {stop_time + DATA_COMM_SECONDS * dtool.sec};")
            if input_index + 1 < len(input_rows) and sim_time_ms < stop_time:
                next_time, next_value = input_rows[input_index + 1]
                if sim_time_ms > next_time:
                    raise RuntimeError(f"Simulation passed input boundary {next_time} ms")
                if sim_time_ms == next_time:
                    input_index += 1
                    next_limit = (
                        min(input_rows[input_index + 1][0], stop_time)
                        if input_index + 1 < len(input_rows) else stop_time
                    )
                    # Update input before releasing the next simulation interval.
                    for column in input_columns:
                        ds.sumo.sendCommand(job, f"set {column} {next_value[column]};")
                    applied_input = next_value
                    ds.sumo.sendCommand(job, f"set Sumo__LimitTime {next_limit};")
                    logging.info("Inputs requested at %s ms: %s", sim_time_ms, next_value)
        except Exception as exc:
            logging.exception("CSV output or input synchronization failed: %s", csv_path)
            csv_errors.append(exc)
            done_event.set()
        for variable in OUTPUT_VARIABLES:
            value = data.get(variable)
            print(f"job: {job}, sim_time: {time_label}, {variable}: {value}")

    # define and use data_callback if want to suggest simulation results on web
    ds.sumo.datacomm_callback = data_callback

    initial_state_path = norm(initial_state_path)
    output_state_path = norm(output_state_path)
    job_data = {getattr(ds.sumo, "persistent", "persistent"): True}

    job = None
    try:
        csv_file = open(csv_path, "x", newline="", encoding="utf-8-sig")
        csv_writer = csv.writer(csv_file)
        csv_writer.writerow([
            "job", "sim_time_ms", "sim_time_seconds", "sim_time_days",
            *(f"{column}__requested_before_sample" for column in input_columns),
            *OUTPUT_VARIABLES,
        ])
        csv_file.flush()
        print("Saving CSV to:", csv_path)
        commands = [
            f'load "{initial_state_path}";',
            "maptoic;",
            "set Sumo__Time 0;",
            f"set Sumo__StopTime {stop_time};",
            f"set Sumo__DataComm {DATA_COMM_SECONDS * dtool.sec};",
            "mode dynamic;",
            *(f"set {column} {applied_input[column]};" for column in input_columns),
            f"set Sumo__LimitTime {first_limit};",
            "start;",
        ]
        job = ds.sumo.schedule(
            model,
            commands=commands,
            # Always subscribe to the input parameter needed for verification,
            # even when it is omitted from the user-facing output columns.
            variables=list(dict.fromkeys(["Sumo__Time", *input_columns, *OUTPUT_VARIABLES, *extra_variables])),
            jobData=job_data,
        )

        while not done_event.is_set():
            if save_started_at is not None and time.monotonic() - save_started_at > STATE_SAVE_TIMEOUT_SECONDS:
                raise TimeoutError("SUMO did not confirm state saving within the timeout")
            done_event.wait(0.2)
        if not csv_errors:
            validate_state_file(output_state_path)
        ds.sumo.finish(job)
    finally:
        try:
            ds.sumo.cleanup()
        except Exception:
            logging.exception("cleanup failed")
        ds.sumo.message_callback = None
        ds.sumo.datacomm_callback = None
        if csv_file is not None:
            csv_file.close()

    if csv_errors:
        raise RuntimeError(f"Simulation CSV output or input synchronization failed: {csv_errors[0]}") from csv_errors[0]
    logging.info("dynamic results saved at: %s", csv_path)
    logging.info("dynamic state saved at: %s", output_state_path)
    return True


if __name__ == "__main__":
    print("Loading initial state:", INITIAL_STATE)
    run_dynamic(SUMO_PROJECT, INITIAL_STATE)
