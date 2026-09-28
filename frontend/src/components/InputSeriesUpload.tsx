import type { InputSeriesKey } from "../api/client";
import type { InputSeriesControls } from "../hooks/useInputSeries";

export function InputSeriesUpload({ seriesKey, label, controls, busy }: {
  seriesKey: InputSeriesKey; label: string; controls: InputSeriesControls; busy: boolean;
}) {
  const info = controls.selected[seriesKey] ?? controls.defaults[seriesKey];
  const uploading = controls.uploading[seriesKey];
  return <div className="input-series-card">
    <h4>{label}</h4>
    <p>{info ? `${info.filename} | ${info.unit}` : "Loading input series..."}</p>
    {info && <p>{info.count} points | 0-{Number(info.end_h.toFixed(4))} h | values {Number(info.minimum.toFixed(3))}-{Number(info.maximum.toFixed(3))}</p>}
    <div className="input-series-actions">
      <label className="secondary">{uploading ? "Importing..." : "Import Excel"}
        <input type="file" accept=".xlsx" disabled={busy || uploading} aria-label={`Import ${label} Excel time series`}
          onChange={(event) => { const file = event.target.files?.[0]; if (file) void controls.upload(seriesKey, file); event.target.value = ""; }} />
      </label>
      <a href={`/api/input-series/template/${seriesKey}`}>Download template</a>
      {controls.selected[seriesKey] && <button className="secondary" disabled={busy || uploading} onClick={() => controls.restore(seriesKey)}>Use built-in</button>}
    </div>
    {controls.errors[seriesKey] && <p role="alert" className="series-error">{controls.errors[seriesKey]}</p>}
    {seriesKey.startsWith("airflow") && !controls.selected[seriesKey] && <p>Built-in airflow uses the existing total-airflow split (55% / 26% / 19%). Import a per-reactor measurement to replace it.</p>}
  </div>;
}
