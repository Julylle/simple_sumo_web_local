import { t, useLanguage } from '../i18n';
import type { InputSeriesKey } from "../api/client";
import type { InputSeriesControls } from "../hooks/useInputSeries";

export function InputSeriesUpload({ seriesKey, label, controls, busy }: {
  seriesKey: InputSeriesKey; label: string; controls: InputSeriesControls; busy: boolean;
}) {
  useLanguage();
  const info = controls.selected[seriesKey] ?? controls.defaults[seriesKey]; 
  const uploading = controls.uploading[seriesKey];
  return <div className="input-series-card">
    <h4>{t(label)}</h4>
    <p>{t(info ? `${info.filename} | ${info.unit}` : t("Loading input series..."))}</p>
    {info && <p>{t(info.count)} {t("points | 0-")}{t(Number(info.end_h.toFixed(4)))} {t("h | values")} {t(Number(info.minimum.toFixed(3)))}-{t(Number(info.maximum.toFixed(3)))}</p>}
    <div className="input-series-actions">
      <label className="secondary">{t(uploading ? t("Importing...") : t("Import Excel"))}
        <input type="file" accept=".xlsx" disabled={busy || uploading} aria-label={t(`Import ${label} Excel time series`)}
          onChange={(event) => { const file = event.target.files?.[0]; if (file) void controls.upload(seriesKey, file); event.target.value = ""; }} />
      </label>
      <a href={`/api/input-series/template/${seriesKey}`}>{t("Download template")}</a>
      {controls.selected[seriesKey] && <button className="secondary" disabled={busy || uploading} onClick={() => controls.restore(seriesKey)}>{t("Use built-in")}</button>}
    </div>
    {controls.errors[seriesKey] && <p role="alert" className="series-error">{t(controls.errors[seriesKey])}</p>}
    {seriesKey.startsWith("airflow") && !controls.selected[seriesKey] && <p>{t("Built-in airflow uses the existing total-airflow split (55% / 26% / 19%). Import a per-reactor measurement to replace it.")}</p>}
  </div>;
}
