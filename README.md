# Secure Interactive Model Platform

Starter architecture for an interactive browser UI that changes model parameters, executes a server-side Python model, and displays approved results. A SUMO adapter placeholder is included.

## Run with Docker

```bash
docker compose up --build
```

Open `http://localhost:8080`.

## Development without Docker

Backend:
```bash
cd backend
conda env create --name model-platform --file environment.yml
conda activate model-platform
python -m pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Frontend:
```bash
cd frontend
npm install
npm run dev
```

For local Vite development, add a Vite proxy or point the client to the backend. Docker/Nginx already proxies `/api/`.

## Security model
- Browser never receives Python/SUMO source files or private raw datasets.
- `private/` is mounted read-only into the backend and is not served by Nginx.
- API response uses an explicit output allow-list and downsampling.
- FastAPI interactive documentation is disabled in production starter config.
- Backend is not published to the host in Docker Compose; only Nginx is exposed.
- Any numeric values rendered interactively in a browser can still be inspected by a technically capable user. Do not send genuinely secret values to the browser.

## Before production
Add TLS/HTTPS, authentication/authorization (e.g. institutional SSO/OIDC), CSRF/session strategy as appropriate, rate limits, request-size limits, audit logging, secrets management, network/firewall rules, and asynchronous jobs (Redis + Celery/RQ) for long simulations.

## SUMO migration
Implement `backend/models/sumo_engine.py`, keeping Dynamita/SUMO installation and model files on the server. Then select the engine in `simulation_service.py`. The frontend/API contract can remain unchanged.

## ASM simulation files

The Workspace **Auto-Calibration** page runs `backend/auto_calibration.py` via
`POST /api/auto-calibration`. It uses the same kinetic parameter table and
29-parameter list as Simulation, with separate editable values. Submitted values
seed the optimizer (clipped to the script's search bounds). Successful results
can be downloaded using **Save parameters (.json)** or copied into Simulation's
input table using **Update parameters to Simulation**. Run Simulation again to
update its outputs. Calibration does not automatically overwrite Simulation
inputs, write a pickle, or mutate server defaults.

Simulation's **Model variable time series** also accepts measurement uploads.
Only the `validation` worksheet is needed: `t (min)` plus one or more model
variable columns, such as `S5NH`. Measurements appear as points on the same
elapsed-hour axis as simulated lines, with matching variable colors and shared
Tank/Component filters. This comparison upload does not alter simulation inputs.

Auto-Calibration requires a user-uploaded `.xlsx` workbook matching
`TwoDays_Subiaco_DynamicCali_20260401.xlsx`. The page offers a blank template.
The `validation` sheet holds `t (min)` and tank 1-5 O2, NH4, NO2 and NO3
concentrations; N2O columns are optional. Blank measurements are excluded from
fitting and RMSE. The `dyinput` sheet supplies the uploaded influent, plant-wide
flows and aeration used in every calibration simulation. Times start at zero
and increase strictly; dyinput must cover the measured period.

Uploads are validated and persisted in the input-series volume. The UI previews
measurements and, after calibration, overlays before/after simulations and RMSE
for the selected tank and component. The existing objective fits NH4 and NO3;
other components are displayed for comparison. API calibration uses dynamic
mode, configured initial states and the script's model defaults (MLR ratio 2.5),
not the Simulation page's operating-condition edits. Search bounds remain
separate from literature reference ranges. PyGMO is installed through
`backend/environment.yml`; rebuild the backend after this dependency change.
Requests run synchronously with a one-hour Nginx read timeout.

Auto-Calibration's **Oxygen control** selects DO setpoint, Constant KLa or
Calculated KLa (default). DO setpoint initializes and holds all five tank oxygen
states at the entered values; the three KLa parameters are retained without
optimization. Constant KLa optimizes time-constant coefficients, while Calculated
KLa scales those coefficients with uploaded airflow. Both calculate DO dynamically.
The selected mode is used for fitting and before/after comparisons, and is included
in saved parameter JSON. **Update parameters to Simulation** transfers parameter
values only; Simulation retains its own operating controls.

- `backend/steady_simulation.py`: steady-state simulation entry point.
- `backend/dynamic_simulation.py`: dynamic simulation entry point.
- `backend/models/asm_model.py`: ASM model implementation.
- `backend/config/`: model parameters and shared filesystem paths.
- `private/DataForModel/`: original Excel datasets (mounted read-only in Docker).

Run the scripts from the project root with `python backend/steady_simulation.py`
and `python backend/dynamic_simulation.py`. These standalone simulations
require pandas, scipy, matplotlib, openpyxl and Assimulo in addition to the API
requirements. The optional `visualization.plotting` module is not included;
plots are skipped when it is unavailable.

Dataset paths are independent of the working directory. `PRIVATE_DATA_DIR` can
override the private directory; Docker Compose sets it to `/private`.
The generated steady-state pickle and relative calibration pickle paths use
`backend/`, so both phases share the same state file. The Python engine now calls `run_dynamic_simulation`, refreshing steady biomass
in memory for each request without writing a shared state pickle. API duration
is converted from hours to minutes; DO sets the three aerobic tanks.

Flow, influent COD/NH4 and sludge wasting still come from the workbook in dynamic
mode; the legacy UI flow/COD/NH4/SRT controls are not used by this adapter.
The public output uses tank 5: `S5NH` as NH4, `S5S` as biodegradable COD and
`S5N2O` as dissolved N2O (mg N/L) under the legacy `n2o_index` key. The frontend's
demo/index labels therefore still need updating before interpreting these plots.
The backend installs Python 3.12, NumPy and compiled Assimulo/CVode through
`backend/environment.yml` using conda-forge. Other Python dependencies are in
`backend/requirements.txt`. Docker uses micromamba to create the same environment
and runs a CVode integration check during the build. Installing requirements
with pip alone does not install Assimulo: its PyPI source build is not used.

After changing backend dependencies, rebuild with `docker compose build backend`
and start the services with `docker compose up -d`.

## Interactive MLE configuration

Below the plant map, **Simplify configuration** opens a representative MLE lane
for the 11 parallel lines. Select influent, any of the five reactors, MLR, or SST
to edit parameters. Changes are included in the next Run simulation request;
Reset restores the defaults, and hiding the diagram preserves edits.

Flow is total plant flow, divided by 11 in both steady and dynamic calculations.
Reactor volumes are per lane in cubic metres and converted to litres by the API.
Each reactor has its own DO setpoint; editing the common DO input updates all
three aerobic setpoints. SST exposes RAS ratio and SRT using the existing ideal
separation and volume/SRT wasting approximation, not a settling geometry model.
The drawing is a process schematic based on the supplied layout, not a geographic
mapping of the satellite image. Default volumes come from the existing model.

Backend checks: `python -m unittest discover -s tests -v` from `backend/`.

## Excel time-series boundary conditions

The MLE editor accepts eight independent `.xlsx` inputs: single-lane inflow,
bCOD, NH4-N, RAS, WAS, and airflow for each of Aerobic 1/2/3. Download the
per-input template and replace the values in the first worksheet. Columns are
`time_h` and `value`; time starts at zero and increases strictly. Each input
can have its own irregular time grid. Values are held until the next timestamp;
after the final timestamp the final value remains in use. RAS must be positive.

Water/sludge flows use m3/day per lane, concentrations mg/L, and airflow m3/hour
per lane. Uploaded inflow/RAS/WAS are converted to L/min without dividing by 11;
bCOD is used directly. The built-in workbook fallback converts plant flow to
one lane, and splits its original airflow by 55%/26%/19% as in the existing model.

Uploads preserve the original Excel and normalized JSON in the `input-series`
Docker volume. Browser local storage retains the selected file IDs across
refreshes. Reset leaves file selections intact; Use built-in clears a selection.
Files are not written into the read-only private data mount.

`PythonEngine` resolves selected file IDs and passes the eight profiles into
`GrowthCoupledProduction`. `get_dynamic_inputs(t)` reads each profile at t.
Steady initialization uses the first point of each profile. Dynamic DO is solved
from oxygen transfer, not fixed. The existing calibrated KLa relationship uses
(airflow / built-in reference airflow)^0.86, preserving independent air inputs.
