import { t, useLanguage } from '../i18n';
import { calibrationRanges } from "../config/calibrationRanges";

export interface CalibrationParametersProps {
  parameters: Record<string, string>;
  loaded: boolean;
  error: string;
  busy: boolean;
  onChange: (name: string, value: string) => void;
  onRetry: () => void;
  description?: string;
}

export function CalibrationParameters({ parameters, loaded, error, busy, onChange, onRetry, description = t("Edit values, then Run simulation to apply.") }: CalibrationParametersProps) {
  useLanguage();

  return (
    <div className="chart-card calibration-card">
      <div className="chart-head">
        <div>
          <h3>{t("Kinetic parameter values")}</h3>
          <p>{t(description)}</p>
        </div>
      </div>
      {/* <p className="calibration-note">KLa parameters scale oxygen transfer from the reactor airflow series. DO is calculated dynamically.</p> */}
      {error ? (
        <div role="alert"><p>{t(error)}</p><button className="secondary" onClick={onRetry}>{t("Retry")}</button></div>
      ) : loaded ? (
        <div className="calibration-table-scroll" tabIndex={0} aria-label={t("Initial calibration parameters")}>
          <table className="calibration-table">
            <thead><tr><th scope="col">{t("Parameter")}</th><th scope="col">{t("Value")}</th><th scope="col">{t("Range")}</th></tr></thead>
            <tbody>{Object.entries(parameters).map(([name, value]) => (
              <tr key={name}><th scope="row">{t(name)}</th><td><input type="number" step="any" min={name.startsWith("K") ? undefined : 0}
                aria-label={t(`Calibration parameter ${name}`)} value={value} disabled={busy}
                onChange={(event) => onChange(name, event.target.value)} /></td>
                <td className="calibration-range">{t(calibrationRanges[name] ?? t("Not provided"))}</td></tr>
            ))}</tbody>
          </table>
          <p className="calibration-note">{t("Reference ranges from literature; not enforced as input limits.")}</p>
        </div>
      ) : <p role="status">{t("Loading calibration parameters…")}</p>}
    </div>
  );
}
