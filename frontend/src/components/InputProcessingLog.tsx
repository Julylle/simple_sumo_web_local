import { useState } from 'react';
import { t, useLanguage } from '../i18n';

export type InputProcessingRecord = {
  sequence: number; recorded_at: string; start_ms: number; end_ms: number;
  interval_start?: string | null; interval_end?: string | null;
  column: string; node_id: string; model_value: number; treatment?: string;
  replacement_raw_value?: number; reason?: string; raw_value?: number | string | null; negative_count?: number; previous_model_value?: number; invalid_count?: number;
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
    <summary>
      <span className="processing-log-heading">{t('Sensor input processing history')}<span className="processing-log-count">{records.length}</span></span>
      <span className="processing-log-chevron" aria-hidden="true">⌄</span>
    </summary>
    {open && <div className="processing-log-body">
      <p className="processing-log-policy">{t('Negative readings use zero, except Sideflowdivider3 Qpumped_target uses 0.001 before scaling. Invalid or failed readings reuse the previous model input. Records are saved with the checkpoint and restored on Resume.')}</p>
      {!records.length ? <div className="processing-log-empty">{t('No sensor input adjustments recorded.')}</div> : <>
        <div className="processing-log-toolbar">
          <span className="processing-log-order">{t('Newest first')} · {t('Records')} {Math.max(1, records.length - (current + 1) * 100 + 1)}–{records.length - current * 100} / {records.length}</span>
          <nav className="processing-log-pagination" aria-label={t('Processing history pages')}>
            <button type="button" className="secondary" disabled={!current} onClick={() => setPage(current - 1)}>{t('Newer records')}</button>
            <span>{current + 1} / {pages}</span>
            <button type="button" className="secondary" disabled={current + 1 >= pages} onClick={() => setPage(current + 1)}>{t('Older records')}</button>
          </nav>
        </div>
        <div className="processing-log-scroll" tabIndex={0} role="region" aria-label={t('Sensor input processing history')}>
          <table className="processing-log-table">
            <colgroup><col className="processing-col-time"/><col className="processing-col-sensor"/><col className="processing-col-action"/><col className="processing-col-reason"/><col className="processing-col-value"/></colgroup>
            <thead><tr>{['Simulation interval', 'Sensor / model input', 'Processing', 'Reason / original reading', 'Applied model value'].map(label => <th scope="col" key={label}>{t(label)}</th>)}</tr></thead>
            <tbody>{rows.map(row => {
              const negative = row.treatment === 'negative_to_minimum' || row.treatment === 'negative_to_zero';
              const parts = row.column.split('__');
              const shortName = parts.length > 2 ? parts.slice(2).filter(part => part !== 'param').join(' · ') : row.column;
              return <tr key={row.sequence}>
                <td>
                  <span className="processing-log-sequence">#{row.sequence}</span>
                  <div className="processing-log-interval">{row.interval_start
                    ? <><time dateTime={row.interval_start}>{local(row.interval_start)}</time><span className="processing-log-end">→ {local(row.interval_end)}</span></>
                    : <span>{row.start_ms / 1000}–{row.end_ms / 1000} {t('s')}</span>}</div>
                  <div className="processing-log-recorded"><span>{t('Recorded at')}</span><time dateTime={row.recorded_at}>{local(row.recorded_at)}</time></div>
                </td>
                <td>
                  <strong className="processing-log-sensor-name">{shortName}</strong>
                  <code className="processing-log-model-id">{row.column}</code>
                  <code className="processing-log-node">{row.node_id}</code>
                </td>
                <td><span className={`processing-log-treatment ${negative ? 'is-replaced' : 'is-held'}`}>{t(row.treatment === 'negative_to_minimum' ? 'Negative → 0.001' : row.treatment === 'negative_to_zero' ? 'Negative → zero' : row.treatment === 'held_previous_samples' ? 'Invalid samples → previous value, then average' : 'Reuse previous value')}</span></td>
                <td>
                  <p className="processing-log-reason">{t(row.reason || 'No valid recorded input in interval')}</p>
                  <dl className="processing-log-facts">
                    {row.raw_value != null && <div><dt>{t('Original reading')}</dt><dd>{String(row.raw_value)}</dd></div>}
                    {row.replacement_raw_value != null && <div><dt>{t('Replacement raw value')}</dt><dd>{row.replacement_raw_value}</dd></div>}
                    {row.negative_count != null && <div><dt>{t('Negative samples')}</dt><dd>{row.negative_count}</dd></div>}
                    {row.invalid_count != null && row.invalid_count > 0 && <div><dt>{t('Invalid samples')}</dt><dd>{row.invalid_count}</dd></div>}
                  </dl>
                </td>
                <td className="processing-log-value-cell">
                  <strong className="processing-log-value">{row.model_value}</strong>
                  {row.previous_model_value != null && <div className="processing-log-previous"><span>{t('Previous model value')}</span><span>{row.previous_model_value}</span></div>}
                </td>
              </tr>;
            })}</tbody>
          </table>
        </div>
      </>}
    </div>}
  </details>;
}
