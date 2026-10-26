import { t, useLanguage } from '../i18n';
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
  useLanguage();
  if (!value) return null;
  const {input_frontier: frontier, timings} = value;
  return <div>
    <p role="status">{t("Latest model result: ")}{t(local(value.model_at))}{t(" · Behind current time: ")}{t(minutes(value.model_lag_seconds))}{t(" · Available input backlog: ")}{t(minutes(value.backlog_seconds))}</p>
    {frontier.checked_at && <p>{t("Latest database collection: ")}{t(local(frontier.latest_collection_at))}{t(" · Latest complete interval: ")}{t(local(frontier.complete_until))}{t(" · Database checked: ")}{t(local(frontier.checked_at))}</p>}
    {!!frontier.missing_inputs?.length && <p className="alert">{t("No database records for: ")}{t(frontier.missing_inputs.join(', '))}</p>}
    {value.input_lag_seconds != null && value.input_lag_seconds > 180 && <p className="alert">{t("Latest database collection is ")}{t(minutes(value.input_lag_seconds))}{t(" behind current time.")}</p>}
    {!!value.held_inputs?.length && <details><summary>{t("Previous inputs reused at ")}{t(local(value.held_at))}: {t(value.held_inputs.length)}{t(" variables (")}{t(value.held_intervals)}{t(" intervals with reused inputs)")}</summary><p>{t(value.held_inputs.join(', '))}</p></details>}
    {timings.interval_work_seconds != null && <p>{t("Last interval (")}{t(seconds(timings.interval_simulated_seconds))}{t(" simulated): model and transfer ")}{t(seconds(timings.model_seconds))}{t(" · database wait ")}{t(seconds(timings.database_wait_seconds))}{t(" · checkpoint ")}{t(seconds(timings.checkpoint_seconds))}{t(" · total ")}{t(seconds(timings.interval_work_seconds))}{t(" · last history query ")}{t(seconds(timings.history_read_seconds))}</p>}
    {timings.interval_work_seconds != null && timings.interval_simulated_seconds != null && timings.interval_work_seconds > timings.interval_simulated_seconds && <p className="alert">{t("The last interval took longer than its simulated duration; sustained performance at this rate cannot catch up.")}</p>}
  </div>;
}
