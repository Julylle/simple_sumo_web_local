import { calibrationRanges } from "../config/calibrationRanges";

export interface CalibrationParametersProps {
  parameters: Record<string, string>;
  loaded: boolean;
  error: string;
  busy: boolean;
  onChange: (name: string, value: string) => void;
  onRetry: () => void;
}

export function CalibrationParameters({ parameters, loaded, error, busy, onChange, onRetry }: CalibrationParametersProps) {

  return (
    <div className="chart-card calibration-card">
      <div className="chart-head">
        <div>
          <h3>Kinetic parameter values</h3>
          <p>Edit values, then Run simulation to apply.</p>
        </div>
      </div>
      {/* <p className="calibration-note">KLa parameters scale oxygen transfer from the reactor airflow series. DO is calculated dynamically.</p> */}
      {error ? (
        <div role="alert"><p>{error}</p><button className="secondary" onClick={onRetry}>Retry</button></div>
      ) : loaded ? (
        <div className="calibration-table-scroll" tabIndex={0} aria-label="Initial calibration parameters">
          <table className="calibration-table">
            <thead><tr><th scope="col">Parameter</th><th scope="col">Value</th><th scope="col">Range</th></tr></thead>
            <tbody>{Object.entries(parameters).map(([name, value]) => (
              <tr key={name}><th scope="row">{name}</th><td><input type="number" step="any" min={name.startsWith("K") ? undefined : 0}
                aria-label={`Calibration parameter ${name}`} value={value} disabled={busy}
                onChange={(event) => onChange(name, event.target.value)} /></td>
                <td className="calibration-range">{calibrationRanges[name] ?? "Not provided"}</td></tr>
            ))}</tbody>
          </table>
          <p className="calibration-note">Reference ranges from literature; not enforced as input limits.</p>
        </div>
      ) : <p role="status">Loading calibration parameters…</p>}
    </div>
  );
}
