# MySQL time-series database

The database `sumo_timeseries` exposes two SQL views named exactly **`raw data`** and **`sumo simulation`**. SQL identifiers with spaces must be enclosed in backticks. They are datasets in one database, backed by normalized catalog and time-series tables; no new table or file is created per variable or per LimitTime.

## Scope and provenance

`cx_opcua1124.csv` is copied from `Julylle/Sumo_web/demo_MLE/cx_opcua1124.csv` (retrieved 2026-10-25). All 73 rows and all 12 columns are preserved, including blank comments, tag spaces, duplicated OPC tags, original unit/type strings, Scaling and Offset. The complete CSV and its SHA-256 are versioned in `mapping_versions`; each raw row references its immutable catalog row. A changed CSV creates a new mapping version, so previous readings retain their original mapping/scaling.

The collector reads every unique tag once per cycle and stores a reading for **every mapping row**. An OPC tag used by multiple SUMO variables therefore generates multiple linked rows with the same read timestamp and source value. STRING lab values stay strings in `raw_value`; parseable scalar values are also available as `numeric_value`. Arrays stay JSON arrays. Bad quality and disconnected/unreadable tags produce quality/error records rather than zero values or missing rows. This collector never writes to OPC UA.

Raw values are never scaled in place. The separate `scaled_value` follows the existing project convention `(raw - Offset) / Scaling`; all offsets in the supplied CSV are zero. CSV metadata alone does not specify the scaling direction: verify this convention on site before using the scaled column for a new mapping. Failed conversions and bad-quality values have NULL scaled values. This feature does not change the live solver's existing input selection or conversion rules.

## Install and initialize on Windows

Run from the repository root in the Python environment used by the SUMO backend (Python 3.11+). MySQL 8.4 is the deployment target.

```powershell
# Create configuration once; edit passwords and the KEPServer endpoint before use.
Copy-Item .\backend\database\.env.example .\.env
notepad .\.env

# Load settings into this PowerShell process; passwords are not printed.
. .\backend\scripts\load-database-env.ps1
python -m pip install -r .\backend\database\requirements.txt

# Optional: provision MySQL locally with a persistent Docker named volume.
# Skip this command if using an existing MySQL server/database.
docker compose -f docker-compose.mysql.yml up -d --wait

Set-Location backend
python -m database init
python -m database catalog --project '.\real_sim_1202\Cixi Eastern WWTP_20260920.sumo'

# Run ONE collector process, independently of any browser or SUMO simulation.
python -m database.collector
```

For an existing server, have an administrator create `sumo_timeseries` and grant the application user privileges on that database. `python -m database init --create-database` can create it if the supplied account has permission. Initialization is repeatable and nondestructive. Do not point it at an unrelated existing schema with the same table names. Use `MYSQL_PORT=3307` in `.env` if port 3306 is already occupied; this also changes the optional Docker host port. Do not replace an existing MySQL installation.

In a second PowerShell window, load the same environment **before launching the usual backend**:

```powershell
. .\backend\scripts\load-database-env.ps1
Set-Location backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 1
```

If you use another port/start script, keep that existing command and make sure it inherits these environment variables. `SUMO_MYSQL_ENABLED=1` enables recording in both the realtime worker and the web offline worker. The standalone `steady_run.py` is not a time-series collector. With the flag unset/0, direct live and offline modes do not require MySQL recording. Historical data → Live always records its outputs to the history database, regardless of this flag. Credentials are read from environment variables; `.env` and raw spool files are gitignored. If the offline worker uses a different `SUMO_PYTHON`, install the database requirements in that Python environment as well.

Use the OPC namespace URI when possible (`KEPSERVER_NAMESPACE_URI`); otherwise the supplied default is `ns=2`. OPC node IDs are constructed as `ns=<index>;s=<OpcTag>` without trimming or altering the tag. Only no-security/anonymous OPC UA connections are configured here, matching the existing project; server-specific certificate/user authentication requires additional configuration.

## SUMO variables and timestamps

The recorder parses the **actual selected `.sumo` project's `variables.var`**, preserves its field metadata, and subscribes to all `StateVariable` and `AccumulatedStateVariable` entries, plus existing dashboard outputs (including derived TCOD). The bundled project contains 3,549 + 55 = **3,604 formal state variables**. It supports uploaded models and arrays without flattening or casting arrays to floats. Missing/non-finite values are explicitly marked and raw JSON preserved. The full catalog is stored in `sumo_variables`; database variables are not all sent to the browser or added to the dashboard CSV.

`SystemState` is a different SUMO category containing about 152,359 derived/internal entries in this project. Set `SUMO_DB_INCLUDE_SYSTEM_STATE=1` **before starting a new run** to additionally subscribe to every one. This can greatly increase Scheduler payloads, write time and disk use; native SUMO capacity must be verified on the licensed host. Do not change this scope while resuming the same run; start a new run instead.

Every live DataComm sample and every offline DataComm sample is stored at the model's communication interval. Live sampling follows LimitTime; offline sampling follows the runner's DataComm setting. Each run is linked to its model SHA-256 and configuration. Live checkpoint resume keeps the run ID; `(run_id, simulated_ms)` uniqueness prevents duplicate history. If an interval is recomputed after an interrupted checkpoint save, its timestamp and values are transactionally replaced by the recomputed result. Offline runs get independent database UUIDs, exposed as `database_run_id` in the API result. Simulation time and real time remain separate:

- `simulated_ms` / `time_h`: model clock.
- `sensor_read_at`: acquisition-completion time for a direct live input snapshot; the historical/collected interval's model timestamp in Historical data → Live; NULL for offline runs.
- `acquired_at`: database writer observation time.
- Raw data additionally includes OPC source/server timestamps, status code, and collector acquisition time.

Base-table DATETIME values and `*_utc` view columns remain **UTC**. The `raw data` and `sumo simulation` display views expose local-time timestamps after initialization or the `local-time` update. Do not interpret simulated hours as wall-clock time. Raw collection and SUMO input reads are independent, so their timestamps are not guaranteed to be identical. Existing historical runs are not backfilled automatically.

## Durability and capacity

MySQL writes are incremental and transactional. No accumulated history is rewritten at each interval. The Docker named volume persists across restarts; **do not run `docker compose down -v`** if you need to retain the database.

The raw collector defaults to 60 seconds (`RAW_SAMPLE_SECONDS`). A small fsynced pending-batch file is retained across failed DB writes and collector restarts; retry is idempotent by batch UUID. While the database is unavailable, acquisition pauses with an error rather than creating an unbounded file backlog. This creates an explicit acquisition gap; it does not reconstruct samples from downtime. Run only one collector per spool directory. If changing CSV with an outstanding batch, restore the original CSV and drain that batch first.

The SUMO writer has a bounded queue of eight snapshots and uses a separate thread so MySQL I/O does not block native callbacks. Live worker flushes the queue before checkpointing/releasing the next interval. A database error/full queue stops the simulation with an error instead of silently dropping values. The previous successful checkpoint remains recoverable. A crash before an interval is committed may require resuming that interval. The database is not a replacement for the model-state checkpoint.

Storage remains cumulative: at 73 rows/minute raw data adds 105,120 rows/day. At 3,604 variables every five minutes, formal SUMO states add about 1.04 million value rows/day, plus dashboard outputs. SystemState inclusion raises this dramatically. No automatic deletion is enabled. Monitor disk usage and choose an archive/retention policy before long unattended operation. Tables are indexed by variable/time and run/time; queries should always restrict time/run and use LIMIT. Back up the MySQL volume/database separately.

## Query examples

```sql
SELECT * FROM `raw data`
WHERE variable = 'Sumo__Plant__Influent__param__Q'
  AND acquired_at_utc >= UTC_TIMESTAMP() - INTERVAL 1 DAY
ORDER BY acquired_at DESC LIMIT 100;

SELECT run_id, simulated_ms, sensor_read_at, variable, value_json, numeric_value
FROM `sumo simulation`
WHERE run_id = 'YOUR-RUN-UUID'
  AND variable = 'Sumo__Plant__CSTR3_10__TCOD'
ORDER BY simulated_ms LIMIT 1000;

SELECT `row_number`,sumo_name,opc_tag,metadata FROM raw_variables ORDER BY id;
SELECT category,COUNT(*) FROM sumo_variables GROUP BY category;
SELECT run_id,run_mode,model_sha,started_at FROM sumo_runs ORDER BY started_at DESC;
SELECT table_name,ROUND((data_length+index_length)/1024/1024,1) AS size_mb
FROM information_schema.tables WHERE table_schema = 'sumo_timeseries';
```

## Validation

Run `python -m pytest tests/test_timeseries_database.py tests/test_live_checkpoint.py tests/test_live_flow_scaling.py`. `tests/test_timeseries_mysql.py` is an opt-in real MySQL integration test: set `MYSQL_TEST_ENABLED=1` with a **disposable, initialized test database** to run it. Native Scheduler subscriptions and the actual KEPServer tags still require validation on the Windows SUMO host. No running database or live sensor connection is provisioned merely by pulling this repository.

## Historical data → Live result recording

This mode always enables the SUMO result writer, even when `SUMO_MYSQL_ENABLED`
is unset or 0. Its output destination is the same database as its historical
input source: `sumo_web_database` by default, or `SUMO_HISTORY_DATABASE`. The
selected database is preserved in the checkpoint. `MYSQL_DATABASE` continues to
control direct-live/offline output recording and the separate raw collector.
Ensure the raw collector is configured to write into the history database too.

The selected project's state-variable catalog and dashboard outputs are written
after every DataComm sample, both during accelerated replay and after catching
up. Data goes to `sumo_runs`, `sumo_samples`, and `sumo_values` with catalog data
in `sumo_models`/`sumo_variables`; query it through the existing `sumo simulation`
view. Raw sensor tables are not overwritten or duplicated by replay.

The raw collector collects sensors independently; the backend's simulation
recorder collects actual SUMO callbacks and commits them on a separate thread.
Each interval flushes its writes before saving the checkpoint or advancing.
A database error stops the model instead of dropping results. The same `run_id`
continues across replay, live following and checkpoint resume; `(run_id,
simulated_ms)` makes retries idempotent. `sensor_read_at` preserves the simulated
historical timestamp, while `acquired_at` is the actual recording time.

The database schema must already be initialized and the backend account must
have result-table/catalog write privileges. No prior unrecorded results are
backfilled merely by updating the application.

```sql
SELECT run_id, time_h, sensor_read_at, acquired_at, variable, numeric_value
FROM sumo_web_database.`sumo simulation`
WHERE run_id = 'YOUR-RUN-UUID'
ORDER BY simulated_ms, variable LIMIT 1000;
```

## Align database displays with the local computer and web plots

Canonical UTC storage in `raw_data` and `sumo_samples` remains unchanged. This
prevents double-shifting old records and keeps indexed history queries correct.
The user-facing `raw data` and `sumo simulation` views convert their timestamp
columns into the configured local timezone and retain explicitly named
`acquired_at_utc`, `sensor_read_at_utc`, and raw source/server `*_utc` columns.
Both views expose `plot_time` as `YYYY-MM-DD HH:mm:ss.SSS`, matching web hover
labels (milliseconds are truncated from database microseconds, just as JS Date
does), plus `display_timezone` for verification. Offline samples with no sensor
time retain NULL `plot_time` rather than inventing a historical timestamp.

For the browser computer in **Asia/Shanghai**, run once from the project root:

```powershell
. .\backend\scripts\load-database-env.ps1
Push-Location backend
python -m database local-time --database sumo_web_database --timezone "+08:00"
Pop-Location
```

This replaces only the two views, including how existing rows are displayed;
it does not rewrite stored timestamps. It requires CREATE VIEW privileges.
Set `SUMO_DISPLAY_TIMEZONE=+08:00` in the database environment file to preserve
this choice during future `database init` calls. Without a setting or CLI
argument, initialization uses the backend computer's current UTC offset.
For a browser on another timezone, configure these views to that same timezone.
For locations with DST, use an IANA zone (e.g. `Australia/Sydney`) and load the
MySQL timezone tables first; a fixed offset is only suitable when the offset is
constant over the data period. Unsupported named zones fail explicitly.

The web sends local history selections as timezone-qualified UTC timestamps;
backend queries remain in UTC. For a five-minute Shanghai interval from 08:00
to 08:05, raw inputs occupy **[08:00,08:05)** and its simulated endpoint is
**08:05**. Query the local display views with local bounds:

```sql
SELECT acquired_at, acquired_at_utc, plot_time, variable, numeric_value
FROM `raw data`
WHERE acquired_at >= '2026-10-26 08:00:00'
  AND acquired_at <  '2026-10-26 08:05:00';

SELECT sensor_read_at, sensor_read_at_utc, plot_time, variable, numeric_value
FROM `sumo simulation`
WHERE run_id = 'YOUR-RUN-UUID'
  AND sensor_read_at >  '2026-10-26 08:00:00'
  AND sensor_read_at <= '2026-10-26 08:05:00';
```

Use `sensor_read_at` / `plot_time` to compare simulated history with chart dates.
`acquired_at` on simulation rows is when the replay result was actually written,
so it is intentionally different from the simulated historical date. For large
queries, use UTC bounds on the indexed base tables. Live preview sensors are
sampled independently from the database collector; timestamps share a time
basis but samples need not represent the exact same acquisition cycle.

### Large model subscriptions

Live and Historical → Live sessions write initialization commands and one
`follow` command per recorded variable to a job-local `startup.scs`. Scheduler
receives only a short `execute` command and the `Sumo__Time` subscription; the
script adds the full input/output/state catalog before `start`. This avoids
sending the complete state catalog as a single large Scheduler subscription
argument. No state variables are removed from database recording. The script
remains available until the native job is cleaned up.

This addresses a suspected command-transport truncation path behind
`230013 Unknown command "fol"`; native SUMO validation is still required on the
Windows installation. Error diagnostics include the executed script path.

### Temporary Windows background collector (no administrator password)

From the project root in an ordinary PowerShell window:

```powershell
conda activate sumo_web
.\startCollectorBackground.ps1
```

The launcher loads `backend/database/.env`, checks the existing spool lock,
then starts a hidden Python process and prints its PID and unique log paths.
If the lock is occupied or cannot be checked, it starts nothing and leaves the
existing collector untouched. It does not hide or detach an already running
foreground collector. Keep that terminal open until you can stop it with Ctrl+C,
then rerun the launcher. Logs from previous launches are not overwritten.

Watch the printed `.error.log` path with `Get-Content -LiteralPath "..." -Tail 20
-Wait`; Python's normal `raw data: stored ...` messages also use that log. A live
PID alone does not confirm successful database writes. Closing the launcher
terminal does not stop the new process. Logout, reboot or a process crash will
not automatically restart it. Keep `runCollector.ps1` for Task Scheduler use.

For a different Conda installation, activate `sumo_web` there, or explicitly pass
`-PythonPath 'C:\path\to\envs\sumo_web\python.exe'`.

To stop the collector from the project root:

```powershell
.\stopCollector.ps1
```

This targets only `python.exe`/`pythonw.exe` command lines running
`-m database.collector`. It leaves SUMO and web-server processes alone. If several
collectors are found, it lists them and stops none until you select a PID:

```powershell
.\stopCollector.ps1 -CollectorProcessId 12345
```

Use `-WhatIf` to preview the target. Run under the account that launched the
collector; an inaccessible command line cannot be identified safely. The script
terminates the process (not a graceful completion of the current sample), waits
up to five seconds for exit, and does not delete logs, spool files or database
records. Windows releases the collector lock on exit. A configured Task Scheduler
restart policy may start the collector again; disable that task first if needed.

### Missing historical inputs and lag diagnostics

Historical → Live now carries forward the previous simulated interval's input
for each variable with no good numeric reading in a completed interval. Other
variables use their new interval means. Empty intervals still advance the model
by LimitTime; model time is never skipped. A subsequent valid reading replaces
the held value. Raw sensor records are never filled or rewritten.

The previous inputs are stored in model units in each completed checkpoint.
Older checkpoints recover them from their saved input series, without rescaling
flow a second time. If the first interval has a missing input and no previous
value is available, startup reports an error rather than choosing zero or using
a future observation. Invalid negative/non-finite numeric inputs still error.

The collection frontier now uses the newest recorded acquisition among mapped
inputs (including quality-error records), so one missing sensor does not block
an initialized model. It does not advance beyond the last complete collected
interval: if all collection stops, the model waits. These queries retain the
existing LimitTime polling cadence.

The live status displays model lag, available-interval backlog, the collection
frontier and its last query time, plus the variables held in the last completed
interval. It also reports the last interval's model/transfer, database-wait and
checkpoint durations, and the latest history-query duration. Timings measure
wall time; database-wait time measures only the flush wait because writes also
run concurrently. The first model timing includes native initialization. These
metrics do not change solver steps or sampling frequency.


### Resume with database catch-up

All `Resume a saved simulation` requests now restore the checkpoint's model,
state, mapping, LimitTime, run ID and result arrays, then replay database sensor
intervals after the saved model boundary. This includes checkpoints originally
created in direct Live mode. Resuming does not alter the saved bundle; the next
successfully completed interval atomically replaces it as before.

Each resume starts a new replay cursor at zero while native SUMO time continues
from `simulated_ms`. The saved `model_time_offset_ms` links the two clocks, so
multiple resumes and legacy partial final intervals do not duplicate, skip or
shift model timestamps. New bundles store `sensor_boundary_at`. For older
direct-live bundles, the last sensor-read timestamp plus LimitTime identifies
the end of the already-computed interval. If no sensor timestamp exists, the
save time is used as an explicitly labelled approximate boundary.

Replay runs without wall-clock pacing until collected data is exhausted. The
same SUMO job then waits for new complete collected intervals using the existing
LimitTime polling cadence. Missing inputs retain their previous model values.
No fresh OPC snapshot bypasses database replay. The history database from a
saved history run is retained; direct-live conversions use
`SUMO_HISTORY_DATABASE` (default `sumo_web_database`). A collector and database
access are therefore required for resume, even for formerly direct-live runs.
The displayed history interval count restarts at each resume; saved results and
native accumulated simulation time are retained.

### Realtime effluent/reactor comparisons

Realtime plots retain Effluent1 COD/TP/NHx/NOx and reactor CSTR3_10/CSTR4_10
NHx/NOx, hide reactor COD/TP, and add CSTR3_4/CSTR4_4 SNHx/SNOx. Offline output
choices are unchanged. Newly subscribed outputs are blank for old saved samples;
resuming appends new samples without fabricating earlier model values.

Two measured nitrate curves use the existing collector CSV mappings:

- CSTR3_4: `SiemensEth.PLC200.II_anoxic_nitrate`.
- CSTR3_10: `SiemensEth.PLC200.II_aerobic_nitrate`.

No CSTR4 or NHx sensor is inferred from another tank. These read-only comparisons
query good numeric `raw_data` measurements from `sumo_web_database` and do
not assign sensor values to SUMO. Nitrate measurements are labelled separately
from simulated SNOx. Dotted lines/markers use the corresponding model-line color
and the same browser-local time axis. Missing observations remain null gaps.

The separate comparison endpoint excludes data beyond the latest displayed model
time. Queries refresh no faster than once per selected LimitTime (minimum one
minute), independently of two-second result polling. Interval means are labelled;
long runs use a larger multiple of LimitTime to bound each series to 5,000 points.
Database comparison failures report a chart message without stopping simulation.
The collector must be writing these mapped tags into `sumo_web_database`.
Set `SUMO_COMPARISON_DATABASE` only to explicitly override this measurement
source. It is independent of `SUMO_HISTORY_DATABASE`, `MYSQL_DATABASE`, and
the database stored in a model checkpoint. Previously saved plot selections are respected;
select the new variables in the Effluent pollutants dropdown if needed.

### Replacing results when starting a new historical run

A new Historical data → Live run replaces **all previous SUMO simulation results**
in its history database (normally `sumo_web_database`), including timestamps outside
the new replay range. It does not append another run to the `sumo simulation` view.
Replacement happens once, in the same InnoDB transaction as the first successfully
written sample: old `sumo_samples` and their cascading `sumo_values`, followed by old
`sumo_runs`, are deleted. Startup without a successful sample leaves old results
intact; a failed replacement transaction rolls back both the new sample and deletes.
Raw sensor data/mappings and model/variable catalogs are retained. The view definition
and local-time display settings are unchanged. Download any old results you want to
keep before starting a new historical run.

Resume a saved simulation retains its run ID and appends/upserts results; it never
requests this cleanup, even for a checkpoint at simulation time zero. Replacement
is not inferred from timestamps. Existing running processes pick up this behavior
only after the backend code is restarted and a new historical run is started.
