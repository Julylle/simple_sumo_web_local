# Standalone steady simulation with fresh sensor inputs

From the repository root, in the Windows Python environment containing SUMO/DTool and `asyncua`:

```powershell
# Read current sensors once, scale as on the web, and hold inputs until convergence.
python .\backend\real_sim_1202\steady_run.py

# Override the OPC UA endpoint if it is not the same computer.
python .\backend\real_sim_1202\steady_run.py --endpoint opc.tcp://YOUR-KEPSERVER:49320

# Use mappings from the active web run (or its latest saved checkpoint).
# This retrieves mapping configuration only; sensor values are freshly read.
python .\backend\real_sim_1202\steady_run.py --live-url http://127.0.0.1:8000

# Choose another output file instead of replacing the built-in initial state.
python .\backend\real_sim_1202\steady_run.py --output D:\SUMO\new_steady_state.xml
```

Defaults: project and output XML in this script's own directory, tolerance `1e-6`, maximum wall time 3.5 hours. Paths work when launched from the repository root, backend directory, or model directory. Use `--project`, `--tolerance` and `--timeout-hours` to override. `KEPSERVER_OPC_URL` is also supported. `.env` is not loaded automatically: if needed, dot-source `backend/scripts/load-database-env.ps1` before running. MySQL is not required for this command.

The default 40 mappings match the web's prefilled 12 influent, 24 DO and 4 control mappings, selected from `backend/database/cx_opcua1124.csv`. A changed browser-only draft is not visible to the script. Use `--mapping mapping.json` for a JSON object of SUMO parameter names to full `ns=...;s=...` node IDs, or `--live-url` after starting the web run. `--live-url` cannot read an unstarted browser draft and does not stop/change the live run.

A fresh snapshot uses the same `read_snapshot` and `scale_model_inputs` functions as web steady calculation, with the same 30-second acquisition timeout. Flow scaling is applied exactly once. Inputs are held constant throughout the steady solve, rather than continually updated. Any missing/failed reading aborts before solving; there is no fallback to older data or project defaults.

Raw readings, mapping, UTC read time and applied inputs are saved to a timestamped `steady_sensor_inputs_*.json` alongside the chosen output XML. Solver observations go to a timestamped `steady_results_*.csv` in the script directory, and the terminal. Convergence follows the existing web solver: three consecutive MaxAbsDer readings below tolerance, or a natural solver finish with a verified residual below tolerance. Only a successfully saved non-empty systemstate replaces the requested XML; failures retain the previous output. DLLs use an isolated temporary directory to avoid reusing a loaded DLL on Windows.

The web's existing `prepare_steady_state(..., inputs=...)` API remains unchanged in behavior. Directly invoking that Python function still uses the inputs supplied by its caller; fresh KEPServer acquisition is performed by this script's CLI entry point. Do not launch many steady jobs concurrently on a single SUMO license.
