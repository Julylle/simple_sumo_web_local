import { useState } from 'react';
import { t, useLanguage } from '../i18n';

export type InputProcessingRecord = {
  sequence: number; recorded_at: string; start_ms: number; end_ms: number;
  interval_start?: string | null; interval_end?: string | null;
  column: string; node_id: string; model_value: number; treatment?: string;
  reason?: string; raw_value?: number | string | null; negative_count?: number; previous_model_value?: number; invalid_count?: number;
};
const local = (value?: string | null) => value ? new Date(value).toLocaleString() : '—';
export function InputProcessingLog({records = []}: {records?: InputProcessingRecord[]}) {
  useLanguage();
  const [page, setPage] = useState(0);
  const [open, setOpen] = useState(false);
  const pages = Math.max(1, Math.ceil(records.length / 100));
  const current = Math.min(page, pages - 1);
  const rows = records.slice(Math.max(0, records.length - (current + 1) * 100), records.length - current * 100).reverse();
  return <details className="sensor-mapping-list input-processing-log" onToggle={e => setOpen(e.currentTarget.open)}>
    <summary>{t('Sensor input processing history')} · {records.length}</summary>
    {open && <>
      <p>{t('Negative readings use zero. Invalid or failed readings reuse the previous model input. Records are saved with the checkpoint and restored on Resume.')}</p>
      {!records.length ? <p>{t('No sensor input adjustments recorded.')}</p> : <>
        <div className="sensor-actions">
          <button type="button" className="secondary" disabled={!current} onClick={() => setPage(current - 1)}>{t('Newer records')}</button>
          <span>{current + 1} / {pages}</span>
          <button type="button" className="secondary" disabled={current + 1 >= pages} onClick={() => setPage(current + 1)}>{t('Older records')}</button>
        </div>
        <div style={{overflowX:'auto', maxHeight:440}}><table>
          <thead><tr>{['Simulation interval', 'Sensor / model input', 'Processing', 'Reason / original reading', 'Applied model value'].map(label => <th key={label}>{t(label)}</th>)}</tr></thead>
          <tbody>{rows.map(row => <tr key={row.sequence}>
            <td>{row.interval_start ? <>{local(row.interval_start)} → {local(row.interval_end)}</> : <>{row.start_ms / 1000}–{row.end_ms / 1000} {t('s')}</>}<br/><small>{t('Recorded at')}: {local(row.recorded_at)}</small></td>
            <td>{row.column}<br/><small>{row.node_id}</small></td>
            <td>{t(row.treatment === 'negative_to_zero' ? 'Negative → zero' : row.treatment === 'held_previous_samples' ? 'Invalid samples → previous value, then average' : 'Reuse previous value')}</td>
            <td>{t(row.reason || 'No valid recorded input in interval')}{row.raw_value != null && <div>{String(row.raw_value)}</div>}{row.negative_count != null && <div>{t('Negative samples')}: {row.negative_count}</div>}</td>
            <td>{row.model_value}{row.previous_model_value != null && <div><small>{t('Previous model value')}: {row.previous_model_value}</small></div>}</td>
          </tr>)}</tbody>
        </table></div>
      </>}
    </>}
  </details>;
}
