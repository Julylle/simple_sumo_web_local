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
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
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
The backend now requires the ASM dependencies in `requirements.txt`, including
a working Assimulo/CVode installation; a full simulation and Docker build must
be validated in an environment with those dependencies.
