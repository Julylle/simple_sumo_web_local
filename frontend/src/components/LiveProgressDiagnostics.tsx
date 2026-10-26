export type LiveDiagnostics = {
  observed_at: string; model_at: string | null; model_lag_seconds: number | null;
  held_inputs: string[]; held_at: string | null; held_intervals: number;
  input_lag_seconds: number | null; backlog_seconds: number | null;
  input_frontier: {checked_at?: string; latest_collection_at?: string | null; complete_until?: string | null;
    limiting_inputs?: string[]; missing_inputs?: string[]};
  timings: {model_seconds?: number; database_wait_seconds?: number; checkpoint_seconds?: number;
    interval_work_seconds?: number; interval_simulated_seconds?: number; history_read_seconds?: number};
};
const minutes = (value: number | null | undefined) => value == null ? '—' : `${(value / 60).toFixed(1)} min`;
const seconds = (value: number | undefined) => value == null ? '—' : `${value.toFixed(1)} s`;
const local = (value: string | null | undefined) => value ? new Date(value).toLocaleString() : '—';
export function LiveProgressDiagnostics({value}: {value?: LiveDiagnostics}) {
  if (!value) return null;
  const {input_frontier: frontier, timings} = value;
  return <div>
    <p role="status">Latest model result: {local(value.model_at)} · Behind current time: {minutes(value.model_lag_seconds)} · Available input backlog: {minutes(value.backlog_seconds)}</p>
    {frontier.checked_at && <p>Latest database collection: {local(frontier.latest_collection_at)} · Latest complete interval: {local(frontier.complete_until)} · Database checked: {local(frontier.checked_at)}</p>}
    {!!frontier.missing_inputs?.length && <p className="alert">No database records for: {frontier.missing_inputs.join(', ')}</p>}
    {value.input_lag_seconds != null && value.input_lag_seconds > 180 && <p className="alert">Latest database collection is {minutes(value.input_lag_seconds)} behind current time.</p>}
    {!!value.held_inputs?.length && <details><summary>Previous inputs reused at {local(value.held_at)}: {value.held_inputs.length} variables ({value.held_intervals} intervals with reused inputs)</summary><p>{value.held_inputs.join(', ')}</p></details>}
    {timings.interval_work_seconds != null && <p>Last interval ({seconds(timings.interval_simulated_seconds)} simulated): model and transfer {seconds(timings.model_seconds)} · database wait {seconds(timings.database_wait_seconds)} · checkpoint {seconds(timings.checkpoint_seconds)} · total {seconds(timings.interval_work_seconds)} · last history query {seconds(timings.history_read_seconds)}</p>}
    {timings.interval_work_seconds != null && timings.interval_simulated_seconds != null && timings.interval_work_seconds > timings.interval_simulated_seconds && <p className="alert">The last interval took longer than its simulated duration; sustained performance at this rate cannot catch up.</p>}
  </div>;
}
