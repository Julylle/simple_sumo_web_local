# Live SUMO recovery

Each completed LimitTime interval saves the full SUMO state before reading the next sensor snapshot or advancing the model. The server retains one recovery bundle: `backend/live_states/latest_checkpoint.zip`. Set `SUMO_LIVE_STATE_DIR` to use another durable folder. For container deployments, mount that directory on a persistent volume.

The bundle contains the exact `.sumo` project, state XML, simulation time, sensor mappings, interval and save timestamp. It includes uploaded models so recovery does not depend on the temporary model-upload registry surviving a restart. Historical plot samples are not included.

A new bundle is written and flushed to a temporary file before atomically replacing the previous complete bundle. Interrupted writes and solver/sensor errors leave the last complete checkpoint available. An incomplete `.pending` file is ignored during recovery and overwritten on the next save. No per-interval archive is accumulated. Previously created per-run XML files are not deleted.

After restarting the backend, click **Resume latest checkpoint**. The backend restores the saved model and simulation time, rereads sensors, and runs the next interval. Downtime is not replayed and simulation time is not reset to zero. Recovery is explicit, not automatically started on server boot. Normal **Run SUMO** starts from the selected initial state; its first completed interval replaces the old checkpoint.

**Stop SUMO** completes and checkpoints the current interval before stopping. Checkpoint save failures stop the live run rather than advancing without a durable recovery point. A new checkpoint becomes available only after at least one full interval has completed and its save has succeeded.

API: `GET /api/sumo/live/status` includes checkpoint information, including while idle after a restart. `POST /api/sumo/live/resume` starts recovery and rejects an already active run. Use a single backend worker for the live SUMO scheduler.
