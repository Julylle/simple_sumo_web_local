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
from pathlib import Path
import sys


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    filename="steady_run.log",
    filemode="a",
)

MODEL_DIR = Path(__file__).resolve().parent
SUMO_PROJECT = str(MODEL_DIR / "real_sim_1202_test.sumo")
SUMO_STATE = str(MODEL_DIR / "sumo_steady_state.xml")
OUTPUT_VARIABLES = [
    "Sumo__Plant__Effluent1__SNHx",
    "Sumo__Plant__Effluent1__SNOx",
    "Sumo__Plant__Influent__TCOD",
    "Sumo__Plant__Influent__Q",
    "Sumo__Plant__Effluent1__TCOD",
    "Sumo__Plant__CSTR3_10__XVSS",
    "Sumo__Plant__CSTR3_10__TCOD",
    "Sumo__MaxAbsDer",
]

def prepare_steady_state(sumo_project_path, out_state_path, wall_run_seconds=5*60*60, inputs=None, tolerance=100, work_dir=None, timeout_state_path=None):
    import dynamita.tool as dtool
    import dynamita.scheduler as ds
    runtime_dir = str(Path(work_dir or os.getcwd()).resolve())
    if not math.isfinite(wall_run_seconds) or wall_run_seconds <= 0:
        raise ValueError("Solver time limit must be positive and finite.")
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

    model = norm(os.path.join(runtime_dir, "steady_headless.dll"))
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
        f"steady_results_{datetime.now():%Y%m%d_%H%M%S_%f}.csv",
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
        parameter_files = tempfile.TemporaryDirectory(prefix="steady_parameters_", dir=runtime_dir)
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
                if timeout_state_path is None:
                    raise TimeoutError('Steady state did not converge within the time limit; no usable state was saved.')
                if output_errors or solver_errors or sample_index == 0:
                    raise RuntimeError('Cannot save timeout state: solver errors or no received samples.')
                recovery = Path(timeout_state_path).resolve()
                if recovery in (Path(out_state_path).resolve(), Path(sumo_project_path).resolve()):
                    raise ValueError('Timeout state must have a separate output path.')
                # Stop first so the saved state is stable; retain the native job until save confirmation.
                with output_lock:
                    phase = "timeout_unconverged"
                ds.sumo.sendCommand(job, "stop;")
                if not done_event.wait(timeout=60):
                    raise TimeoutError('SUMO did not confirm stopping; timeout state was not saved.')
                if output_errors or solver_errors:
                    raise RuntimeError('SUMO reported an error while stopping; timeout state was not saved.')
                from uuid import uuid4
                recovery.parent.mkdir(parents=True, exist_ok=True)
                staging = recovery.with_name(f'.{recovery.stem}-{uuid4().hex}.pending.xml')
                try:
                    saved_event.clear()
                    ds.sumo.sendCommand(job, f'save "{norm(staging)}";')
                    if not saved_event.wait(timeout=60):
                        raise TimeoutError('SUMO did not confirm timeout state saving within 60 seconds.')
                    if solver_errors or output_errors:
                        raise RuntimeError('SUMO reported an error while saving timeout state.')
                    root = ET.parse(staging).getroot()
                    if root.tag != 'systemstate' or not len(root):
                        raise ValueError('Timeout state is not a non-empty SUMO systemstate.')
                    os.replace(staging, recovery)
                finally:
                    staging.unlink(missing_ok=True)
                ds.sumo.finish(job)
                message = (f'Steady solver timed out. UNCONVERGED state saved: {recovery}; '
                           f'MaxAbsDer={last_derivative}, tolerance={tolerance}. '
                           'The converged steady-state output was not replaced.')
                print(message, flush=True)
                logging.warning(message)
                raise TimeoutError(message)
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


def main(argv=None):
    """Read the same fresh sensor inputs as the web steady-state workflow."""
    import argparse
    import asyncio
    import json
    from urllib.request import urlopen
    from uuid import uuid4

    # Allows `python backend/real_sim_1202/steady_run.py` from any directory.
    backend = MODEL_DIR.parent
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    parser = argparse.ArgumentParser(description='Compute SUMO steady state from a fresh KEPServer snapshot.')
    parser.add_argument('--project', type=Path, default=Path(SUMO_PROJECT))
    parser.add_argument('--output', type=Path, default=Path(SUMO_STATE))
    parser.add_argument('--endpoint', help='Override KEPSERVER_OPC_URL for this run.')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--mapping', type=Path, help='JSON object mapping SUMO parameter names to full OPC UA node IDs.')
    source.add_argument('--live-url', help='Backend base URL to obtain the current live/checkpoint mapping; sensor values are freshly read.')
    parser.add_argument('--tolerance', type=float, default=100)
    parser.add_argument('--timeout-hours', type=float, default=5)
    args = parser.parse_args(argv)
    if not math.isfinite(args.tolerance) or args.tolerance <= 0:
        parser.error('--tolerance must be positive and finite.')
    if not math.isfinite(args.timeout_hours) or args.timeout_hours <= 0:
        parser.error('--timeout-hours must be positive and finite.')
    from services.kepserver import read_snapshot
    from services.model_inputs import scale_model_inputs
    from services.sensor_inputs import SENSOR_COLUMNS
    from database.catalog import load_mapping
    if args.endpoint:
        os.environ['KEPSERVER_OPC_URL'] = args.endpoint
    if args.mapping:
        mapping = json.loads(args.mapping.read_text(encoding='utf-8-sig'))
    elif args.live_url:
        with urlopen(args.live_url.rstrip('/') + '/api/sumo/live/status', timeout=10) as response:
            status = json.load(response)
        mapping = status.get('mapping') or (status.get('checkpoint') or {}).get('mapping')
        if not mapping:
            raise ValueError('The backend has no live/checkpoint mapping. Use --mapping or the default presets.')
    else:
        _, _, rows = load_mapping()
        mapping = {row['SumoName']: 'ns=2;s=' + row['OpcTag'] for row in rows if row['SumoName'] in SENSOR_COLUMNS}
        if set(mapping) != set(SENSOR_COLUMNS):
            raise ValueError('Default CSV does not cover every web sensor mapping.')
    if (not isinstance(mapping, dict) or not 1 <= len(mapping) <= 40 or
        any(k not in SENSOR_COLUMNS or not isinstance(v, str) or not v.strip() for k, v in mapping.items())):
        raise ValueError('Provide 1–40 valid web sensor mappings.')
    project = args.project.resolve()
    output = args.output.resolve()
    if project == output:
        raise ValueError('Output state must not overwrite the SUMO project.')
    with zipfile.ZipFile(project) as archive:
        fields = [line.split('\t') for line in archive.read('variables.var').decode('utf-8-sig').splitlines()]
    writable = {row[1] for row in fields if len(row) > 4 and row[4] in ('Parameter', 'SystemParameter', 'Dimension')}
    if set(mapping) - writable:
        raise ValueError('SUMO inputs not writable: ' + ', '.join(sorted(set(mapping) - writable)))
    async def fresh_snapshot():
        return await asyncio.wait_for(read_snapshot(mapping), timeout=30)
    readings = asyncio.run(fresh_snapshot())
    values = scale_model_inputs(readings)
    if set(values) != set(mapping):
        raise ValueError('Incomplete sensor snapshot; steady-state calculation was not started.')
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = output.parent / f'steady_sensor_inputs_{datetime.now():%Y%m%d_%H%M%S_%f}.json'
    snapshot.write_text(json.dumps({'project': str(project), 'mapping': mapping,
        'sensor_read_at': max(r['timestamp'] for r in readings), 'readings': readings,
        'values': values, 'tolerance': args.tolerance}, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    print(f'Read {len(values)} fresh inputs. Snapshot: {snapshot}', flush=True)
    for name, value in values.items():
        print(f'  {name} = {value:.15g}', flush=True)
    recovery = output.with_name(f'{output.stem}_unconverged_{datetime.now():%Y%m%d_%H%M%S_%f}.xml')
    pending = output.with_name(f'.{output.stem}-{uuid4().hex}.pending.xml')
    try:
        # Keep native DLLs isolated; cleanup may be delayed by Windows DLL handles.
        with tempfile.TemporaryDirectory(prefix='sumo_steady_', ignore_cleanup_errors=True) as runtime:
            prepare_steady_state(str(project), str(pending),
                wall_run_seconds=args.timeout_hours * 3600, inputs=values,
                tolerance=args.tolerance, work_dir=runtime, timeout_state_path=recovery)
        root = ET.parse(pending).getroot()
        if root.tag != 'systemstate' or not len(root):
            raise ValueError('Solver did not produce a non-empty SUMO systemstate.')
        os.replace(pending, output)
    finally:
        pending.unlink(missing_ok=True)
    print(f'Converged steady state saved: {output}', flush=True)


if __name__ == '__main__':
    main()
