"""Isolated bridge to the supplied SUMO dynamic runner (stdlib only)."""
import csv
import json
import math
import sys
import time
from uuid import uuid4
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[1] / 'real_sim_1202'
# Use the actual model variable names, including TCOD.
OUTPUTS = {
    f'Sumo__Plant__{tank}__{pollutant}': f'Sumo__Plant__{tank}__{pollutant}'
    for tank in ('Effluent1', 'CSTR3_10', 'CSTR4_10')
    for pollutant in ('SNHx', 'SNOx', 'TCOD', 'TP')
}
OUTPUTS.update({f'Sumo__Plant__CSTR{line}_{tank}__SO2': f'Sumo__Plant__CSTR{line}_{tank}__SO2'
                for line in (3, 4) for tank in range(5, 11)})



def read_result(path, duration_h, input_columns=()):
    with open(path, encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError('SUMO returned no samples')
    times = [float(row['sim_time_seconds']) / 3600 for row in rows]
    sources = {**OUTPUTS, **{column: column for column in input_columns}}
    values = {key: [float(row[column]) for row in rows] for key, column in sources.items()}
    if any(not math.isfinite(v) for series in [times, *values.values()] for v in series):
        raise ValueError('SUMO returned non-finite samples')
    if any(b < a for a, b in zip(times, times[1:])) or times[-1] < duration_h - 1e-6:
        raise ValueError('SUMO did not reach the requested end time')
    indices = sorted({round(i * (len(rows) - 1) / min(499, max(1, len(rows) - 1))) for i in range(min(500, len(rows)))})
    return {'time_h': [times[i] for i in indices],
            'variables': {key: [series[i] for i in indices] for key, series in values.items()},
            'sources': sources, 'input_columns': list(input_columns)}


def main():
    duration_h = float(sys.argv[1])
    sys.dont_write_bytecode = True  # Keep model assets free of generated caches.
    sys.path.insert(0, str(MODEL_DIR.parent))
    from services.sumo_data import parse_input
    sys.path.insert(0, str(MODEL_DIR))
    import fixed_dynamic_run as runner
    runner.SIM_STOPTIME_SECONDS = duration_h / 24
    runner.INPUT_CSV = str(Path.cwd() / 'input.csv' if Path('input.csv').is_file()
                           else MODEL_DIR / 'Sumo__Plant__Influent__param.csv')
    input_columns, _ = parse_input(Path(runner.INPUT_CSV).read_bytes())
    runner.OUTPUT_VARIABLES = list(dict.fromkeys([*input_columns, *OUTPUTS.values()]))
    from database.simulation import open_recorder
    project = MODEL_DIR / 'Cixi Eastern WWTP_20260920.sumo'
    recorder = open_recorder(project, str(uuid4()), 'offline', {'duration_h': duration_h}, runner.OUTPUT_VARIABLES)
    last_report = 0.0

    def report_progress(sim_time_ms, data):
        nonlocal last_report
        if recorder and sim_time_ms is not None:
            recorder.submit(int(sim_time_ms), data)
        now = time.monotonic()
        if sim_time_ms is None or (now - last_report < 0.5 and sim_time_ms < duration_h * 3600000):
            return
        temporary = Path('progress.tmp')
        temporary.write_text(json.dumps({'simulated_h': sim_time_ms / 3600000}, allow_nan=False), encoding='utf-8')
        temporary.replace('progress.json')
        last_report = now

    try:
        runner.run_dynamic(str(MODEL_DIR / 'Cixi Eastern WWTP_20260920.sumo'),
                           str(MODEL_DIR / 'sumo_steady_state.xml'),
                           str(Path.cwd() / 'final_state.xml'), output_dir=str(Path.cwd()), on_sample=report_progress, input_columns=input_columns, extra_variables=recorder.names if recorder else ())
    finally:
        if recorder:
            recorder.close()
    result = read_result(next(Path.cwd().glob('dynamic_results_*.csv')), duration_h, input_columns)
    if recorder:
        result['database_run_id'] = recorder.run_id
    Path('result.json').write_text(json.dumps(result, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
