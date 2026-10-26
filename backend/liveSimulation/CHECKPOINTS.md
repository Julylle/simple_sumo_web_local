# Live SUMO recovery

Each completed LimitTime interval saves the full SUMO state before reading the next sensor snapshot or advancing the model. The server retains one recovery bundle: `backend/live_states/latest_checkpoint.zip`. Set `SUMO_LIVE_STATE_DIR` to use another durable folder. For container deployments, mount that directory on a persistent volume.

The bundle contains the exact `.sumo` project, state XML, simulation time, sensor mappings, interval and save timestamp. It includes uploaded models so recovery does not depend on the temporary model-upload registry surviving a restart. Cumulative output samples are included in `results.json`, atomically saved alongside the matching model state. Older bundles without results remain resumable, but their past samples cannot be reconstructed.

A new bundle is written and flushed to a temporary file before atomically replacing the previous complete bundle. Interrupted writes and solver/sensor errors leave the last complete checkpoint available. An incomplete `.pending` file is ignored during recovery and overwritten on the next save. No per-interval archive is accumulated. Previously created per-run XML files are not deleted.

A browser refresh only reconnects to the current server session; it does not stop the worker. Browser drafts and the bounded one-hour sensor preview are stored locally, while simulation output history is stored on the server. Other browsers see the same live output and active mappings. This is a shared session, not a per-user login system. Stop and new-run buttons ask for confirmation; these prompts are not an authorization boundary.

After restarting the backend, saved output is immediately available for plots and CSV download without launching SUMO. To continue calculation, click **Resume latest checkpoint**. The backend restores the saved model and simulation time, rereads sensors, and runs the next interval. Downtime is not replayed and simulation time is not reset to zero. The original run ID and cumulative result arrays are retained; duplicate initial samples at the restored time are ignored. Recovery is explicit, not automatically started on server boot. Normal **Run SUMO** starts from the selected initial state; its first completed interval replaces the old checkpoint.

**Stop SUMO** completes and checkpoints the current interval before stopping. Checkpoint save failures stop the live run rather than advancing without a durable recovery point. A new checkpoint becomes available only after at least one full interval has completed and its save has succeeded.

API: `GET /api/sumo/live/status` includes checkpoint information, including while idle after a restart. `POST /api/sumo/live/resume` starts recovery and rejects an already active run. Use a single backend worker for the live SUMO scheduler.

Live output samples now include `sensor_timestamps`: UTC timestamps captured immediately after the sensor read that supplied their input interval. These are acquisition-completion times, not an estimated simulation-time offset or PLC source timestamps. They survive checkpoint recovery and export as `sensor_read_at_utc` in CSV. The realtime dashboard converts them to the viewing computer’s local time. Legacy samples without recorded timestamps remain in CSV but cannot appear on a dated axis.

## Historical replay followed by live operation

In Step2 choose **Historical data → Live**, enter a local start/end time, and set
LimitTime. The browser sends timezone-qualified UTC timestamps. The end is
exclusive. Use an initial state appropriate for the selected historical start.

The backend reads the `raw_data` / `raw_variables` tables in `sumo_web_database`
using the existing `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, and `MYSQL_PASSWORD`.
`SUMO_HISTORY_DATABASE` can override the history database without changing the
simulation recorder's `MYSQL_DATABASE`. The database account needs SELECT access
to these history tables. No database creation or schema migration is performed.

One indexed, parameterized SQL query computes interval means of good-quality
`numeric_value` readings, matched by both SUMO variable and OPC tag. It uses
`acquired_at` (UTC), not PLC source timestamps. Raw input means receive the same
flow conversion as live OPC inputs, exactly once; `scaled_value` is not scaled
again. Every selected input must have at least one valid reading per interval;
missing intervals fail before creating a SUMO job. The final interval may be
shorter than LimitTime. At most 100,000 intervals may be selected per run.

Replay has no real-time sleeping: each completed boundary publishes output,
flushes any enabled database recorder, saves the latest checkpoint, assigns the
next historical inputs and advances the same scheduler job. Native solver,
checkpoint and database write time still determine throughput. The browser polls
results every two seconds and shows completed/total historical intervals.

After the selected range finishes, a fresh KEPServer snapshot is read and the
same job/state continues at the configured LimitTime with real-time pacing. The
gap between the selected end and now is deliberately not simulated. If KEPServer
is unavailable, the worker stops with an error and retains the completed history
checkpoint. Resume restores that state and tries live operation again.

Checkpoints include the historical selection and number of completed intervals.
Resume during replay re-queries only the remaining historical intervals, then
switches to live. The underlying historical database must therefore remain
available and unchanged for reproducible recovery. Only the latest checkpoint
is retained, including during accelerated replay.
