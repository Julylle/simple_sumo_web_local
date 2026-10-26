# Live SUMO recovery

Each completed LimitTime interval saves the full SUMO state before reading the next sensor snapshot or advancing the model. The server retains one recovery bundle: `backend/live_states/latest_checkpoint.zip`. Set `SUMO_LIVE_STATE_DIR` to use another durable folder. For container deployments, mount that directory on a persistent volume.

The bundle contains the exact `.sumo` project, state XML, simulation time, sensor mappings, interval and save timestamp. It includes uploaded models so recovery does not depend on the temporary model-upload registry surviving a restart. Cumulative output samples are included in `results.json`, atomically saved alongside the matching model state. Older bundles without results remain resumable, but their past samples cannot be reconstructed.

A new bundle is written and flushed to a temporary file before atomically replacing the previous complete bundle. Interrupted writes and solver/sensor errors leave the last complete checkpoint available. An incomplete `.pending` file is ignored during recovery and overwritten on the next save. No per-interval archive is accumulated. Previously created per-run XML files are not deleted.

A browser refresh only reconnects to the current server session; it does not stop the worker. Browser drafts and the bounded one-hour sensor preview are stored locally, while simulation output history is stored on the server. Other browsers see the same live output and active mappings. This is a shared session, not a per-user login system. Stop and new-run buttons ask for confirmation; these prompts are not an authorization boundary.

After restarting the backend, saved output is immediately available for plots and CSV download without launching SUMO. To continue calculation, choose **Resume a saved simulation** under **Simulation mode**, then click **Resume SUMO**. The backend restores the saved model and simulation time. Direct live mode rereads sensors without replaying downtime; database-following mode processes unconsumed collected intervals. Simulation time is not reset to zero. The original run ID and cumulative result arrays are retained; duplicate initial samples at the restored time are ignored. Recovery is explicit, not automatically started on server boot. Normal **Run SUMO** starts from the selected initial state; its first completed interval replaces the old checkpoint.

**Stop SUMO** completes and checkpoints the current interval before stopping. Checkpoint save failures stop the live run rather than advancing without a durable recovery point. A new checkpoint becomes available only after at least one full interval has completed and its save has succeeded.

API: `GET /api/sumo/live/status` includes checkpoint information, including while idle after a restart. `POST /api/sumo/live/resume` starts recovery and rejects an already active run. Use a single backend worker for the live SUMO scheduler.

Live output samples now include `sensor_timestamps`: UTC timestamps captured immediately after the sensor read that supplied their input interval. These are acquisition-completion times, not an estimated simulation-time offset or PLC source timestamps. They survive checkpoint recovery and export as `sensor_read_at_utc` in CSV. The realtime dashboard converts them to the viewing computer’s local time. Legacy samples without recorded timestamps remain in CSV but cannot appear on a dated axis.

## Historical replay followed by live operation

In Step2 choose **Historical data → Live**, enter a local **start time** and set
LimitTime. There is no end-time input. Use an initial state appropriate for the
selected start. The browser sends timezone-qualified UTC timestamps.

The backend reads `raw_data` / `raw_variables` in `sumo_web_database` using
`MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, and `MYSQL_PASSWORD`.
`SUMO_HISTORY_DATABASE` can override the history database independently of the
simulation recorder's `MYSQL_DATABASE`. The account needs SELECT access to raw history and write access to simulation result/catalog tables. No
schema migration or database creation is performed.

The selected inputs' latest good acquisition timestamps determine the newest
complete interval: all inputs must have reached its end. The newest partial
interval waits for more collection. History is loaded in chunks of at most 2,000
intervals with indexed latest-reading lookups and SQL interval averaging. Means
use good-quality raw `numeric_value` samples by `acquired_at` UTC, matched by both
SUMO variable and OPC tag, with the same one-time flow scaling as live inputs.
Missing required values in older, complete intervals produce an explicit error;
they are not filled with zero or skipped.

Replay runs without real-time sleeping. After each chunk it checks again for
newly collected data, so data arriving during replay is also simulated. Each
completed interval updates results, commits the required simulation recorder to the same database and replaces the
latest disk checkpoint. The browser polls results every two seconds.

Once caught up, the mode becomes live and displays
`waiting_for_sensor_collection`. The same SUMO job stays paused at the last
boundary. Every two seconds the backend checks for the next complete LimitTime
interval; once collected, that interval runs and the process repeats. This mode
continues using the database collector's records, not a direct OPC snapshot.
Keep `python -m database.collector` / `runCollector.ps1` running. If acquisition
stops, simulation waits without advancing; Stop remains available. Database
connection errors fail the run with the previous checkpoint retained.

Resume restores the cursor (completed interval count), same state, mapping and
start time; it loads only unprocessed intervals. Data collected during downtime
is replayed without gaps. The database must remain available and unchanged for
reproducible recovery. Old fixed-end checkpoints retain their original behavior.
The ordinary **Live · continuous (1×)** mode still reads OPC directly.
