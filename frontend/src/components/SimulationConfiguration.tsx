import type { Params } from "../api/client";

interface SimulationConfigurationProps {
  parameters: Params;
  busy: boolean;
  dirty: boolean;
  onRun: () => void;
  onReset: () => void;
  onChange: (key: keyof Params, value: number) => void;
}

export function SimulationConfiguration({ parameters, onChange, busy, dirty, onRun, onReset }: SimulationConfigurationProps) {
  return (
    <section className="config-card simulation-settings">
      <div className="section-title">
        <div>
          <h2>Simulation settings</h2>
          <p>Set the simulation duration. Edit process parameters in MLE configuration.</p>
        </div>
              <div className="run-controls">
                {dirty && <span className="dirty">● Parameters changed</span>}
                <button className="secondary" onClick={onReset} disabled={busy}>
                  Reset
                </button>
                <button className="primary" onClick={onRun} disabled={busy}>
                  <span>{busy ? "◌" : "▶"}</span>
                  {busy ? "Running model…" : "Run simulation"}
                </button>
              </div>
      </div>
      <label className="field duration-field">
        <span className="field-label">Simulation duration<small>h</small></span>
        <div className="input-wrap">
          <input type="number" value={parameters.duration_h} min={1} step={1}
            onChange={(event) => onChange("duration_h", Number(event.target.value))} />
          <span>h</span>
        </div>
        <small className="hint">Minimum 1 h; no upper limit</small>
      </label>
      <label className="do-mode-toggle">
        <input type="checkbox" checked={Boolean(parameters.use_do_setpoint)} disabled={busy}
          onChange={(event) => onChange("use_do_setpoint", Number(event.target.checked))} />
        Use DO setpoints
      </label>
      <p className="calibration-note">{parameters.use_do_setpoint
        ? "DO is held at each aerobic zone's setpoint during steady initialization and dynamic simulation. Anoxic DO is fixed at 0 mg/L. Airflow uploads are retained but do not control DO in this mode."
        : "DO is calculated from airflow and oxygen consumption. Enable Use DO setpoints to hold DO at the values entered in each aerobic zone."}</p>
      <p className="calibration-note">Dynamic inputs use the selected Excel time series. Beyond each series end, its final value is held. The initial steady state uses the first value of each input.</p>
    </section>
  );
}
