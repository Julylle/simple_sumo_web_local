"""Isolated bridge to the supplied SUMO dynamic runner (stdlib only)."""
import csv
import json
import math
import sys
import time
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parents[1] / 'real_sim_1202'
OUTPUTS = {
    'influent_nh4': 'Sumo__Plant__Influent__SNHx',
    'influent_tkn': 'Sumo__Plant__Influent__TKN',
    'influent_cod': 'Sumo__Plant__Influent__TCOD',
    'effluent_nh4': 'Sumo__Plant__Effluent1__SNHx',
    'effluent_nox': 'Sumo__Plant__Effluent1__SNOx',
}


def read_result(path, duration_h):
    with open(path, encoding='utf-8-sig', newline='') as source:
        rows = list(csv.DictReader(source))
    if not rows:
        raise ValueError('SUMO returned no samples')
    times = [float(row['sim_time_seconds']) / 3600 for row in rows]
    values = {key: [float(row[column]) for row in rows] for key, column in OUTPUTS.items()}
    if any(not math.isfinite(v) for series in [times, *values.values()] for v in series):
        raise ValueError('SUMO returned non-finite samples')
    if any(b < a for a, b in zip(times, times[1:])) or times[-1] < duration_h - 1e-6:
        raise ValueError('SUMO did not reach the requested end time')
    indices = sorted({round(i * (len(rows) - 1) / min(499, max(1, len(rows) - 1))) for i in range(min(500, len(rows)))})
    return {'time_h': [times[i] for i in indices],
            'variables': {key: [series[i] for i in indices] for key, series in values.items()}}


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
    last_report = 0.0

    def report_progress(sim_time_ms, data):
        nonlocal last_report
        now = time.monotonic()
        if sim_time_ms is None or (now - last_report < 0.5 and sim_time_ms < duration_h * 3600000):
            return
        temporary = Path('progress.tmp')
        temporary.write_text(json.dumps({'simulated_h': sim_time_ms / 3600000}, allow_nan=False), encoding='utf-8')
        temporary.replace('progress.json')
        last_report = now

    runner.run_dynamic(str(MODEL_DIR / 'Cixi Eastern WWTP_20260920.sumo'),
                       str(MODEL_DIR / 'sumo_steady_state.xml'),
                       str(Path.cwd() / 'final_state.xml'), output_dir=str(Path.cwd()), on_sample=report_progress, input_columns=input_columns)
    result = read_result(next(Path.cwd().glob('dynamic_results_*.csv')), duration_h)
    Path('result.json').write_text(json.dumps(result, allow_nan=False), encoding='utf-8')


if __name__ == '__main__':
    main()
